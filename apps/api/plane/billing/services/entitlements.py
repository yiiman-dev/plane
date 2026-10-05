# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The single place where workspace plan access is decided.

Plans are workspace entitlements even though a user pays for them, so every
question of the form "what may this workspace do and how many people may join
it" is answered here and never duplicated in a view.
"""

# Python imports
from typing import Any, Dict, List, Optional, Tuple

# Django imports
from django.db.models import F, Q
from django.utils import timezone

# Module imports
from plane.billing.models import (
    FeatureFlag,
    Plan,
    PlanFeatureFlag,
    Subscription,
    SubscriptionStatus,
    WorkspaceFeatureFlag,
)
from plane.db.models import WorkspaceMember, WorkspaceMemberInvite
from plane.license.utils.instance_value import get_workspace_free_seat_limit

FREE_PLAN_CODE = "free"
WORKSPACE_ADMIN_ROLE = 20

SEAT_LIMIT_REACHED_CODE = "seat_limit_reached"
FEATURE_NOT_IN_PLAN_CODE = "feature_not_in_plan"

SEAT_LIMIT_REACHED_MESSAGE = "سقف صندلی این پلن تکمیل است. برای افزودن عضو بیشتر باید پلن ورک‌اسپیس را ارتقا دهید."
SEAT_LIMIT_REACHED_PROJECT_MESSAGE = (
    "سقف صندلی این پلن تکمیل است و دعوت این پروژه پذیرفته نمی‌شود. برای پذیرش آن باید پلن ورک‌اسپیس را ارتقا دهید."
)
FEATURE_NOT_IN_PLAN_MESSAGE = "این قابلیت در پلن فعلی ورک‌اسپیس شما فعال نیست."
FEATURE_UNKNOWN_MESSAGE = "قابلیت درخواستی وجود ندارد."
FEATURE_UNAVAILABLE_MESSAGE = "این قابلیت در حال حاضر روی این نمونه فعال نیست."


def _active_subscriptions():
    """Subscriptions that are active right now, never expired."""
    now = timezone.now()
    return Subscription.objects.filter(status=SubscriptionStatus.ACTIVE).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gt=now)
    )


def _most_recent(subscriptions):
    """Pick one subscription deterministically: latest end date, then newest.

    A subscription without an end date never expires, so it is the strongest
    match and is sorted first. The id breaks any remaining tie so repeated
    calls can never return different rows.
    """
    return (
        subscriptions.select_related("plan").order_by(F("ends_at").desc(nulls_first=True), "-created_at", "-id").first()
    )


def resolve_workspace_plan(workspace) -> Optional[Plan]:
    """Return the plan that currently entitles ``workspace``, or None.

    The order is a fixed priority list: a subscription bought for this very
    workspace wins, then the owner's own paid subscription, then the same for a
    workspace admin, then the free plan row, and finally nothing at all so that
    an instance without plans is never locked down.
    """
    if workspace is None:
        return None

    subscription = _most_recent(_active_subscriptions().filter(workspace=workspace))
    if subscription is not None:
        return subscription.plan

    subscription = _most_recent(
        _active_subscriptions().filter(user_id=workspace.owner_id).exclude(plan__code=FREE_PLAN_CODE)
    )
    if subscription is not None:
        return subscription.plan

    admin_ids = WorkspaceMember.objects.filter(
        workspace=workspace, role__gte=WORKSPACE_ADMIN_ROLE, is_active=True
    ).values_list("member_id", flat=True)
    subscription = _most_recent(
        _active_subscriptions().filter(user_id__in=list(admin_ids)).exclude(plan__code=FREE_PLAN_CODE)
    )
    if subscription is not None:
        return subscription.plan

    return Plan.objects.filter(code=FREE_PLAN_CODE, is_active=True).first()


def get_seat_usage(workspace) -> int:
    """Seats taken right now: active human members plus pending invitations.

    An invitation already holds a seat, which is why accepting one never
    changes this number.
    """
    if workspace is None:
        return 0

    active_members = WorkspaceMember.objects.filter(workspace=workspace, is_active=True, member__is_bot=False).count()
    pending_invitations = WorkspaceMemberInvite.objects.filter(workspace=workspace, responded_at__isnull=True).count()
    return active_members + pending_invitations


def _instance_free_seat_limit() -> Optional[int]:
    """Seat cap for workspaces with no plan, read from instance configuration.

    An empty or malformed value means unlimited so a bad setting can never lock
    an existing installation out.
    """
    (raw_value,) = get_workspace_free_seat_limit()
    if raw_value is None:
        return None

    text = str(raw_value).strip()
    if not text:
        return None

    try:
        value = int(text)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


def get_seat_limit(workspace) -> Optional[int]:
    """Maximum seats for the workspace, or None when unlimited."""
    plan = resolve_workspace_plan(workspace)
    if plan is None:
        return _instance_free_seat_limit()
    return plan.max_seats


def seat_limit_rejection(
    workspace, additional: int = 1, message: str = SEAT_LIMIT_REACHED_MESSAGE
) -> Optional[Dict[str, Any]]:
    """Error body for a refused seat operation, or None when it may proceed.

    ``message`` only changes the human readable ``error`` line so a caller can
    name the operation that was refused.  The machine readable keys never move,
    every client reads the same body shape.
    """
    limit = get_seat_limit(workspace)
    if limit is None:
        return None

    seats_used = get_seat_usage(workspace)
    requested = max(int(additional or 0), 0)
    if seats_used + requested <= limit:
        return None

    return {
        "error": message,
        "code": SEAT_LIMIT_REACHED_CODE,
        "seat_limit": limit,
        "seats_used": seats_used,
    }


def check_seat_availability(workspace, additional: int = 1) -> Tuple[bool, Optional[str]]:
    """Whether ``additional`` more seats fit, with the Persian reason when not."""
    rejection = seat_limit_rejection(workspace, additional=additional)
    if rejection is None:
        return True, None
    return False, rejection["error"]


def has_feature(workspace, code: str) -> bool:
    """True only when the flag is on, granted by the plan, and switched on here."""
    if workspace is None or not code:
        return False

    feature_flag = FeatureFlag.objects.filter(code=code, is_active=True).first()
    if feature_flag is None:
        return False

    plan = resolve_workspace_plan(workspace)
    if plan is None:
        return False

    granted = PlanFeatureFlag.objects.filter(plan=plan, feature_flag=feature_flag, is_enabled=True).exists()
    if not granted:
        return False

    return WorkspaceFeatureFlag.objects.filter(workspace=workspace, feature_flag=feature_flag, is_enabled=True).exists()


def grantable_feature_codes(workspace) -> List[str]:
    """Feature codes the current plan allows the workspace to switch on."""
    plan = resolve_workspace_plan(workspace)
    if plan is None:
        return []

    return list(
        FeatureFlag.objects.filter(is_active=True, plan_grants__plan=plan, plan_grants__is_enabled=True)
        .order_by("category", "code")
        .distinct()
        .values_list("code", flat=True)
    )


def get_feature_flag_rows(workspace) -> List[Dict[str, Any]]:
    """Every active feature flag with this workspace's access state."""
    grantable = set(grantable_feature_codes(workspace))
    enabled_codes = set(
        WorkspaceFeatureFlag.objects.filter(
            workspace=workspace, is_enabled=True, feature_flag__is_active=True
        ).values_list("feature_flag__code", flat=True)
    )

    return [
        {
            "code": feature_flag.code,
            "name": feature_flag.name,
            "description": feature_flag.description,
            "category": feature_flag.category,
            "is_public": feature_flag.is_public,
            "has_access": feature_flag.code in grantable,
            "is_enabled": feature_flag.code in enabled_codes,
        }
        for feature_flag in FeatureFlag.objects.filter(is_active=True).order_by("category", "code")
    ]


def get_workspace_entitlement(workspace) -> Dict[str, Any]:
    """Everything a workspace needs to render its plan, seats and feature UI."""
    plan = resolve_workspace_plan(workspace)
    seat_limit = get_seat_limit(workspace)
    seats_used = get_seat_usage(workspace)

    return {
        "plan": (
            {
                "code": plan.code,
                "name": plan.name,
                "description": plan.description,
                "access_level": plan.access_level,
                "is_free": plan.code == FREE_PLAN_CODE,
            }
            if plan is not None
            else None
        ),
        "seat_limit": seat_limit,
        "seats_used": seats_used,
        "seats_remaining": None if seat_limit is None else max(0, seat_limit - seats_used),
        "feature_flags": get_feature_flag_rows(workspace),
    }
