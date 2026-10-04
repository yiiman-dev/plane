# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""User facing endpoints for the external notification channels."""

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
    User,
    UserNotificationChannel,
)
from plane.utils.notifications import PROVIDERS, ChannelMessage, get_provider
from plane.utils.notifications.bale import normalize_chat_id
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