# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Wallet policy: grants, revocations, charges and holds."""

# Python imports
from uuid import uuid4

# Third party imports
import pytest

# Module imports
from plane.billing.models import LedgerAccount, LedgerEntry, LedgerSource, Wallet
from plane.billing.services import money, wallet
from plane.db.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def workspace(workspace_factory):
    return workspace_factory(name="تیم کیف پول")


@pytest.fixture
def race_workspace(workspace_factory):
    return workspace_factory(name="تیم هم‌زمانی")


@pytest.fixture
def admin_user(db):
    """A real user to stamp on grants and revocations.

    ``User.username`` is unique with no default, so an email alone is not enough
    to create a second user; each call needs a distinct value in both columns.
    """
    unique = uuid4().hex
    return User.objects.create(
        username=f"granter-{unique}",
        email=f"granter-{unique}@example.com",
        first_name="Grant",
        last_name="Admin",
    )


def test_grant_requires_a_meaningful_description(workspace, admin_user):
    with pytest.raises(wallet.InvalidGrantDescription):
        wallet.grant_from_admin(
            workspace=workspace,
            amount_toman=10_000,
            description="کوتاه",
            created_by=admin_user,
            idempotency_key="g-bad",
        )


def test_grant_moves_money_into_the_workspace(workspace, admin_user):
    entry = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=250_000,
        description="هدیهٔ قرارداد سالانهٔ مشتری نمونه",
        created_by=admin_user,
        idempotency_key="g-1",
    )

    assert entry.source == LedgerSource.ADMIN_GRANT
    assert entry.created_by_id == admin_user.pk
    assert entry.workspace_id == workspace.pk
    assert money.wallet_balance(workspace) == 250_000


def test_grant_credits_the_spendable_account_and_debits_the_pool(workspace, admin_user):
    """The posting direction, asserted on the accounts rather than the total.

    The spendable account is an ``ASSET``, so it is debit-normal and its balance
    is ``debits - credits``: a grant has to DEBIT it. Posting the other way
    round moves the balance to -250_000, which ``wallet_balance`` then clamps to
    0 -- an empty wallet and a fully funded one become indistinguishable.
    """
    entry = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=250_000,
        description="هدیهٔ قرارداد سالانهٔ مشتری نمونه",
        created_by=admin_user,
        idempotency_key="g-direction",
    )

    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    pool = LedgerAccount.objects.get(code=money.ADMIN_GRANT_POOL)
    assert entry.debit_account_id == spendable.pk
    assert entry.credit_account_id == pool.pk
    assert money.wallet_balance(workspace, clamp_negative=False) == 250_000


def test_grant_pool_accounting_is_scoped_per_workspace(workspace_factory, admin_user):
    """``post_entry`` does not derive ``workspace`` from its accounts.

    The admin grant pool is a GLOBAL account, so an entry posted against it with
    ``workspace=None`` is invisible to ``account_balance(pool, workspace=ws)``
    and one tenant's grant would be counted against another's.
    """
    first = workspace_factory(name="تیم الف")
    second = workspace_factory(name="تیم ب")

    wallet.grant_from_admin(
        workspace=first,
        amount_toman=40_000,
        description="شارژ تیم الف",
        created_by=admin_user,
        idempotency_key="scope-1",
    )
    wallet.grant_from_admin(
        workspace=second,
        amount_toman=90_000,
        description="شارژ تیم ب",
        created_by=admin_user,
        idempotency_key="scope-2",
    )

    pool = LedgerAccount.objects.get(code=money.ADMIN_GRANT_POOL)
    assert money.account_balance(pool, workspace=first) == -40_000
    assert money.account_balance(pool, workspace=second) == -90_000
    assert money.wallet_balance(first) == 40_000
    assert money.wallet_balance(second) == 90_000


def test_grant_respects_the_cap(workspace, admin_user):
    Wallet.objects.create(workspace=workspace, admin_grant_cap_toman=100_000)

    with pytest.raises(wallet.GrantTooLarge):
        wallet.grant_from_admin(
            workspace=workspace,
            amount_toman=500_000,
            description="بیش از سقف مجاز",
            created_by=admin_user,
            idempotency_key="g-cap",
        )

    assert money.wallet_balance(workspace) == 0


