# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""API tests: the admin endpoints require InstanceAdmin, callbacks stay public."""

# Python imports

# Third party imports
import pytest

# Django imports

# Module imports
from plane.billing.models import PaymentGateway, Plan

# Local imports
from plane.billing.tests.conftest import CREDENTIALS, make_gateway

pytestmark = pytest.mark.django_db


ADMIN_URLS = [
    ("get", "/api/billing/admin/gateways/"),
    ("post", "/api/billing/admin/gateways/"),
    ("get", "/api/billing/admin/routing/"),
    ("put", "/api/billing/admin/routing/"),
    ("get", "/api/billing/admin/plans/"),
    ("post", "/api/billing/admin/plans/"),
    ("get", "/api/billing/admin/invoices/"),
    ("get", "/api/billing/admin/transactions/"),
]


@pytest.fixture
def anonymous_client():
    from rest_framework.test import APIClient

    return APIClient()


def test_admin_endpoints_reject_an_anonymous_request(anonymous_client):
    for method, url in ADMIN_URLS:
        response = getattr(anonymous_client, method)(url, format="json")
        assert response.status_code in (401, 403), f"{method} {url} -> {response.status_code}"


def test_admin_endpoints_reject_a_plain_user(client, django_user_model):
    user = django_user_model.objects.create_user(email="member@example.com", username="member", password="password1234")
    client.force_login(user)

    for method, url in ADMIN_URLS:
        response = getattr(client, method)(url, format="json")
        assert response.status_code in (401, 403), f"{method} {url} -> {response.status_code}"


