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
    assert entry.workspace_id == workspace.pk
    assert money.wallet_balance(workspace) == 250_000
    # Refetched rather than read off the returned instance: ``post_entry``
    # hands back the object it just saved, and ``BaseModel.save`` mutates that
    # same object, so an assertion on it cannot tell "the row carries the author"
    # apart from "the attribute is set in memory".
    assert LedgerEntry.objects.get(pk=entry.pk).created_by_id == admin_user.pk


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

    wallet.hold_funds(workspace=workspace, amount_toman=120_000, idempotency_key="h-1")

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
    wallet.hold_funds(workspace=workspace, amount_toman=150_000, idempotency_key="hs-1")

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
    wallet.hold_funds(workspace=workspace, amount_toman=20_000, idempotency_key="rh-1")

    with pytest.raises(wallet.InsufficientBalance):
        wallet.release_hold(workspace=workspace, amount_toman=40_000, idempotency_key="rh-1-bad")

    assert money.wallet_hold_balance(workspace) == 20_000


def test_second_charge_is_refused_once_the_balance_is_gone(race_workspace):
    """A charge the wallet cannot fund is refused, so two cannot both succeed.

    What this actually pins is the balance CHECK, not ``select_for_update``:
    each ``charge_sms`` opens and commits its own ``atomic()``, so these two
    calls do not overlap at all. It proves the second call is refused once the
    first has committed, which is the outcome the row lock exists to produce --
    it does not prove the lock serialises two real threads. See the report.
    """
    workspace = race_workspace

    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000,
        description="شارژ برای تست هم‌زمانی",
        created_by=None,
        idempotency_key="race-setup",
    )

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
        workspace=first,
        amount_toman=25_000,
        reason="پرداخت توسط درگاه رد شد",
        reference="TXN-7788",
        idempotency_key="ref-1",
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
        workspace=workspace,
        amount_toman=25_000,
        reason="پرداخت توسط درگاه رد شد",
        reference="TXN-7789",
        idempotency_key="ref-2",
    )
    second = wallet.refund_to_spendable(
        workspace=workspace,
        amount_toman=25_000,
        reason="پرداخت توسط درگاه رد شد",
        reference="TXN-7789",
        idempotency_key="ref-2",
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


# --- retry safety of the admin actions (C1) ----------------------------------


def test_revoke_replay_succeeds_once_the_wallet_is_empty(workspace, admin_user):
    """The revoke counterpart of ``test_charge_sms_replay_succeeds_once_the_wallet_is_empty``.

    A completed reversal has, by construction, taken the whole grant back out
    of the wallet. Checking affordability before the idempotency lookup made the
    second identical call raise ``InsufficientBalance`` -- the admin UI showed
    "wallet insufficient" for work already done, and the admin would retry
    again.
    """
    original = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=80_000,
        description="شارژ برای تست تکرار ابطال",
        created_by=admin_user,
        idempotency_key="rr-1",
    )

    first = wallet.revoke_grant(
        workspace=workspace,
        entry=original,
        description="ابطال اشتباه ادمین",
        created_by=admin_user,
        idempotency_key="rr-1-rev",
    )
    assert money.wallet_balance(workspace) == 0

    second = wallet.revoke_grant(
        workspace=workspace,
        entry=original,
        description="ابطال اشتباه ادمین",
        created_by=admin_user,
        idempotency_key="rr-1-rev",
    )

    assert second.pk == first.pk
    assert money.wallet_balance(workspace) == 0
    assert LedgerEntry.objects.filter(source=LedgerSource.REFUND, workspace=workspace).count() == 1


