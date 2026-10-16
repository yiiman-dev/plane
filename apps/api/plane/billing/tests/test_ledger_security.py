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
from plane.billing.tests.conftest import force_instance_admin_login
from plane.billing.api.permissions import WorkspaceBillingLedgerPermission
from plane.billing.models import LedgerEntry, LedgerSource
from plane.billing.services import ledger, money, wallet
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


# --- Task 5: the ledger read side and its two projections ---------------
#
# The permission above decides WHO may ask. These tests decide WHAT comes
# back once they have asked, which is the half a permission class cannot
# enforce: an instance admin and a workspace admin both hold authority, and
# they must not receive the same projection.


@pytest.fixture
def internal_admin():
    """An operator who writes the entries.

    Not the ``instance_admin`` fixture: that user is the *reader* under test,
    and reusing one row for the writer would mean the actor hidden from the
    workspace admin is the same identity the test asserts against.
    """
    unique = uuid4().hex
    return User.objects.create(
        username=f"internal-admin-{unique}",
        email=f"internal-admin-{unique}@example.com",
        first_name="Internal",
        last_name="Operator",
    )


@pytest.fixture
def funded_workspace(workspace_factory, internal_admin):
    """A workspace credited once by hand, with the operator's note on it."""
    ws = workspace_factory(name="تیم نشت", slug=f"leak-team-{uuid4().hex[:8]}")
    wallet.grant_from_admin(
        workspace=ws,
        amount_toman=400_000,
        description="اعتبار داخلی محرمانه برای شرکت نمونه",
        created_by=internal_admin,
        idempotency_key="leak-1",
    )
    return ws, internal_admin


def test_workspace_projection_hides_the_actor_and_internal_accounts(funded_workspace):
    from plane.billing.api.serializers import WorkspaceLedgerEntrySerializer

    ws, _operator = funded_workspace
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")
    data = WorkspaceLedgerEntrySerializer(entry).data

    assert "created_by" not in data
    assert "invoice" not in data
    assert "transaction" not in data
    assert "debit_account" not in data
    assert "credit_account" not in data
    # the amount is the workspace's own business and stays visible
    assert data["amount_toman"] == 400_000


def test_workspace_projection_shows_no_raw_enum_value(funded_workspace):
    """``source`` is a machine value; the workspace admin gets a label instead.

    Asserted rather than assumed: the projection is the only place the raw
    ``LedgerSource`` member could reach a tenant, and every member is checked
    so that adding a source later fails here rather than shipping.
    """
    from plane.billing.api.serializers import WorkspaceLedgerEntrySerializer

    entry = LedgerEntry.objects.get(idempotency_key="leak-1")
    data = WorkspaceLedgerEntrySerializer(entry).data

    assert "source" not in data
    raw_values = {value for value, _label in LedgerSource.choices}
    assert data["source_label"] not in raw_values
    assert data["source_label"] == ledger.PUBLIC_SOURCE_LABELS[LedgerSource.ADMIN_GRANT]


def test_workspace_projection_does_not_repeat_the_internal_description(funded_workspace):
    from plane.billing.api.serializers import WorkspaceLedgerEntrySerializer

    ws, _operator = funded_workspace
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")

    data = WorkspaceLedgerEntrySerializer(entry).data

    assert "محرمانه" not in data["description"]
    assert data["description"] == ledger.PUBLIC_SOURCE_LABELS[LedgerSource.ADMIN_GRANT]


def test_workspace_projection_keeps_the_owners_own_descriptions(funded_workspace):
    """Only ADMIN_GRANT is redacted.

    A charge description is written about the workspace's own SMS log and a
    hold description is the answer the owner is owed, so over-redacting would
    hide the customer's own history behind a generic label. Every non-internal
    source keeps its description.
    """
    from plane.billing.api.serializers import WorkspaceLedgerEntrySerializer

    ws, _operator = funded_workspace
    charge = wallet.charge_sms(workspace=ws, amount_toman=1_000, log_id=uuid4().hex, idempotency_key="leak-sms-1")

    data = WorkspaceLedgerEntrySerializer(charge).data

    assert data["description"] == charge.description
    assert charge.description != ledger.PUBLIC_SOURCE_LABELS[LedgerSource.SMS_CHARGE]


def test_admin_projection_keeps_the_internal_detail(funded_workspace):
    from plane.billing.api.serializers import AdminLedgerEntrySerializer

    ws, operator = funded_workspace
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")

    data = AdminLedgerEntrySerializer(entry).data

    assert "محرمانه" in data["description"]
    assert data["created_by"]["id"] == str(operator.pk)
    # the instance admin also gets the legs, the links and the machine key
    assert data["debit_account"] is not None
    assert data["credit_account"] is not None
    assert data["idempotency_key"] == "leak-1"


def test_workspace_entries_queryset_never_spans_workspaces(funded_workspace, workspace_factory, internal_admin):
    ws, _operator = funded_workspace
    other = workspace_factory(name="تیم دیگر", slug=f"other-team-{uuid4().hex[:8]}")
    wallet.grant_from_admin(
        workspace=other,
        amount_toman=999_000,
        description="اعتبار تیم دیگر که نباید دیده شود",
        created_by=internal_admin,
        idempotency_key="leak-2",
    )

    codes = set(ledger.workspace_entries(ws).values_list("idempotency_key", flat=True))
    assert codes == {"leak-1"}


