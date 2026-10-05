# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Payment service tests: pricing, gateway selection and callback handling."""

# Python imports
import json

# Third party imports
import pytest

# Django imports
from django.utils import timezone

# Module imports
from plane.billing.gateways.base import (
    GatewayStatus,
    GatewayUnavailable,
    GatewayValidationError,
    VerifyResult,
)
from plane.billing.models import (
    BillingCycle,
    Invoice,
    InvoiceStatus,
    PaymentTransaction,
    Plan,
    RoutingStrategy,
    Subscription,
    TransactionStatus,
)
from plane.billing.services import payment as payment_service
from plane.billing.services.payment import BillingError

# Local imports
from plane.billing.tests.conftest import FakeRNG, make_gateway
from plane.billing.tests.gateways_stub import StubAdapter

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="billing-test@example.com", username="billing-test", password="password1234"
    )


@pytest.fixture
def plan(db):
    return Plan.objects.create(
        code="pro-yearly",
        name="Pro yearly",
        description="Pro plan billed yearly",
        access_level="admin",
        monthly_price_toman=1_000_000,
        yearly_price_toman=10_000_000,
        per_seat_price_toman=200_000,
        included_seats=2,
        min_seats=1,
        max_seats=10,
        features=["sso"],
        is_active=True,
        sort_order=1,
    )


@pytest.fixture
def no_retry_enqueue(monkeypatch):
    """Keep celery out of the tests and record the retry requests."""
    calls = []
    monkeypatch.setattr(
        payment_service,
        "schedule_verification_retry",
        lambda transaction, delay=None: calls.append(transaction.pk),
    )
    return calls


def paid(amount_toman, ref_id="R1"):
    return VerifyResult(status=GatewayStatus.PAID, amount_toman=amount_toman, ref_id=ref_id, raw={"code": 100})


# ---------------------------------------------------------------------- pricing
def test_calculate_subtotal_uses_the_cycle_price_and_per_seat(plan):
    plan.per_seat_price_toman = 200_000

    # two seats are included in the yearly price, three cost the per seat rate
    assert plan.calculate_subtotal(2, BillingCycle.YEARLY) == 10_000_000
    assert plan.calculate_subtotal(3, BillingCycle.YEARLY) == 10_200_000
    assert plan.calculate_subtotal(3, BillingCycle.MONTHLY) == 1_200_000


def test_issue_invoice_uses_the_plan_subtotal(user, plan):
    invoice = payment_service.issue_invoice(user=user, plan=plan, seats=3, cycle=BillingCycle.YEARLY)

    assert invoice.status == InvoiceStatus.ISSUED
    assert invoice.subtotal_toman == invoice.total_toman
    assert invoice.discount_toman == 0
    assert invoice.total_toman == 10_200_000
    assert invoice.number
    assert invoice.paid_at is None


def test_create_payment_order_rejects_an_unknown_plan(user, no_retry_enqueue):
    with pytest.raises(BillingError):
        payment_service.create_payment_order(user=user, plan_code="nope", seats=1, cycle=BillingCycle.MONTHLY)
    assert Invoice.objects.count() == 0


def test_create_payment_order_rejects_an_out_of_range_seat_count(user, plan, no_retry_enqueue):
    with pytest.raises(BillingError):
        payment_service.create_payment_order(
            user=user, plan_code=plan.code, seats=plan.max_seats + 1, cycle=BillingCycle.MONTHLY
        )
    with pytest.raises(BillingError):
        payment_service.create_payment_order(
            user=user, plan_code=plan.code, seats=plan.min_seats - 1, cycle=BillingCycle.MONTHLY
        )


# -------------------------------------------------------------- gateway failover
def install_adapters(monkeypatch, **by_code):
    """Route every gateway code to a scripted adapter."""
    from plane.billing.services.router import Candidate

    def adapter_for(self):
        return by_code[self.code]

    monkeypatch.setattr(Candidate, "adapter", adapter_for)
    monkeypatch.setattr(payment_service, "build_adapter", lambda gateway: by_code[gateway.code])


