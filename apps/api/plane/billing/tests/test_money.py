# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Schema level invariants for the double entry ledger."""

# Third party imports
import pytest

# Django imports
from django.db import IntegrityError, transaction
from django.db.models import Sum

# Module imports
from plane.billing.models import LedgerAccount, LedgerAccountKind, LedgerEntry, LedgerSource, Wallet
from plane.db.models import User, Workspace

pytestmark = pytest.mark.django_db


def make_workspace(name: str, slug: str, email: str) -> Workspace:
    """A workspace always needs an owner; the column is NOT NULL with no default."""
    owner = User.objects.create(email=email, first_name="Wallet", last_name="Owner")
    return Workspace.objects.create(name=name, slug=slug, owner=owner)


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


def test_wallet_is_one_per_workspace():
    workspace = make_workspace("تیم", "team-wallet-test", "owner-team-wallet@example.com")
    Wallet.objects.create(workspace=workspace)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Wallet.objects.create(workspace=workspace)


def test_balance_is_the_sum_of_entries_not_a_column():
    """A wallet has no balance column; the sum of debits minus credits is the balance."""
    workspace = make_workspace("تیم ۲", "team-sum-test", "owner-team-sum@example.com")
    wallet = Wallet.objects.create(workspace=workspace)
    assert not hasattr(wallet, "balance_toman")

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
    balance = LedgerEntry.objects.filter(workspace=workspace).aggregate(total=Sum("amount_toman"))["total"]
    assert balance == 120_000