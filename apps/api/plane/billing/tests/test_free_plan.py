# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Moving a paid workspace back to the free plan at the end of its period."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from plane.billing.models import Plan, Subscription, SubscriptionStatus
from plane.billing.services.entitlements import (
    FREE_PLAN_CODE,
    current_workspace_subscription,
    resolve_workspace_plan,
    schedule_free_plan,
)
from plane.db.models import User, Workspace, WorkspaceMember


def _user(label):
    return User.objects.create(email=f"{label}-{uuid4().hex[:6]}@example.com", username=uuid4().hex)


def _plan(code, **kwargs):
    defaults = {"name": code.title(), "max_seats": 10, "is_active": True}
    defaults.update(kwargs)
    return Plan.objects.create(code=code, **defaults)


def _workspace(label, owner):
    workspace = Workspace.objects.create(name=label, owner=owner, slug=f"{label}-{uuid4().hex[:6]}")
    WorkspaceMember.objects.create(workspace=workspace, member=owner, role=20, is_active=True)
    return workspace


@pytest.fixture
def free_plan(db):
    return _plan(FREE_PLAN_CODE, name="Free")


@pytest.mark.unit
@pytest.mark.django_db
class TestScheduleFreePlan:
    def test_paid_workspace_keeps_plan_until_period_end(self, free_plan):
        owner = _user("paid")
        workspace = _workspace("paid", owner)
        paid = _plan("pro-paid")
        ends_at = timezone.now() + timedelta(days=20)
        subscription = Subscription.objects.create(
            user=owner,
            plan=paid,
            workspace=workspace,
            status=SubscriptionStatus.ACTIVE,
            starts_at=timezone.now(),
            ends_at=ends_at,
            auto_renew=True,
        )

        result = schedule_free_plan(workspace)

        assert result == {"status": "scheduled", "effective_at": ends_at}
        subscription.refresh_from_db()
        assert subscription.auto_renew is False
        assert subscription.status == SubscriptionStatus.ACTIVE
        # nothing changes until the period runs out
        assert resolve_workspace_plan(workspace).code == paid.code

    def test_workspace_already_on_free_plan(self, free_plan):
        workspace = _workspace("free", _user("free"))

        assert schedule_free_plan(workspace) == {"status": "already_free", "effective_at": None}

    def test_paid_plan_from_owner_is_not_changed_here(self, free_plan):
        owner = _user("owner-level")
        workspace = _workspace("owner-level", owner)
        Subscription.objects.create(
            user=owner,
            plan=_plan("owner-paid"),
            status=SubscriptionStatus.ACTIVE,
            starts_at=timezone.now(),
            ends_at=timezone.now() + timedelta(days=5),
            auto_renew=True,
        )

        result = schedule_free_plan(workspace)

        assert result["status"] == "not_workspace_subscription"
        assert Subscription.objects.get(user=owner).auto_renew is True

    def test_current_subscription_reports_its_period_end(self, free_plan):
        owner = _user("period")
        workspace = _workspace("period", owner)
        ends_at = timezone.now() + timedelta(days=3)
        Subscription.objects.create(
            user=owner,
            plan=_plan("period-paid"),
            workspace=workspace,
            status=SubscriptionStatus.ACTIVE,
            starts_at=timezone.now(),
            ends_at=ends_at,
        )

        assert current_workspace_subscription(workspace).ends_at == ends_at
