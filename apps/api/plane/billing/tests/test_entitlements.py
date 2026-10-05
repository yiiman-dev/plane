# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Entitlement tests.

No test here opens a socket: the real invitation and acceptance routes are
exercised through the in process Django test client and the invitation email
task is stubbed out.
"""

# Python imports
from datetime import timedelta
from uuid import uuid4

# Third party imports
import pytest

# Django imports
from django.urls import reverse
from django.utils import timezone

# Module imports
from plane.app.views.workspace import invite as invite_views
from plane.billing.models import (
    FeatureFlag,
    Plan,
    PlanFeatureFlag,
    Subscription,
    SubscriptionStatus,
    WorkspaceFeatureFlag,
)
from plane.billing.services.entitlements import (
    FEATURE_NOT_IN_PLAN_CODE,
    SEAT_LIMIT_REACHED_CODE,
    SEAT_LIMIT_REACHED_MESSAGE,
    SEAT_LIMIT_REACHED_PROJECT_MESSAGE,
    check_seat_availability,
    get_seat_limit,
    get_seat_usage,
    has_feature,
    resolve_workspace_plan,
)
from plane.db.models import (
    Project,
    ProjectMember,
    ProjectMemberInvite,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceMemberInvite,
)

pytestmark = pytest.mark.django_db


def make_user(email):
    # the username column is unique, so every test user needs its own value
    return User.objects.create(
        email=email,
        username=uuid4().hex,
        first_name="Test",
        last_name="User",
    )


def make_plan(code, **kwargs):
    defaults = {"name": code.title(), "max_seats": 5, "is_active": True}
    defaults.update(kwargs)
    return Plan.objects.create(code=code, **defaults)


def make_workspace(slug, owner=None, seats=5):
    """A workspace whose owner is an active admin member."""
    owner = owner or make_user(f"{slug}-owner@example.com")
    workspace = Workspace.objects.create(name=slug, owner=owner, slug=slug)
    WorkspaceMember.objects.create(workspace=workspace, member=owner, role=20, is_active=True)
    make_plan(f"{slug}-plan", max_seats=seats)
    Subscription.objects.create(
        user=owner,
        plan=Plan.objects.get(code=f"{slug}-plan"),
        workspace=workspace,
        status=SubscriptionStatus.ACTIVE,
        starts_at=timezone.now(),
    )
    return workspace


@pytest.fixture
def no_invitation_email(monkeypatch):
    """Never talk to celery, the invitation email is irrelevant here."""
    monkeypatch.setattr(invite_views.workspace_invitation, "delay", lambda *args, **kwargs: None)


@pytest.fixture
def no_free_seat_setting(monkeypatch):
    """An unset instance configuration means unlimited, never a guessed cap."""
    monkeypatch.setattr(
        "plane.billing.services.entitlements.get_workspace_free_seat_limit",
        lambda: ("",),
    )


# ---------------------------------------------------------------------------
# plan resolution
# ---------------------------------------------------------------------------


def test_workspace_subscription_wins():
    workspace = make_workspace("resolve-workspace")
    other = make_workspace("resolve-other")
    # the owner also bought something, the workspace bound row must still win
    Subscription.objects.create(
        user=workspace.owner,
        plan=make_plan("owner-paid"),
        status=SubscriptionStatus.ACTIVE,
        starts_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=10),
    )

    assert resolve_workspace_plan(workspace).code == f"{workspace.slug}-plan"
    assert resolve_workspace_plan(other).code == f"{other.slug}-plan"


def test_owner_subscription_used_without_workspace_subscription():
    owner = make_user("owner-only@example.com")
    workspace = Workspace.objects.create(name="Owner", owner=owner, slug="owner-only")
    WorkspaceMember.objects.create(workspace=workspace, member=owner, role=20, is_active=True)
    plan = make_plan("owner-plan")
    Subscription.objects.create(
        user=owner,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        starts_at=timezone.now(),
        ends_at=timezone.now() + timedelta(days=5),
    )

    assert resolve_workspace_plan(workspace) == plan


def test_free_plan_is_the_last_resort():
    owner = make_user("free-owner@example.com")
    workspace = Workspace.objects.create(name="Free", owner=owner, slug="free-only")
    free_plan = make_plan("free", max_seats=3)

    assert resolve_workspace_plan(workspace) == free_plan
    assert get_seat_limit(workspace) == 3


def test_no_plan_at_all_is_never_locked_down(no_free_seat_setting):
    owner = make_user("noplan-owner@example.com")
    workspace = Workspace.objects.create(name="NoPlan", owner=owner, slug="no-plan")

    assert resolve_workspace_plan(workspace) is None
    assert get_seat_limit(workspace) is None


def test_expired_subscription_is_ignored(no_free_seat_setting):
    owner = make_user("expired-owner@example.com")
    workspace = Workspace.objects.create(name="Expired", owner=owner, slug="expired")
    Subscription.objects.create(
        user=owner,
        plan=make_plan("expired-plan"),
        status=SubscriptionStatus.ACTIVE,
        starts_at=timezone.now() - timedelta(days=30),
        ends_at=timezone.now() - timedelta(days=1),
    )

    assert resolve_workspace_plan(workspace) is None


# ---------------------------------------------------------------------------
# seat limit through the real invitation route
# ---------------------------------------------------------------------------


def test_invitation_below_the_seat_limit_is_accepted(client, no_invitation_email):
    workspace = make_workspace("seat-below", seats=3)
    client.force_authenticate(user=workspace.owner)

    response = client.post(
        reverse("workspace-invitations", kwargs={"slug": workspace.slug}),
        {"emails": [{"email": "newcomer@example.com", "role": 5}], "project_role": None},
        format="json",
    )

    assert response.status_code == 200, response.content.decode()
    assert WorkspaceMemberInvite.objects.filter(workspace=workspace).count() == 1
    # the owner and the new pending invitation both hold a seat
    assert get_seat_usage(workspace) == 2


def test_invitation_exactly_at_the_seat_limit_is_refused(client, no_invitation_email):
    workspace = make_workspace("seat-full", seats=2)
    WorkspaceMemberInvite.objects.create(
        workspace=workspace,
        email="pending@example.com",
        role=5,
        token="token-pending",
        created_by=workspace.owner,
    )
    client.force_authenticate(user=workspace.owner)

    response = client.post(
        reverse("workspace-invitations", kwargs={"slug": workspace.slug}),
        {"emails": [{"email": "another@example.com", "role": 5}], "project_role": None},
        format="json",
    )

    assert response.status_code == 403, response.content.decode()
    body = response.json()
    assert body["code"] == SEAT_LIMIT_REACHED_CODE
    assert body["error"] == SEAT_LIMIT_REACHED_MESSAGE
    assert body["seat_limit"] == 2
    assert body["seats_used"] == 2
    # nothing was written, the batch is refused as a whole
    assert not WorkspaceMemberInvite.objects.filter(workspace=workspace, email="another@example.com").exists()


def test_availability_check_above_the_seat_limit():
    workspace = make_workspace("seat-over", seats=2)
    WorkspaceMemberInvite.objects.create(
        workspace=workspace,
        email="pending@example.com",
        role=5,
        token="token-pending",
        created_by=workspace.owner,
    )

    allowed, reason = check_seat_availability(workspace, additional=1)

    assert allowed is False
    assert reason == SEAT_LIMIT_REACHED_MESSAGE


def test_accepting_an_invitation_is_refused_when_seats_filled_up(client):
    workspace = make_workspace("accept-full", seats=2)
    invited = make_user("acceptor@example.com")
    invite = WorkspaceMemberInvite.objects.create(
        workspace=workspace,
        email=invited.email,
        role=5,
        token="token-accept",
        created_by=workspace.owner,
    )
    # the workspace filled up after the invitation was sent
    WorkspaceMember.objects.create(
        workspace=workspace,
        member=make_user("late@example.com"),
        role=5,
        is_active=True,
    )
    client.force_authenticate(user=invited)

    response = client.post(
        reverse("workspace-join", kwargs={"slug": workspace.slug, "pk": invite.pk}),
        {"token": "token-accept", "accepted": True},
        format="json",
    )

    assert response.status_code == 403, response.content.decode()
    assert response.json()["code"] == SEAT_LIMIT_REACHED_CODE
    # the invitee never became a member
    assert not WorkspaceMember.objects.filter(workspace=workspace, member=invited).exists()


# ---------------------------------------------------------------------------
# seat limit through the real project invitation route
# ---------------------------------------------------------------------------


def make_project_invite(workspace, email, token):
    """A project and a pending project invitation addressed to ``email``."""
    project = Project.objects.create(
        name=f"Project {token}",
        identifier=token[:12].upper(),
        workspace=workspace,
    )
    invite = ProjectMemberInvite.objects.create(project=project, email=email, token=token, role=5)
    return project, invite


def test_project_invitation_is_refused_when_the_workspace_is_full(client):
    workspace = make_workspace("project-seat-full", seats=2)
    invited = make_user("project-invitee@example.com")
    project, invite = make_project_invite(workspace, invited.email, "token-project-full")
    # the workspace filled up after the project invitation was sent
    WorkspaceMember.objects.create(
        workspace=workspace,
        member=make_user("project-late@example.com"),
        role=5,
        is_active=True,
    )
    client.force_authenticate(user=invited)

    response = client.post(
        reverse(
            "project-join",
            kwargs={"slug": workspace.slug, "project_id": project.pk, "pk": invite.pk},
        ),
        {"token": "token-project-full", "accepted": True},
        format="json",
    )

    assert response.status_code == 403, response.content.decode()
    body = response.json()
    assert body["code"] == SEAT_LIMIT_REACHED_CODE
    # the message names the project invitation, the machine keys stay the same
    assert body["error"] == SEAT_LIMIT_REACHED_PROJECT_MESSAGE
    assert body["seat_limit"] == 2
    assert body["seats_used"] == 2
    # nothing was written: no workspace membership and the invitation stays open
    assert not WorkspaceMember.objects.filter(workspace=workspace, member=invited).exists()
    assert not ProjectMember.objects.filter(project=project, member=invited).exists()
    invite.refresh_from_db()
    assert invite.responded_at is None


def test_project_invitation_is_accepted_below_the_seat_limit(client):
    workspace = make_workspace("project-seat-free", seats=3)
    invited = make_user("project-accepted@example.com")
    project, invite = make_project_invite(workspace, invited.email, "token-project-ok")
    client.force_authenticate(user=invited)

    response = client.post(
        reverse(
            "project-join",
            kwargs={"slug": workspace.slug, "project_id": project.pk, "pk": invite.pk},
        ),
        {"token": "token-project-ok", "accepted": True},
        format="json",
    )

    assert response.status_code == 200, response.content.decode()
    # accepting a project invitation joins the workspace too, so it took a seat
    assert WorkspaceMember.objects.filter(workspace=workspace, member=invited, is_active=True).exists()
    assert ProjectMember.objects.filter(project=project, member=invited, is_active=True).exists()
    assert get_seat_usage(workspace) == 2


def test_declining_a_project_invitation_never_hits_the_seat_limit(client):
    workspace = make_workspace("project-seat-decline", seats=2)
    invited = make_user("project-decliner@example.com")
    project, invite = make_project_invite(workspace, invited.email, "token-project-decline")
    WorkspaceMember.objects.create(
        workspace=workspace,
        member=make_user("project-full@example.com"),
        role=5,
        is_active=True,
    )
    client.force_authenticate(user=invited)

    response = client.post(
        reverse(
            "project-join",
            kwargs={"slug": workspace.slug, "project_id": project.pk, "pk": invite.pk},
        ),
        {"token": "token-project-decline", "accepted": False},
        format="json",
    )

    assert response.status_code == 200, response.content.decode()
    # a decline costs no seat, so it is always recorded
    invite.refresh_from_db()
    assert invite.responded_at is not None
    assert invite.accepted is False
    assert not WorkspaceMember.objects.filter(workspace=workspace, member=invited).exists()


# ---------------------------------------------------------------------------
# feature flags
# ---------------------------------------------------------------------------


def make_feature(code, **kwargs):
    defaults = {"name": code, "is_active": True, "is_public": True}
    defaults.update(kwargs)
    return FeatureFlag.objects.create(code=code, **defaults)


def grant(plan, feature_flag, is_enabled=True):
    return PlanFeatureFlag.objects.create(plan=plan, feature_flag=feature_flag, is_enabled=is_enabled)


def test_granted_and_enabled_feature_is_available():
    workspace = make_workspace("feature-on", seats=5)
    plan = Plan.objects.get(code=f"{workspace.slug}-plan")
    feature_flag = make_feature("analytics")
    grant(plan, feature_flag)
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=feature_flag, is_enabled=True)

    assert has_feature(workspace, "analytics") is True


def test_feature_not_granted_by_the_plan_is_refused(client):
    workspace = make_workspace("feature-locked", seats=5)
    feature_flag = make_feature("machine-translation")
    client.force_authenticate(user=workspace.owner)

    response = client.post(
        reverse(
            "billing-workspace-feature-flag-enable",
            kwargs={"slug": workspace.slug, "code": feature_flag.code},
        ),
        {},
        format="json",
    )

    assert response.status_code == 403, response.content.decode()
    body = response.json()
    assert body["code"] == FEATURE_NOT_IN_PLAN_CODE
    assert not WorkspaceFeatureFlag.objects.filter(workspace=workspace).exists()


def test_global_flag_switch_invalidates_an_active_workspace():
    workspace = make_workspace("feature-global-off", seats=5)
    plan = Plan.objects.get(code=f"{workspace.slug}-plan")
    feature_flag = make_feature("automations")
    grant(plan, feature_flag)
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=feature_flag, is_enabled=True)
    assert has_feature(workspace, "automations") is True

    # the instance admin turns the capability off everywhere, the grant and the
    # workspace row stay untouched
    feature_flag.is_active = False
    feature_flag.save()
    assert has_feature(workspace, "automations") is False
    assert WorkspaceFeatureFlag.objects.filter(workspace=workspace, feature_flag=feature_flag, is_enabled=True).exists()
