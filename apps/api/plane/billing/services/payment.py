# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Order creation, gateway selection and idempotent callback processing."""

# Python imports
import logging
from typing import Optional

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
from plane.billing.services.router import GatewayRouter
from plane.billing.services.tasks import schedule_verification_retry
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
) -> Invoice:
    seats = max(plan.min_seats, min(int(seats or 0), plan.max_seats))
    subtotal = plan.calculate_subtotal(seats, cycle)
    now = timezone.now()
    due = now + timezone.timedelta(days=365 if cycle == BillingCycle.YEARLY else 31)
    # the workspace travels on the invoice metadata so the gateway callback, which only sees
    # the transaction row, can still bind the resulting subscription to that workspace
    metadata = {"workspace_slug": workspace_slug} if workspace_slug else {}
    return Invoice.objects.create(
        number=Invoice.generate_number(),
        user=user,
        plan=plan,
        seats=seats,
        cycle=cycle,
        subtotal_toman=subtotal,
        discount_toman=0,
        total_toman=subtotal,
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

    invoice = issue_invoice(
        user=user,
        plan=plan,
        seats=seats,
        cycle=cycle,
        notes=notes,
        workspace_slug=workspace_slug,
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


def _activate_subscription(invoice: Invoice, transaction: PaymentTransaction) -> None:
    now = timezone.now()
    period = timezone.timedelta(days=365 if invoice.cycle == BillingCycle.YEARLY else 31)
    # A plan is a workspace entitlement, so the subscription is bound to the workspace the
    # order was raised for. An order without one keeps the older owner level behaviour.
    workspace = resolve_invoice_workspace(invoice)
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
            ends_at=now + period,
            source_transaction=transaction,
            workspace=workspace,
        )
        return
    subscription.seats = invoice.seats
    subscription.cycle = invoice.cycle
    subscription.starts_at = now
    subscription.ends_at = now + period
    subscription.source_transaction = transaction
    subscription.workspace = workspace
    subscription.save()


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
            transaction.mark_status(TransactionStatus.FAILED, "Payer reported a failed payment.")
            transaction.save()
            return _serialize(transaction, message="Payment was not completed.")

        # the adapter needs the merchant side ids it generated, not just the callback
        callback_payload = {**payload, **(transaction.meta or {})}
        try:
            result = adapter.verify(token, transaction.amount_toman, callback_payload)
        except GatewayUnavailable as exc:
            transaction.mark_status(TransactionStatus.UNAVAILABLE, str(exc))
            transaction.save()
            schedule_verification_retry(transaction)
            return _serialize(transaction, message=str(exc))
        except GatewayValidationError as exc:
            transaction.mark_status(TransactionStatus.FAILED, str(exc))
            transaction.save()
            return _serialize(transaction, message=str(exc))

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
                transaction.mark_status(TransactionStatus.PROCESSING, message)
                transaction.save()
                schedule_verification_retry(transaction)
                return _serialize(transaction, message=message)
            if int(confirmed) != int(transaction.amount_toman):
                message = (
                    f"Amount mismatch: the gateway confirmed {confirmed} toman "
                    f"while the invoice is {transaction.amount_toman} toman."
                )
                transaction.mark_status(TransactionStatus.FAILED, message)
                transaction.save()
                return _serialize(transaction, message=message)
            transaction.mark_paid(
                ref_id=result.ref_id,
                amount_toman=transaction.amount_toman,
                fee=result.fee,
            )
            transaction.save()
            invoice = transaction.invoice
            if invoice is not None:
                invoice.status = InvoiceStatus.PAID
                invoice.paid_at = timezone.now()
                invoice.save(update_fields=["status", "paid_at", "updated_at"])
                _activate_subscription(invoice, transaction)
            return _serialize(transaction, message=result.message or "Paid")
        if result.status == GatewayStatus.PROCESSING:
            transaction.mark_status(TransactionStatus.PROCESSING, result.message)
            transaction.save()
            schedule_verification_retry(transaction)
            return _serialize(transaction, message=result.message or "Payment is being processed.")
        if result.status == GatewayStatus.UNAVAILABLE:
            # a gateway outage is never a payer failure, so the transaction stays
            # retryable instead of being recorded as a failed payment
            message = result.message or f"{gateway_code} is currently unavailable."
            transaction.mark_status(TransactionStatus.UNAVAILABLE, message)
            transaction.save()
            schedule_verification_retry(transaction)
            return _serialize(transaction, message=message)

        transaction.mark_status(TransactionStatus.FAILED, result.message)
        transaction.save()
        return _serialize(transaction, message=result.message or "Payment failed.")


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
