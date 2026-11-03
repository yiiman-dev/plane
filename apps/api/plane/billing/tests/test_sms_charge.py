# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Billing the workspace wallet for outbound SMS.

Four claims, one per way this can be wrong: a priced message takes its price, an
unpriced one takes nothing, an empty wallet stops the delivery instead of sending
on credit, and the rate is snapshotted so a later price change cannot rewrite what
the past cost. The last test reads the balance against the ledger, which is the
claim the operator's report rests on.
"""

# Python imports
from types import SimpleNamespace
from uuid import uuid4

# Third party imports
import pytest

# Module imports
from plane.bgtasks import notification_channel_task as task_module
from plane.billing.models import (
    BillingCycle,
    LedgerEntry,
    LedgerSource,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from plane.billing.services import money, sms, wallet
from plane.db.models import (
    NOTIFICATION_CHANNEL_SMS,
    NOTIFICATION_EVENT_MENTION,
    NotificationChannelLog,
    User,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def granter(db):
    unique = uuid4().hex
    return User.objects.create(
        username=f"sms-granter-{unique}",
        email=f"sms-granter-{unique}@example.com",
        first_name="SMS",
        last_name="Granter",
    )


@pytest.fixture
def provider_calls(monkeypatch):
    """Replace the SMS provider with a recorder, so no HTTP call is attempted."""
    calls = []

    class FakeProvider:
        def send_to_user(self, user, message):
            calls.append((user, message))
            return SimpleNamespace(ok=True, summary="")

    monkeypatch.setattr(task_module, "get_provider", lambda channel: FakeProvider())
    monkeypatch.setattr(task_module, "build_channel_message", lambda event, data: SimpleNamespace(text="متن"))
    return calls


def plan_with_prices(workspace, prices: dict) -> Plan:
    """A plan priced per event, subscribed by the workspace."""
    plan = Plan.objects.create(code=f"priced-{uuid4().hex[:6]}", name="پلن پیامک", sms_prices=prices)
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
        description="شارژ آزمایشی برای تست پیامک",
        created_by=granter,
        idempotency_key=f"fund-{uuid4().hex}",
    )


def make_log(workspace=None, event: str = NOTIFICATION_EVENT_MENTION) -> NotificationChannelLog:
    unique = uuid4().hex
    receiver = User.objects.create(
        username=f"sms-receiver-{unique}",
        email=f"sms-receiver-{unique}@example.com",
    )
    return NotificationChannelLog.objects.create(
        workspace=workspace,
        receiver=receiver,
        channel=NOTIFICATION_CHANNEL_SMS,
        event=event,
        entity_name="کار",
    )


def charge_entries(workspace):
    return LedgerEntry.objects.filter(workspace=workspace, source=LedgerSource.SMS_CHARGE)


def test_a_priced_message_takes_its_price_and_is_delivered(workspace_factory, granter, provider_calls):
    workspace = workspace_factory(name="تیم پیامک")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: 1_200})
    fund(workspace, 5_000, granter)
    log = make_log(workspace=workspace)

    task_module.send_notification_channel_log(log.id)

    log.refresh_from_db()
    assert log.status == "sent"
    assert log.sms_price_toman == 1_200
    assert len(provider_calls) == 1
    assert money.wallet_balance(workspace) == 3_800
    entry = charge_entries(workspace).get()
    assert entry.amount_toman == 1_200
    assert str(log.id) in entry.description


def test_an_unpriced_event_is_delivered_without_touching_the_wallet(workspace_factory, provider_calls):
    """An installation that prices nothing keeps delivering exactly as before."""
    workspace = workspace_factory(name="تیم بی‌قیمت")
    plan_with_prices(workspace, {})
    # Deliberately no wallet funding: an unpriced event must not need a balance.
    log = make_log(workspace=workspace)

    task_module.send_notification_channel_log(log.id)

    log.refresh_from_db()
    assert log.status == "sent"
    assert log.sms_price_toman is None
    assert charge_entries(workspace).count() == 0


def test_an_empty_wallet_skips_the_delivery_instead_of_sending_on_credit(workspace_factory, provider_calls):
    workspace = workspace_factory(name="تیم بی‌موجودی")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: 1_200})
    log = make_log(workspace=workspace)

    task_module.send_notification_channel_log(log.id)

    log.refresh_from_db()
    assert log.status == "skipped"
    assert log.error_message == sms.INSUFFICIENT_BALANCE_REASON
    # The price is still recorded: the row answers "what would this have cost".
    assert log.sms_price_toman == 1_200
    assert provider_calls == []
    assert charge_entries(workspace).count() == 0
    assert money.wallet_balance(workspace) == 0


def test_the_rate_is_snapshotted_so_a_price_change_does_not_rewrite_the_past(
    workspace_factory, granter, provider_calls
):
    workspace = workspace_factory(name="تیم نرخ")
    plan = plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: 1_200})
    fund(workspace, 5_000, granter)
    log = make_log(workspace=workspace)

    task_module.send_notification_channel_log(log.id)

    plan.sms_prices = {NOTIFICATION_EVENT_MENTION: 900}
    plan.save(update_fields=["sms_prices", "updated_at"])

    log.refresh_from_db()
    assert log.sms_price_toman == 1_200
    assert charge_entries(workspace).get().amount_toman == 1_200


def test_a_log_without_a_workspace_is_delivered_and_never_charged(workspace_factory, provider_calls):
    """Rows queued before the workspace was carried onto the log must not break."""
    log = make_log(workspace=None)

    task_module.send_notification_channel_log(log.id)

    log.refresh_from_db()
    assert log.status == "sent"
    assert LedgerEntry.objects.count() == 0


def test_a_redelivered_log_is_never_charged_twice(workspace_factory, granter, provider_calls):
    workspace = workspace_factory(name="تیم تکرار")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: 1_200})
    fund(workspace, 5_000, granter)
    log = make_log(workspace=workspace)

    task_module.send_notification_channel_log(log.id)
    task_module.send_notification_channel_log(log.id)

    assert charge_entries(workspace).count() == 1
    assert money.wallet_balance(workspace) == 3_800


def test_the_service_replays_the_charge_for_the_same_log(workspace_factory, granter):
    """The idempotency key is the log id, so a re-queued log costs nothing extra."""
    workspace = workspace_factory(name="تیم replay")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: 1_500})
    fund(workspace, 5_000, granter)
    log = make_log(workspace=workspace)

    first = sms.charge_for_log(log)
    second = sms.charge_for_log(log)

    assert first.entry is not None
    assert second.entry is not None
    assert first.entry.id == second.entry.id
    assert charge_entries(workspace).count() == 1
    assert money.wallet_balance(workspace) == 3_500


@pytest.mark.parametrize(
    "prices",
    [
        {},
        {NOTIFICATION_EVENT_MENTION: 0},
        # A negative price would move money the wrong way, so it is not a price.
        {NOTIFICATION_EVENT_MENTION: -500},
        {NOTIFICATION_EVENT_MENTION: "بهای نامعتبر"},
    ],
)
def test_an_unusable_price_is_zero_rather_than_a_crash(workspace_factory, prices):
    workspace = workspace_factory(name="تیم قیمت نامعتبر")
    plan_with_prices(workspace, prices)

    assert sms.price_for_event(workspace, NOTIFICATION_EVENT_MENTION) == 0


def test_the_queued_log_carries_the_workspace_that_will_be_billed(workspace_factory):
    """Without this the charge silently never happens: no workspace, no payer.

    The queue step copies in app notifications onto the external channels, and the
    in app row is the only place the workspace is known. Losing it here would look
    exactly like an installation that prices nothing.
    """
    from plane.db.models import (
        NOTIFICATION_EVENT_MENTION,
        Notification,
        NotificationChannelPreference,
        UserNotificationChannel,
    )

    workspace = workspace_factory(name="تیم صف")
    unique = uuid4().hex
    receiver = User.objects.create(
        username=f"queued-{unique}",
        email=f"queued-{unique}@example.com",
        mobile_number="00989123456789",
    )
    UserNotificationChannel.objects.create(user=receiver, channel=NOTIFICATION_CHANNEL_SMS, is_enabled=True)
    NotificationChannelPreference.objects.create(
        user=receiver, channel=NOTIFICATION_CHANNEL_SMS, event=NOTIFICATION_EVENT_MENTION, is_enabled=True
    )
    notification = Notification.objects.create(
        workspace=workspace,
        receiver=receiver,
        entity_name="کار",
        data={"issue": {"event": "mention", "identifier": "PRJ-1", "name": "کار"}},
    )

    queued = task_module.queue_notification_channel_logs([notification])

    assert queued == 1
    log = NotificationChannelLog.objects.get(receiver=receiver)
    assert log.workspace_id == workspace.id


def test_the_balance_the_report_shows_is_the_ledger(workspace_factory, granter, provider_calls):
    """The operator's cost report reads the ledger; this is that claim, in data."""
    workspace = workspace_factory(name="تیم گزارش")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: 700})
    fund(workspace, 10_000, granter)

    for _index in range(4):
        task_module.send_notification_channel_log(make_log(workspace=workspace).id)

    charged = sum(entry.amount_toman for entry in charge_entries(workspace))
    assert charged == 2_800
    assert money.wallet_balance(workspace) == 10_000 - 2_800
    assert NotificationChannelLog.objects.filter(workspace=workspace, status="sent").count() == 4
