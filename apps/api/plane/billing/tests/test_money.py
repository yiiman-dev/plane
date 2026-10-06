# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Schema level invariants for the double entry ledger."""

# Third party imports
import pytest

# Django imports
from django.db import IntegrityError, transaction
from django.db.models import Case, F, IntegerField, Sum, Value, When

# Module imports
from plane.billing.models import LedgerAccount, LedgerAccountKind, LedgerEntry, LedgerSource, Wallet

pytestmark = pytest.mark.django_db


# Mirrors the set ``LedgerAccount.is_debit_normal`` hard codes; that property has
# its own test below so the two cannot drift apart silently.
DEBIT_NORMAL_KINDS = (LedgerAccountKind.ASSET, LedgerAccountKind.ADMIN_POOL)


def account_balance(workspace) -> int:
    """Sum entries with the correct sign per account side.

    A debit-normal account (ASSET, ADMIN_POOL) grows with debits and shrinks with
    credits; a credit-normal one does the opposite. A plain ``Sum("amount_toman")``
    is volume, not balance.
    """
    return (
        LedgerEntry.objects.filter(workspace=workspace).aggregate(
            total=Sum(
                Case(
                    When(debit_account__kind__in=DEBIT_NORMAL_KINDS, then=F("amount_toman")),
                    When(credit_account__kind__in=DEBIT_NORMAL_KINDS, then=-F("amount_toman")),
                    default=Value(0, output_field=IntegerField()),
                )
            )
        )["total"]
        or 0
    )


def test_account_code_is_unique():
    LedgerAccount.objects.create(code="wallet:default:1", kind=LedgerAccountKind.ASSET, title="کیف پول")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerAccount.objects.create(code="wallet:default:1", kind=LedgerAccountKind.ASSET, title="تکراری")


def test_entry_rejects_identical_debit_and_credit():
    account = LedgerAccount.objects.create(code="a", kind=LedgerAccountKind.ASSET, title="الف")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                debit_account=account,
                credit_account=account,
                amount_toman=1000,
                source=LedgerSource.ADMIN_GRANT,
                idempotency_key="k1",
            )


def test_entry_rejects_zero_amount():
    debit = LedgerAccount.objects.create(code="d", kind=LedgerAccountKind.ASSET, title="بدهکار")
    credit = LedgerAccount.objects.create(code="c", kind=LedgerAccountKind.LIABILITY, title="بستانه")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                debit_account=debit,
                credit_account=credit,
                amount_toman=0,
                source=LedgerSource.ADMIN_GRANT,
                idempotency_key="k2",
            )


def test_idempotency_key_is_unique():
    debit = LedgerAccount.objects.create(code="d2", kind=LedgerAccountKind.ASSET, title="بدهکار")
    credit = LedgerAccount.objects.create(code="c2", kind=LedgerAccountKind.REVENUE, title="درآمد")
    LedgerEntry.objects.create(
        debit_account=debit,
        credit_account=credit,
        amount_toman=500,
        source=LedgerSource.ADMIN_GRANT,
        idempotency_key="dup",
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                debit_account=debit,
                credit_account=credit,
                amount_toman=500,
                source=LedgerSource.ADMIN_GRANT,
                idempotency_key="dup",
            )


def test_wallet_is_one_per_workspace(make_workspace):
    workspace = make_workspace(name="تیم")
    Wallet.objects.create(workspace=workspace)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Wallet.objects.create(workspace=workspace)


def test_balance_is_the_sum_of_entries_not_a_column(make_workspace):
    """No model carries a balance column; the balance is debits minus credits."""
    workspace = make_workspace(name="تیم ۲")
    wallet = Wallet.objects.create(workspace=workspace)

    # The constraint is "no writable balance column anywhere", so check the
    # metadata rather than a single guessed attribute name.
    for model in (Wallet, LedgerAccount):
        field_names = {field.name for field in model._meta.get_fields()}
        assert not any("balance" in name for name in field_names), f"{model.__name__} has a balance column"
    assert not hasattr(type(wallet), "balance_toman")  # no property or descriptor either

    default = LedgerAccount.objects.create(
        code=f"wallet:default:{workspace.pk}", kind=LedgerAccountKind.ASSET, title="کیف پول", workspace=workspace
    )
    pool = LedgerAccount.objects.create(
        code="admin_grant_pool", kind=LedgerAccountKind.ADMIN_POOL, title="اعتبار ادمین"
    )
    LedgerEntry.objects.create(
        debit_account=default,
        credit_account=pool,
        amount_toman=120_000,
        source=LedgerSource.ADMIN_GRANT,
        workspace=workspace,
        idempotency_key="sum-1",
    )
    assert account_balance(workspace) == 120_000

    # A credit side posting against the same wallet must reduce the balance,
    # not add to it. Volume would be 130_000 here.
    revenue = LedgerAccount.objects.create(code="plan_revenue", kind=LedgerAccountKind.REVENUE, title="درآمد اشتراک")
    LedgerEntry.objects.create(
        debit_account=revenue,
        credit_account=default,
        amount_toman=30_000,
        source=LedgerSource.PLAN_PURCHASE,
        workspace=workspace,
        idempotency_key="sum-2",
    )
    assert account_balance(workspace) == 90_000


def test_is_debit_normal_follows_kind():
    for kind, expected in (
        (LedgerAccountKind.ASSET, True),
        (LedgerAccountKind.ADMIN_POOL, True),
        (LedgerAccountKind.LIABILITY, False),
        (LedgerAccountKind.REVENUE, False),
        (LedgerAccountKind.GATEWAY_SETTLEMENT, False),
    ):
        account = LedgerAccount.objects.create(code=f"is-debit-{kind}", kind=kind)
        assert account.is_debit_normal is expected
