# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared gateway abstraction: HTTP transport, amount conversion, results."""

# Python imports
import json
import socket
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from urllib.parse import urlencode

# Module imports
from plane.billing.services.credentials import decrypt_credentials

DEFAULT_TIMEOUT_SECONDS = 20
AMOUNT_UNIT_FACTORS = {"toman": 1, "rial": 10}


class GatewayStatus:
    PAID = "paid"
    FAILED = "failed"
    PROCESSING = "processing"
    UNAVAILABLE = "unavailable"


class GatewayError(Exception):
    """Base class for every gateway level error."""


class GatewayUnavailable(GatewayError):
    """The gateway could not be reached or is temporarily unable to serve."""


class GatewayValidationError(GatewayError):
    """The request was rejected locally, before reaching the gateway."""


@dataclass
class CreatePaymentResult:
    redirect_url: str
    token: str
    raw: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    # gateway identifiers that the caller must persist (e.g. Digipay providerId)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VerifyResult:
    status: str
    amount_toman: Optional[int] = None
    ref_id: str = ""
    fee: Optional[int] = None
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)
    already_verified: bool = False


@dataclass
class ReverseResult:
    status: str
    message: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


def http_request(
    method: str,
    url: str,
    headers: Optional[Dict[str, str]] = None,
    json_body: Optional[Dict[str, Any]] = None,
    form: Optional[Dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> "tuple[int, Any]":
    """Perform one HTTP call without automatic retries.

    Network level failures raise ``GatewayUnavailable`` so every adapter maps
    transport problems onto the same status vocabulary.
    """
    request_headers = dict(headers or {})
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    elif form is not None:
        data = urlencode(form).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")

    request = urllib.request.Request(url, data=data, headers=request_headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            status_code = int(response.status)
    except urllib.error.HTTPError as exc:  # 4xx / 5xx still carry a body
        body = exc.read().decode("utf-8", errors="replace")
        status_code = int(exc.code)
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        raise GatewayUnavailable(f"{method.upper()} {url} failed: {exc}") from exc

    try:
        payload = json.loads(body) if body else {}
    except (TypeError, ValueError):
        payload = {"raw_body": body}
    if not isinstance(payload, dict):
        payload = {"raw_body": payload}
    return status_code, payload


class BaseGateway(ABC):
    """Uniform interface implemented by every payment gateway adapter."""

    code: str = ""
    default_base_url: str = ""
    default_sandbox_base_url: str = ""
    # unit the provider expects for the amount field
    amount_unit: str = "toman"
    supports_reverse: bool = False
    # provider side hard limits
    max_amount_toman: Optional[int] = None
    min_amount_toman: Optional[int] = None
    max_description_length: Optional[int] = None

    def __init__(self, gateway, timeout: Optional[float] = None):
        self.gateway = gateway
        self.credentials = decrypt_credentials(gateway.credentials)
        self.extra_config = gateway.extra_config or {}
        self.is_sandbox = bool(gateway.is_sandbox)
        self.timeout = float(self.extra_config.get("timeout") or timeout or DEFAULT_TIMEOUT_SECONDS)
        self.amount_unit = (self.extra_config.get("amount_unit") or self.amount_unit).lower()
        self.max_amount_toman = self.extra_config.get("max_amount_toman", self.max_amount_toman)
        self.min_amount_toman = self.extra_config.get("min_amount_toman", self.min_amount_toman)
        self.callback_url = self.extra_config.get("callback_url") or ""

    # ------------------------------------------------------------------ utils
    @property
    def base_url(self) -> str:
        override = self.extra_config.get("base_url")
        if override:
            return str(override).rstrip("/")
        if self.is_sandbox and self.default_sandbox_base_url:
            return self.default_sandbox_base_url.rstrip("/")
        return self.default_base_url.rstrip("/")

    def url_for(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    def credential(self, key: str, default=None):
        return self.credentials.get(key, self.extra_config.get(key, default))

    def unit_factor(self) -> int:
        factor = AMOUNT_UNIT_FACTORS.get(self.amount_unit)
        if factor is None:
            raise GatewayValidationError(f"Unsupported amount unit: {self.amount_unit}")
        return factor

    def to_gateway_amount(self, amount_toman: int) -> int:
        """Convert the canonical internal amount (toman) to the provider unit."""
        amount = int(amount_toman or 0)
        if amount <= 0:
            raise GatewayValidationError("Amount must be greater than zero.")
        if self.min_amount_toman and amount < int(self.min_amount_toman):
            raise GatewayValidationError(f"Amount is below the gateway minimum of {self.min_amount_toman} toman.")
        if self.max_amount_toman and amount > int(self.max_amount_toman):
            raise GatewayValidationError(f"Amount exceeds the gateway limit of {self.max_amount_toman} toman.")
        return amount * self.unit_factor()

    def from_gateway_amount(self, amount) -> Optional[int]:
        """Convert a provider unit amount back to the canonical toman amount."""
        if amount in (None, ""):
            return None
        try:
            value = int(amount)
        except (TypeError, ValueError):
            return None
        factor = self.unit_factor()
        if value % factor:
            return None
        return value // factor

    def validate_description(self, description: str) -> str:
        text = (description or "")[: self.max_description_length] if self.max_description_length else description or ""
        return text

    def _request(self, method: str, url: str, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        kwargs.setdefault("headers", {})
        return http_request(method, url, **kwargs)

    # ------------------------------------------------------------- interface
    @abstractmethod
    def create_payment(
        self,
        amount_toman: int,
        description: str,
        order_id: str,
        callback: str,
        mobile: str = "",
    ) -> CreatePaymentResult:
        """Create a payment and return the user facing redirect."""

    @abstractmethod
    def verify(self, token: str, amount_toman: int, callback_payload: Optional[dict] = None) -> VerifyResult:
        """Verify a payment token and map the gateway answer onto GatewayStatus."""

    def reverse(self, token: str, context: Optional[dict] = None) -> ReverseResult:
        """Optional reverse / refund, only for gateways that support it."""
        return ReverseResult(
            status=GatewayStatus.UNAVAILABLE,
            message=f"Reverse is not supported by {self.code}.",
        )

    def extract_callback_token(self, payload: dict) -> str:
        """Extract the gateway token out of a raw callback payload."""
        return ""

    def extract_callback_meta(self, payload: dict) -> dict:
        """Named identifiers a raw callback carries.

        The values are persisted on the transaction so a later callback, which
        may no longer contain the ticket token, can still be matched, and so
        the adapter has the merchant side ids verify requires.
        """
        return {}

    def extract_callback_refs(self, payload: dict) -> list:
        """Extra identifiers a callback carries, used to locate the transaction."""
        return [str(value) for value in self.extract_callback_meta(payload or {}).values() if value not in (None, "")]

    def mark_unhealthy(self, message: str) -> None:
        try:
            self.gateway.mark_unhealthy(message)
        except Exception:  # pragma: no cover - health bookkeeping is best effort
            pass

    def mark_healthy(self) -> None:
        try:
            self.gateway.mark_healthy()
        except Exception:  # pragma: no cover - health bookkeeping is best effort
            pass
