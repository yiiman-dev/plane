# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Order creation, gateway selection and idempotent callback processing."""

# Python imports
import logging
from datetime import datetime
from typing import Any, Dict, Optional

# Django imports
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

# Module imports
from plane.billing.gateways.base import GatewayError, GatewayStatus, GatewayUnavailable, GatewayValidationError
from plane.billing.gateways.registry import build_adapter
from plane.billing.models import (
    BillingCycle,
    Invoice,
    InvoiceStatus,
    PaymentGateway,
    PaymentTransaction,
    Plan,
    Subscription,
    SubscriptionStatus,
    TransactionStatus,
)
from plane.billing.services import hold as hold_service
from plane.billing.services.router import GatewayRouter
from plane.billing.services.tasks import max_verify_attempts, schedule_verification_retry
from plane.billing.services.upgrade import RenewalLockedError, UpgradeQuote, quote_for_workspace
from plane.db.models import Workspace

logger = logging.getLogger("plane.billing")

CALLBACK_PATH_TEMPLATE = "/api/billing/callback/{code}/"
RESULT_PATH_TEMPLATE = "/billing/result/{transaction_id}/"
DEFAULT_CALLBACK_URLS = {
    "zarinpal": "/api/billing/callback/zarinpal/",
    "payping": "/api/billing/callback/payping/",
    "zibal": "/api/billing/callback/zibal/",
    "digipay": "/api/billing/callback/digipay/",
}


class BillingError(Exception):
    """Raised when a payment cannot be created or processed."""


def get_gateway_row(code: str) -> PaymentGateway:
    gateway = PaymentGateway.objects.filter(code=code).first()
    if gateway is None:
        gateway = PaymentGateway.all_objects.filter(code=code).first()
    if gateway is None:
        raise BillingError(f"Unknown payment gateway: {code}")
    return gateway


def web_base_url() -> str:
    return str(getattr(settings, "WEB_URL", "") or "").rstrip("/")


def build_callback_url(code: str, gateway: Optional[PaymentGateway] = None) -> str:
    """Return the callback URL registered in the gateway panel."""
    override = ""
    if gateway is not None:
        override = (gateway.extra_config or {}).get("callback_url") or ""
    if override:
        return override if override.startswith("http") else f"{web_base_url()}{override}"
    base = web_base_url()
    path = DEFAULT_CALLBACK_URLS.get(code, CALLBACK_PATH_TEMPLATE.format(code=code))
    return f"{base}{path}"


def build_result_url(transaction: PaymentTransaction) -> str:
    base = web_base_url()
    return f"{base}{RESULT_PATH_TEMPLATE.format(transaction_id=transaction.id)}"


def build_zibal_start_url(track_id: str) -> str:
    """Absolute Zibal start URL built from configuration only.

    Zibal matches the Referer of the start request against the domain that is
    registered in its panel, therefore the browser is sent through our own
    intermediate endpoint which then redirects to this fixed, configuration
    derived target. A caller supplied URL is never honoured.
    """
    adapter = build_adapter(get_gateway_row("zibal"))
    if not hasattr(adapter, "start_url"):
        raise BillingError("The Zibal gateway does not expose a start URL builder.")
    return adapter.start_url(track_id)


@db_transaction.atomic
def issue_invoice(
    *,
    user,
    plan: Plan,
    seats: int,
    cycle: str,
    notes: str = "",
    workspace_slug: str = "",
    quote: Optional[UpgradeQuote] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
    due_at: Optional[datetime] = None,
) -> Invoice:
    seats = max(plan.min_seats, min(int(seats or 0), plan.max_seats))
    subtotal = plan.calculate_subtotal(seats, cycle)
    credit = quote.credit_applied_toman if quote is not None else 0
    now = timezone.now()
    due = due_at or (now + timezone.timedelta(days=365 if cycle == BillingCycle.YEARLY else 31))
    # the workspace travels on the invoice metadata so the gateway callback, which only sees
    # the transaction row, can still bind the resulting subscription to that workspace
    metadata = {"workspace_slug": workspace_slug} if workspace_slug else {}
    if quote is not None:
        # the callback rebuilds the period from this, it must not re-price the order
        metadata["proration"] = {
            "credit_applied_toman": credit,
            "new_ends_at": quote.new_ends_at.isoformat() if quote.new_ends_at else None,
        }
    if extra_metadata:
        metadata.update(extra_metadata)
    return Invoice.objects.create(
        number=Invoice.generate_number(),
        user=user,
        plan=plan,
        seats=seats,
        cycle=cycle,
        subtotal_toman=subtotal,
        discount_toman=credit,
        total_toman=subtotal - credit,
        status=InvoiceStatus.ISSUED,
        issued_at=now,
        due_at=due,
        notes=notes,
        metadata=metadata,
    )


