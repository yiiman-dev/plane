# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The public API project-create endpoint, gated by the same plan limit.

An API token must not be a way around a limit the web app enforces. These tests
exist because the two create paths are separate views: implementing the gate in
one and not the other would leave a documented limit that any integrator can
ignore by calling the other URL.
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
from plane.billing.services.entitlements import FEATURE_LIMIT_REACHED_CODE, PROJECT_LIMIT_FLAG_CODE
from plane.db.models import Project

PROJECTS_URL = "/api/v1/workspaces/{slug}/projects/"


def grant_project_limit(workspace, limit=1):
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
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=flag, is_enabled=True)
    return flag


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectLimitGatePublicAPI:
    def test_an_api_token_cannot_create_past_the_limit(self, api_key_client, workspace):
        grant_project_limit(workspace, limit=1)
        Project.objects.create(name="پروژه اول", identifier="P1", workspace=workspace)

        response = api_key_client.post(
            PROJECTS_URL.format(slug=workspace.slug),
            {"name": "پروژه دوم", "identifier": "P2"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN, response.content
        assert response.json()["code"] == FEATURE_LIMIT_REACHED_CODE
        assert Project.objects.filter(workspace=workspace).count() == 1

    def test_creating_under_the_limit_still_succeeds(self, api_key_client, workspace):
        grant_project_limit(workspace, limit=3)

        response = api_key_client.post(
            PROJECTS_URL.format(slug=workspace.slug),
            {"name": "پروژه اول", "identifier": "P1"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.content
        assert Project.objects.filter(workspace=workspace).count() == 1

    def test_an_instance_without_the_flag_row_creates_projects_as_before(self, api_key_client, workspace):
        assert FeatureFlag.objects.count() == 0

        response = api_key_client.post(
            PROJECTS_URL.format(slug=workspace.slug),
            {"name": "پروژه اول", "identifier": "P1"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED, response.content