def test_ledger_module_has_no_scope_parameter():
    """Scope comes from the queryset the caller built, never from a parameter.

    ``source`` is allowed and is keyword-only: it can only narrow the one
    workspace already pinned by the positional argument, never widen it.
    Anything that could WIDEN the result set is the defect this guards.
    """
    import inspect

    signature = inspect.signature(ledger.workspace_entries)
    assert list(signature.parameters) == ["workspace", "source"]
    # source is keyword-only, so no positional call can smuggle one in
    assert signature.parameters["source"].kind is inspect.Parameter.KEYWORD_ONLY

    # A widening parameter would have to be one that selects tenants.
    for name, parameter in signature.parameters.items():
        assert "workspace" not in name or name == "workspace", f"{name} could widen the scope"


def test_all_entries_reaches_every_workspace(funded_workspace, workspace_factory, internal_admin):
    """The instance-wide read is a separate function, not a flag on the other one."""
    ws, _operator = funded_workspace
    other = workspace_factory(name="تیم دیگر", slug=f"other-team-{uuid4().hex[:8]}")
    wallet.grant_from_admin(
        workspace=other,
        amount_toman=999_000,
        description="اعتبار تیم دیگر",
        created_by=internal_admin,
        idempotency_key="leak-2",
    )

    codes = set(ledger.all_entries().values_list("idempotency_key", flat=True))
    assert codes == {"leak-1", "leak-2"}


def test_entries_are_ordered_newest_first(funded_workspace):
    """A statement read top to bottom must run backwards in time."""
    from datetime import timedelta

    from django.utils import timezone

    ws, operator = funded_workspace
    second = wallet.grant_from_admin(
        workspace=ws,
        amount_toman=5_000,
        description="اعتبار دوم برای تست",
        created_by=operator,
        idempotency_key="leak-3",
    )
    # ``created_at`` is auto-set on insert, so order it explicitly rather than
    # trusting two inserts to land on distinguishable microsecond timestamps.
    LedgerEntry.objects.filter(pk=second.pk).update(created_at=timezone.now() + timedelta(minutes=5))

    entries = list(ledger.workspace_entries(ws))
    assert [e.idempotency_key for e in entries] == ["leak-3", "leak-1"]


def test_public_description_never_leaks_the_grant_note_for_any_internal_source(funded_workspace):
    """The redaction is driven by the source, not by the text.

    A grant note that happens to omit the word "محرمانه" is still a grant
    note, so the assertion is on the function's contract rather than on the
    sample string.
    """
    ws, operator = funded_workspace
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")

    assert ledger.public_description(entry) == ledger.PUBLIC_SOURCE_LABELS[LedgerSource.ADMIN_GRANT]
    assert "اعتبار داخلی" not in ledger.public_description(entry)


def test_public_source_label_covers_every_source():
    """A source added later must not reach a tenant as a raw enum member."""
    missing = [value for value, _label in LedgerSource.choices if value not in ledger.PUBLIC_SOURCE_LABELS]
    assert missing == []


def test_workspace_entries_returns_a_queryset_a_view_can_filter(funded_workspace):
    """The returned object must stay a queryset, not a list.

    A list here would silently disable pagination in the view that consumes it.
    """
    from django.db.models import QuerySet

    ws, _operator = funded_workspace
    assert isinstance(ledger.workspace_entries(ws), QuerySet)


def test_wallet_serializer_reports_the_balance(workspace_factory):
    from plane.billing.api.serializers import WalletSerializer
    from plane.billing.models import Wallet

    ws = workspace_factory(name="Wallet Balance")
    wallet.grant_from_admin(
        workspace=ws,
        amount_toman=400_000,
        description="اعتبار برای تست موجودی",
        created_by=None,
        idempotency_key="leak-wallet-1",
    )

    data = WalletSerializer(Wallet.objects.get(workspace=ws)).data

    assert data["balance_toman"] == 400_000
    assert data["hold_balance_toman"] == 0
    assert data["workspace_slug"] == ws.slug


def test_wallet_serializer_separates_the_hold_balance(workspace_factory):
    """Money under a hold is not spendable, and the projection says so."""
    from plane.billing.api.serializers import WalletSerializer
    from plane.billing.models import Wallet

    ws = workspace_factory(name="Wallet Hold")
    wallet.grant_from_admin(
        workspace=ws,
        amount_toman=400_000,
        description="اعتبار برای تست قفل",
        created_by=None,
        idempotency_key="leak-wallet-2",
    )
    wallet.hold_funds(
        workspace=ws,
        amount_toman=120_000,
        description="نگهداری تا تایید پرداخت",
        idempotency_key="leak-hold-1",
    )

    data = WalletSerializer(Wallet.objects.get(workspace=ws)).data

    assert data["balance_toman"] == 280_000
    assert data["hold_balance_toman"] == 120_000


def test_grant_serializer_refuses_a_zero_amount():
    from plane.billing.api.serializers import WalletGrantSerializer

    serializer = WalletGrantSerializer(data={"amount_toman": 0, "description": "یک توضیح کافی بلند"})
    assert serializer.is_valid() is False
    assert "amount_toman" in serializer.errors


def test_grant_serializer_refuses_a_typing_of_a_description():
    from plane.billing.api.serializers import WalletGrantSerializer

    serializer = WalletGrantSerializer(data={"amount_toman": 1000, "description": "کوتاه"})
    assert serializer.is_valid() is False
    assert "description" in serializer.errors


