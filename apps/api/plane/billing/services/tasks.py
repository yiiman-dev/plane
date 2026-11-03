# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Celery helpers for payments that need a second look."""

# Python imports
import logging
from datetime import timedelta

# Django imports
from django.conf import settings
from django.utils import timezone

# Third party imports
from celery import shared_task

# Module imports
from plane.billing.models import PaymentTransaction, TransactionStatus

logger = logging.getLogger("plane.billing")

# The default verification budget. The instance can override it with
# ``BILLING_MAX_VERIFY_ATTEMPTS``; read it through ``max_verify_attempts()``.
MAX_VERIFY_ATTEMPTS = 5

# Age after which a pending/redirected transaction is considered stale and re-queried (default: 15 minutes)
STALE_TRANSACTION_MINUTES = 15

# Age after which an uncompleted transaction is expired (default: 2 hours)
MAX_PENDING_TRANSACTION_HOURS = 2

# Maximum stale transactions to inspect in one batch
STALE_BATCH_SIZE = 50


def max_verify_attempts() -> int:
    """How many verifications a payment gets before its money is parked in the hold queue."""
    configured = getattr(settings, "BILLING_MAX_VERIFY_ATTEMPTS", None)
    try:
        return max(1, int(configured)) if configured is not None else MAX_VERIFY_ATTEMPTS
    except (TypeError, ValueError):
        return MAX_VERIFY_ATTEMPTS


def stale_transaction_minutes() -> int:
    configured = getattr(settings, "BILLING_STALE_TRANSACTION_MINUTES", None)
    try:
        return max(1, int(configured)) if configured is not None else STALE_TRANSACTION_MINUTES
    except (TypeError, ValueError):
        return STALE_TRANSACTION_MINUTES


def max_pending_transaction_hours() -> int:
    configured = getattr(settings, "BILLING_MAX_PENDING_TRANSACTION_HOURS", None)
    try:
        return max(1, int(configured)) if configured is not None else MAX_PENDING_TRANSACTION_HOURS
    except (TypeError, ValueError):
        return MAX_PENDING_TRANSACTION_HOURS


def _is_backoff_due(transaction, now) -> bool:
    attempts = int(transaction.attempts or 0)
    if attempts >= max_verify_attempts():
        return False
    elapsed = (now - transaction.created_at).total_seconds()
    return elapsed >= min(600, 2**attempts * 30)


@shared_task
def requery_stale_transactions(now=None):
    """Re-query transactions left in pending or redirected status.

    When a payer visits the payment gateway but closes the tab, suffers a network drop,
    or does not get redirected back, the transaction remains in ``PENDING`` or ``REDIRECTED``.
    This task re-queries the gateway to discover if the payment was completed. If the gateway
    confirms payment, the order is fulfilled. If the transaction has passed the maximum pending
    window and remains uncompleted, it is marked as failed/expired and its draft invoice cancelled.
    """
    from plane.billing.services.payment import cancel_invoice, process_callback

    now = now or timezone.now()
    stale_cutoff = now - timedelta(minutes=stale_transaction_minutes())
    expiry_cutoff = now - timedelta(hours=max_pending_transaction_hours())

    candidates = (
        PaymentTransaction.objects.filter(
            status__in=(TransactionStatus.PENDING, TransactionStatus.REDIRECTED),
            created_at__lte=stale_cutoff,
        )
        .select_related("invoice")
        .order_by("created_at")[:STALE_BATCH_SIZE]
    )

    processed = 0
    for transaction in candidates:
        if transaction.created_at <= expiry_cutoff:
            try:
                process_callback(
                    transaction.gateway_code,
                    transaction.callback_payload or {},
                    transaction=transaction,
                )
                transaction.refresh_from_db()
                if transaction.status not in (TransactionStatus.PENDING, TransactionStatus.REDIRECTED):
                    processed += 1
                    continue
            except Exception as exc:
                logger.warning("billing: final verify failed for %s: %s", transaction.id, exc)

            transaction.mark_status(TransactionStatus.FAILED, "انقضای مهلت پرداخت (تراکنش متروکه)")
            transaction.save(update_fields=["status", "failure_reason", "updated_at"])
            if transaction.invoice:
                cancel_invoice(transaction.invoice)
            processed += 1
            logger.info("billing: expired stale transaction %s", transaction.id)
            continue

        try:
            process_callback(
                transaction.gateway_code,
                transaction.callback_payload or {},
                transaction=transaction,
            )
            processed += 1
        except Exception as exc:
            logger.warning("billing: requery failed for stale transaction %s: %s", transaction.id, exc)

    return processed


@shared_task
def retry_pending_verifications():
    """Re-verify transactions that a gateway left in a processing state."""
    from plane.billing.services.payment import process_callback

    now = timezone.now()
    candidates = PaymentTransaction.objects.filter(
        status__in=(TransactionStatus.PROCESSING, TransactionStatus.UNAVAILABLE)
    )
    processed = 0
    for transaction in candidates:
        if not _is_backoff_due(transaction, now):
            continue
        try:
            process_callback(transaction.gateway_code, transaction.callback_payload or {}, transaction=transaction)
            processed += 1
        except Exception as exc:  # pragma: no cover - background best effort
            logger.warning("billing: retry verify failed for %s: %s", transaction.id, exc)
    return processed


@shared_task
def release_expired_holds():
    """Release every hold nobody decided on within ``HOLD_RELEASE_AFTER_DAYS``.

    Runs from beat once a day. The money goes back to the workspace's wallet,
    which is the safe default: a hold that stays for ever is a payer's money
    lost, and an admin who disagrees still has the ledger row to reverse.
    """
    from plane.billing.services import hold as hold_service

    cutoff = timezone.now() - timedelta(days=hold_service.HOLD_RELEASE_AFTER_DAYS)
    released = 0
    expired = PaymentTransaction.objects.filter(status=TransactionStatus.HELD, held_at__lte=cutoff).order_by("held_at")
    for transaction in expired:
        try:
            hold_service.release_held_payment(
                transaction,
                description=f"آزادسازی خودکار پس از {hold_service.HOLD_RELEASE_AFTER_DAYS} روز بدون تصمیم",
                created_by=None,
            )
            released += 1
        except Exception as exc:  # pragma: no cover - background best effort
            logger.warning("billing: automatic hold release failed for %s: %s", transaction.pk, exc)
    return released


@shared_task
def send_renewal_notices():
    """Remind workspace admins of subscriptions ending on a configured day. Runs from beat daily.

    Returns how many reminders went out, which is 0 on most days.
    """
    from plane.billing.services import renewal

    return renewal.send_due_renewal_notices()


def schedule_verification_retry(transaction) -> None:
    """Best effort enqueue; the scheduler picks the transaction up otherwise."""
    try:
        retry_pending_verifications.delay()
    except Exception as exc:  # pragma: no cover - broker may be unavailable
        logger.warning("billing: unable to enqueue verification retry: %s", exc)
