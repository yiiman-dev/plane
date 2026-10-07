# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Wallet policy: how money enters a workspace wallet and how it leaves.

Every function here delegates the arithmetic to ``services.money``. This
layer owns the rules -- what a valid grant looks like, when a charge is
refused, what a hold means -- so those rules can be read in one place.

Posting direction, once, so no function has to re-derive it
--------------------------------------------------------------
Both sides of a workspace wallet are ``ASSET`` accounts, which
``LedgerAccount.is_debit_normal`` makes debit-normal: their balance is
``debits - credits``. So a wallet balance GROWS when the spendable account
is debited and SHRINKS when it is credited. Concretely:

* a grant DEBITS spendable, CREDITS the admin pool
* a charge DEBITS the expense account, CREDITS spendable
* a hold DEBITS the hold account, CREDITS spendable
* a release DEBITS spendable, CREDITS the hold account

Getting one of these the wrong way round does not raise -- it produces a
mirrored entry that silently inverts the balance. ``wallet_balance`` clamps
at 0, so the error reads as "the wallet is empty" rather than as a bug.
"""

# Python imports
from typing import Optional

# Django imports
from django.db import transaction

# Module imports
from plane.billing.models import LedgerAccount, LedgerAccountKind, LedgerEntry, LedgerSource, Wallet
from plane.billing.services import money

# An admin grant is an internal note. Anything shorter than this is a typo,
# not an explanation.
MIN_GRANT_DESCRIPTION_LENGTH = 10

# The single account an SMS charge is booked against. Shared by every
# workspace, which is safe precisely because the entry carries ``workspace``
# (see ``grant_from_admin``'s note on GLOBAL account scoping).
SMS_EXPENSE_ACCOUNT_CODE = "expense:sms"

# One shared account for gateway reversals. Keying the account CODE on the
# idempotency key would mint a new ledger account per refund, so the accounts
# table would grow without bound and no per-account statement would ever be
# readable.
GATEWAY_REVERSAL_ACCOUNT_CODE = "gateway:reversal"


class WalletError(Exception):
    """Base class for wallet policy violations."""

    message = "عملیات کیف پول نامعتبر است."

    def __init__(self, message: Optional[str] = None):
        self.message = message or self.__class__.message
        super().__init__(self.message)


class InvalidGrantDescription(WalletError):
    message = "توضیح اعتبار دستی الزامی و باید حداقل ۱۰ کاراکتر باشد."


class GrantTooLarge(WalletError):
    message = "مبلغ اعتبار از سقف مجاز هر بار بیشتر است."


class InsufficientBalance(WalletError):
    message = "موجودی کیف پول کافی نیست."


def _assert_amount(amount_toman: int) -> None:
    if not isinstance(amount_toman, bool) and not isinstance(amount_toman, int):
        raise WalletError("مبلغ باید عدد صحیح مثبت باشد.")
    if amount_toman <= 0:
        raise WalletError("مبلغ باید عدد صحیح مثبت باشد.")


def _assert_description(description: str) -> str:
    """Return the stripped description, or refuse it."""
    if not description or len(description.strip()) < MIN_GRANT_DESCRIPTION_LENGTH:
        raise InvalidGrantDescription()
    return description.strip()


def _lock_account(account: LedgerAccount) -> LedgerAccount:
    """Re-read an account under ``SELECT ... FOR UPDATE``.

    The lock is what makes the balance check below safe: a second transaction
    charging the same wallet blocks here until the first one commits, so it
    then reads a balance that already reflects the first charge instead of
    racing past the same limit.
    """
    return LedgerAccount.objects.select_for_update().get(pk=account.pk)


def _already_posted(idempotency_key: str) -> bool:
    """Whether ``idempotency_key`` already has an entry, live or soft deleted.

    Consulted BEFORE the balance check so a replay of a completed movement is
    never refused for lack of funds. ``charge_sms`` exists to stop a redelivered
    notification being billed twice; if the first attempt emptied the wallet,
    a check-first ordering would turn the harmless retry into an
    ``InsufficientBalance`` and the caller would retry again.

    Looked up through ``all_objects`` because a soft-deleted row still occupies
    its unique key (see ``LedgerEntry.idempotency_key``).
    """
    return LedgerEntry.all_objects.filter(idempotency_key=idempotency_key).exists()


def _pool_account() -> LedgerAccount:
    return money.get_or_create_account(money.ADMIN_GRANT_POOL, LedgerAccountKind.ADMIN_POOL, "اعتبار اعطایی مدیر")


def _sms_expense_account() -> LedgerAccount:
    return money.get_or_create_account(SMS_EXPENSE_ACCOUNT_CODE, LedgerAccountKind.REVENUE, "هزینهٔ پیامک")


def grant_from_admin(
    *, workspace, amount_toman: int, description: str, created_by, idempotency_key: str
) -> LedgerEntry:
    """Credit a workspace wallet from the instance admin grant pool.

    ``created_by`` comes from the authenticated request, never from the
    request body, so an admin cannot be forged onto a grant.

    ``workspace`` is passed on the entry even though the debit side (the pool)
    is a GLOBAL account: ``post_entry`` does not derive the workspace from its
    accounts, so a posting against the pool without it is invisible to
    ``account_balance(pool, workspace=ws)`` and per-workspace pool accounting
    under-counts.
    """
    _assert_amount(amount_toman)
    description = _assert_description(description)

    spendable, _held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        wallet_row, _created = Wallet.objects.get_or_create(workspace=workspace)
        cap = wallet_row.admin_grant_cap_toman
        if cap and amount_toman > cap:
            raise GrantTooLarge()

        return money.post_entry(
            debit=spendable,
            credit=_pool_account(),
            amount_toman=amount_toman,
            source=LedgerSource.ADMIN_GRANT,
            workspace=workspace,
            description=description,
            created_by=created_by,
            idempotency_key=idempotency_key,
        )


def revoke_grant(*, workspace, entry: LedgerEntry, description: str, created_by, idempotency_key: str) -> LedgerEntry:
    """Reverse a grant with a new entry. The original row is never edited or deleted.

    The reversal is the strict mirror of the entry being reversed: its debit
    side is the original's CREDIT account and vice versa. That is what makes it
    a reversal rather than a second copy of the same movement.
    """
    description = _assert_description(description)

    spendable, _held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        # Re-read under the lock so the amount and legs come from committed
        # state, and so two concurrent revocations serialise on one row.
        locked = LedgerEntry.objects.select_for_update().get(pk=entry.pk)
        _assert_amount(locked.amount_toman)

        if locked.workspace_id != workspace.pk:
            raise WalletError("این تراکنش متعلق به کیف پول این فضای کاری نیست.")

        # Lock the spendable account, which is the one whose balance the check
        # below reads and which the reversal CREDITS (a grant is debit=spendable,
        # so its reversal debits the pool and credits spendable). Locking
        # anything else would take a row the posting never contends on, and two
        # concurrent revocations could both pass the check and drive the wallet
        # negative between them.
        _lock_account(spendable)
        if not money.wallet_balance_is_enough(workspace, locked.amount_toman):
            raise InsufficientBalance("موجودی برای ابطال کل مبلغ کافی نیست.")

        return money.post_entry(
            debit=locked.credit_account,
            credit=locked.debit_account,
            amount_toman=locked.amount_toman,
            source=LedgerSource.REFUND,
            workspace=workspace,
            description=description,
            created_by=created_by,
            idempotency_key=idempotency_key,
        )


def charge_sms(*, workspace, amount_toman: int, log_id, idempotency_key: Optional[str] = None) -> LedgerEntry:
    """Spend from the wallet for one outbound SMS.

    Keyed on the notification log id so a retried delivery never charges
    the workspace twice for the same message.
    """
    _assert_amount(amount_toman)
    key = idempotency_key or f"sms:{log_id}:charge"

    spendable, _held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        locked_spendable = _lock_account(spendable)

        # Replay first (see ``_already_posted``), then affordability.
        if not _already_posted(key) and not money.wallet_balance_is_enough(workspace, amount_toman):
            raise InsufficientBalance()

        return money.post_entry(
            debit=_sms_expense_account(),
            credit=locked_spendable,
            amount_toman=amount_toman,
            source=LedgerSource.SMS_CHARGE,
            workspace=workspace,
            idempotency_key=key,
        )


def hold_funds(*, workspace, amount_toman: int, source: str, idempotency_key: str) -> LedgerEntry:
    """Move money out of the spendable balance into the hold.

    Used when a payment was taken but could not be applied. The workspace
    owner cannot spend or see this money until an admin decides.
    """
    _assert_amount(amount_toman)

    spendable, held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        locked_spendable = _lock_account(spendable)
        if not _already_posted(idempotency_key) and not money.wallet_balance_is_enough(workspace, amount_toman):
            raise InsufficientBalance("موجودی برای قفل کردن کافی نیست.")

        return money.post_entry(
            debit=held,
            credit=locked_spendable,
            amount_toman=amount_toman,
            source=source,
            workspace=workspace,
            idempotency_key=idempotency_key,
        )


def release_hold(*, workspace, amount_toman: int, idempotency_key: str) -> LedgerEntry:
    """Return held money to the spendable balance."""
    _assert_amount(amount_toman)

    spendable, held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        locked_held = _lock_account(held)
        if not _already_posted(idempotency_key) and money.wallet_hold_balance(workspace) < amount_toman:
            raise InsufficientBalance("مبلغ قفل‌شده کافی نیست.")

        return money.post_entry(
            debit=spendable,
            credit=locked_held,
            amount_toman=amount_toman,
            source=LedgerSource.RELEASE_HOLD,
            workspace=workspace,
            idempotency_key=idempotency_key,
        )


def refund_to_spendable(*, workspace, amount_toman: int, reason: str, idempotency_key: str) -> LedgerEntry:
    """Return money directly to the spendable balance without passing through a hold.

    Only for a payment the gateway explicitly rejected, where we know no
    money was ever taken.
    """
    _assert_amount(amount_toman)

    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    reversal = money.get_or_create_account(
        GATEWAY_REVERSAL_ACCOUNT_CODE, LedgerAccountKind.GATEWAY_SETTLEMENT, "برگشت درگاه"
    )

    return money.post_entry(
        debit=spendable,
        credit=reversal,
        amount_toman=amount_toman,
        source=LedgerSource.REFUND,
        workspace=workspace,
        description=reason,
        idempotency_key=idempotency_key,
    )