def test_grant_replay_succeeds_even_after_the_cap_is_lowered(workspace, admin_user):
    """An admin lowering the cap between two identical calls must not see ``GrantTooLarge``."""
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=200_000,
        description="شارژ برای تست سقف و تکرار",
        created_by=admin_user,
        idempotency_key="g-cap-replay",
    )
    row = Wallet.objects.get(workspace=workspace)
    row.admin_grant_cap_toman = 50_000
    row.save(update_fields=["admin_grant_cap_toman"])

    replay = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=200_000,
        description="شارژ برای تست سقف و تکرار",
        created_by=admin_user,
        idempotency_key="g-cap-replay",
    )

    assert replay.amount_toman == 200_000
    assert money.wallet_balance(workspace) == 200_000


def test_grant_cap_still_refuses_a_new_grant_that_is_over_it(workspace, admin_user):
    """The cap check must survive the reordering, not be swallowed by it."""
    Wallet.objects.create(workspace=workspace, admin_grant_cap_toman=50_000)

    with pytest.raises(wallet.GrantTooLarge):
        wallet.grant_from_admin(
            workspace=workspace,
            amount_toman=200_000,
            description="شارژ جدید بالای سقف",
            created_by=admin_user,
            idempotency_key="g-cap-new",
        )


# --- revoke only reverses grants (I3) ----------------------------------------


def test_revoke_refuses_an_entry_belonging_to_another_workspace(workspace, workspace_factory, admin_user):
    """The pk comes from the caller; a cross-tenant pk must not move another wallet."""
    other = workspace_factory(name="تیم دیگر")
    theirs = wallet.grant_from_admin(
        workspace=other,
        amount_toman=80_000,
        description="شارژ فضای کاری دیگر",
        created_by=admin_user,
        idempotency_key="xw-1",
    )

    with pytest.raises(wallet.WalletError):
        wallet.revoke_grant(
            workspace=workspace,
            entry=theirs,
            description="ابطال از فضای کاری اشتباه",
            created_by=admin_user,
            idempotency_key="xw-2",
        )

    assert money.wallet_balance(other) == 80_000


def test_revoke_refuses_an_entry_that_is_not_a_grant(workspace, admin_user):
    """Handed an SMS charge, ``revoke_grant`` used to post a silent refund."""
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست ابطال غیرشارژ",
        created_by=admin_user,
        idempotency_key="ng-setup",
    )
    charge = wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=4711)

    with pytest.raises(wallet.NotAGrantEntry):
        wallet.revoke_grant(
            workspace=workspace,
            entry=charge,
            description="ابطال یک هزینهٔ پیامک",
            created_by=admin_user,
            idempotency_key="ng-1",
        )

    # the charge stands and the wallet is unchanged
    assert money.wallet_balance(workspace) == 98_800
    assert LedgerEntry.objects.filter(idempotency_key="ng-1").count() == 0


def test_revoke_refuses_a_grant_that_was_already_reversed(workspace, admin_user):
    """Two keys, one grant, one reversal -- not two."""
    original = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=80_000,
        description="شارژ برای تست ابطال تکراری",
        created_by=admin_user,
        idempotency_key="ar-1",
    )
    wallet.revoke_grant(
        workspace=workspace,
        entry=original,
        description="ابطال بار اول",
        created_by=admin_user,
        idempotency_key="ar-1-a",
    )

    with pytest.raises(wallet.GrantAlreadyReversed):
        wallet.revoke_grant(
            workspace=workspace,
            entry=original,
            description="ابطال بار دوم با کلید دیگر",
            created_by=admin_user,
            idempotency_key="ar-1-b",
        )

    assert money.wallet_balance(workspace) == 0
    assert LedgerEntry.objects.filter(source=LedgerSource.REFUND, workspace=workspace).count() == 1


# --- traceability of an SMS charge (I4, I6) ----------------------------------


def test_sms_charge_entry_records_the_log_id_and_the_author(workspace, admin_user):
    """``log_id`` is the index, not the story: the entry has to carry the reference too."""
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست ردیابی پیامک",
        created_by=admin_user,
        idempotency_key="tr-setup",
    )

    entry = wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=987654, created_by=admin_user)

    stored = LedgerEntry.objects.get(pk=entry.pk)
    assert "987654" in stored.description
    assert stored.created_by_id == admin_user.pk


