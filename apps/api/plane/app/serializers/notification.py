# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Module imports
from .base import BaseSerializer
from .user import UserLiteSerializer
from plane.db.models import (
    Notification,
    NotificationChannelLog,
    NotificationChannelPreference,
    UserNotificationChannel,
    UserNotificationPreference,
)

# Third Party imports
from rest_framework import serializers


class NotificationSerializer(BaseSerializer):
    triggered_by_details = UserLiteSerializer(read_only=True, source="triggered_by")
    is_inbox_issue = serializers.BooleanField(read_only=True)
    is_intake_issue = serializers.BooleanField(read_only=True)
    is_mentioned_notification = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = "__all__"


class UserNotificationPreferenceSerializer(BaseSerializer):
    class Meta:
        model = UserNotificationPreference
        fields = "__all__"


class UserNotificationChannelSerializer(BaseSerializer):
    """Serialized notification channel configuration"""

    channel = serializers.CharField(read_only=True)

    class Meta:
        model = UserNotificationChannel
        fields = [
            "id",
            "channel",
            "is_enabled",
            "is_verified",
            "verified_at",
            "last_status",
            "last_delivered_at",
            "last_error",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class NotificationChannelPreferenceSerializer(BaseSerializer):
    """Serialized event level preference of a notification channel"""

    channel = serializers.ChoiceField(choices=["SMS", "BALE"])
    event = serializers.ChoiceField(
        choices=["property_change", "state_change", "comment", "mention", "issue_completed"]
    )

    class Meta:
        model = NotificationChannelPreference
        fields = ["id", "channel", "event", "is_enabled"]
        read_only_fields = ["id"]


class NotificationChannelLogSerializer(BaseSerializer):
    """Serialized delivery log of a notification channel message"""

    class Meta:
        model = NotificationChannelLog
        fields = [
            "id",
            "receiver",
            "triggered_by",
            "channel",
            "event",
            "entity_identifier",
            "entity_name",
            "status",
            "error_message",
            "processed_at",
            "sent_at",
            "created_at",
        ]
        read_only_fields = fields