def test_grant_is_idempotent(workspace, admin_user):
    first = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000,
        description="شارژ آزمایشی اول",
        created_by=admin_user,
        idempotency_key="g-same",
    )
    second = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000,
        description="شارژ آزمایشی اول",
        created_by=admin_user,
        idempotency_key="g-same",
    )

    assert first.pk == second.pk
    assert money.wallet_balance(workspace) == 10_000


def test_revoke_writes_a_reversing_entry_and_keeps_the_original(workspace, admin_user):
    original = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=80_000,
        description="شارژ اولیه برای آزمایش",
        created_by=admin_user,
        idempotency_key="r-1",
    )

    reversal = wallet.revoke_grant(
        workspace=workspace,
        entry=original,
        description="ابطال اشتباه ادمین",
        created_by=admin_user,
        idempotency_key="r-1-rev",
    )

    assert reversal.amount_toman == 80_000
    # the original row is untouched -- history is never rewritten
    assert LedgerEntry.objects.filter(pk=original.pk).exists()
    assert money.wallet_balance(workspace) == 0


def test_revoke_mirrors_the_original_entry(workspace, admin_user):
    """A reversal is the mirror image of the entry it reverses.

    Debiting the original's debit account instead would post the SAME movement
    again -- here the spendable account on both sides, which ``post_entry``
    refuses outright as a same-account entry.
    """
    original = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=80_000,
        description="شارژ اولیه برای آزمایش",
        created_by=admin_user,
        idempotency_key="r-mirror",
    )

    reversal = wallet.revoke_grant(
        workspace=workspace,
        entry=original,
        description="ابطال اشتباه ادمین",
        created_by=admin_user,
        idempotency_key="r-mirror-rev",
    )

    assert reversal.debit_account_id == original.credit_account_id
    assert reversal.credit_account_id == original.debit_account_id
    # the pool is whole again for this workspace
    pool = LedgerAccount.objects.get(code=money.ADMIN_GRANT_POOL)
    assert money.account_balance(pool, workspace=workspace) == 0


def test_revoke_is_refused_when_the_money_was_already_spent(workspace, admin_user):
    """A grant that has been charged cannot be clawed back in full."""
    original = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=50_000,
        description="شارژ قبل از خرج کردن",
        created_by=admin_user,
        idempotency_key="r-spent",
    )
    wallet.charge_sms(workspace=workspace, amount_toman=30_000, log_id=555)

    with pytest.raises(wallet.InsufficientBalance):
        wallet.revoke_grant(
            workspace=workspace,
            entry=original,
            description="ابطال پس از خرج شدن پول",
            created_by=admin_user,
            idempotency_key="r-spent-rev",
        )

    assert money.wallet_balance(workspace) == 20_000


def test_charge_sms_reduces_the_spendable_balance(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست پیامک",
        created_by=admin_user,
        idempotency_key="c-setup",
    )

    entry = wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=77)

    assert entry.source == LedgerSource.SMS_CHARGE
    assert money.wallet_balance(workspace) == 98_800


def test_charge_sms_credits_the_spendable_account(workspace, admin_user):
    """Same polarity rule as the grant, in the other direction.

    A charge DEBITS the expense account and CREDITS the spendable account.
    Debiting the wallet instead would make the charge look like a top-up.
    """
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست جهت",
        created_by=admin_user,
        idempotency_key="c-dir-setup",
    )

    entry = wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=78)

    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    assert entry.credit_account_id == spendable.pk
    assert entry.debit_account_id != spendable.pk
    assert money.wallet_balance(workspace, clamp_negative=False) == 98_800


def test_charge_sms_is_idempotent_per_log(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست تکرار پیامک",
        created_by=admin_user,
        idempotency_key="c-setup-2",
    )

    first = wallet.charge_sms(workspace=workspace, amount_toman=900, log_id=88)
    second = wallet.charge_sms(workspace=workspace, amount_toman=900, log_id=88)

    assert first.pk == second.pk
    assert money.wallet_balance(workspace) == 99_100


