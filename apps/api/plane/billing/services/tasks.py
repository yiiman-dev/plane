# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Celery helpers for payments that need a second look."""

# Python imports
import logging

# Django imports
from django.utils import timezone

# Third party imports
from celery import shared_task

# Module imports
from plane.billing.models import PaymentTransaction, TransactionStatus

logger = logging.getLogger("plane.billing")

MAX_VERIFY_ATTEMPTS = 5


def _is_backoff_due(transaction, now) -> bool:
    attempts = int(transaction.attempts or 0)
    if attempts >= MAX_VERIFY_ATTEMPTS:
        return False
    elapsed = (now - transaction.created_at).total_seconds()
    return elapsed >= min(600, 2**attempts * 30)


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


def schedule_verification_retry(transaction) -> None:
    """Best effort enqueue; the scheduler picks the transaction up otherwise."""
    try:
        retry_pending_verifications.delay()
    except Exception as exc:  # pragma: no cover - broker may be unavailable
        logger.warning("billing: unable to enqueue verification retry: %s", exc)
