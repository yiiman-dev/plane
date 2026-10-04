# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Base contracts shared by every external notification channel provider."""

# Python imports
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional


logger = logging.getLogger("plane.bgtasks.notification.channel")

# Every outbound call is bounded so a slow provider can never block a worker
DEFAULT_HTTP_TIMEOUT = 10


class NotificationChannelError(Exception):
    """Base error for the notification channel providers"""


class NotificationChannelValidationError(NotificationChannelError):
    """Raised when the provider is not configured or the payload is invalid"""


@dataclass(frozen=True)
class ChannelResult:
    """Outcome of a single delivery attempt"""

    ok: bool
    provider_message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @property
    def summary(self) -> str:
        """Return a log and storage safe description of the failure"""
        if self.ok:
            return "delivered"
        return f"{self.error_code or 'unknown'}: {self.error_message or 'unknown error'}"[:255]


@dataclass(frozen=True)
class ChannelMessage:
    """Channel agnostic message with a provider independent metadata"""

    text: str
    # deep link to the entity that triggered the notification
    url: Optional[str] = None
    # entity name, used as the notification title on the provider side
    title: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class NotificationChannelProvider(ABC):
    """Interface every notification channel provider implements"""

    # channel key as stored on UserNotificationChannel
    channel: str = ""
    # maximum length accepted by the provider for a single message
    max_message_length: int = 1000

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True when the instance has the credentials the provider needs"""
        raise NotImplementedError

    @abstractmethod
    def get_recipient_address(self, user: Any) -> Optional[str]:
        """Return the address of the user for this channel, None when not linked"""
        raise NotImplementedError

    @abstractmethod
    def send(self, address: str, message: ChannelMessage) -> ChannelResult:
        """Deliver the message, return the outcome instead of raising"""
        raise NotImplementedError

    def build_configured_message(self, address: str, message: ChannelMessage) -> ChannelResult:
        """Send the message honouring the provider length limit"""
        text = message.text
        if len(text) > self.max_message_length:
            text = text[: self.max_message_length - 1].rstrip() + "…"
        return self.send(
            address,
            ChannelMessage(text=text, url=message.url, title=message.title, metadata=message.metadata),
        )

    def check_config(self) -> None:
        """Validate the provider configuration

        :raises NotificationChannelValidationError: when the provider is not usable
        """
        if not self.is_configured():
            raise NotificationChannelValidationError(f"{self.channel} provider is not configured on this instance")

    def resolve_recipient(self, user: Any) -> str:
        """Return the address of the user

        :raises NotificationChannelValidationError: when the user has no address linked
        """
        address = self.get_recipient_address(user)
        if not address:
            raise NotificationChannelValidationError(f"User has no {self.channel} address configured")
        return address

    def send_to_user(self, user: Any, message: ChannelMessage) -> ChannelResult:
        """Deliver a message to a user, converting every error into a ChannelResult"""
        try:
            self.check_config()
            address = self.resolve_recipient(user)
        except NotificationChannelValidationError as e:
            return ChannelResult(ok=False, error_code="not_configured", error_message=str(e)[:255])
        return self.build_configured_message(address, message)