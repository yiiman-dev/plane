# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Adapter level tests. Every HTTP answer is scripted, no network is used."""

# Python imports
import pytest

# Module imports
from plane.billing.gateways.base import GatewayStatus, GatewayUnavailable
from plane.billing.gateways.registry import (
    UnknownGatewayError,
    build_adapter,
    get_adapter_class,
    supported_codes,
)

# Local imports
from plane.billing.tests.conftest import CREDENTIALS, make_gateway

pytestmark = pytest.mark.django_db


def adapter_for(code, http):
    """Create a gateway row and wire its adapter to the scripted transport."""
    gateway = make_gateway(code)
    adapter = build_adapter(gateway)
    adapter._request = http
    return adapter


# --------------------------------------------------------------------- zarinpal
def test_zarinpal_create_and_verify_paid(http):
    adapter = adapter_for("zarinpal", http)
    http.queue((200, {"data": {"code": 100, "authority": "A0000001"}}))

    result = adapter.create_payment(amount_toman=50000, description="Plan", order_id="INV-1", callback="https://app/cb")

    assert result.token == "A0000001"
    assert result.redirect_url.endswith("/StartPay/A0000001")
    # zarinpal is configured in rial, the canonical amount is toman
    assert http.last_body()["amount"] == 500000
    assert http.last_body()["currency"] == "IRR"
    assert "/v4/payment/request.json" in http.last_url()

    http.queue((200, {"data": {"code": 100, "ref_id": 123456, "amount": 500000, "fee": 5000}}))
    verified = adapter.verify("A0000001", 50000, {})

    assert verified.status == GatewayStatus.PAID
    assert verified.amount_toman == 50000
    assert verified.ref_id == "123456"
    assert verified.already_verified is False


def test_zarinpal_verify_already_verified_is_paid(http):
    adapter = adapter_for("zarinpal", http)
    http.queue((200, {"data": {"code": 101, "ref_id": 77, "amount": 500000}}))

    verified = adapter.verify("A0000001", 50000, {})

    assert verified.status == GatewayStatus.PAID
    assert verified.already_verified is True


def test_zarinpal_verify_failed_code_is_failed(http):
    adapter = adapter_for("zarinpal", http)
    http.queue((200, {"data": {"code": -51, "message": "Failed"}}))

    verified = adapter.verify("A0000001", 50000, {})

    assert verified.status == GatewayStatus.FAILED


def test_zarinpal_verify_unavailable_code_and_http_error(http):
    adapter = adapter_for("zarinpal", http)
    http.queue((200, {"data": {"code": -12, "message": "Unavailable"}}))
    with pytest.raises(GatewayUnavailable):
        adapter.verify("A0000001", 50000, {})

    http.queue((503, {}))
    with pytest.raises(GatewayUnavailable):
        adapter.verify("A0000001", 50000, {})

    # a transport failure is unavailable too
    http.queue(GatewayUnavailable("connection reset"))
    with pytest.raises(GatewayUnavailable):
        adapter.verify("A0000001", 50000, {})


def test_zarinpal_callback_status_nok_is_not_a_payment(http):
    adapter = adapter_for("zarinpal", http)

    assert adapter.callback_indicates_payment({"Status": "OK"}) is True
    assert adapter.callback_indicates_payment({"Status": "NOK"}) is False
    assert adapter.callback_indicates_payment({}) is None
    assert adapter.extract_callback_token({"Authority": "A1"}) == "A1"


def test_zarinpal_amount_over_limit_is_rejected_locally(http):
    adapter = adapter_for("zarinpal", http)

    with pytest.raises(Exception):
        adapter.create_payment(amount_toman=200_000_000, description="x", order_id="INV-1", callback="https://app/cb")
    assert http.call_count == 0