def test_grant_serializer_accepts_a_real_grant():
    from plane.billing.api.serializers import WalletGrantSerializer

    serializer = WalletGrantSerializer(data={"amount_toman": 1000, "description": "  اعتبار جبران خطای سیستم  "})
    assert serializer.is_valid() is True, serializer.errors
    # stripped, so the note stored on the entry has no stray whitespace
    assert serializer.validated_data["description"] == "اعتبار جبران خطای سیستم"


# --- a grant reversal's operator note must not reach the tenant -------------
# ``revoke_grant`` books under LedgerSource.GRANT_REVERSAL, not REFUND,
# precisely so the redaction in ledger.public_description can catch it.


@pytest.fixture
def reversed_grant_workspace(workspace_factory):
    from plane.db.models import User

    workspace = workspace_factory(name="تیم ابطال")
    admin = User.objects.create(email="revoker@example.com", username="revoker", first_name="Revoke", last_name="Admin")
    original = wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=300_000,
        description="اعتبار اولیه با یادداشت کاملاً داخلی",
        created_by=admin,
        idempotency_key="rev-setup",
    )
    wallet.revoke_grant(
        workspace=workspace,
        entry=original,
        description="ابطال اشتباه ادمین، این یادداشت داخلی است",
        created_by=admin,
        idempotency_key="rev-reversal",
    )
    return workspace


def test_a_grant_reversals_operator_note_never_reaches_the_tenant(reversed_grant_workspace):
    from plane.billing.api.serializers import WorkspaceLedgerEntrySerializer

    entry = LedgerEntry.objects.get(idempotency_key="rev-reversal")
    body = WorkspaceLedgerEntrySerializer(entry).data

    assert entry.source == "grant_reversal"
    assert "محرمانه" not in body["description"]
    assert "داخلی" not in body["description"]


def test_a_grant_reversal_shows_the_tenant_a_public_label(reversed_grant_workspace):
    from plane.billing.api.serializers import WorkspaceLedgerEntrySerializer

    entry = LedgerEntry.objects.get(idempotency_key="rev-reversal")
    body = WorkspaceLedgerEntrySerializer(entry).data

    assert body["description"] == "ابطال اعتبار توسط مدیریت سامانه"


def test_a_payment_refund_reference_does_reach_the_tenant(reversed_grant_workspace):
    """The payer owns this reference. Only admin-written notes are internal."""
    from plane.billing.api.serializers import WorkspaceLedgerEntrySerializer

    wallet.refund_to_spendable(
        workspace=reversed_grant_workspace,
        amount_toman=50_000,
        reason="بازگشت وجه به دلیل انصراف از خرید",
        reference="payping-ref-7788",
        idempotency_key="ref-visible",
    )
    entry = LedgerEntry.objects.get(idempotency_key="ref-visible")
    body = WorkspaceLedgerEntrySerializer(entry).data

    assert "payping-ref-7788" in body["description"]


def test_the_admin_projection_still_shows_the_internal_note(reversed_grant_workspace):
    from plane.billing.api.serializers import AdminLedgerEntrySerializer

    entry = LedgerEntry.objects.get(idempotency_key="rev-reversal")
    body = AdminLedgerEntrySerializer(entry).data

    assert "داخلی" in body["description"]


# --- D1: the tenant projection's field list is a deliberate contract --------


def test_the_workspace_projection_field_list_is_pinned():
    from plane.billing.api.serializers import WorkspaceLedgerEntrySerializer

    assert WorkspaceLedgerEntrySerializer.Meta.fields == [
        "id",
        "amount_toman",
        "source_label",
        "description",
        "created_at",
    ]


def test_the_admin_projection_field_list_is_pinned():
    from plane.billing.api.serializers import AdminLedgerEntrySerializer, WorkspaceLedgerEntrySerializer

    for leaked in ("created_by", "invoice", "transaction", "debit_account", "credit_account"):
        assert leaked in AdminLedgerEntrySerializer.Meta.fields
    assert "created_by" not in WorkspaceLedgerEntrySerializer.Meta.fields


# --- tenant filtering works without exposing the machine member -------------


def test_a_tenant_can_filter_by_the_persian_label_it_was_shown(reversed_grant_workspace):
    """The tenant was shown a Persian label, so that is what it filters by."""
    shown = ledger.public_source_label(LedgerEntry.objects.get(idempotency_key="rev-reversal"))
    assert shown == "ابطال اعتبار توسط مدیریت سامانه"

    rows = ledger.workspace_entries(reversed_grant_workspace, source=shown)

    assert {row.idempotency_key for row in rows} == {"rev-reversal"}


def test_a_tenant_filter_never_spans_workspaces(reversed_grant_workspace, workspace_factory):
    other = workspace_factory(name="تیم بیگانه")
    # Give the other tenant entries of its own, so a leak has somewhere to go.
    wallet.grant_from_admin(
        workspace=other,
        amount_toman=777_000,
        description="اعتبار تیم بیگانه که نباید دیده شود",
        created_by=None,
        idempotency_key="other-tenant",
    )

    rows = list(ledger.workspace_entries(reversed_grant_workspace))
    assert rows, "the fixture workspace must actually have entries for this to test anything"
    assert all(row.workspace_id == reversed_grant_workspace.pk for row in rows)
    assert "other-tenant" not in {row.idempotency_key for row in rows}
    # and the other tenant can see only its own
    assert {row.idempotency_key for row in ledger.workspace_entries(other)} == {"other-tenant"}


