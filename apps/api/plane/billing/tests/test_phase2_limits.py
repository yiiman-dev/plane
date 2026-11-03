# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Phase 2: typed feature flag limits and the three Plan policy fields."""

# Python imports
from itertools import count
from uuid import uuid4

# Third party imports
import pytest

# Module imports
from plane.billing.tests.conftest import force_instance_admin_login
from plane.billing.models import (
    BillingAccessLog,
    BillingCycle,
    FeatureFlag,
    Plan,
    PlanFeatureFlag,
    Subscription,
    SubscriptionStatus,
    WorkspaceFeatureFlag,
)

_flag_counter = count(1)


def test_a_new_flag_defaults_to_a_boolean_limit(db):
    flag = FeatureFlag.objects.create(code="charts", name="نمودارها")
    assert flag.limit_type == FeatureFlag.LIMIT_TYPE_BOOLEAN
    assert flag.unit_label == ""


@pytest.mark.parametrize("limit_type", ["boolean", "number", "unlimited"])
def test_every_limit_type_is_accepted(db, limit_type):
    flag = FeatureFlag.objects.create(code=f"flag-{limit_type}", name="پرچم", limit_type=limit_type)
    flag.refresh_from_db()
    assert flag.limit_type == limit_type


def test_an_unknown_limit_type_is_refused_by_the_model_validator(db):
    """choices is enforced by Django's validator, not by the column type.

    The database would happily store "infinite" in a varchar(16); it is
    ``full_clean()`` that runs the ``choices`` check.
    """
    from django.core.exceptions import ValidationError

    flag = FeatureFlag(code="bad", name="بد", limit_type="infinite")
    with pytest.raises(ValidationError):
        flag.full_clean()


def test_a_plan_carries_its_three_policy_fields(db):
    plan = Plan.objects.create(code="pro", name="حرفه‌ای", monthly_price_toman=1000)
    assert plan.renew_lock_days == 0
    assert plan.proration_mode == Plan.PRORATION_CREDIT_REMAINING
    assert plan.sms_prices == {}


def test_sms_prices_round_trip_as_a_dict(db):
    plan = Plan.objects.create(code="pro2", name="حرفه‌ای", sms_prices={"send_sms": 120})
    plan.refresh_from_db()
    assert plan.sms_prices == {"send_sms": 120}


def test_a_granted_number_flag_carries_its_limit(db):
    plan = Plan.objects.create(code="p3", name="پلن")
    flag = FeatureFlag.objects.create(code="projects", name="پروژه", limit_type="number", unit_label="پروژه")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, limit_value=10)
    grant.refresh_from_db()
    assert grant.limit_value == 10


def test_a_limit_is_optional(db):
    plan = Plan.objects.create(code="p4", name="پلن")
    flag = FeatureFlag.objects.create(code="boolflag", name="پرچم")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag)
    assert grant.limit_value is None


def test_config_remains_a_free_json_field(db):
    """The decision: config stays a free JSONField. Retiring it is a later migration.

    No migration is exercised here -- ``pytest.ini`` sets ``--nomigrations``, so
    the schema is built from the models. This guards the modelling decision, not
    the migration.
    """
    plan = Plan.objects.create(code="p5", name="پلن")
    flag = FeatureFlag.objects.create(code="legacy", name="قدیمی")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, config={"anything": [1, 2]})
    grant.refresh_from_db()
    assert grant.config == {"anything": [1, 2]}


def test_an_access_log_row_records_the_viewer_and_the_workspace(db, workspace_factory):
    from plane.db.models import User

    workspace = workspace_factory(name="تیم لاگ")
    viewer = User.objects.create(username="auditor", email="auditor@example.com")

    BillingAccessLog.objects.create(
        viewer=viewer, workspace=workspace, view=BillingAccessLog.VIEW_LEDGER, ip_address="127.0.0.1"
    )

    row = BillingAccessLog.objects.get()
    assert row.viewer_id == viewer.pk
    assert row.workspace_id == workspace.pk
    assert row.view == "ledger"


def test_deleting_a_workspace_takes_its_access_log_with_it(db, workspace_factory):
    """The FK CASCADE, not the soft delete task.

    ``Workspace.delete()`` defaults to a soft delete: it stamps ``deleted_at`` and
    enqueues ``soft_delete_related_objects``, which needs a broker this container
    does not have. Soft deleting the workspace leaves the row in the table, so the
    DB-level ``on_delete=CASCADE`` this test is about never fires. Hard deleting
    exercises the declared cascade directly.
    """
    workspace = workspace_factory(name="تیم حذف")
    BillingAccessLog.objects.create(workspace=workspace, view=BillingAccessLog.VIEW_WALLET)
    workspace.delete(soft=False)
    assert BillingAccessLog.objects.count() == 0


