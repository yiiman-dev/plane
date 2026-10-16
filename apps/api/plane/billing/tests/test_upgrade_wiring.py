# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Upgrade quotes wired into the quote endpoint, order creation and the gateway callback."""

# Third party imports
import pytest

# Django imports
from django.utils import timezone

# Module imports
from plane.billing.models import (
    BillingCycle,
    Invoice,
    InvoiceStatus,
    PaymentTransaction,
    Plan,
    Subscription,
    SubscriptionStatus,
    TransactionStatus,
)
from plane.billing.services import payment as payment_service
from plane.billing.services.payment import BillingError
from plane.billing.tests.conftest import make_gateway
from plane.billing.tests.gateways_stub import StubAdapter
from plane.billing.tests.test_payment_service import install_adapters, paid
from plane.db.models import WorkspaceMember

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def no_retry(monkeypatch):
    monkeypatch.setattr(payment_service, "schedule_verification_retry", lambda *a, **k: None)


@pytest.fixture
def member(workspace_factory, django_user_model):
    workspace = workspace_factory()
    user = django_user_model.objects.create_user(email="payer@example.com", username="payer", password="password1234")
    WorkspaceMember.objects.create(workspace=workspace, member=user, role=20, is_active=True)
    return workspace, user


def make_plan(code, rank, monthly, lock_days=0):
    return Plan.objects.create(
        code=code,
        name=code,
        access_level="admin",
        monthly_price_toman=monthly,
        yearly_price_toman=monthly * 10,
        per_seat_price_toman=0,
        included_seats=5,
        min_seats=1,
        max_seats=10,
        is_active=True,
        tier_rank=rank,
        renew_lock_days=lock_days,
    )


def subscribe(workspace, user, plan, days_left, charge):
    transaction = PaymentTransaction.objects.create(
        user=user, gateway_code="zarinpal", gateway_token="OLD", amount_toman=charge, status=TransactionStatus.PAID
    )
    return Subscription.objects.create(
        user=user,
        plan=plan,
        workspace=workspace,
        seats=1,
        cycle=BillingCycle.MONTHLY,
        status=SubscriptionStatus.ACTIVE,
        starts_at=timezone.now() - timezone.timedelta(days=31 - days_left),
        ends_at=timezone.now() + timezone.timedelta(days=days_left),
        source_transaction=transaction,
    )


def quote(client, plan, workspace):
    return client.get(f"/api/billing/plans/{plan.code}/quote/?workspace_slug={workspace.slug}&seats=1")


def test_quote_credits_the_unused_remainder_of_a_lower_tier(client, member):
    workspace, user = member
    low, high = make_plan("low", 1, 1_000_000), make_plan("high", 2, 2_000_000)
    subscribe(workspace, user, low, days_left=15, charge=1_000_000)
    client.force_login(user)

    body = quote(client, high, workspace).json()

    assert body["credit_applied_toman"] > 0
    assert body["total_toman"] == 2_000_000 - body["credit_applied_toman"]
    assert body["new_ends_at"]


def test_quote_for_a_lower_tier_takes_no_credit(client, member):
    workspace, user = member
    low, high = make_plan("low", 1, 1_000_000), make_plan("high", 2, 2_000_000)
    subscribe(workspace, user, high, days_left=15, charge=2_000_000)
    client.force_login(user)

    body = quote(client, low, workspace).json()

    assert body["credit_applied_toman"] == 0
    assert body["total_toman"] == 1_000_000
    assert body["new_ends_at"] is None


def test_quote_refuses_a_renewal_inside_the_lock_window(client, member):
    workspace, user = member
    plan = make_plan("pro", 1, 1_000_000, lock_days=20)
    subscribe(workspace, user, plan, days_left=15, charge=1_000_000)
    client.force_login(user)

    response = quote(client, plan, workspace)

    assert response.status_code == 409
    assert response.json()["code"] == "renewal_locked"


def test_quote_for_a_workspace_requires_membership(client, member, workspace_factory):
    _, user = member
    other = workspace_factory()
    client.force_login(user)

    assert quote(client, make_plan("pro", 1, 1_000_000), other).status_code == 403


