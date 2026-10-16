# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The first capability actually gated by a feature flag.

Phase 2 stored limits and wrote ``feature_limit`` with no production caller.
This is the caller: ``project_limit_rejection`` decides whether one more project
may be created in a workspace, and every branch of that decision is pinned here
because the failure modes point in opposite directions.

Two of them matter most:

* A missing or inactive catalogue row must NOT refuse anything. The flag
  catalogue is opt-in configuration that an instance admin fills in; an
  installation that has never created the flag has to keep behaving exactly as
  it did before the upgrade, or shipping the gate takes every workspace's
  projects away.
* An active flag the plan does not grant, or that the workspace has switched
  off, must refuse. That is the whole point of gating, and the acceptance
  criterion is that the capability really does not work when it is off.
"""

# Python imports
from itertools import count

# Django imports
from django.utils import timezone

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
    FEATURE_LIMIT_REACHED_CODE,
    FEATURE_LIMIT_UNSET_CODE,
    FEATURE_NOT_IN_PLAN_CODE,
    PROJECT_LIMIT_FLAG_CODE,
    get_project_usage,
    project_limit_rejection,
)
from plane.db.models import Project


def _subscribe(workspace, plan: Plan) -> None:
    Subscription.objects.create(
        user=workspace.owner,
        workspace=workspace,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        seats=1,
        cycle=BillingCycle.MONTHLY,
    )


def granted_workspace(workspace_factory, limit=3, limit_type="number", switched_on=True):
    """A workspace whose plan grants the project limit, switched on by default."""
    workspace = workspace_factory(name="تیم محدود")
    flag = FeatureFlag.objects.create(
        code=PROJECT_LIMIT_FLAG_CODE,
        name="پروژه‌ها",
        limit_type=limit_type,
        unit_label="پروژه",
    )
    plan = Plan.objects.create(code="limited", name="پلن محدود")
    PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, is_enabled=True, limit_value=limit)
    _subscribe(workspace, plan)
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=flag, is_enabled=switched_on)
    return workspace, flag


_project_identifiers = count(1)


def make_projects(workspace, amount: int, archived: bool = False) -> None:
    """Create ``amount`` projects, from a module counter.

    ``identifier`` is unique per workspace, so two calls in one test must not
    both start at zero -- and the constraint ignores soft deleted rows, which
    makes a collision look like a bug in whatever the test is actually about.
    """
    for _index in range(amount):
        serial = next(_project_identifiers)
        Project.objects.create(
            name=f"پروژه {serial}",
            identifier=f"PRJ{serial}",
            workspace=workspace,
            archived_at=timezone.now() if archived else None,
        )


def test_a_missing_flag_row_leaves_creation_open(workspace_factory):
    """The upgrade-safety branch: an unconfigured installation is unchanged."""
    workspace = workspace_factory(name="تیم بدون پرچم")
    assert project_limit_rejection(workspace) is None


def test_an_inactive_flag_row_leaves_creation_open(workspace_factory):
    """Deactivating a catalogue row is how an operator takes a gate back out."""
    workspace, flag = granted_workspace(workspace_factory)
    FeatureFlag.objects.filter(code=flag.code).update(is_active=False)
    make_projects(workspace, 10)

    assert project_limit_rejection(workspace) is None


def test_a_flag_the_plan_does_not_grant_refuses_the_creation(workspace_factory):
    workspace, flag = granted_workspace(workspace_factory)
    PlanFeatureFlag.objects.filter(feature_flag=flag).update(is_enabled=False)

    rejection = project_limit_rejection(workspace)

    assert rejection is not None
    assert rejection["code"] == FEATURE_NOT_IN_PLAN_CODE
    assert "error" in rejection


def test_a_workspace_that_switched_the_flag_off_is_refused(workspace_factory):
    """Off means off: the switch the workspace owns is the one the acceptance criterion names."""
    workspace, flag = granted_workspace(workspace_factory, switched_on=False)

    rejection = project_limit_rejection(workspace)

    assert rejection is not None
    assert rejection["code"] == FEATURE_NOT_IN_PLAN_CODE


def test_under_the_limit_the_creation_is_allowed(workspace_factory):
    workspace, _flag = granted_workspace(workspace_factory, limit=3)
    make_projects(workspace, 2)

    assert project_limit_rejection(workspace) is None


def test_at_the_limit_the_creation_is_refused_with_the_bound_and_the_usage(workspace_factory):
    workspace, _flag = granted_workspace(workspace_factory, limit=3)
    make_projects(workspace, 3)

    rejection = project_limit_rejection(workspace)

    assert rejection is not None
    assert rejection["code"] == FEATURE_LIMIT_REACHED_CODE
    assert rejection["limit"] == 3
    assert rejection["used"] == 3
    # The unit label is the flag's own Persian noun, so the operator reads
    # "پروژه" rather than a generic "limit".
    assert "پروژه" in rejection["error"]


def test_a_request_for_more_than_one_counts_the_additional_amount(workspace_factory):
    workspace, _flag = granted_workspace(workspace_factory, limit=3)
    make_projects(workspace, 2)

    assert project_limit_rejection(workspace, additional=1) is None
    assert project_limit_rejection(workspace, additional=2) is not None


def test_an_unlimited_flag_allows_any_count(workspace_factory):
    workspace, _flag = granted_workspace(workspace_factory, limit=None, limit_type="unlimited")
    make_projects(workspace, 25)

    assert project_limit_rejection(workspace) is None


def test_a_granted_number_flag_without_a_bound_refuses(workspace_factory):
    """A countable capability with no number stored cannot be gated on safely."""
    workspace, flag = granted_workspace(workspace_factory, limit=3)
    PlanFeatureFlag.objects.filter(feature_flag=flag).update(limit_value=None)

    rejection = project_limit_rejection(workspace)

    assert rejection is not None
    assert rejection["code"] == FEATURE_LIMIT_UNSET_CODE


def test_no_workspace_is_never_refused(workspace_factory):
    assert project_limit_rejection(None) is None


def test_the_usage_counts_live_projects_and_not_archived_ones(workspace_factory):
    """Archived projects are not capacity: counting them would charge for the past."""
    workspace = workspace_factory(name="تیم آرشیو")
    make_projects(workspace, 2)
    make_projects(workspace, 1, archived=True)

    assert get_project_usage(workspace) == 2


def test_the_usage_of_a_missing_workspace_is_zero():
    assert get_project_usage(None) == 0