def _plan_with_flag(limit_type: str, **flag_kwargs):
    """A plan and a flag of the given limit type, with codes that stay unique per call.

    The brief's version interpolates the kwargs dict straight into the code, which
    puts a Persian ``unit_label`` into a 50-char ``code`` column and into a URL
    slug later. A counter keeps the codes short and distinct instead.
    """
    suffix = next(_flag_counter)
    plan = Plan.objects.create(code=f"sp-{suffix}", name="پلن")
    flag = FeatureFlag.objects.create(code=f"f-{suffix}", name="پرچم", limit_type=limit_type, **flag_kwargs)
    return plan, flag


def test_a_number_flag_stores_its_limit(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="پروژه")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True, "limit_value": 25})

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["limit_value"] == 25


def test_a_limit_on_a_boolean_flag_is_refused_not_ignored(db):
    """Silently dropping it would let the admin's UI appear to save and do nothing."""
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("boolean")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True, "limit_value": 5})

    assert serializer.is_valid() is False
    assert "limit_value" in serializer.errors


def test_a_limit_on_an_unlimited_flag_is_refused(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("unlimited")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True, "limit_value": 5})

    assert serializer.is_valid() is False
    assert "limit_value" in serializer.errors


def test_a_number_flag_saved_without_a_limit_is_refused(db):
    """The whole point of limit_type=number is a countable bound. Without it the flag is a lie."""
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="نمودار")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True})

    assert serializer.is_valid() is False
    assert "limit_value" in serializer.errors


def test_a_boolean_flag_saved_without_a_limit_is_fine(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("boolean")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True})

    assert serializer.is_valid(), serializer.errors


def test_an_explicit_null_limit_on_a_number_flag_is_refused(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="پروژه")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True, "limit_value": None})

    assert serializer.is_valid() is False
    assert "limit_value" in serializer.errors


def test_a_partial_update_may_omit_the_limit_of_a_stored_number_grant(db):
    """``not self.partial``: omitting the field means the stored value still stands.

    The instance's own flag decides here, because ``feature_flag`` is absent from
    a partial update.
    """
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="پروژه")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, limit_value=10)

    serializer = PlanFeatureFlagSerializer(grant, data={"is_enabled": False}, partial=True)

    assert serializer.is_valid(), serializer.errors
    assert "limit_value" not in serializer.validated_data


def test_a_partial_update_may_not_null_out_a_number_flag_limit(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="پروژه")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, limit_value=10)

    serializer = PlanFeatureFlagSerializer(grant, data={"limit_value": None}, partial=True)

    assert serializer.is_valid() is False
    assert "limit_value" in serializer.errors


def test_a_partial_update_may_change_the_limit_of_a_stored_number_grant(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="پروژه")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, limit_value=10)

    serializer = PlanFeatureFlagSerializer(grant, data={"limit_value": 42}, partial=True)

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["limit_value"] == 42


def test_the_grant_projection_exposes_the_flag_limit_type(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="نمودار")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, limit_value=5)

    body = PlanFeatureFlagSerializer(grant).data

    assert body["limit_type"] == "number"
    assert body["unit_label"] == "نمودار"
    assert body["limit_value"] == 5


def test_the_flag_catalogue_exposes_the_typed_limit(db):
    from plane.billing.api.serializers import FeatureFlagSerializer

    flag = FeatureFlag.objects.create(code="charts", name="نمودارها", limit_type="number", unit_label="نمودار")
    body = FeatureFlagSerializer(flag).data

    assert body["limit_type"] == "number"
    assert body["unit_label"] == "نمودار"


def test_the_flag_catalogue_accepts_a_typed_limit_on_write(db):
    from plane.billing.api.serializers import FeatureFlagSerializer

    serializer = FeatureFlagSerializer(
        data={"code": "charts", "name": "نمودارها", "limit_type": "number", "unit_label": "نمودار"}
    )

    assert serializer.is_valid(), serializer.errors
    flag = serializer.save()
    assert (flag.limit_type, flag.unit_label) == ("number", "نمودار")


