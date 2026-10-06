# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Schema level invariants for the double entry ledger."""

# Python imports
from decimal import Decimal

# Third party imports
import pytest

# Django imports
from django.db import IntegrityError, transaction
from django.db.models import Case, F, IntegerField, Sum, Value, When
from django.utils import timezone as django_timezone

# Module imports
from plane.billing.models import LedgerAccount, LedgerAccountKind, LedgerEntry, LedgerSource, Wallet

pytestmark = pytest.mark.django_db


# Mirrors the set ``LedgerAccount.is_debit_normal`` hard codes; that property has
# its own test below so the two cannot drift apart silently.
DEBIT_NORMAL_KINDS = (LedgerAccountKind.ASSET, LedgerAccountKind.ADMIN_POOL)


def _side_total(workspace, side: str, account) -> int:
    """Total of ``amount_toman`` for entries where ``account`` sits on ``side``."""
    entries = LedgerEntry.objects.filter(workspace=workspace)
    return (
        entries.aggregate(
            total=Sum(
                Case(
                    When(**{f"{side}_account": account}, then=F("amount_toman")),
                    default=Value(0, output_field=IntegerField()),
                )
            )
        )["total"]
        or 0
    )


def account_balance(workspace, account) -> int:
    """Balance of one account: debits minus credits, signed by its normal side.

    Two aggregates over the same account, never one ``Case`` pass over a kind.
    ``Case`` is first-match-wins, so a single pass over ``kind__in=...`` drops the
    second leg of any entry whose two accounts share a normal side (ASSET ->
    ADMIN_POOL contributes its full amount once and never its negative side), and
    an entry between two credit-normal accounts contributes nothing at all. The
    two legs have to be counted independently and only then signed.
    """
    debits = _side_total(workspace, "debit", account)
    credits = _side_total(workspace, "credit", account)
    # A debit-normal account (ASSET, ADMIN_POOL) grows on the debit side; a
    # credit-normal one (LIABILITY, REVENUE, GATEWAY_SETTLEMENT) grows on the credit side.
    sign = 1 if account.is_debit_normal else -1
    return sign * (debits - credits)


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


def test_workspace_factory_makes_distinct_workspaces(workspace_factory):
    """Two calls in one test must not collide on the unique owner columns."""
    first = workspace_factory(name="یک")
    second = workspace_factory(name="دو")
    assert first.pk != second.pk
    assert first.owner.pk != second.owner.pk
    assert first.owner.email != second.owner.email
    assert first.owner.username != second.owner.username


def test_wallet_is_one_per_workspace(workspace_factory):
    workspace = workspace_factory(name="تیم")
    Wallet.objects.create(workspace=workspace)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Wallet.objects.create(workspace=workspace)


def test_balance_is_the_sum_of_entries_not_a_column(workspace_factory):
    """No model carries a balance column; the balance is debits minus credits."""
    workspace = workspace_factory(name="تیم ۲")
    wallet = Wallet.objects.create(workspace=workspace)

    # The constraint is "no writable balance column anywhere", so check the
    # metadata rather than a single guessed attribute name. ``LedgerEntry`` is in
    # the loop too: a denormalised running total there (``balance_after_toman``)
    # is the obvious place to drift, and the bare ``"balance"`` substring would
    # miss it, so it is checked by name as well.
    for model in (Wallet, LedgerAccount, LedgerEntry):
        field_names = {field.name for field in model._meta.get_fields()}
        assert not any("balance" in name for name in field_names), f"{model.__name__} has a balance column"
    entry_field_names = {field.name for field in LedgerEntry._meta.get_fields()}
    assert not any("balance_after" in name for name in entry_field_names), "LedgerEntry has a balance_after column"
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
    # Both legs of that entry are debit-normal. A single first-match-wins
    # Case/When pass over the kind would score it as +120_000 for the wallet and
    # never subtract the pool's side, so the pool must come out at -120_000.
    assert account_balance(workspace, default) == 120_000
    assert account_balance(workspace, pool) == -120_000

    # A credit side posting against the same wallet must reduce its balance, not
    # add to it. Plain volume over the two entries would read 150_000 here.
    revenue = LedgerAccount.objects.create(code="plan_revenue", kind=LedgerAccountKind.REVENUE, title="درآمد اشتراک")
    LedgerEntry.objects.create(
        debit_account=revenue,
        credit_account=default,
        amount_toman=30_000,
        source=LedgerSource.PLAN_PURCHASE,
        workspace=workspace,
        idempotency_key="sum-2",
    )
    assert account_balance(workspace, default) == 90_000
    # Credit-normal polarity: a debit shrinks the account.
    assert account_balance(workspace, revenue) == -30_000

    # An entry between two credit-normal accounts contributes nothing to the
    # wallet but still moves both accounts by the full amount.
    liability = LedgerAccount.objects.create(code="sms_reserve", kind=LedgerAccountKind.LIABILITY, title="ذخیره پیامک")
    gateway = LedgerAccount.objects.create(
        code="gateway_settlement", kind=LedgerAccountKind.GATEWAY_SETTLEMENT, title="تسویه درگاه"
    )
    LedgerEntry.objects.create(
        debit_account=liability,
        credit_account=gateway,
        amount_toman=5_000,
        source=LedgerSource.SMS_CHARGE,
        workspace=workspace,
        idempotency_key="sum-3",
    )
    assert account_balance(workspace, liability) == -5_000
    assert account_balance(workspace, gateway) == 5_000
    assert account_balance(workspace, default) == 90_000


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