def test_sms_charge_description_is_extended_never_replaced(workspace, admin_user):
    """An override adds to the canonical label; it never hides the log id.

    A caller overriding ``description`` AND ``idempotency_key`` used to leave the
    entry with no trace of which notification log was charged -- the description
    was the only place that reference existed, and the key is the index, not the
    story.
    """
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست توضیح پیامک",
        created_by=admin_user,
        idempotency_key="tr-setup-2",
    )

    entry = wallet.charge_sms(
        workspace=workspace,
        amount_toman=1_200,
        log_id=987655,
        description="اعلان پایان آزمون",
        idempotency_key="sms-override-key",
    )

    stored = LedgerEntry.objects.get(pk=entry.pk)
    assert "987655" in stored.description
    assert "اعلان پایان آزمون" in stored.description


def test_sms_charge_default_description_is_the_log_id(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست توضیح پیش‌فرض",
        created_by=admin_user,
        idempotency_key="tr-setup-3",
    )

    entry = wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=987656)

    assert LedgerEntry.objects.get(pk=entry.pk).description == "پیامک 987656"


@pytest.mark.parametrize("bad_log_id", [None, "", "   "])
def test_charge_sms_refuses_a_missing_log_id(workspace, bad_log_id):
    """A ``None`` log id would collapse every SMS onto the key ``sms:None:charge``."""
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست شناسهٔ لاگ",
        created_by=None,
        idempotency_key="lg-setup",
    )

    with pytest.raises(wallet.InvalidChargeReference):
        wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=bad_log_id)

    assert money.wallet_balance(workspace) == 100_000


# --- hold / release idempotency (C2) -----------------------------------------


def test_hold_funds_is_idempotent(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=200_000,
        description="شارژ برای تست تکرار قفل",
        created_by=admin_user,
        idempotency_key="hi-setup",
    )

    first = wallet.hold_funds(workspace=workspace, amount_toman=120_000, idempotency_key="hi-1")
    second = wallet.hold_funds(workspace=workspace, amount_toman=120_000, idempotency_key="hi-1")

    assert first.pk == second.pk
    assert money.wallet_balance(workspace) == 80_000
    assert money.wallet_hold_balance(workspace) == 120_000


def test_release_hold_is_idempotent(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=200_000,
        description="شارژ برای تست تکرار آزادسازی",
        created_by=admin_user,
        idempotency_key="ri-setup",
    )
    wallet.hold_funds(workspace=workspace, amount_toman=120_000, idempotency_key="ri-hold")

    first = wallet.release_hold(workspace=workspace, amount_toman=120_000, idempotency_key="ri-rel")
    assert money.wallet_balance(workspace) == 200_000
    assert money.wallet_hold_balance(workspace) == 0

    # the second identical call must replay, not refuse on a zero hold balance
    second = wallet.release_hold(workspace=workspace, amount_toman=120_000, idempotency_key="ri-rel")

    assert second.pk == first.pk
    assert money.wallet_balance(workspace) == 200_000
    assert money.wallet_hold_balance(workspace) == 0


# --- refund does not credit a settlement account (I5) ------------------------


def test_refund_does_not_move_the_gateway_account_more_positive(workspace):
    """A credit-normal contra account would be driven further from zero by a refund.

    ``GATEWAY_SETTLEMENT`` is credit-normal, so crediting it increases its
    balance and no later genuine settlement could bring it back. The contra side
    of an entry for money that never moved has to be a funding source.
    """
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست جهت حساب برگشت",
        created_by=None,
        idempotency_key="rf-setup",
    )
    contra = money.get_or_create_account(
        wallet.GATEWAY_REVERSAL_ACCOUNT_CODE, wallet.GATEWAY_REVERSAL_ACCOUNT_KIND, "برگشت درگاه"
    )
    before = money.account_balance(contra, workspace=workspace)

    wallet.refund_to_spendable(
        workspace=workspace,
        amount_toman=25_000,
        reason="پرداخت توسط درگاه رد شد",
        reference="TXN-7790",
        idempotency_key="rf-1",
    )

    after = money.account_balance(contra, workspace=workspace)
    assert after <= before
    # and the money really did land in the wallet
    assert money.wallet_balance(workspace) == 125_000


