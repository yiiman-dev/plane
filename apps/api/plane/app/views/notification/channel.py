# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""User facing endpoints for the external notification channels."""

# Python imports
import hashlib
import secrets
from datetime import timedelta

# Django imports
from django.utils import timezone

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.serializers import NotificationChannelPreferenceSerializer
from plane.db.models import (
    NOTIFICATION_CHANNEL_BALE,
    NOTIFICATION_CHANNEL_SMS,
    NOTIFICATION_EVENTS,
    NotificationChannelPreference,
    NotificationChannelPairingCode,
    User,
    UserNotificationChannel,
)
from plane.utils.notifications import PROVIDERS, ChannelMessage, get_provider
from plane.utils.notifications.bale import get_bot_id, get_bale_bot_username, normalize_chat_id
from plane.utils.notifications.kavenegar import normalize_receptor
from ..base import BaseAPIView


# the user profile field that holds the delivery address of every channel
CHANNEL_ADDRESS_FIELDS = {
    NOTIFICATION_CHANNEL_SMS: "mobile_number",
    NOTIFICATION_CHANNEL_BALE: "bale_chat_id",
}

TEST_MESSAGE_TEMPLATE = "{app_name}: this is a test notification, your {channel_label} channel is connected."
CHANNEL_LABELS = {
    NOTIFICATION_CHANNEL_SMS: "SMS",
    NOTIFICATION_CHANNEL_BALE: "Bale",
}

# pairing of a chat account with a plane account
PAIRING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIRING_CODE_LENGTH = 8
PAIRING_CODE_EXPIRY = timedelta(minutes=10)
PAIRING_MAX_ACTIVE_CODES = 5
PAIRING_STATUS_NOT_STARTED = "not_started"
PAIRING_STATUS_PENDING = "pending"
PAIRING_STATUS_CONNECTED = "connected"


def generate_pairing_code() -> str:
    """Return a fresh readable pairing code without any ambiguous character"""
    return "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))


def normalize_pairing_code(value: str) -> str:
    """Return the canonical form of a user typed pairing code, ie A1B2C3D4"""
    return "".join(str(value or "").split()).upper()


def format_pairing_code(code: str) -> str:
    """Return the pairing code as it is displayed to the user, ie A1B2-C3D4"""
    half = len(code) // 2
    return f"{code[:half]}-{code[half:]}"


def hash_pairing_code(code: str) -> str:
    """Return the sha256 hexdigest that is persisted for a pairing code"""
    return hashlib.sha256(normalize_pairing_code(code).encode("utf-8")).hexdigest()


class NotificationChannelBaseEndpoint(BaseAPIView):
    """Shared helpers of the notification channel endpoints"""

    def get_provider(self, request):
        """Return the provider of the requested channel, or None when unsupported"""
        channel = request.data.get("channel") if request.method != "GET" else request.GET.get("channel")
        if channel not in PROVIDERS:
            return None
        return get_provider(channel)

    def serialize_channels(self, user):
        """Build the aggregated channel state of the user"""
        configurations = {config.channel: config for config in UserNotificationChannel.objects.filter(user=user)}
        preferences = {
            (preference.channel, preference.event): preference.is_enabled
            for preference in NotificationChannelPreference.objects.filter(user=user)
        }

        channels = []
        for provider in PROVIDERS.values():
            configuration = configurations.get(provider.channel)
            # the bale chat is never typed by hand, it is established with the pairing code
            is_linked = (
                provider.channel == NOTIFICATION_CHANNEL_BALE and bool(getattr(user, "bale_chat_id", None))
            )
            channels.append(
                {
                    "channel": provider.channel,
                    "provider_configured": provider.is_configured(),
                    "is_enabled": bool(configuration.is_enabled) if configuration else False,
                    "is_verified": bool(configuration.is_verified) if configuration else False,
                    "last_status": configuration.last_status if configuration else None,
                    "last_delivered_at": configuration.last_delivered_at if configuration else None,
                    "last_error": configuration.last_error if configuration else "",
                    "address": provider.get_recipient_address(user) or "",
                    "address_field": CHANNEL_ADDRESS_FIELDS[provider.channel],
                    "is_linked": is_linked,
                    "linked_at": configuration.verified_at if (configuration and is_linked) else None,
                    "bot_username": get_bale_bot_username() if is_linked else None,
                    "preferences": {
                        event: bool(preferences.get((provider.channel, event), False))
                        for event in NOTIFICATION_EVENTS
                    },
                }
            )
        return {"channels": channels, "events": NOTIFICATION_EVENTS}


