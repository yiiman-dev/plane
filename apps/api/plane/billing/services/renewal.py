# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Renewal reminders for workspace admins (phase 5).

A reminder is due on a configured number of days before a subscription ends.
Beat runs once a day and only looks at today: a subscription whose mark fell
on an earlier day is not reminded late, and a mark that is due today is sent
once, because ``RenewalNotice`` is unique per (subscription, mark, period end).

Dates are compared in UTC, the same zone the beat schedule uses, so a reminder
never lands on a different calendar day than the one the schedule names.
"""

# Python imports
import logging
from datetime import datetime, time, timedelta, timezone as dt_timezone
from typing import List

# Django imports
from django.db import transaction as db_transaction
from django.utils import timezone

# Module imports
from plane.billing.models import (
    DEFAULT_RENEWAL_NOTICE_DAYS,
    RenewalNotice,
    RenewalNoticeSchedule,
    Subscription,
    SubscriptionStatus,
)
from plane.db.models import Notification, WorkspaceMember

logger = logging.getLogger("plane.billing")

# Workspace role that receives the reminder: the admin who can renew the plan.
ADMIN_ROLE = 20

# The schedule is validated against these bounds. A year is the longest a
# reminder can sensibly be early for a plan that bills per cycle.
MIN_NOTICE_DAY = 1
MAX_NOTICE_DAY = 365


class InvalidSchedule(ValueError):
    """The requested reminder days are not usable."""


def validate_days(days) -> List[int]:
    """Return the days sorted high to low, or raise ``InvalidSchedule``.

    Duplicates and out-of-range values are rejected rather than dropped: a
    silently ignored day would look configured and never fire.
    """
    if not isinstance(days, list) or not days:
        raise InvalidSchedule("days_before must be a non-empty list of whole numbers")
    cleaned = []
    for day in days:
        # ``bool`` is a subclass of ``int``; ``true`` in the body is not a day.
        if isinstance(day, bool) or not isinstance(day, int):
            raise InvalidSchedule("days_before must contain only whole numbers")
        if not MIN_NOTICE_DAY <= day <= MAX_NOTICE_DAY:
            raise InvalidSchedule(f"each day must be between {MIN_NOTICE_DAY} and {MAX_NOTICE_DAY}")
        cleaned.append(day)
    if len(set(cleaned)) != len(cleaned):
        raise InvalidSchedule("days_before must not repeat a day")
    return sorted(cleaned, reverse=True)


def get_schedule() -> RenewalNoticeSchedule:
    """The single schedule row, created with the default days on first read."""
    schedule = RenewalNoticeSchedule.objects.order_by("created_at").first()
    if schedule is None:
        schedule = RenewalNoticeSchedule.objects.create(days_before=list(DEFAULT_RENEWAL_NOTICE_DAYS))
    return schedule


def save_schedule(days) -> RenewalNoticeSchedule:
    schedule = get_schedule()
    schedule.days_before = validate_days(days)
    schedule.save(update_fields=["days_before", "updated_at"])
    return schedule


def _start_of_day(day) -> datetime:
    return datetime.combine(day, time.min, tzinfo=dt_timezone.utc)


def _admin_user_ids(workspace) -> List:
    return list(
        WorkspaceMember.objects.filter(workspace=workspace, role=ADMIN_ROLE, is_active=True).values_list(
            "member_id", flat=True
        )
    )


def _notify(subscription: Subscription, days_before: int, recipients: List) -> None:
    plan_name = subscription.plan.name
    title = f"اشتراک پلن «{plan_name}» {days_before} روز دیگر به پایان می‌رسد"
    for user_id in recipients:
        Notification.objects.create(
            workspace=subscription.workspace,
            receiver_id=user_id,
            title=title,
            entity_name="billing_subscription",
            entity_identifier=subscription.pk,
            sender="billing",
            data={"subscription_id": str(subscription.pk), "days_before": days_before},
        )


def send_due_renewal_notices(today=None) -> int:
    """Send every reminder whose mark is today. Returns how many were sent.

    ``today`` exists so tests can pick the day; beat leaves it unset.
    """
    today = today or timezone.now().astimezone(dt_timezone.utc).date()
    days = sorted(set(get_schedule().days_before or []))
    if not days:
        return 0

    # A subscription ending on day D has its mark for day ``D - n`` on today
    # when ``D == today + n``. Only subscriptions ending inside the widest
    # window can have a mark today, so the query is bounded by it.
    day_start = _start_of_day(today)
    candidates = Subscription.objects.select_related("plan", "workspace").filter(
        status=SubscriptionStatus.ACTIVE,
        workspace__isnull=False,
        ends_at__gte=day_start + timedelta(days=min(days)),
        ends_at__lt=day_start + timedelta(days=max(days) + 1),
    )

    sent = 0
    for subscription in candidates:
        ends_on = subscription.ends_at.astimezone(dt_timezone.utc).date()
        for days_before in days:
            if ends_on != today + timedelta(days=days_before):
                continue
            sent += _send_one(subscription, days_before)
    return sent


def _send_one(subscription: Subscription, days_before: int) -> int:
    """Record one reminder and notify the admins, or do nothing if it already went out."""
    with db_transaction.atomic():
        # ``get_or_create`` is the race guard: two beat workers that reach this
        # line together see one row, and only the creator notifies.
        notice, created = RenewalNotice.objects.get_or_create(
            subscription=subscription,
            days_before=days_before,
            period_ends_at=subscription.ends_at,
        )
        if not created:
            return 0
        recipients = _admin_user_ids(subscription.workspace)
        notice.recipients = len(recipients)
        notice.save(update_fields=["recipients", "updated_at"])
        _notify(subscription, days_before, recipients)
    logger.info(
        "billing: renewal notice %s days before subscription %s to %s admins",
        days_before,
        subscription.pk,
        len(recipients),
    )
    return 1