def test_refund_records_its_author(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست نویسندهٔ بازگشت",
        created_by=admin_user,
        idempotency_key="ra-setup",
    )

    entry = wallet.refund_to_spendable(
        workspace=workspace,
        amount_toman=25_000,
        reason="پرداخت توسط درگاه رد شد",
        reference="TXN-7791",
        idempotency_key="ra-1",
        created_by=admin_user,
    )

    assert LedgerEntry.objects.get(pk=entry.pk).created_by_id == admin_user.pk


# --- input validation edges --------------------------------------------------


@pytest.mark.parametrize("length", [9, 10])
def test_grant_description_minimum_length_boundary(workspace, admin_user, length):
    """``MIN_GRANT_DESCRIPTION_LENGTH`` is an exact boundary, not a fuzzy rule.

    The literals 9 and 10 are pinned, NOT read off the constant. Driving the
    expectation from ``wallet.MIN_GRANT_DESCRIPTION_LENGTH`` meant that if the
    constant drifted down to 5, ``length=9`` would take the accept branch and
    still pass -- the test would have followed the drift instead of catching it.
    A separate assertion below pins the constant to the documented 10.
    """
    assert wallet.MIN_GRANT_DESCRIPTION_LENGTH == 10
    description = "ا" * length

    if length < 10:
        with pytest.raises(wallet.InvalidGrantDescription):
            wallet.grant_from_admin(
                workspace=workspace,
                amount_toman=10_000,
                description=description,
                created_by=admin_user,
                idempotency_key="bd-short",
            )
    else:
        entry = wallet.grant_from_admin(
            workspace=workspace,
            amount_toman=10_000,
            description=description,
            created_by=admin_user,
            idempotency_key="bd-exact",
        )
        assert entry.description == description


@pytest.mark.parametrize("bad_amount", [True, False])
def test_amount_validation_rejects_a_bool(workspace, bad_amount):
    """``isinstance(True, int)`` is ``True``, so a bare type check would let a 1-toman charge through."""
    with pytest.raises(wallet.InvalidAmount):
        wallet.charge_sms(workspace=workspace, amount_toman=bad_amount, log_id=7)

    assert money.wallet_balance(workspace) == 0


def test_amount_validation_raises_its_own_subclass_not_the_base(workspace):
    """A caller must be able to tell a malformed amount from a policy refusal."""
    with pytest.raises(wallet.InvalidAmount) as excinfo:
        wallet.hold_funds(workspace=workspace, amount_toman="1000", idempotency_key="av-1")
    assert isinstance(excinfo.value, wallet.WalletError)


# --- C1: a reversal is identified by the FK, not by coinciding legs ------------