def test_the_plan_projection_exposes_the_three_policy_fields(db):
    from plane.billing.api.serializers import PlanSerializer

    plan = Plan.objects.create(
        code="pp", name="پلن", renew_lock_days=7, proration_mode="no_extension", sms_prices={"send_sms": 250}
    )
    body = PlanSerializer(plan).data

    assert body["renew_lock_days"] == 7
    assert body["proration_mode"] == "no_extension"
    assert body["sms_prices"] == {"send_sms": 250}


@pytest.mark.django_db
def test_the_endpoint_passes_the_limit_through(client, instance_admin):
    """``update_or_create`` in the view: without the field in ``defaults`` the value is dropped."""
    force_instance_admin_login(client, instance_admin)
    plan = Plan.objects.create(code="ep", name="پلن")
    flag = FeatureFlag.objects.create(code="projects", name="پروژه", limit_type="number", unit_label="پروژه")

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": str(flag.pk), "is_enabled": True, "limit_value": 12},
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["limit_value"] == 12
    grant = PlanFeatureFlag.objects.get(plan=plan, feature_flag=flag)
    assert grant.limit_value == 12


@pytest.mark.django_db
def test_the_endpoint_omitting_the_limit_leaves_a_stored_one_alone(client, instance_admin):
    """The ``if "limit_value" in validated_data`` guard, proven through the endpoint.

    A bare ``defaults["limit_value"] = validated_data.get("limit_value")`` would
    clear the stored limit on every re-add of the same grant.
    """
    force_instance_admin_login(client, instance_admin)
    plan = Plan.objects.create(code="ep2", name="پلن")
    flag = FeatureFlag.objects.create(code="projects2", name="پروژه", limit_type="number", unit_label="پروژه")
    PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, limit_value=7)

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": str(flag.pk), "is_enabled": False},
        format="json",
    )

    assert response.status_code == 201, response.content
    grant = PlanFeatureFlag.objects.get(plan=plan, feature_flag=flag)
    assert grant.limit_value == 7
    assert grant.is_enabled is False


@pytest.mark.django_db
def test_the_endpoint_refuses_a_limit_on_a_boolean_flag(client, instance_admin):
    force_instance_admin_login(client, instance_admin)
    plan = Plan.objects.create(code="ep3", name="پلن")
    flag = FeatureFlag.objects.create(code="dark", name="تاریک", limit_type="boolean")

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": str(flag.pk), "is_enabled": True, "limit_value": 3},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "limit_value" in response.json()
    assert PlanFeatureFlag.objects.count() == 0


@pytest.mark.django_db
def test_the_endpoint_refuses_a_new_number_grant_without_a_bound(client, instance_admin):
    """The guard that makes a number flag's bound mandatory lives in the VIEW.

    Changing ``partial=existing`` to ``partial=True`` would let an unbounded
    number grant through, and this is the test that stops it.
    """
    plan = Plan.objects.create(code="boundless", name="پلن")
    flag = FeatureFlag.objects.create(code="boundless-flag", name="پروژه", limit_type="number", unit_label="پروژه")
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": str(flag.pk), "is_enabled": True},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "limit_value" in response.json()
    assert PlanFeatureFlag.objects.count() == 0


@pytest.mark.django_db
def test_a_malformed_feature_flag_pk_is_a_400_not_a_500(client, instance_admin):
    """The ``existing`` lookup runs before the serializer can validate anything.

    A garbage pk pushed straight into a UUID filter raises Django's
    ``ValidationError``, which DRF's exception_handler does not catch — so the
    guard is what turns a 500 back into the serializer's 400.
    """
    plan = Plan.objects.create(code="badpk", name="پلن")
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": "not-a-uuid", "is_enabled": True},
        format="json",
    )

    assert response.status_code == 400, response.content


@pytest.mark.django_db
def test_a_json_list_as_the_feature_flag_pk_is_a_400_not_a_500(client, instance_admin):
    """``str()`` of a list is not a UUID either, and must take the same path."""
    plan = Plan.objects.create(code="listpk", name="پلن")
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": ["a", "b"], "is_enabled": True},
        format="json",
    )

    assert response.status_code == 400, response.content


# --- feature_limit: the reader that makes limit_value reachable --------------


@pytest.fixture
def limited_workspace(workspace_factory):
    """A workspace on a plan that grants a number flag with a limit of 7."""
    workspace = workspace_factory(name="تیم محدود")
    plan = Plan.objects.create(code="limited", name="پلن محدود")
    flag = FeatureFlag.objects.create(code="projects", name="پروژه", limit_type="number", unit_label="پروژه")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, is_enabled=True, limit_value=7)
    Subscription.objects.create(
        user=workspace.owner,
        workspace=workspace,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        seats=1,
        cycle=BillingCycle.MONTHLY,
    )
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=flag, is_enabled=True)
    return workspace, flag, grant