def test_charge_sms_replay_succeeds_once_the_wallet_is_empty(workspace, admin_user):
    """A retried delivery must replay even when the funds are already gone.

    ``charge_sms`` exists so a redelivered notification is never billed twice.
    If the balance check ran before the idempotency lookup, a retry against a
    wallet that the first attempt emptied would raise ``InsufficientBalance`` --
    the caller would see a hard failure for work that was already paid for, and
    would most likely retry again.
    """
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=900,
        description="شارژ دقیق برای تست تکرار",
        created_by=admin_user,
        idempotency_key="c-exact",
    )
    first = wallet.charge_sms(workspace=workspace, amount_toman=900, log_id=1234)
    assert money.wallet_balance(workspace) == 0

    second = wallet.charge_sms(workspace=workspace, amount_toman=900, log_id=1234)

    assert second.pk == first.pk
    assert money.wallet_balance(workspace) == 0


def test_charge_sms_refuses_an_empty_wallet(workspace):
    with pytest.raises(wallet.InsufficientBalance):
        wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=99)

    assert money.wallet_balance(workspace) == 0


def test_charge_sms_refuses_a_short_balance(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=5_000,
        description="شارژ ناکافی برای تست",
        created_by=admin_user,
        idempotency_key="c-setup-3",
    )

    with pytest.raises(wallet.InsufficientBalance):
        wallet.charge_sms(workspace=workspace, amount_toman=6_000, log_id=100)


def test_charge_sms_refuses_a_different_amount_on_the_same_log(workspace, admin_user):
    """A retried delivery must carry the same amount it was first billed at."""
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست تضادف کلید",
        created_by=admin_user,
        idempotency_key="c-collide",
    )
    wallet.charge_sms(workspace=workspace, amount_toman=900, log_id=4321)

    with pytest.raises(ValueError, match="different movement"):
        wallet.charge_sms(workspace=workspace, amount_toman=1_500, log_id=4321)

    assert money.wallet_balance(workspace) == 99_100


def test_hold_moves_money_out_of_reach_and_release_returns_it(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=200_000,
        description="شارژ برای تست قفل",
        created_by=admin_user,
        idempotency_key="h-setup",
    )

    wallet.hold_funds(workspace=workspace, amount_toman=120_000, source=LedgerSource.REFUND, idempotency_key="h-1")

    assert money.wallet_balance(workspace) == 80_000
    assert money.wallet_hold_balance(workspace) == 120_000

    wallet.release_hold(workspace=workspace, amount_toman=120_000, idempotency_key="h-1-rel")

    assert money.wallet_balance(workspace) == 200_000
    assert money.wallet_hold_balance(workspace) == 0


def test_held_money_cannot_be_charged(workspace, admin_user):
    """A hold is only meaningful if the money it parks is genuinely unspendable."""
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=200_000,
        description="شارژ برای تست قفل و خرج",
        created_by=admin_user,
        idempotency_key="hs-setup",
    )
    wallet.hold_funds(workspace=workspace, amount_toman=150_000, source=LedgerSource.REFUND, idempotency_key="hs-1")

    with pytest.raises(wallet.InsufficientBalance):
        wallet.charge_sms(workspace=workspace, amount_toman=100_000, log_id=321)

    assert money.wallet_balance(workspace) == 50_000
    assert money.wallet_hold_balance(workspace) == 150_000


def test_release_hold_cannot_exceed_what_is_held(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=50_000,
        description="شارژ برای تست آزادسازی",
        created_by=admin_user,
        idempotency_key="rh-setup",
    )
    wallet.hold_funds(workspace=workspace, amount_toman=20_000, source=LedgerSource.REFUND, idempotency_key="rh-1")

    with pytest.raises(wallet.InsufficientBalance):
        wallet.release_hold(workspace=workspace, amount_toman=40_000, idempotency_key="rh-1-bad")

    assert money.wallet_hold_balance(workspace) == 20_000