# ---------------------------------------------------------------------- payping
def test_payping_create_and_verify_paid(http):
    adapter = adapter_for("payping", http)
    http.queue(
        (
            200,
            {
                "paymentCode": "PP1",
                "url": "https://pay.payping.ir/PP1",
                "amount": 50000,
                "gatewayAmount": 51500,
            },
        )
    )

    result = adapter.create_payment(amount_toman=50000, description="Plan", order_id="INV-1", callback="https://app/cb")

    assert result.token == "PP1"
    assert result.redirect_url == "https://pay.payping.ir/PP1"
    # payping is configured in toman, no conversion happens
    assert http.last_body()["amount"] == 50000
    assert http.calls[0]["headers"]["Authorization"] == "Bearer test-token-1234567890"

    http.queue((200, {"amount": 50000, "paymentRefId": 987, "paymentCode": "PP1"}))
    verified = adapter.verify("PP1", 50000, {"paymentRefId": 987})

    assert verified.status == GatewayStatus.PAID
    assert verified.amount_toman == 50000
    assert verified.ref_id == "987"
    assert http.last_body()["paymentRefId"] == 987


def test_payping_verify_repeated_is_paid(http):
    adapter = adapter_for("payping", http)
    http.queue(
        (
            409,
            {
                "title": "Conflict",
                "status": 409,
                "detail": "already verified",
                "metaData": {
                    "code": 110,
                    "message": {"amount": 50000, "paymentRefId": 987},
                },
            },
        )
    )

    verified = adapter.verify("PP1", 50000, {"paymentRefId": 987})

    assert verified.status == GatewayStatus.PAID
    assert verified.already_verified is True
    assert verified.amount_toman == 50000


def test_payping_verify_failed_is_failed(http):
    adapter = adapter_for("payping", http)
    http.queue((400, {"title": "Bad Request", "detail": "invalid amount", "metaData": {"code": 101}}))

    verified = adapter.verify("PP1", 50000, {"paymentRefId": 987})

    assert verified.status == GatewayStatus.FAILED


def test_payping_verify_processing_codes(http):
    adapter = adapter_for("payping", http)

    for status_code in (202, 502):
        http.queue((status_code, {"detail": "still processing"}))
        assert adapter.verify("PP1", 50000, {"paymentRefId": 987}).status == GatewayStatus.PROCESSING


def test_payping_verify_unavailable(http):
    adapter = adapter_for("payping", http)
    http.queue((500, {"detail": "boom"}))
    with pytest.raises(GatewayUnavailable):
        adapter.verify("PP1", 50000, {"paymentRefId": 987})

    http.queue((401, {"detail": "bad token"}))
    with pytest.raises(GatewayUnavailable):
        adapter.verify("PP1", 50000, {"paymentRefId": 987})


def test_payping_verify_requires_payment_ref_id(http):
    adapter = adapter_for("payping", http)

    with pytest.raises(Exception):
        adapter.verify("PP1", 50000, {})
    assert http.call_count == 0


def test_payping_callback_meta_carries_the_merchant_ids(http):
    # Local imports
    from plane.billing.tests.conftest import payping_callback_data

    adapter = adapter_for("payping", http)
    payload = payping_callback_data()

    assert adapter.extract_callback_token(payload) == "PP-CODE-1"
    assert adapter.extract_callback_meta(payload)["payment_ref_id"] == "987"
    assert adapter.extract_callback_meta(payload)["invoice_number"] == "INV-1"
    assert adapter.callback_indicates_payment(payload) is True
    assert adapter.callback_indicates_payment({"status": "FAILED"}) is False


# ----------------------------------------------------------------------- zibal
def test_zibal_create_uses_the_server_side_start_url(http):
    adapter = adapter_for("zibal", http)
    http.queue((200, {"trackId": "TRK1", "result": 100}))

    result = adapter.create_payment(
        amount_toman=50000, description="Plan", order_id="INV-1", callback="https://evil/cb"
    )

    assert result.token == "TRK1"
    # the caller supplied callback is never echoed back as a redirect target
    assert result.redirect_url.endswith("/api/billing/callback/zibal/start/TRK1/")
    assert "evil" not in result.redirect_url
    assert http.last_body()["amount"] == 500000
    assert http.last_body()["callbackUrl"]


def test_zibal_verify_paid_converts_rial_to_toman(http):
    adapter = adapter_for("zibal", http)
    http.queue((200, {"result": 100, "status": 1, "amount": 500000, "refNumber": "ZB1"}))

    verified = adapter.verify("TRK1", 50000, {})

    assert verified.status == GatewayStatus.PAID
    assert verified.amount_toman == 50000
    assert verified.ref_id == "ZB1"
    assert http.last_body() == {"merchant": "zibal", "trackId": "TRK1"}


