# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Tests for core feature flags gating (task blocking, pages, AI, etc.).

AGENTS.md rule:
- Gating needs a test that covers the off case, otherwise the flag silently does nothing.
- Missing or inactive flag must allow (upgrade safety).
- Active flag not granted or switched off must refuse with FEATURE_NOT_IN_PLAN_CODE.
"""

# Django imports
import pytest

# Module imports
from plane.billing.models import (
    BillingCycle,
    FeatureFlag,
    Plan,
    PlanFeatureFlag,
    Subscription,
    SubscriptionStatus,
    WorkspaceFeatureFlag,
)
from plane.billing.services.entitlements import (
    AI_FEATURES_FLAG_CODE,
    AI_FEATURES_NOT_IN_PLAN_MESSAGE,
    FEATURE_NOT_IN_PLAN_CODE,
    PAGES_FLAG_CODE,
    PAGES_NOT_IN_PLAN_MESSAGE,
    TASK_BLOCKING_FLAG_CODE,
    TASK_BLOCKING_NOT_IN_PLAN_MESSAGE,
    TIME_TRACKING_FLAG_CODE,
    TIME_TRACKING_NOT_IN_PLAN_MESSAGE,
    ai_features_rejection,
    feature_gate_rejection,
    has_feature,
    pages_rejection,
    task_blocking_rejection,
    time_tracking_rejection,
)


def _subscribe(workspace, plan: Plan) -> None:
    Subscription.objects.create(
        user=workspace.owner,
        workspace=workspace,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        seats=1,
        cycle=BillingCycle.MONTHLY,
    )


@pytest.mark.django_db
def test_missing_or_inactive_feature_flag_is_allowed(workspace_factory):
    """When a feature flag is not registered or is inactive, operations are allowed."""
    workspace = workspace_factory(name="تیم تستی")

    # Flag not in DB
    assert feature_gate_rejection(workspace, "unregistered_flag") is None

    # Flag in DB but is_active = False
    FeatureFlag.objects.create(code=TASK_BLOCKING_FLAG_CODE, name="قفل تسک", is_active=False)
    assert task_blocking_rejection(workspace) is None
    assert pages_rejection(workspace) is None
    assert ai_features_rejection(workspace) is None


@pytest.mark.django_db
def test_active_flag_not_in_plan_is_refused(workspace_factory):
    """When a flag is active, but the workspace's plan does not grant it, it is refused."""
    workspace = workspace_factory(name="تیم بدون دسترسی")
    FeatureFlag.objects.create(code=TASK_BLOCKING_FLAG_CODE, name="قفل تسک", is_active=True)
    FeatureFlag.objects.create(code=PAGES_FLAG_CODE, name="صفحات", is_active=True)
    FeatureFlag.objects.create(code=AI_FEATURES_FLAG_CODE, name="هوش مصنوعی", is_active=True)

    plan = Plan.objects.create(code="basic", name="پلن پایه")
    _subscribe(workspace, plan)

    # Task blocking off case
    rejection = task_blocking_rejection(workspace)
    assert rejection is not None
    assert rejection["code"] == FEATURE_NOT_IN_PLAN_CODE
    assert rejection["error"] == TASK_BLOCKING_NOT_IN_PLAN_MESSAGE

    # Pages off case
    rejection = pages_rejection(workspace)
    assert rejection is not None
    assert rejection["code"] == FEATURE_NOT_IN_PLAN_CODE
    assert rejection["error"] == PAGES_NOT_IN_PLAN_MESSAGE

    # AI off case
    rejection = ai_features_rejection(workspace)
    assert rejection is not None
    assert rejection["code"] == FEATURE_NOT_IN_PLAN_CODE
    assert rejection["error"] == AI_FEATURES_NOT_IN_PLAN_MESSAGE


@pytest.mark.django_db
def test_active_flag_granted_and_enabled_is_allowed(workspace_factory):
    """When a flag is active, granted to the plan, and enabled for the workspace, it succeeds."""
    workspace = workspace_factory(name="تیم پیشرفته")
    task_flag = FeatureFlag.objects.create(code=TASK_BLOCKING_FLAG_CODE, name="قفل تسک", is_active=True)
    pages_flag = FeatureFlag.objects.create(code=PAGES_FLAG_CODE, name="صفحات", is_active=True)
    ai_flag = FeatureFlag.objects.create(code=AI_FEATURES_FLAG_CODE, name="هوش مصنوعی", is_active=True)

    pro_plan = Plan.objects.create(code="pro", name="پلن حرفه‌ای")
    PlanFeatureFlag.objects.create(plan=pro_plan, feature_flag=task_flag, is_enabled=True)
    PlanFeatureFlag.objects.create(plan=pro_plan, feature_flag=pages_flag, is_enabled=True)
    PlanFeatureFlag.objects.create(plan=pro_plan, feature_flag=ai_flag, is_enabled=True)

    _subscribe(workspace, pro_plan)

    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=task_flag, is_enabled=True)
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=pages_flag, is_enabled=True)
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=ai_flag, is_enabled=True)

    assert has_feature(workspace, TASK_BLOCKING_FLAG_CODE) is True
    assert has_feature(workspace, PAGES_FLAG_CODE) is True
    assert has_feature(workspace, AI_FEATURES_FLAG_CODE) is True

    assert task_blocking_rejection(workspace) is None
    assert pages_rejection(workspace) is None
    assert ai_features_rejection(workspace) is None


@pytest.mark.django_db
def test_workspace_switched_off_feature_is_refused(workspace_factory):
    """When granted by plan but workspace admin disabled it, it is refused."""
    workspace = workspace_factory(name="تیم غیرفعال‌کننده")
    task_flag = FeatureFlag.objects.create(code=TASK_BLOCKING_FLAG_CODE, name="قفل تسک", is_active=True)
    pro_plan = Plan.objects.create(code="pro", name="پلن حرفه‌ای")
    PlanFeatureFlag.objects.create(plan=pro_plan, feature_flag=task_flag, is_enabled=True)
    _subscribe(workspace, pro_plan)

    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=task_flag, is_enabled=False)

    assert has_feature(workspace, TASK_BLOCKING_FLAG_CODE) is False
    rejection = task_blocking_rejection(workspace)
    assert rejection is not None
    assert rejection["code"] == FEATURE_NOT_IN_PLAN_CODE


@pytest.mark.django_db
def test_time_tracking_feature_gate(workspace_factory):
    """Time tracking gating works correctly when flag is active vs inactive."""
    workspace = workspace_factory(name="تیم مدیریت زمان")
    # Missing flag allows
    assert time_tracking_rejection(workspace) is None

    # Active flag without grant refuses
    time_flag = FeatureFlag.objects.create(code=TIME_TRACKING_FLAG_CODE, name="ثبت زمان", is_active=True)
    rejection = time_tracking_rejection(workspace)
    assert rejection is not None
    assert rejection["code"] == FEATURE_NOT_IN_PLAN_CODE
    assert rejection["error"] == TIME_TRACKING_NOT_IN_PLAN_MESSAGE

    # With plan grant and workspace flag enabled, allowed
    plan = Plan.objects.create(code="business", name="پلن شرکتی")
    PlanFeatureFlag.objects.create(plan=plan, feature_flag=time_flag, is_enabled=True)
    _subscribe(workspace, plan)
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=time_flag, is_enabled=True)

    assert has_feature(workspace, TIME_TRACKING_FLAG_CODE) is True
    assert time_tracking_rejection(workspace) is None

