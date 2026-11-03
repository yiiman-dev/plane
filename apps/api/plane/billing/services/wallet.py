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
from django.db import IntegrityError, transaction

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

# A caller-supplied pk or idempotency key that turns out to name another
# workspace's money. Plain ``WalletError``, deliberately not a subclass: it is
# a confused-deputy refusal, not a policy decision about the caller's own
# wallet, and an HTTP layer must not be able to treat it as one.
WORKSPACE_MISMATCH_MESSAGE = "این تراکنش متعلق به کیف پول این فضای کاری نیست."

# Which ``LedgerSource`` values a hold may be booked under. A hold is money that
# WAS taken and cannot yet be applied, so the reasons are the payment-driven
# ones plus the neutral ``HOLD``.
#
# The list is an allow-list, not a deny-list of ``ADMIN_GRANT``: an entry that
# says "a grant was made" while actually moving money into a hold account makes
# every later statement about grants a lie, and a deny-list only catches the
# labels someone thought of in advance.
HOLD_ALLOWED_SOURCES = (
    LedgerSource.HOLD,
    LedgerSource.GATEWAY,
    LedgerSource.PLAN_PURCHASE,
    LedgerSource.UPGRADE,
)


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


class InvalidHoldSource(WalletError):
    """``hold_funds`` was asked to book the movement under a non-hold source."""

    message = "منبع قفل کردن وجه نامعتبر است."


class InvalidHoldDescription(WalletError):
    """``hold_funds`` / ``release_hold`` was called without a reason.

    Money withheld from a workspace is invisible to its owner until an admin
    releases it, and the entry is the only place the reason can live. An
    unattributed hold that is later released leaves two unattributed entries
    and no way to answer the owner's question of why.
    """

    message = "ثبت دلیل قفل کردن یا آزادسازی وجه الزامی است."


class InvalidIdempotencyKey(WalletError):
    """A blank or non-string idempotency key was supplied.

    The key is the whole of the retry protection. A blank one is not "no key":
    it looks absent to the replay pre-check, which then skips it, while
    ``post_entry`` still writes the blank string into the unique column -- so
    the pre-check is disabled and the second call has to be caught by the
    unique index instead of by the check that was supposed to catch it.
    """

    message = "کلید یکتایی تراکنش نمی‌تواند خالی باشد."


class InvalidPaymentReference(WalletError):
    """``refund_to_spendable`` was called without a reference to the failed payment.

    The docstring claims this function is only for a payment the gateway
    explicitly rejected. A mandatory reference is what makes that claim
    checkable: a refund nobody can point at a transaction, invoice or gateway
    ref for is indistinguishable from an operator handing out money.
    """

    message = "ارجاع به پرداخت ناموفق الزامی است."


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


def _assert_required_description(description) -> str:
    """Return the stripped description, or refuse a hold/release that has none.

    Unlike ``_assert_description`` this imposes NO minimum length, and the
    asymmetry is deliberate rather than an oversight. A grant and a revoke are
    admin decisions with no external document behind them, so the note is prose
    and a one-word note is a typo. A hold is frequently booked against a payment
    -- ``HOLD_ALLOWED_SOURCES`` says so -- and the caller may legitimately have
    only a gateway reference or an invoice number to hand, which is short by
    nature. Forcing prose onto that caller would produce filler, and filler is
    worse than a terse reference because it reads like a real explanation.
    """

    if description is None or isinstance(description, bool):
        raise InvalidHoldDescription()
    if not isinstance(description, str) or not description.strip():
        raise InvalidHoldDescription()
    return description.strip()


def _assert_payment_reference(reference) -> str:
    """Refuse a refund with nothing to trace it to.

    Same shape as ``_assert_log_id`` for the same reason: this function is only
    legitimate for a payment that demonstrably failed, so a blank reference is
    not a cosmetic omission -- it is the absence of the only evidence that
    justifies minting the money back.
    """
    if reference is None or isinstance(reference, bool) or (isinstance(reference, str) and not reference.strip()):
        raise InvalidPaymentReference()
    if not isinstance(reference, (str, int)):
        raise InvalidPaymentReference()
    return str(reference).strip()