def test_the_effective_limit_is_returned(limited_workspace):
    from plane.billing.services.entitlements import feature_limit

    workspace, _flag, _grant = limited_workspace
    assert feature_limit(workspace, "projects") == 7


def test_a_boolean_flag_has_no_numeric_limit(workspace_factory):
    from plane.billing.services.entitlements import feature_limit

    other = workspace_factory(name="تیم دیگر")
    bool_flag = FeatureFlag.objects.create(code="charts", name="نمودار", limit_type="boolean")
    plan = Plan.objects.create(code="boolplan", name="پلن")
    PlanFeatureFlag.objects.create(plan=plan, feature_flag=bool_flag, is_enabled=True)
    Subscription.objects.create(
        user=other.owner,
        workspace=other,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        seats=1,
        cycle=BillingCycle.MONTHLY,
    )
    WorkspaceFeatureFlag.objects.create(workspace=other, feature_flag=bool_flag, is_enabled=True)

    assert feature_limit(other, "charts") is None


def test_a_flag_the_workspace_has_not_switched_on_has_no_limit(limited_workspace):
    from plane.billing.services.entitlements import feature_limit

    workspace, flag, _grant = limited_workspace
    WorkspaceFeatureFlag.objects.filter(workspace=workspace, feature_flag=flag).update(is_enabled=False)

    assert feature_limit(workspace, "projects") is None


def test_a_flag_the_plan_does_not_grant_has_no_limit(limited_workspace):
    from plane.billing.services.entitlements import feature_limit

    workspace, flag, _grant = limited_workspace
    grant = PlanFeatureFlag.objects.get(feature_flag=flag)
    grant.is_enabled = False
    grant.save()

    assert feature_limit(workspace, "projects") is None


def test_an_unknown_code_has_no_limit(limited_workspace):
    from plane.billing.services.entitlements import feature_limit

    workspace, _flag, _grant = limited_workspace
    assert feature_limit(workspace, "no-such-flag") is None


def test_a_missing_workspace_has_no_limit():
    from plane.billing.services.entitlements import feature_limit

    assert feature_limit(None, "projects") is None


def test_a_granted_number_flag_with_no_stored_limit_reports_none(limited_workspace):
    """A row like this predates the serializer, and must not crash or over-grant.

    ``None`` means "no countable bound here", which grants nothing. Returning the
    stored ``None`` verbatim is the same answer, and it is the safe one: the
    opposite reading -- "no stored bound means unbounded" -- would hand an
    unlimited amount to every workspace on such a plan.
    """
    from plane.billing.services.entitlements import feature_limit

    workspace, flag, _grant = limited_workspace
    PlanFeatureFlag.objects.filter(feature_flag=flag).update(limit_value=None)

    assert feature_limit(workspace, "projects") is None


def test_a_zero_limit_is_returned_as_zero_not_as_none(limited_workspace):
    """``0`` is a bound -- "none allowed" -- and must survive the read.

    A reader that confuses ``0`` with ``None`` turns "this plan allows no
    projects" into "this plan allows any number of projects", which is the exact
    inversion Phase 3's ``usage > limit`` comparison would then rely on.
    """
    from plane.billing.services.entitlements import feature_limit

    workspace, flag, _grant = limited_workspace
    PlanFeatureFlag.objects.filter(feature_flag=flag).update(limit_value=0)

    limit = feature_limit(workspace, "projects")

    assert limit is not None
    assert limit == 0


def test_an_inactive_flag_has_no_limit(limited_workspace):
    from plane.billing.services.entitlements import feature_limit

    workspace, flag, _grant = limited_workspace
    FeatureFlag.objects.filter(code=flag.code).update(is_active=False)

    assert feature_limit(workspace, "projects") is None


def test_a_workspace_with_no_plan_has_no_limit(workspace_factory):
    """The plan layer: no subscription and no free plan row means nothing is granted."""
    from plane.billing.services.entitlements import feature_limit

    workspace = workspace_factory(name="تیم بی‌پلن")
    plan = Plan.objects.create(code="orphanplan", name="پلن")
    flag = FeatureFlag.objects.create(code="orphan", name="پرچم", limit_type="number", unit_label="پروژه")
    PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, is_enabled=True, limit_value=5)
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=flag, is_enabled=True)

    assert feature_limit(workspace, "orphan") is None


