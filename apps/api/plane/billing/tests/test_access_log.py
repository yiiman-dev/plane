# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Every instance-admin read of a tenant wallet or ledger leaves an audit row."""

# Python imports
from uuid import uuid4

# Third party imports
import pytest

# Django imports
from django.contrib.auth.models import AnonymousUser

# Module imports
from plane.billing.models import BillingAccessLog
from plane.billing.services import ledger, wallet
from plane.db.models import User, WorkspaceMember


@pytest.fixture
def funded_workspace(workspace_factory):
    """A workspace credited once by hand.

    Local rather than imported: ``test_ledger_security.py`` owns a fixture of
    this name with its own ``internal_admin`` dependency, and a fixture cannot
    be imported across test modules without dragging that dependency along.
    """
    unique = uuid4().hex
    operator = User.objects.create(
        username=f"log-internal-admin-{unique}",
        email=f"log-internal-admin-{unique}@example.com",
        first_name="Internal",
        last_name="Operator",
    )
    ws = workspace_factory(name="تیم حسابرسی", slug=f"audit-team-{unique[:8]}")
    wallet.grant_from_admin(
        workspace=ws,
        amount_toman=400_000,
        description="اعتبار داخلی برای تیم حسابرسی",
        created_by=operator,
        idempotency_key=f"audit-{unique}",
    )
    return ws, operator


def test_reading_a_wallet_as_admin_writes_one_row(client, funded_workspace, instance_admin):
    workspace, _operator = funded_workspace
    client.force_login(instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/")

    assert response.status_code == 200
    row = BillingAccessLog.objects.get()
    assert row.viewer_id == instance_admin.pk
    assert row.workspace_id == workspace.pk
    assert row.view == BillingAccessLog.VIEW_WALLET


def test_reading_the_ledger_as_admin_writes_one_row(client, funded_workspace, instance_admin):
    workspace, _operator = funded_workspace
    client.force_login(instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/ledger/")

    assert response.status_code == 200
    assert BillingAccessLog.objects.get().view == BillingAccessLog.VIEW_LEDGER


def test_every_repeated_read_is_recorded(client, funded_workspace, instance_admin):
    """A log that collapses repeats cannot show a pattern."""
    workspace, _operator = funded_workspace
    client.force_login(instance_admin)

    for _ in range(3):
        client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/ledger/")

    assert BillingAccessLog.objects.filter(view=BillingAccessLog.VIEW_LEDGER).count() == 3


def test_the_row_records_where_the_read_came_from(client, funded_workspace, instance_admin):
    workspace, _operator = funded_workspace
    client.force_login(instance_admin)

    client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/", HTTP_USER_AGENT="plane-ops-console/1.0")

    row = BillingAccessLog.objects.get()
    assert row.user_agent != ""
    assert row.user_agent == "plane-ops-console/1.0"


def test_a_workspace_admin_reading_their_own_ledger_writes_no_row(client, workspace_factory):
    """The log is an operator accountability record. A tenant's own read is not an operator event."""
    unique = uuid4().hex
    workspace = workspace_factory(name="تیم خودش")
    admin = User.objects.create(username=f"own-admin-{unique}", email=f"own-admin-{unique}@example.com")
    WorkspaceMember.objects.create(workspace=workspace, member=admin, role=20)
    client.force_login(admin)

    response = client.get(f"/api/billing/workspaces/{workspace.slug}/billing/ledger/")

    assert response.status_code == 200
    assert BillingAccessLog.objects.count() == 0


def test_a_plain_user_is_refused_and_writes_no_row(client, funded_workspace):
    """The canary has to hold on the log too, not only on the response."""
    unique = uuid4().hex
    workspace, _operator = funded_workspace
    plain = User.objects.create(username=f"plain-{unique}", email=f"plain-{unique}@example.com")
    client.force_login(plain)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/")

    assert response.status_code in (401, 403)
    assert BillingAccessLog.objects.count() == 0


def test_an_anonymous_read_writes_no_row(client, funded_workspace):
    workspace, _operator = funded_workspace

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/")

    assert response.status_code in (401, 403)
    assert BillingAccessLog.objects.count() == 0


def test_the_service_returns_none_for_a_request_with_no_user(db, workspace_factory):
    """An anonymous request must not leave a row attributing a read to nobody."""
    workspace = workspace_factory(name="تیم بی‌درخواست")

    class FakeRequest:
        user = None
        META: dict = {}

    row = ledger.record_admin_read(workspace=workspace, view=BillingAccessLog.VIEW_WALLET, request=FakeRequest())
    assert row is None
    assert BillingAccessLog.objects.count() == 0


def test_the_service_returns_none_for_an_anonymous_user_object(db, workspace_factory):
    """The real anonymous object is not the same case as ``user is None``.

    ``AnonymousUser.is_authenticated`` is ``False`` rather than missing, so this
    is the branch the anonymous HTTP request above actually reaches once the
    permission has let the request past authentication.
    """
    workspace = workspace_factory(name="تیم ناشناس")

    class AnonymousRequest:
        user = AnonymousUser()
        META: dict = {}

    assert (
        ledger.record_admin_read(workspace=workspace, view=BillingAccessLog.VIEW_WALLET, request=AnonymousRequest())
        is None
    )
    assert BillingAccessLog.objects.count() == 0


def test_the_service_survives_a_request_object_with_no_meta(db, workspace_factory, instance_admin):
    """Not every caller is a Django request. A missing META must not be an AttributeError."""
    workspace = workspace_factory(name="تیم حداقلی")

    class MinimalRequest:
        user = instance_admin

    # ``User`` inherits ``AbstractBaseUser.is_authenticated``, a read-only
    # property that is already ``True``. Assigning to it raises
    # ``AttributeError: property ... has no setter``, so the fixture value is
    # asserted instead of being forced.
    assert MinimalRequest.user.is_authenticated is True
    ledger.record_admin_read(workspace=workspace, view=BillingAccessLog.VIEW_LEDGER, request=MinimalRequest())

    row = BillingAccessLog.objects.get()
    assert row.viewer_id == instance_admin.pk
    assert row.user_agent == ""


def test_a_broken_audit_does_not_break_the_read(db, workspace_factory, instance_admin, monkeypatch):
    """The docstring promises the audit never raises. This is what proves it.

    Without the try/except a database error here escapes as a 500 on a read the
    operator is entitled to, and the operator cannot tell a failed audit from a
    successful read -- which is the exact failure the audit table exists to
    prevent.
    """
    from plane.billing.services import ledger as ledger_service

    workspace = workspace_factory(name="تیم لاگ خراب")

    def explode(*args, **kwargs):
        raise RuntimeError("audit table unavailable")

    monkeypatch.setattr(ledger_service.BillingAccessLog.objects, "create", explode)

    class AuthenticatedRequest:
        user = instance_admin
        META: dict = {}

    # Must not raise.
    result = ledger_service.record_admin_read(
        workspace=workspace, view=BillingAccessLog.VIEW_WALLET, request=AuthenticatedRequest()
    )

    assert result is None
