# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The plan form's save path: one PATCH writes a plan's whole grant set.

The admin plan screen edits every flag of a plan at once and sends the result as
one request, because a half-saved plan is a plan whose catalogue disagrees with
itself. The endpoint therefore answers ``PATCH`` with a ``grants`` list, and
these tests pin the two properties that make a batch worth having: it is atomic
(one bad item writes nothing) and it is partial (a grant the payload does not
mention keeps whatever it had).
"""

# Python imports
from uuid import uuid4

# Third party imports
import pytest

# Module imports
from plane.billing.tests.conftest import force_instance_admin_login
from plane.billing.models import FeatureFlag, Plan, PlanFeatureFlag
from plane.db.models import User

URL = "/api/billing/admin/plans/{plan_id}/feature-flags/"


def number_flag(code: str = "projects") -> FeatureFlag:
    return FeatureFlag.objects.create(code=code, name="پروژه", limit_type="number", unit_label="پروژه")


def boolean_flag(code: str = "charts") -> FeatureFlag:
    return FeatureFlag.objects.create(code=code, name="نمودار", limit_type="boolean")


def grants_url(plan: Plan) -> str:
    return URL.format(plan_id=plan.pk)


@pytest.mark.django_db
def test_the_plan_form_saves_every_grant_and_limit_in_one_patch(client, instance_admin):
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")
    flag_a = number_flag("projects")
    flag_b = boolean_flag("charts")
    force_instance_admin_login(client, instance_admin)

    response = client.patch(
        grants_url(plan),
        {
            "grants": [
                {"feature_flag_code": flag_a.code, "is_enabled": True, "limit_value": 12},
                {"feature_flag_code": flag_b.code, "is_enabled": True},
            ]
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    first = PlanFeatureFlag.objects.get(plan=plan, feature_flag=flag_a)
    second = PlanFeatureFlag.objects.get(plan=plan, feature_flag=flag_b)
    assert (first.is_enabled, first.limit_value) == (True, 12)
    assert (second.is_enabled, second.limit_value) == (True, None)


@pytest.mark.django_db
def test_the_save_response_carries_every_grant_so_the_screen_can_re_render(client, instance_admin):
    """The form rebuilds its rows from the answer, so the answer is the saved set."""
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")
    number_flag("projects")
    boolean_flag("charts")
    force_instance_admin_login(client, instance_admin)

    response = client.patch(
        grants_url(plan),
        {
            "grants": [
                {"feature_flag_code": "projects", "is_enabled": True, "limit_value": 12},
                {"feature_flag_code": "charts", "is_enabled": False},
            ]
        },
        format="json",
    )

    assert response.status_code == 200, response.content

    body = response.json()
    assert "grants" in body, body
    by_code = {grant["feature_flag_code"]: grant for grant in body["grants"]}
    assert set(by_code) == {"projects", "charts"}
    assert by_code["projects"]["limit_value"] == 12
    assert by_code["projects"]["limit_type"] == "number"
    assert by_code["charts"]["is_enabled"] is False


@pytest.mark.django_db
def test_a_limit_on_a_boolean_flag_refuses_the_whole_batch(client, instance_admin):
    """Atomicity is the point: the good item must not be written by a bad sibling."""
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")
    number_flag("projects")
    boolean_flag("charts")
    force_instance_admin_login(client, instance_admin)

    response = client.patch(
        grants_url(plan),
        {
            "grants": [
                {"feature_flag_code": "projects", "is_enabled": True, "limit_value": 12},
                {"feature_flag_code": "charts", "is_enabled": True, "limit_value": 3},
            ]
        },
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "grants" in response.json(), response.json()
    assert PlanFeatureFlag.objects.count() == 0


@pytest.mark.django_db
def test_a_number_grant_without_a_bound_refuses_the_whole_batch(client, instance_admin):
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")
    number_flag("projects")
    boolean_flag("charts")
    force_instance_admin_login(client, instance_admin)

    response = client.patch(
        grants_url(plan),
        {"grants": [{"feature_flag_code": "projects", "is_enabled": True}]},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert PlanFeatureFlag.objects.count() == 0


@pytest.mark.django_db
def test_an_unknown_flag_code_is_refused_rather_than_ignored(client, instance_admin):
    """A silently skipped grant is a screen that saved and did nothing."""
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")
    force_instance_admin_login(client, instance_admin)

    response = client.patch(
        grants_url(plan),
        {"grants": [{"feature_flag_code": "no-such-flag", "is_enabled": True}]},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "grants" in response.json(), response.json()
    assert PlanFeatureFlag.objects.count() == 0


@pytest.mark.django_db
def test_the_batch_leaves_a_grant_it_does_not_list_alone(client, instance_admin):
    """The screen sends what it knows; a grant outside the payload is not deleted."""
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")
    listed = boolean_flag("charts")
    unlisted = boolean_flag("wiki")
    PlanFeatureFlag.objects.create(plan=plan, feature_flag=unlisted, is_enabled=True)
    force_instance_admin_login(client, instance_admin)

    response = client.patch(
        grants_url(plan),
        {"grants": [{"feature_flag_code": listed.code, "is_enabled": True}]},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert PlanFeatureFlag.objects.filter(plan=plan, feature_flag=unlisted, is_enabled=True).exists()


@pytest.mark.django_db
def test_the_batch_keeps_an_existing_config_it_does_not_mention(client, instance_admin):
    """``config`` is free-form data other code writes; a grant save must not wipe it."""
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")
    flag = boolean_flag("charts")
    PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, is_enabled=False, config={"notes": "نگه‌داشته شود"})
    force_instance_admin_login(client, instance_admin)

    response = client.patch(
        grants_url(plan),
        {"grants": [{"feature_flag_code": flag.code, "is_enabled": True}]},
        format="json",
    )

    assert response.status_code == 200, response.content
    grant = PlanFeatureFlag.objects.get(plan=plan, feature_flag=flag)
    assert grant.config == {"notes": "نگه‌داشته شود"}
    assert grant.is_enabled is True


@pytest.mark.django_db
def test_a_missing_grants_list_is_refused(client, instance_admin):
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")
    force_instance_admin_login(client, instance_admin)

    response = client.patch(grants_url(plan), {}, format="json")

    assert response.status_code == 400, response.content
    assert "grants" in response.json(), response.json()


@pytest.mark.django_db
def test_the_batch_is_refused_to_a_plain_user(client, workspace_factory):
    unique = uuid4().hex
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")
    plain = User.objects.create(username=f"plain-{unique}", email=f"plain-{unique}@example.com")
    client.force_login(plain)

    response = client.patch(
        grants_url(plan),
        {"grants": [{"feature_flag_code": "charts", "is_enabled": True}]},
        format="json",
    )

    assert response.status_code in (401, 403), response.content
    assert PlanFeatureFlag.objects.count() == 0


@pytest.mark.django_db
def test_the_batch_is_refused_to_an_anonymous_caller(client):
    plan = Plan.objects.create(code="pro", name="حرفه‌ای")

    response = client.patch(
        grants_url(plan),
        {"grants": [{"feature_flag_code": "charts", "is_enabled": True}]},
        format="json",
    )

    assert response.status_code in (401, 403), response.content
    assert PlanFeatureFlag.objects.count() == 0
