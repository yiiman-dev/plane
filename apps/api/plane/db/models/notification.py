# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.conf import settings
from django.db import models

# Module imports
from .base import BaseModel


class Notification(BaseModel):
    workspace = models.ForeignKey("db.Workspace", related_name="notifications", on_delete=models.CASCADE)
    project = models.ForeignKey("db.Project", related_name="notifications", on_delete=models.CASCADE, null=True)
    data = models.JSONField(null=True)
    entity_identifier = models.UUIDField(null=True)
    entity_name = models.CharField(max_length=255)
    title = models.TextField()
    message = models.JSONField(null=True)
    message_html = models.TextField(blank=True, default="<p></p>")
    message_stripped = models.TextField(blank=True, null=True)
    sender = models.CharField(max_length=255)
    triggered_by = models.ForeignKey(
        "db.User",
        related_name="triggered_notifications",
        on_delete=models.SET_NULL,
        null=True,
    )
    receiver = models.ForeignKey("db.User", related_name="received_notifications", on_delete=models.CASCADE)
    read_at = models.DateTimeField(null=True)
    snoozed_till = models.DateTimeField(null=True)
    archived_at = models.DateTimeField(null=True)

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        db_table = "notifications"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["entity_identifier"], name="notif_entity_identifier_idx"),
            models.Index(fields=["entity_name"], name="notif_entity_name_idx"),
            models.Index(fields=["read_at"], name="notif_read_at_idx"),
            models.Index(fields=["receiver", "read_at"], name="notif_entity_idx"),
            models.Index(
                fields=["receiver", "workspace", "read_at", "created_at"],
                name="notif_receiver_status_idx",
            ),
            models.Index(
                fields=["receiver", "workspace", "entity_name", "read_at"],
                name="notif_receiver_entity_idx",
            ),
            models.Index(
                fields=["receiver", "workspace", "snoozed_till", "archived_at"],
                name="notif_receiver_state_idx",
            ),
            models.Index(
                fields=["receiver", "workspace", "sender"],
                name="notif_receiver_sender_idx",
            ),
            models.Index(
                fields=["workspace", "entity_identifier", "entity_name"],
                name="notif_entity_lookup_idx",
            ),
        ]

    def __str__(self):
        """Return name of the notifications"""
        return f"{self.receiver.email} <{self.workspace.name}>"


def get_default_preference():
    return {
        "property_change": {"email": True},
        "state": {"email": True},
        "comment": {"email": True},
        "mentions": {"email": True},
    }


class UserNotificationPreference(BaseModel):
    # user it is related to
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_preferences",
    )
    # workspace if it is applicable
    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="workspace_notification_preferences",
        null=True,
    )
    # project
    project = models.ForeignKey(
        "db.Project",
        on_delete=models.CASCADE,
        related_name="project_notification_preferences",
        null=True,
    )

    # preference fields
    property_change = models.BooleanField(default=True)
    state_change = models.BooleanField(default=True)
    comment = models.BooleanField(default=True)
    mention = models.BooleanField(default=True)
    issue_completed = models.BooleanField(default=True)

    class Meta:
        verbose_name = "UserNotificationPreference"
        verbose_name_plural = "UserNotificationPreferences"
        db_table = "user_notification_preferences"
        ordering = ("-created_at",)

    def __str__(self):
        """Return the user"""
        return f"<{self.user}>"


class EmailNotificationLog(BaseModel):
    # receiver
    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_notifications",
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="triggered_emails",
    )
    # entity - can be issues, pages, etc.
    entity_identifier = models.UUIDField(null=True)
    entity_name = models.CharField(max_length=255)
    # data
    data = models.JSONField(null=True)
    # sent at
    processed_at = models.DateTimeField(null=True)
    sent_at = models.DateTimeField(null=True)
    entity = models.CharField(max_length=200)
    old_value = models.CharField(max_length=300, blank=True, null=True)
    new_value = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        verbose_name = "Email Notification Log"
        verbose_name_plural = "Email Notification Logs"
        db_table = "email_notification_logs"
        ordering = ("-created_at",)


# --------------------------------------------------------------------------------------
# External notification channels (SMS, Bale bot, ...)
# --------------------------------------------------------------------------------------

NOTIFICATION_CHANNEL_SMS = "SMS"
NOTIFICATION_CHANNEL_BALE = "BALE"

NOTIFICATION_CHANNEL_CHOICES = (
    (NOTIFICATION_CHANNEL_SMS, "SMS"),
    (NOTIFICATION_CHANNEL_BALE, "Bale"),
)