def test_two_same_amount_grants_to_one_workspace_can_both_be_revoked(workspace, admin_user):
    """The defect fix round 1 introduced.

    Grants are all ``debit=spendable, credit=pool``, so two grants of the SAME
    amount to the SAME workspace have byte-identical legs. With the reversal
    identified by a mirrored-legs query, revoking the FIRST grant created a
    mirror that also matched the SECOND, and the second revoke then raised
    ``GrantAlreadyReversed`` for a grant nobody had touched -- with no
    in-product way to clear it. Round-number grants to one workspace are an
    ordinary case.

    ``LedgerEntry.reversal_of`` makes the question exact: "does THIS row have a
    reversal pointing at it?"
    """
    first = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=80_000,
        description="شارژ مرحلهٔ اول با همان مبلغ",
        created_by=admin_user,
        idempotency_key="same-1",
    )
    second = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=80_000,
        description="شارژ مرحلهٔ دوم با همان مبلغ",
        created_by=admin_user,
        idempotency_key="same-2",
    )
    assert first.debit_account_id == second.debit_account_id
    assert first.credit_account_id == second.credit_account_id
    assert first.amount_toman == second.amount_toman
    assert money.wallet_balance(workspace) == 160_000

    reversal_of_first = wallet.revoke_grant(
        workspace=workspace,
        entry=first,
        description="ابطال مرحلهٔ اول",
        created_by=admin_user,
        idempotency_key="same-1-rev",
    )
    reversal_of_second = wallet.revoke_grant(
        workspace=workspace,
        entry=second,
        description="ابطال مرحلهٔ دوم",
        created_by=admin_user,
        idempotency_key="same-2-rev",
    )

    # Each reversal names the grant it actually undid -- not just "the other
    # same-amount grant on this workspace".
    assert LedgerEntry.objects.get(pk=reversal_of_first.pk).reversal_of_id == first.pk
    assert LedgerEntry.objects.get(pk=reversal_of_second.pk).reversal_of_id == second.pk
    assert money.wallet_balance(workspace) == 0


def test_revoking_the_first_of_three_same_amount_grants_still_refuses_the_second_revoke(workspace, admin_user):
    """The FK makes the guard exact in BOTH directions.

    Fixing "the second grant of the same amount is refused" by loosening the
    check would have reintroduced "the same grant reversed twice". One reversal
    per grant, no matter how many identical siblings exist.
    """
    grants = [
        wallet.grant_from_admin(
            workspace=workspace,
            amount_toman=50_000,
            description=f"شارژ نوبت {index} با همان مبلغ",
            created_by=admin_user,
            idempotency_key=f"triple-{index}",
        )
        for index in range(3)
    ]

    for index, grant in enumerate(grants):
        wallet.revoke_grant(
            workspace=workspace,
            entry=grant,
            description=f"ابطال نوبت {index}",
            created_by=admin_user,
            idempotency_key=f"triple-{index}-rev",
        )

    # and each is now refuseable once more, under a third key
    for index, grant in enumerate(grants):
        with pytest.raises(wallet.GrantAlreadyReversed):
            wallet.revoke_grant(
                workspace=workspace,
                entry=grant,
                description=f"ابطال دوبارهٔ نوبت {index}",
                created_by=admin_user,
                idempotency_key=f"triple-{index}-rev-again",
            )

    assert money.wallet_balance(workspace) == 0
    assert LedgerEntry.objects.filter(reversal_of__isnull=False).count() == 3


def test_an_unreversed_grant_has_no_reversal_pointer(workspace, admin_user):
    grant = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000,
        description="شارژ ساده برای تست اشاره‌گر",
        created_by=admin_user,
        idempotency_key="ptr-1",
    )
    assert LedgerEntry.objects.get(pk=grant.pk).reversal_of_id is None


# --- C2: a replay may never cross a tenant boundary ----------------------------


def test_replaying_another_workspaces_revoke_is_refused(workspace, workspace_factory, admin_user):
    """The defect fix round 1 introduced.

    Hoisting the replay ahead of the workspace check meant the legs compared
    came from the CALLER-SUPPLIED ``entry``. A caller in workspace A who named
    workspace B's grant pk and guessed B's reversal key satisfied
    ``_assert_same_movement`` and got B's entry back -- amount, description and
    ``created_by_id`` -- with no workspace check ever performed. That is a
    cross-tenant read of an audit record.
    """
    other = workspace_factory(name="تیم قربانی")
    theirs = wallet.grant_from_admin(
        workspace=other,
        amount_toman=80_000,
        description="شارژ فضای کاری دیگر برای تست نشت",
        created_by=admin_user,
        idempotency_key="leak-1",
    )
    their_reversal = wallet.revoke_grant(
        workspace=other,
        entry=theirs,
        description="ابطال شارژ فضای کاری دیگر",
        created_by=admin_user,
        idempotency_key="leak-1-rev",
    )
    assert their_reversal.workspace_id == other.pk
    entries_before = LedgerEntry.objects.count()

    with pytest.raises(wallet.WalletError) as excinfo:
        wallet.revoke_grant(
            workspace=workspace,
            entry=theirs,
            description="تلاش برای تکرار ابطال از فضای کاری دیگر",
            created_by=admin_user,
            idempotency_key="leak-1-rev",
        )

    # The plain base class, NOT a policy subclass: this is a confused-deputy
    # refusal, and an HTTP layer must not map it to "conflict/policy".
    assert excinfo.type is wallet.WalletError
    assert excinfo.value.message == wallet.WORKSPACE_MISMATCH_MESSAGE
    assert LedgerEntry.objects.count() == entries_before
    assert money.wallet_balance(other) == 0