def test_zibal_verify_already_veried_is_paid(http):
    adapter = adapter_for("zibal", http)
    http.queue((200, {"result": 201, "status": 1, "amount": 500000, "refNumber": "ZB1"}))

    verified = adapter.verify("TRK1", 50000, {})

    assert verified.status == GatewayStatus.PAID
    assert verified.already_verified is True


def test_zibal_verify_failed_is_failed(http):
    adapter = adapter_for("zibal", http)
    http.queue((200, {"result": 202, "status": -1, "message": "not paid"}))

    assert adapter.verify("TRK1", 50000, {}).status == GatewayStatus.FAILED

    http.queue((200, {"result": 203, "status": 1, "message": "invalid track"}))
    assert adapter.verify("TRK1", 50000, {}).status == GatewayStatus.FAILED


def test_zibal_paid_but_unverified_is_processing(http):
    adapter = adapter_for("zibal", http)
    http.queue((200, {"result": 202, "status": 2, "amount": 500000}))

    assert adapter.verify("TRK1", 50000, {}).status == GatewayStatus.PROCESSING


def test_zibal_verify_unavailable(http):
    adapter = adapter_for("zibal", http)
    http.queue((200, {"result": 102, "message": "gateway busy"}))
    with pytest.raises(GatewayUnavailable):
        adapter.verify("TRK1", 50000, {})

    http.queue((502, {}))
    with pytest.raises(GatewayUnavailable):
        adapter.verify("TRK1", 50000, {})


def test_zibal_inquiry_reports_the_confirmed_amount(http):
    adapter = adapter_for("zibal", http)
    http.queue((200, {"result": 100, "status": 1, "amount": 500000, "refNumber": "ZB1"}))

    verified = adapter.inquiry("TRK1")

    assert verified.status == GatewayStatus.PAID
    assert verified.amount_toman == 50000
    assert "/v1/inquiry" in http.last_url()


def test_zibal_callback_meta_carries_the_invoice(http):
    adapter = adapter_for("zibal", http)
    payload = {"success": "1", "trackId": "TRK1", "orderId": "INV-1", "status": "OK"}

    assert adapter.extract_callback_token(payload) == "TRK1"
    assert adapter.extract_callback_meta(payload) == {"invoice_number": "INV-1"}
    assert adapter.callback_indicates_payment(payload) is True
    assert adapter.callback_indicates_payment({"success": "0"}) is False


# --------------------------------------------------------------------- digipay
def digipay_adapter(http, fake_cache):
    # Local imports
    from plane.billing.gateways import digipay as digipay_gateway_module

    adapter = adapter_for("digipay", http)
    adapter._request = http
    # the OAuth token is cached across calls, keep the fake cache authoritative
    digipay_gateway_module.cache = fake_cache
    return adapter


def seed_digipay_token(adapter, fake_cache, token: str = "tok"):
    """Pre-load the OAuth token so the next scripted answer reaches verify."""
    from plane.billing.gateways import digipay as digipay_gateway_module

    digipay_gateway_module.cache = fake_cache
    fake_cache.store[f"billing:digipay:token:{adapter.gateway.code}:{adapter.gateway.id}"] = token


def test_digipay_create_and_verify_paid(http, fake_cache):
    adapter = digipay_adapter(http, fake_cache)
    http.queue((200, {"access_token": "tok", "expires_in": 3600}))
    http.queue(
        (
            200,
            {
                "result": {"status": 0, "message": "ok"},
                "ticket": "TK1",
                "trackingCode": "TK1",
                "redirectUrl": "https://pay.digipay/TK1",
            },
        )
    )

    result = adapter.create_payment(amount_toman=50000, description="Plan", order_id="INV-1", callback="https://app/cb")

    assert result.token == "TK1"
    assert result.redirect_url == "https://pay.digipay/TK1"
    assert result.meta["provider_id"]
    assert "tickets/business?type=11" in http.last_url()
    assert http.last_body()["amount"] == 500000
    assert http.calls[-1]["headers"]["Authorization"] == "Bearer tok"
    assert http.calls[-1]["headers"]["Digipay-Version"]

    http.queue((200, {"result": {"status": 0}, "amount": 500000, "rrn": "RRN1"}))
    verified = adapter.verify("TK1", 50000, {"providerId": result.meta["provider_id"]})

    assert verified.status == GatewayStatus.PAID
    assert verified.amount_toman == 50000
    assert verified.ref_id == "RRN1"


