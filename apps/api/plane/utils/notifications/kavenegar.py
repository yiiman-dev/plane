# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Kavenegar SMS provider.

Reference: https://kavenegar.com/sdk.html
"""

# Python imports
import logging
import re
from typing import Any, Dict, Optional

import requests

# Module imports
from plane.db.models.notification import NOTIFICATION_CHANNEL_SMS
from plane.license.utils.instance_value import get_kavenegar_configuration
from .base import (
    DEFAULT_HTTP_TIMEOUT,
    ChannelMessage,
    ChannelResult,
    NotificationChannelProvider,
    NotificationChannelValidationError,
)


logger = logging.getLogger("plane.bgtasks.notification.channel")

KAVENEGAR_API_BASE_URL = "https://api.kavenegar.com/v1"
# Iranian mobile numbers are sent in the +98XXXXXXXXXX format
IRAN_MOBILE_PATTERN = re.compile(r"^(?:\+?98|0)?(9\d{9})$")


class KavenegarProvider(NotificationChannelProvider):
    """Send SMS through the Kavenegar API"""

    channel = NOTIFICATION_CHANNEL_SMS
    # Kavenegar accepts up to 900 characters per message, keep some room for the sender note
    max_message_length = 700

    def is_configured(self) -> bool:
        """Return True when the api key and the dedicated line are set"""
        api_key, sender_line = get_kavenegar_configuration()
        return bool(api_key and sender_line)

    def get_recipient_address(self, user: Any) -> Optional[str]:
        """Return the mobile number of the user in the E164 format"""
        return normalize_receptor(getattr(user, "mobile_number", None))

    def check_config(self) -> None:
        """Validate the instance credentials

        :raises NotificationChannelValidationError: when credentials are missing
        """
        api_key, sender_line = get_kavenegar_configuration()
        if not api_key:
            raise NotificationChannelValidationError("KAVENEGAR_API_KEY is not configured on this instance")
        if not sender_line:
            raise NotificationChannelValidationError("KAVENEGAR_SENDER_LINE is not configured on this instance")

    def get_account_info(self) -> Dict[str, Any]:
        """Return the account balance and remaining credit

        :raises NotificationChannelValidationError: when the credentials are rejected
        """
        api_key, _sender_line = get_kavenegar_configuration()
        if not api_key:
            raise NotificationChannelValidationError("KAVENEGAR_API_KEY is not configured on this instance")
        # The api key lives in the url, it is never logged
        response = requests.get(
            f"{KAVENEGAR_API_BASE_URL}/{api_key}/account/info.json",
            timeout=DEFAULT_HTTP_TIMEOUT,
        )
        payload = parse_response(response, f"account info for the configured api key returned {response.status_code}")
        entries = payload.get("entries") or []
        entry = entries[0] if entries else {}
        return {"status": entry.get("status"), "message": entry.get("message"), "remaining_credit": entry.get("remain")}

    def send(self, address: str, message: ChannelMessage) -> ChannelResult:
        """Deliver an SMS, returning the outcome instead of raising"""
        try:
            api_key, sender_line = get_kavenegar_configuration()
        except Exception as e:  # pragma: no cover - defensive, configuration read failure
            logger.error("Kavenegar configuration could not be read: %s", type(e).__name__)
            return ChannelResult(ok=False, error_code="not_configured", error_message="Kavenegar is not configured")

        if not api_key or not sender_line:
            return ChannelResult(
                ok=False,
                error_code="not_configured",
                error_message="Kavenegar is not configured on this instance",
            )

        receptor = normalize_receptor(address)
        if not receptor:
            return ChannelResult(ok=False, error_code="invalid_receptor", error_message="Invalid phone number")

        try:
            response = requests.post(
                f"{KAVENEGAR_API_BASE_URL}/{api_key}/sms/send.json",
                json={"receptor": receptor, "sender": sender_line, "message": message.text},
                timeout=DEFAULT_HTTP_TIMEOUT,
            )
        except requests.RequestException as e:
            logger.error("Kavenegar request failed: %s", type(e).__name__)
            return ChannelResult(ok=False, error_code="request_failed", error_message="Kavenegar is unreachable")

        entries = parse_response(response, f"sms send returned {response.status_code}").get("entries") or []
        entry = entries[0] if entries else {}
        status = entry.get("status", 200)
        if status == 200:
            return ChannelResult(
                ok=True,
                provider_message_id=str(entry.get("messageid")) if entry.get("messageid") else None,
            )
        return ChannelResult(
            ok=False,
            error_code=str(status),
            error_message=str(entry.get("message") or "Kavenegar rejected the message")[:255],
        )


def normalize_receptor(receptor: Optional[str]) -> Optional[str]:
    """Normalize an Iranian mobile number into the +98XXXXXXXXXX format"""
    if not receptor:
        return None
    value = re.sub(r"[\s\-()]", "", str(receptor))
    match = IRAN_MOBILE_PATTERN.match(value)
    if match:
        return f"+98{match.group(1)}"
    # Non mobile receptors, ie landlines, are passed through untouched
    if not re.match(r"^\+?\d{8,15}$", value):
        return None
    return value


def parse_response(response: requests.Response, failure_message: str) -> Dict[str, Any]:
    """Parse a Kavenegar json response

    :raises NotificationChannelValidationError: when the payload is not a valid success payload
    """
    try:
        payload = response.json()
    except ValueError:
        raise NotificationChannelValidationError(failure_message)

    if not isinstance(payload, dict):
        raise NotificationChannelValidationError(failure_message)

    # Kavenegar reports transport level errors on the top level return object
    # and per entry errors on the entries, both are handled by the callers
    return payload