def test_feature_limit_agrees_with_has_feature(limited_workspace):
    """Two answers to two questions about the same switch. If they disagree, one is a lie.

    The second half is the one that earns this test: drop the
    ``WorkspaceFeatureFlag`` check from ``feature_limit`` and ``has_feature``
    goes False while ``feature_limit`` still returns 7, so the failure lands
    here rather than in some future consumer's incident.
    """
    from plane.billing.services.entitlements import feature_limit, has_feature

    workspace, flag, _grant = limited_workspace
    assert has_feature(workspace, flag.code) is True
    assert feature_limit(workspace, flag.code) == 7

    WorkspaceFeatureFlag.objects.filter(workspace=workspace, feature_flag=flag).update(is_enabled=False)

    assert has_feature(workspace, flag.code) is False
    assert feature_limit(workspace, flag.code) is None


@pytest.mark.django_db
def test_a_zero_limit_on_a_number_flag_is_accepted_and_stored(client, instance_admin):
    """0 is a bound, not "unset": the column is ``null=True`` for unset.

    Phase 3's ``usage > limit`` comparison depends on that reading, so it is
    pinned here rather than left to the reader of ``is None`` in ``validate()``.
    """
    plan = Plan.objects.create(code="zero", name="پلن")
    flag = FeatureFlag.objects.create(code="zero-flag", name="صفر", limit_type="number", unit_label="پروژه")
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": str(flag.pk), "is_enabled": True, "limit_value": 0},
        format="json",
    )

    assert response.status_code == 201, response.content
    assert response.json()["limit_value"] == 0
    grant = PlanFeatureFlag.objects.get(plan=plan, feature_flag=flag)
    assert grant.limit_value == 0


@pytest.mark.django_db
def test_a_zero_limit_on_a_boolean_flag_is_refused(client, instance_admin):
    """The other half of the same rule: any non-None limit on a non-number flag goes."""
    plan = Plan.objects.create(code="zero-bool", name="پلن")
    flag = FeatureFlag.objects.create(code="zero-bool-flag", name="تاریک", limit_type="boolean")
    force_instance_admin_login(client, instance_admin)

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": str(flag.pk), "is_enabled": True, "limit_value": 0},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "limit_value" in response.json()
    assert PlanFeatureFlag.objects.count() == 0


# --- wallet_balances: the batch reader behind the list page -----------------
# The dangerous failure is reporting HELD money as spendable, so the held
# account is pinned separately from the spendable one.


@pytest.fixture
def funded_workspace(workspace_factory):
    """A workspace credited once by hand.

    Local rather than imported: ``test_access_log.py`` owns a fixture of this
    name, and a fixture cannot be imported across test modules without
    dragging that module's dependencies along.
    """
    from plane.billing.services import wallet

    ws = workspace_factory(name="تیم بررسی", slug=f"limits-team-{uuid4().hex[:8]}")
    wallet.grant_from_admin(
        workspace=ws,
        amount_toman=400_000,
        description="اعتبار برای بررسی",
        created_by=None,
        idempotency_key=f"limits-{uuid4().hex}",
    )
    return ws, None


def test_the_batch_balance_matches_the_single_read(workspace_factory):
    from plane.billing.services import money, wallet

    first = workspace_factory(name="تیم یک")
    second = workspace_factory(name="تیم دو")
    wallet.grant_from_admin(
        workspace=first, amount_toman=400_000, description="اعتبار اول", created_by=None, idempotency_key="wb-1"
    )
    wallet.grant_from_admin(
        workspace=second, amount_toman=900_000, description="اعتبار دوم", created_by=None, idempotency_key="wb-2"
    )

    totals = money.wallet_balances([first.pk, second.pk])

    assert totals[first.pk] == money.wallet_balance(first) == 400_000
    assert totals[second.pk] == money.wallet_balance(second) == 900_000


def test_held_money_is_not_reported_as_spendable(workspace_factory):
    """A hold moves money to the held account. If both accounts are summed the
    balance looks untouched and every grant appears to have been ignored."""
    from plane.billing.services import money, wallet

    workspace = workspace_factory(name="تیم نگه‌داری")
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=500_000,
        description="اعتبار اولیه",
        created_by=None,
        idempotency_key="wb-hold-grant",
    )
    wallet.hold_funds(
        workspace=workspace,
        amount_toman=300_000,
        description="نگه‌داری بابت فاکتور",
        idempotency_key="wb-hold-1",
    )

    totals = money.wallet_balances([workspace.pk])

    assert totals[workspace.pk] == 200_000
    assert money.wallet_hold_balance(workspace) == 300_000
    # The single read must agree, or the two APIs disagree about the same wallet.
    assert totals[workspace.pk] == money.wallet_balance(workspace)