def test_digipay_repeated_verify_is_failed_not_paid(http, fake_cache):
    adapter = digipay_adapter(http, fake_cache)
    seed_digipay_token(adapter, fake_cache)
    http.queue((200, {"result": {"status": 9010, "message": "verify failed"}}))

    verified = adapter.verify("TK1", 50000, {"providerId": "P1"})

    assert verified.status == GatewayStatus.FAILED
    assert "9006" not in http.last_url()


def test_digipay_verify_unavailable(http, fake_cache):
    adapter = digipay_adapter(http, fake_cache)
    seed_digipay_token(adapter, fake_cache)
    http.queue((200, {"result": {"status": 9006, "message": "gateway unreachable"}}))
    with pytest.raises(GatewayUnavailable):
        adapter.verify("TK1", 50000, {"providerId": "P1"})

    http.queue((503, {}))
    with pytest.raises(GatewayUnavailable):
        adapter.verify("TK1", 50000, {"providerId": "P1"})


def test_digipay_processing_code_is_processing(http, fake_cache):
    adapter = digipay_adapter(http, fake_cache)
    seed_digipay_token(adapter, fake_cache)
    http.queue((200, {"result": {"status": 9011, "message": "indeterminate"}}))

    assert adapter.verify("TK1", 50000, {"providerId": "P1"}).status == GatewayStatus.PROCESSING


def test_digipay_oauth_failure_is_unavailable(http, fake_cache):
    adapter = digipay_adapter(http, fake_cache)
    http.queue((500, {}))

    with pytest.raises(GatewayUnavailable):
        adapter.create_payment(amount_toman=50000, description="Plan", order_id="INV-1", callback="https://app/cb")


def test_digipay_callback_meta_and_indicator(http, fake_cache):
    adapter = digipay_adapter(http, fake_cache)
    payload = {"result": "SUCCESS", "trackingCode": "TK1", "providerId": "P1", "amount": 500000}

    assert adapter.extract_callback_token(payload) == "TK1"
    assert adapter.extract_callback_meta(payload) == {"provider_id": "P1"}
    assert adapter.callback_indicates_payment(payload) is True
    assert adapter.callback_indicates_payment({"result": "FAILURE"}) is False
    assert adapter.callback_indicates_payment({}) is None


def test_digipay_reverse_stays_disabled(http, fake_cache):
    adapter = digipay_adapter(http, fake_cache)

    assert adapter.reverse("TK1").status == GatewayStatus.UNAVAILABLE
    assert http.call_count == 0


# ------------------------------------------------------------------- registry
def test_registry_covers_every_configured_code():
    from plane.billing.models import GatewayCode

    assert set(GatewayCode.values) == set(supported_codes())
    for code in GatewayCode.values:
        assert get_adapter_class(code).code == code

    with pytest.raises(UnknownGatewayError):
        get_adapter_class("not-a-gateway")


def test_every_adapter_shares_the_same_interface():
    for code, credentials in CREDENTIALS.items():
        adapter = build_adapter(make_gateway(code, credentials=credentials))
        assert adapter.code == code
        for method in ("create_payment", "verify", "reverse", "callback_indicates_payment"):
            assert callable(getattr(adapter, method))
        # inquiry is an optional capability, only Zibal exposes it
        assert hasattr(adapter, "inquiry") is (code == "zibal")


def test_amount_unit_conversion_is_configurable_per_gateway():
    gateway = make_gateway("zarinpal")
    rial_gateway = build_adapter(gateway)
    gateway.extra_config = {"amount_unit": "toman"}
    gateway.save(update_fields=["extra_config", "updated_at"])
    toman_gateway = build_adapter(gateway)

    assert rial_gateway.amount_unit == "rial"
    assert rial_gateway.to_gateway_amount(50000) == 500000
    assert toman_gateway.amount_unit == "toman"
    assert toman_gateway.to_gateway_amount(50000) == 50000