# --- Task 6: the HTTP layer ---------------------------------------------
#
# Everything above tested the policy in isolation. These tests drive it over
# HTTP, which is where the two endpoint families could be confused with one
# another: an instance admin and a workspace admin both hold real authority,
# so only the URL, the permission class and the serializer projection tell
# them apart.


def _user(label: str) -> User:
    """A user with both unique columns set.

    ``User.email`` and ``User.username`` are both unique and neither is
    populated by ``save()``, so a helper that omits one of them silently
    collides on the second call.
    """
    unique = uuid4().hex
    return User.objects.create(
        username=f"{label}-{unique}",
        email=f"{label}-{unique}@example.com",
        first_name=label,
        last_name="Tester",
    )


def _member(workspace, role, is_active=True):
    user = _user("member")
    WorkspaceMember.objects.create(
        workspace=workspace,
        member=user,
        role=role,
        is_active=is_active,
    )
    return user


@pytest.fixture
def funded_roles(funded_workspace):
    """A funded workspace plus one member of each interesting role."""
    ws, _operator = funded_workspace
    plain = _member(ws, role=15)
    ws_admin = _member(ws, role=20)
    return ws, plain, ws_admin


def test_role_15_member_is_refused_the_workspace_ledger(client, funded_roles):
    ws, plain, _ws_admin = funded_roles
    client.force_login(plain)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/")

    assert response.status_code == 403, response.content


def test_role_20_admin_can_read_the_workspace_ledger(client, funded_roles):
    ws, _plain, ws_admin = funded_roles
    client.force_login(ws_admin)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/")

    assert response.status_code == 200, response.content
    rows = response.json()["results"]
    assert rows and rows[0]["amount_toman"] == 400_000


def test_role_20_admin_can_read_the_workspace_wallet(client, funded_roles):
    ws, _plain, ws_admin = funded_roles
    client.force_login(ws_admin)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/wallet/")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["balance_toman"] == 400_000
    assert body["workspace_slug"] == ws.slug


def test_inactive_role_20_member_is_refused(client, funded_roles):
    ws, _plain, _ws_admin = funded_roles
    stale = _member(ws, role=20, is_active=False)
    client.force_login(stale)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/")

    assert response.status_code == 403, response.content


def test_admin_of_another_workspace_is_refused_the_ledger(client, funded_roles, workspace_factory):
    ws, _plain, _ws_admin = funded_roles
    other = workspace_factory(name="بیگانه")
    stranger = _member(other, role=20)
    client.force_login(stranger)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/")

    assert response.status_code == 403, response.content


@pytest.mark.parametrize("probe", ["scope", "workspace", "workspace_slug", "slug", "all", "instance"])
def test_query_parameters_cannot_widen_the_workspace_ledger(
    client, funded_roles, workspace_factory, internal_admin, probe
):
    """A forged scope parameter must not add a single foreign row."""
    ws, _plain, ws_admin = funded_roles

    # A second workspace with a distinctive amount, so any leak is visible.
    other = workspace_factory(name="دیگر")
    wallet.grant_from_admin(
        workspace=other,
        amount_toman=777_000,
        description="اعتبار تیم دیگر که نباید دیده شود",
        created_by=internal_admin,
        idempotency_key=f"probe-{probe}-grant",
    )
    client.force_login(ws_admin)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/", {probe: "all"})

    assert response.status_code == 200, response.content
    other_ids = set(LedgerEntry.objects.filter(workspace=other).values_list("id", flat=True))
    returned_ids = {row["id"] for row in response.json()["results"]}
    assert returned_ids.isdisjoint(other_ids), f"{probe} leaked another workspace's row"
    assert "777000" not in response.content.decode()
    assert other.slug not in response.content.decode()


def test_workspace_ledger_response_omits_internal_columns(client, funded_roles):
    ws, _plain, ws_admin = funded_roles
    client.force_login(ws_admin)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/")

    body = response.content.decode()
    assert "created_by" not in body
    assert "محرمانه" not in body


def test_workspace_wallet_response_omits_internal_columns(client, funded_roles):
    ws, _plain, ws_admin = funded_roles
    client.force_login(ws_admin)

    body = client.get(f"/api/billing/workspaces/{ws.slug}/billing/wallet/").content.decode()

    assert "idempotency_key" not in body
    assert "debit_account" not in body


def test_a_slug_that_names_no_workspace_is_a_404(client, funded_roles):
    _ws, _plain, ws_admin = funded_roles
    client.force_login(ws_admin)

    response = client.get("/api/billing/workspaces/no-such-team/billing/ledger/")

    # Not a 403 and above all not a 500: the slug resolved to nothing, and the
    # permission class denied it for the same reason. Either is honest.
    assert response.status_code in (403, 404), response.content


def test_an_anonymous_caller_reaches_no_endpoint(client, funded_roles):
    ws, _plain, _ws_admin = funded_roles

    for url in (
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/",
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/ledger/",
        f"/api/billing/workspaces/{ws.slug}/billing/ledger/",
        f"/api/billing/workspaces/{ws.slug}/billing/wallet/",
    ):
        response = client.get(url)
        assert response.status_code in (401, 403), f"{url} -> {response.status_code}"


# --- the admin family ----------------------------------------------------


