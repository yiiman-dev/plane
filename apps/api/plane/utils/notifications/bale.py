# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Bale messenger bot provider.

Reference: https://docs.bale.ai/
Bale mirrors the Telegram bot api, the commercial api is prefixed with `business`.
"""

# Python imports
import logging
import re
from typing import Any, Dict, Optional

import requests

# Django imports
from django.conf import settings
from django.core.cache import cache

# Module imports
from plane.db.models.notification import NOTIFICATION_CHANNEL_BALE
from plane.license.utils.instance_value import get_bale_bot_configuration, get_bale_configuration
from .base import (
    DEFAULT_HTTP_TIMEOUT,
    ChannelMessage,
    ChannelResult,
    NotificationChannelProvider,
    NotificationChannelValidationError,
)


logger = logging.getLogger("plane.bgtasks.notification.channel")

BALE_API_BASE_URL = "https://tapi.bale.ai"
BALE_BUSINESS_API_BASE_URL = "https://business.bale.ai"
# The text argument of sendMessage accepts 1 to 4096 characters
BALE_MAX_MESSAGE_LENGTH = 4096
CHAT_ID_PATTERN = re.compile(r"^-?\d+$")
# public url of the webhook receiver, the secret in the path is what authenticates the caller
WEBHOOK_URL_PATH = "/api/integrations/bale/webhook/{secret}/"
# the bot identity is cached so the pairing endpoints do not have to call the api on every read
BOT_IDENTITY_CACHE_KEY = "notification_channel:bale:bot_identity"
BOT_IDENTITY_CACHE_TIMEOUT = 60 * 60 * 12


class BaleProvider(NotificationChannelProvider):
    """Send messages through a Bale bot"""

    channel = NOTIFICATION_CHANNEL_BALE
    max_message_length = BALE_MAX_MESSAGE_LENGTH

    def get_api_base_url(self) -> str:
        """Return the api base url for the configured token"""
        token = get_bale_token()
        return BALE_BUSINESS_API_BASE_URL if token and token.startswith("business") else BALE_API_BASE_URL

    def is_configured(self) -> bool:
        """Return True when a bot token is set on the instance"""
        return bool(get_bale_token())

    def get_recipient_address(self, user: Any) -> Optional[str]:
        """Return the bale chat id or @username of the user"""
        return normalize_chat_id(getattr(user, "bale_chat_id", None))

    def check_config(self) -> None:
        """Validate the instance credentials

        :raises NotificationChannelValidationError: when the token is missing
        """
        if not get_bale_token():
            raise NotificationChannelValidationError("BALE_BOT_TOKEN is not configured on this instance")

    def get_bot_info(self) -> Dict[str, Any]:
        """Validate the token and return the bot identity

        :raises NotificationChannelValidationError: when the token is rejected
        """
        token = get_bale_token()
        if not token:
            raise NotificationChannelValidationError("BALE_BOT_TOKEN is not configured on this instance")
        # The token lives in the url, it is never logged
        payload = request(f"{self.get_api_base_url()}/bot{token}/getMe")
        return payload.get("result") or {}

    def send(self, address: str, message: ChannelMessage) -> ChannelResult:
        """Deliver a message, returning the outcome instead of raising"""
        token = get_bale_token()
        if not token:
            return ChannelResult(
                ok=False,
                error_code="not_configured",
                error_message="Bale is not configured on this instance",
            )

        chat_id = normalize_chat_id(address)
        if not chat_id:
            return ChannelResult(ok=False, error_code="invalid_chat_id", error_message="Invalid Bale chat id")

        try:
            # The token lives in the url, it is never logged
            payload = request(f"{self.get_api_base_url()}/bot{token}/sendMessage", data=build_payload(chat_id, message))
        except NotificationChannelValidationError as e:
            return ChannelResult(ok=False, error_code="api_error", error_message=str(e)[:255])

        result = payload.get("result") or {}
        return ChannelResult(
            ok=True,
            provider_message_id=str(result.get("message_id")) if result.get("message_id") else None,
        )


def get_bale_token() -> Optional[str]:
    """Return the bale bot token of the instance"""
    (token,) = get_bale_configuration()
    return (token or "").strip() or None


def get_bale_bot_username() -> Optional[str]:
    """Return the public username of the bot as it is shown to the end users"""
    _, username, _base_url, _secret = get_bale_bot_configuration()
    if not username:
        return None
    return username if username.startswith("@") else f"@{username}"


def build_webhook_url() -> Optional[str]:
    """Return the url the bale bot has to call, None when it cannot be built"""
    _token, _username, base_url, secret = get_bale_bot_configuration()
    base_url = base_url or (settings.WEB_URL or "").strip()
    if not base_url or not secret:
        return None
    return f"{base_url.rstrip('/')}{WEBHOOK_URL_PATH.format(secret=secret)}"


def get_me() -> Dict[str, Any]:
    """Return the identity of the configured bot

    :raises NotificationChannelValidationError: when the token is missing or rejected
    """
    token = get_bale_token()
    if not token:
        raise NotificationChannelValidationError("BALE_BOT_TOKEN is not configured on this instance")
    # The token lives in the url, it is never logged
    payload = request(f"{BALE_API_BASE_URL}/bot{token}/getMe")
    identity = payload.get("result") or {}
    # Cache the identity so the user facing endpoints can show the bot without an api round trip
    cache.set(
        BOT_IDENTITY_CACHE_KEY,
        {
            "id": str(identity.get("id")) if identity.get("id") else None,
            "first_name": identity.get("first_name"),
        },
        BOT_IDENTITY_CACHE_TIMEOUT,
    )
    return identity


def get_cached_bot_identity() -> Dict[str, Any]:
    """Return the last known bot identity, empty when the bot was never resolved"""
    return cache.get(BOT_IDENTITY_CACHE_KEY) or {}


def get_bot_id() -> Optional[str]:
    """Return the numeric bot id when it is known"""
    return get_cached_bot_identity().get("id")


def set_webhook(url: str) -> Dict[str, Any]:
    """Point the bot at the given webhook url

    :raises NotificationChannelValidationError: when the token is missing or rejected
    """
    token = get_bale_token()
    if not token:
        raise NotificationChannelValidationError("BALE_BOT_TOKEN is not configured on this instance")
    # The token lives in the url, it is never logged
    payload = request(f"{BALE_API_BASE_URL}/bot{token}/setWebhook", data={"url": url})
    return payload.get("result") or {}


def get_webhook_info() -> Dict[str, Any]:
    """Return the webhook the bot is currently calling

    :raises NotificationChannelValidationError: when the token is missing or rejected
    """
    token = get_bale_token()
    if not token:
        raise NotificationChannelValidationError("BALE_BOT_TOKEN is not configured on this instance")
    # The token lives in the url, it is never logged
    payload = request(f"{BALE_API_BASE_URL}/bot{token}/getWebhookInfo")
    return payload.get("result") or {}


def delete_webhook() -> Dict[str, Any]:
    """Remove the webhook registration of the bot

    :raises NotificationChannelValidationError: when the token is missing or rejected
    """
    token = get_bale_token()
    if not token:
        raise NotificationChannelValidationError("BALE_BOT_TOKEN is not configured on this instance")
    # An empty url is how bale removes an existing registration
    return request(f"{BALE_API_BASE_URL}/bot{token}/deleteWebhook", data={"url": ""})


def send_text(chat_id: str, text: str) -> ChannelResult:
    """Send a plain text message to a chat, used by the webhook replies"""
    return BaleProvider().send(chat_id, ChannelMessage(text=text))


def normalize_chat_id(value: Optional[str]) -> Optional[str]:
    """Validate a bale chat id or @username"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if CHAT_ID_PATTERN.match(text):
        return text
    # Username references are passed to the api as is, ie @username
    if text.startswith("@") and len(text) > 1:
        return text
    return None