def test_gateway_credentials_are_never_returned_to_the_client(client, django_user_model, instance_admin):
    instance_admin
    client.force_login(instance_admin)
    make_gateway("zarinpal")
    make_gateway("payping")

    response = client.get("/api/billing/admin/gateways/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["results"], payload
    masked = {row["code"]: row["credentials"] for row in payload["results"]}
    # only the masked form reaches the client, the clear value never does
    assert masked["zarinpal"]["merchant_id"] == "000******01"
    assert masked["payping"]["api_token"] == "tes******90"
    body = response.content.decode()
    assert "00000000-0000-0000-0000-000000000001" not in body
    assert "test-token-1234567890" not in body


def test_gateway_credentials_are_stored_encrypted_at_rest():
    gateway = make_gateway("payping")
    gateway.refresh_from_db()

    assert "test-token-1234567890" not in gateway.credentials
    # the encrypted blob only exists once decrypted
    # Local imports
    from plane.billing.services.credentials import decrypt_credentials

    assert decrypt_credentials(gateway.credentials)["api_token"] == "test-token-1234567890"


def test_callback_endpoint_is_public_and_reports_an_unknown_gateway(client):
    response = client.get("/api/billing/callback/not-a-gateway/")

    assert response.status_code == 400


def test_callback_endpoint_is_public_and_reports_a_missing_transaction(client):
    make_gateway("zarinpal")

    response = client.get("/api/billing/callback/zarinpal/", {"Authority": "missing"})

    assert response.status_code == 200
    assert response.json()["status"] == "unknown"


def test_plan_list_returns_only_active_plans_for_any_signed_in_user(client, db):
    from plane.db.models import User

    user = User.objects.create(
        email="regular-user@example.com",
        first_name="Regular",
        last_name="User",
    )
    user.set_password("password1234")
    user.save()
    client.force_authenticate(user=user)

    Plan.objects.create(code="active-plan", name="Active", is_active=True, sort_order=1)
    Plan.objects.create(code="archived-plan", name="Archived", is_active=False, sort_order=2)

    response = client.get("/api/billing/plans/")

    assert response.status_code == 200
    codes = [item["code"] for item in response.json()["results"]]
    assert codes == ["active-plan"]


def test_plan_list_is_closed_to_anonymous_callers(anonymous_client):
    assert anonymous_client.get("/api/billing/plans/").status_code in (401, 403)


def test_admin_routing_round_trip(client, instance_admin):
    client.force_login(instance_admin)

    response = client.patch(
        "/api/billing/admin/routing/",
        {
            "strategy": "schedule",
            "schedule_entries": [{"start_hour": 22, "end_hour": 6, "gateway_code": "zarinpal"}],
            "priority_order": ["zarinpal", "payping"],
            "cooldown_seconds": 300,
            "max_attempts_per_gateway": 3,
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    # Local imports
    from plane.billing.models import GatewayRoutingConfig

    config = GatewayRoutingConfig.get_solo()
    assert config.strategy == "schedule"
    assert config.schedule_entries[0]["start_hour"] == 22
    assert config.priority_order == ["zarinpal", "payping"]


def test_admin_plan_crud(client, instance_admin):
    client.force_login(instance_admin)

    created = client.post(
        "/api/billing/admin/plans/",
        {
            "code": "starter",
            "name": "Starter",
            "description": "Starter plan",
            "access_level": "member",
            "monthly_price_toman": 500000,
            "yearly_price_toman": 5000000,
            "per_seat_price_toman": 100000,
            "included_seats": 1,
            "min_seats": 1,
            "max_seats": 5,
            "features": ["sso"],
            "is_active": True,
            "sort_order": 0,
        },
        format="json",
    )

    assert created.status_code in (200, 201), created.content
    assert Plan.objects.filter(code="starter").exists()
    assert created.json()["monthly_price_toman"] == 500000


def test_admin_gateway_create_encrypts_the_credentials(client, instance_admin):
    client.force_login(instance_admin)

    response = client.post(
        "/api/billing/admin/gateways/",
        {
            "code": "zarinpal",
            "title": "ZarinPal",
            "is_enabled": False,
            "is_sandbox": True,
            "credentials": CREDENTIALS["zarinpal"],
            "extra_config": {"amount_unit": "rial"},
            "priority": 3,
        },
        format="json",
    )

    assert response.status_code in (200, 201), response.content
    body = response.content.decode()
    assert "00000000-0000-0000-0000-000000000001" not in body
    assert response.json()["credentials"]["merchant_id"] == "000******01"
    gateway = PaymentGateway.objects.get(code="zarinpal")
    assert "00000000-0000-0000-0000-000000000001" not in gateway.credentials

    # the stored code comes from the request and stays immutable afterwards
    assert response.json()["code"] == "zarinpal"
    renamed = client.patch(
        f"/api/billing/admin/gateways/{gateway.id}/",
        {"code": "payping"},
        format="json",
    )
    assert renamed.status_code == 400, renamed.content
    gateway.refresh_from_db()
    assert gateway.code == "zarinpal"


def _signed_in_user(client, email: str):
    from plane.db.models import User

    user = User.objects.create(username=email.split("@")[0], email=email, first_name="Payer", last_name="User")
    user.set_password("password1234")
    user.save()
    client.force_authenticate(user=user)
    return user


def test_plan_quote_prices_the_order_on_the_server(client, db):
    _signed_in_user(client, "quote-user@example.com")
    Plan.objects.create(
        code="team",
        name="Team",
        is_active=True,
        sort_order=1,
        monthly_price_toman=500000,
        yearly_price_toman=5000000,
        per_seat_price_toman=100000,
        included_seats=2,
        min_seats=1,
        max_seats=10,
    )

    response = client.get("/api/billing/plans/team/quote/", {"seats": 5, "cycle": "monthly"})

    assert response.status_code == 200, response.content
    payload = response.json()
    # base price of the cycle plus the seats above the included ones
    assert payload["extra_seats"] == 3
    assert payload["base_price_toman"] == 500000
    assert payload["subtotal_toman"] == 500000 + 3 * 100000
    assert payload["total_toman"] == payload["subtotal_toman"]


def test_plan_quote_rejects_a_seat_count_outside_the_plan_bounds(client, db):
    _signed_in_user(client, "bounds-user@example.com")
    Plan.objects.create(
        code="team",
        name="Team",
        is_active=True,
        sort_order=1,
        per_seat_price_toman=100000,
        included_seats=1,
        min_seats=3,
        max_seats=10,
    )

    too_many = client.get("/api/billing/plans/team/quote/", {"seats": 50, "cycle": "monthly"})
    too_few = client.get("/api/billing/plans/team/quote/", {"seats": 1, "cycle": "monthly"})

    assert too_many.status_code == 400
    assert too_few.status_code == 400


def test_order_status_is_scoped_to_the_paying_user(client, db):
    from plane.billing.models import PaymentTransaction, TransactionStatus
    from plane.billing.services.payment import issue_invoice

    user = _signed_in_user(client, "owner@example.com")
    plan = Plan.objects.create(
        code="solo",
        name="Solo",
        is_active=True,
        sort_order=1,
        monthly_price_toman=400000,
        per_seat_price_toman=90000,
        included_seats=1,
        min_seats=1,
        max_seats=10,
    )
    invoice = issue_invoice(user=user, plan=plan, seats=3, cycle="monthly")
    transaction = PaymentTransaction.objects.create(
        invoice=invoice,
        user=user,
        gateway_code="zarinpal",
        gateway_token="token-1234567890",
        amount_toman=invoice.total_toman,
        status=TransactionStatus.REDIRECTED,
    )

    response = client.get(f"/api/billing/orders/{transaction.id}/")

    assert response.status_code == 200, response.content
    payload = response.json()
    assert payload["status"] == TransactionStatus.REDIRECTED
    assert payload["invoice_number"] == invoice.number
    assert payload["plan_code"] == "solo"
    assert payload["seats"] == 3
    assert payload["cycle"] == "monthly"
    assert payload["amount_toman"] == invoice.total_toman

    # another signed in user must not be able to read somebody else's payment
    from plane.db.models import User

    intruder = User.objects.create(
        username="intruder", email="intruder@example.com", first_name="Other", last_name="User"
    )
    intruder.set_password("password1234")
    intruder.save()
    client.force_authenticate(user=intruder)
    assert client.get(f"/api/billing/orders/{transaction.id}/").status_code == 404


def test_admin_transaction_list_filters_by_invoice_cycle(client, instance_admin, db):
    from plane.billing.models import PaymentTransaction
    from plane.billing.services.payment import issue_invoice

    user = _signed_in_user(client, "cycles@example.com")
    plan = Plan.objects.create(
        code="solo", name="Solo", is_active=True, sort_order=1, included_seats=1, min_seats=1, max_seats=10
    )
    monthly_invoice = issue_invoice(user=user, plan=plan, seats=1, cycle="monthly")
    yearly_invoice = issue_invoice(user=user, plan=plan, seats=1, cycle="yearly")
    for invoice in (monthly_invoice, yearly_invoice):
        PaymentTransaction.objects.create(
            invoice=invoice,
            user=user,
            gateway_code="zarinpal",
            gateway_token=f"token-{invoice.number}",
            amount_toman=invoice.total_toman,
        )

    # The payer above was attached with force_authenticate, which DRF prefers over the session, so
    # it has to be detached before the admin session login takes effect.
    client.force_authenticate(user=None)
    client.force_login(instance_admin)
    response = client.get("/api/billing/admin/transactions/", {"cycle": "yearly"})

    assert response.status_code == 200, response.content
    numbers = [item["invoice_number"] for item in response.json()["results"]]
    assert numbers == [yearly_invoice.number]
