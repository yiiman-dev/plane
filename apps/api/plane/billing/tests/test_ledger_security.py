# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Leak tests for the financial endpoints.

The permission used here must reject role 15. WorkSpaceAdminPermission
does not — it accepts role__in=[Admin, Member] — so financial data may
never be guarded by it.
"""

# Python imports
from uuid import uuid4

# Third party imports
import pytest

# Django imports

# Module imports
from plane.billing.api.permissions import WorkspaceBillingLedgerPermission
from plane.db.models import User, WorkspaceMember

pytestmark = pytest.mark.django_db


class _FakeView:
    def __init__(self, slug):
        self.workspace_slug = slug


class _ViewWithoutSlug:
    """A view that forgot to set ``workspace_slug``."""


class _FakeRequest:
    def __init__(self, user, method="GET"):
        self.user = user
        self.method = method


def test_existing_workspace_admin_permission_accepts_role_15():
    """The reason this permission exists: guard against reusing the loose one."""
    from plane.app.permissions.workspace import WorkSpaceAdminPermission

    import inspect

    source = inspect.getsource(WorkSpaceAdminPermission.has_permission)
    assert "role=Admin" not in source, "if this now filters to role 20 only, revisit whether this permission is needed"
    assert "role__in=[Admin, Member]" in source


# --- Additional coverage -------------------------------------------------
# The tripwire above only inspects source text. The tests below exercise the
# new permission against real rows so the security property itself is pinned.


def _make_user():
    """``User.email`` and ``User.username`` are both unique, so both are set."""
    unique = uuid4().hex
    return User.objects.create(
        username=f"ledger-user-{unique}",
        email=f"ledger-user-{unique}@example.com",
        first_name="Ledger",
        last_name="User",
    )


def _make_member(workspace, role, is_active=True):
    user = _make_user()
    WorkspaceMember.objects.create(
        workspace=workspace,
        member=user,
        role=role,
        is_active=is_active,
    )
    return _FakeRequest(user)


def _allows(workspace, request):
    return WorkspaceBillingLedgerPermission().has_permission(request, _FakeView(workspace.slug))


def test_admits_role_20_member(workspace_factory):
    workspace = workspace_factory(name="Admin Wallet")
    assert _allows(workspace, _make_member(workspace, role=20)) is True


def test_rejects_role_15_member(workspace_factory):
    workspace = workspace_factory(name="Member Wallet")
    assert _allows(workspace, _make_member(workspace, role=15)) is False


def test_rejects_non_member_of_the_workspace(workspace_factory):
    """An admin elsewhere must not reach this workspace's money."""
    other = workspace_factory(name="Other Wallet")
    this = workspace_factory(name="Target Wallet")
    assert _allows(this, _make_member(other, role=20)) is False


def test_rejects_inactive_admin(workspace_factory):
    workspace = workspace_factory(name="Inactive Wallet")
    assert _allows(workspace, _make_member(workspace, role=20, is_active=False)) is False


def test_rejects_anonymous_user(workspace_factory):
    from django.contrib.auth.models import AnonymousUser

    workspace = workspace_factory(name="Anonymous Wallet")
    assert _allows(workspace, _FakeRequest(AnonymousUser())) is False


def test_rejects_missing_user_without_querying(workspace_factory, django_assert_num_queries):
    """A ``user`` of ``None`` must short-circuit before any DB access.

    Asserting only the return value is vacuous: ``filter(member=None)``
    on a non-nullable FK becomes ``member__isnull=True``, which matches no
    rows, so the queryset would return ``False`` even with the guard deleted.
    The query counter is what actually pins the guard.
    """
    workspace = workspace_factory(name="No User Wallet")
    request = _FakeRequest(None)

    with django_assert_num_queries(0):
        assert WorkspaceBillingLedgerPermission().has_permission(request, _FakeView(workspace.slug)) is False


def test_rejects_role_5_guest(workspace_factory):
    workspace = workspace_factory(name="Guest Wallet")
    assert _allows(workspace, _make_member(workspace, role=5)) is False


def test_rejects_owner_without_membership_row(workspace_factory):
    """``Workspace.owner`` alone is not authority for the ledger.

    ``workspace_factory`` builds a ``Workspace`` with ``owner=`` and no
    ``WorkspaceMember`` row at all. The owner is denied. This is deliberate
    and matches ``WorkspaceOwnerPermission``, which also ignores
    ``Workspace.owner``: authority for this permission is an active role-20
    ``WorkspaceMember`` row and nothing else.
    """
    workspace = workspace_factory(name="Ownerless Membership Wallet")
    assert workspace.owner is not None
    assert not WorkspaceMember.objects.filter(workspace=workspace).exists()
    assert _allows(workspace, _FakeRequest(workspace.owner)) is False


def test_rejects_view_without_workspace_slug(workspace_factory, django_assert_num_queries):
    """A view that omits ``workspace_slug`` is denied, not a 500."""
    workspace = workspace_factory(name="No Slug Wallet")
    request = _make_member(workspace, role=20)

    with django_assert_num_queries(0):
        allowed = WorkspaceBillingLedgerPermission().has_permission(request, _ViewWithoutSlug())

    assert allowed is False