def test_workspace_admin_cannot_grant_themselves_credit(client, funded_roles):
    ws, _plain, ws_admin = funded_roles
    client.force_login(ws_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 5_000_000, "description": "دور زدن سیستم با دسترسی مدیر ورک‌اسپیس"},
        content_type="application/json",
    )

    assert response.status_code in (401, 403), response.content
    # and nothing was written
    assert money.wallet_balance(ws) == 400_000


def test_plain_member_cannot_read_the_admin_wallet(client, funded_roles):
    ws, plain, _ws_admin = funded_roles
    client.force_login(plain)

    response = client.get(f"/api/billing/admin/workspaces/{ws.slug}/wallet/")

    assert response.status_code in (401, 403), response.content


def test_instance_admin_can_grant_and_the_actor_comes_from_the_session(client, funded_roles, instance_admin):
    ws, plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {
            "amount_toman": 250_000,
            "description": "اعتبار هدیهٔ آزمایشی برای تیم",
            # A forged actor. The grant's author must be the session, not this.
            "created_by": str(plain.pk),
            "workspace": str(ws.pk),
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="api-grant-1",
    )

    assert response.status_code == 201, response.content
    entry = LedgerEntry.objects.get(idempotency_key="api-grant-1")
    assert entry.created_by_id == instance_admin.pk
    assert entry.created_by_id != plain.pk
    assert money.wallet_balance(ws) == 650_000
    assert entry.workspace_id == ws.pk


def test_instance_admin_sees_the_internal_description(client, funded_roles, instance_admin):
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{ws.slug}/wallet/ledger/")

    assert response.status_code == 200, response.content
    assert "محرمانه" in response.content.decode()


def test_instance_admin_may_read_any_workspaces_wallet(client, funded_roles, workspace_factory, instance_admin):
    _ws, _plain, _ws_admin = funded_roles
    other = workspace_factory(name="تیم بیگانه برای ادمین")
    force_instance_admin_login(client, instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{other.slug}/wallet/")

    assert response.status_code == 200, response.content
    assert response.json()["balance_toman"] == 0


def test_a_forged_workspace_in_the_body_does_not_retarget_the_grant(
    client, funded_roles, workspace_factory, instance_admin
):
    """The URL names the workspace; a body naming another one is ignored.

    Not merely refused -- IGNORED, and then granted to the URL's workspace.
    A serializer that echoed the field back as an error would be one DRF
    version away from accepting it.
    """
    ws, _plain, _ws_admin = funded_roles
    other = workspace_factory(name="تیم هدف جعل")
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {
            "amount_toman": 250_000,
            "description": "اعتبار با هدف جعلی در بدنه",
            "workspace": str(other.pk),
            "workspace_slug": other.slug,
        },
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assert money.wallet_balance(ws) == 650_000
    assert money.wallet_balance(other) == 0


def test_instance_admin_grant_rejects_a_short_description(client, funded_roles, instance_admin):
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 250_000, "description": "کم"},
        content_type="application/json",
    )

    assert response.status_code == 400, response.content
    assert money.wallet_balance(ws) == 400_000


def test_instance_admin_grant_rejects_a_zero_amount(client, funded_roles, instance_admin):
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 0, "description": "توضیح کاملاً معتبر و بلند"},
        content_type="application/json",
    )

    assert response.status_code == 400, response.content


def test_instance_admin_grant_over_the_cap_is_a_conflict(client, funded_roles, instance_admin):
    from plane.billing.models import Wallet

    ws, _plain, _ws_admin = funded_roles
    Wallet.objects.filter(workspace=ws).update(admin_grant_cap_toman=100_000)
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 250_000, "description": "اعتبار بیش از سقف مجاز"},
        content_type="application/json",
    )

    assert response.status_code == 409, response.content
    assert money.wallet_balance(ws) == 400_000


def test_grant_for_a_slug_that_names_no_workspace_is_a_404(client, instance_admin):
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        "/api/billing/admin/workspaces/no-such-team/wallet/grant/",
        {"amount_toman": 250_000, "description": "اعتبار برای اسلگ ناموجود"},
        content_type="application/json",
    )

    assert response.status_code == 404, response.content


def test_a_replayed_grant_is_a_200_and_posts_once(client, funded_roles, instance_admin):
    """The idempotency key is the retry protection, so a retry must not mint twice.

    The view derives the key from the header and never pre-checks for it, so
    the second call is the SAME code path as the first. That is deliberate:
    a view-side pre-check is a second, weaker copy of the rule the service
    already applies, and it is the copy that drifted in an earlier task.
    """
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)
    payload = {"amount_toman": 250_000, "description": "اعتبار تکراری برای تست"}

    first = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="replay-1",
    )
    second = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="replay-1",
    )

    assert first.status_code == 201, first.content
    assert second.status_code == 200, second.content
    assert second.json()["id"] == first.json()["id"]
    assert money.wallet_balance(ws) == 650_000
    assert LedgerEntry.objects.filter(idempotency_key="replay-1").count() == 1


def test_the_idempotency_key_never_comes_from_the_body(client, funded_roles, instance_admin):
    """Two calls that differ only by a body key are two grants, not one."""
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)
    payload = {"amount_toman": 250_000, "description": "اعتبار با کلید در بدنه"}

    first = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {**payload, "idempotency_key": "forged"},
        content_type="application/json",
    )
    second = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {**payload, "idempotency_key": "forged"},
        content_type="application/json",
    )

    assert first.status_code == 201, first.content
    assert second.status_code == 201, second.content
    assert LedgerEntry.objects.filter(idempotency_key="forged").count() == 0
    assert money.wallet_balance(ws) == 900_000


