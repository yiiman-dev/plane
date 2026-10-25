# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the public time-tracking endpoints (/api/v1).

Covers the timer lifecycle (start, pause, stop, cancel), manual logs, listing, edit and
delete, the project report filters, the project feature gate and project membership.
"""

from datetime import datetime, timezone as dt_timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    Issue,
    IssueWorklog,
    Project,
    ProjectMember,
    ProjectTimeTrackingSetting,
)
from plane.db.models.api import APIToken
from plane.tests.factories import UserFactory, WorkspaceMemberFactory

ADMIN, MEMBER = 20, 15


@pytest.fixture
def project(workspace, create_user):
    project = Project.objects.create(
        name="Time", identifier="TT", workspace=workspace, created_by=create_user, is_time_tracking_enabled=True
    )
    ProjectMember.objects.create(project=project, member=create_user, role=ADMIN, is_active=True)
    return project


@pytest.fixture
def issue(workspace, project):
    return Issue.objects.create(name="Track me", workspace=workspace, project=project)


def _base(workspace, project, issue):
    return f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/issues/{issue.id}/time-logs"


@pytest.mark.contract
@pytest.mark.django_db
class TestTimerLifecycle:
    def test_start_pause_stop_then_list_and_delete(self, api_key_client, workspace, project, issue):
        base = _base(workspace, project, issue)

        started = api_key_client.post(f"{base}/timer/start/", {"description": "coding"}, format="json")
        assert started.status_code == status.HTTP_201_CREATED, started.data
        assert started.data["is_running"] is True

        paused = api_key_client.post(f"{base}/timer/pause/", {}, format="json")
        assert paused.status_code == status.HTTP_200_OK, paused.data
        assert paused.data["is_paused"] is True and paused.data["is_running"] is False

        stopped = api_key_client.post(f"{base}/timer/stop/", {"description": "done"}, format="json")
        assert stopped.status_code == status.HTTP_200_OK, stopped.data
        assert stopped.data["end_time"] is not None
        assert stopped.data["description"] == "done"

        listed = api_key_client.get(base + "/")
        assert listed.status_code == status.HTTP_200_OK, listed.data
        assert len(listed.data["logs"]) == 1
        log_id = listed.data["logs"][0]["id"]

        deleted = api_key_client.delete(f"{base}/{log_id}/")
        assert deleted.status_code == status.HTTP_204_NO_CONTENT
        assert IssueWorklog.objects.filter(issue=issue, deleted_at__isnull=True).count() == 0

    def test_cancel_discards_running_timer(self, api_key_client, workspace, project, issue):
        base = _base(workspace, project, issue)
        assert api_key_client.post(f"{base}/timer/start/", {}, format="json").status_code == 201

        cancelled = api_key_client.post(f"{base}/timer/cancel/", {}, format="json")
        assert cancelled.status_code == status.HTTP_200_OK
        assert api_key_client.get(base + "/").data["logs"] == []

    def test_stop_without_active_timer_is_404(self, api_key_client, workspace, project, issue):
        response = api_key_client.post(f"{_base(workspace, project, issue)}/timer/stop/", {}, format="json")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_start_is_rejected_when_time_tracking_disabled(self, api_key_client, workspace, project, issue):
        ProjectTimeTrackingSetting.objects.create(project=project, workspace=workspace, is_enabled=False)

        response = api_key_client.post(f"{_base(workspace, project, issue)}/timer/start/", {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.contract
@pytest.mark.django_db
class TestManualLogs:
    def test_manual_log_from_hours_minutes_and_patch_duration(self, api_key_client, workspace, project, issue):
        base = _base(workspace, project, issue)

        created = api_key_client.post(base + "/", {"hours": 1, "minutes": 30}, format="json")
        assert created.status_code == status.HTTP_201_CREATED, created.data
        assert created.data["duration_seconds"] == 5400

        patched = api_key_client.patch(f"{base}/{created.data['id']}/", {"duration_seconds": 600}, format="json")
        assert patched.status_code == status.HTTP_200_OK, patched.data
        assert patched.data["duration_seconds"] == 600

    def test_issue_list_reports_totals(self, api_key_client, workspace, project, issue):
        base = _base(workspace, project, issue)
        api_key_client.post(base + "/", {"duration_seconds": 3600}, format="json")
        api_key_client.post(base + "/", {"duration_seconds": 1800}, format="json")

        listed = api_key_client.get(base + "/")

        assert listed.status_code == status.HTTP_200_OK
        assert listed.data["completed_duration_seconds"] == 5400
        assert len(listed.data["logs"]) == 2


@pytest.mark.contract
@pytest.mark.django_db
class TestProjectReport:
    def _log(self, issue, user, start, seconds):
        return IssueWorklog.objects.create(
            issue=issue,
            project=issue.project,
            workspace=issue.workspace,
            user=user,
            start_time=start,
            end_time=start,
            duration_seconds=seconds,
        )

    def test_report_filters_by_date_range_and_summarises(self, api_key_client, workspace, project, issue, create_user):
        self._log(issue, create_user, datetime(2026, 10, 1, 9, tzinfo=dt_timezone.utc), 3600)
        self._log(issue, create_user, datetime(2026, 10, 5, 9, tzinfo=dt_timezone.utc), 1800)
        self._log(issue, create_user, datetime(2026, 10, 20, 9, tzinfo=dt_timezone.utc), 900)
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/time-logs/"

        response = api_key_client.get(url, {"start_date": "2026-10-02", "end_date": "2026-10-10"})

        assert response.status_code == status.HTTP_200_OK, response.data
        assert len(response.data["results"]) == 1
        summary = response.data["summary"]
        assert summary["total_duration_seconds"] == 1800
        assert summary["by_date"] == [{"date": "2026-10-05", "total_duration_seconds": 1800}]
        assert summary["by_user"][0]["total_duration_seconds"] == 1800

    def test_report_filters_by_user(self, api_key_client, workspace, project, issue, create_user):
        other = UserFactory()
        WorkspaceMemberFactory(workspace=workspace, member=other, role=MEMBER)
        ProjectMember.objects.create(project=project, member=other, role=MEMBER, is_active=True)
        self._log(issue, create_user, datetime(2026, 10, 1, tzinfo=dt_timezone.utc), 600)
        self._log(issue, other, datetime(2026, 10, 1, tzinfo=dt_timezone.utc), 900)
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/time-logs/"

        response = api_key_client.get(url, {"user_id": str(other.id)})

        assert response.data["summary"]["total_duration_seconds"] == 900
        assert len(response.data["results"]) == 1

    def test_report_rejects_bad_date(self, api_key_client, workspace, project):
        url = f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/time-logs/"

        response = api_key_client.get(url, {"start_date": "01/10/2026"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_non_member_is_refused(self, workspace, project):
        outsider = UserFactory()
        WorkspaceMemberFactory(workspace=workspace, member=outsider, role=MEMBER)
        client = APIClient()
        client.credentials(HTTP_X_API_KEY=APIToken.objects.create(user=outsider).token)

        response = client.get(f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/time-logs/")

        assert response.status_code == status.HTTP_403_FORBIDDEN
