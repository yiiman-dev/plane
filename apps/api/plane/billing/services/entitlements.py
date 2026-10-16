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
    LIMIT_TYPE_NUMBER,
    FeatureFlag,
    Plan,
    PlanFeatureFlag,
    Subscription,
    SubscriptionStatus,
    WorkspaceFeatureFlag,
)
from plane.db.models import Project, WorkspaceMember, WorkspaceMemberInvite
from plane.license.utils.instance_value import get_workspace_free_seat_limit

FREE_PLAN_CODE = "free"
WORKSPACE_ADMIN_ROLE = 20

SEAT_LIMIT_REACHED_CODE = "seat_limit_reached"
FEATURE_NOT_IN_PLAN_CODE = "feature_not_in_plan"
FEATURE_LIMIT_REACHED_CODE = "feature_limit_reached"
FEATURE_LIMIT_UNSET_CODE = "feature_limit_unset"

# The code of the first capability gated by a flag. The catalogue row is created
# by a migration and ships INACTIVE on purpose: an instance that has never
# configured it keeps creating projects exactly as before, and an operator turns
# the gate on by activating the row and granting it to a plan.
PROJECT_LIMIT_FLAG_CODE = "projects"

SEAT_LIMIT_REACHED_MESSAGE = "سقف صندلی این پلن تکمیل است. برای افزودن عضو بیشتر باید پلن ورک‌اسپیس را ارتقا دهید."
SEAT_LIMIT_REACHED_PROJECT_MESSAGE = (
    "سقف صندلی این پلن تکمیل است و دعوت این پروژه پذیرفته نمی‌شود. برای پذیرش آن باید پلن ورک‌اسپیس را ارتقا دهید."
)
FEATURE_NOT_IN_PLAN_MESSAGE = "این قابلیت در پلن فعلی ورک‌اسپیس شما فعال نیست."
FEATURE_LIMIT_UNSET_MESSAGE = "حد این قابلیت در پلن فعلی تعیین نشده است."
FEATURE_LIMIT_REACHED_TEMPLATE = (
    "سقف «{unit}» این پلن تکمیل است ({used} از {limit}). برای افزودن مورد بیشتر باید پلن ورک‌اسپیس را ارتقا دهید."
)
FEATURE_LIMIT_REACHED_NO_UNIT_TEMPLATE = (
    "سقف این قابلیت در پلن فعلی تکمیل است ({used} از {limit}). برای افزودن مورد بیشتر باید پلن ورک‌اسپیس را ارتقا دهید."
)
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


def _resolve_active_grant(workspace, code: str) -> Tuple[Optional[FeatureFlag], Optional[PlanFeatureFlag]]:
    """The active flag and the plan's grant of it, or ``(None, None)``.

    This is the ONE implementation of the three layers a feature needs before it
    is usable: the catalogue row is active, the workspace's plan grants it, and
    the workspace itself has switched it on. ``has_feature`` and
    ``feature_limit`` both delegate here rather than restating the sequence.

    Why a shared helper rather than two parallel implementations: the two
    functions answer different questions about the same switch, and a pair of
    hand-written copies drifts the moment one of them is fixed. A feature that
    ``has_feature`` calls off but that still reports a limit is one a caller
    starts trusting. Returning the grant (not just a bool) saves
    ``feature_limit`` a second query for the same row.

    The order of the checks is also the order of the cheapest first: a missing
    flag costs one query, and only an existing flag reaches plan resolution.
    """
    if workspace is None or not code:
        return None, None

    feature_flag = FeatureFlag.objects.filter(code=code, is_active=True).first()
    if feature_flag is None:
        return None, None

    plan = resolve_workspace_plan(workspace)
    if plan is None:
        return None, None

    grant = PlanFeatureFlag.objects.filter(plan=plan, feature_flag=feature_flag, is_enabled=True).first()
    if grant is None:
        return None, None

    switched_on = WorkspaceFeatureFlag.objects.filter(
        workspace=workspace, feature_flag=feature_flag, is_enabled=True
    ).exists()
    if not switched_on:
        return None, None

    return feature_flag, grant


def has_feature(workspace, code: str) -> bool:
    """True only when the flag is on, granted by the plan, and switched on here.

    Delegates to ``_resolve_active_grant`` so it cannot come to disagree with
    ``feature_limit`` about the same switch.
    """
    feature_flag, _grant = _resolve_active_grant(workspace, code)
    return feature_flag is not None