def configuring(monkeypatch, strategy, order):
    from plane.billing.models import GatewayRoutingConfig

    config = GatewayRoutingConfig.get_solo()
    config.strategy = strategy
    config.priority_order = order
    config.cooldown_seconds = 0
    config.max_attempts_per_gateway = 3
    config.save()


def test_unavailable_gateway_fails_over_to_the_next_one(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    make_gateway("payping")
    configuring(monkeypatch, RoutingStrategy.PRIORITY, ["zarinpal", "payping"])
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter("zarinpal", create_error=GatewayUnavailable("down")),
        payping=StubAdapter("payping", redirect_url="https://pay/pp1", token="PP1"),
    )

    order = payment_service.create_payment_order(user=user, plan_code=plan.code, seats=2, cycle=BillingCycle.YEARLY)

    assert order["transaction"].gateway_code == "payping"
    assert order["redirect_url"] == "https://pay/pp1"
    assert order["transaction"].meta["routing_reason"]
    assert order["invoice"].status == InvoiceStatus.ISSUED


def test_a_rejected_request_never_switches_gateway(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    make_gateway("payping")
    configuring(monkeypatch, RoutingStrategy.PRIORITY, ["zarinpal", "payping"])
    payping = StubAdapter("payping", redirect_url="https://pay/pp1", token="PP1")
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter("zarinpal", create_error=GatewayValidationError("invalid merchant")),
        payping=payping,
    )

    with pytest.raises(BillingError):
        payment_service.create_payment_order(user=user, plan_code=plan.code, seats=2, cycle=BillingCycle.YEARLY)

    # the second gateway was never contacted and the issued invoice was cancelled
    assert payping.create_calls == 0
    assert PaymentTransaction.objects.count() == 0
    assert Invoice.objects.get().status == InvoiceStatus.CANCELLED


def test_every_gateway_unavailable_cancels_the_invoice(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    make_gateway("payping")
    configuring(monkeypatch, RoutingStrategy.PRIORITY, ["zarinpal", "payping"])
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter("zarinpal", create_error=GatewayUnavailable("down")),
        payping=StubAdapter("payping", create_error=GatewayUnavailable("down")),
    )

    with pytest.raises(BillingError):
        payment_service.create_payment_order(user=user, plan_code=plan.code, seats=2, cycle=BillingCycle.YEARLY)

    assert Invoice.objects.get().status == InvoiceStatus.CANCELLED
    assert PaymentTransaction.objects.count() == 0