def test_a_workspace_with_no_wallet_is_absent_rather_than_zero(workspace_factory):
    """The list page reads a missing account as zero. The helper must not CREATE
    a wallet row on a read-only page."""
    from plane.billing.models import LedgerAccount, Wallet
    from plane.billing.services import money

    workspace = workspace_factory(name="تیم خالی")

    totals = money.wallet_balances([workspace.pk])

    assert workspace.pk not in totals
    assert Wallet.objects.filter(workspace=workspace).count() == 0
    # The Wallet row is not the one that matters: it is the ledger ACCOUNT that
    # ``wallet_balance`` creates, through ``get_or_create_wallet_accounts``. If
    # the batch reader called that, a read-only list page would leave a row per
    # workspace behind it. Pinned by code, not by kind, because both legs share
    # the ``wallet:default:`` prefix.
    assert not LedgerAccount.objects.filter(code=money.WalletAccountCode.wallet_default(workspace.pk)).exists()


def test_the_batch_reader_agrees_with_the_single_read_after_a_refund(workspace_factory):
    from plane.billing.services import money, wallet

    workspace = workspace_factory(name="تیم بازپرداخت")
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=1_000_000,
        description="اعتبار اولیه",
        created_by=None,
        idempotency_key="wb-r-grant",
    )
    wallet.refund_to_spendable(
        workspace=workspace,
        amount_toman=400_000,
        reason="انصراف از خرید",
        reference="pay-7788",
        idempotency_key="wb-r-1",
    )

    # 1_400_000, not 1_000_000: a grant DEBITS the wallet (it draws on the
    # admin grant pool) and ``refund_to_spendable`` debits it again, so both
    # movements land on the same side and the sum is 1_000_000 + 400_000. The
    # point of the test is the agreement, and it is checked against the single
    # read as well so a future change to either direction breaks it here.
    assert money.wallet_balances([workspace.pk])[workspace.pk] == money.wallet_balance(workspace) == 1_400_000


def test_the_batch_reader_returns_nothing_for_an_empty_workspace_list():
    from plane.billing.services import money

    assert money.wallet_balances([]) == {}


@pytest.mark.django_db
def test_the_batch_reader_sees_an_entry_posted_without_a_workspace(workspace_factory):
    """``post_entry`` accepts ``workspace=None``, so a workspace-owned account
    owns entries that name no workspace. Scoping the entries by workspace as
    well would hide them and under-count the balance -- which is exactly what
    ``money._signed_total``'s docstring says, so it is pinned here rather than
    trusted."""
    from plane.billing.models import LedgerAccount
    from plane.billing.services import money

    workspace = workspace_factory(name="تیم بی‌فضای کاری")
    wallet_service = pytest.importorskip("plane.billing.services.wallet")
    wallet_service.grant_from_admin(
        workspace=workspace,
        amount_toman=300_000,
        description="اعتبار اولیه",
        created_by=None,
        idempotency_key="ws-less-1",
    )
    spendable = LedgerAccount.objects.get(code=money.WalletAccountCode.wallet_default(workspace.pk))
    pool = LedgerAccount.objects.get(code=money.ADMIN_GRANT_POOL)
    money.post_entry(
        debit=pool,
        credit=spendable,
        amount_toman=120_000,
        source="admin_grant",
        workspace=None,  # the whole point of the test
        description="اعتبار بدون فضای کاری",
        created_by=None,
        idempotency_key="ws-less-2",
    )

    # 180_000, not 420_000: a grant DEBITS the spendable account, so the
    # hand-posted 120_000 CREDIT is what comes off the top.
    assert money.wallet_balances([workspace.pk])[workspace.pk] == money.wallet_balance(workspace) == 180_000


# --- the admin workspace endpoints -----------------------------------------


@pytest.mark.django_db
def test_the_workspace_list_needs_an_instance_admin(client, funded_workspace):
    from plane.db.models import User

    plain = User.objects.create(username="lister", email="lister@example.com")
    client.force_login(plain)

    response = client.get("/api/billing/admin/workspaces/")

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_the_workspace_list_returns_each_workspace_with_its_plan_and_balance(client, workspace_factory, instance_admin):
    force_instance_admin_login(client, instance_admin)
    first = workspace_factory(name="تیم الف")
    second = workspace_factory(name="تیم ب")

    response = client.get("/api/billing/admin/workspaces/")

    assert response.status_code == 200, response.content
    slugs = {row["slug"] for row in response.json()["results"]}
    assert {first.slug, second.slug} <= slugs