def _lock_account(account: LedgerAccount) -> LedgerAccount:
    """Re-read an account under ``SELECT ... FOR UPDATE``.

    The lock is what makes the balance check below safe: a second transaction
    charging the same wallet blocks here until the first one commits, so it
    then reads a balance that already reflects the first charge instead of
    racing past the same limit.
    """
    return LedgerAccount.objects.select_for_update().get(pk=account.pk)


def _replay_or_none(
    idempotency_key: Optional[str], *, workspace, debit: LedgerAccount, credit: LedgerAccount, amount_toman: int
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

    ``workspace`` is asserted here rather than left to each caller because the
    lookup is by key ALONE: the legs compared below are the ones the CALLER
    passed in, not the ones recorded on the row, so nothing else about the
    lookup is tenant-scoped.

    THE WORKSPACE ASSERTION COMES FIRST, AHEAD OF
    ``money._assert_same_movement``. It bought nothing the other way round and
    leaked: ``_assert_same_movement`` builds its ``ValueError`` message out of
    the FOUND row's data --
    ``"debit {existing.debit_account_id} != {debit.pk} ... amount_toman
    {existing.amount_toman} != ..."`` -- so a caller in workspace A who guessed
    another workspace's idempotency key was handed that workspace's amount and
    account UUIDs, plus confirmation that the key exists. That is true for all
    six functions, not just the caller-supplied-legs one: "the legs are my own
    workspace-scoped accounts, so the comparison fails loudly" was never not a
    leak, only a leak in a shape that looked like a safety property.

    Moving it costs nothing because ``existing.workspace_id`` does not depend on
    the legs. The assertion stays on the REPLAYED row rather than the
    caller-supplied one -- that is what makes the ``revoke_grant`` fix work,
    since ``revoke_grant``'s legs come from a pk the caller chose.

    The consequence for callers is that a cross-tenant key now raises the plain
    ``WalletError`` with ``WORKSPACE_MISMATCH_MESSAGE`` for all six functions,
    rather than a ``ValueError`` naming the foreign row for five of them. An
    HTTP layer therefore maps it to 403/404 and never sees a 500.
    """
    # ``None`` still means "this caller did not bring a key" -- ``charge_sms``
    # derives one from the log id before ever getting here. A BLANK key is a
    # caller bug and is refused: treated as absent it skips the pre-check,
    # while ``post_entry`` goes on to write "" into the unique column, so the
    # retry protection silently degrades to whatever the unique index catches.
    if idempotency_key is None:
        return None
    if isinstance(idempotency_key, bool) or not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise InvalidIdempotencyKey()
    existing = LedgerEntry.all_objects.filter(idempotency_key=idempotency_key).first()
    if existing is None:
        return None
    if existing.workspace_id != workspace.pk:
        raise WalletError(WORKSPACE_MISMATCH_MESSAGE)
    money._assert_same_movement(existing, debit=debit, credit=credit, amount_toman=amount_toman)
    return existing


def _assert_hold_source(source: str) -> str:
    """Return ``source`` if a hold may be booked under it, refuse it otherwise."""
    if source not in HOLD_ALLOWED_SOURCES:
        raise InvalidHoldSource()
    return source


def _already_reversed(entry: LedgerEntry) -> bool:
    """Whether ``entry`` has a reversal posted against it.

    ``LedgerEntry.reversal_of`` is a real foreign key, so this is exact. The
    earlier version inferred a reversal from mirrored legs, which is wrong the
    moment two grants share an amount: grants are all
    ``debit=spendable, credit=pool``, so grant B of 80 000 has byte-identical
    legs to grant A of 80 000 on the same workspace, and after A was reversed
    the leg mirror of A's reversal matched B as well. ``revoke_grant(B)`` then
    raised ``GrantAlreadyReversed`` for a grant nobody had touched, with no
    in-product way to clear it.

    Queried through ``all_objects`` for the same reason as the idempotency key:
    a soft-deleted reversal still took the money out of the wallet, so it must
    still count as a reversal.

    ``filter(reversal_of_id=...)`` rather than the ``reversals`` reverse
    accessor: Django only exposes a reverse manager on the model's *default*
    manager class, and ``LedgerEntry.all_objects`` is a plain
    ``models.Manager()`` that does not carry it.
    """
    return LedgerEntry.all_objects.filter(reversal_of_id=entry.pk).exists()


def _lock_wallet_row(workspace) -> Wallet:
    """The workspace's ``Wallet`` row, locked, created on first use.

    The lock is what makes ``admin_grant_cap_toman`` enforceable. The cap is
    the one policy limit on how much money an operator can mint, and an
    unsynchronised read lets two concurrent grants both observe "under the cap"
    and jointly blow through it. Every other balance-bearing read in this module
    takes its row lock; the cap read was the exception.

    First-ever grant, where no row exists yet: there is nothing to lock, and
    that is handled rather than skipped. The insert is wrapped in its own
    savepoint so the ``OneToOneField`` violation raised by a concurrent
    creator poisons only the savepoint, and the loser then falls through to
    ``select_for_update`` on the winner's now-committed row. The ``INSERT`` in
    the winner's transaction already holds that row exclusively for itself, so
    the create path needs no separate lock.
    """
    existing = Wallet.objects.select_for_update().filter(workspace=workspace).first()
    if existing is not None:
        return existing

    try:
        with transaction.atomic():
            return Wallet.objects.create(workspace=workspace)
    except IntegrityError:
        return Wallet.objects.select_for_update().get(workspace=workspace)


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

    Returns the entry alone; :func:`grant_from_admin_with_outcome` is this
    function plus the replay fact, for callers that have to tell a client
    whether its key had been used before.
    """
    entry, _replayed = grant_from_admin_with_outcome(
        workspace=workspace,
        amount_toman=amount_toman,
        description=description,
        created_by=created_by,
        idempotency_key=idempotency_key,
    )
    return entry


def grant_from_admin_with_outcome(
    *, workspace, amount_toman: int, description: str, created_by, idempotency_key: str
) -> tuple[LedgerEntry, bool]:
    """Credit a workspace wallet and say whether this call posted it.

    ``(entry, was_replayed)``. ``True`` means the row was already on file --
    found by the ``_replay_or_none`` fast path or won by a concurrent caller
    inside ``post_entry`` -- and nothing was minted.

    The flag is passed all the way up from ``money.post_entry_with_outcome``
    rather than reconstructed from ``created_at``. An HTTP layer has to
    answer 200 for a replay and 201 for a fresh post, and the only way to get
    that right from the outside is to be told; comparing timestamps is a
    wall-clock guess that fails in both directions under clock skew and
    reproduces in CI only by accident.
    """
    _assert_amount(amount_toman)
    description = _assert_description(description)

    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    # ONE pool instance for both the replay comparison and the posting. These
    # were two separate ``_pool_account()`` calls, which happen to return the
    # same row, but the replay's correctness argument then rested on an unstated
    # identity assumption rather than on the code -- the same thing round 2
    # fixed in ``charge_sms``.
    pool = _pool_account()

    # Replay BEFORE the cap check: an admin who lowers the cap between two
    # identical calls must not get ``GrantTooLarge`` for a grant that already
    # posted (see ``_replay_or_none``).
    replay = _replay_or_none(
        idempotency_key, workspace=workspace, debit=spendable, credit=pool, amount_toman=amount_toman
    )
    if replay is not None:
        return replay, True

    with transaction.atomic():
        # Locked, not read plainly (see ``_lock_wallet_row``): without the lock
        # two concurrent grants each observe "under the cap" and jointly exceed
        # it, which is the one limit standing between a mistyped amount and
        # unlimited money an operator can mint.
        cap = _lock_wallet_row(workspace).admin_grant_cap_toman
        if cap and amount_toman > cap:
            raise GrantTooLarge()

        return money.post_entry_with_outcome(
            debit=spendable,
            credit=pool,
            amount_toman=amount_toman,
            source=LedgerSource.ADMIN_GRANT,
            workspace=workspace,
            description=description,
            created_by=created_by,
            idempotency_key=idempotency_key,
        )


def revoke_grant(*, workspace, entry: LedgerEntry, description: str, created_by, idempotency_key: str) -> LedgerEntry:
    """Reverse a grant with a new entry. The original row is never edited or deleted.

    Returns the reversal alone; :func:`revoke_grant_with_outcome` is this
    function plus the replay fact.
    """
    reversal, _replayed = revoke_grant_with_outcome(
        workspace=workspace,
        entry=entry,
        description=description,
        created_by=created_by,
        idempotency_key=idempotency_key,
    )
    return reversal


def revoke_grant_with_outcome(
    *, workspace, entry: LedgerEntry, description: str, created_by, idempotency_key: str
) -> tuple[LedgerEntry, bool]:
    """Reverse a grant and say whether this call posted the reversal.

    ``(reversal, was_replayed)``. Same contract and same reasoning as
    :func:`grant_from_admin_with_outcome`: the fact is stated by the layer
    that knows it, not reconstructed from a timestamp by the caller.

    The reversal is the strict mirror of the entry being reversed: its debit
    side is the original's CREDIT account and vice versa. That is what makes it
    a reversal rather than a second copy of the same movement.

    ``entry`` is the ``LedgerEntry`` instance to reverse -- the caller fetches
    it, so an HTTP layer resolves the pk from the request body to a row before
    calling this. The row is checked on two axes before anything is reversed:
    it must belong to ``workspace``, and it must actually BE an admin grant
    that has not been reversed yet. Reversing an arbitrary ledger row on a pk
    from a request body is a confused-deputy surface -- handed an SMS charge it
    would quietly refund an SMS charge.

    RAISES ``LedgerEntry.DoesNotExist`` for a pk that is not live. The locked
    re-read below goes through ``LedgerEntry.objects``, the soft-delete-filtering
    manager, so an ``entry`` that was soft deleted between the caller's fetch
    and this call is indistinguishable from a pk that never existed, and both
    raise ``DoesNotExist`` rather than a ``WalletError``. Deliberate, and pinned
    by ``test_revoke_grant_raises_does_not_exist_for_an_entry_that_is_not_live``:
    this is not a policy decision about the caller's wallet, it is the absence
    of the resource, and the caller must not be able to tell the two apart by
    catching one exception type. An HTTP layer should map it to 404 -- the row
    is gone, so nothing about the grant can be said -- and must catch
    ``LedgerEntry.DoesNotExist`` alongside ``WalletError``.
    """
    _assert_amount(entry.amount_toman)
    description = _assert_description(description)

    spendable, _held = money.get_or_create_wallet_accounts(workspace)

    # Replay BEFORE the workspace, source and affordability checks. A retry of a
    # completed reversal has already drained the wallet by construction, so an
    # affordability check ahead of this one raises ``InsufficientBalance`` for
    # work that is already done (see ``_replay_or_none``).
    #
    # The replay's legs are built from ``entry``, which is caller-supplied and
    # may name another tenant's grant, so the workspace assertion lives INSIDE
    # ``_replay_or_none``. Checking it only further down -- as this function
    # did when the replay was hoisted -- meant a caller in workspace A who
    # guessed workspace B's grant pk and reversal key satisfied
    # ``_assert_same_movement`` and got B's entry back without a single
    # workspace check running.
    replay = _replay_or_none(
        idempotency_key,
        workspace=workspace,
        debit=entry.credit_account,
        credit=entry.debit_account,
        amount_toman=entry.amount_toman,
    )
    if replay is not None:
        return replay, True

    with transaction.atomic():
        # Re-read under the lock so the amount and legs come from committed
        # state, and so two concurrent revocations serialise on one row.
        locked = LedgerEntry.objects.select_for_update().get(pk=entry.pk)
        _assert_amount(locked.amount_toman)

        if locked.workspace_id != workspace.pk:
            raise WalletError(WORKSPACE_MISMATCH_MESSAGE)

        if locked.source != LedgerSource.ADMIN_GRANT:
            raise NotAGrantEntry()

        # Exact: the FK points at THIS row, so a same-amount sibling grant on
        # the same workspace is not mistaken for a reversal of this one.
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

        entry_reversal, replayed = money.post_entry_with_outcome(
            debit=locked.credit_account,
            credit=locked.debit_account,
            amount_toman=locked.amount_toman,
            source=LedgerSource.GRANT_REVERSAL,
            workspace=workspace,
            description=description,
            created_by=created_by,
            idempotency_key=idempotency_key,
        )
        # Stamped after the write because ``money.post_entry`` is a pure
        # double-entry primitive with no notion of reversal. It runs inside this
        # same atomic block, so the entry and its back-reference commit or roll
        # back together -- a reversal can never exist without saying which
        # grant it undid, which is the property ``_already_reversed`` relies on.
        entry_reversal.reversal_of_id = locked.pk
        # ``disable_auto_set_user`` because ``BaseModel.save`` otherwise takes
        # its crum branch on this second write and clobbers the in-memory
        # ``created_by`` with ``None`` outside a request. ``update_fields``
        # keeps the row's author intact; this keeps the returned object honest.
        entry_reversal.save(
            update_fields=["reversal_of_id", "updated_at"],
            disable_auto_set_user=True,
        )
        return entry_reversal, replayed


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

    ``log_id`` is mandatory and is written into the entry's ``description``
    UNCONDITIONALLY -- an override is appended to the canonical
    ``"پیامک {log_id}"`` rather than replacing it. Before, a caller who
    overrode ``description`` and ``idempotency_key`` together left no trace of
    which notification log was charged, and the description is the only place
    that reference exists. The key is the index, not the story.

    ``created_by`` is the actor when one exists -- SMS charges are usually
    taken outside a request (a Celery task, where crum yields ``None``), so it
    is ``None`` far more often here than for a grant.
    """
    _assert_log_id(log_id)
    _assert_amount(amount_toman)
    # ``is not None`` rather than ``or``: a caller who explicitly passed a blank
    # key must be told so by ``_replay_or_none``, not silently handed the
    # log-derived key it did not ask for.
    key = idempotency_key if idempotency_key is not None else f"sms:{log_id}:charge"

    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    # ONE expense instance for both the replay comparison and the posting. The
    # two used to be separate ``_sms_expense_account()`` calls, which happen to
    # return the same row, but the replay's correctness argument then rested on
    # an unstated identity assumption instead of on the code.
    expense = _sms_expense_account()

    replay = _replay_or_none(key, workspace=workspace, debit=expense, credit=spendable, amount_toman=amount_toman)
    if replay is not None:
        return replay

    label = f"پیامک {log_id}"
    if description and description.strip():
        label = f"{label} — {description.strip()}"

    with transaction.atomic():
        locked_spendable = _lock_account(spendable)

        if not money.wallet_balance_is_enough(workspace, amount_toman):
            raise InsufficientBalance()

        return money.post_entry(
            debit=expense,
            credit=locked_spendable,
            amount_toman=amount_toman,
            source=LedgerSource.SMS_CHARGE,
            workspace=workspace,
            description=label,
            created_by=created_by,
            idempotency_key=key,
        )


def hold_funds(
    *,
    workspace,
    amount_toman: int,
    description: str,
    source: str = LedgerSource.HOLD,
    idempotency_key: str,
    created_by=None,
) -> LedgerEntry:
    """Move money out of the spendable balance into the hold.

    Used when a payment was taken but could not be applied. The workspace
    owner cannot spend or see this money until an admin decides.

    ``source`` defaults to ``LedgerSource.HOLD``, which is what a hold IS.
    Booking one as ``REFUND`` (the old default in practice) put holds in the
    "Refund" bucket of every statement, so the two were indistinguishable. The
    value is validated against ``HOLD_ALLOWED_SOURCES`` so a caller cannot
    mislabel a hold as an admin grant and make the grant statements a lie.

    ``created_by`` records the operator who withheld the money -- a hold is an
    action taken on a workspace, not a side effect of one.

    ``description`` is REQUIRED and is written to the entry. It is required for
    the same reason ``refund_to_spendable`` requires a ``reference``: ``source``
    is a machine label out of a four-value allow-list, not a reason, and a hold
    is money taken out of a customer's reach with no other record of why. The
    ledger is the only place that reason can live, so an optional description
    here would restore exactly the hole the rest of the module closes -- money an
    operator withheld from someone, recorded as an unexplained number. A hold
    that is later released without ever having been explained leaves two
    unattributed entries and no way to answer the owner's question. Making it
    required also means the HTTP layer cannot ship an endpoint that accepts a
    hold with no reason field.

    No minimum length, unlike a grant description: see
    ``_assert_required_description`` -- a hold is frequently booked against a
    payment, and a gateway reference or invoice number is a legitimate, short
    reason.
    """
    _assert_amount(amount_toman)
    _assert_hold_source(source)
    description = _assert_required_description(description)

    spendable, held = money.get_or_create_wallet_accounts(workspace)

    replay = _replay_or_none(
        idempotency_key, workspace=workspace, debit=held, credit=spendable, amount_toman=amount_toman
    )
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
            description=description,
            created_by=created_by,
            idempotency_key=idempotency_key,
        )


def release_hold(
    *, workspace, amount_toman: int, description: str, idempotency_key: str, created_by=None
) -> LedgerEntry:
    """Return held money to the spendable balance.

    ``description`` is REQUIRED for the same reason as in ``hold_funds``, and
    for one extra reason specific to a release: the release is the moment a
    customer gets an answer, and it is the operator's chance to record why. A
    hold taken with a reason and released without one still leaves the hold
    unexplained in the workspace's own view of the money.
    """
    _assert_amount(amount_toman)
    description = _assert_required_description(description)

    spendable, held = money.get_or_create_wallet_accounts(workspace)

    replay = _replay_or_none(
        idempotency_key, workspace=workspace, debit=spendable, credit=held, amount_toman=amount_toman
    )
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
            description=description,
            created_by=created_by,
            idempotency_key=idempotency_key,
        )


def refund_to_spendable(
    *, workspace, amount_toman: int, reason: str, reference: str, idempotency_key: str, created_by=None
) -> LedgerEntry:
    """Return money directly to the spendable balance without passing through a hold.

    Only for a payment the gateway explicitly rejected, where we know no
    money was ever taken.

    ``reference`` is MANDATORY and names the payment that failed -- a
    ``PaymentTransaction`` id, an invoice number, or a gateway reference id.
    The docstring above has always asserted "gateway explicitly rejected", and
    free-text ``reason`` alone made that unenforceable: any caller could mint
    money into a workspace by describing why. A refund nobody can trace to a
    transaction or invoice is indistinguishable from an operator handing out
    cash, so the reference is required and is written into the entry's
    description next to the reason.
    """
    _assert_amount(amount_toman)
    reference = _assert_payment_reference(reference)

    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    reversal = money.get_or_create_account(GATEWAY_REVERSAL_ACCOUNT_CODE, GATEWAY_REVERSAL_ACCOUNT_KIND, "برگشت درگاه")

    replay = _replay_or_none(
        idempotency_key, workspace=workspace, debit=spendable, credit=reversal, amount_toman=amount_toman
    )
    if replay is not None:
        return replay

    # ``post_entry`` writes a single row, so the block here is not for its own
    # sake -- it keeps all six money functions structurally identical, so the
    # next reader does not have to work out which ones wrap their work.
    with transaction.atomic():
        return money.post_entry(
            debit=spendable,
            credit=reversal,
            amount_toman=amount_toman,
            source=LedgerSource.REFUND,
            workspace=workspace,
            description=f"{(reason or '').strip()} — {reference}".strip(" —"),
            created_by=created_by,
            idempotency_key=idempotency_key,
        )
