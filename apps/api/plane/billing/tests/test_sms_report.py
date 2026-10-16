# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The admin SMS cost report: what the wallets paid, against what was delivered.

One claim per way the report can lie: a total that does not agree with the
ledger, a charge with no delivery beside it, today's price shown as if it were
the price that was charged, a refused message counted as a cost, a workspace
whose wallet the report would create by looking at it, and a read that leaves no
audit row. The reconciliation test computes the ledger side independently of the
endpoint, so it checks the report against the database rather than against
itself.
"""

# Python imports
from types import SimpleNamespace
from uuid import uuid4

# Third party imports
import pytest

# Django imports
from django.db.models import Sum

# Module imports
from plane.bgtasks import notification_channel_task as task_module
from plane.billing.models import (
    BillingAccessLog,
    BillingCycle,
    LedgerAccount,
    LedgerEntry,
    LedgerSource,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from plane.billing.services import wallet
from plane.db.models import (
    NOTIFICATION_CHANNEL_BALE,
    NOTIFICATION_CHANNEL_SMS,
    NOTIFICATION_EVENT_MENTION,
    NotificationChannelLog,
    User,
    WorkspaceMember,
)

pytestmark = pytest.mark.django_db

REPORT_URL = "/api/billing/admin/sms-report/"
RATE_TOMAN = 1_000


@pytest.fixture
def granter(db):
    unique = uuid4().hex
    return User.objects.create(
        username=f"report-granter-{unique}",
        email=f"report-granter-{unique}@example.com",
    )


def plan_with_prices(workspace, prices: dict) -> Plan:
    """A plan priced per event, subscribed by the workspace."""
    plan = Plan.objects.create(code=f"report-{uuid4().hex[:6]}", name="پلن گزارش", sms_prices=prices)
    Subscription.objects.create(
        user=workspace.owner,
        workspace=workspace,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        seats=1,
        cycle=BillingCycle.MONTHLY,
    )
    return plan


def fund(workspace, amount_toman: int, granter) -> None:
    wallet.grant_from_admin(
        workspace=workspace,
        amount_toman=amount_toman,
        description="شارژ آزمایشی برای تست گزارش",
        created_by=granter,
        idempotency_key=f"report-fund-{uuid4().hex}",
    )


def make_log(workspace, channel: str = NOTIFICATION_CHANNEL_SMS, event: str = NOTIFICATION_EVENT_MENTION):
    unique = uuid4().hex
    receiver = User.objects.create(
        username=f"report-receiver-{unique}",
        email=f"report-receiver-{unique}@example.com",
    )
    return NotificationChannelLog.objects.create(
        workspace=workspace,
        receiver=receiver,
        channel=channel,
        event=event,
        entity_name="کار",
    )


def deliver(log) -> None:
    """Run the real delivery task with the provider replaced by a stub."""
    task_module.send_notification_channel_log(log.id)


@pytest.fixture(autouse=True)
def silent_provider(monkeypatch):
    """A recorder in place of the provider, so no test can reach the network."""

    class FakeProvider:
        def send_to_user(self, user, message):
            return SimpleNamespace(ok=True, summary="")

    monkeypatch.setattr(task_module, "get_provider", lambda channel: FakeProvider())
    monkeypatch.setattr(task_module, "build_channel_message", lambda event, data: SimpleNamespace(text="متن"))


def report(client, workspace=None, **params) -> dict:
    query = {"workspace_slug": workspace.slug} if workspace is not None else {}
    response = client.get(REPORT_URL, {**query, **params})
    assert response.status_code == 200, response.content[:500]
    return response.json()


def only_row(client, workspace=None) -> dict:
    rows = report(client, workspace)["results"]
    assert len(rows) == 1, rows
    return rows[0]


def ledger_charges(workspace) -> int:
    """What the ledger says left this wallet for SMS, summed independently."""
    return (
        LedgerEntry.objects.filter(workspace=workspace, source=LedgerSource.SMS_CHARGE).aggregate(
            total=Sum("amount_toman")
        )["total"]
        or 0
    )


def test_a_workspace_member_is_refused(client, workspace_factory):
    """The report is over every tenant's money, so it is instance admin only."""
    workspace = workspace_factory(name="تیم عضو")
    member = User.objects.create(
        username=f"report-member-{uuid4().hex}", email=f"report-member-{uuid4().hex}@example.com"
    )
    WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
    client.force_login(member)

    assert client.get(REPORT_URL).status_code == 403


def test_an_anonymous_request_is_refused(client, workspace_factory):
    workspace_factory(name="تیم ناشناس")

    assert client.get(REPORT_URL).status_code in (401, 403)


def test_the_report_reconciles_with_the_ledger(client, workspace_factory, granter, instance_admin):
    workspace = workspace_factory(name="تیم گزارش")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
    fund(workspace, RATE_TOMAN * 5, granter)
    for _index in range(3):
        deliver(make_log(workspace))

    client.force_login(instance_admin)
    row = only_row(client, workspace)

    assert row["workspace_slug"] == workspace.slug
    assert row["sent_count"] == 3
    assert row["failed_count"] == 0
    assert row["skipped_count"] == 0
    # Both sides of the reconciliation, from two different places: the report's
    # own figure and a sum taken straight from the ledger rows.
    assert row["charged_toman"] == ledger_charges(workspace) == 3 * RATE_TOMAN
    assert row["delivered_toman"] == 3 * RATE_TOMAN
    assert row["unexplained_toman"] == 0