def create_payment_order(
    *,
    user,
    plan_code: str,
    seats: int,
    cycle: str,
    mobile: str = "",
    notes: str = "",
    workspace_slug: str = "",
) -> dict:
    """Issue an invoice, select a gateway and create the payment."""
    plan = Plan.objects.filter(code=plan_code, is_active=True).first()
    if plan is None:
        raise BillingError("The requested plan is not available.")
    if cycle not in (BillingCycle.MONTHLY, BillingCycle.YEARLY):
        raise BillingError("Invalid billing cycle.")
    try:
        seats = int(seats)
    except (TypeError, ValueError) as exc:
        raise BillingError("Invalid seat count.") from exc
    if seats < plan.min_seats:
        raise BillingError(f"The plan requires at least {plan.min_seats} seat(s).")
    if seats > plan.max_seats:
        raise BillingError(f"The plan allows at most {plan.max_seats} seat(s).")

    # the lock window is checked again here: a quote shown earlier may be stale
    quote = None
    workspace = Workspace.objects.filter(slug=workspace_slug).first() if workspace_slug else None
    if workspace is not None:
        try:
            quote = quote_for_workspace(workspace=workspace, plan=plan, seats=seats, cycle=cycle)
        except RenewalLockedError as exc:
            raise BillingError(str(exc)) from exc

    invoice = issue_invoice(
        user=user,
        plan=plan,
        seats=seats,
        cycle=cycle,
        notes=notes,
        workspace_slug=workspace_slug,
        quote=quote,
    )
    description = f"{plan.name} - {invoice.number}"
    router = GatewayRouter()
    try:
        candidates = router.candidates()
        if not candidates:
            raise BillingError("No payment gateway is currently enabled.")

        attempts_per_gateway = {}
        errors = []
        for candidate in candidates:
            adapter = candidate.adapter()
            result = None
            # the admin limit caps how often a single gateway is contacted for
            # one payment, every attempt still has to answer to fail over
            for _ in range(max(1, int(router.config.max_attempts_per_gateway or 1))):
                attempts_per_gateway[candidate.code] = attempts_per_gateway.get(candidate.code, 0) + 1
                try:
                    result = adapter.create_payment(
                        amount_toman=invoice.total_toman,
                        description=description,
                        order_id=invoice.number,
                        callback=build_callback_url(candidate.code, candidate.gateway),
                        mobile=mobile or "",
                    )
                    break
                except GatewayUnavailable as exc:
                    # failover is only allowed for unavailable / processing gateways
                    errors.append(f"{candidate.code}: {exc}")
                except GatewayValidationError as exc:
                    # a rejected request is a definitive answer and never a failover
                    logger.warning("billing: gateway %s rejected the order: %s", candidate.code, exc)
                    raise BillingError(str(exc)) from exc
                except GatewayError as exc:
                    # an unexpected adapter failure must not silently switch gateway
                    logger.exception("billing: gateway %s raised an unexpected error", candidate.code)
                    raise BillingError(f"{candidate.code}: {exc}") from exc
            if result is None:
                continue

            transaction = PaymentTransaction.objects.create(
                invoice=invoice,
                user=user,
                gateway_code=candidate.code,
                gateway_token=str(result.token),
                amount_toman=invoice.total_toman,
                status=TransactionStatus.REDIRECTED,
                meta={
                    "routing_reason": candidate.reason,
                    "routing_strategy": router.config.strategy,
                    **(result.meta or {}),
                },
            )
            router.record_selection(candidate)
            return {
                "invoice": invoice,
                "transaction": transaction,
                "redirect_url": result.redirect_url,
            }
        raise BillingError("No payment gateway could start this payment: " + "; ".join(errors))
    except Exception:
        # the invoice is already issued at this point, so any rejected order
        # must cancel it instead of leaving a dangling issued invoice behind
        cancel_invoice(invoice)
        raise


def cancel_invoice(invoice: Optional[Invoice]) -> None:
    if invoice is None or invoice.status in (InvoiceStatus.PAID, InvoiceStatus.CANCELLED):
        return
    invoice.status = InvoiceStatus.CANCELLED
    invoice.save(update_fields=["status", "updated_at"])


def find_transaction(gateway_code: str, token: str) -> Optional[PaymentTransaction]:
    if not token:
        return None
    token = str(token)
    transaction = PaymentTransaction.objects.filter(gateway_code=gateway_code, gateway_token=token).first()
    if transaction is not None:
        return transaction
    # some gateways echo their own reference instead of the ticket token, the
    # ids the merchant stored on the transaction are matched as a fallback
    for key in ("payment_ref_id", "provider_id", "invoice_number"):
        transaction = PaymentTransaction.objects.filter(gateway_code=gateway_code, **{f"meta__{key}": token}).first()
        if transaction is not None:
            return transaction
    return None


