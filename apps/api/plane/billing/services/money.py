# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Pure balance arithmetic for the double entry ledger.

This module owns every money movement in the product. It deliberately
knows nothing about requests, users or permissions so that it can be
tested without a database and reused by every subsystem that spends or
receives money.

No balance is ever stored. ``account_balance`` derives it from entries.
"""

# Python imports
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, Iterable
from uuid import UUID

# Django imports
from django.db import IntegrityError, transaction as db_transaction
from django.db.models import Sum

# Module imports
from plane.billing.models import LedgerAccount, LedgerAccountKind, LedgerEntry

# All Toman amounts are rounded to the nearest 1,000 so an invoice reads cleanly.
ROUNDING_UNIT = Decimal("1000")


class WalletAccountCode:
    """Account codes for the two sides of a workspace wallet."""

    @staticmethod
    def wallet_default(workspace_pk) -> str:
        """Spendable balance."""
        return f"wallet:default:{workspace_pk}"

    @staticmethod
    def wallet_hold(workspace_pk) -> str:
        """Balance withheld pending an admin decision. Never spendable."""
        return f"wallet:hold:{workspace_pk}"


class LedgerAccountCode:
    """Account codes that are not a side of a workspace wallet.

    A gateway receivable is money owed to us by a payment gateway. It has no
    workspace and is not spendable, so it does not belong on
    :class:`WalletAccountCode`, which is exactly the pair of sides of one
    workspace's wallet.
    """

    @staticmethod
    def gateway_receivable(gateway_code: str) -> str:
        return f"gateway:{gateway_code}:receivable"


# The single account an admin grant is drawn from. No code owns it, so it is a
# bare constant rather than a method on either class. Task 4 (charging a
# workspace) consumes it as the credit side of ``admin -> wallet:default``.
ADMIN_GRANT_POOL = "admin_grant_pool"


def round_to_toman(value: Decimal) -> int:
    """Round to the nearest 1,000 Toman, halves going up.

    ``Decimal.quantize(ROUNDING_UNIT)`` does NOT do this. ``quantize`` sets the
    result's DECIMAL EXPONENT, and ``Decimal("1000")`` has exponent 0, so it is
    a no-op: ``Decimal("1234.4").quantize(Decimal("1000"))`` is ``Decimal("1234")``.
    Rounding to a multiple of 1,000 means dividing by 1,000 first, quantizing to
    a whole number, then scaling back.
    """
    units = (Decimal(value) / ROUNDING_UNIT).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(units * ROUNDING_UNIT)


def get_or_create_account(code: str, kind: str, title: str, workspace=None) -> LedgerAccount:
    """Fetch an account by its stable code, creating it the first time.

    Must revive a soft-deleted row rather than fall over on it. Every
    model in this project inherits ``SoftDeleteModel``, so ``delete()``
    only stamps ``deleted_at`` and the row keeps occupying its unique
    ``code``. The default manager hides it, so a plain ``get_or_create``
    would try to insert a duplicate and raise ``IntegrityError``.
    """
    account = LedgerAccount.objects.filter(code=code).first()
    if account is not None:
        return account

    revived = LedgerAccount.all_objects.filter(code=code, deleted_at__isnull=False).first()
    if revived is not None:
        revived.deleted_at = None
        revived.kind = kind
        revived.title = title or revived.title
        revived.save(update_fields=["deleted_at", "kind", "title", "updated_at"])
        return revived

    return LedgerAccount.objects.create(code=code, kind=kind, title=title, workspace=workspace)


def get_or_create_wallet_accounts(workspace) -> tuple[LedgerAccount, LedgerAccount]:
    """The spendable and held accounts of a workspace, created on demand."""
    spendable = get_or_create_account(
        WalletAccountCode.wallet_default(workspace.pk), LedgerAccountKind.ASSET, "موجودی قابل خرج", workspace
    )
    # ASSET, not LIABILITY. A hold restricts money the workspace still owns, so
    # it is restricted cash on the debit-normal side; it is not money owed to a
    # third party. Reading it as a credit-normal liability inverts its sign and
    # ``wallet_hold_balance`` clamps the negative to 0.
    held = get_or_create_account(
        WalletAccountCode.wallet_hold(workspace.pk), LedgerAccountKind.ASSET, "موجودی قفل‌شده", workspace
    )
    return spendable, held


def _find_entry_any_state(idempotency_key: str):
    """The row for ``idempotency_key``, live or soft deleted, or ``None``.

    ``LedgerEntry.idempotency_key`` is unique across soft deleted rows too (see
    the field's comment in ``models.py``): ``delete()`` only stamps
    ``deleted_at``, so the key stays taken and a plain ``objects`` lookup misses
    the row that is still occupying it. Looking through ``all_objects`` and then
    reviving is the only way to retry an operation whose entry was deleted.
    """
    return LedgerEntry.all_objects.filter(idempotency_key=idempotency_key).first()


def _assert_same_movement(existing: LedgerEntry, *, debit, credit, amount_toman: int) -> None:
    """Refuse to treat a same-key/different-payload call as a replay.

    Returning the existing row without this check turns a key-construction bug
    in a caller into a silent no-op that moved a different amount of money.
    """
    mismatches = []
    if existing.debit_account_id != debit.pk:
        mismatches.append(f"debit {existing.debit_account_id} != {debit.pk}")
    if existing.credit_account_id != credit.pk:
        mismatches.append(f"credit {existing.credit_account_id} != {credit.pk}")
    if existing.amount_toman != amount_toman:
        mismatches.append(f"amount_toman {existing.amount_toman} != {amount_toman}")
    if mismatches:
        raise ValueError(
            f"idempotency_key {existing.idempotency_key!r} was already used for a different movement "
            f"({'; '.join(mismatches)}); refusing to post a second movement under the same key"
        )


def post_entry_with_outcome(
    *,
    debit: LedgerAccount,
    credit: LedgerAccount,
    amount_toman: int,
    source: str,
    workspace=None,
    description: str = "",
    created_by=None,
    invoice=None,
    transaction=None,
    idempotency_key: str,
) -> tuple[LedgerEntry, bool]:
    """Write one balanced movement of money and say whether it was a replay.

    Returns ``(entry, was_replayed)``. ``was_replayed`` is ``True`` when the
    row returned already existed -- either the fast path found it, or this
    call lost the race and the ``IntegrityError`` handler re-looked it up.
    Both are replays; neither posted anything new.

    The flag exists because the entry alone cannot tell the two apart, and
    every attempt to infer it afterwards is a wall-clock comparison against
    ``created_at``, which is wrong in both directions: a clock that steps
    backwards between the two reads reports a fresh post as a replay, and
    an app host whose clock runs ahead of the database host reports a replay
    as fresh. Both produce the correct ledger and the wrong answer, and
    neither reproduces reliably in CI. The fact is known here and only here,
    so it is stated here.

    :func:`post_entry` is this function with the flag dropped; it keeps its
    original signature and return type for the callers that do not care.

    The ``transaction`` argument names the ``PaymentTransaction`` this entry
    settles, which shadows ``django.db.transaction`` inside this scope; the
    module imports the database one as ``db_transaction`` for that reason.
    """
    if debit.pk == credit.pk:
        raise ValueError("debit and credit accounts must differ")
    if amount_toman <= 0:
        raise ValueError("amount_toman must be positive")

    existing = _find_entry_any_state(idempotency_key)
    if existing is not None:
        _assert_same_movement(existing, debit=debit, credit=credit, amount_toman=amount_toman)
        return _revive_entry(existing), True

    try:
        with db_transaction.atomic():
            entry = LedgerEntry(
                debit_account=debit,
                credit_account=credit,
                amount_toman=amount_toman,
                source=source,
                workspace=workspace,
                description=description,
                created_by=created_by,
                invoice=invoice,
                transaction=transaction,
                idempotency_key=idempotency_key,
            )
            # Saved explicitly rather than via ``objects.create()`` so that
            # ``disable_auto_set_user`` can be passed. ``create()`` forwards its
            # kwargs to ``__init__``, never to ``save()``, so the author set above
            # would reach ``BaseModel.save`` with no ``created_by_id`` keyword --
            # save() would take its crum branch and overwrite it with the current
            # request user, which is None outside a request. The explicit author
            # would be silently dropped.
            entry.save(
                force_insert=True,
                disable_auto_set_user=created_by is not None,
            )
            return entry, False
    except IntegrityError as error:
        # Either we lost a race against a concurrent replay of the same key, or
        # the create failed for an unrelated reason (stale FK, PROTECT on a
        # deleted account, a bad ``source``). Only the first is recoverable, so
        # re-look the key up and, if there is no such row, re-raise the original
        # error rather than reporting a missing entry and losing the diagnostic.
        winner = _find_entry_any_state(idempotency_key)
        if winner is None:
            raise error
        _assert_same_movement(winner, debit=debit, credit=credit, amount_toman=amount_toman)
        return _revive_entry(winner), True


def post_entry(
    *,
    debit: LedgerAccount,
    credit: LedgerAccount,
    amount_toman: int,
    source: str,
    workspace=None,
    description: str = "",
    created_by=None,
    invoice=None,
    transaction=None,
    idempotency_key: str,
) -> LedgerEntry:
    """Write one balanced movement of money.

    Replaying the same ``idempotency_key`` returns the original row and
    posts nothing, so a gateway callback that arrives twice cannot double
    a balance. If the key was already used for a *different* movement this
    raises ``ValueError`` rather than silently succeeding.

    A key whose entry was soft deleted is revived (see
    :func:`_find_entry_any_state`), not re-posted, because the key is still
    unique across deleted rows.

    The ``transaction`` argument names the ``PaymentTransaction`` this entry
    settles, which shadows ``django.db.transaction`` inside this scope; the
    module imports the database one as ``db_transaction`` for that reason.

    Deliberately blind to whether it replayed. A caller that must report
    that to a client -- an HTTP layer answering 200 or 201 -- uses
    :func:`post_entry_with_outcome`, which is this function with the fact
    attached. Two spellings rather than an extra return value because every
    other caller wants only the entry, and changing their return type would
    make them unpack a tuple they would immediately drop.
    """
    entry, _was_replayed = post_entry_with_outcome(
        debit=debit,
        credit=credit,
        amount_toman=amount_toman,
        source=source,
        workspace=workspace,
        description=description,
        created_by=created_by,
        invoice=invoice,
        transaction=transaction,
        idempotency_key=idempotency_key,
    )
    return entry


def _revive_entry(entry: LedgerEntry) -> LedgerEntry:
    """Clear ``deleted_at`` on a soft-deleted entry and return it."""
    if entry.deleted_at is not None:
        entry.deleted_at = None
        entry.save(update_fields=["deleted_at", "updated_at"])
    return entry


def _signed_total(account: LedgerAccount, workspace=None) -> int:
    """Debits minus credits for one account, respecting its normal side.

    Two aggregates over ONE account, never one pass over a kind. A
    single ``Case``/``When`` over ``debit_account__kind`` is
    first-match-wins, so it silently drops the credit leg of an entry
    whose debit side is debit-normal — an ``ASSET -> ADMIN_POOL`` posting
    would contribute ``+amount`` and a two-credit-normal entry would
    contribute nothing.

    Scoping: an account that BELONGS to a workspace (its ``workspace`` FK is
    set) owns every entry that touches it, so it is filtered by account alone.
    Filtering those entries by ``LedgerEntry.workspace`` as well would be
    redundant scoping against a second, independently optional notion of
    ownership: ``post_entry`` accepts ``workspace=None``, so an entry posted
    against a workspace account without a workspace is invisible here and the
    balance silently under-counts — exactly the failure "compute it, never store
    it" exists to prevent. The ``workspace`` argument is therefore only used for
    GLOBAL accounts (pool, gateway, admin), where it is genuinely needed to
    separate one tenant's postings from another's.
    """
    if account.workspace_id is not None:
        entries = LedgerEntry.objects.all()
    elif workspace is not None:
        entries = LedgerEntry.objects.filter(workspace=workspace)
    else:
        entries = LedgerEntry.objects.all()
    debit_total = entries.filter(debit_account=account).aggregate(total=Sum("amount_toman"))["total"] or 0
    credit_total = entries.filter(credit_account=account).aggregate(total=Sum("amount_toman"))["total"] or 0

    if account.is_debit_normal:
        return debit_total - credit_total
    return credit_total - debit_total


def account_balance(account: LedgerAccount, workspace=None) -> int:
    """Balance of a single account. Positive means the account holds money."""
    return _signed_total(account, workspace=workspace)


def wallet_balance(workspace, *, clamp_negative: bool = True) -> int:
    """Spendable wallet balance for a workspace.

    ``clamp_negative`` (the default) floors the result at 0, because a
    spendable figure is never negative as far as a caller is concerned — but
    the clamp DOES hide an overdraw. Pass ``clamp_negative=False`` to see the
    raw signed figure, which is what a caller must do before it decides whether
    a charge is affordable: comparing ``amount_toman`` against a clamped
    balance cannot tell a full wallet from an overdrawn one.
    """
    spendable, _held = get_or_create_wallet_accounts(workspace)
    total = _signed_total(spendable)
    return max(0, total) if clamp_negative else total


def wallet_balance_is_enough(workspace, amount_toman: int) -> bool:
    """Whether ``amount_toman`` can be drawn from the workspace's spendable balance.

    Reads the UNCLAMPED balance, so an already-overdrawn wallet fails here
    instead of being reported as an empty-but-affordable one.
    """
    return wallet_balance(workspace, clamp_negative=False) >= amount_toman


def wallet_hold_balance(workspace) -> int:
    """How much of the workspace's money is currently withheld."""
    _spendable, held = get_or_create_wallet_accounts(workspace)
    return max(0, _signed_total(held))


def wallet_balances(workspace_ids: Iterable[UUID]) -> Dict[UUID, int]:
    """Spendable balance for many workspaces in three queries.

    The admin workspace list needs a balance per row. Calling
    ``wallet_balance`` per workspace is two aggregate queries each, which turns
    a 50-row page into 100 round trips.

    A workspace whose wallet has no ledger account yet is simply absent from the
    result, and the caller reads that as zero. It is NOT created here:
    ``get_or_create_wallet_accounts`` would write a row per workspace on a
    read-only list page, so a GET would create hundreds of rows. The detail page
    already creates them on demand.

    The aggregates are over one account set, never one pass over a kind. A
    single ``Case``/``When`` over ``debit_account__kind`` is first-match-wins, so
    it silently drops the credit leg of an entry whose debit side is
    debit-normal -- the exact defect ``_signed_total``'s docstring warns about.
    """
    # Materialised once: ``workspace_ids`` is typed as an Iterable, so a caller
    # passing a generator would otherwise be exhausted by the first loop.
    workspace_ids = list(workspace_ids)
    if not workspace_ids:
        return {}

    account_ids = list(
        LedgerAccount.objects.filter(
            workspace_id__in=workspace_ids,
            # NOT a kind filter. BOTH wallet legs are ASSET -- see the note in
            # get_or_create_wallet_accounts above -- so filtering on kind=ASSET
            # would return the HELD account as well and a page row would report
            # a wallet as fully funded when its money is in hold. The spendable
            # leg is identified by its account code, which is the only thing
            # that distinguishes the two accounts.
            code__in=[WalletAccountCode.wallet_default(workspace_id) for workspace_id in workspace_ids],
        ).values_list("id", "workspace_id")
    )
    if not account_ids:
        return {}

    ids = [account_id for account_id, _workspace_id in account_ids]
    workspace_by_account = dict(account_ids)

    debits: Dict[UUID, int] = {}
    for row in (
        LedgerEntry.objects.filter(debit_account_id__in=ids)
        .values("debit_account_id")
        .annotate(total=Sum("amount_toman"))
    ):
        debits[row["debit_account_id"]] = row["total"] or 0

    credits: Dict[UUID, int] = {}
    for row in (
        LedgerEntry.objects.filter(credit_account_id__in=ids)
        .values("credit_account_id")
        .annotate(total=Sum("amount_toman"))
    ):
        credits[row["credit_account_id"]] = row["total"] or 0

    # NO ``LedgerEntry.workspace`` filter, for the reason ``_signed_total``
    # gives: a workspace-owned account owns every entry that touches it, and
    # ``post_entry`` accepts ``workspace=None``, so scoping the entries as well
    # would make those postings invisible and under-count the balance.
    #
    # Every wallet account is ASSET (debit-normal), so the sign is fixed here.
    # Read ``is_debit_normal`` from the account instead if a wallet account ever
    # stops being debit-normal; the assumption is local to this return.
    return {
        workspace_by_account[account_id]: debits.get(account_id, 0) - credits.get(account_id, 0) for account_id in ids
    }