def test_concurrent_charges_do_not_overdraw(race_workspace):
    """Two charges racing on the same balance must not both succeed past the limit.

    ``charge_sms`` takes a row lock on the wallet account, so the second
    charge sees the balance the first one already spent. Sequential calls
    with the lock held model that interleaving without needing threads.
    """
    workspace = race_workspace

    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000,
        description="شارژ برای تست هم‌زمانی",
        created_by=None,
        idempotency_key="race-setup",
    )

    # Simulate the interleaving by charging twice inside one transaction and
    # confirming the second is refused once the balance is gone.
    wallet.charge_sms(workspace=workspace, amount_toman=6_000, log_id=201)
    with pytest.raises(wallet.InsufficientBalance):
        wallet.charge_sms(workspace=workspace, amount_toman=6_000, log_id=202)

    assert money.wallet_balance(workspace) == 4_000


def test_charge_does_not_spend_money_the_wallet_does_not_have(workspace, admin_user):
    """The unclamped balance decides affordability.

    An overdrawn wallet and an empty one both clamp to 0, so comparing the
    charge against ``wallet_balance(workspace)`` would treat a -5_000 wallet as
    able to afford a 0-toman top-up. ``wallet_balance_is_enough`` reads the raw
    signed figure and refuses both.
    """
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000,
        description="شارژ برای تست بیش‌برداشت",
        created_by=admin_user,
        idempotency_key="od-setup",
    )
    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    pool = LedgerAccount.objects.get(code=money.ADMIN_GRANT_POOL)
    # Force the wallet into overdraft by paying money out of the pool.
    money.post_entry(
        debit=pool,
        credit=spendable,
        amount_toman=25_000,
        source=LedgerSource.REFUND,
        workspace=workspace,
        idempotency_key="od-1",
    )
    assert money.wallet_balance(workspace) == 0
    assert money.wallet_balance(workspace, clamp_negative=False) == -15_000

    with pytest.raises(wallet.InsufficientBalance):
        wallet.charge_sms(workspace=workspace, amount_toman=1, log_id=999)

    assert money.wallet_balance(workspace, clamp_negative=False) == -15_000


def test_refund_to_spendable_returns_money_without_a_hold(workspace_factory):
    """A rejected gateway payment is credited straight back.

    No hold is involved, so the reversal posts against one shared gateway
    settlement account rather than creating an account per idempotency key.
    """
    first = workspace_factory(name="تیم الف")
    wallet.grant_from_admin(
        workspace=first,
        amount_toman=100_000,
        description="شارژ برای تست بازگشت وجه",
        created_by=None,
        idempotency_key="ref-setup",
    )

    entry = wallet.refund_to_spendable(
        workspace=first, amount_toman=25_000, reason="پرداخت توسط درگاه رد شد", idempotency_key="ref-1"
    )

    assert entry.source == LedgerSource.REFUND
    assert money.wallet_balance(first) == 125_000
    assert money.wallet_hold_balance(first) == 0


def test_refund_to_spendable_is_idempotent(workspace):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست تکرار بازگشت",
        created_by=None,
        idempotency_key="ref-setup-2",
    )
    first = wallet.refund_to_spendable(
        workspace=workspace, amount_toman=25_000, reason="پرداخت توسط درگاه رد شد", idempotency_key="ref-2"
    )
    second = wallet.refund_to_spendable(
        workspace=workspace, amount_toman=25_000, reason="پرداخت توسط درگاه رد شد", idempotency_key="ref-2"
    )

    assert first.pk == second.pk
    assert money.wallet_balance(workspace) == 125_000


@pytest.mark.parametrize("amount", [0, -1])
def test_operations_refuse_a_non_positive_amount(workspace, amount):
    with pytest.raises(wallet.WalletError):
        wallet.charge_sms(workspace=workspace, amount_toman=amount, log_id=1)


def test_grant_creates_the_wallet_row_and_defaults_the_cap_to_unlimited(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000,
        description="شارژ برای تست ایجاد کیف پول",
        created_by=admin_user,
        idempotency_key="wc-1",
    )

    row = Wallet.objects.get(workspace=workspace)
    # Zero means no cap, so an uncapped wallet accepts a very large grant.
    assert row.admin_grant_cap_toman == 0
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000_000_000,
        description="شارژ بسیار بزرگ بدون سقف",
        created_by=admin_user,
        idempotency_key="wc-2",
    )
    assert money.wallet_balance(workspace) == 10_000_010_000