def locate_transaction(gateway_code: str, adapter, payload: dict) -> Optional[PaymentTransaction]:
    """Resolve the transaction a raw callback belongs to."""
    payload = payload or {}
    values = [adapter.extract_callback_token(payload)]
    values.extend(adapter.extract_callback_refs(payload))
    for value in values:
        transaction = find_transaction(gateway_code, value)
        if transaction is not None:
            return transaction
    return None


def resolve_invoice_workspace(invoice: Invoice) -> Optional[Workspace]:
    """The workspace an order was bought for, or None for a workspace-less order."""

    metadata = invoice.metadata if isinstance(invoice.metadata, dict) else {}
    slug = str(metadata.get("workspace_slug") or "").strip()
    if not slug:
        return None
    return Workspace.objects.filter(slug=slug).first()


def _renewal_now_locked(invoice: Invoice) -> bool:
    workspace = resolve_invoice_workspace(invoice)
    if workspace is None or invoice.plan is None:
        return False
    try:
        quote_for_workspace(workspace=workspace, plan=invoice.plan, seats=invoice.seats, cycle=invoice.cycle)
    except RenewalLockedError:
        return True
    return False


def _activate_subscription(invoice: Invoice, transaction: PaymentTransaction) -> None:
    now = timezone.now()
    period = timezone.timedelta(days=365 if invoice.cycle == BillingCycle.YEARLY else 31)
    ends_at = now + period
    # An order that kept the existing end date (a downgrade or sideways move) records
    # new_ends_at as None, and the subscription must not be extended by paying for it.
    keeps_end_date = False
    proration = (invoice.metadata or {}).get("proration") if isinstance(invoice.metadata, dict) else None
    if proration is not None and proration.get("new_ends_at") is None:
        keeps_end_date = True
    # A plan is a workspace entitlement, so the subscription is bound to the workspace the
    # order was raised for. An order without one keeps the older owner level behaviour.
    workspace = resolve_invoice_workspace(invoice)
    if workspace is not None:
        # a purchase for another plan replaces the workspace's live subscription
        previous = Subscription.objects.filter(workspace=workspace, status=SubscriptionStatus.ACTIVE).exclude(
            plan=invoice.plan
        )
        if keeps_end_date:
            latest = previous.order_by("-ends_at").first()
            if latest is not None and latest.ends_at:
                ends_at = latest.ends_at
        previous.update(status=SubscriptionStatus.EXPIRED)
    queryset = Subscription.objects.filter(user=invoice.user, plan=invoice.plan, status=SubscriptionStatus.ACTIVE)
    if workspace is not None:
        queryset = queryset.filter(workspace=workspace)
    subscription = queryset.order_by("-created_at").first()
    if subscription is None:
        Subscription.objects.create(
            user=invoice.user,
            plan=invoice.plan,
            seats=invoice.seats,
            cycle=invoice.cycle,
            status=SubscriptionStatus.ACTIVE,
            starts_at=now,
            ends_at=ends_at,
            source_transaction=transaction,
            workspace=workspace,
        )
        return
    subscription.seats = invoice.seats
    subscription.cycle = invoice.cycle
    subscription.starts_at = now
    subscription.ends_at = ends_at
    subscription.source_transaction = transaction
    subscription.workspace = workspace
    subscription.save()


def _settle_hold(transaction: PaymentTransaction, description: str) -> None:
    """A parked payment got its answer: the hold ends and the wallet is not credited.

    Paid means the money became a plan; failed means there never was any. Either
    way the amount leaves the hold account without passing through the wallet.
    """
    if transaction.held_at is not None:
        hold_service.close_hold(transaction, description=description)


def _fail(transaction: PaymentTransaction, reason: str, message: str = "") -> dict:
    """The gateway (or the payer) said no. A confirmed failure is never retried."""
    transaction.mark_status(TransactionStatus.FAILED, reason)
    transaction.save()
    _settle_hold(transaction, reason or "Payment failed.")
    return _serialize(transaction, message=message or reason or "Payment failed.")


def _leave_ambiguous(transaction: PaymentTransaction, status: str, message: str) -> dict:
    """The gateway could not say yet: retry later, or park the money if this was the last try.

    ``transaction.attempts`` already counts the attempt being answered here, so
    reaching the budget means the retry loop is over and the amount goes to the
    hold queue (M5) instead of being retried for ever or quietly failed.
    """
    if int(transaction.attempts or 0) >= max_verify_attempts():
        hold_service.park_ambiguous_payment(transaction, reason=message)
        return _serialize(transaction, message=message)
    transaction.mark_status(status, message)
    transaction.save()
    schedule_verification_retry(transaction)
    return _serialize(transaction, message=message)


