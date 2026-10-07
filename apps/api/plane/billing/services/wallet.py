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
* a refund DEBITS spendable, CREDITS the gateway reversal account

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

# The KIND of that account is the part that is easy to get wrong, and the code
# name hides it.
#
# ``refund_to_spendable`` is only for a payment the gateway *rejected*, where
# no money was ever taken -- there is no prior gateway leg for this entry to
# mirror. It still has to be double entry, so it needs a contra side, and that
# side has to be an account we can drive back toward zero later.
#
# ``GATEWAY_SETTLEMENT`` is credit-normal, so its balance is
# ``credits - debits``: crediting it pushes it FURTHER from zero and a later
# genuine settlement could never bring it back. The contra side of an entry for
# money that never moved has to be a source of funds, so it is booked against
# ``ADMIN_POOL`` -- debit-normal, like every other funding account, which makes
# crediting it move it TOWARD zero. The account is still a gateway reversal in
# name, which is what the statement for it should say; only its normal balance
# side is that of the pool it draws on.
GATEWAY_REVERSAL_ACCOUNT_KIND = LedgerAccountKind.ADMIN_POOL


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


class InvalidAmount(WalletError):
    """A malformed amount -- not a policy violation about an otherwise valid one.

    Kept distinct from ``WalletError`` itself so a caller can tell "you sent
    ``amount_toman='10''" apart from "the workspace cannot afford this",
    which usually deserve different HTTP statuses and different operator alerts.
    """

    message = "مبلغ باید عدد صحیح مثبت باشد."


class NotAGrantEntry(WalletError):
    """``revoke_grant`` was handed an entry that is not an admin grant."""

    message = "فقط اعتبار اعطایی مدیر قابل ابطال است."


class GrantAlreadyReversed(WalletError):
    """``revoke_grant`` was handed a grant that a reversal already neutralised."""

    message = "این اعتبار قبلاً ابطال شده است."


class InvalidChargeReference(WalletError):
    """``charge_sms`` was called without a usable notification log reference."""

    message = "شناسهٔ لاگ پیامک الزامی است."


def _assert_amount(amount_toman: int) -> None:
    """Reject anything that is not a positive non-bool integer.

    ``isinstance(True, int)`` is ``True`` in Python, so a bool would sail
    through a bare type check and post a 1-toman charge; the explicit bool
    rejection is what makes ``amount_toman`` mean money.
    """
    if isinstance(amount_toman, bool) or not isinstance(amount_toman, int):
        raise InvalidAmount()
    if amount_toman <= 0:
        raise InvalidAmount()


def _assert_log_id(log_id) -> None:
    """Refuse a missing notification log id.

    ``charge_sms`` builds its idempotency key from ``log_id``. A ``None`` would
    collapse every SMS in the product onto the single key ``"sms:None:charge"``:
    the first one posts and every later one raises from the same-movement check.
    Validating here means the caller finds out at the call it made the mistake,
    not on an unrelated message later.
    """
    if log_id is None or isinstance(log_id, bool) or (isinstance(log_id, str) and not log_id.strip()):
        raise InvalidChargeReference()


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


def _replay_or_none(
    idempotency_key: Optional[str], *, debit: LedgerAccount, credit: LedgerAccount, amount_toman: int
) -> Optional[LedgerEntry]:
    """The entry already posted under this key, or ``None``.

    THE ordering rule for every money function in this module: consult this
    FIRST, before any affordability, cap or eligibility check. A retry of work
    that already succeeded must never raise, and the only check that can tell it
    apart from new work is this one. Checking anything else first is how a
    completed ``revoke_grant`` came to raise ``InsufficientBalance`` on its
    second identical call, because the first call had already emptied the
    wallet it was checking against.

    It is one helper called at the top of all six functions rather than an
    inline check per function, because the rule drifted once already: three
    functions had it and three did not, and the three that did not were the
    admin-facing ones.

    The legs and amount are required, not optional, because a replay is only a
    replay if it is the SAME movement: a key reused for a different amount is a
    caller bug, and ``money._assert_same_movement`` is the one place that
    decides so. Callers therefore resolve their accounts before calling it,
    which they all have to do anyway to post.

    Looked up through ``all_objects`` because a soft-deleted row still occupies
    its unique key (see ``LedgerEntry.idempotency_key``).
    """
    if not idempotency_key:
        return None
    existing = LedgerEntry.all_objects.filter(idempotency_key=idempotency_key).first()
    if existing is None:
        return None
    money._assert_same_movement(existing, debit=debit, credit=credit, amount_toman=amount_toman)
    return existing