def test_wallet_account_codes_are_stable():
    # Local imports
    from plane.billing.services import money

    assert money.WalletAccountCode.wallet_default("abc-123") == "wallet:default:abc-123"
    assert money.WalletAccountCode.wallet_hold("abc-123") == "wallet:hold:abc-123"
    assert money.WalletAccountCode.gateway_receivable("zarinpal") == "gateway:zarinpal:receivable"


def test_post_entry_creates_one_balanced_row(workspace_factory):
    from plane.billing.services import money

    workspace = workspace_factory(name="تیم ۳")
    debit = money.get_or_create_account("d3", LedgerAccountKind.ASSET, "بدهکار")
    credit = money.get_or_create_account("c3", LedgerAccountKind.ADMIN_POOL, "بستانه")

    entry = money.post_entry(
        debit=debit,
        credit=credit,
        amount_toman=7_500,
        source=LedgerSource.ADMIN_GRANT,
        workspace=workspace,
        idempotency_key="post-1",
    )

    assert entry.amount_toman == 7_500
    assert entry.debit_account_id == debit.pk
    assert entry.credit_account_id == credit.pk


def test_post_entry_is_idempotent_and_returns_the_first_row():
    from plane.billing.services import money

    debit = money.get_or_create_account("d4", LedgerAccountKind.ASSET, "بدهکار")
    credit = money.get_or_create_account("c4", LedgerAccountKind.ADMIN_POOL, "بستانه")

    first = money.post_entry(
        debit=debit, credit=credit, amount_toman=1000, source=LedgerSource.ADMIN_GRANT, idempotency_key="same"
    )
    second = money.post_entry(
        debit=debit, credit=credit, amount_toman=1000, source=LedgerSource.ADMIN_GRANT, idempotency_key="same"
    )

    assert first.pk == second.pk
    assert LedgerEntry.objects.filter(idempotency_key="same").count() == 1
    # the replay must not double the balance
    assert money.account_balance(debit) == 1000


def test_wallet_balance_counts_debits_minus_credits(workspace_factory):
    from plane.billing.services import money

    workspace = workspace_factory(name="تیم ۴")
    default = money.get_or_create_account(
        money.WalletAccountCode.wallet_default(workspace.pk), LedgerAccountKind.ASSET, "کیف پول قابل خرج", workspace
    )
    # The hold is a RESTRICTED ASSET, not a liability: the workspace still owns
    # the money, it just cannot spend it. As a liability it is credit-normal, so
    # debiting it to move money in would read -20_000 and clamp to 0.
    hold = money.get_or_create_account(
        money.WalletAccountCode.wallet_hold(workspace.pk), LedgerAccountKind.ASSET, "کیف پول قفل", workspace
    )
    pool = money.get_or_create_account("pool-1", LedgerAccountKind.ADMIN_POOL, "استخر اعتبار")

    money.post_entry(
        debit=default,
        credit=pool,
        amount_toman=50_000,
        source=LedgerSource.ADMIN_GRANT,
        workspace=workspace,
        idempotency_key="b1",
    )
    # Holding money moves it OUT of the spendable account, so the hold is the
    # debit side and the wallet the credit side. Posting this the other way
    # round (debit=default) would GROW the spendable balance to 70_000.
    money.post_entry(
        debit=hold,
        credit=default,
        amount_toman=20_000,
        source=LedgerSource.REFUND,
        workspace=workspace,
        idempotency_key="b2",
    )

    assert money.wallet_balance(workspace) == 30_000
    # the hold is tracked separately and is not spendable
    assert money.wallet_hold_balance(workspace) == 20_000


def test_round_to_toman_rounds_to_the_nearest_thousand():
    from plane.billing.services import money

    assert money.round_to_toman(Decimal("1234.4")) == 1000
    # The brief asserted 2000 here, but 1234.5 is 234.5 from 1000 and 765.5
    # from 2000, so the nearest thousand is 1000. HALF_UP decides the tie, not
    # the magnitude of the distance, and there is no tie to decide at all.
    assert money.round_to_toman(Decimal("1234.5")) == 1000
    # An exact midpoint is the case HALF_UP exists for: 1500 is 500 from both.
    assert money.round_to_toman(Decimal("1500")) == 2000
    assert money.round_to_toman(Decimal("999")) == 1000


def test_get_or_create_account_revives_a_soft_deleted_row():
    """A deleted account keeps its unique code, so the lookup must revive it."""
    from plane.billing.services import money

    first = money.get_or_create_account("revive-me", LedgerAccountKind.ASSET, "کیف پول")
    # ``delete()`` would stamp the same field but also fire a Celery task, which
    # needs a broker the test stack does not run. Stamp it directly instead.
    first.deleted_at = django_timezone.now()
    first.save(update_fields=["deleted_at"])
    # SoftDeleteModel only stamps deleted_at, so the row still occupies the code.
    assert LedgerAccount.all_objects.filter(code="revive-me", deleted_at__isnull=False).count() == 1

    revived = money.get_or_create_account("revive-me", LedgerAccountKind.ASSET, "کیف پول")

    assert revived.pk == first.pk
    assert revived.deleted_at is None
    assert LedgerAccount.all_objects.filter(code="revive-me").count() == 1