@pytest.mark.django_db
def test_the_workspace_list_reports_the_plan_code(client, workspace_factory, instance_admin):
    workspace = workspace_factory(name="تیم پلن")
    plan = Plan.objects.create(code="listed", name="پلن فهرست")
    # ``user`` is NOT NULL on Subscription: the plan is bought by somebody, and
    # the workspace's owner stands in for them here.
    Subscription.objects.create(
        workspace=workspace,
        user=workspace.owner,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        seats=3,
        cycle=BillingCycle.MONTHLY,
    )
    force_instance_admin_login(client, instance_admin)

    rows = {row["slug"]: row for row in client.get("/api/billing/admin/workspaces/").json()["results"]}

    assert rows[workspace.slug]["plan_code"] == "listed"
    assert rows[workspace.slug]["seats"] == 3


@pytest.mark.django_db
def test_the_workspace_list_reports_the_wallet_balance(client, workspace_factory, instance_admin):
    from plane.billing.services import wallet

    workspace = workspace_factory(name="تیم موجودی")
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=250_000,
        description="اعتبار اولیه برای فهرست",
        created_by=None,
        idempotency_key="list-1",
    )
    force_instance_admin_login(client, instance_admin)

    rows = {row["slug"]: row for row in client.get("/api/billing/admin/workspaces/").json()["results"]}

    assert rows[workspace.slug]["balance_toman"] == 250_000


@pytest.mark.django_db
def test_the_workspace_list_reports_a_held_wallet_as_its_spendable_remainder(client, workspace_factory, instance_admin):
    """The row must agree with the detail page's balance, and the detail page's
    balance is the SPENDABLE one -- a hold moves money out of it."""
    from plane.billing.services import wallet

    workspace = workspace_factory(name="تیم قفل")
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=700_000,
        description="اعتبار اولیه",
        created_by=None,
        idempotency_key="hold-list-1",
    )
    wallet.hold_funds(workspace=workspace, amount_toman=200_000, description="نگه‌داری", idempotency_key="hold-list-2")
    force_instance_admin_login(client, instance_admin)

    rows = {row["slug"]: row for row in client.get("/api/billing/admin/workspaces/").json()["results"]}

    assert rows[workspace.slug]["balance_toman"] == 500_000


@pytest.mark.django_db
def test_the_workspace_list_reads_a_workspace_with_no_wallet_as_zero(client, workspace_factory, instance_admin):
    """An absent account is the list page's zero, and reaching the page must not
    have created one."""
    from plane.billing.models import LedgerAccount, Wallet
    from plane.billing.services import money

    workspace = workspace_factory(name="تیم بی‌موجودی")
    force_instance_admin_login(client, instance_admin)

    rows = {row["slug"]: row for row in client.get("/api/billing/admin/workspaces/").json()["results"]}

    assert rows[workspace.slug]["balance_toman"] == 0
    assert Wallet.objects.filter(workspace=workspace).count() == 0
    assert not LedgerAccount.objects.filter(code=money.WalletAccountCode.wallet_default(workspace.pk)).exists()


@pytest.mark.django_db
def test_the_workspace_list_is_not_audited_row_by_row(client, funded_workspace, instance_admin):
    """The list page exists to choose a workspace to open; the money is inspected
    on the detail page. One row per tenant per page view would bury that."""
    force_instance_admin_login(client, instance_admin)

    client.get("/api/billing/admin/workspaces/")

    assert BillingAccessLog.objects.count() == 0


@pytest.mark.django_db
def test_the_detail_page_returns_plan_seats_and_money(client, workspace_factory, instance_admin):
    from plane.billing.services import wallet

    workspace = workspace_factory(name="تیم جزئیات")
    plan = Plan.objects.create(code="detail", name="پلن جزئیات")
    Subscription.objects.create(
        workspace=workspace,
        user=workspace.owner,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        seats=5,
        cycle=BillingCycle.YEARLY,
    )
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=1_000_000,
        description="اعتبار برای صفحهٔ جزئیات",
        created_by=None,
        idempotency_key="det-1",
    )
    force_instance_admin_login(client, instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["slug"] == workspace.slug
    assert body["name"] == "تیم جزئیات"
    assert body["plan_code"] == "detail"
    assert body["seats"] == 5
    assert body["balance_toman"] == 1_000_000


@pytest.mark.django_db
def test_the_detail_page_separates_the_held_amount_from_the_spendable_one(client, workspace_factory, instance_admin):
    from plane.billing.services import wallet

    workspace = workspace_factory(name="تیم نگه‌داری جزئیات")
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=500_000,
        description="اعتبار اولیه",
        created_by=None,
        idempotency_key="det-hold-1",
    )
    wallet.hold_funds(workspace=workspace, amount_toman=150_000, description="نگه‌داری", idempotency_key="det-hold-2")
    force_instance_admin_login(client, instance_admin)

    body = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/").json()

    assert body["balance_toman"] == 350_000
    assert body["hold_balance_toman"] == 150_000


