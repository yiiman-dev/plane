# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Celery tasks delivering the notifications of the external channels (SMS, Bale)."""

# Python imports
import logging

# Django imports
from django.utils import timezone

# Third party imports
from celery import shared_task

# Module imports
from plane.db.models import (
    NOTIFICATION_CHANNEL_BALE,
    NOTIFICATION_CHANNEL_SMS,
    NOTIFICATION_EVENT_COMMENT,
    NOTIFICATION_EVENT_ISSUE_COMPLETED,
    NOTIFICATION_EVENT_MENTION,
    NOTIFICATION_EVENT_PROPERTY_CHANGE,
    NOTIFICATION_EVENT_STATE_CHANGE,
    NOTIFICATION_CHANNEL_STATUS_FAILED,
    NOTIFICATION_CHANNEL_STATUS_PENDING,
    NOTIFICATION_CHANNEL_STATUS_SENT,
    Notification,
    NotificationChannelLog,
    NotificationChannelPreference,
    UserNotificationChannel,
)
from plane.utils.notifications import PROVIDERS, get_provider
from plane.utils.notifications.messages import build_channel_message


logger = logging.getLogger("plane.bgtasks.notification.channel")

# in app notification events mapped to the channel events exposed to the users
EVENT_MAP = {
    "property": NOTIFICATION_EVENT_PROPERTY_CHANGE,
    "state": NOTIFICATION_EVENT_STATE_CHANGE,
    "comment": NOTIFICATION_EVENT_COMMENT,
    "mention": NOTIFICATION_EVENT_MENTION,
    "issue": NOTIFICATION_EVENT_ISSUE_COMPLETED,
}


def resolve_channel_event(notification: Notification):
    """Map an in app notification to the channel event key

    :param notification: in app notification record
    :returns: channel event key or None when the event has no channel counterpart
    """
    data = notification.data or {}
    issue_data = data.get("issue") or {}
    activity = data.get("issue_activity") or {}

    # an issue completion is a state change with the completed verb
    verb = str(activity.get("verb") or "").lower()
    if verb == "completed" or str(issue_data.get("event") or "") == "completed":
        return NOTIFICATION_EVENT_ISSUE_COMPLETED

    return EVENT_MAP.get(str(issue_data.get("event") or verb))


def queue_notification_channel_logs(notifications):
    """Queue the in app notifications on the external channels the receivers opted into

    :param notifications: list of in app Notification records
    :returns: number of queued channel logs
    """
    if not notifications:
        return 0

    receiver_ids = {str(notification.receiver_id) for notification in notifications if notification.receiver_id}
    if not receiver_ids:
        return 0

    enabled_channels = set()
    channels_by_user = {}
    for configuration in UserNotificationChannel.objects.filter(
        user_id__in=receiver_ids, is_enabled=True, channel__in=list(PROVIDERS.keys())
    ).select_related("user"):
        # a channel without a delivery address can never be used
        if get_provider(configuration.channel).get_recipient_address(configuration.user):
            enabled_channels.add(configuration.channel)
            channels_by_user.setdefault(str(configuration.user_id), set()).add(configuration.channel)

    if not enabled_channels:
        return 0

    enabled_events = {
        (str(preference.user_id), preference.channel, preference.event)
        for preference in NotificationChannelPreference.objects.filter(
            user_id__in=receiver_ids, channel__in=list(enabled_channels), is_enabled=True
        )
    }

    bulk_logs = []
    for notification in notifications:
        event = resolve_channel_event(notification)
        if event is None:
            continue
        channels = channels_by_user.get(str(notification.receiver_id), set())
        for channel in channels:
            if (str(notification.receiver_id), channel, event) not in enabled_events:
                continue
            bulk_logs.append(
                NotificationChannelLog(
                    receiver_id=notification.receiver_id,
                    triggered_by_id=notification.triggered_by_id,
                    channel=channel,
                    event=event,
                    entity_identifier=notification.entity_identifier,
                    entity_name=notification.entity_name,
                    data=notification.data,
                )
            )

    if not bulk_logs:
        return 0
    NotificationChannelLog.objects.bulk_create(bulk_logs, batch_size=100, ignore_conflicts=True)
    return len(bulk_logs)


@shared_task
def stack_notification_channel(batch_size: int = 100):
    """Pick up the pending channel logs and hand them over to the senders"""
    log_ids = list(
        NotificationChannelLog.objects.filter(
            channel__in=list(PROVIDERS.keys()), status=NOTIFICATION_CHANNEL_STATUS_PENDING, processed_at__isnull=True
        )
        .values_list("id", flat=True)[:batch_size]
    )
    if not log_ids:
        return
    NotificationChannelLog.objects.filter(id__in=log_ids).update(processed_at=timezone.now())
    for log_id in log_ids:
        send_notification_channel_log.delay(log_id)
    return len(log_ids)


@shared_task
def send_notification_channel_log(log_id):
    """Deliver a single queued channel log"""
    try:
        channel_log = NotificationChannelLog.objects.select_related("receiver").get(id=log_id)
    except NotificationChannelLog.DoesNotExist:
        logger.warning("Notification channel log %s no longer exists", log_id)
        return

    # the queue task may have picked up the same log twice
    if channel_log.status != NOTIFICATION_CHANNEL_STATUS_PENDING:
        return

    provider = get_provider(channel_log.channel)
    try:
        message = build_channel_message(channel_log.event, channel_log.data or {})
        result = provider.send_to_user(channel_log.receiver, message)
    except Exception as e:
        # never let a provider error bubble up, the log carries the reason
        logger.error("Notification channel %s delivery raised %s", channel_log.channel, type(e).__name__)
        result = None

    if result is None:
        channel_log.status = NOTIFICATION_CHANNEL_STATUS_FAILED
        channel_log.error_message = "Unexpected delivery error"[:255]
    elif result.ok:
        channel_log.status = NOTIFICATION_CHANNEL_STATUS_SENT
        channel_log.sent_at = timezone.now()
        channel_log.error_message = ""
    else:
        channel_log.status = NOTIFICATION_CHANNEL_STATUS_FAILED
        channel_log.error_message = result.summary

    channel_log.save(update_fields=["status", "sent_at", "error_message", "updated_at"])

    configuration, _created = UserNotificationChannel.objects.get_or_create(
        user=channel_log.receiver, channel=channel_log.channel
    )
    configuration.last_status = channel_log.status
    configuration.last_error = channel_log.error_message
    if result is not None and result.ok:
        configuration.is_verified = True
        configuration.verified_at = channel_log.sent_at
        configuration.last_delivered_at = channel_log.sent_at
    configuration.save(
        update_fields=["last_status", "last_error", "is_verified", "verified_at", "last_delivered_at", "updated_at"]
    )


__all__ = [
    "NOTIFICATION_CHANNEL_BALE",
    "NOTIFICATION_CHANNEL_SMS",
    "queue_notification_channel_logs",
    "resolve_channel_event",
    "send_notification_channel_log",
    "stack_notification_channel",
]