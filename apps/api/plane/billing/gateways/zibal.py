# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Zibal (gateway.zibal.ir) v1 adapter.

Contract taken from sources/zibal_ipg.json:
  * every endpoint takes and returns a JSON body,
  * ``amount`` is always expressed in rial,
  * ``/v1/request`` answers ``trackId`` + ``result`` and the browser is sent to
    ``/start/{trackId}``,
  * ``/v1/verify`` answers ``result``/``status`` where result 100 = verified
    now, 201 = already verified, 202 = not verified yet, 203 = invalid
    trackId, and status -1 = not paid, 2 = paid but unverified, 1 = verified.
"""

# Python imports
from typing import Optional

# Django imports
from django.conf import settings

# Module imports
from plane.billing.gateways.base import (
    BaseGateway,
    CreatePaymentResult,
    GatewayStatus,
    GatewayUnavailable,
    GatewayValidationError,
    VerifyResult,
)

RESULT_VERIFIED = 100
RESULT_ALREADY_VERIFIED = 201
RESULT_UNPAID = 202
RESULT_INVALID_TRACK_ID = 203
UNAVAILABLE_RESULTS = {21, 102, 103, 104, 106, 115}

STATUS_VERIFIED = 1
STATUS_PAID_UNVERIFIED = 2
STATUS_UNPAID = -1

SANDBOX_MERCHANT = "zibal"


class ZibalGateway(BaseGateway):
    code = "zibal"
    default_base_url = "https://gateway.zibal.ir"
    default_sandbox_base_url = "https://gateway.zibal.ir"
    amount_unit = "rial"

    @property
    def merchant(self) -> str:
        merchant = self.credential("merchant") or ""
        if not merchant:
            raise GatewayValidationError("Zibal merchant is not configured.")
        if self.is_sandbox and merchant == SANDBOX_MERCHANT:
            # the sandbox merchant is a test credential, never production traffic
            return merchant
        return str(merchant)

    @property
    def public_base_url(self) -> str:
        return str(
            self.extra_config.get("public_base_url") or getattr(settings, "WEB_URL", "") or "http://localhost:3000"
        ).rstrip("/")

    def start_url(self, track_id: str) -> str:
        """Absolute Zibal start URL, built from configuration only.

        The caller supplied ``redirect_url`` is never honoured, the target is
        always derived from the configured gateway base URL.
        """
        template = self.extra_config.get("start_url") or ""
        if template:
            if "{track_id}" in template:
                return template.replace("{track_id}", str(track_id))
            return f"{template.rstrip('/')}/{track_id}"
        return f"{self.base_url}/start/{track_id}"

    def create_payment(self, amount_toman, description, order_id, callback, mobile=""):
        body = {
            "merchant": self.merchant,
            "amount": self.to_gateway_amount(amount_toman),
            "callbackUrl": callback,
            "description": self.validate_description(description),
            "orderId": order_id,
        }
        if mobile:
            body["mobile"] = str(mobile)
        status_code, payload = self._request("POST", self.url_for("v1/request"), json_body=body)
        if status_code >= 500:
            self.mark_unhealthy(f"Zibal request failed with HTTP {status_code}")
            raise GatewayUnavailable(f"Zibal HTTP {status_code}")
        result = payload.get("result")
        if result == RESULT_VERIFIED and payload.get("trackId"):
            track_id = str(payload["trackId"])
            # Zibal validates the Referer of the start request against the
            # merchant domain, therefore the browser goes through our own
            # intermediate URL which then redirects to the fixed gateway URL.
            return CreatePaymentResult(
                redirect_url=f"{self.public_base_url}/api/billing/callback/zibal/start/{track_id}/",
                token=track_id,
                raw=payload,
                message=str(payload.get("message") or ""),
            )
        message = str(payload.get("message") or "")
        if result in UNAVAILABLE_RESULTS:
            self.mark_unhealthy(f"Zibal result {result}: {message}")
            raise GatewayUnavailable(f"Zibal result {result}: {message}")
        raise GatewayValidationError(message or f"Zibal rejected the request: result={result}")

    def _lookup(self, path: str, token: str) -> dict:
        status_code, payload = self._request(
            "POST",
            self.url_for(path),
            json_body={"merchant": self.merchant, "trackId": token},
        )
        if status_code >= 500:
            self.mark_unhealthy(f"Zibal {path} failed with HTTP {status_code}")
            raise GatewayUnavailable(f"Zibal {path} HTTP {status_code}")
        return payload

    def _map_result(self, payload: dict, fallback_amount: Optional[int]) -> VerifyResult:
        """Map a verify / inquiry answer onto the internal status vocabulary.

        This is the single point where the rial amount is converted back to the
        canonical toman amount.
        """
        result = payload.get("result")
        status = payload.get("status")
        message = str(payload.get("message") or "")
        amount_toman = self.from_gateway_amount(payload.get("amount")) or fallback_amount
        ref_id = str(payload.get("refNumber") or payload.get("trackId") or "")
        already_verified = result == RESULT_ALREADY_VERIFIED

        if result in UNAVAILABLE_RESULTS:
            self.mark_unhealthy(f"Zibal result {result}: {message}")
            raise GatewayUnavailable(f"Zibal result {result}: {message}")
        if status == STATUS_PAID_UNVERIFIED:
            # money moved but Zibal has not confirmed it yet, retry later
            return VerifyResult(
                status=GatewayStatus.PROCESSING,
                amount_toman=amount_toman,
                ref_id=ref_id,
                message=message or "Paid but not verified yet",
                raw=payload,
            )
        if result == RESULT_INVALID_TRACK_ID:
            return VerifyResult(
                status=GatewayStatus.FAILED,
                amount_toman=amount_toman,
                ref_id=ref_id,
                message=message or "Zibal trackId is invalid",
                raw=payload,
            )
        if result in (RESULT_VERIFIED, RESULT_ALREADY_VERIFIED) and status in (
            STATUS_VERIFIED,
            None,
        ):
            return VerifyResult(
                status=GatewayStatus.PAID,
                amount_toman=amount_toman,
                ref_id=ref_id,
                message=message or ("Already verified" if already_verified else "Paid"),
                raw=payload,
                already_verified=already_verified,
            )
        if status == STATUS_UNPAID or result == RESULT_UNPAID:
            return VerifyResult(
                status=GatewayStatus.FAILED,
                amount_toman=amount_toman,
                ref_id=ref_id,
                message=message or "Payment was not completed",
                raw=payload,
            )
        return VerifyResult(
            status=GatewayStatus.FAILED,
            amount_toman=amount_toman,
            ref_id=ref_id,
            message=message or f"Zibal result={result} status={status}",
            raw=payload,
        )

    def verify(self, token, amount_toman, callback_payload=None):
        payload = self._lookup("v1/verify", token)
        result = self._map_result(payload, int(amount_toman))
        if result.status == GatewayStatus.PAID:
            self.mark_healthy()
        return result

    def inquiry(self, token: str, amount_toman: Optional[int] = None) -> VerifyResult:
        """Polling fallback used when the browser callback is lost."""
        payload = self._lookup("v1/inquiry", token)
        return self._map_result(payload, amount_toman)

    def extract_callback_token(self, payload: dict) -> str:
        payload = payload or {}
        return str(payload.get("trackId") or "")

    def extract_callback_meta(self, payload: dict) -> dict:
        payload = payload or {}
        return {"invoice_number": str(payload["orderId"])} if payload.get("orderId") else {}

    def callback_indicates_payment(self, payload: dict) -> Optional[bool]:
        payload = payload or {}
        if "success" not in payload:
            return None
        return str(payload.get("success")) in ("1", "true", "True")