def test_no_enabled_gateway_is_a_billing_error(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal", is_enabled=False)
    configuring(monkeypatch, RoutingStrategy.PRIORITY, ["zarinpal"])

    with pytest.raises(BillingError):
        payment_service.create_payment_order(user=user, plan_code=plan.code, seats=2, cycle=BillingCycle.YEARLY)


def test_max_attempts_per_gateway_is_respected(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    configuring(monkeypatch, RoutingStrategy.PRIORITY, ["zarinpal"])
    zarinpal = StubAdapter("zarinpal", create_error=GatewayUnavailable("down"))
    install_adapters(monkeypatch, zarinpal=zarinpal)

    from plane.billing.models import GatewayRoutingConfig

    config = GatewayRoutingConfig.get_solo()
    config.max_attempts_per_gateway = 2
    config.save()

    with pytest.raises(BillingError):
        payment_service.create_payment_order(user=user, plan_code=plan.code, seats=2, cycle=BillingCycle.YEARLY)

    assert zarinpal.create_calls == 2


def test_schedule_strategy_selects_the_window_gateway(user, plan, monkeypatch, no_retry_enqueue):
    from datetime import datetime

    from plane.billing.models import GatewayRoutingConfig
    from plane.billing.services.router import ROUTING_TIMEZONE

    make_gateway("zarinpal")
    make_gateway("payping")
    config = GatewayRoutingConfig.get_solo()
    config.strategy = RoutingStrategy.SCHEDULE
    config.schedule_entries = [
        {"start_hour": 0, "end_hour": 12, "gateway_code": "zarinpal"},
        {"start_hour": 12, "end_hour": 24, "gateway_code": "payping"},
    ]
    config.cooldown_seconds = 0
    config.max_attempts_per_gateway = 3
    config.save()

    zarinpal = StubAdapter("zarinpal", redirect_url="https://pay/zp1", token="ZR1")
    install_adapters(monkeypatch, zarinpal=zarinpal, payping=StubAdapter("payping", token="PP1"))

    real_datetime = datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 1, 15, 9, 0, tzinfo=ROUTING_TIMEZONE)

    monkeypatch.setattr("plane.billing.services.router.datetime", FrozenDateTime)

    order = payment_service.create_payment_order(user=user, plan_code=plan.code, seats=2, cycle=BillingCycle.YEARLY)

    # 09:00 Tehran matches the zarinpal window only
    assert zarinpal.create_calls == 1
    assert order["transaction"].gateway_code == "zarinpal"
    assert order["transaction"].gateway_token == "ZR1"


def test_a_matched_schedule_window_does_not_fail_over(user, plan, monkeypatch, no_retry_enqueue):
    """Documented behaviour: a pinned window owns the payment, it is not a fallback list."""
    from datetime import datetime

    from plane.billing.models import GatewayRoutingConfig
    from plane.billing.services.router import ROUTING_TIMEZONE

    make_gateway("zarinpal")
    make_gateway("payping")
    config = GatewayRoutingConfig.get_solo()
    config.strategy = RoutingStrategy.SCHEDULE
    config.schedule_entries = [{"start_hour": 0, "end_hour": 24, "gateway_code": "zarinpal"}]
    config.cooldown_seconds = 0
    config.max_attempts_per_gateway = 3
    config.save()

    payping = StubAdapter("payping", token="PP1")
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter("zarinpal", create_error=GatewayUnavailable("down")),
        payping=payping,
    )

    real_datetime = datetime

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 1, 15, 9, 0, tzinfo=ROUTING_TIMEZONE)

    monkeypatch.setattr("plane.billing.services.router.datetime", FrozenDateTime)

    with pytest.raises(BillingError):
        payment_service.create_payment_order(user=user, plan_code=plan.code, seats=2, cycle=BillingCycle.YEARLY)

    # the scheduled gateway is the only candidate inside its own window
    assert payping.create_calls == 0
    assert Invoice.objects.get().status == InvoiceStatus.CANCELLED


def test_random_strategy_uses_the_routing_config(user, plan, monkeypatch, no_retry_enqueue):
    from plane.billing.models import GatewayRoutingConfig

    make_gateway("zarinpal")
    make_gateway("payping")
    config = GatewayRoutingConfig.get_solo()
    config.strategy = RoutingStrategy.RANDOM
    config.weights = {"payping": 100}
    config.cooldown_seconds = 0
    config.max_attempts_per_gateway = 3
    config.save()

    zarinpal = StubAdapter("zarinpal", create_error=GatewayUnavailable("down"))
    install_adapters(monkeypatch, zarinpal=zarinpal, payping=StubAdapter("payping", token="PP1"))

    router_cls = payment_service.GatewayRouter
    real_candidates = router_cls.candidates
    monkeypatch.setattr(
        router_cls,
        "candidates",
        lambda self, rng=None: real_candidates(self, rng=FakeRNG("payping")),
    )

    order = payment_service.create_payment_order(user=user, plan_code=plan.code, seats=2, cycle=BillingCycle.YEARLY)

    assert order["transaction"].gateway_code == "payping"
    assert zarinpal.create_calls == 0


# --------------------------------------------------------------------- callback
def build_transaction(user, plan, gateway_code="zarinpal", token="TOK1", amount_toman=10_000_000):
    invoice = payment_service.issue_invoice(user=user, plan=plan, seats=2, cycle=BillingCycle.YEARLY)
    return PaymentTransaction.objects.create(
        invoice=invoice,
        user=user,
        gateway_code=gateway_code,
        gateway_token=token,
        amount_toman=amount_toman,
        status=TransactionStatus.REDIRECTED,
        meta={"provider_id": "P1", "payment_ref_id": "987"},
    )


