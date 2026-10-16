# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The ambiguous payment queue (M5).

A gateway callback that still cannot say whether the payer was charged after
the last allowed verification is neither paid nor failed. Treating it as failed
risks a payer who WAS charged and got nothing; treating it as paid risks a plan
that was never paid for. So the amount is parked: a ledger entry moves it into
the workspace's hold account, where the workspace cannot spend or see it, and
the transaction enters the queue an instance admin reads.

The admin has three decisions, and beat makes the first one after ninety days
if nobody did:

* ``release_held_payment`` -- the money is the workspace's: hold -> spendable.
* ``reject_held_payment`` -- the payer was never charged: the hold is closed
  and the wallet gets nothing.
* ``retry_held_payment`` -- verify once more. A confirmed payment activates
  the plan and closes the hold; a confirmed failure closes it too; another
  ambiguous answer keeps the hold and re-enters the retry loop.

Every movement is keyed on the transaction, so a repeated decision or a
duplicate callback posts nothing twice.
"""

# Python imports
import logging
from datetime import timedelta
from typing import Optional

# Django imports
from django.db import transaction as db_transaction
from django.utils import timezone

# Module imports
from plane.billing.models import (
    InvoiceStatus,
    LedgerAccountKind,
    LedgerEntry,
    LedgerSource,
    PaymentTransaction,
    TransactionStatus,
)
from plane.billing.services import money, wallet

logger = logging.getLogger("plane.billing")

# A hold nobody decided on is released to the wallet after this many days, so
# a payer's money is never lost in the queue.
HOLD_RELEASE_AFTER_DAYS = 90


class HoldError(Exception):
    """Base class for a decision the queue refuses."""


class NotHeld(HoldError):
    """The transaction is not in the queue, so there is no hold to decide on."""


class DescriptionRequired(HoldError):
    """A decision moves or writes off a payer's money; it must say why."""


def hold_key(transaction: PaymentTransaction) -> str:
    return f"payment:{transaction.pk}:hold"


def release_key(transaction: PaymentTransaction) -> str:
    return f"payment:{transaction.pk}:hold:release"


def close_key(transaction: PaymentTransaction) -> str:
    return f"payment:{transaction.pk}:hold:close"


def auto_release_at(transaction: PaymentTransaction):
    """When beat will release this hold if no admin decides first."""
    if transaction.held_at is None:
        return None
    return transaction.held_at + timedelta(days=HOLD_RELEASE_AFTER_DAYS)


def workspace_of(transaction: PaymentTransaction):
    """The workspace the order was raised for, or None for a workspace-less order."""
    # Local import: ``payment`` imports this module at load time.
    from plane.billing.services.payment import resolve_invoice_workspace

    invoice = transaction.invoice
    return resolve_invoice_workspace(invoice) if invoice is not None else None


def _receivable(gateway_code: str):
    return money.get_or_create_account(
        money.LedgerAccountCode.gateway_receivable(gateway_code),
        LedgerAccountKind.GATEWAY_SETTLEMENT,
        f"مطالبات درگاه {gateway_code}",
    )


def _assert_description(description) -> str:
    text = str(description or "").strip()
    if not text:
        raise DescriptionRequired()
    return text


def _lock_held(transaction: PaymentTransaction) -> PaymentTransaction:
    """Re-read the row under a lock and refuse anything that is not in the queue."""
    # ``of=("self",)``: the invoice is a nullable join, and Postgres refuses to
    # lock the nullable side of an outer join.
    locked = PaymentTransaction.objects.select_for_update(of=("self",)).select_related("invoice").get(pk=transaction.pk)
    if locked.status != TransactionStatus.HELD:
        raise NotHeld()
    return locked


def _hold_entry(transaction: PaymentTransaction) -> Optional[LedgerEntry]:
    return LedgerEntry.objects.filter(transaction=transaction, source=LedgerSource.HOLD).first()


def _close_invoice(transaction: PaymentTransaction, status: str) -> None:
    invoice = transaction.invoice
    if invoice is None or invoice.status == InvoiceStatus.PAID:
        return
    invoice.status = status
    invoice.save(update_fields=["status", "updated_at"])