def test_replaying_another_workspaces_charge_key_is_refused(workspace, workspace_factory, admin_user):
    """The other five functions are self-defending, and this pins why.

    Their legs are the caller's OWN workspace-scoped wallet accounts, so a
    foreign entry's accounts cannot satisfy ``_assert_same_movement`` -- the
    comparison fails loudly instead of leaking. ``revoke_grant`` was the sole
    exception, because its legs come from the caller's pk.
    """
    other = workspace_factory(name="تیم دیگر برای تست کلید")
    wallet.grant_from_admin(
        workspace=other,
        amount_toman=100_000,
        description="شارژ فضای کاری دیگر",
        created_by=admin_user,
        idempotency_key="xw-charge-setup",
    )
    wallet.charge_sms(workspace=other, amount_toman=1_200, log_id=31337)

    with pytest.raises(ValueError):
        wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=31337)


def test_replaying_another_workspaces_hold_key_is_refused(workspace, workspace_factory, admin_user):
    other = workspace_factory(name="تیم دیگر برای تست قفل")
    wallet.grant_from_admin(
        workspace=other,
        amount_toman=100_000,
        description="شارژ فضای کاری دیگر",
        created_by=admin_user,
        idempotency_key="xw-hold-setup",
    )
    wallet.hold_funds(workspace=other, amount_toman=40_000, idempotency_key="xw-hold-1")

    with pytest.raises(ValueError):
        wallet.hold_funds(workspace=workspace, amount_toman=40_000, idempotency_key="xw-hold-1")


# --- I1: the cap read is serialised like every other balance-bearing read ------


def test_grant_cap_read_takes_the_row_lock(workspace, admin_user, mocker):
    """The cap is the one limit on how much money an operator can mint.

    It was read through a plain ``get_or_create``, unlike every other
    balance-bearing read in the module, so two concurrent grants could both
    observe "under the cap" and jointly exceed it. Asserted structurally -- a
    threaded test would need a second DB connection, and what matters here is
    that the read is routed through ``select_for_update`` at all.
    """
    spy = mocker.spy(Wallet.objects, "select_for_update")

    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000,
        description="شارژ برای تست قفل سقف",
        created_by=admin_user,
        idempotency_key="cap-lock-1",
    )

    assert spy.call_count >= 1


def test_first_grant_creates_the_wallet_row_and_a_later_grant_is_capped(workspace, admin_user):
    """The create path, where there is no row to lock yet.

    ``_lock_wallet_row`` inserts inside its own savepoint on the first call (a
    concurrent creator's ``OneToOneField`` violation then poisons only the
    savepoint, and the loser re-reads under the lock) and locks on every call
    after. This exercises both halves in sequence.
    """
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=10_000,
        description="شارژ اولیه برای تست ایجاد ردیف",
        created_by=admin_user,
        idempotency_key="cap-create-1",
    )
    Wallet.objects.filter(workspace=workspace).update(admin_grant_cap_toman=15_000)

    with pytest.raises(wallet.GrantTooLarge):
        wallet.grant_from_admin(
            workspace=workspace,
            amount_toman=40_000,
            description="شارژ دوم که از سقف عبور می‌کند",
            created_by=admin_user,
            idempotency_key="cap-create-2",
        )

    assert money.wallet_balance(workspace) == 10_000