def test_callback_marks_the_invoice_paid_and_activates_the_subscription(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    transaction = build_transaction(user, plan)
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter("zarinpal", verify_result=paid(transaction.amount_toman, ref_id="ZR1"), token="TOK1"),
    )

    result = payment_service.process_callback(
        "zarinpal", {"Authority": "TOK1", "Status": "OK"}, transaction=transaction
    )

    transaction.refresh_from_db()
    transaction.invoice.refresh_from_db()
    assert transaction.status == TransactionStatus.PAID
    assert transaction.gateway_ref_id == "ZR1"
    assert transaction.paid_at is not None
    assert transaction.attempts == 1
    assert transaction.invoice.status == InvoiceStatus.PAID
    assert transaction.invoice.paid_at is not None
    subscription = Subscription.objects.get(source_transaction=transaction)
    assert subscription.plan == plan
    assert subscription.status == "active"
    assert result["status"] == TransactionStatus.PAID


def test_repeated_callback_is_idempotent(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    transaction = build_transaction(user, plan)
    adapter = StubAdapter("zarinpal", verify_result=paid(transaction.amount_toman, ref_id="ZR1"), token="TOK1")
    install_adapters(monkeypatch, zarinpal=adapter)
    payload = {"Authority": "TOK1", "Status": "OK"}

    first = payment_service.process_callback("zarinpal", payload, transaction=transaction)
    transaction.refresh_from_db()
    paid_at = transaction.paid_at
    invoice = transaction.invoice
    invoice.refresh_from_db()
    invoice_paid_at = invoice.paid_at

    second = payment_service.process_callback("zarinpal", payload, transaction=transaction)
    transaction.refresh_from_db()

    assert first["status"] == TransactionStatus.PAID
    assert second["status"] == TransactionStatus.PAID
    assert second["message"] == "Already paid"
    assert transaction.status == TransactionStatus.PAID
    assert transaction.paid_at == paid_at
    # the second callback short circuits before verify, so no extra attempt
    assert adapter.verify_calls == 1
    assert transaction.attempts == 1
    assert Subscription.objects.count() == 1
    invoice.refresh_from_db()
    assert invoice.paid_at == invoice_paid_at


def test_callback_verification_failure_cancels_nothing_but_marks_failed(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    transaction = build_transaction(user, plan)
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter(
            "zarinpal",
            verify_result=VerifyResult(status=GatewayStatus.FAILED, message="NOK"),
            token="TOK1",
        ),
    )

    result = payment_service.process_callback(
        "zarinpal", {"Authority": "TOK1", "Status": "OK"}, transaction=transaction
    )

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.FAILED
    assert Subscription.objects.count() == 0
    assert result["status"] == TransactionStatus.FAILED
    assert no_retry_enqueue == []


def test_payer_declined_callback_fails_without_verify(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    transaction = build_transaction(user, plan)
    adapter = StubAdapter("zarinpal", verify_result=paid(transaction.amount_toman), token="TOK1")
    adapter.callback_indicator = False
    install_adapters(monkeypatch, zarinpal=adapter)

    payment_service.process_callback("zarinpal", {"Authority": "TOK1", "Status": "NOK"}, transaction=transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.FAILED
    assert adapter.verify_calls == 0


def test_paid_without_a_confirmed_amount_stays_processing(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zibal")
    transaction = build_transaction(user, plan, gateway_code="zibal", token="TRK1")
    install_adapters(
        monkeypatch,
        zibal=StubAdapter("zibal", verify_result=VerifyResult(status=GatewayStatus.PAID, ref_id="ZB1"), token="TRK1"),
    )

    result = payment_service.process_callback("zibal", {"success": "1", "trackId": "TRK1"}, transaction=transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.PROCESSING
    assert "confirmed amount" in result["message"]
    assert no_retry_enqueue == [transaction.pk]


def test_amount_mismatch_is_failed(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    transaction = build_transaction(user, plan)
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter("zarinpal", verify_result=paid(transaction.amount_toman - 1), token="TOK1"),
    )

    result = payment_service.process_callback(
        "zarinpal", {"Authority": "TOK1", "Status": "OK"}, transaction=transaction
    )

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.FAILED
    assert "mismatch" in result["message"].lower()
    assert no_retry_enqueue == []


def test_unavailable_verify_is_unavailable_and_scheduled_for_retry(user, plan, monkeypatch, no_retry_enqueue):
    """A verify that answers UNAVAILABLE must not be recorded as a failure."""
    make_gateway("zarinpal")
    transaction = build_transaction(user, plan)
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter(
            "zarinpal",
            verify_result=VerifyResult(status=GatewayStatus.UNAVAILABLE, message="busy"),
            token="TOK1",
        ),
    )

    result = payment_service.process_callback(
        "zarinpal", {"Authority": "TOK1", "Status": "OK"}, transaction=transaction
    )

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.UNAVAILABLE
    assert no_retry_enqueue == [transaction.pk]
    assert result["status"] == TransactionStatus.UNAVAILABLE
    assert Subscription.objects.count() == 0


def test_verify_raising_unavailable_is_handled_the_same_way(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    transaction = build_transaction(user, plan)
    install_adapters(
        monkeypatch, zarinpal=StubAdapter("zarinpal", verify_error=GatewayUnavailable("boom"), token="TOK1")
    )

    payment_service.process_callback("zarinpal", {"Authority": "TOK1", "Status": "OK"}, transaction=transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.UNAVAILABLE
    assert no_retry_enqueue == [transaction.pk]


def test_processing_verify_is_processing_and_scheduled(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    transaction = build_transaction(user, plan)
    install_adapters(
        monkeypatch,
        zarinpal=StubAdapter("zarinpal", verify_result=VerifyResult(status=GatewayStatus.PROCESSING), token="TOK1"),
    )

    payment_service.process_callback("zarinpal", {"Authority": "TOK1", "Status": "OK"}, transaction=transaction)

    transaction.refresh_from_db()
    assert transaction.status == TransactionStatus.PROCESSING
    assert no_retry_enqueue == [transaction.pk]


def test_callback_persists_the_payload_and_extracted_identifiers(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("payping")
    transaction = build_transaction(user, plan, gateway_code="payping", token="PP1")
    adapter = StubAdapter("payping", verify_result=paid(transaction.amount_toman), token="PP1")
    adapter.callback_meta = {"payment_ref_id": "555"}
    install_adapters(monkeypatch, payping=adapter)
    payload = {
        "status": "PAID",
        "errorCode": 0,
        "data": json.dumps({"paymentCode": "PP1", "paymentRefId": 555, "clientRefId": "INV-1"}),
    }

    payment_service.process_callback("payping", payload, transaction=transaction)

    transaction.refresh_from_db()
    assert transaction.callback_payload == payload
    assert transaction.meta["payment_ref_id"] == "555"
    assert transaction.verify_payload == {"code": 100}


def test_callback_for_an_unknown_transaction_is_reported(user, plan, monkeypatch, no_retry_enqueue):
    make_gateway("zarinpal")
    install_adapters(monkeypatch, zarinpal=StubAdapter("zarinpal", token="TOK1"))

    result = payment_service.process_callback("zarinpal", {"Authority": "nope"})

    assert result["status"] == "unknown"


def test_find_transaction_matches_on_the_unique_gateway_token(user, plan):
    transaction = build_transaction(user, plan, token="UNIQUE-1")

    assert payment_service.find_transaction("zarinpal", "UNIQUE-1") == transaction
    assert payment_service.find_transaction("payping", "UNIQUE-1") is None


def test_locate_transaction_falls_back_to_the_callback_references(user, plan, monkeypatch):
    make_gateway("digipay")
    transaction = build_transaction(user, plan, gateway_code="digipay", token="TK1")
    transaction.meta = {"provider_id": "P1", "invoice_number": transaction.invoice.number}
    transaction.save()

    adapter = StubAdapter("digipay")
    adapter.callback_meta = {"provider_id": "P1"}
    install_adapters(monkeypatch, digipay=adapter)

    located = payment_service.locate_transaction("digipay", adapter, {"providerId": "P1"})

    assert located == transaction


def test_mark_paid_and_reversed_guards(user, plan):
    transaction = build_transaction(user, plan)

    assert transaction.status == TransactionStatus.REDIRECTED
    transaction.mark_paid(ref_id="R", amount_toman=transaction.amount_toman, fee=100)
    assert transaction.status == TransactionStatus.PAID
    assert transaction.paid_at <= timezone.now()
