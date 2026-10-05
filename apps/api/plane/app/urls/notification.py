# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path


from plane.app.views import (
    NotificationViewSet,
    UnreadNotificationEndpoint,
    MarkAllReadNotificationViewSet,
    UserNotificationPreferenceEndpoint,
    NotificationChannelEndpoint,
    NotificationChannelPreferenceEndpoint,
    NotificationChannelTestEndpoint,
)

# Imported directly so the shared views __init__ stays untouched
from plane.app.views.notification.bale_webhook import BaleWebhookEndpoint
from plane.app.views.notification.channel import NotificationChannelPairingEndpoint


urlpatterns = [
    path(
        "workspaces/<str:slug>/users/notifications/",
        NotificationViewSet.as_view({"get": "list"}),
        name="notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/<uuid:pk>/",
        NotificationViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/<uuid:pk>/read/",
        NotificationViewSet.as_view({"post": "mark_read", "delete": "mark_unread"}),
        name="notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/<uuid:pk>/archive/",
        NotificationViewSet.as_view({"post": "archive", "delete": "unarchive"}),
        name="notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/unread/",
        UnreadNotificationEndpoint.as_view(),
        name="unread-notifications",
    ),
    path(
        "workspaces/<str:slug>/users/notifications/mark-all-read/",
        MarkAllReadNotificationViewSet.as_view({"post": "create"}),
        name="mark-all-read-notifications",
    ),
    path(
        "users/me/notification-preferences/",
        UserNotificationPreferenceEndpoint.as_view(),
        name="user-notification-preferences",
    ),
    path(
        "users/me/notification-channels/",
        NotificationChannelEndpoint.as_view(),
        name="user-notification-channels",
    ),
    path(
        "users/me/notification-channel-preferences/",
        NotificationChannelPreferenceEndpoint.as_view(),
        name="user-notification-channel-preferences",
    ),
    path(
        "users/me/notification-channels/test/",
        NotificationChannelTestEndpoint.as_view(),
        name="user-notification-channel-test",
    ),
    path(
        "users/me/notification-channels/bale/pairing/",
        NotificationChannelPairingEndpoint.as_view(),
        name="user-notification-channel-bale-pairing",
    ),
    path(
        "integrations/bale/webhook/<str:webhook_secret>/",
        BaleWebhookEndpoint.as_view(),
        name="bale-webhook",
    ),
]