def test_reusing_a_key_for_a_different_amount_is_a_conflict(client, funded_roles, instance_admin):
    """``money._assert_same_movement`` raising is a 409, never a 500."""
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)

    first = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 250_000, "description": "اعتبار اول با کلید مشترک"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="shared-key",
    )
    second = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 260_000, "description": "اعتبار دوم با همان کلید"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="shared-key",
    )

    assert first.status_code == 201, first.content
    assert second.status_code == 409, second.content
    assert money.wallet_balance(ws) == 650_000


def test_the_admin_ledger_is_paginated_in_the_same_envelope(client, funded_roles, instance_admin):
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{ws.slug}/wallet/ledger/")

    body = response.json()
    assert body["total_results"] == 1
    assert body["results"][0]["idempotency_key"] == "leak-1"
    assert body["results"][0]["workspace"] == ws.slug


# --- revoking a grant -----------------------------------------------------


def test_instance_admin_can_revoke_a_grant(client, funded_roles, instance_admin):
    ws, _plain, _ws_admin = funded_roles
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/revoke/",
        {"entry": str(entry.pk), "description": "ابطال اعتبار اشتباه توسط مدیر"},
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    assert money.wallet_balance(ws) == 0
    reversal = LedgerEntry.objects.get(idempotency_key=response.json()["idempotency_key"])
    assert reversal.reversal_of_id == entry.pk


def test_revoke_refuses_an_entry_from_another_workspace(client, funded_roles, workspace_factory, instance_admin):
    """The pk is resolved scoped by the workspace, so this is a 404 not a 403.

    A bare ``LedgerEntry.objects.get(pk=...)`` here would hand the service a
    foreign row; the service would then refuse it, but the refusal is a
    confused-deputy error the HTTP layer should never have created at all.
    """
    ws, _plain, _ws_admin = funded_roles
    other = workspace_factory(name="تیم بیگانه برای ابطال")
    foreign = wallet.grant_from_admin(
        workspace=other,
        amount_toman=100_000,
        description="اعتبار تیم بیگانه که نباید دست بخورد",
        created_by=None,
        idempotency_key="foreign-grant",
    )
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/revoke/",
        {"entry": str(foreign.pk), "description": "دور زدن مرز بین کیف پول‌ها"},
        content_type="application/json",
    )

    assert response.status_code == 404, response.content
    assert money.wallet_balance(other) == 100_000


def test_revoke_refuses_a_row_that_is_not_a_grant(client, funded_roles, instance_admin):
    ws, _plain, _ws_admin = funded_roles
    charge = wallet.charge_sms(workspace=ws, amount_toman=1_000, log_id="revoke-me", idempotency_key="sms-for-revoke")
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/revoke/",
        {"entry": str(charge.pk), "description": "دور زدن با یک ردیف غیر اعتبار"},
        content_type="application/json",
    )

    assert response.status_code == 409, response.content


def test_revoke_refuses_a_grant_that_was_already_reversed(client, funded_roles, instance_admin):
    ws, _plain, _ws_admin = funded_roles
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")
    force_instance_admin_login(client, instance_admin)
    wallet.revoke_grant(
        workspace=ws,
        entry=entry,
        description="ابطال اول برای آماده‌سازی تست",
        created_by=instance_admin,
        idempotency_key="revoke-setup",
    )

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/revoke/",
        {"entry": str(entry.pk), "description": "ابطال دوم همان اعتبار"},
        content_type="application/json",
    )

    assert response.status_code == 409, response.content


def test_workspace_admin_cannot_revoke(client, funded_roles):
    ws, _plain, ws_admin = funded_roles
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")
    client.force_login(ws_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/revoke/",
        {"entry": str(entry.pk), "description": "ابطال اعتبار توسط مدیر ورک‌اسپیس"},
        content_type="application/json",
    )

    assert response.status_code in (401, 403), response.content
    assert money.wallet_balance(ws) == 400_000


# --- the shape of the layer itself ----------------------------------------


def test_no_endpoint_reads_a_workspace_from_the_query_string():
    """The scope is the URL or nothing.

    Asserted against the source rather than left to the response tests: a
    view that grew a ``request.GET`` lookup would still pass every leak test
    above as long as the forged value happened to name nothing.
    """
    import inspect

    from plane.billing.api.views import wallet_views

    source = inspect.getsource(wallet_views)
    assert "request.GET" not in source
    assert "request.query_params" not in source


def test_every_workspace_endpoint_resolves_its_slug_from_the_url_kwargs():
    import inspect

    from plane.billing.api.views.wallet_views import (
        AdminWorkspaceGrantView,
        AdminWorkspaceLedgerView,
        AdminWorkspaceWalletView,
        WorkspaceLedgerView,
        WorkspaceWalletView,
    )

    for view in (
        AdminWorkspaceWalletView,
        AdminWorkspaceLedgerView,
        AdminWorkspaceGrantView,
        WorkspaceLedgerView,
        WorkspaceWalletView,
    ):
        assert isinstance(inspect.getattr_static(view, "workspace_slug"), property), (
            f"{view.__name__} must expose workspace_slug for the permission class to read"
        )