@pytest.mark.django_db
def test_the_detail_page_of_a_workspace_with_no_subscription_reports_nulls(client, workspace_factory, instance_admin):
    """A workspace with no plan is a normal state, not an error: nulls and zeros,
    never a 404."""
    workspace = workspace_factory(name="تیم بدون پلن")
    force_instance_admin_login(client, instance_admin)

    body = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/").json()

    assert body["plan_code"] is None
    assert body["plan_name"] is None
    assert body["seats"] == 0
    assert body["balance_toman"] == 0
    assert body["hold_balance_toman"] == 0
    assert body["subscription_status"] is None


@pytest.mark.django_db
def test_the_detail_page_of_an_unknown_workspace_is_404(client, instance_admin):
    force_instance_admin_login(client, instance_admin)

    assert client.get("/api/billing/admin/workspaces/no-such-workspace/billing/").status_code == 404


@pytest.mark.django_db
def test_a_404_detail_page_leaves_no_audit_row(client, instance_admin):
    """The row must name a read that happened. A refused lookup is not one."""
    force_instance_admin_login(client, instance_admin)

    client.get("/api/billing/admin/workspaces/no-such-workspace/billing/")

    assert BillingAccessLog.objects.count() == 0


@pytest.mark.django_db
def test_the_detail_page_is_refused_to_a_plain_user(client, funded_workspace):
    from plane.db.models import User

    workspace, _operator = funded_workspace
    plain = User.objects.create(username="detail-plain", email="detail-plain@example.com")
    client.force_login(plain)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/")

    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_the_detail_page_writes_an_access_log_row(client, funded_workspace, instance_admin):
    """It returns the balance, so it is a money read and must be audited like one."""
    workspace, _operator = funded_workspace
    force_instance_admin_login(client, instance_admin)

    client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/")

    assert BillingAccessLog.objects.filter(view=BillingAccessLog.VIEW_WALLET).count() == 1


@pytest.mark.django_db
def test_the_detail_page_ignores_a_forged_workspace_query_parameter(client, workspace_factory, instance_admin):
    """The URL decides which workspace; ?slug= must not widen it."""
    mine = workspace_factory(name="تیم خودم")
    other = workspace_factory(name="تیم بیگانه")
    force_instance_admin_login(client, instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{mine.slug}/billing/?slug={other.slug}")

    assert response.status_code == 200
    assert response.json()["slug"] == mine.slug


@pytest.mark.django_db
def test_the_detail_page_counts_the_active_members(client, workspace_factory, instance_admin):
    from plane.db.models import User, WorkspaceMember

    workspace = workspace_factory(name="تیم اعضا")
    live = User.objects.create(username="live-member", email="live-member@example.com")
    gone = User.objects.create(username="gone-member", email="gone-member@example.com")
    WorkspaceMember.objects.create(workspace=workspace, member=live, role=20)
    WorkspaceMember.objects.create(workspace=workspace, member=gone, role=15, is_active=False)
    force_instance_admin_login(client, instance_admin)

    body = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/").json()

    assert body["active_members"] == 1


@pytest.mark.django_db
def test_the_feature_flag_catalogue_is_instance_admin_only(client):
    from plane.db.models import User

    plain = User.objects.create(username="flag-plain", email="flag-plain@example.com")
    client.force_login(plain)

    assert client.get("/api/billing/admin/feature-flags/").status_code in (401, 403)


@pytest.mark.django_db
def test_the_feature_flag_catalogue_returns_the_typed_limit(client, instance_admin):
    FeatureFlag.objects.create(code="typed", name="پرچم نوع‌دار", limit_type="number", unit_label="پروژه")
    force_instance_admin_login(client, instance_admin)

    body = client.get("/api/billing/admin/feature-flags/").json()

    assert body["results"][0]["limit_type"] == "number"
    assert body["results"][0]["unit_label"] == "پروژه"