# --- holds are holds, and they have an author ----------------------------------


def test_hold_funds_defaults_to_the_hold_source(workspace, admin_user):
    """A hold booked as ``REFUND`` put holds in the "Refund" bucket of every statement."""
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست منبع قفل",
        created_by=admin_user,
        idempotency_key="hs-setup",
    )

    entry = wallet.hold_funds(workspace=workspace, amount_toman=30_000, idempotency_key="hs-1")

    assert entry.source == LedgerSource.HOLD


@pytest.mark.parametrize("bad_source", [LedgerSource.ADMIN_GRANT, LedgerSource.REFUND, LedgerSource.SMS_CHARGE, "nope"])
def test_hold_funds_refuses_a_source_that_is_not_a_hold(workspace, admin_user, bad_source):
    """An entry labelled "a grant was made" while moving money into a hold account
    makes every later statement about grants a lie.
    """
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست منبع نامعتبر قفل",
        created_by=admin_user,
        idempotency_key="hb-setup",
    )

    with pytest.raises(wallet.InvalidHoldSource):
        wallet.hold_funds(workspace=workspace, amount_toman=30_000, source=bad_source, idempotency_key="hb-1")

    assert money.wallet_balance(workspace) == 100_000
    assert money.wallet_hold_balance(workspace) == 0


def test_hold_funds_records_its_author(workspace, admin_user):
    """A hold is an operator action on a workspace, so it has an identifiable actor."""
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست نویسندهٔ قفل",
        created_by=admin_user,
        idempotency_key="ha-setup",
    )

    entry = wallet.hold_funds(workspace=workspace, amount_toman=30_000, idempotency_key="ha-1", created_by=admin_user)

    assert LedgerEntry.objects.get(pk=entry.pk).created_by_id == admin_user.pk


# --- a refund has to name the payment that failed ------------------------------


@pytest.mark.parametrize("bad_reference", [None, "", "   "])
def test_refund_refuses_a_missing_payment_reference(workspace, bad_reference):
    """The docstring claims "only a payment the gateway explicitly rejected".

    Free-text ``reason`` alone made that unenforceable -- any caller could mint
    money into a workspace by describing why.
    """
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست ارجاع پرداخت",
        created_by=None,
        idempotency_key="pr-setup",
    )

    with pytest.raises(wallet.InvalidPaymentReference):
        wallet.refund_to_spendable(
            workspace=workspace,
            amount_toman=25_000,
            reason="پرداخت توسط درگاه رد شد",
            reference=bad_reference,
            idempotency_key="pr-1",
        )

    assert money.wallet_balance(workspace) == 100_000


def test_refund_records_the_payment_reference_it_cites(workspace):
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست ثبت ارجاع",
        created_by=None,
        idempotency_key="pr2-setup",
    )

    entry = wallet.refund_to_spendable(
        workspace=workspace,
        amount_toman=25_000,
        reason="پرداخت توسط درگاه رد شد",
        reference="A000000004231",
        idempotency_key="pr-2",
    )

    stored = LedgerEntry.objects.get(pk=entry.pk)
    assert "A000000004231" in stored.description
    assert "پرداخت توسط درگاه رد شد" in stored.description


def test_refund_accepts_a_numeric_transaction_id(workspace):
    """A gateway reference may arrive as a number, not only as a string."""
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=100_000,
        description="شارژ برای تست ارجاع عددی",
        created_by=None,
        idempotency_key="pr3-setup",
    )

    entry = wallet.refund_to_spendable(
        workspace=workspace,
        amount_toman=25_000,
        reason="پرداخت توسط درگاه رد شد",
        reference=4231,
        idempotency_key="pr-3",
    )

    assert "4231" in LedgerEntry.objects.get(pk=entry.pk).description
