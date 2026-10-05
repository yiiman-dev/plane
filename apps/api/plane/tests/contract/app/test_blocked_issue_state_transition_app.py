# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Contract tests for the "a blocked work item cannot be started" rule.

Plane models "blocked by" as an ``IssueRelation`` row where ``issue`` is the
blocker and ``related_issue`` is the blocked work item. The API refuses to move a
work item into a ``started`` state while any of its blockers has not reached the
``completed`` group, and the rejection is enforced on every path that changes a
state (the web app's single issue PATCH - used by the state picker, the board and
list drag & drop, the spreadsheet and the bulk operations - and the external API).

Every other destination group stays unrestricted.
"""

import pytest
from rest_framework import status

from plane.db.models import (
    Issue,
    IssueRelation,
    Project,
    ProjectMember,
    State,
    StateGroup,
)
from plane.utils.error_codes import ERROR_CODES

ISSUE_URL = (
    "/api/workspaces/{slug}/projects/{project_id}/issues/{issue_id}/"
)


def _make_issue(name, project, workspace, author):
    """Create an issue with a deterministic ``created_by``.

    ``BaseModel.save`` auto-sets ``created_by`` from the current request user
    (None/anonymous under tests), so passing ``created_by_id`` to ``save`` sets
    it explicitly.
    """
    issue = Issue(name=name, project=project, workspace=workspace)
    issue.save(created_by_id=author.id)
    return issue


def _make_state(name, group, project, workspace, is_default=False):
    state = State(
        name=name,
        group=group,
        color="#000000",
        project=project,
        workspace=workspace,
        default=is_default,
    )
    state.save()
    return state


@pytest.fixture
def project(db, workspace, create_user):
    project = Project.objects.create(
        name="Blocked Project",
        identifier="BP",
        workspace=workspace,
        created_by=create_user,
    )
    ProjectMember.objects.create(
        project=project, member=create_user, workspace=workspace, role=20
    )
    # Every real Plane project ships with states, and ``Issue.save`` copies the
    # default one onto the issue. The blocking guard reads ``issue__state``, so a
    # stateless project would make every blocker look resolved.
    _make_state("Backlog", StateGroup.BACKLOG, project, workspace, is_default=True)
    return project


@pytest.fixture
def started_state(db, project, workspace):
    return _make_state("In Progress", StateGroup.STARTED, project, workspace)


@pytest.fixture
def done_state(db, project, workspace):
    return _make_state("Done", StateGroup.COMPLETED, project, workspace)


@pytest.fixture
def backlog_state(db, project):
    """The project default state.

    ``Issue.save`` runs ``_ensure_default_state``, so every issue created in this
    module ends up in this state. The blocking guard reads ``issue__state``, so a
    project without any state at all would leave every blocker stateless and the
    guard would treat it as resolved.
    """
    return State.objects.filter(project=project, default=True).first()


@pytest.fixture
def blocked_issue(db, project, workspace, create_user):
    """The work item that carries the unresolved blocker."""
    return _make_issue("Blocked work item", project, workspace, create_user)


@pytest.fixture
def blocker_issue(db, blocked_issue, project, workspace, create_user):
    """The unresolved blocker: ``issue`` is the blocker, ``related_issue`` is blocked."""
    blocker = _make_issue("Blocker work item", project, workspace, create_user)
    IssueRelation.objects.create(
        issue=blocker,
        related_issue=blocked_issue,
        project_id=blocker.project_id,
        workspace_id=blocker.workspace_id,
        relation_type="blocked_by",
    )
    return blocker


@pytest.fixture
def unblocked_issue(db, project, workspace, create_user):
    return _make_issue("Free work item", project, workspace, create_user)


def _issue_url(workspace, project, issue):
    return ISSUE_URL.format(slug=workspace.slug, project_id=project.id, issue_id=issue.id)


@pytest.mark.contract
class TestBlockedIssueCannotBeStarted:
    """A work item blocked by unresolved work items may not enter ``started``."""

    @pytest.mark.django_db
    def test_move_to_started_rejected_with_unresolved_blocker(
        self,
        session_client,
        workspace,
        project,
        blocked_issue,
        blocker_issue,
        started_state,
        backlog_state,
    ):
        """The transition is refused, the error code is explicit, nothing is written."""
        url = _issue_url(workspace, project, blocked_issue)
        response = session_client.patch(url, {"state_id": str(started_state.id)}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        assert ERROR_CODES["ISSUE_BLOCKED_BY_UNRESOLVED"] in [
            int(code) for code in response.data["error_code"]
        ], f"Missing blocking error code: {response.data!r}"
        assert blocker_issue.name in response.data["state_id"][0], (
            f"Error message does not name the blocker: {response.data!r}"
        )
        assert [row["name"] for row in response.data["blocked_by"]] == [blocker_issue.name]

        blocked_issue.refresh_from_db()
        # The issue keeps the project default state it was created with: the
        # rejected transition must not have been persisted.
        assert blocked_issue.state_id == backlog_state.id, "State changed despite the rejection"

    @pytest.mark.django_db
    def test_move_to_started_allowed_once_every_blocker_completed(
        self,
        session_client,
        workspace,
        project,
        blocked_issue,
        blocker_issue,
        started_state,
        done_state,
    ):
        """Completing every blocker unlocks the very same transition."""
        blocker_issue.state = done_state
        blocker_issue.save()

        url = _issue_url(workspace, project, blocked_issue)
        response = session_client.patch(url, {"state_id": str(started_state.id)}, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        blocked_issue.refresh_from_db()
        assert str(blocked_issue.state_id) == str(started_state.id)

    @pytest.mark.django_db
    def test_every_other_group_stays_allowed_for_a_blocked_issue(
        self,
        session_client,
        workspace,
        project,
        blocked_issue,
        blocker_issue,
        started_state,
        backlog_state,
        done_state,
    ):
        """Only ``started`` is gated: backlog and completed moves still persist."""
        url = _issue_url(workspace, project, blocked_issue)

        response = session_client.patch(url, {"state_id": str(backlog_state.id)}, format="json")
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        blocked_issue.refresh_from_db()
        assert str(blocked_issue.state_id) == str(backlog_state.id)

        response = session_client.patch(url, {"state_id": str(done_state.id)}, format="json")
        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        blocked_issue.refresh_from_db()
        assert str(blocked_issue.state_id) == str(done_state.id)

    @pytest.mark.django_db
    def test_issue_without_blockers_can_be_started(
        self, session_client, workspace, project, unblocked_issue, started_state
    ):
        """A work item with no relations is unaffected by the rule."""
        url = _issue_url(workspace, project, unblocked_issue)
        response = session_client.patch(url, {"state_id": str(started_state.id)}, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        unblocked_issue.refresh_from_db()
        assert str(unblocked_issue.state_id) == str(started_state.id)

    @pytest.mark.django_db
    def test_soft_deleted_blocker_relation_does_not_gate_the_transition(
        self,
        session_client,
        workspace,
        project,
        blocked_issue,
        blocker_issue,
        started_state,
    ):
        """Deleting the relation removes the gate, exactly as the UI does."""
        IssueRelation.objects.filter(issue=blocker_issue, related_issue=blocked_issue).delete()

        url = _issue_url(workspace, project, blocked_issue)
        response = session_client.patch(url, {"state_id": str(started_state.id)}, format="json")

        assert response.status_code == status.HTTP_204_NO_CONTENT, (
            f"Got {response.status_code}: {getattr(response, 'data', None)!r}"
        )
        blocked_issue.refresh_from_db()
        assert str(blocked_issue.state_id) == str(started_state.id)


@pytest.mark.contract
class TestUnresolvedBlockerLookup:
    """The shared lookup resolves every unresolved blocker and ignores resolved ones."""

    @pytest.mark.django_db
    def test_only_unresolved_blockers_are_reported(
        self,
        workspace,
        project,
        blocked_issue,
        blocker_issue,
        done_state,
        create_user,
    ):
        from plane.utils.issue_blocking import get_unresolved_blockers

        other_blocker = _make_issue("Second blocker", project, workspace, create_user)
        IssueRelation.objects.create(
            issue=other_blocker,
            related_issue=blocked_issue,
            project_id=other_blocker.project_id,
            workspace_id=other_blocker.workspace_id,
            relation_type="blocked_by",
        )
        blocker_issue.state = done_state
        blocker_issue.save()

        blockers = get_unresolved_blockers([blocked_issue.id])[str(blocked_issue.id)]

        assert [blocker.name for blocker in blockers] == ["Second blocker"]