class NotificationChannelEndpoint(NotificationChannelBaseEndpoint):
    """Read and update the notification channels of the current user"""

    def get(self, request):
        return Response(self.serialize_channels(request.user), status=status.HTTP_200_OK)

    def patch(self, request):
        provider = self.get_provider(request)
        if provider is None:
            return Response(
                {"error": "Unsupported notification channel"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        address_field = CHANNEL_ADDRESS_FIELDS[provider.channel]
        # the bale chat id is written by the webhook once the pairing code is verified
        if provider.channel == NOTIFICATION_CHANNEL_BALE and address_field in request.data:
            return Response(
                {
                    "error": "Your Bale chat is linked with a one time pairing code, "
                    "the chat id cannot be set manually"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if address_field in request.data:
            error = self.update_address(request.user, address_field, request.data.get(address_field))
            if error is not None:
                return Response({"error": error}, status=status.HTTP_400_BAD_REQUEST)

        configuration, _created = UserNotificationChannel.objects.get_or_create(
            user=request.user, channel=provider.channel
        )
        is_enabled = request.data.get("is_enabled")
        if is_enabled is not None:
            is_enabled = bool(is_enabled)
            if is_enabled and not provider.get_recipient_address(request.user):
                return Response(
                    {"error": f"Add your {CHANNEL_LABELS[provider.channel]} address before enabling the channel"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            configuration.is_enabled = is_enabled
            configuration.save(update_fields=["is_enabled", "updated_at"])

        return Response(self.serialize_channels(request.user), status=status.HTTP_200_OK)

    def update_address(self, user, address_field, value):
        """Persist the delivery address of the user, returns an error message when invalid"""
        value = (value or "").strip() if isinstance(value, str) else ""
        if not value:
            User.objects.filter(pk=user.pk).update(**{address_field: None})
            user.refresh_from_db(fields=[address_field])
            return None

        if address_field == "mobile_number":
            normalized = normalize_receptor(value)
            if not normalized:
                return "Enter a valid phone number, ie 09123456789 or +989123456789"
        else:
            normalized = normalize_chat_id(value)
            if not normalized:
                return "Enter a valid Bale chat id or a @username"

        User.objects.filter(pk=user.pk).update(**{address_field: normalized})
        user.refresh_from_db(fields=[address_field])
        return None


class NotificationChannelPreferenceEndpoint(NotificationChannelBaseEndpoint):
    """Read and update the event level preferences of the current user"""

    def get(self, request):
        preferences = NotificationChannelPreference.objects.filter(user=request.user)
        return Response(
            {
                "preferences": NotificationChannelPreferenceSerializer(preferences, many=True).data,
                "events": NOTIFICATION_EVENTS,
            },
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        provider = self.get_provider(request)
        event = request.data.get("event")
        if provider is None or event not in NOTIFICATION_EVENTS:
            return Response(
                {"error": "Unsupported notification channel or event"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_enabled = bool(request.data.get("is_enabled", False))
        NotificationChannelPreference.objects.update_or_create(
            user=request.user,
            channel=provider.channel,
            event=event,
            defaults={"is_enabled": is_enabled},
        )
        return Response(self.get(request).data, status=status.HTTP_200_OK)


class NotificationChannelTestEndpoint(NotificationChannelBaseEndpoint):
    """Verify the provider credentials and send a test message to the current user"""

    def post(self, request):
        provider = self.get_provider(request)
        if provider is None:
            return Response({"error": "Unsupported notification channel"}, status=status.HTTP_400_BAD_REQUEST)

        result = provider.send_to_user(
            request.user,
            ChannelMessage(
                text=TEST_MESSAGE_TEMPLATE.format(
                    app_name="Plane", channel_label=CHANNEL_LABELS[provider.channel]
                )
            ),
        )
        if not result.ok:
            # The provider error is safe to return, it never carries the credentials
            return Response(
                {"error": result.error_message, "code": result.error_code},
                status=status.HTTP_400_BAD_REQUEST,
            )

        UserNotificationChannel.objects.update_or_create(
            user=request.user,
            channel=provider.channel,
            defaults={
                "is_verified": True,
                "verified_at": timezone.now(),
                "last_status": "sent",
                "last_delivered_at": timezone.now(),
                "last_error": "",
            },
        )
        return Response(
            {"message": "Test notification sent", "channel": provider.channel},
            status=status.HTTP_200_OK,
        )


class NotificationChannelPairingEndpoint(NotificationChannelBaseEndpoint):
    """Link a chat account with the account of the current user using a one time code

    The user never types a chat id, they hand the code to the bot and the webhook writes
    the resolved chat id onto their profile.
    """

    channel = NOTIFICATION_CHANNEL_BALE

    def active_codes(self, user):
        """Return the pairing codes of the user that are still usable"""
        return NotificationChannelPairingCode.objects.filter(
            user=user,
            channel=self.channel,
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
        )

    def invalidate_active_codes(self, user):
        """Expire every usable pairing code of the user, they are single use by design"""
        return self.active_codes(user).update(expires_at=timezone.now())

    def is_linked(self, user):
        """Return True when a verified chat is already attached to the account"""
        if not getattr(user, "bale_chat_id", None):
            return False
        return UserNotificationChannel.objects.filter(user=user, channel=self.channel, is_verified=True).exists()

    def bot_identity(self):
        """Return the public identity of the instance bot"""
        return {"bot_username": get_bale_bot_username(), "bot_id": get_bot_id()}

    def build_state(self, user):
        """Return the pairing state of the user, the raw code is only known at creation time"""
        if self.is_linked(user):
            configuration = UserNotificationChannel.objects.filter(user=user, channel=self.channel).first()
            return {
                "status": PAIRING_STATUS_CONNECTED,
                "code": None,
                "expires_at": None,
                "expires_in_seconds": 0,
                **self.bot_identity(),
                "linked_at": configuration.verified_at if configuration else None,
            }

        active = self.active_codes(user).first()
        if active is None:
            return {
                "status": PAIRING_STATUS_NOT_STARTED,
                "code": None,
                "expires_at": None,
                "expires_in_seconds": 0,
                **self.bot_identity(),
                "linked_at": None,
            }

        return {
            "status": PAIRING_STATUS_PENDING,
            # the raw code is never persisted so it cannot be displayed again
            "code": None,
            "expires_at": active.expires_at,
            "expires_in_seconds": max(int((active.expires_at - timezone.now()).total_seconds()), 0),
            **self.bot_identity(),
            "linked_at": None,
        }

    def post(self, request):
        provider = get_provider(self.channel)
        if not provider.is_configured():
            return Response(
                {"error": "The Bale bot is not configured on this instance yet, ask an administrator to set it up"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if self.active_codes(request.user).count() >= PAIRING_MAX_ACTIVE_CODES:
            return Response(
                {
                    "error": "You have too many active pairing codes, use the code you already "
                    "received or wait until they expire"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # a new code always supersedes the previous ones, only one of them stays usable
        self.invalidate_active_codes(request.user)

        now = timezone.now()
        expires_at = now + PAIRING_CODE_EXPIRY
        # the raw code lives only in this response, the row keeps its sha256 digest
        raw_code = generate_pairing_code()
        NotificationChannelPairingCode.objects.create(
            user=request.user,
            channel=self.channel,
            code=hash_pairing_code(raw_code),
            expires_at=expires_at,
        )

        return Response(
            {
                "status": PAIRING_STATUS_PENDING,
                "code": format_pairing_code(raw_code),
                "expires_at": expires_at,
                "expires_in_seconds": int(PAIRING_CODE_EXPIRY.total_seconds()),
                **self.bot_identity(),
            },
            status=status.HTTP_200_OK,
        )

    def get(self, request):
        return Response(self.build_state(request.user), status=status.HTTP_200_OK)

    def delete(self, request):
        User.objects.filter(pk=request.user.pk).update(bale_chat_id=None)
        request.user.refresh_from_db(fields=["bale_chat_id"])
        UserNotificationChannel.objects.filter(user=request.user, channel=self.channel).update(
            is_verified=False,
            is_enabled=False,
            verified_at=None,
        )
        self.invalidate_active_codes(request.user)
        return Response(self.build_state(request.user), status=status.HTTP_200_OK)