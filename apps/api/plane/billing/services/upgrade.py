# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Upgrade pricing and the renewal lock window.

Pure arithmetic over values the caller has already read. Nothing here touches
the database or the clock, so the money rules can be pinned without a fixture
stack, and every endpoint that quotes a price calls the same function.
"""

# Python imports
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

# Module imports
from plane.billing.models import PRORATION_NO_EXTENSION

# Amounts shown to the customer are whole thousands of toman, so an invoice reads cleanly.
ROUNDING_STEP_TOMAN = 1000


class RenewalLockedError(Exception):
    """A renewal of the same plan was asked for inside its lock window."""

    def __init__(self, lock_days: int, days_left: int):
        self.lock_days = lock_days
        self.days_left = days_left
        super().__init__(f"Renewal is locked: {days_left} day(s) left, the lock starts at {lock_days} day(s).")


@dataclass(frozen=True)
class CurrentPeriod:
    """The paid period a workspace is in right now."""

    ends_at: datetime
    cycle_length: timedelta
    charge_toman: int
    plan_code: str
    tier_rank: int


@dataclass(frozen=True)
class UpgradeQuote:
    full_price_toman: int
    credit_applied_toman: int
    payable_toman: int
    # None means the current end date is kept (no extension).
    new_ends_at: Optional[datetime]


def _round_to_step(value: Decimal) -> int:
    step = Decimal(ROUNDING_STEP_TOMAN)
    return int((value / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step)


def quote_upgrade(
    *,
    now: datetime,
    current: Optional[CurrentPeriod],
    target_plan_code: str,
    target_tier_rank: int,
    target_full_price_toman: int,
    target_cycle_length: timedelta,
    target_renew_lock_days: int,
    proration_mode: str,
) -> UpgradeQuote:
    """Quote what a purchase costs and when the paid period ends.

    A purchase is an upgrade only when the target's ``tier_rank`` is strictly
    above the current plan's. Equal ranks are sideways moves and get no credit.
    """
    full = int(target_full_price_toman)
    if current is None or current.ends_at <= now:
        # Nothing is paid for right now, so there is nothing to credit or lock.
        return UpgradeQuote(
            full_price_toman=full,
            credit_applied_toman=0,
            payable_toman=full,
            new_ends_at=now + target_cycle_length,
        )

    days_left = (current.ends_at - now).days
    if target_plan_code == current.plan_code and days_left <= target_renew_lock_days:
        raise RenewalLockedError(target_renew_lock_days, days_left)

    # Only a real upgrade is credited, and only when the plan allows proration.
    # A downgrade or sideways move pays full price and keeps the existing end date.
    is_upgrade = target_tier_rank > current.tier_rank
    if not is_upgrade or proration_mode == PRORATION_NO_EXTENSION:
        return UpgradeQuote(
            full_price_toman=full,
            credit_applied_toman=0,
            payable_toman=full,
            new_ends_at=None,
        )

    remaining_seconds = max(0.0, (current.ends_at - now).total_seconds())
    cycle_seconds = Decimal(str(current.cycle_length.total_seconds()))
    ratio = min(Decimal("1"), Decimal(str(remaining_seconds)) / cycle_seconds)
    credit_exact = Decimal(int(current.charge_toman)) * ratio
    payable = max(0, _round_to_step(Decimal(full) - credit_exact))
    return UpgradeQuote(
        full_price_toman=full,
        credit_applied_toman=full - payable,
        payable_toman=payable,
        new_ends_at=now + target_cycle_length,
    )
