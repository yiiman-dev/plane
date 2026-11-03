# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The ambiguous payment queue (M5).

The last allowed verification attempt that still cannot say whether the payer
was charged parks the amount in the workspace's hold account. The workspace
cannot spend it, the instance admin decides what it was, and beat releases
whatever nobody decided on after ninety days so the money is never lost.
"""

# Python imports
from datetime import timedelta
from uuid import uuid4

# Third party imports
import pytest

# Django imports
from django.utils import timezone

# Module imports
from plane.billing.gateways.base import GatewayStatus, GatewayUnavailable, VerifyResult
from plane.billing.models import (
    BillingCycle,
    InvoiceStatus,
    LedgerEntry,
    LedgerSource,
    PaymentTransaction,
    Plan,
    Subscription,
    SubscriptionStatus,
    TransactionStatus,
)
from plane.billing.services import hold as hold_service
from plane.billing.services import money
from plane.billing.services import payment as payment_service
from plane.billing.services import tasks as billing_tasks
from plane.billing.tests.conftest import make_gateway, force_instance_admin_login
from plane.billing.tests.gateways_stub import StubAdapter
from plane.billing.tests.test_payment_service import install_adapters, paid

pytestmark = pytest.mark.django_db

# The attempt counter a transaction carries when the NEXT callback is the last
# one the retry policy allows.
LAST_ATTEMPT = billing_tasks.MAX_VERIFY_ATTEMPTS - 1


@pytest.fixture
def payer(django_user_model):
    return django_user_model.objects.create_user(
        email="hold-payer@example.com", username="hold-payer", password="password1234"
    )


@pytest.fixture
def plan(db):
    return Plan.objects.create(
        code="hold-pro",
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
    return workspace_factory(name="تیم قفل")


@pytest.fixture
def gateway(db):
    return make_gateway("zarinpal")


@pytest.fixture
def no_retry(monkeypatch):
    """Keep celery out and record which transactions asked for a retry."""
    calls = []
    monkeypatch.setattr(
        payment_service, "schedule_verification_retry", lambda transaction, delay=None: calls.append(transaction.pk)
    )
    return calls


def make_transaction(payer, plan, workspace=None, *, attempts=LAST_ATTEMPT, token=None):
    token = token or f"HOLD-{uuid4().hex[:8]}"
    invoice = payment_service.issue_invoice(
        user=payer,
        plan=plan,
        seats=1,
        cycle=BillingCycle.MONTHLY,
        workspace_slug=workspace.slug if workspace is not None else "",
    )
    return PaymentTransaction.objects.create(
        invoice=invoice,
        user=payer,
        gateway_code="zarinpal",
        gateway_token=token,
        amount_toman=invoice.total_toman,
        status=TransactionStatus.PROCESSING,
        attempts=attempts,
        callback_payload={"Authority": token, "Status": "OK"},
    )


def install_stub(monkeypatch, transaction, *, verify_result=None, verify_error=None):
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter(
            "zarinpal", verify_result=verify_result, verify_error=verify_error, token=transaction.gateway_token
        ),
    )


def callback(transaction):
    return payment_service.process_callback("zarinpal", transaction.callback_payload, transaction=transaction)


def processing():
    return VerifyResult(status=GatewayStatus.PROCESSING, message="still processing")


def failed():
    return VerifyResult(status=GatewayStatus.FAILED, message="declined by the bank")


def park(monkeypatch, payer, plan, workspace=None):
    """A transaction that has just been parked by its final ambiguous attempt."""
    transaction = make_transaction(payer, plan, workspace)
    install_stub(monkeypatch, transaction, verify_result=processing())
    callback(transaction)
    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.HELD
    return transaction


def hold_entries(transaction):
    return LedgerEntry.objects.filter(transaction=transaction, source=LedgerSource.HOLD)


# ----------------------------------------------------------------- parking


def test_the_final_ambiguous_attempt_parks_the_money_in_the_hold(
    payer, plan, workspace, gateway, monkeypatch, no_retry
):
    transaction = make_transaction(payer, plan, workspace)
    install_stub(monkeypatch, transaction, verify_result=processing())

    result = callback(transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.HELD
    assert transaction.attempts == billing_tasks.MAX_VERIFY_ATTEMPTS
    assert transaction.held_at is not None
    assert result["status"] == TransactionStatus.HELD
    # the money is withheld from the workspace, not handed to it
    assert money.wallet_hold_balance(workspace) == transaction.amount_toman
    assert money.wallet_balance(workspace) == 0
    entry = LedgerEntry.objects.get(transaction=transaction)
    assert entry.source == LedgerSource.HOLD
    assert entry.workspace_id == workspace.pk
    assert entry.invoice_id == transaction.invoice_id
    assert entry.idempotency_key == hold_service.hold_key(transaction)
    # a parked payment is not retried any more
    assert no_retry == []


def test_an_attempt_before_the_last_one_still_retries(payer, plan, workspace, gateway, monkeypatch, no_retry):
    transaction = make_transaction(payer, plan, workspace, attempts=LAST_ATTEMPT - 1)
    install_stub(monkeypatch, transaction, verify_result=processing())

    callback(transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.PROCESSING
    assert transaction.held_at is None
    assert money.wallet_hold_balance(workspace) == 0
    assert no_retry == [transaction.pk]


def test_a_gateway_outage_on_the_final_attempt_parks_too(payer, plan, workspace, gateway, monkeypatch, no_retry):
    transaction = make_transaction(payer, plan, workspace)
    install_stub(monkeypatch, transaction, verify_error=GatewayUnavailable("gateway timed out"))

    callback(transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.HELD
    assert "timed out" in transaction.failure_reason
    assert money.wallet_hold_balance(workspace) == transaction.amount_toman
    assert no_retry == []


def test_parking_twice_posts_one_hold(payer, plan, workspace, gateway, monkeypatch, no_retry):
    transaction = park(monkeypatch, payer, plan, workspace)

    callback(transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.HELD
    assert hold_entries(transaction).count() == 1
    assert money.wallet_hold_balance(workspace) == transaction.amount_toman


def test_an_explicit_failure_on_the_final_attempt_moves_no_money(
    payer, plan, workspace, gateway, monkeypatch, no_retry
):
    """The gateway says the payer was not charged, so there is nothing to withhold or refund."""
    transaction = make_transaction(payer, plan, workspace)
    install_stub(monkeypatch, transaction, verify_result=failed())

    callback(transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.FAILED
    assert transaction.held_at is None
    assert LedgerEntry.objects.filter(transaction=transaction).count() == 0
    assert money.wallet_balance(workspace) == 0
    assert money.wallet_hold_balance(workspace) == 0


def test_a_workspace_less_order_is_parked_without_a_ledger_entry(payer, plan, gateway, monkeypatch, no_retry):
    transaction = make_transaction(payer, plan, workspace=None)
    install_stub(monkeypatch, transaction, verify_result=processing())

    callback(transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.HELD
    assert transaction.held_at is not None
    assert LedgerEntry.objects.filter(transaction=transaction).count() == 0


# ------------------------------------------------------------ admin decisions


def test_release_credits_the_wallet_and_closes_the_payment(
    payer, plan, workspace, gateway, monkeypatch, no_retry, instance_admin
):
    transaction = park(monkeypatch, payer, plan, workspace)

    entry = hold_service.release_held_payment(
        transaction, description="درگاه تسویه را تأیید کرد", created_by=instance_admin
    )

    assert entry.source == LedgerSource.RELEASE_HOLD
    assert entry.created_by_id == instance_admin.pk
    assert entry.transaction_id == transaction.pk
    assert money.wallet_balance(workspace) == transaction.amount_toman
    assert money.wallet_hold_balance(workspace) == 0
    transaction.refresh_from_db()
    transaction.invoice.refresh_from_db()
    assert transaction.status == TransactionStatus.REVERSED
    assert transaction.invoice.status == InvoiceStatus.REFUND


def test_reject_closes_the_hold_without_crediting_the_wallet(
    payer, plan, workspace, gateway, monkeypatch, no_retry, instance_admin
):
    transaction = park(monkeypatch, payer, plan, workspace)
    hold = hold_entries(transaction).get()

    entry = hold_service.reject_held_payment(
        transaction, description="بانک مبلغ را برگشت زده", created_by=instance_admin
    )

    assert entry.source == LedgerSource.HOLD_CLOSED
    assert entry.reversal_of_id == hold.pk
    assert money.wallet_balance(workspace) == 0
    assert money.wallet_hold_balance(workspace) == 0
    transaction.refresh_from_db()
    transaction.invoice.refresh_from_db()
    assert transaction.status == TransactionStatus.FAILED
    assert transaction.invoice.status == InvoiceStatus.CANCELLED


def test_decisions_refuse_a_payment_that_is_not_held(payer, plan, workspace, gateway, monkeypatch, instance_admin):
    transaction = make_transaction(payer, plan, workspace)

    with pytest.raises(hold_service.NotHeld):
        hold_service.release_held_payment(transaction, description="بی‌دلیل", created_by=instance_admin)
    with pytest.raises(hold_service.NotHeld):
        hold_service.reject_held_payment(transaction, description="بی‌دلیل", created_by=instance_admin)
    with pytest.raises(hold_service.NotHeld):
        hold_service.retry_held_payment(transaction, created_by=instance_admin)


def test_a_decision_needs_a_reason(payer, plan, workspace, gateway, monkeypatch, no_retry, instance_admin):
    transaction = park(monkeypatch, payer, plan, workspace)

    with pytest.raises(hold_service.DescriptionRequired):
        hold_service.release_held_payment(transaction, description="   ", created_by=instance_admin)
    with pytest.raises(hold_service.DescriptionRequired):
        hold_service.reject_held_payment(transaction, description="", created_by=instance_admin)

    assert money.wallet_hold_balance(workspace) == transaction.amount_toman
    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.HELD


def test_a_workspace_less_release_only_closes_the_payment(payer, plan, gateway, monkeypatch, no_retry, instance_admin):
    transaction = park(monkeypatch, payer, plan, workspace=None)

    entry = hold_service.release_held_payment(transaction, description="بدون ورک‌اسپیس", created_by=instance_admin)

    assert entry is None
    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.REVERSED


# ----------------------------------------------------------------- retry


def test_a_retry_that_pays_activates_the_plan_and_closes_the_hold(
    payer, plan, workspace, gateway, monkeypatch, no_retry, instance_admin
):
    transaction = park(monkeypatch, payer, plan, workspace)
    install_stub(monkeypatch, transaction, verify_result=paid(transaction.amount_toman, ref_id="ZR-HOLD"))

    result = hold_service.retry_held_payment(transaction, created_by=instance_admin)

    assert result["status"] == TransactionStatus.PAID
    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.PAID
    assert transaction.gateway_ref_id == "ZR-HOLD"
    # the money became a plan, so it is neither held nor spendable
    assert money.wallet_hold_balance(workspace) == 0
    assert money.wallet_balance(workspace) == 0
    closed = LedgerEntry.objects.get(transaction=transaction, source=LedgerSource.HOLD_CLOSED)
    assert closed.reversal_of_id == hold_entries(transaction).get().pk
    assert Subscription.objects.filter(
        workspace=workspace, plan=plan, status=SubscriptionStatus.ACTIVE, source_transaction=transaction
    ).exists()


def test_a_retry_that_stays_ambiguous_keeps_the_hold_and_re_enters_the_retry_loop(
    payer, plan, workspace, gateway, monkeypatch, no_retry, instance_admin
):
    transaction = park(monkeypatch, payer, plan, workspace)
    install_stub(monkeypatch, transaction, verify_result=processing())

    hold_service.retry_held_payment(transaction, created_by=instance_admin)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.PROCESSING
    assert transaction.attempts == 1
    assert no_retry == [transaction.pk]
    assert hold_entries(transaction).count() == 1
    assert money.wallet_hold_balance(workspace) == transaction.amount_toman


def test_a_retry_the_gateway_rejects_closes_the_hold(
    payer, plan, workspace, gateway, monkeypatch, no_retry, instance_admin
):
    transaction = park(monkeypatch, payer, plan, workspace)
    install_stub(monkeypatch, transaction, verify_result=failed())

    hold_service.retry_held_payment(transaction, created_by=instance_admin)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.FAILED
    assert money.wallet_hold_balance(workspace) == 0
    assert money.wallet_balance(workspace) == 0
    assert LedgerEntry.objects.filter(transaction=transaction, source=LedgerSource.HOLD_CLOSED).exists()


# ------------------------------------------------------------------ beat


def test_beat_releases_holds_older_than_ninety_days(payer, plan, workspace, gateway, monkeypatch, no_retry):
    stale = park(monkeypatch, payer, plan, workspace)
    fresh = park(monkeypatch, payer, plan, workspace)
    PaymentTransaction.objects.filter(pk=stale.pk).update(
        held_at=timezone.now() - timedelta(days=hold_service.HOLD_RELEASE_AFTER_DAYS + 1)
    )
    PaymentTransaction.objects.filter(pk=fresh.pk).update(held_at=timezone.now() - timedelta(days=10))

    released = billing_tasks.release_expired_holds()

    assert released == 1
    stale.refresh_from_db()
    fresh.refresh_from_db()
    assert stale.status == TransactionStatus.REVERSED
    assert fresh.status == TransactionStatus.HELD
    assert money.wallet_balance(workspace) == stale.amount_toman
    assert money.wallet_hold_balance(workspace) == fresh.amount_toman


def test_beat_schedule_registers_the_hold_release_task():
    from plane.celery import app

    entry = app.conf.beat_schedule["release-expired-payment-holds"]

    assert entry["task"] == billing_tasks.release_expired_holds.name


def test_the_verification_retry_leaves_held_payments_alone(payer, plan, workspace, gateway, monkeypatch, no_retry):
    transaction = park(monkeypatch, payer, plan, workspace)
    PaymentTransaction.objects.filter(pk=transaction.pk).update(
        attempts=0, created_at=timezone.now() - timedelta(hours=1)
    )
    seen = []
    monkeypatch.setattr(
        payment_service, "process_callback", lambda code, payload, transaction=None: seen.append(transaction.pk)
    )

    assert billing_tasks.retry_pending_verifications() == 0
    assert seen == []


# ------------------------------------------------------------- endpoints


@pytest.fixture
def admin_client(client, instance_admin):
    force_instance_admin_login(client, instance_admin)
    return client


def test_the_queue_lists_held_payments_with_their_age(
    payer, plan, workspace, gateway, monkeypatch, no_retry, admin_client
):
    held = park(monkeypatch, payer, plan, workspace)
    PaymentTransaction.objects.filter(pk=held.pk).update(held_at=timezone.now() - timedelta(days=3))
    make_transaction(payer, plan, workspace)  # still processing, not queued

    response = admin_client.get("/api/billing/admin/transactions/queued/")

    assert response.status_code == 200
    rows = response.data["results"]
    assert [row["id"] for row in rows] == [str(held.pk)]
    row = rows[0]
    assert row["status"] == TransactionStatus.HELD
    assert row["age_days"] == 3
    assert row["attempts"] == billing_tasks.MAX_VERIFY_ATTEMPTS
    assert row["amount_toman"] == held.amount_toman
    assert row["workspace_slug"] == workspace.slug
    assert row["workspace_name"] == workspace.name
    assert row["invoice_number"] == held.invoice.number
    assert row["failure_reason"]
    assert row["auto_release_at"] is not None


def test_release_endpoint_credits_the_wallet(payer, plan, workspace, gateway, monkeypatch, no_retry, admin_client):
    held = park(monkeypatch, payer, plan, workspace)

    response = admin_client.post(
        f"/api/billing/admin/transactions/{held.pk}/release-hold/",
        {"description": "درگاه تسویه را تأیید کرد"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["status"] == TransactionStatus.REVERSED
    assert money.wallet_balance(workspace) == held.amount_toman


def test_release_endpoint_requires_a_description(payer, plan, workspace, gateway, monkeypatch, no_retry, admin_client):
    held = park(monkeypatch, payer, plan, workspace)

    response = admin_client.post(f"/api/billing/admin/transactions/{held.pk}/release-hold/", {}, format="json")

    assert response.status_code == 400
    assert money.wallet_balance(workspace) == 0


def test_decision_endpoints_answer_409_for_a_payment_that_is_not_held(payer, plan, workspace, gateway, admin_client):
    transaction = make_transaction(payer, plan, workspace)
    body = {"description": "بی‌دلیل"}

    for action in ("release-hold", "reject-hold", "retry"):
        response = admin_client.post(f"/api/billing/admin/transactions/{transaction.pk}/{action}/", body, format="json")
        assert response.status_code == 409, action


def test_decision_endpoints_answer_404_for_an_unknown_payment(admin_client):
    response = admin_client.post(
        f"/api/billing/admin/transactions/{uuid4()}/reject-hold/", {"description": "x"}, format="json"
    )

    assert response.status_code == 404


def test_reject_endpoint_closes_the_hold(payer, plan, workspace, gateway, monkeypatch, no_retry, admin_client):
    held = park(monkeypatch, payer, plan, workspace)

    response = admin_client.post(
        f"/api/billing/admin/transactions/{held.pk}/reject-hold/",
        {"description": "بانک مبلغ را برگشت زده"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["status"] == TransactionStatus.FAILED
    assert money.wallet_hold_balance(workspace) == 0
    assert money.wallet_balance(workspace) == 0


def test_retry_endpoint_verifies_again(payer, plan, workspace, gateway, monkeypatch, no_retry, admin_client):
    held = park(monkeypatch, payer, plan, workspace)
    install_stub(monkeypatch, held, verify_result=paid(held.amount_toman, ref_id="ZR-RETRY"))

    response = admin_client.post(f"/api/billing/admin/transactions/{held.pk}/retry/", {}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == TransactionStatus.PAID
    held.refresh_from_db()
    assert held.status == TransactionStatus.PAID
