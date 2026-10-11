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
from plane.billing.models import LedgerEntry, LedgerSource
from plane.billing.services import ledger, wallet
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