def park_ambiguous_payment(transaction: PaymentTransaction, *, reason: str) -> Optional[LedgerEntry]:
    """Withhold the amount of a payment whose last allowed verification was still ambiguous.

    Returns the hold entry, or None for a workspace-less order, which has no
    wallet to hold anything in and is only queued for the admin's eyes.
    """
    workspace = workspace_of(transaction)
    entry = None
    with db_transaction.atomic():
        if workspace is not None and int(transaction.amount_toman or 0) > 0:
            _spendable, held = money.get_or_create_wallet_accounts(workspace)
            entry = money.post_entry(
                debit=held,
                credit=_receivable(transaction.gateway_code),
                amount_toman=int(transaction.amount_toman),
                source=LedgerSource.HOLD,
                workspace=workspace,
                description=f"پرداخت نامشخص {transaction.gateway_code} — {transaction.gateway_token}",
                invoice=transaction.invoice,
                transaction=transaction,
                idempotency_key=hold_key(transaction),
            )
        transaction.mark_status(TransactionStatus.HELD, reason)
        # A second parking (a late duplicate callback) keeps the original date,
        # otherwise it would push the automatic release out again.
        transaction.held_at = transaction.held_at or timezone.now()
        transaction.save()
    logger.warning("billing: payment %s parked in the hold queue: %s", transaction.pk, reason)
    return entry


def close_hold(transaction: PaymentTransaction, *, description: str, created_by=None) -> Optional[LedgerEntry]:
    """End a hold without crediting the wallet: the money goes back where it came from.

    Used when the gateway finally answered -- paid, so the money became a plan,
    or failed, so there never was any. The entry reverses the hold entry and
    says so through ``reversal_of``.
    """
    hold = _hold_entry(transaction)
    if hold is None:
        return None
    with db_transaction.atomic():
        entry, replayed = money.post_entry_with_outcome(
            debit=hold.credit_account,
            credit=hold.debit_account,
            amount_toman=hold.amount_toman,
            source=LedgerSource.HOLD_CLOSED,
            workspace=hold.workspace,
            description=description,
            created_by=created_by,
            invoice=transaction.invoice,
            transaction=transaction,
            idempotency_key=close_key(transaction),
        )
        if not replayed and entry.reversal_of_id is None:
            entry.reversal_of_id = hold.pk
            entry.save(update_fields=["reversal_of_id", "updated_at"], disable_auto_set_user=True)
    return entry


def release_held_payment(
    transaction: PaymentTransaction, *, description: str, created_by=None
) -> Optional[LedgerEntry]:
    """The money is the workspace's: move it from the hold to the spendable balance.

    Returns the release entry, or None for a workspace-less order, where only
    the transaction and its invoice are closed.
    """
    description = _assert_description(description)
    with db_transaction.atomic():
        transaction = _lock_held(transaction)
        workspace = workspace_of(transaction)
        entry = None
        if workspace is not None and _hold_entry(transaction) is not None:
            entry = wallet.release_hold(
                workspace=workspace,
                amount_toman=int(transaction.amount_toman),
                description=description,
                idempotency_key=release_key(transaction),
                created_by=created_by,
            )
            if entry.transaction_id is None:
                # ``wallet.release_hold`` is a wallet primitive and does not know
                # about payments; the statement still has to name the one this
                # release answers.
                entry.transaction = transaction
                entry.invoice = transaction.invoice
                entry.save(update_fields=["transaction", "invoice", "updated_at"], disable_auto_set_user=True)
        transaction.mark_status(TransactionStatus.REVERSED, description)
        transaction.save()
        _close_invoice(transaction, InvoiceStatus.REFUND)
    return entry


def reject_held_payment(transaction: PaymentTransaction, *, description: str, created_by=None) -> Optional[LedgerEntry]:
    """The payer was never charged: close the hold, the wallet gets nothing."""
    description = _assert_description(description)
    with db_transaction.atomic():
        transaction = _lock_held(transaction)
        entry = close_hold(transaction, description=description, created_by=created_by)
        transaction.mark_status(TransactionStatus.FAILED, description)
        transaction.save()
        _close_invoice(transaction, InvoiceStatus.CANCELLED)
    return entry


def retry_held_payment(transaction: PaymentTransaction, *, created_by=None) -> dict:
    """Verify once more, with a fresh attempt budget. The hold stays until the gateway answers."""
    # Local import: ``payment`` imports this module at load time.
    from plane.billing.services.payment import process_callback

    with db_transaction.atomic():
        transaction = _lock_held(transaction)
        transaction.attempts = 0
        transaction.mark_status(TransactionStatus.PROCESSING, "تلاش مجدد دستی")
        transaction.save()
    logger.info("billing: manual retry of held payment %s by %s", transaction.pk, getattr(created_by, "pk", None))
    return process_callback(transaction.gateway_code, transaction.callback_payload or {}, transaction=transaction)