def test_a_charge_with_no_delivery_row_is_reported_as_unexplained(client, workspace_factory, granter, instance_admin):
    """Money out of the wallet with nothing to show for it is the column that matters.

    Built by charging a log id that has no row at all, which is the crash
    between the charge and the status write that the charge-before-send order
    deliberately leaves behind.
    """
    workspace = workspace_factory(name="تیم گم‌شده")
    fund(workspace, RATE_TOMAN * 2, granter)
    wallet.charge_sms(workspace=workspace, amount_toman=RATE_TOMAN, log_id=uuid4())

    client.force_login(instance_admin)
    row = only_row(client)

    assert row["charged_toman"] == RATE_TOMAN
    assert row["delivered_toman"] == 0
    assert row["lost_toman"] == 0
    assert row["unexplained_toman"] == RATE_TOMAN
    assert row["sent_count"] == 0


def test_a_charge_for_a_message_that_failed_is_shown_as_lost(
    client, workspace_factory, granter, instance_admin, monkeypatch
):
    """Paid and not delivered: the row an operator refunds from."""

    class BrokenProvider:
        def send_to_user(self, user, message):
            raise RuntimeError("provider is down")

    monkeypatch.setattr(task_module, "get_provider", lambda channel: BrokenProvider())
    monkeypatch.setattr(task_module, "build_channel_message", lambda event, data: SimpleNamespace(text="متن"))

    workspace = workspace_factory(name="تیم خرابی")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
    fund(workspace, RATE_TOMAN * 2, granter)
    deliver(make_log(workspace))

    client.force_login(instance_admin)
    row = only_row(client, workspace)

    assert row["failed_count"] == 1
    assert row["lost_toman"] == RATE_TOMAN
    assert row["charged_toman"] == RATE_TOMAN
    assert row["unexplained_toman"] == 0


def test_todays_rate_is_shown_beside_the_snapshotted_one(client, workspace_factory, granter, instance_admin):
    """A price change must not rewrite what the past cost, and must still be visible."""
    workspace = workspace_factory(name="تیم نرخ")
    plan = plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
    fund(workspace, RATE_TOMAN * 2, granter)
    deliver(make_log(workspace))

    plan.sms_prices = {NOTIFICATION_EVENT_MENTION: RATE_TOMAN * 3}
    plan.save(update_fields=["sms_prices", "updated_at"])

    client.force_login(instance_admin)
    row = only_row(client, workspace)

    assert row["delivered_toman"] == RATE_TOMAN
    assert row["charged_toman"] == RATE_TOMAN
    event = row["events"][0]
    assert event["event"] == NOTIFICATION_EVENT_MENTION
    assert event["count"] == 1
    assert event["snapshotted_toman"] == RATE_TOMAN
    assert event["current_rate_toman"] == RATE_TOMAN * 3


def test_a_refused_message_is_counted_but_never_charged(client, workspace_factory, instance_admin):
    """An empty wallet refuses delivery; the report must not call that a cost."""
    workspace = workspace_factory(name="تیم بدون موجودی")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
    deliver(make_log(workspace))

    client.force_login(instance_admin)
    row = only_row(client, workspace)

    assert row["skipped_count"] == 1
    assert row["refused_toman"] == RATE_TOMAN
    assert row["charged_toman"] == 0
    assert row["delivered_toman"] == 0
    assert row["unexplained_toman"] == 0


def test_reading_the_report_does_not_create_a_wallet(client, workspace_factory, instance_admin):
    """A report is a read: it must not leave a wallet account behind for a tenant that has none."""
    workspace = workspace_factory(name="تیم بی‌کیف")
    plan_with_prices(workspace, {})
    deliver(make_log(workspace))
    assert LedgerAccount.objects.filter(workspace=workspace).count() == 0

    client.force_login(instance_admin)
    row = only_row(client, workspace)

    assert row["sent_count"] == 1
    assert row["charged_toman"] == 0
    assert LedgerAccount.objects.filter(workspace=workspace).count() == 0


def test_a_channel_that_is_not_sms_is_not_in_the_report(client, workspace_factory, instance_admin):
    """The report is about SMS spend, so another channel's messages do not appear."""
    workspace = workspace_factory(name="تیم بله")
    make_log(workspace, channel=NOTIFICATION_CHANNEL_BALE)

    client.force_login(instance_admin)

    assert report(client)["results"] == []


def test_the_report_is_audited_once_per_workspace_shown(client, workspace_factory, granter, instance_admin):
    """Every tenant whose figures the page hands over gets a trail row."""
    first = workspace_factory(name="تیم الف")
    second = workspace_factory(name="تیم ب")
    for workspace in (first, second):
        plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
        fund(workspace, RATE_TOMAN, granter)
        deliver(make_log(workspace))

    client.force_login(instance_admin)
    report(client)

    rows = BillingAccessLog.objects.all()
    assert rows.count() == 2
    assert {row.workspace_id for row in rows} == {first.pk, second.pk}
    assert {row.view for row in rows} == {BillingAccessLog.VIEW_LEDGER}
    assert {row.viewer_id for row in rows} == {instance_admin.pk}


def test_the_workspace_filter_narrows_both_the_report_and_the_trail(client, workspace_factory, granter, instance_admin):
    """One filter, two effects: what is shown and what is recorded as read.

    A trail that logged every tenant on a filtered read would overstate what the
    operator actually saw; a report that showed every tenant would ignore the
    filter.
    """
    first = workspace_factory(name="تیم الف")
    second = workspace_factory(name="تیم ب")
    for workspace in (first, second):
        plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
        fund(workspace, RATE_TOMAN, granter)
        deliver(make_log(workspace))

    client.force_login(instance_admin)
    payload = report(client, second)

    assert [row["workspace_slug"] for row in payload["results"]] == [second.slug]
    assert list(BillingAccessLog.objects.values_list("workspace_id", flat=True)) == [second.pk]
