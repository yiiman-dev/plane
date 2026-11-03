# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Upgrade quotes: proration arithmetic and the renewal lock window."""

# Python imports
from datetime import datetime, timedelta, timezone

# Third party imports
import pytest

# Module imports
from plane.billing.models import PRORATION_CREDIT_REMAINING, PRORATION_NO_EXTENSION
from plane.billing.services.upgrade import CurrentPeriod, RenewalLockedError, quote_upgrade

NOW = datetime(2026, 10, 1, tzinfo=timezone.utc)
MONTH = timedelta(days=30)


def period(days_left: float, charge: int = 1_000_000, plan_code: str = "pro", tier_rank: int = 1) -> CurrentPeriod:
    return CurrentPeriod(
        ends_at=NOW + timedelta(days=days_left),
        cycle_length=MONTH,
        charge_toman=charge,
        plan_code=plan_code,
        tier_rank=tier_rank,
    )


def quote(current, **overrides):
    params = dict(
        now=NOW,
        current=current,
        target_plan_code="team",
        target_tier_rank=2,
        target_full_price_toman=2_000_000,
        target_cycle_length=MONTH,
        target_renew_lock_days=0,
        proration_mode=PRORATION_CREDIT_REMAINING,
    )
    params.update(overrides)
    return quote_upgrade(**params)


@pytest.mark.unit
def test_no_current_period_charges_full_price_and_starts_a_new_one():
    result = quote(None)

    assert result.payable_toman == 2_000_000
    assert result.credit_applied_toman == 0
    assert result.new_ends_at == NOW + MONTH


@pytest.mark.unit
def test_expired_period_is_not_credited_or_locked():
    result = quote(period(days_left=-1), target_plan_code="pro", target_renew_lock_days=10)

    assert result.payable_toman == 2_000_000
    assert result.credit_applied_toman == 0


@pytest.mark.unit
def test_upgrade_mid_cycle_credits_the_unused_half():
    # Half of a 1,000,000 toman month is left, so 500,000 is credited.
    result = quote(period(days_left=15))

    assert result.credit_applied_toman == 500_000
    assert result.payable_toman == 1_500_000
    assert result.new_ends_at == NOW + MONTH


@pytest.mark.unit
def test_credit_is_rounded_to_the_nearest_thousand():
    # 10 of 30 days left on a 1,000,001 charge: the exact credit is not a whole thousand.
    result = quote(period(days_left=10, charge=1_000_001))

    assert result.payable_toman % 1000 == 0
    assert result.payable_toman + result.credit_applied_toman == 2_000_000


@pytest.mark.unit
def test_credit_never_exceeds_the_full_price():
    result = quote(period(days_left=29, charge=10_000_000), target_full_price_toman=500_000)

    assert result.payable_toman == 0
    assert result.credit_applied_toman == 500_000


@pytest.mark.unit
def test_a_downgrade_earns_no_credit_and_keeps_the_end_date():
    result = quote(period(days_left=15, tier_rank=2), target_plan_code="basic", target_tier_rank=1)

    assert result.credit_applied_toman == 0
    assert result.payable_toman == 2_000_000
    assert result.new_ends_at is None


@pytest.mark.unit
def test_a_sideways_move_to_an_equal_rank_earns_no_credit():
    result = quote(period(days_left=15, tier_rank=2), target_plan_code="other", target_tier_rank=2)

    assert result.credit_applied_toman == 0
    assert result.payable_toman == 2_000_000
    assert result.new_ends_at is None


@pytest.mark.unit
def test_no_extension_mode_disables_the_credit():
    result = quote(period(days_left=15), proration_mode=PRORATION_NO_EXTENSION)

    assert result.credit_applied_toman == 0
    assert result.payable_toman == 2_000_000
    assert result.new_ends_at is None


@pytest.mark.unit
def test_renewing_the_same_plan_inside_the_lock_window_is_refused():
    with pytest.raises(RenewalLockedError) as raised:
        quote(
            period(days_left=5, plan_code="pro"),
            target_plan_code="pro",
            target_renew_lock_days=7,
        )

    assert raised.value.lock_days == 7
    assert raised.value.days_left == 5


@pytest.mark.unit
def test_renewing_the_same_plan_before_the_lock_window_is_allowed():
    result = quote(
        period(days_left=20, plan_code="pro", tier_rank=1),
        target_plan_code="pro",
        target_tier_rank=1,
        target_renew_lock_days=7,
    )

    assert result.payable_toman == 2_000_000


@pytest.mark.unit
def test_the_lock_does_not_apply_to_a_different_plan():
    result = quote(period(days_left=2, plan_code="pro"), target_plan_code="team", target_renew_lock_days=7)

    assert result.payable_toman > 0