def process_callback(
    gateway_code: str,
    payload: dict,
    transaction: Optional[PaymentTransaction] = None,
) -> dict:
    """Idempotently process a gateway callback and verify it."""
    gateway = get_gateway_row(gateway_code)
    adapter = build_adapter(gateway)
    payload = payload or {}

    if transaction is None:
        transaction = locate_transaction(gateway_code, adapter, payload)
    if transaction is None:
        return {
            "status": "unknown",
            "detail": "No transaction matches this callback.",
        }

    with db_transaction.atomic():
        # duplicate callbacks must never pay twice, so the row is locked first
        transaction = PaymentTransaction.objects.select_for_update().get(pk=transaction.pk)
        if transaction.status == TransactionStatus.PAID:
            return _serialize(transaction, message="Already paid")

        token = transaction.gateway_token
        transaction.callback_payload = payload
        # the ids the callback carries are persisted, they are mandatory for
        # verify (PayPing paymentRefId, Digipay providerId) and allow a later
        # callback without the ticket token to be matched
        transaction.meta = {**(transaction.meta or {}), **adapter.extract_callback_meta(payload)}
        transaction.attempts = int(transaction.attempts or 0) + 1
        transaction.save(update_fields=["callback_payload", "meta", "attempts", "updated_at"])

        indicator = adapter.callback_indicates_payment(payload)
        if indicator is False:
            # confirmed payer failure, never a failover trigger
            return _fail(transaction, "Payer reported a failed payment.", message="Payment was not completed.")

        # the adapter needs the merchant side ids it generated, not just the callback
        callback_payload = {**payload, **(transaction.meta or {})}
        try:
            result = adapter.verify(token, transaction.amount_toman, callback_payload)
        except GatewayUnavailable as exc:
            return _leave_ambiguous(transaction, TransactionStatus.UNAVAILABLE, str(exc))
        except GatewayValidationError as exc:
            return _fail(transaction, str(exc))

        transaction.verify_payload = result.raw or {}
        if result.status == GatewayStatus.PAID:
            # the amount the gateway confirms must match the invoice exactly and
            # a missing confirmation is never treated as a match
            confirmed = result.amount_toman
            if confirmed is None:
                message = (
                    f"{gateway_code} reported a successful verification without a confirmed "
                    "amount, the payment is not marked paid until it does."
                )
                return _leave_ambiguous(transaction, TransactionStatus.PROCESSING, message)
            if int(confirmed) != int(transaction.amount_toman):
                message = (
                    f"Amount mismatch: the gateway confirmed {confirmed} toman "
                    f"while the invoice is {transaction.amount_toman} toman."
                )
                return _fail(transaction, message)
            transaction.mark_paid(
                ref_id=result.ref_id,
                amount_toman=transaction.amount_toman,
                fee=result.fee,
            )
            transaction.save()
            _settle_hold(transaction, "پرداخت توسط درگاه تأیید شد")
            invoice = transaction.invoice
            if invoice is not None:
                invoice.status = InvoiceStatus.PAID
                invoice.paid_at = timezone.now()
                invoice.save(update_fields=["status", "paid_at", "updated_at"])
                if _renewal_now_locked(invoice):
                    # The window closed between the order and the payment. The money
                    # is real and stays recorded, but it must not silently renew the plan.
                    invoice.metadata = {**(invoice.metadata or {}), "activation_blocked": "renewal_locked"}
                    invoice.save(update_fields=["metadata", "updated_at"])
                    logger.warning("billing: invoice %s paid inside the renewal lock, not activated", invoice.number)
                    return _serialize(
                        transaction, message="Paid, but the plan cannot be renewed yet. Support will reconcile."
                    )
                _activate_subscription(invoice, transaction)
            return _serialize(transaction, message=result.message or "Paid")
        if result.status == GatewayStatus.PROCESSING:
            return _leave_ambiguous(
                transaction, TransactionStatus.PROCESSING, result.message or "Payment is being processed."
            )
        if result.status == GatewayStatus.UNAVAILABLE:
            # a gateway outage is never a payer failure, so the transaction stays
            # retryable instead of being recorded as a failed payment
            message = result.message or f"{gateway_code} is currently unavailable."
            return _leave_ambiguous(transaction, TransactionStatus.UNAVAILABLE, message)

        return _fail(transaction, result.message or "", message=result.message or "Payment failed.")


def _serialize(transaction: PaymentTransaction, message: str = "") -> dict:
    invoice = transaction.invoice
    return {
        "status": transaction.status,
        "transaction_id": str(transaction.id),
        "invoice_number": invoice.number if invoice else None,
        "amount_toman": transaction.amount_toman,
        "gateway_code": transaction.gateway_code,
        "ref_id": transaction.gateway_ref_id,
        "message": message,
        "result_url": build_result_url(transaction),
    }
