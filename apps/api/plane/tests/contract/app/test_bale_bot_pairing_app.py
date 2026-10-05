# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Tests for the bale bot pairing flow

A user never types a chat id. They ask the pairing endpoint for a one time code, hand
that code to the instance bot inside bale and the webhook links the bale chat to their
plane account. The raw code is returned exactly once, only its sha256 digest is stored.
"""

# Python imports
import hashlib
import sys
from types import ModuleType
from unittest.mock import Mock, patch

# Third party imports
import pytest
from django.utils import timezone
from rest_framework import status

# Module imports
from plane.db.models import (
    NOTIFICATION_CHANNEL_BALE,
    NotificationChannelPairingCode,
    UserNotificationChannel,
)
from plane.app.views.notification.bale_webhook import clear_attempts
from plane.license.models import InstanceConfiguration
from plane.utils.notifications.base import ChannelResult

PAIRING_URL = "/api/users/me/notification-channels/bale/pairing/"
CHANNELS_URL = "/api/users/me/notification-channels/"
WEBHOOK_URL = "/api/integrations/bale/webhook/{secret}/"

WEBHOOK_SECRET = "webhook-secret-for-tests"


def configure_instance(token="bot-token", username="@plane_bot", secret=WEBHOOK_SECRET):
    """Seed the instance configuration the bale channel reads through"""
    for key, value in (
        ("BALE_BOT_TOKEN", token),
        ("BALE_BOT_USERNAME", username),
        ("BALE_WEBHOOK_SECRET", secret),
    ):
        InstanceConfiguration.objects.update_or_create(key=key, defaults={"value": value, "is_encrypted": False})
    if secret is None:
        InstanceConfiguration.objects.filter(key="BALE_WEBHOOK_SECRET").delete()


def build_update(text, chat_id=778899, update_id="update-1"):
    """Build a bale text message update the way the bale api delivers it"""
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "chat": {"id": chat_id, "type": "private"},
            "from": {"id": chat_id, "username": "someone"},
            "date": 1700000000,
            "text": text,
        },
    }


@pytest.fixture(autouse=True)
def _bale_instance_configured():
    """Every test runs against an instance that has the bale channel configured"""
    configure_instance()


@pytest.fixture(autouse=True)
def reset_pairing_attempts():
    """Start every test with an empty rate limit counter

    The counter lives in the shared cache with a ten minute window, so it survives
    between pytest processes and would otherwise leak into unrelated tests.
    """
    for chat_id in ("778899", "445566", "999001", "515151"):
        clear_attempts(chat_id)
    yield
    for chat_id in ("778899", "445566", "999001", "515151"):
        clear_attempts(chat_id)


@pytest.fixture
def sent_messages():
    """Collect the replies the webhook sends back to bale instead of calling the api"""
    with patch("plane.app.views.notification.bale_webhook.send_text") as send_text:
        send_text.return_value = ChannelResult(ok=True, provider_message_id="1")
        yield send_text


@pytest.mark.contract
class TestPairingCodeCreation:
    @pytest.mark.django_db
    def test_post_returns_a_readable_code_and_stores_only_its_hash(self, session_client, db):
        response = session_client.post(PAIRING_URL, {}, format="json")

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "pending"
        assert body["expires_in_seconds"] == 600
        assert body["bot_username"] == "@plane_bot"
        # displayed as two readable groups of four characters
        assert len(body["code"]) == 9
        assert body["code"][4] == "-"
        assert body["code"].replace("-", "").isalnum()

        row = NotificationChannelPairingCode.objects.get()
        assert row.channel == NOTIFICATION_CHANNEL_BALE
        # the raw code is never persisted, only its digest
        assert row.code == hashlib.sha256(body["code"].replace("-", "").encode()).hexdigest()
        assert body["code"].replace("-", "") not in row.code

    @pytest.mark.django_db
    def test_post_is_rejected_when_the_bot_is_not_configured(self, session_client, db):
        configure_instance(token="")

        response = session_client.post(PAIRING_URL, {}, format="json")

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()
        assert NotificationChannelPairingCode.objects.count() == 0

    @pytest.mark.django_db
    def test_a_new_code_supersedes_the_previous_one(self, session_client, db):
        first = session_client.post(PAIRING_URL, {}, format="json").json()["code"]
        second = session_client.post(PAIRING_URL, {}, format="json").json()["code"]

        assert first != second
        # only the newest code stays usable
        assert NotificationChannelPairingCode.objects.filter(
            channel=NOTIFICATION_CHANNEL_BALE, consumed_at__isnull=True, expires_at__gt=timezone.now()
        ).count() == 1

    @pytest.mark.django_db
    def test_get_reports_not_started_before_any_code(self, session_client, db):
        response = session_client.get(PAIRING_URL)

        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["status"] == "not_started"
        assert body["code"] is None
        assert body["linked_at"] is None


@pytest.mark.contract
class TestWebhookSecret:
    @pytest.mark.django_db
    def test_a_wrong_secret_is_not_found(self, db, sent_messages):
        from rest_framework.test import APIClient

        response = APIClient().post(WEBHOOK_URL.format(secret="wrong-secret"), build_update("/start"), format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        # nothing is processed and nothing is answered back
        assert sent_messages.call_count == 0

    @pytest.mark.django_db
    def test_an_unset_secret_disables_the_endpoint(self, db, sent_messages):
        from rest_framework.test import APIClient

        configure_instance(secret=None)

        response = APIClient().post(WEBHOOK_URL.format(secret="anything"), build_update("/start"), format="json")

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert sent_messages.call_count == 0

    @pytest.mark.django_db
    def test_a_malformed_update_is_a_bad_request(self, db, sent_messages):
        from rest_framework.test import APIClient

        response = APIClient().post(
            WEBHOOK_URL.format(secret=WEBHOOK_SECRET), {"message": {"text": "hi"}}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert sent_messages.call_count == 0


@pytest.mark.contract
class TestPairingLifecycle:
    def _pair(self, api_client, chat_id):
        """Run the whole flow: ask for a code, deliver it through the webhook, return the code"""
        code = api_client.post(PAIRING_URL, {}, format="json").json()["code"]
        api_client.post(
            WEBHOOK_URL.format(secret=WEBHOOK_SECRET), build_update(code, chat_id=chat_id), format="json"
        )
        return code

    @pytest.mark.django_db
    def test_the_full_cycle_links_and_unlinks_the_account(self, session_client, sent_messages):
        # the webhook is unauthenticated, the same db session client can call it
        self._pair(session_client, chat_id=445566)

        user = session_client.handler._force_user
        # the webhook writes the chat id with a queryset update, reload it
        user.refresh_from_db()
        assert user.bale_chat_id == "445566"

        configuration = UserNotificationChannel.objects.get(user=user, channel=NOTIFICATION_CHANNEL_BALE)
        assert configuration.is_verified is True
        assert configuration.verified_at is not None

        # the webhook confirmed the pairing to the chat
        assert sent_messages.call_args[0][0] == "445566"
        assert "linked" in sent_messages.call_args[0][1].lower()

        # the aggregate tells the ui the account is linked
        aggregate = session_client.get(CHANNELS_URL).json()
        bale = next(channel for channel in aggregate["channels"] if channel["channel"] == NOTIFICATION_CHANNEL_BALE)
        assert bale["is_linked"] is True
        assert bale["linked_at"] is not None
        assert bale["bot_username"] == "@plane_bot"

        state = session_client.get(PAIRING_URL).json()
        assert state["status"] == "connected"
        assert state["code"] is None
        assert state["linked_at"] is not None

        # unlinking clears the chat, the verification and the pending codes
        response = session_client.delete(PAIRING_URL)
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "not_started"

        user.refresh_from_db()
        assert user.bale_chat_id is None
        configuration.refresh_from_db()
        assert configuration.is_verified is False
        assert configuration.is_enabled is False

    @pytest.mark.django_db
    def test_a_consumed_code_cannot_be_replayed(self, session_client, sent_messages):
        code = self._pair(session_client, chat_id=445566)
        sent_messages.reset_mock()

        response = session_client.post(
            WEBHOOK_URL.format(secret=WEBHOOK_SECRET),
            build_update(code, chat_id=999001, update_id="update-2"),
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        # the second chat is not linked by the replayed code
        session_client.handler._force_user.refresh_from_db()
        assert session_client.handler._force_user.bale_chat_id == "445566"
        assert "expired" in sent_messages.call_args[0][1].lower() or "used" in sent_messages.call_args[0][1].lower()

    @pytest.mark.django_db
    def test_an_unknown_code_is_rejected(self, session_client, sent_messages):
        response = session_client.post(
            WEBHOOK_URL.format(secret=WEBHOOK_SECRET), build_update("ZZZZ-ZZZZ"), format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        session_client.handler._force_user.refresh_from_db()
        assert session_client.handler._force_user.bale_chat_id is None
        assert "not valid" in sent_messages.call_args[0][1].lower()

    @pytest.mark.django_db
    def test_an_expired_code_is_rejected(self, session_client, db, sent_messages):
        code = session_client.post(PAIRING_URL, {}, format="json").json()["code"]
        NotificationChannelPairingCode.objects.update(expires_at=timezone.now() - timezone.timedelta(minutes=1))

        session_client.post(WEBHOOK_URL.format(secret=WEBHOOK_SECRET), build_update(code), format="json")

        session_client.handler._force_user.refresh_from_db()
        assert session_client.handler._force_user.bale_chat_id is None

    @pytest.mark.django_db
    def test_start_answers_with_the_instructions(self, session_client, sent_messages):
        response = session_client.post(
            WEBHOOK_URL.format(secret=WEBHOOK_SECRET), build_update("/start"), format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "welcome"
        text = sent_messages.call_args[0][1].lower()
        assert "notifications" in text
        assert "code" in text

    @pytest.mark.django_db
    def test_repeated_failures_are_rate_limited(self, session_client, sent_messages):
        for index in range(7):
            session_client.post(
                WEBHOOK_URL.format(secret=WEBHOOK_SECRET),
                build_update("ZZZZ-ZZZZ", chat_id=515151, update_id=f"update-{index}"),
                format="json",
            )

        replies = [call[0][1] for call in sent_messages.call_args_list]
        assert any("too many attempts" in reply.lower() for reply in replies)

    @pytest.mark.django_db
    def test_a_linked_chat_reaches_the_command_handler(self, session_client, sent_messages):
        self._pair(session_client, chat_id=445566)

        # The command handler is a separate workstream, stand a stub in for it so the
        # wiring itself is what is under test here.
        module = ModuleType("plane.utils.notifications.bale_commands")
        module.handle_bale_message = Mock()
        sys.modules["plane.utils.notifications.bale_commands"] = module
        handle_bale_message = module.handle_bale_message
        try:
            session_client.post(
                WEBHOOK_URL.format(secret=WEBHOOK_SECRET),
                build_update("my tasks", chat_id=445566, update_id="update-9"),
                format="json",
            )
        finally:
            del sys.modules["plane.utils.notifications.bale_commands"]

        assert handle_bale_message.call_count == 1
        assert handle_bale_message.call_args.kwargs["text"] == "my tasks"
        assert handle_bale_message.call_args.kwargs["chat_id"] == "445566"


@pytest.mark.contract
class TestManualBaleAddressIsRejected:
    @pytest.mark.django_db
    def test_patch_refuses_a_hand_typed_chat_id(self, session_client, db):
        response = session_client.patch(
            CHANNELS_URL, {"channel": "BALE", "bale_chat_id": "12345"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "pairing" in response.json()["error"].lower() or "code" in response.json()["error"].lower()

    @pytest.mark.django_db
    def test_patch_still_accepts_the_sms_address(self, session_client, create_user):
        response = session_client.patch(
            CHANNELS_URL, {"channel": "SMS", "mobile_number": "09121234567"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        create_user.refresh_from_db()
        # the sms path keeps its existing normalization to the international form
        assert create_user.mobile_number == "+989121234567"