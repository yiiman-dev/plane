# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Two deliveries racing for one wallet balance.

The named acceptance criterion of the SMS phase: two simultaneous sends must not
draw the same money twice. ``wallet.charge_sms`` holds the balance check inside a
transaction that first takes ``SELECT ... FOR UPDATE`` on the spendable account,
so the second transaction blocks and then reads a balance that already reflects
the first charge.

``transaction=True`` is load bearing rather than incidental: the racing writers
are separate connections, and rows written inside an uncommitted test
transaction are invisible to them, so every thread would charge a wallet that
looks full. The threads also have to release together -- a barrier does that --
because the failure this test guards against is only reachable when both balance
checks happen before either commit.

The outcome is the same whichever way they interleave (blocked, or arriving after
the first commits and finding the money gone), which is why the assertions are
exact rather than statistical. Removing the row lock makes both threads pass the
same balance check and the round fails on two ledger entries instead of one.
"""

# Python imports
from threading import Barrier, Thread
from types import SimpleNamespace
from typing import Callable
from uuid import uuid4

# Third party imports
import pytest

# Django imports
from django.db import connection

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
from plane.billing.services import money, wallet
from plane.db.models import (
    NOTIFICATION_CHANNEL_SMS,
    NOTIFICATION_EVENT_MENTION,
    NotificationChannelLog,
    User,
)

pytestmark = pytest.mark.django_db(transaction=True)

RATE_TOMAN = 1_000


def run_concurrently(callables: list[Callable], timeout: int = 30) -> list:
    """Run every callable in its own thread, released at the same moment.

    Anything a worker raised is re-raised in the test thread: an exception inside
    a thread would otherwise be swallowed and leave the test asserting on a table
    that was never written.

    Each worker closes its database connection on the way out. A thread that
    leaves one open holds a session the teardown truncation has to wait for.
    """
    results: list = [None] * len(callables)
    errors: list = []
    barrier = Barrier(len(callables), timeout=timeout)

    def worker(index: int, call: Callable) -> None:
        try:
            barrier.wait()
            results[index] = call()
        except BaseException as exc:  # noqa: BLE001 - handed to the test thread below
            errors.append(exc)
        finally:
            connection.close()

    threads = [
        Thread(target=worker, args=(index, call), name=f"sms-race-{index}") for index, call in enumerate(callables)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=timeout)

    alive = [thread.name for thread in threads if thread.is_alive()]
    assert not alive, f"threads never finished: {alive}"
    assert not errors, errors
    return results


@pytest.fixture
def granter(db):
    unique = uuid4().hex
    return User.objects.create(
        username=f"race-granter-{unique}",
        email=f"race-granter-{unique}@example.com",
    )


@pytest.fixture
def provider_calls(monkeypatch):
    """A recorder in place of the SMS provider, so no HTTP call is attempted."""
    calls = []

    class FakeProvider:
        def send_to_user(self, user, message):
            calls.append(user)
            return SimpleNamespace(ok=True, summary="")

    monkeypatch.setattr(task_module, "get_provider", lambda channel: FakeProvider())
    monkeypatch.setattr(task_module, "build_channel_message", lambda event, data: SimpleNamespace(text="متن"))
    return calls


def plan_with_prices(workspace, prices: dict) -> Plan:
    plan = Plan.objects.create(code=f"race-{uuid4().hex[:6]}", name="پلن مسابقه", sms_prices=prices)
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
        description="شارژ آزمایشی برای تست هم‌زمانی",
        created_by=granter,
        idempotency_key=f"race-fund-{uuid4().hex}",
    )


def make_log(workspace) -> NotificationChannelLog:
    unique = uuid4().hex
    receiver = User.objects.create(
        username=f"race-receiver-{unique}",
        email=f"race-receiver-{unique}@example.com",
    )
    return NotificationChannelLog.objects.create(
        workspace=workspace,
        receiver=receiver,
        channel=NOTIFICATION_CHANNEL_SMS,
        event=NOTIFICATION_EVENT_MENTION,
        entity_name="کار",
    )


def charge_entries(workspace):
    return LedgerEntry.objects.filter(workspace=workspace, source=LedgerSource.SMS_CHARGE)


def test_two_deliveries_racing_for_one_balance_charge_it_once(workspace_factory, granter, provider_calls):
    """One message's worth of money buys exactly one message, however they race.

    Repeated, because a single interleaving proves very little: the race has to
    be run often enough that the threads really do collide.
    """
    for _round in range(5):
        workspace = workspace_factory(name="تیم مسابقه")
        plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
        fund(workspace, RATE_TOMAN, granter)
        logs = [make_log(workspace) for _index in range(2)]

        run_concurrently([lambda log=log: task_module.send_notification_channel_log(log.id) for log in logs])

        assert charge_entries(workspace).count() == 1
        assert money.wallet_balance(workspace) == 0
        statuses = sorted(NotificationChannelLog.objects.filter(workspace=workspace).values_list("status", flat=True))
        assert statuses == ["sent", "skipped"]

        sent = NotificationChannelLog.objects.get(workspace=workspace, status="sent")
        skipped = NotificationChannelLog.objects.get(workspace=workspace, status="skipped")
        assert sent.sms_price_toman == RATE_TOMAN
        # The refused message still records what it would have cost.
        assert skipped.sms_price_toman == RATE_TOMAN
        assert skipped.error_message == "insufficient_wallet_balance"


def test_two_deliveries_that_are_both_affordable_are_both_charged(workspace_factory, granter, provider_calls):
    """The lock must serialise the charges, not refuse the second one.

    Without this, a lock that dropped every concurrent charge -- or a balance
    check that read its own write -- would pass the test above.
    """
    workspace = workspace_factory(name="تیم سرشناس")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
    fund(workspace, RATE_TOMAN * 2, granter)
    logs = [make_log(workspace) for _index in range(2)]

    run_concurrently([lambda log=log: task_module.send_notification_channel_log(log.id) for log in logs])

    assert charge_entries(workspace).count() == 2
    assert money.wallet_balance(workspace) == 0
    statuses = list(NotificationChannelLog.objects.filter(workspace=workspace).values_list("status", flat=True))
    assert statuses == ["sent", "sent"]


def test_two_workspaces_charging_for_the_first_time_do_not_collide_on_the_shared_account(
    workspace_factory, granter, provider_calls
):
    """The first charges on a fresh installation race on a GLOBAL account.

    The SMS expense account belongs to no workspace, so no per workspace lock
    can serialise it: both deliveries look for it, both find nothing and both
    insert, and the unique ``code`` refuses one of them. That loser has to use
    the winner's row rather than fail its message -- a delivery that dies on a
    create race leaves a picked up log row, no message, and an ``IntegrityError``
    in a task nobody is watching.
    """
    first = workspace_factory(name="تیم نخست")
    second = workspace_factory(name="تیم دوم")
    for workspace in (first, second):
        plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
        fund(workspace, RATE_TOMAN * 2, granter)
    logs = [make_log(first), make_log(second)]

    run_concurrently([lambda log=log: task_module.send_notification_channel_log(log.id) for log in logs])

    for workspace in (first, second):
        assert charge_entries(workspace).count() == 1
        assert money.wallet_balance(workspace) == RATE_TOMAN
    statuses = list(
        NotificationChannelLog.objects.filter(id__in=[log.id for log in logs]).values_list("status", flat=True)
    )
    assert statuses == ["sent", "sent"]


def test_money_goes_before_the_message_when_the_provider_fails(workspace_factory, granter, monkeypatch):
    """The deliberate order: a crash between the two costs money, never a free message.

    A failed delivery that took payment is a row an operator can see and refund.
    The opposite order gives away a free message on every crash, and nothing in
    the data says it happened.
    """

    class BrokenProvider:
        def send_to_user(self, user, message):
            raise RuntimeError("provider is down")

    monkeypatch.setattr(task_module, "get_provider", lambda channel: BrokenProvider())
    monkeypatch.setattr(task_module, "build_channel_message", lambda event, data: SimpleNamespace(text="متن"))

    workspace = workspace_factory(name="تیم خرابی درگاه")
    plan_with_prices(workspace, {NOTIFICATION_EVENT_MENTION: RATE_TOMAN})
    fund(workspace, RATE_TOMAN * 3, granter)
    log = make_log(workspace)

    task_module.send_notification_channel_log(log.id)

    log.refresh_from_db()
    assert log.status == "failed"
    # Both sides of the design, in one assertion pair: the message did not go
    # out, and the money did.
    entry = charge_entries(workspace).get()
    assert entry.amount_toman == RATE_TOMAN
    assert money.wallet_balance(workspace) == RATE_TOMAN * 2