def build_payload(chat_id: str, message: ChannelMessage) -> Dict[str, Any]:
    """Build the sendMessage payload, messages are formatted with markdown"""
    payload: Dict[str, Any] = {"chat_id": chat_id, "text": message.text, "parse_mode": "Markdown"}
    if message.url:
        payload["reply_markup"] = build_inline_keyboard(message.url)
    return payload


def build_inline_keyboard(url: str) -> Dict[str, Any]:
    """Build a reply markup with a single link button to the entity"""
    return {"inline_keyboard": [[{"text": "Open in Plane", "url": url}]]}


def request(url: str, data: Optional[Dict[str, Any]] = None, method: str = "POST") -> Dict[str, Any]:
    """Call the bale api and unwrap the ok / error envelope

    :raises NotificationChannelValidationError: when the api rejects the call
    """
    try:
        response = requests.request(method, url, json=data, timeout=DEFAULT_HTTP_TIMEOUT)
    except requests.RequestException as e:
        logger.error("Bale request failed: %s", type(e).__name__)
        raise NotificationChannelValidationError("Bale is unreachable")

    try:
        payload = response.json()
    except ValueError:
        raise NotificationChannelValidationError(f"Bale api returned a non json response ({response.status_code})")

    if not isinstance(payload, dict) or not payload.get("ok"):
        description = (payload or {}).get("description") or f"http {response.status_code}"
        raise NotificationChannelValidationError(f"Bale api error: {str(description)[:200]}")
    return payload