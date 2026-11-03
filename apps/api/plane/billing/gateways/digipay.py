# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Digipay UPG adapter (api.mydigipay.com / uat.mydigipay.info).

Contract taken from sources/digipay_upg.txt:
  * ``POST oauth/token`` is form encoded with ``grant_type=password`` plus the
    client credentials in an ``Authorization: Basic base64(client_id:client_secret)``
    header,
  * ``POST tickets/business?type=11`` sends a JSON body with the mandatory
    ``amount``, ``cellNumber``, ``providerId`` and ``callbackUrl`` and the
    headers ``Agent: WEB`` and ``Digipay-Version``,
  * the answer carries ``result.status`` (0 = success) together with the
    ``ticket`` identifier and the ``redirectUrl`` / ``payUrl`` the browser has
    to visit. That ticket is the ``trackingCode`` that comes back in the
    callback and in the verify call,
  * ``POST purchases/verify?type=<n>`` takes ``trackingCode`` and ``providerId``
    and answers ``result.status`` where 9011 means "indeterminate, call verify
    again" and 9010 means "verification failed". Every other non zero code is a
    definitive failure,
  * ``POST reverse?type=<n>`` takes the same pair and may only be called once,
    within 25 minutes.
"""

# Python imports
import base64
import uuid
from typing import Optional

# Django imports
from django.core.cache import cache

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

DIGIPAY_VERSION = "2022-02-02"
AGENT = "WEB"
DEFAULT_TICKET_TYPE = 11

RESULT_SUCCESS = 0
RESULT_PROCESSING = 9011
UNAVAILABLE_CODES = {9006}
REVERSE_WINDOW_MINUTES = 25

# documented result.status messages, used only for logging context
RESULT_CODES = {
    0: "عملیات با موفقیت انجام شد",
    1054: "اطلاعات ورودی اشتباه می باشد",
    9000: "اطلاعات خرید یافت نشد",
    9001: "توکن پرداخت معتبر نمی باشد",
    9003: "خرید مورد نظر منقضی شده است",
    9004: "خرید مورد نظر درحال انجام است",
    9005: "خرید قابل پرداخت نمی باشد",
    9006: "خطا در برقراری ارتباط با درگاه پرداخت",
    9007: "خرید با موفقیت انجام نشده است",
    9008: "این خرید با داده های متفاوتی قبلا ثبت شده است",
    9009: "محدوده زمانی تایید تراکنش گذشته است",
    9010: "تایید خرید ناموفق بود",
    9011: "نتیجه تایید خرید نامشخص است",
    9012: "وضعیت خرید برای این درخواست صحیح نمی باشد",
    9030: "ورود شماره مهراه برای کاربران ثبت نام شده الزامی است",
    9031: "اعطای تیکت برای کاربر مورد نظر امکان پذیر نمی باشد",
}


class DigipayGateway(BaseGateway):
    code = "digipay"
    default_base_url = "https://api.mydigipay.com/digipay/api"
    default_sandbox_base_url = "https://uat.mydigipay.info/digipay/api"
    # the documentation does not state the amount unit unambiguously, it stays
    # a per gateway setting in extra_config and needs a UAT confirmation
    amount_unit = "rial"
    # the archived documentation contradicts itself about the reverse body
    # (purchaseTrackingCode in one revision, trackingCode in the next), so the
    # call stays disabled until a sandbox trial confirms the contract
    supports_reverse = False

    # ------------------------------------------------------------- helpers
    @property
    def ticket_type(self) -> int:
        return int(self.extra_config.get("ticket_type", DEFAULT_TICKET_TYPE))

    @property
    def api_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token()}",
            "Agent": str(self.extra_config.get("agent", AGENT)),
            "Digipay-Version": str(self.extra_config.get("digipay_version", DIGIPAY_VERSION)),
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json",
        }

    @staticmethod
    def _result(payload: dict) -> tuple:
        """Return ``(status_code, message)`` out of the ``result`` envelope."""
        result = payload.get("result")
        if not isinstance(result, dict):
            return None, str(payload.get("message") or "")
        code = result.get("status")
        try:
            code = int(code) if code is not None else None
        except (TypeError, ValueError):
            code = None
        return code, str(result.get("message") or "")

    def new_provider_id(self) -> str:
        """Digipay requires a merchant side unique id per purchase."""
        prefix = str(self.extra_config.get("provider_id_prefix") or "")
        return f"{prefix}{uuid.uuid4().int % (10**19):019d}"

    @staticmethod
    def _provider_id(payload: dict) -> str:
        payload = payload or {}
        return str(payload.get("providerId") or payload.get("ProviderId") or "")

    def _require(self, *keys: str) -> list:
        values = []
        for key in keys:
            value = self.credential(key)
            if not value:
                raise GatewayValidationError(f"Digipay {key} is not configured.")
            values.append(value)
        return values

    def access_token(self) -> str:
        """Fetch (and cache) the OAuth access token."""
        cache_key = f"billing:digipay:token:{self.gateway.code}:{self.gateway.id}"
        cached = cache.get(cache_key)
        if cached:
            return str(cached)

        client_id, client_secret = self._require("client_id", "client_secret")
        basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        form = {
            "grant_type": self.credential("grant_type", "password"),
            "username": self.credential("username", ""),
            "password": self.credential("password", ""),
        }
        status_code, payload = self._request(
            "POST",
            self.url_for("oauth/token"),
            headers={"Authorization": f"Basic {basic}", "Accept": "application/json"},
            form={key: value for key, value in form.items() if value != ""},
        )
        token = payload.get("access_token")
        if status_code >= 500:
            self.mark_unhealthy(f"Digipay OAuth failed with HTTP {status_code}")
            raise GatewayUnavailable(f"Digipay OAuth HTTP {status_code}")
        if not token:
            self.mark_unhealthy("Digipay OAuth returned no access token")
            raise GatewayUnavailable("Digipay OAuth returned no access token")
        try:
            ttl = max(30, int(payload.get("expires_in") or 3600) - 60)
        except (TypeError, ValueError):
            ttl = 3540
        cache.set(cache_key, token, ttl)
        return str(token)

    # ------------------------------------------------------------ interface
    def create_payment(self, amount_toman, description, order_id, callback, mobile=""):
        provider_id = self.new_provider_id()
        body = {
            "amount": self.to_gateway_amount(amount_toman),
            "providerId": provider_id,
            "callbackUrl": callback,
        }
        if mobile:
            # only sent when the caller knows it, result 9030 is raised by
            # Digipay itself when the registered account demands a cell number
            body["cellNumber"] = str(mobile)
        elif self.extra_config.get("require_mobile"):
            raise GatewayValidationError("Digipay requires a mobile number for this account.")
        status_code, payload = self._request(
            "POST",
            self.url_for(f"tickets/business?type={self.ticket_type}"),
            headers=self.api_headers,
            json_body=body,
        )
        if status_code >= 500:
            self.mark_unhealthy(f"Digipay ticket failed with HTTP {status_code}")
            raise GatewayUnavailable(f"Digipay ticket HTTP {status_code}")
        code, message = self._result(payload)
        ticket = str(payload.get("ticket") or payload.get("trackingCode") or "")
        redirect_url = str(payload.get("redirectUrl") or payload.get("payUrl") or "")
        if ticket and redirect_url and code in (RESULT_SUCCESS, None):
            self.mark_healthy()
            return CreatePaymentResult(
                redirect_url=redirect_url,
                token=ticket,
                raw=payload,
                message=message,
                meta={"provider_id": provider_id},
            )
        if code in UNAVAILABLE_CODES:
            self.mark_unhealthy(f"Digipay {code}: {message}")
            raise GatewayUnavailable(f"Digipay {code}: {message}")
        raise GatewayValidationError(message or f"Digipay rejected the ticket ({code})")

    def verify(self, token, amount_toman, callback_payload=None):
        callback_payload = callback_payload or {}
        provider_id = self._provider_id(callback_payload)
        if not provider_id:
            raise GatewayValidationError(
                "Digipay verify requires the providerId generated when the ticket was created."
            )
        # the ticket id and the callback trackingCode are not documented to be
        # the same value, the callback identity wins when it is present
        tracking_code = str(callback_payload.get("trackingCode") or token)
        status_code, payload = self._request(
            "POST",
            self.url_for(f"purchases/verify?type={self.ticket_type}"),
            headers=self.api_headers,
            json_body={"trackingCode": tracking_code, "providerId": provider_id},
        )
        if status_code >= 500:
            self.mark_unhealthy(f"Digipay verify failed with HTTP {status_code}")
            raise GatewayUnavailable(f"Digipay verify HTTP {status_code}")
        code, message = self._result(payload)
        if code == RESULT_PROCESSING:
            return VerifyResult(
                status=GatewayStatus.PROCESSING,
                message=message or "Digipay verification is indeterminate, retry later",
                raw=payload,
            )
        if code in UNAVAILABLE_CODES:
            self.mark_unhealthy(f"Digipay {code}: {message}")
            raise GatewayUnavailable(f"Digipay {code}: {message}")
        if status_code == 200 and code == RESULT_SUCCESS:
            self.mark_healthy()
            return VerifyResult(
                status=GatewayStatus.PAID,
                amount_toman=self.from_gateway_amount(payload.get("amount"))
                or self.from_gateway_amount(callback_payload.get("amount")),
                ref_id=str(payload.get("rrn") or payload.get("trackingCode") or token),
                message=message or "Paid",
                raw=payload,
            )
        return VerifyResult(
            status=GatewayStatus.FAILED,
            amount_toman=self.from_gateway_amount(payload.get("amount"))
            or self.from_gateway_amount(callback_payload.get("amount")),
            ref_id=str(payload.get("trackingCode") or token),
            message=message or RESULT_CODES.get(code, f"Digipay result {code}"),
            raw=payload,
        )

    def reverse(self, token: str, context: Optional[dict] = None) -> ReverseResult:
        return ReverseResult(
            status=GatewayStatus.UNAVAILABLE,
            message=(
                "Digipay reverse stays disabled because the archived documentation "
                "disagrees on the purchase tracking field."
            ),
        )

    # ------------------------------------------------------------ callbacks
    def extract_callback_token(self, payload: dict) -> str:
        payload = payload or {}
        # the callback names the purchase trackingCode, the ticket answer calls it ticket
        return str(payload.get("trackingCode") or payload.get("ticket") or "")

    def extract_callback_meta(self, payload: dict) -> dict:
        provider_id = self._provider_id(payload)
        return {"provider_id": provider_id} if provider_id else {}

    def callback_indicates_payment(self, payload: dict) -> Optional[bool]:
        payload = payload or {}
        result = payload.get("result") or payload.get("Result")
        if result in (None, ""):
            return None
        return str(result).strip().upper() == "SUCCESS"
