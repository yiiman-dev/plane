# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""ZarinPal v4 adapter (payment.zarinpal.com)."""

# Python imports
from typing import Optional

# Module imports
from plane.billing.gateways.base import (
    BaseGateway,
    CreatePaymentResult,
    GatewayStatus,
    GatewayUnavailable,
    GatewayValidationError,
    ReverseResult,
    VerifyResult,
)

# Business codes documented by ZarinPal for v4 request/verify.
SUCCESS_CODES = {100}
ALREADY_VERIFIED_CODES = {101}
PROCESSING_CODES = {-52}
FAILED_CODES = {-33, -34, -50, -51, -53, -54}
UNAVAILABLE_CODES = {-10, -11, -12, -13, -14, -15, -16, -17, -18, -19}
# merchant / configuration problems, the money did not move and the payer can retry later
UNAVAILABLE_EXTRA_CODES = {30, 31, 40, 53}
REVERSIBLE_CODES = {100, 101, 102}
REVERSED_CODES = {100, 101, 200, 201}


class ZarinPalGateway(BaseGateway):
    code = "zarinpal"
    default_base_url = "https://payment.zarinpal.com/pg"
    default_sandbox_base_url = "https://sandbox.zarinpal.com/pg"
    amount_unit = "rial"
    supports_reverse = True
    max_amount_toman = 100_000_000  # 100 million toman
    max_description_length = 500

    @property
    def merchant_id(self) -> str:
        merchant_id = self.credential("merchant_id") or ""
        if not merchant_id:
            raise GatewayValidationError("ZarinPal merchant_id is not configured.")
        return str(merchant_id)

    @property
    def currency(self) -> str:
        # IRR (rial) is the documented default, IRT (toman) is accepted too.
        return str(self.extra_config.get("currency") or "IRR").upper()

    def create_payment(self, amount_toman, description, order_id, callback, mobile=""):
        body = {
            "merchant_id": self.merchant_id,
            "amount": self.to_gateway_amount(amount_toman),
            "description": self.validate_description(description),
            "callback_url": callback,
            "currency": self.currency,
            "metadata": {"order_id": order_id, "mobile": mobile or ""},
        }
        status_code, payload = self._request("POST", self.url_for("v4/payment/request.json"), json_body=body)
        data = payload.get("data") or {}
        code = data.get("code")
        if status_code >= 500:
            self.mark_unhealthy(f"ZarinPal request failed with HTTP {status_code}")
            raise GatewayUnavailable(f"ZarinPal returned HTTP {status_code}")
        if code in SUCCESS_CODES:
            authority = str(data.get("authority") or "")
            if not authority:
                raise GatewayUnavailable("ZarinPal returned no authority.")
            redirect_url = self.extra_config.get("start_pay_url") or f"{self.base_url}/StartPay/{authority}"
            return CreatePaymentResult(redirect_url=redirect_url, token=authority, raw=payload)
        message = str(data.get("message") or payload.get("errors") or "ZarinPal rejected the request.")
        if code in UNAVAILABLE_CODES or code in UNAVAILABLE_EXTRA_CODES:
            self.mark_unhealthy(f"ZarinPal code {code}: {message}")
            raise GatewayUnavailable(f"ZarinPal code {code}: {message}")
        if code in PROCESSING_CODES:
            raise GatewayUnavailable(f"ZarinPal code {code}: {message}")
        raise GatewayValidationError(f"ZarinPal code {code}: {message}")

    def verify(self, token, amount_toman, callback_payload=None):
        body = {
            "merchant_id": self.merchant_id,
            "amount": self.to_gateway_amount(amount_toman),
            "authority": token,
        }
        status_code, payload = self._request("POST", self.url_for("v4/payment/verify.json"), json_body=body)
        data = payload.get("data") or {}
        code = data.get("code")
        message = str(data.get("message") or "")

        if status_code >= 500:
            self.mark_unhealthy(f"ZarinPal verify failed with HTTP {status_code}")
            raise GatewayUnavailable(f"ZarinPal verify HTTP {status_code}")

        if code in SUCCESS_CODES or code in ALREADY_VERIFIED_CODES:
            self.mark_healthy()
            return VerifyResult(
                status=GatewayStatus.PAID,
                amount_toman=self.from_gateway_amount(data.get("amount")),
                ref_id=str(data.get("ref_id") or ""),
                fee=self.from_gateway_amount(data.get("fee")),
                message=message or ("Already verified" if code in ALREADY_VERIFIED_CODES else "Verified"),
                raw=payload,
                already_verified=code in ALREADY_VERIFIED_CODES,
            )
        if code in PROCESSING_CODES:
            return VerifyResult(
                status=GatewayStatus.PROCESSING, message=message or "Payment is being processed", raw=payload
            )
        if code in UNAVAILABLE_CODES or code in UNAVAILABLE_EXTRA_CODES:
            self.mark_unhealthy(f"ZarinPal code {code}: {message}")
            raise GatewayUnavailable(f"ZarinPal code {code}: {message}")
        return VerifyResult(
            status=GatewayStatus.FAILED,
            message=message or f"ZarinPal verify failed with code {code}",
            raw=payload,
        )

    def reverse(self, token: str) -> ReverseResult:
        status_code, payload = self._request(
            "POST",
            self.url_for("v4/payment/refund.json"),
            json_body={"merchant_id": self.merchant_id, "authority": token},
        )
        data = payload.get("data") or {}
        code = data.get("code")
        if code in REVERSED_CODES:
            return ReverseResult(status=GatewayStatus.PAID, message="Reversed", raw=payload)
        return ReverseResult(
            status=GatewayStatus.FAILED, message=str(data.get("message") or "Reverse failed"), raw=payload
        )

    def extract_callback_token(self, payload: dict) -> str:
        payload = payload or {}
        return str(payload.get("Authority") or payload.get("authority") or "")

    def callback_indicates_payment(self, payload: dict) -> Optional[bool]:
        """Return False when the payer cancelled, None when unknown."""
        payload = payload or {}
        raw_status = payload.get("Status") or payload.get("status")
        if raw_status is None:
            return None
        return str(raw_status).upper() == "OK"
