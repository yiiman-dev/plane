# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The session project-create endpoint, gated by the plan's project limit.

The service tests pin the decision; these pin the wiring, because a gate that is
implemented and never called is the failure this whole phase exists to stop.
Three cases, one per direction the wiring can be wrong in: refused when the plan
is exhausted, refused when the workspace switched the capability off, and open
when the instance has never configured the flag at all -- an installation that
upgrades without touching the catalogue must keep creating projects.
"""

import pytest
from rest_framework import status

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
    FEATURE_NOT_IN_PLAN_CODE,
    PROJECT_LIMIT_FLAG_CODE,
)
from plane.db.models import Project

PROJECTS_URL = "/api/workspaces/{slug}/projects/"


def grant_project_limit(workspace, limit=1, switched_on=True):
    """An active flag, a plan granting it, and the workspace subscribed to that plan."""
    flag = FeatureFlag.objects.create(
        code=PROJECT_LIMIT_FLAG_CODE,
        name="پروژه‌ها",
        limit_type="number",
        unit_label="پروژه",
    )
    plan = Plan.objects.create(code="limited", name="پلن محدود")
    PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, is_enabled=True, limit_value=limit)
    Subscription.objects.create(
        user=workspace.owner,
        workspace=workspace,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        seats=1,
        cycle=BillingCycle.MONTHLY,
    )
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=flag, is_enabled=switched_on)
    return flag


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectLimitGateApp:
    def test_creating_past_the_limit_is_refused_and_writes_nothing(self, session_client, workspace):
        grant_project_limit(workspace, limit=1)
        Project.objects.create(name="پروژه اول", identifier="P1", workspace=workspace)

        response = session_client.post(
            PROJECTS_URL.format(slug=workspace.slug),
            {"name": "پروژه دوم", "identifier": "P2"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN, response.content
        body = response.json()
        assert body["code"] == FEATURE_LIMIT_REACHED_CODE
        assert body["limit"] == 1
        assert body["used"] == 1
        assert Project.objects.filter(workspace=workspace).count() == 1

    def test_creating_under_the_limit_still_succeeds(self, session_client, workspace):
        grant_project_limit(workspace, limit=3)

        response = session_client.post(
            PROJECTS_URL.format(slug=workspace.slug),
            {"name": "پروژه اول", "identifier": "P1"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.content
        assert Project.objects.filter(workspace=workspace).count() == 1

    def test_a_workspace_that_switched_the_capability_off_is_refused(self, session_client, workspace):
        """Off means off: the workspace's own switch is the acceptance criterion."""
        grant_project_limit(workspace, limit=10, switched_on=False)

        response = session_client.post(
            PROJECTS_URL.format(slug=workspace.slug),
            {"name": "پروژه اول", "identifier": "P1"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN, response.content
        assert response.json()["code"] == FEATURE_NOT_IN_PLAN_CODE
        assert Project.objects.filter(workspace=workspace).count() == 0

    def test_an_instance_without_the_flag_row_creates_projects_as_before(self, session_client, workspace):
        """The upgrade case: no catalogue row means no gate, not a locked workspace."""
        assert FeatureFlag.objects.count() == 0

        response = session_client.post(
            PROJECTS_URL.format(slug=workspace.slug),
            {"name": "پروژه اول", "identifier": "P1"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.content
