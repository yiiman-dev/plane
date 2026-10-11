# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Phase 2: typed feature flag limits and the three Plan policy fields."""

# Third party imports
import pytest

# Module imports
from plane.billing.models import (
    BillingAccessLog,
    FeatureFlag,
    Plan,
    PlanFeatureFlag,
)


def test_a_new_flag_defaults_to_a_boolean_limit(db):
    flag = FeatureFlag.objects.create(code="charts", name="نمودارها")
    assert flag.limit_type == FeatureFlag.LIMIT_TYPE_BOOLEAN
    assert flag.unit_label == ""


@pytest.mark.parametrize("limit_type", ["boolean", "number", "unlimited"])
def test_every_limit_type_is_accepted(db, limit_type):
    flag = FeatureFlag.objects.create(code=f"flag-{limit_type}", name="پرچم", limit_type=limit_type)
    flag.refresh_from_db()
    assert flag.limit_type == limit_type


def test_an_unknown_limit_type_is_refused_by_the_database(db):
    """choices is enforced by Django's validator, not by the column type."""
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


def test_config_survives_the_migration_untouched(db):
    """The decision: config stays a free JSONField. Retiring it is a later migration."""
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
