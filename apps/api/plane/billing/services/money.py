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

    @staticmethod
    def gateway_receivable(gateway_code: str) -> str:
        return f"gateway:{gateway_code}:receivable"


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
    a balance.

    The ``transaction`` argument names the ``PaymentTransaction`` this entry
    settles, which shadows ``django.db.transaction`` inside this scope; the
    module imports the database one as ``db_transaction`` for that reason.
    """
    if debit.pk == credit.pk:
        raise ValueError("debit and credit accounts must differ")
    if amount_toman <= 0:
        raise ValueError("amount_toman must be positive")

    existing = LedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing

    try:
        with db_transaction.atomic():
            return LedgerEntry.objects.create(
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
    except IntegrityError:
        # Lost a race against a concurrent replay of the same key.
        return LedgerEntry.objects.get(idempotency_key=idempotency_key)


def _signed_total(account: LedgerAccount, workspace=None) -> int:
    """Debits minus credits for one account, respecting its normal side.

    Two aggregates over ONE account, never one pass over a kind. A
    single ``Case``/``When`` over ``debit_account__kind`` is
    first-match-wins, so it silently drops the credit leg of an entry
    whose debit side is debit-normal — an ``ASSET -> ADMIN_POOL`` posting
    would contribute ``+amount`` and a two-credit-normal entry would
    contribute nothing.
    """
    entries = LedgerEntry.objects.filter(workspace=workspace) if workspace is not None else LedgerEntry.objects.all()
    debit_total = entries.filter(debit_account=account).aggregate(total=Sum("amount_toman"))["total"] or 0
    credit_total = entries.filter(credit_account=account).aggregate(total=Sum("amount_toman"))["total"] or 0

    if account.is_debit_normal:
        return debit_total - credit_total
    return credit_total - debit_total


def account_balance(account: LedgerAccount, workspace=None) -> int:
    """Balance of a single account. Positive means the account holds money."""
    return _signed_total(account, workspace=workspace)


def wallet_balance(workspace) -> int:
    """Spendable wallet balance for a workspace. Never returns a negative value silently."""
    spendable, _held = get_or_create_wallet_accounts(workspace)
    return max(0, _signed_total(spendable, workspace=workspace))


def wallet_hold_balance(workspace) -> int:
    """How much of the workspace's money is currently withheld."""
    _spendable, held = get_or_create_wallet_accounts(workspace)
    return max(0, _signed_total(held, workspace=workspace))
