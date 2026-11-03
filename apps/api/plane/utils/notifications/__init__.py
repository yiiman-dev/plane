# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Provider registry for the external notification channels."""

# Python imports
from typing import Dict

# Module imports
from plane.db.models.notification import NOTIFICATION_CHANNEL_BALE, NOTIFICATION_CHANNEL_SMS
from .base import (
    ChannelMessage,
    ChannelResult,
    NotificationChannelError,
    NotificationChannelProvider,
    NotificationChannelValidationError,
)
from .bale import BaleProvider
from .kavenegar import KavenegarProvider


PROVIDERS: Dict[str, NotificationChannelProvider] = {
    NOTIFICATION_CHANNEL_SMS: KavenegarProvider(),
    NOTIFICATION_CHANNEL_BALE: BaleProvider(),
}


def get_provider(channel: str) -> NotificationChannelProvider:
    """Return the provider registered for the given channel

    :param channel: notification channel key, ie SMS or BALE
    :raises NotificationChannelValidationError: if the channel is not supported
    """
    provider = PROVIDERS.get(channel)
    if provider is None:
        raise NotificationChannelValidationError(f"Unsupported notification channel {channel}")
    return provider


__all__ = [
    "BaleProvider",
    "ChannelMessage",
    "ChannelResult",
    "KavenegarProvider",
    "NotificationChannelError",
    "NotificationChannelProvider",
    "NotificationChannelValidationError",
    "PROVIDERS",
    "get_provider",
]