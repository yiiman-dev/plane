# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Phase 2: typed feature flag limits and the three Plan policy fields."""

# Python imports
from itertools import count

# Third party imports
import pytest

# Module imports
from plane.billing.models import (
    BillingAccessLog,
    FeatureFlag,
    Plan,
    PlanFeatureFlag,
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
    client.force_login(instance_admin)
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
    client.force_login(instance_admin)
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
    client.force_login(instance_admin)
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
    client.force_login(instance_admin)

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
    client.force_login(instance_admin)

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
    client.force_login(instance_admin)

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": ["a", "b"], "is_enabled": True},
        format="json",
    )

    assert response.status_code == 400, response.content


@pytest.mark.django_db
def test_a_zero_limit_on_a_number_flag_is_accepted_and_stored(client, instance_admin):
    """0 is a bound, not "unset": the column is ``null=True`` for unset.

    Phase 3's ``usage > limit`` comparison depends on that reading, so it is
    pinned here rather than left to the reader of ``is None`` in ``validate()``.
    """
    plan = Plan.objects.create(code="zero", name="پلن")
    flag = FeatureFlag.objects.create(code="zero-flag", name="صفر", limit_type="number", unit_label="پروژه")
    client.force_login(instance_admin)

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
    client.force_login(instance_admin)

    response = client.post(
        f"/api/billing/admin/plans/{plan.pk}/feature-flags/",
        {"feature_flag": str(flag.pk), "is_enabled": True, "limit_value": 0},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "limit_value" in response.json()
    assert PlanFeatureFlag.objects.count() == 0