NOTIFICATION_EVENT_PROPERTY_CHANGE = "property_change"
NOTIFICATION_EVENT_STATE_CHANGE = "state_change"
NOTIFICATION_EVENT_COMMENT = "comment"
NOTIFICATION_EVENT_MENTION = "mention"
NOTIFICATION_EVENT_ISSUE_COMPLETED = "issue_completed"

NOTIFICATION_EVENT_CHOICES = (
    (NOTIFICATION_EVENT_PROPERTY_CHANGE, "Property change"),
    (NOTIFICATION_EVENT_STATE_CHANGE, "State change"),
    (NOTIFICATION_EVENT_COMMENT, "Comment"),
    (NOTIFICATION_EVENT_MENTION, "Mention"),
    (NOTIFICATION_EVENT_ISSUE_COMPLETED, "Issue completed"),
)

NOTIFICATION_EVENTS = [event[0] for event in NOTIFICATION_EVENT_CHOICES]

NOTIFICATION_CHANNEL_STATUS_PENDING = "pending"
NOTIFICATION_CHANNEL_STATUS_SENT = "sent"
NOTIFICATION_CHANNEL_STATUS_FAILED = "failed"
NOTIFICATION_CHANNEL_STATUS_SKIPPED = "skipped"

NOTIFICATION_CHANNEL_STATUS_CHOICES = (
    (NOTIFICATION_CHANNEL_STATUS_PENDING, "Pending"),
    (NOTIFICATION_CHANNEL_STATUS_SENT, "Sent"),
    (NOTIFICATION_CHANNEL_STATUS_FAILED, "Failed"),
    (NOTIFICATION_CHANNEL_STATUS_SKIPPED, "Skipped"),
)


class UserNotificationChannel(BaseModel):
    """Per user, per channel configuration and delivery state"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_channels",
    )
    channel = models.CharField(max_length=20, choices=NOTIFICATION_CHANNEL_CHOICES)
    # master switch for the channel
    is_enabled = models.BooleanField(default=True)
    # set once a message has been delivered successfully on this channel
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    # last delivery state, used to surface delivery problems in the UI
    last_status = models.CharField(
        max_length=20,
        choices=NOTIFICATION_CHANNEL_STATUS_CHOICES,
        null=True,
        blank=True,
    )
    last_delivered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        verbose_name = "User Notification Channel"
        verbose_name_plural = "User Notification Channels"
        db_table = "user_notification_channels"
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=["user", "channel"], name="uniq_user_notification_channel")]

    def __str__(self):
        """Return the user and channel"""
        return f"<{self.user}>:{self.channel}"


class NotificationChannelPreference(BaseModel):
    """Event level opt in / opt out for an external notification channel"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notification_channel_preferences",
    )
    channel = models.CharField(max_length=20, choices=NOTIFICATION_CHANNEL_CHOICES)
    event = models.CharField(max_length=30, choices=NOTIFICATION_EVENT_CHOICES)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Notification Channel Preference"
        verbose_name_plural = "Notification Channel Preferences"
        db_table = "notification_channel_preferences"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=["user", "channel", "event"], name="uniq_notification_channel_preference")
        ]

    def __str__(self):
        """Return the user, channel and event"""
        return f"<{self.user}>:{self.channel}:{self.event}"


class NotificationChannelLog(BaseModel):
    """Delivery log for a single message queued on an external notification channel"""

    receiver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="channel_notifications",
    )
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="triggered_channel_notifications",
    )
    channel = models.CharField(max_length=20, choices=NOTIFICATION_CHANNEL_CHOICES)
    event = models.CharField(max_length=30, choices=NOTIFICATION_EVENT_CHOICES)
    # entity - can be issues, pages, etc.
    entity_identifier = models.UUIDField(null=True)
    entity_name = models.CharField(max_length=255)
    # data
    data = models.JSONField(null=True)
    status = models.CharField(
        max_length=20,
        choices=NOTIFICATION_CHANNEL_STATUS_CHOICES,
        default=NOTIFICATION_CHANNEL_STATUS_PENDING,
    )
    error_message = models.CharField(max_length=255, blank=True, default="")
    # processed at marks the log as picked up by the dispatcher
    processed_at = models.DateTimeField(null=True)
    # sent at marks a successful delivery
    sent_at = models.DateTimeField(null=True)

    class Meta:
        verbose_name = "Notification Channel Log"
        verbose_name_plural = "Notification Channel Logs"
        db_table = "notification_channel_logs"
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["channel", "processed_at", "status"], name="notif_channel_queue_idx"),
            models.Index(fields=["receiver", "channel", "created_at"], name="notif_channel_receiver_idx"),
        ]

    def __str__(self):
        """Return the receiver, channel and event"""
        return f"<{self.receiver}>:{self.channel}:{self.event}"