def feature_limit(workspace, code: str) -> Optional[int]:
    """The effective numeric limit of a ``number`` feature flag, or None.

    None means "this question does not apply", and it covers every case that is
    not a countable bound: the flag is not a number flag, the plan does not grant
    it, the workspace has not switched it on, the catalogue row is inactive, or
    there is no such flag at all. ``0`` is a bound -- "none allowed" -- and is
    returned as ``0``.

    The three layers are NOT restated here. ``_resolve_active_grant`` is the
    single implementation of "the flag exists, the plan grants it, the workspace
    switched it on", and ``has_feature`` calls the same helper. Two hand-written
    copies of that sequence is how they drift: a later fix to one would leave
    the other answering a different question about the same switch, and a
    feature reported off while still reporting a limit is one a caller starts
    trusting. Sharing the helper removes the possibility rather than documenting
    the risk.

    Phase 2 has no production caller for this yet. It is written and tested now
    so that Phase 3 gates its first real capability on proven behaviour rather
    than on a function nobody has run.
    """
    feature_flag, grant = _resolve_active_grant(workspace, code)
    if feature_flag is None or feature_flag.limit_type != LIMIT_TYPE_NUMBER:
        return None

    # A granted number flag with no stored limit cannot be gated on, so it grants
    # nothing rather than granting an unbounded amount by accident. The
    # serializer refuses creating that row; this handles one that predates it.
    #
    # ``None`` and ``0`` are different answers and must stay different: None is
    # "no bound is known", 0 is "none allowed". A caller writing
    # ``if not limit:`` conflates them and treats a workspace allowed zero of
    # something as one with no limit at all.
    return grant.limit_value


def get_project_usage(workspace) -> int:
    """Projects the workspace currently holds against its limit.

    Archived projects are history, not capacity, so they do not count. Soft
    deleted rows are already excluded by the model's own manager.
    """
    if workspace is None:
        return 0

    return Project.objects.filter(workspace=workspace, archived_at__isnull=True).count()


def feature_limit_rejection(workspace, code: str, used: int, additional: int = 1) -> Optional[Dict[str, Any]]:
    """Error body for a refused countable capability, or None when it may proceed.

    Four answers, and the order they are asked in is deliberate:

    1. The catalogue row is missing or inactive -> ``None``, allowed. The flag
       catalogue is opt-in configuration an instance admin fills in, so an
       installation that has never created the row must keep the behaviour it
       had before the gate existed. Failing closed here would take a capability
       away from every workspace on every installation the moment the code
       shipped, which is a worse outcome than an ungated capability.
    2. The plan does not grant it, or the workspace switched it off ->
       ``feature_not_in_plan``. This is the branch the acceptance criterion
       names: off really does mean the capability does not work.
    3. A ``number`` flag with a stored bound -> allowed while
       ``used + additional`` fits, refused past that.
    4. A ``number`` flag with no stored bound -> ``feature_limit_unset``.
       Treating an unknown bound as unlimited is how a workspace gets an
       unbounded amount of a countable thing by accident; the plan serializer
       already refuses to create such a row, and this catches the older ones.

    A non-number flag that is granted and switched on is treated as "on, no
    bound" -- for a countable capability the operator has to register the flag
    as ``number`` or ``unlimited``, and ``boolean`` then behaves as unlimited
    rather than silently refusing.
    """
    if workspace is None:
        return None

    feature_flag = FeatureFlag.objects.filter(code=code, is_active=True).first()
    if feature_flag is None:
        return None

    if not has_feature(workspace, code):
        return {
            "error": FEATURE_NOT_IN_PLAN_MESSAGE,
            "code": FEATURE_NOT_IN_PLAN_CODE,
        }

    limit = feature_limit(workspace, code)
    if feature_flag.limit_type != LIMIT_TYPE_NUMBER:
        return None

    requested = max(int(additional or 0), 0)
    counted = max(int(used or 0), 0)
    if limit is None:
        return {
            "error": FEATURE_LIMIT_UNSET_MESSAGE,
            "code": FEATURE_LIMIT_UNSET_CODE,
            "used": counted,
        }

    if counted + requested <= limit:
        return None

    unit = (feature_flag.unit_label or "").strip()
    template = FEATURE_LIMIT_REACHED_TEMPLATE if unit else FEATURE_LIMIT_REACHED_NO_UNIT_TEMPLATE
    return {
        "error": template.format(unit=unit, used=counted, limit=limit),
        "code": FEATURE_LIMIT_REACHED_CODE,
        "limit": limit,
        "used": counted,
    }


def project_limit_rejection(workspace, additional: int = 1) -> Optional[Dict[str, Any]]:
    """Error body for a refused project creation, or None when it may proceed.

    Named for the resource rather than the flag, matching
    ``seat_limit_rejection``: a caller refuses an operation, and which flag
    represents it stays in here.
    """
    return feature_limit_rejection(
        workspace,
        PROJECT_LIMIT_FLAG_CODE,
        used=get_project_usage(workspace),
        additional=additional,
    )


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