def _already_reversed(entry: LedgerEntry) -> bool:
    """Whether ``entry`` has a reversal posted against it.

    A reversal is a ``REFUND`` entry on the same workspace with the opposite
    legs, so the mirror is what identifies it -- not a back-reference column the
    model does not have. Without this, an admin who revokes the same grant twice
    under two different keys gets two reversals and the wallet is driven
    negative by a duplicate of work that was already undone.
    """
    return (
        LedgerEntry.objects.filter(
            workspace_id=entry.workspace_id,
            source=LedgerSource.REFUND,
            debit_account_id=entry.credit_account_id,
            credit_account_id=entry.debit_account_id,
            amount_toman=entry.amount_toman,
        )
        .exclude(pk=entry.pk)
        .exists()
    )


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

    # Replay BEFORE the cap check: an admin who lowers the cap between two
    # identical calls must not get ``GrantTooLarge`` for a grant that already
    # posted (see ``_replay_or_none``).
    replay = _replay_or_none(idempotency_key, debit=spendable, credit=_pool_account(), amount_toman=amount_toman)
    if replay is not None:
        return replay

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

    ``entry`` is a caller-supplied primary key, so the row is checked on two
    axes before anything is reversed: it must belong to ``workspace``, and it
    must actually BE an admin grant that has not been reversed yet. Reversing an
    arbitrary ledger row on a pk from a request body is a confused-deputy
    surface -- handed an SMS charge it would quietly refund an SMS charge.
    """
    _assert_amount(entry.amount_toman)
    description = _assert_description(description)

    spendable, _held = money.get_or_create_wallet_accounts(workspace)

    # Replay BEFORE the workspace, source and affordability checks. A retry of a
    # completed reversal has already drained the wallet by construction, so an
    # affordability check ahead of this one raises ``InsufficientBalance`` for
    # work that is already done (see ``_replay_or_none``).
    replay = _replay_or_none(
        idempotency_key,
        debit=entry.credit_account,
        credit=entry.debit_account,
        amount_toman=entry.amount_toman,
    )
    if replay is not None:
        return replay

    with transaction.atomic():
        # Re-read under the lock so the amount and legs come from committed
        # state, and so two concurrent revocations serialise on one row.
        locked = LedgerEntry.objects.select_for_update().get(pk=entry.pk)
        _assert_amount(locked.amount_toman)

        if locked.workspace_id != workspace.pk:
            raise WalletError("این تراکنش متعلق به کیف پول این فضای کاری نیست.")

        if locked.source != LedgerSource.ADMIN_GRANT:
            raise NotAGrantEntry()

        if _already_reversed(locked):
            raise GrantAlreadyReversed()

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


def charge_sms(
    *,
    workspace,
    amount_toman: int,
    log_id,
    idempotency_key: Optional[str] = None,
    description: str = "",
    created_by=None,
) -> LedgerEntry:
    """Spend from the wallet for one outbound SMS.

    Keyed on the notification log id so a retried delivery never charges
    the workspace twice for the same message.

    ``log_id`` is mandatory and is written into the entry's ``description``, so
    the notification log stays recoverable from the ledger: the idempotency key
    embeds it, but the key is the index, not the story, and without the
    reference there is no way to answer "which message cost this?" from the
    ledger alone. ``created_by`` is the actor when one exists -- SMS charges are
    usually taken outside a request (a Celery task, where crum yields ``None``),
    so it is ``None`` far more often here than for a grant.
    """
    _assert_log_id(log_id)
    _assert_amount(amount_toman)
    key = idempotency_key or f"sms:{log_id}:charge"

    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    expense = _sms_expense_account()

    replay = _replay_or_none(key, debit=expense, credit=spendable, amount_toman=amount_toman)
    if replay is not None:
        return replay

    with transaction.atomic():
        locked_spendable = _lock_account(spendable)

        if not money.wallet_balance_is_enough(workspace, amount_toman):
            raise InsufficientBalance()

        return money.post_entry(
            debit=_sms_expense_account(),
            credit=locked_spendable,
            amount_toman=amount_toman,
            source=LedgerSource.SMS_CHARGE,
            workspace=workspace,
            description=description or f"پیامک {log_id}",
            created_by=created_by,
            idempotency_key=key,
        )


def hold_funds(*, workspace, amount_toman: int, source: str, idempotency_key: str) -> LedgerEntry:
    """Move money out of the spendable balance into the hold.

    Used when a payment was taken but could not be applied. The workspace
    owner cannot spend or see this money until an admin decides.
    """
    _assert_amount(amount_toman)

    spendable, held = money.get_or_create_wallet_accounts(workspace)

    replay = _replay_or_none(idempotency_key, debit=held, credit=spendable, amount_toman=amount_toman)
    if replay is not None:
        return replay

    with transaction.atomic():
        locked_spendable = _lock_account(spendable)
        if not money.wallet_balance_is_enough(workspace, amount_toman):
            raise InsufficientBalance("موجودی برای قفل کردن کافی نیست.")

        return money.post_entry(
            debit=held,
            credit=locked_spendable,
            amount_toman=amount_toman,
            source=source,
            workspace=workspace,
            idempotency_key=idempotency_key,
        )


def release_hold(*, workspace, amount_toman: int, idempotency_key: str, created_by=None) -> LedgerEntry:
    """Return held money to the spendable balance."""
    _assert_amount(amount_toman)

    spendable, held = money.get_or_create_wallet_accounts(workspace)

    replay = _replay_or_none(idempotency_key, debit=spendable, credit=held, amount_toman=amount_toman)
    if replay is not None:
        return replay

    with transaction.atomic():
        locked_spendable = _lock_account(spendable)
        locked_held = _lock_account(held)

        # ``wallet_hold_balance`` CLAMPS at 0, unlike ``wallet_balance_is_enough``
        # on the spendable side. The asymmetry is deliberate, not an oversight:
        # an over-released hold account holds a negative signed balance, and
        # "you have 0 held, so you may not release 1 Toman" is the correct
        # answer to that. Clamping the spendable side instead would make an
        # overdrawn wallet look able to afford a charge.
        if money.wallet_hold_balance(workspace) < amount_toman:
            raise InsufficientBalance("مبلغ قفل‌شده کافی نیست.")

        return money.post_entry(
            debit=locked_spendable,
            credit=locked_held,
            amount_toman=amount_toman,
            source=LedgerSource.RELEASE_HOLD,
            workspace=workspace,
            created_by=created_by,
            idempotency_key=idempotency_key,
        )


def refund_to_spendable(
    *, workspace, amount_toman: int, reason: str, idempotency_key: str, created_by=None
) -> LedgerEntry:
    """Return money directly to the spendable balance without passing through a hold.

    Only for a payment the gateway explicitly rejected, where we know no
    money was ever taken.
    """
    _assert_amount(amount_toman)

    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    reversal = money.get_or_create_account(GATEWAY_REVERSAL_ACCOUNT_CODE, GATEWAY_REVERSAL_ACCOUNT_KIND, "برگشت درگاه")

    replay = _replay_or_none(idempotency_key, debit=spendable, credit=reversal, amount_toman=amount_toman)
    if replay is not None:
        return replay

    with transaction.atomic():
        return money.post_entry(
            debit=spendable,
            credit=reversal,
            amount_toman=amount_toman,
            source=LedgerSource.REFUND,
            workspace=workspace,
            description=reason,
            created_by=created_by,
            idempotency_key=idempotency_key,
        )