def test_the_two_families_use_different_permissions():
    from plane.billing.api.permissions import WorkspaceBillingLedgerPermission
    from plane.billing.api.views.wallet_views import (
        AdminWorkspaceGrantView,
        AdminWorkspaceLedgerView,
        AdminWorkspaceWalletView,
        WorkspaceLedgerView,
        WorkspaceWalletView,
    )
    from plane.license.api.permissions import InstanceAdminPermission

    for view in (AdminWorkspaceWalletView, AdminWorkspaceLedgerView, AdminWorkspaceGrantView):
        assert view.permission_classes == [InstanceAdminPermission], view.__name__
    for view in (WorkspaceLedgerView, WorkspaceWalletView):
        assert view.permission_classes == [WorkspaceBillingLedgerPermission], view.__name__


def test_the_workspace_ledger_is_not_guarded_by_the_loose_admin_permission():
    """``WorkSpaceAdminPermission`` admits role 15, so it may not appear here."""
    from plane.app.permissions.workspace import WorkSpaceAdminPermission
    from plane.billing.api.views.wallet_views import WorkspaceLedgerView, WorkspaceWalletView

    for view in (WorkspaceLedgerView, WorkspaceWalletView):
        assert WorkSpaceAdminPermission not in view.permission_classes, view.__name__


# --- fix round 1: the replay signal, and the exception taxonomy -----------


def test_the_view_never_compares_timestamps_to_detect_a_replay():
    """The 200/201 decision may not be a wall-clock comparison.

    The earlier version read ``entry.created_at < started_at``, which is wrong
    in both directions: a clock stepping backwards between the two reads makes
    a genuinely new entry look like a replay (200 for a 201), and an app host
    running ahead of the database host makes a replay look fresh (201 for a
    200). Neither is reproducible in CI, so neither would ever have been
    caught by a response test -- which is the reason the view source is
    asserted here instead.

    The service must state the fact, so the flag is checked on the way up too:
    ``grant_from_admin`` and ``revoke_grant`` keep their plain signatures for
    the other four callers, and the ``_with_outcome`` spellings are what the
    views read.
    """
    import inspect

    from plane.billing.api.views import wallet_views

    source = inspect.getsource(wallet_views)
    assert "started_at" not in source, "the view must not timestamp-compare; the service tells it the outcome"
    assert "timezone.now" not in source
    assert ".created_at <" not in source

    # and the signal really does exist at the service boundary
    assert hasattr(wallet_service := wallet_views.wallet_service, "grant_from_admin_with_outcome")
    assert hasattr(wallet_service, "revoke_grant_with_outcome")
    assert hasattr(money, "post_entry_with_outcome")


def test_the_service_states_the_replay_fact_not_a_timestamp(client, funded_roles, instance_admin):
    """200 on a replay, 201 on a fresh post -- from the service's own word."""
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)
    payload = {"amount_toman": 250_000, "description": "اعتبار برای آزمون سیگنال بازپخش"}

    first = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="signal-1",
    )
    second = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="signal-1",
    )
    third = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="signal-2",
    )

    assert first.status_code == 201, first.content
    assert second.status_code == 200, second.content
    assert third.status_code == 201, third.content
    assert second.json()["id"] == first.json()["id"]
    assert third.json()["id"] != first.json()["id"]


def test_the_replay_flag_is_true_on_the_second_call_and_false_on_the_first(funded_workspace):
    """The signal is asserted at the service, not only through the status code."""
    ws, _operator = funded_workspace

    first_entry, first_replayed = wallet.grant_from_admin_with_outcome(
        workspace=ws,
        amount_toman=10_000,
        description="اعتبار اول برای بررسی پرچم بازپخش",
        created_by=None,
        idempotency_key="outcome-1",
    )
    second_entry, second_replayed = wallet.grant_from_admin_with_outcome(
        workspace=ws,
        amount_toman=10_000,
        description="اعتبار اول برای بررسی پرچم بازپخش",
        created_by=None,
        idempotency_key="outcome-1",
    )

    assert (first_replayed, second_replayed) == (False, True)
    assert first_entry.pk == second_entry.pk


def test_revoke_states_the_replay_fact_too(client, funded_roles, instance_admin):
    ws, _plain, _ws_admin = funded_roles
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")
    force_instance_admin_login(client, instance_admin)
    payload = {"entry": str(entry.pk), "description": "ابطال برای بررسی پرچم بازپخش"}

    first = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/revoke/",
        payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="revoke-signal-1",
    )
    second = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/revoke/",
        payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="revoke-signal-1",
    )

    assert first.status_code == 201, first.content
    assert second.status_code == 200, second.content
    assert second.json()["id"] == first.json()["id"]


def test_every_wallet_error_subclass_is_in_the_status_registry():
    """The taxonomy is closed, by introspection rather than by memory.

    ``HOLD_ALLOWED_SOURCES`` drifted because an allow-list nobody re-read
    silently accepted a source it was meant to refuse. A ``WalletError``
    subclass added to ``wallet.py`` without a status here would drift the same
    way, so the check is mechanical: walk every subclass, transitively, and
    require it in the registry.

    Transitive because the direct-children check would pass while a
    second-generation subclass escaped it -- and a subclass is exactly the
    thing ``handle_wallet_error`` refuses to resolve, since it looks up the
    exact type.
    """
    from plane.billing.api.views import wallet_views
    from plane.billing.services import wallet as wallet_module
    from plane.billing.services.wallet import WalletError

    registry = wallet_views.WALLET_ERROR_STATUS
    assert WalletError in registry, "the bare cross-tenant refusal must stay mapped, never become a 500"

    # Scoped to the module the policy errors live in, not just to the direct
    # children: transitive, because ``handle_wallet_error`` looks up the EXACT
    # type, and a second-generation subclass is exactly what it refuses to
    # resolve. The module filter is what lets a test define a throwaway
    # subclass (see below) without making this assertion meaningless.
    found, frontier = set(), [WalletError]
    while frontier:
        for child in frontier.pop().__subclasses__():
            if child.__module__ != wallet_module.__name__:
                continue
            if child not in found:
                found.add(child)
                frontier.append(child)

    assert found, "introspection found no subclasses at all; this test is not doing its job"
    unmapped = sorted(cls.__name__ for cls in found if cls not in registry)
    assert not unmapped, f"WalletError subclasses with no HTTP status: {unmapped}"


