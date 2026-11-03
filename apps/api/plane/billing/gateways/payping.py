# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""PayPing v3 adapter (api.payping.ir).

Contract taken from sources/payping_openapi.json:
  * ``POST /v3/pay`` answers ``PaymentDto`` directly (``paymentCode``, ``url``,
    ``amount``, ``payerWage``, ``businessWage``, ``gatewayAmount``,
    ``paypingVat``), there is no ``data`` envelope,
  * ``POST /v3/pay/verify`` requires ``paymentCode``, integer ``paymentRefId``
    and ``amount``; ``amount`` is the order amount and must be compared with
    the local database value, ``gatewayAmount`` carries the fee on top,
  * failures use RFC 7807 problem details: ``detail``/``title`` plus
    ``metaData.code``. HTTP 409 with ``metaData.code == 110`` means the
    transaction was verified before and must be treated as paid, HTTP 202/502
    mean "still processing, call verify again",
  * the merchant callback posts ``status`` / ``errorCode`` / ``data`` where
    ``data`` carries ``clientRefId``, ``paymentCode``, ``paymentRefId`` and
    ``amount``.
"""

# Python imports
import json
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

# Only the two codes the OpenAPI document actually enumerates are listed here.
# Every other business code is passed through as a failed result carrying the
# raw problem details instead of an invented translation.
PAYPING_CODES = {
    101: "اطلاعات ورودی ارسالی نامعتبر است",
    110: "این تراکنش قبلاً وریفای شده است",
}
CODE_ALREADY_VERIFIED = 110

HTTP_SUCCESS = 200
HTTP_ALREADY_VERIFIED = 409
HTTP_PROCESSING = (202, 502)
HTTP_AUTH = (401, 403)

VERIFY_WINDOW_MINUTES = 10
REVERSE_WINDOW_MINUTES = 30


class PayPingGateway(BaseGateway):
    code = "payping"
    default_base_url = "https://api.payping.ir"
    # the OpenAPI document does not advertise a sandbox host
    default_sandbox_base_url = "https://api.payping.ir"
    amount_unit = "toman"
    min_amount_toman = 100
    max_amount_toman = 200_000_000
    supports_reverse = True

    @property
    def api_token(self) -> str:
        token = self.credential("api_token") or ""
        if not token:
            raise GatewayValidationError("PayPing api_token is not configured.")
        return str(token)

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }

    # ------------------------------------------------------------- helpers
    @staticmethod
    def _dto(payload: dict) -> dict:
        """PayPing answers direct DTOs; ``data`` is only a forward fallback."""
        data = payload.get("data")
        return data if isinstance(data, dict) else payload

    @staticmethod
    def _field(dto: dict, *names: str):
        for name in names:
            value = dto.get(name)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _meta(payload: dict) -> dict:
        meta = payload.get("metaData") or payload.get("metadata") or {}
        return meta if isinstance(meta, dict) else {}

    @classmethod
    def _meta_code(cls, payload: dict) -> Optional[int]:
        code = cls._meta(payload).get("code")
        if code is None:
            return None
        try:
            return int(code)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _message(cls, payload: dict, code: Optional[int] = None) -> str:
        meta = cls._meta(payload)
        message = payload.get("detail") or payload.get("message") or ""
        if not message and isinstance(meta.get("message"), str):
            message = meta["message"]
        if not message:
            errors = meta.get("errors")
            if isinstance(errors, list) and errors:
                message = "; ".join(str(error.get("message") if isinstance(error, dict) else error) for error in errors)
        if not message and code is not None:
            message = PAYPING_CODES.get(code, f"PayPing code {code}")
        return str(message or "")

    @classmethod
    def _callback_data(cls, payload: dict) -> dict:
        """The merchant callback sends ``data`` as a JSON encoded string."""
        data = payload.get("data")
        if isinstance(data, dict):
            return data
        if isinstance(data, str) and data.strip():
            try:
                decoded = json.loads(data)
            except (TypeError, ValueError):
                return {}
            return decoded if isinstance(decoded, dict) else {}
        return {}

    def _payment_ref_id(self, payload: dict, token: str) -> int:
        data = self._callback_data(payload)
        raw = self._field(data, "paymentRefId", "PaymentRefId") or self._field(payload, "paymentRefId", "PaymentRefId")
        if raw in (None, ""):
            raise GatewayValidationError(
                "PayPing verify requires paymentRefId, it is only sent in the merchant callback."
            )
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise GatewayValidationError(f"Invalid PayPing paymentRefId: {raw}") from exc

    # ------------------------------------------------------------ interface
    def create_payment(self, amount_toman, description, order_id, callback, mobile=""):
        body = {
            "amount": self.to_gateway_amount(amount_toman),
            "description": self.validate_description(description),
            "clientRefId": order_id,
            "returnUrl": callback,
            "isReversible": bool(self.extra_config.get("is_reversible", True)),
        }
        if mobile:
            body["payerIdentity"] = str(mobile)
        status_code, payload = self._request("POST", self.url_for("v3/pay"), headers=self.headers, json_body=body)
        if status_code >= 500:
            self.mark_unhealthy(f"PayPing create failed with HTTP {status_code}")
            raise GatewayUnavailable(f"PayPing HTTP {status_code}")
        if status_code in HTTP_AUTH:
            self.mark_unhealthy("PayPing authentication rejected")
            raise GatewayUnavailable("PayPing authentication rejected")

        dto = self._dto(payload)
        url = dto.get("url")
        if status_code == HTTP_SUCCESS and url:
            return CreatePaymentResult(
                redirect_url=str(url),
                token=str(dto.get("paymentCode") or ""),
                raw=payload,
                message=self._message(payload, self._meta_code(payload)),
                meta={"amount": dto.get("amount"), "gatewayAmount": dto.get("gatewayAmount")},
            )
        message = self._message(payload, self._meta_code(payload)) or "PayPing rejected the request."
        raise GatewayValidationError(message)

    def verify(self, token, amount_toman, callback_payload=None):
        callback_payload = callback_payload or {}
        payment_ref_id = self._payment_ref_id(callback_payload, token)
        body = {
            "paymentCode": token,
            "paymentRefId": payment_ref_id,
            "amount": self.to_gateway_amount(amount_toman),
        }
        status_code, payload = self._request(
            "POST", self.url_for("v3/pay/verify"), headers=self.headers, json_body=body
        )
        meta_code = self._meta_code(payload)

        if status_code == HTTP_ALREADY_VERIFIED and meta_code == CODE_ALREADY_VERIFIED:
            meta = self._meta(payload)
            message_payload = meta.get("message")
            dto = message_payload if isinstance(message_payload, dict) else {}
            self.mark_healthy()
            return VerifyResult(
                status=GatewayStatus.PAID,
                amount_toman=self.from_gateway_amount(self._field(dto, "amount", "Amount")),
                ref_id=str(self._field(dto, "paymentRefId", "PaymentRefId") or payment_ref_id),
                message=self._message(payload, meta_code) or "Already verified",
                raw=payload,
                already_verified=True,
            )
        if status_code in HTTP_PROCESSING:
            return VerifyResult(
                status=GatewayStatus.PROCESSING,
                message=self._message(payload, meta_code) or "Payment is still being processed, verify again later",
                raw=payload,
            )
        if status_code >= 500 or status_code in HTTP_AUTH:
            self.mark_unhealthy(f"PayPing verify HTTP {status_code}")
            raise GatewayUnavailable(f"PayPing verify HTTP {status_code}")
        if status_code != HTTP_SUCCESS:
            return VerifyResult(
                status=GatewayStatus.FAILED,
                message=self._message(payload, meta_code) or f"PayPing verify failed with HTTP {status_code}",
                raw=payload,
            )

        dto = self._dto(payload)
        self.mark_healthy()
        return VerifyResult(
            status=GatewayStatus.PAID,
            amount_toman=self.from_gateway_amount(self._field(dto, "amount", "Amount")),
            ref_id=str(self._field(dto, "paymentRefId", "PaymentRefId") or payment_ref_id),
            message=self._message(payload, meta_code),
            raw=payload,
        )

    def reverse(self, token: str, context: Optional[dict] = None) -> ReverseResult:
        context = context or {}
        raw_ref_id = context.get("payment_ref_id")
        if raw_ref_id in (None, ""):
            return ReverseResult(
                status=GatewayStatus.UNAVAILABLE,
                message="PayPing reverse requires the paymentRefId captured in the callback.",
            )
        status_code, payload = self._request(
            "POST",
            self.url_for("v3/pay/reverse"),
            headers=self.headers,
            json_body={"paymentCode": token, "paymentRefId": int(raw_ref_id)},
        )
        if status_code >= 500 or status_code in HTTP_AUTH:
            self.mark_unhealthy(f"PayPing reverse HTTP {status_code}")
            raise GatewayUnavailable(f"PayPing reverse HTTP {status_code}")
        if status_code == HTTP_SUCCESS:
            return ReverseResult(status=GatewayStatus.PAID, message="Reversed", raw=payload)
        return ReverseResult(
            status=GatewayStatus.FAILED,
            message=self._message(payload, self._meta_code(payload))
            or f"PayPing reverse failed with HTTP {status_code}",
            raw=payload,
        )

    # ------------------------------------------------------------ callbacks
    def extract_callback_token(self, payload: dict) -> str:
        payload = payload or {}
        data = self._callback_data(payload)
        return str(self._field(data, "paymentCode") or self._field(payload, "paymentCode") or "")

    def extract_callback_meta(self, payload: dict) -> dict:
        payload = payload or {}
        data = self._callback_data(payload)
        meta = {}
        client_ref_id = self._field(data, "clientRefId") or self._field(payload, "clientRefId")
        if client_ref_id not in (None, ""):
            meta["invoice_number"] = str(client_ref_id)
        payment_ref_id = self._field(data, "paymentRefId") or self._field(payload, "paymentRefId")
        if payment_ref_id not in (None, ""):
            # mandatory for /v3/pay/verify and only ever sent in this callback
            meta["payment_ref_id"] = str(payment_ref_id)
        return meta

    def callback_indicates_payment(self, payload: dict) -> Optional[bool]:
        payload = payload or {}
        raw_status = payload.get("status")
        if raw_status in (None, ""):
            return None
        return str(raw_status).strip().upper() in ("PAID", "OK", "SUCCESS", "1", "TRUE")
