# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Renewal reminders for workspace admins (phase 5).

Claims pinned here: a reminder goes out on its configured day and only to
active admins; a mark that already passed is not sent late; a mark is sent once
however many times beat runs that day; expired, cancelled or workspace-less
subscriptions get nothing; and the schedule endpoint refuses a day list that
would silently never fire.
"""

from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import uuid4

import pytest

from plane.billing.models import (
    DEFAULT_RENEWAL_NOTICE_DAYS,
    Invoice,
    Plan,
    RenewalNotice,
    RenewalNoticeSchedule,
    Subscription,
    SubscriptionStatus,
)
from plane.billing.services import renewal
from plane.billing.services import tasks as billing_tasks
from plane.billing.tests.conftest import force_instance_admin_login
from plane.db.models import (
    Notification,
    NotificationChannelLog,
    UserNotificationChannel,
    WorkspaceMember,
)

pytestmark = pytest.mark.django_db

# A fixed UTC day, so the test never depends on the wall clock crossing midnight.
TODAY = datetime(2026, 10, 16, 9, 0, tzinfo=dt_timezone.utc).date()


def at_midnight(day) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=dt_timezone.utc)


@pytest.fixture
def plan(db):
    return Plan.objects.create(
        code="renewal-pro",
        name="Pro",
        access_level="admin",
        monthly_price_toman=1_000_000,
        yearly_price_toman=10_000_000,
        per_seat_price_toman=0,
        included_seats=5,
        min_seats=1,
        max_seats=10,
        is_active=True,
    )


@pytest.fixture
def workspace(workspace_factory):
    return workspace_factory(name="تیم تمدید")


@pytest.fixture
def admins(workspace, django_user_model):
    """Two active admins and one inactive admin and one plain member. Only the first two get reminders."""

    def make(role, active=True):
        user = django_user_model.objects.create(
            username=f"renewal-{uuid4().hex}", email=f"renewal-{uuid4().hex}@example.com"
        )
        WorkspaceMember.objects.create(workspace=workspace, member=user, role=role, is_active=active)
        return user

    return [make(20), make(20), make(20, active=False), make(15)]


def subscribe(workspace, plan, *, ends_on, status=SubscriptionStatus.ACTIVE, owner=None):
    return Subscription.objects.create(
        user=owner or workspace.owner,
        plan=plan,
        workspace=workspace,
        status=status,
        starts_at=at_midnight(TODAY - timedelta(days=20)),
        ends_at=at_midnight(ends_on),
    )


def test_default_schedule_is_seven_three_and_one_days():
    assert renewal.get_schedule().days_before == DEFAULT_RENEWAL_NOTICE_DAYS == [7, 3, 1]


def test_days_are_sorted_high_to_low():
    assert renewal.validate_days([1, 7, 3]) == [7, 3, 1]


@pytest.mark.parametrize(
    "days",
    [[], "7", [7, 7], [0], [366], [True], [7.0], [None]],
)
def test_invalid_days_are_rejected(days):
    with pytest.raises(renewal.InvalidSchedule):
        renewal.validate_days(days)


def test_a_reminder_goes_to_active_admins_on_its_day(workspace, plan, admins):
    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=7))

    sent = renewal.send_due_renewal_notices(today=TODAY)

    assert sent == 1
    notices = RenewalNotice.objects.all()
    assert [(n.days_before, n.recipients) for n in notices] == [(7, 2)]
    receivers = set(Notification.objects.values_list("receiver_id", flat=True))
    assert receivers == {admins[0].pk, admins[1].pk}
    note = Notification.objects.first()
    assert note.entity_name == "billing_subscription"
    assert note.data["days_before"] == 7


def test_a_mark_that_already_passed_is_not_sent_late(workspace, plan, admins):
    # Ends in two days: the seven day mark was five days ago, and two is not configured.
    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=2))

    assert renewal.send_due_renewal_notices(today=TODAY) == 0
    assert not RenewalNotice.objects.exists()


def test_a_mark_is_sent_once_when_beat_runs_twice(workspace, plan, admins):
    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=3))

    assert renewal.send_due_renewal_notices(today=TODAY) == 1
    assert renewal.send_due_renewal_notices(today=TODAY) == 0
    assert RenewalNotice.objects.count() == 1
    assert Notification.objects.count() == 2


def test_a_second_period_gets_its_own_reminder(workspace, plan, admins):
    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=1))
    # A renewal extends the same subscription row; the new end date is a new period.
    Subscription.objects.update(ends_at=at_midnight(TODAY + timedelta(days=1)))
    renewal.send_due_renewal_notices(today=TODAY)

    later = TODAY + timedelta(days=30)
    Subscription.objects.update(ends_at=at_midnight(later + timedelta(days=1)))
    assert renewal.send_due_renewal_notices(today=later) == 1
    assert RenewalNotice.objects.count() == 2


def test_each_configured_day_is_its_own_mark(workspace, plan, admins, django_user_model):
    # Two subscriptions in one workspace, one ending on the seven day mark and one on the three day mark.
    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=7))
    other = django_user_model.objects.create(username=f"other-{uuid4().hex}", email=f"other-{uuid4().hex}@example.com")
    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=3), owner=other)

    assert renewal.send_due_renewal_notices(today=TODAY) == 2
    assert sorted(RenewalNotice.objects.values_list("days_before", flat=True)) == [3, 7]


@pytest.mark.parametrize("status", [SubscriptionStatus.EXPIRED, SubscriptionStatus.CANCELLED])
def test_a_subscription_that_is_no_longer_active_gets_nothing(workspace, plan, admins, status):
    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=7), status=status)

    assert renewal.send_due_renewal_notices(today=TODAY) == 0


def test_a_subscription_without_a_workspace_gets_nothing(plan, django_user_model):
    owner = django_user_model.objects.create(username=f"solo-{uuid4().hex}", email=f"solo-{uuid4().hex}@example.com")
    Subscription.objects.create(
        user=owner,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,
        starts_at=at_midnight(TODAY),
        ends_at=at_midnight(TODAY + timedelta(days=7)),
    )

    assert renewal.send_due_renewal_notices(today=TODAY) == 0


def test_a_workspace_without_admins_records_the_mark_with_no_recipients(workspace, plan):
    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=1))

    assert renewal.send_due_renewal_notices(today=TODAY) == 1
    assert RenewalNotice.objects.get().recipients == 0
    assert Notification.objects.count() == 0


def test_beat_task_runs_the_sender(workspace, plan, admins, monkeypatch):
    monkeypatch.setattr(renewal, "send_due_renewal_notices", lambda: 5)

    assert billing_tasks.send_renewal_notices() == 5


def test_beat_schedule_registers_the_renewal_task():
    from plane.celery import app

    entry = app.conf.beat_schedule["send-renewal-notices"]

    assert entry["task"] == billing_tasks.send_renewal_notices.name


@pytest.fixture
def admin_client(client, instance_admin):
    force_instance_admin_login(client, instance_admin)
    return client


def test_schedule_endpoint_returns_the_default_days(admin_client):
    response = admin_client.get("/api/billing/admin/renewal-notifications/")

    assert response.status_code == 200
    assert response.data["days_before"] == [7, 3, 1]


def test_schedule_endpoint_replaces_the_days(admin_client):
    response = admin_client.patch("/api/billing/admin/renewal-notifications/", {"days_before": [14, 2]}, format="json")

    assert response.status_code == 200
    assert response.data["days_before"] == [14, 2]
    assert RenewalNoticeSchedule.objects.get().days_before == [14, 2]


def test_schedule_endpoint_refuses_a_day_that_would_never_fire(admin_client):
    response = admin_client.patch("/api/billing/admin/renewal-notifications/", {"days_before": [7, 7]}, format="json")

    assert response.status_code == 400
    assert "days_before" in response.data
    assert RenewalNoticeSchedule.objects.get().days_before == [7, 3, 1]


def test_schedule_endpoint_is_closed_to_workspace_members(client):
    response = client.get("/api/billing/admin/renewal-notifications/")

    assert response.status_code in (401, 403)


def test_renewal_notice_creates_proforma_invoice_and_links_it(workspace, plan, admins):
    sub = subscribe(workspace, plan, ends_on=TODAY + timedelta(days=7))

    assert renewal.send_due_renewal_notices(today=TODAY) == 1

    notice = RenewalNotice.objects.get()
    assert notice.invoice is not None
    assert notice.invoice.plan == plan
    assert notice.invoice.seats == sub.seats
    assert notice.invoice.cycle == sub.cycle
    assert notice.invoice.due_at == sub.ends_at
    assert notice.invoice.metadata.get("renewal_subscription_id") == str(sub.pk)

    # In-app notifications contain invoice information
    notif = Notification.objects.filter(receiver_id=admins[0].pk).first()
    assert notif is not None
    assert notif.data["invoice_id"] == str(notice.invoice.pk)
    assert notif.data["invoice_number"] == notice.invoice.number
    assert notif.data["total_toman"] == notice.invoice.total_toman


def test_renewal_notice_reuses_existing_proforma_invoice(workspace, plan, admins):
    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=7))

    # Trigger notice on 7-day mark
    assert renewal.send_due_renewal_notices(today=TODAY) == 1
    invoice = RenewalNotice.objects.get().invoice
    assert invoice is not None

    # Advance time to 3-day mark (4 days later)
    day_3 = TODAY + timedelta(days=4)
    assert renewal.send_due_renewal_notices(today=day_3) == 1

    # Should reuse the exact same invoice, not create a duplicate
    notice_3 = RenewalNotice.objects.get(days_before=3)
    assert notice_3.invoice == invoice
    assert Invoice.objects.count() == 1


def test_renewal_notice_dispatches_sms_when_configured(workspace, plan, admins, monkeypatch):
    # Set mobile number on admin
    admin = admins[0]
    admin.mobile_number = "09123456789"
    admin.save(update_fields=["mobile_number"])

    sent_messages = []

    class MockKavenegarProvider:
        def is_configured(self):
            return True

        def send_to_user(self, user, message):
            sent_messages.append((user.pk, message.text))
            from plane.utils.notifications.base import ChannelResult

            return ChannelResult(ok=True)

    monkeypatch.setattr(renewal, "get_provider", lambda ch: MockKavenegarProvider() if ch == "SMS" else None)

    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=7))
    assert renewal.send_due_renewal_notices(today=TODAY) == 1

    assert len(sent_messages) == 1
    assert sent_messages[0][0] == admin.pk
    assert "اشتراک پلن «Pro»" in sent_messages[0][1]
    assert "پیش‌فاکتور تمدید" in sent_messages[0][1]

    # Verify NotificationChannelLog
    channel_log = NotificationChannelLog.objects.filter(receiver=admin, channel="SMS").first()
    assert channel_log is not None
    assert channel_log.status == "sent"
    assert channel_log.event == "billing_renewal"


def test_renewal_notice_skips_sms_when_kavenegar_not_configured(workspace, plan, admins, monkeypatch):
    admin = admins[0]
    admin.mobile_number = "09123456789"
    admin.save(update_fields=["mobile_number"])

    class MockUnconfiguredProvider:
        def is_configured(self):
            return False

    monkeypatch.setattr(renewal, "get_provider", lambda ch: MockUnconfiguredProvider())

    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=7))
    assert renewal.send_due_renewal_notices(today=TODAY) == 1

    channel_log = NotificationChannelLog.objects.filter(receiver=admin, channel="SMS").first()
    assert channel_log is not None
    assert channel_log.status == "skipped"
    assert channel_log.error_message == "Kavenegar is not configured"


def test_renewal_notice_dispatches_bale_bot_when_configured(workspace, plan, admins, monkeypatch):
    admin = admins[0]
    admin.bale_chat_id = "12345678"
    admin.save(update_fields=["bale_chat_id"])
    UserNotificationChannel.objects.create(user=admin, channel="BALE", is_enabled=True)

    sent_bale = []

    class MockBaleProvider:
        def is_configured(self):
            return True

        def send_to_user(self, user, message):
            sent_bale.append((user.pk, message.text))
            from plane.utils.notifications.base import ChannelResult

            return ChannelResult(ok=True)

    monkeypatch.setattr(renewal, "get_provider", lambda ch: MockBaleProvider())

    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=7))
    assert renewal.send_due_renewal_notices(today=TODAY) == 1

    assert len(sent_bale) == 1
    assert "یادآوری سررسید اشتراک پلن «Pro»" in sent_bale[0][1]

    channel_log = NotificationChannelLog.objects.filter(receiver=admin, channel="BALE").first()
    assert channel_log is not None
    assert channel_log.status == "sent"
    assert channel_log.event == "billing_renewal"


def test_renewal_notice_dispatches_email_when_configured(workspace, plan, admins, monkeypatch):
    sent_emails = []

    class MockEmailMsg:
        def __init__(self, subject, body, from_email, to, connection=None):
            self.subject = subject
            self.body = body
            self.to = to

        def send(self):
            sent_emails.append((self.to, self.subject, self.body))

    monkeypatch.setattr(
        "plane.license.utils.instance_value.get_email_configuration",
        lambda: ("smtp.example.com", "user", "pass", "587", "1", "0", "support@plane.so"),
    )
    monkeypatch.setattr("django.core.mail.EmailMultiAlternatives", MockEmailMsg)
    monkeypatch.setattr("django.core.mail.get_connection", lambda **kwargs: None)

    subscribe(workspace, plan, ends_on=TODAY + timedelta(days=7))
    assert renewal.send_due_renewal_notices(today=TODAY) == 1

    assert len(sent_emails) == 2  # 2 active admins
    assert "یادآوری سررسید اشتراک پلن «Pro»" in sent_emails[0][1]
    assert "پیش‌فاکتور تمدید" in sent_emails[0][2]