def test_an_unmapped_wallet_error_subclass_raises_rather_than_returning_403():
    """A new policy error must be loud, not silently a permission failure.

    This is the drift the registry exists to stop: before it, an unmapped
    subclass fell through to a bare ``WalletError`` branch and answered 403
    forever, with no test failing.
    """
    import pytest

    from plane.billing.api.views import wallet_views
    from plane.billing.services.wallet import WalletError

    class SomePolicyErrorAddedLater(WalletError):
        message = "خطای سیاستی که هنوز نگاشت نشده است."

    with pytest.raises(wallet_views.UnmappedWalletError):
        wallet_views.handle_wallet_error(SomePolicyErrorAddedLater())

    # The subclass is permanently in ``WalletError.__subclasses__`` -- there is
    # no way to unregister one -- so the introspection test above filters on
    # ``__module__`` rather than pretending it can be removed.


def test_the_registry_and_its_grouping_tuples_agree():
    from plane.billing.api.views import wallet_views

    wallet_views._assert_registry_matches_the_groupings()


def test_the_bare_cross_tenant_wallet_error_is_still_a_403():
    from plane.billing.api.views.wallet_views import handle_wallet_error
    from plane.billing.services.wallet import WORKSPACE_MISMATCH_MESSAGE, WalletError

    response = handle_wallet_error(WalletError(WORKSPACE_MISMATCH_MESSAGE))

    assert response.status_code == 403
    assert "not a server fault" not in response.data["error"]


def test_the_generated_idempotency_key_is_unique_per_request(client, funded_roles, instance_admin):
    """Two headerless requests must never collide, or the second looks like a replay.

    A fallback derived from anything stable (the user, the body, the minute)
    would be a correctness bug, not a weak uniqueness argument: the column is
    globally unique, so the colliding second request would find the first
    one's row, answer 200, and silently post nothing while the operator was
    told nothing happened.
    """
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)
    payload = {"amount_toman": 250_000, "description": "دو درخواست بدون هدر کلید یکتا"}

    first = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        payload,
        content_type="application/json",
    )
    second = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        payload,
        content_type="application/json",
    )

    assert first.status_code == 201, first.content
    assert second.status_code == 201, second.content
    assert first.json()["id"] != second.json()["id"]
    assert first.json()["idempotency_key"] != second.json()["idempotency_key"]
    # both grants really posted: no collision meant no silent no-op.
    # The fixture starts at 400_000, so 400_000 + 2 x 250_000.
    assert money.wallet_balance(ws) == 900_000


def test_a_blank_idempotency_header_falls_back_to_a_fresh_key(client, funded_roles, instance_admin):
    """Whitespace is not a key; it must not be stored as one."""
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)
    payload = {"amount_toman": 250_000, "description": "هدر کلید یکتا با فاصله"}

    first = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="   ",
    )
    second = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        payload,
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="   ",
    )

    assert first.status_code == 201, first.content
    assert second.status_code == 201, second.content
    assert first.json()["idempotency_key"] != second.json()["idempotency_key"]


def test_the_supplied_idempotency_key_is_still_honoured(client, funded_roles, instance_admin):
    ws, _plain, _ws_admin = funded_roles
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 250_000, "description": "کلید یکتای ارسالی از هدر"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="  honoured-key  ",
    )

    assert response.status_code == 201, response.content
    assert response.json()["idempotency_key"] == "honoured-key", "the header value is stripped, not refuted"


# --- a client cannot turn either money endpoint into a 500 ----------------
# DataError is a sibling of IntegrityError, not a subclass, and the project's
# handler only catches the latter, so an unbounded integer or an over-long
# idempotency key reached the database as an unhandled server error.


def test_an_out_of_range_amount_is_a_400_not_a_500(client, funded_workspace, instance_admin):
    ws, _operator = funded_workspace
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 2**63, "description": "مبلغی بیش از محدودهٔ ستون پایگاه داده"},
        content_type="application/json",
    )

    assert response.status_code == 400, response.content


def test_the_biggest_storable_amount_is_still_accepted(client, funded_workspace, instance_admin):
    ws, _operator = funded_workspace
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 2**63 - 1, "description": "بیشترین مبلغی که ستون ذخیره می‌کند"},
        content_type="application/json",
    )

    assert response.status_code == 201, response.content


def test_an_over_long_idempotency_key_is_a_400_not_a_500(client, funded_workspace, instance_admin):
    ws, _operator = funded_workspace
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 5_000, "description": "کلید تکرارپذیری بیش از حد طولانی"},
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="x" * 300,
    )

    assert response.status_code == 400, response.content
    assert not LedgerEntry.objects.filter(description="کلید تکرارپذیری بیش از حد طولانی").exists()
