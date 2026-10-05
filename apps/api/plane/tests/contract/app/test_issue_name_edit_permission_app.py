# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for work item (``Issue``) title edit permissions.

Only workspace / project admins may rename an existing work item. Members keep
every other field editable and keep the title fully editable while creating a
new work item. The rule is enforced server side by
``plane.utils.issue_name_lock.get_issue_name_edit_error`` and covered here on
the app endpoint (``IssueViewSet``) for PATCH and PUT.
"""

from uuid import uuid4

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import Issue, Project, ProjectMember, User, WorkspaceMember
from plane.utils.error_codes import ERROR_CODES

LIST_CREATE_URL = "/api/workspaces/{slug}/projects/{project_id}/issues/"
DETAIL_URL = "/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/"

ROLE_ADMIN = 20
ROLE_MEMBER = 15
ROLE_GUEST = 5


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Title Lock Project",
        identifier="TLP",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(
        project=project,
        member=create_user,
        workspace=workspace,
        role=ROLE_ADMIN,
    )
    return project


def _make_user(workspace, prefix, role, project=None):
    unique_id = uuid4().hex[:8]
    user = User.objects.create(
        email=f"{prefix}-{unique_id}@plane.so",
        username=f"{prefix}_{unique_id}",
        first_name=prefix.capitalize(),
        last_name="User",
    )
    user.set_password("test-password")
    user.save()
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=role)
    if project is not None:
        ProjectMember.objects.create(
            project=project,
            member=user,
            workspace=workspace,
            role=role,
        )
    return user


@pytest.fixture
def member_user(db, workspace, project):
    """An active project MEMBER (role=15)."""
    return _make_user(workspace, "member", ROLE_MEMBER, project=project)


@pytest.fixture
def admin_user(db, workspace, project):
    """An active project ADMIN (role=20)."""
    return _make_user(workspace, "admin", ROLE_ADMIN, project=project)


@pytest.fixture
def guest_creator(db, workspace, project):
    """An active project GUEST (role=5)."""
    return _make_user(workspace, "guest", ROLE_GUEST, project=project)


def _client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def member_client(member_user):
    return _client_for(member_user)


@pytest.fixture
def admin_client(admin_user):
    return _client_for(admin_user)


@pytest.fixture
def guest_creator_client(guest_creator):
    return _client_for(guest_creator)


@pytest.fixture
def issue(db, workspace, project, create_user):
    issue = Issue(name="Original title", project=project, workspace=workspace)
    issue.save(created_by_id=create_user.id)
    return issue


@pytest.fixture
def guest_owned_issue(db, workspace, project, guest_creator):
    issue = Issue(name="Guest title", project=project, workspace=workspace)
    issue.save(created_by_id=guest_creator.id)
    return issue


@pytest.mark.contract
class TestIssueTitleEditPermission:
    @pytest.mark.django_db
    def test_member_cannot_patch_title(self, member_client, workspace, project, issue):
        url = DETAIL_URL.format(slug=workspace.slug, project_id=project.id, issue_id=issue.id)

        response = member_client.patch(url, {"name": "Member renamed"}, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        assert response.data["error_code"] == ERROR_CODES["ISSUE_NAME_EDIT_NOT_ALLOWED"]
        issue.refresh_from_db()
        assert issue.name == "Original title"

    @pytest.mark.django_db
    def test_member_cannot_put_title(self, member_client, workspace, project, issue):
        url = DETAIL_URL.format(slug=workspace.slug, project_id=project.id, issue_id=issue.id)

        response = member_client.put(
            url,
            {"name": "Member renamed", "description_html": "<p>body</p>"},
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        issue.refresh_from_db()
        assert issue.name == "Original title"

    @pytest.mark.django_db
    def test_member_can_patch_other_fields(self, member_client, workspace, project, issue):
        url = DETAIL_URL.format(slug=workspace.slug, project_id=project.id, issue_id=issue.id)

        response = member_client.patch(url, {"description_html": "<p>updated by member</p>"}, format="json")

        assert response.status_code not in (status.HTTP_403_FORBIDDEN,), (
            f"Member was blocked from a non-title update: {getattr(response, 'data', None)!r}"
        )
        issue.refresh_from_db()
        assert issue.description_html == "<p>updated by member</p>"

    @pytest.mark.django_db
    def test_member_patch_with_unchanged_title_is_allowed(self, member_client, workspace, project, issue):
        """A client round-tripping the current title is not a rename."""
        url = DETAIL_URL.format(slug=workspace.slug, project_id=project.id, issue_id=issue.id)

        response = member_client.patch(
            url,
            {"name": issue.name, "description_html": "<p>still fine</p>"},
            format="json",
        )

        assert response.status_code != status.HTTP_403_FORBIDDEN, (
            f"Unchanged title was rejected: {getattr(response, 'data', None)!r}"
        )

    @pytest.mark.django_db
    def test_member_can_create_issue_with_title(self, member_client, workspace, project):
        url = LIST_CREATE_URL.format(slug=workspace.slug, project_id=project.id)

        response = member_client.post(url, {"name": "Freshly created by member"}, format="json")

        assert response.status_code in (
            status.HTTP_200_OK,
            status.HTTP_201_CREATED,
        ), f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        assert Issue.objects.filter(name="Freshly created by member", project=project).exists()

    @pytest.mark.django_db
    def test_admin_can_patch_title(self, admin_client, workspace, project, issue):
        url = DETAIL_URL.format(slug=workspace.slug, project_id=project.id, issue_id=issue.id)

        response = admin_client.patch(url, {"name": "Admin renamed"}, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        issue.refresh_from_db()
        assert issue.name == "Admin renamed"

    @pytest.mark.django_db
    def test_workspace_admin_without_project_membership_can_patch_title(
        self, member_user, workspace, project, issue
    ):
        """Workspace admins keep the rename capability."""
        WorkspaceMember.objects.filter(workspace=workspace, member=member_user).update(role=ROLE_ADMIN)
        client = _client_for(member_user)
        url = DETAIL_URL.format(slug=workspace.slug, project_id=project.id, issue_id=issue.id)

        response = client.patch(url, {"name": "Workspace admin renamed"}, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        issue.refresh_from_db()
        assert issue.name == "Workspace admin renamed"

    @pytest.mark.django_db
    def test_guest_creator_cannot_patch_title(self, guest_creator_client, workspace, project, guest_owned_issue):
        """The creator bypass must not leak the rename permission to guests."""
        url = DETAIL_URL.format(
            slug=workspace.slug, project_id=project.id, issue_id=guest_owned_issue.id
        )

        response = guest_creator_client.patch(url, {"name": "Guest renamed"}, format="json")

        assert response.status_code == status.HTTP_403_FORBIDDEN, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        guest_owned_issue.refresh_from_db()
        assert guest_owned_issue.name == "Guest title"

    @pytest.mark.django_db
    def test_guest_creator_can_still_patch_other_fields(
        self, guest_creator_client, workspace, project, guest_owned_issue
    ):
        url = DETAIL_URL.format(
            slug=workspace.slug, project_id=project.id, issue_id=guest_owned_issue.id
        )

        response = guest_creator_client.patch(
            url, {"description_html": "<p>guest edit</p>"}, format="json"
        )

        assert response.status_code != status.HTTP_403_FORBIDDEN, (
            f"Guest creator lost unrelated edit rights: {getattr(response, 'data', None)!r}"
        )
        guest_owned_issue.refresh_from_db()
        assert guest_owned_issue.description_html == "<p>guest edit</p>"