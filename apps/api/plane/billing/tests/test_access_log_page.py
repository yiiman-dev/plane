# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The accountability screen: who read which tenant's money, and when.

The log is only worth writing if somebody can read it, and it is only worth
reading if it cannot be widened by the people it records. These tests pin the
two edges that decide whether the page is an accountability tool or a surface: it
belongs to instance admins alone, and reading it is not itself an audit event --
it returns no balance and no ledger, so it must not manufacture rows that then
appear on the page as if an operator had read a customer's money.
"""

# Python imports
from uuid import uuid4

# Third party imports
import pytest

# Module imports
from plane.billing.tests.conftest import force_instance_admin_login
from plane.billing.models import BillingAccessLog
from plane.db.models import User

URL = "/api/billing/admin/access-log/"


def add_row(workspace, view: str = BillingAccessLog.VIEW_WALLET, viewer=None, ip: str = "10.0.0.1"):
    return BillingAccessLog.objects.create(
        workspace=workspace,
        view=view,
        viewer=viewer,
        ip_address=ip,
        user_agent="plane-ops-console/1.0",
    )


@pytest.mark.django_db
def test_the_page_lists_each_read_with_its_workspace_and_viewer(client, workspace_factory, instance_admin):
    workspace = workspace_factory(name="تیم الف")
    add_row(workspace, BillingAccessLog.VIEW_LEDGER, viewer=instance_admin)
    force_instance_admin_login(client, instance_admin)

    response = client.get(URL)

    assert response.status_code == 200, response.content
    rows = response.json()["results"]
    assert len(rows) == 1
    row = rows[0]
    assert row["view"] == BillingAccessLog.VIEW_LEDGER
    assert row["view_label"] == "دفتر کل"
    assert row["workspace_slug"] == workspace.slug
    assert row["workspace_name"] == "تیم الف"
    assert row["viewer_email"] == instance_admin.email
    assert row["ip_address"] == "10.0.0.1"


@pytest.mark.django_db
def test_the_page_shows_the_newest_read_first(client, workspace_factory, instance_admin):
    """A trail read oldest first is a trail nobody reads to the end."""
    workspace = workspace_factory(name="تیم ب")
    older = add_row(workspace, BillingAccessLog.VIEW_WALLET)
    newer = add_row(workspace, BillingAccessLog.VIEW_LEDGER)
    force_instance_admin_login(client, instance_admin)

    rows = client.get(URL).json()["results"]

    assert [row["id"] for row in rows] == [str(newer.pk), str(older.pk)]


@pytest.mark.django_db
def test_the_page_can_be_narrowed_to_one_kind_of_read(client, workspace_factory, instance_admin):
    workspace = workspace_factory(name="تیم ج")
    add_row(workspace, BillingAccessLog.VIEW_WALLET)
    add_row(workspace, BillingAccessLog.VIEW_LEDGER)
    force_instance_admin_login(client, instance_admin)

    rows = client.get(f"{URL}?view=ledger").json()["results"]

    assert [row["view"] for row in rows] == [BillingAccessLog.VIEW_LEDGER]


@pytest.mark.django_db
def test_the_page_can_be_narrowed_to_one_workspace(client, workspace_factory, instance_admin):
    """Filtering answers "who has been looking at THIS customer", the question a complaint asks."""
    mine = workspace_factory(name="تیم من")
    other = workspace_factory(name="تیم دیگر")
    add_row(mine)
    add_row(other)
    force_instance_admin_login(client, instance_admin)

    rows = client.get(f"{URL}?workspace_slug={mine.slug}").json()["results"]

    assert [row["workspace_slug"] for row in rows] == [mine.slug]


@pytest.mark.django_db
def test_an_unknown_filter_value_matches_nothing_instead_of_failing(client, workspace_factory, instance_admin):
    workspace = workspace_factory(name="تیم د")
    add_row(workspace)
    force_instance_admin_login(client, instance_admin)

    for query in ("view=no-such-view", "workspace_slug=no-such-workspace"):
        response = client.get(f"{URL}?{query}")
        assert response.status_code == 200, response.content
        assert response.json()["results"] == []


@pytest.mark.django_db
def test_a_row_whose_viewer_was_deleted_still_appears_unattributed(client, workspace_factory, instance_admin):
    """``viewer`` is ``SET_NULL`` on purpose: the evidence outlives the account."""
    workspace = workspace_factory(name="تیم ه")
    add_row(workspace, viewer=None)
    force_instance_admin_login(client, instance_admin)

    row = client.get(URL).json()["results"][0]

    assert row["viewer_email"] is None
    assert row["viewer_name"] is None


@pytest.mark.django_db
def test_reading_the_page_is_not_itself_recorded(client, workspace_factory, instance_admin):
    """The page returns no money, so it must not write rows about itself."""
    workspace = workspace_factory(name="تیم و")
    add_row(workspace)
    force_instance_admin_login(client, instance_admin)

    client.get(URL)

    assert BillingAccessLog.objects.count() == 1


@pytest.mark.django_db
def test_the_page_is_refused_to_a_plain_user(client, workspace_factory):
    unique = uuid4().hex
    workspace = workspace_factory(name="تیم ز")
    add_row(workspace)
    plain = User.objects.create(username=f"plain-{unique}", email=f"plain-{unique}@example.com")
    client.force_login(plain)

    response = client.get(URL)

    assert response.status_code in (401, 403), response.content


@pytest.mark.django_db
def test_the_page_is_refused_to_an_anonymous_caller(client, workspace_factory):
    workspace = workspace_factory(name="تیم ح")
    add_row(workspace)

    response = client.get(URL)

    assert response.status_code in (401, 403), response.content