def test_order_creation_charges_the_prorated_amount(member, monkeypatch, no_retry):
    from plane.billing.tests.test_payment_service import configuring
    from plane.billing.models import RoutingStrategy

    workspace, user = member
    low, high = make_plan("low", 1, 1_000_000), make_plan("high", 2, 2_000_000)
    subscribe(workspace, user, low, days_left=15, charge=1_000_000)
    make_gateway("zarinpal")
    configuring(monkeypatch, RoutingStrategy.PRIORITY, ["zarinpal"])
    install_adapters(monkeypatch, zarinpal=StubAdapter("zarinpal", redirect_url="https://pay/1", token="T1"))

    order = payment_service.create_payment_order(
        user=user, plan_code="high", seats=1, cycle=BillingCycle.MONTHLY, workspace_slug=workspace.slug
    )

    invoice = order["invoice"]
    assert invoice.discount_toman > 0
    assert invoice.total_toman == 2_000_000 - invoice.discount_toman
    assert order["transaction"].amount_toman == invoice.total_toman
    assert invoice.metadata["proration"]["credit_applied_toman"] == invoice.discount_toman


def test_order_creation_is_refused_inside_the_lock_window(member, monkeypatch, no_retry):
    workspace, user = member
    plan = make_plan("pro", 1, 1_000_000, lock_days=20)
    subscribe(workspace, user, plan, days_left=15, charge=1_000_000)

    with pytest.raises(BillingError):
        payment_service.create_payment_order(
            user=user, plan_code="pro", seats=1, cycle=BillingCycle.MONTHLY, workspace_slug=workspace.slug
        )
    assert Invoice.objects.count() == 0


def test_callback_inside_the_lock_keeps_the_money_but_does_not_renew(member, monkeypatch, no_retry):
    workspace, user = member
    plan = make_plan("pro", 1, 1_000_000, lock_days=20)
    existing = subscribe(workspace, user, plan, days_left=15, charge=1_000_000)
    ends_before = existing.ends_at
    invoice = payment_service.issue_invoice(
        user=user, plan=plan, seats=1, cycle=BillingCycle.MONTHLY, workspace_slug=workspace.slug
    )
    transaction = PaymentTransaction.objects.create(
        invoice=invoice,
        user=user,
        gateway_code="zarinpal",
        gateway_token="TOK1",
        amount_toman=invoice.total_toman,
        status=TransactionStatus.REDIRECTED,
    )
    make_gateway("zarinpal")
    install_adapters(
        monkeypatch, zarinpal=StubAdapter("zarinpal", verify_result=paid(invoice.total_toman), token="TOK1")
    )

    payment_service.process_callback("zarinpal", {"Authority": "TOK1", "Status": "OK"}, transaction=transaction)

    transaction.refresh_from_db()
    invoice.refresh_from_db()
    existing.refresh_from_db()
    assert transaction.status == TransactionStatus.PAID
    assert invoice.status == InvoiceStatus.PAID
    assert invoice.metadata["activation_blocked"] == "renewal_locked"
    assert existing.ends_at == ends_before
    assert Subscription.objects.count() == 2 - 1


def test_upgrade_callback_replaces_the_old_subscription(member, monkeypatch, no_retry):
    workspace, user = member
    low, high = make_plan("low", 1, 1_000_000), make_plan("high", 2, 2_000_000)
    old = subscribe(workspace, user, low, days_left=15, charge=1_000_000)
    from plane.billing.services.upgrade import quote_for_workspace

    quoted = quote_for_workspace(workspace=workspace, plan=high, seats=1, cycle=BillingCycle.MONTHLY)
    invoice = payment_service.issue_invoice(
        user=user, plan=high, seats=1, cycle=BillingCycle.MONTHLY, workspace_slug=workspace.slug, quote=quoted
    )
    transaction = PaymentTransaction.objects.create(
        invoice=invoice,
        user=user,
        gateway_code="zarinpal",
        gateway_token="TOK2",
        amount_toman=invoice.total_toman,
        status=TransactionStatus.REDIRECTED,
    )
    make_gateway("zarinpal")
    install_adapters(
        monkeypatch, zarinpal=StubAdapter("zarinpal", verify_result=paid(invoice.total_toman), token="TOK2")
    )

    payment_service.process_callback("zarinpal", {"Authority": "TOK2", "Status": "OK"}, transaction=transaction)

    old.refresh_from_db()
    assert old.status == SubscriptionStatus.EXPIRED
    new = Subscription.objects.get(workspace=workspace, status=SubscriptionStatus.ACTIVE)
    assert new.plan == high
    assert new.ends_at > timezone.now() + timezone.timedelta(days=30)
