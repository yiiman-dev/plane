# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Webhook receiver for the bale bot

The receiver is unauthenticated on purpose, the secret in the url path is what proves
that the request really comes from bale.
"""

# Python imports
import hashlib
import hmac
import logging
from typing import Optional

# Django imports
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

# Module imports
from plane.db.models import (
    NOTIFICATION_CHANNEL_BALE,
    NotificationChannelPairingCode,
    User,
    UserNotificationChannel,
)
from plane.license.utils.instance_value import get_bale_bot_configuration
from plane.utils.notifications.bale import normalize_chat_id, send_text

logger = logging.getLogger("plane")

# how many failed codes a single chat may submit inside the rate limit window
PAIRING_ATTEMPT_LIMIT = 5
PAIRING_ATTEMPT_WINDOW_SECONDS = 60 * 10
PAIRING_ATTEMPT_CACHE_PREFIX = "notification_channel:bale:pairing_attempts"

# pairing codes only use unambiguous characters so they can be read out loud
PAIRING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 8

WELCOME_TEXT = (
    "Hi! I am the Plane bot.\n\n"
    "Open your Plane profile, go to Notifications, enable the Bale channel and press "
    "\"Connect to Bale\" to get a one time code. Send me that code here and your Bale "
    "account is linked to your Plane account."
)

SUCCESS_TEXT = (
    "Your Bale account is now linked to your Plane account.\n"
    "You can pick which notifications you want to receive in Plane, under "
    "Profile > Notifications."
)

INVALID_CODE_TEXT = "That code is not valid. Get a new one from Profile > Notifications in Plane."

EXPIRED_CODE_TEXT = "That code has already been used or has expired. Get a new one from Profile > Notifications."

RATE_LIMITED_TEXT = "Too many attempts. Please request a new pairing code from Plane and try again."


def normalize_pairing_code(value) -> str:
    """Return the canonical form of a typed pairing code, ie A1B2C3D4"""
    return "".join(str(value or "").split()).replace("-", "").upper()


def hash_pairing_code(code: str) -> str:
    """Return the sha256 hexdigest that is persisted for a pairing code"""
    return hashlib.sha256(normalize_pairing_code(code).encode("utf-8")).hexdigest()


def get_attempts(chat_id: str) -> int:
    """Return the number of failed pairing attempts of the chat inside the window"""
    return cache.get(f"{PAIRING_ATTEMPT_CACHE_PREFIX}:{chat_id}", 0) or 0


def register_failed_attempt(chat_id: str) -> int:
    """Record a failed pairing attempt and return the new count"""
    key = f"{PAIRING_ATTEMPT_CACHE_PREFIX}:{chat_id}"
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, PAIRING_ATTEMPT_WINDOW_SECONDS)
        count = 1
    return count


def clear_attempts(chat_id: str) -> None:
    """Forget the failed attempts of the chat after a successful pairing"""
    cache.delete(f"{PAIRING_ATTEMPT_CACHE_PREFIX}:{chat_id}")


def reply(chat_id, text: str) -> None:
    """Send a reply back to the chat, delivery failures never break the webhook contract"""
    normalized = normalize_chat_id(chat_id)
    if not normalized:
        logger.warning("bale webhook: dropping reply, the payload carries no usable chat id")
        return
    try:
        result = send_text(normalized, text)
        if not result.ok:
            # The api will retry the update when we answer with an error, an undeliverable
            # reply would be retried forever so the update is still acknowledged
            logger.warning("bale webhook: could not deliver the reply, error %s", result.error_code)
    except Exception:
        logger.exception("bale webhook: unexpected failure while replying")


class BaleWebhookEndpoint(APIView):
    """Receive the updates bale sends to the registered webhook url"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get_secret(self, request) -> Optional[str]:
        """Return the configured webhook secret when the url carries the right one"""
        _token, _username, _base_url, secret = get_bale_bot_configuration()
        if not secret:
            return None
        # constant time comparison so the secret cannot be guessed by timing
        if not hmac.compare_digest(str(secret), str(request.parser_context["kwargs"].get("webhook_secret") or "")):
            return None
        return secret

    def handle_pairing_code(self, chat_id: str, text: str) -> bool:
        """Consume a pairing code, return True when the text was a code and got handled"""
        normalized = normalize_pairing_code(text)
        if len(normalized) != PAIRING_CODE_LENGTH:
            return False
        # only tokens that could come from our own alphabet are treated as a pairing attempt
        if any(character not in PAIRING_CODE_ALPHABET for character in normalized):
            return False

        if register_failed_attempt(chat_id) > PAIRING_ATTEMPT_LIMIT:
            reply(chat_id, RATE_LIMITED_TEXT)
            return True

        digest = hash_pairing_code(normalized)
        now = timezone.now()
        pairing_code = (
            NotificationChannelPairingCode.objects.filter(channel=NOTIFICATION_CHANNEL_BALE, code=digest)
            .filter(Q(consumed_at__isnull=False) | Q(expires_at__lte=now))
            .order_by("-created_at")
            .first()
        )
        if pairing_code is not None:
            # it was already used or it expired, either way it cannot be replayed
            reply(chat_id, EXPIRED_CODE_TEXT)
            return True

        pairing_code = NotificationChannelPairingCode.objects.filter(
            channel=NOTIFICATION_CHANNEL_BALE,
            code=digest,
            consumed_at__isnull=True,
            expires_at__gt=now,
        ).first()
        if pairing_code is None:
            reply(chat_id, INVALID_CODE_TEXT)
            return True

        user = pairing_code.user
        consumed_at = timezone.now()
        with transaction.atomic():
            # Claim the code with a conditional update so two deliveries of the same
            # update arriving at once cannot both link an account.
            claimed = (
                NotificationChannelPairingCode.objects.filter(pk=pairing_code.pk, consumed_at__isnull=True)
                .update(consumed_at=consumed_at, consumed_chat_id=chat_id)
            )
            if claimed:
                User.objects.filter(pk=user.pk).update(bale_chat_id=chat_id)
                # the code is single use, the remaining ones of this user stop working here
                NotificationChannelPairingCode.objects.filter(
                    user=user, channel=NOTIFICATION_CHANNEL_BALE, consumed_at__isnull=True
                ).update(expires_at=consumed_at)

                UserNotificationChannel.objects.update_or_create(
                    user=user,
                    channel=NOTIFICATION_CHANNEL_BALE,
                    defaults={
                        "is_verified": True,
                        "verified_at": consumed_at,
                        "last_status": "paired",
                        "last_error": "",
                    },
                )
        if not claimed:
            # a concurrent delivery consumed it first, so this one is a replay
            reply(chat_id, EXPIRED_CODE_TEXT)
            return True

        user.bale_chat_id = chat_id
        clear_attempts(chat_id)
        reply(chat_id, SUCCESS_TEXT)
        return True

    def handle_linked_message(self, user, text: str, chat_id: str) -> None:
        """Forward a message of an already linked user to the command handler"""
        # Imported lazily so a missing optional module cannot break the whole webhook
        try:
            from plane.utils.notifications.bale_commands import handle_bale_message

            handle_bale_message(user=user, text=text, chat_id=chat_id)
        except ImportError:
            logger.warning("bale webhook: the bale command handler is not available yet")
        except Exception:
            logger.exception("bale webhook: the bale command handler failed")

    def get_linked_user(self, chat_id: str):
        """Return the user the chat is linked to, None when it is not linked yet"""
        user = User.objects.filter(bale_chat_id=chat_id).first()
        if user is None:
            return None
        if not UserNotificationChannel.objects.filter(
            user=user, channel=NOTIFICATION_CHANNEL_BALE, is_verified=True
        ).exists():
            return None
        return user

    def post(self, request, *args, **kwargs):
        if self.get_secret(request) is None:
            # An unconfigured or wrong secret is indistinguishable from an unknown url
            raise Http404()

        data = request.data
        if not isinstance(data, dict) or "update_id" not in data:
            return Response({"error": "Malformed bale update"}, status=status.HTTP_400_BAD_REQUEST)

        # Callback queries need an interactive backend, they are acknowledged but not handled yet
        if "callback_query" in data:
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        message = data.get("message")
        if not isinstance(message, dict):
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        chat_id = normalize_chat_id((message.get("chat") or {}).get("id"))
        if not chat_id:
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        text = str(message.get("text") or "").strip()
        if not text:
            return Response({"status": "ignored"}, status=status.HTTP_200_OK)

        if text.lower().startswith("/start"):
            reply(chat_id, WELCOME_TEXT)
            return Response({"status": "welcome"}, status=status.HTTP_200_OK)

        # A pairing code can never be replayed, even by an already linked user
        if self.handle_pairing_code(chat_id, text):
            return Response({"status": "pairing"}, status=status.HTTP_200_OK)

        user = self.get_linked_user(chat_id)
        if user is not None:
            self.handle_linked_message(user=user, text=text, chat_id=chat_id)

        # Always answer with 200 so bale does not replay an update we already processed
        return Response({"status": "processed"}, status=status.HTTP_200_OK)


__all__ = ["BaleWebhookEndpoint"]