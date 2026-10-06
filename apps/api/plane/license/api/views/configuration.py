# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from smtplib import (
    SMTPAuthenticationError,
    SMTPConnectError,
    SMTPRecipientsRefused,
    SMTPSenderRefused,
    SMTPServerDisconnected,
)

# Django imports
from django.core.mail import BadHeaderError, EmailMultiAlternatives, get_connection
from django.db.models import Q, Case, When, Value
from django.utils.crypto import get_random_string

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from .base import BaseAPIView
from plane.license.api.permissions import InstanceAdminPermission
from plane.license.models import InstanceConfiguration
from plane.utils.notifications import NotificationChannelError, NotificationChannelValidationError, get_provider
from plane.license.api.serializers import InstanceConfigurationSerializer
from plane.license.utils.encryption import encrypt_data
from plane.utils.cache import cache_response, invalidate_cache
from plane.license.utils.instance_value import get_email_configuration
from plane.utils.notifications.bale import (
    build_webhook_url,
    delete_webhook,
    get_bale_bot_username,
    get_me,
    get_webhook_info,
    set_webhook,
)


class InstanceConfigurationEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    @cache_response(60 * 60 * 2, user=False)
    def get(self, request):
        instance_configurations = InstanceConfiguration.objects.all()
        serializer = InstanceConfigurationSerializer(instance_configurations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @invalidate_cache(path="/api/instances/configurations/", user=False)
    @invalidate_cache(path="/api/instances/", user=False)
    def patch(self, request):
        configurations = InstanceConfiguration.objects.filter(key__in=request.data.keys())

        bulk_configurations = []
        for configuration in configurations:
            raw_value = request.data.get(configuration.key, configuration.value)
            value = "" if raw_value is None else str(raw_value).strip()
            if configuration.is_encrypted:
                configuration.value = encrypt_data(value)
            else:
                configuration.value = value
            bulk_configurations.append(configuration)

        InstanceConfiguration.objects.bulk_update(bulk_configurations, ["value"], batch_size=100)

        serializer = InstanceConfigurationSerializer(configurations, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DisableEmailFeatureEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    @invalidate_cache(path="/api/instances/", user=False)
    def delete(self, request):
        try:
            InstanceConfiguration.objects.filter(
                Q(
                    key__in=[
                        "EMAIL_HOST",
                        "EMAIL_HOST_USER",
                        "EMAIL_HOST_PASSWORD",
                        "ENABLE_SMTP",
                        "EMAIL_PORT",
                        "EMAIL_FROM",
                    ]
                )
            ).update(value=Case(When(key="ENABLE_SMTP", then=Value("0")), default=Value("")))
            return Response(status=status.HTTP_200_OK)
        except Exception:
            return Response(
                {"error": "Failed to disable email configuration"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class EmailCredentialCheckEndpoint(BaseAPIView):
    def post(self, request):
        receiver_email = request.data.get("receiver_email", False)
        if not receiver_email:
            return Response(
                {"error": "Receiver email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        (
            EMAIL_HOST,
            EMAIL_HOST_USER,
            EMAIL_HOST_PASSWORD,
            EMAIL_PORT,
            EMAIL_USE_TLS,
            EMAIL_USE_SSL,
            EMAIL_FROM,
        ) = get_email_configuration()

        # Configure all the connections
        connection = get_connection(
            host=EMAIL_HOST,
            port=int(EMAIL_PORT),
            username=EMAIL_HOST_USER,
            password=EMAIL_HOST_PASSWORD,
            use_tls=EMAIL_USE_TLS == "1",
            use_ssl=EMAIL_USE_SSL == "1",
        )
        # Prepare email details
        subject = "Email Notification from Plane"
        message = "This is a sample email notification sent from Plane application."
        # Send the email
        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=message,
                from_email=EMAIL_FROM,
                to=[receiver_email],
                connection=connection,
            )
            msg.send(fail_silently=False)
            return Response({"message": "Email successfully sent."}, status=status.HTTP_200_OK)
        except BadHeaderError:
            return Response({"error": "Invalid email header."}, status=status.HTTP_400_BAD_REQUEST)
        except SMTPAuthenticationError:
            return Response(
                {"error": "Invalid credentials provided"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SMTPConnectError:
            return Response(
                {"error": "Could not connect with the SMTP server."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SMTPSenderRefused:
            return Response(
                {"error": "From address is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SMTPServerDisconnected:
            return Response(
                {"error": "SMTP server disconnected unexpectedly."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except SMTPRecipientsRefused:
            return Response(
                {"error": "All recipient addresses were refused."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except TimeoutError:
            return Response(
                {"error": "Timeout error while trying to connect to the SMTP server."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ConnectionError:
            return Response(
                {"error": "Network connection error. Please check your internet connection."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            return Response(
                {"error": "Could not send email. Please check your configuration"},
                status=status.HTTP_400_BAD_REQUEST,
            )


class NotificationChannelCredentialCheckEndpoint(BaseAPIView):
    """Validate the instance wide credentials of the external notification channels

    The secret values are never echoed back, only the configured state is returned.
    """

    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        channel = str(request.data.get("channel") or "").strip()
        try:
            provider = get_provider(channel)
        except NotificationChannelValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            provider.check_config()
        except NotificationChannelError as e:
            return Response(
                {"channel": channel, "is_configured": False, "error": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            return Response(
                {
                    "channel": channel,
                    "is_configured": True,
                    "error": "Could not reach the provider, please verify the credentials.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"channel": channel, "is_configured": True}, status=status.HTTP_200_OK)


def save_instance_configuration_value(key, value):
    """Create or update a single instance configuration row, encrypted when required"""
    configuration, _created = InstanceConfiguration.objects.get_or_create(
        key=key, defaults={"category": "SECRET", "is_encrypted": False}
    )
    configuration.value = encrypt_data(value) if configuration.is_encrypted else value
    configuration.save(update_fields=["value"])
    return configuration


class BaleWebhookRegisterEndpoint(BaseAPIView):
    """Register the webhook of the bale bot and resolve the public identity of the bot"""

    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        _token, _username, _base_url, secret = get_bale_bot_configuration()
        if not _token:
            return Response(
                {"error": "BALE_BOT_TOKEN is not configured on this instance"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not secret:
            # The secret is what authenticates every incoming webhook call
            secret = get_random_string(48)
            save_instance_configuration_value("BALE_WEBHOOK_SECRET", secret)
            invalidate_cache(path="/api/instances/configurations/", user=False)

        webhook_url = build_webhook_url()
        if webhook_url is None:
            return Response(
                {"error": "Could not build the webhook url, check the instance web url"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            set_webhook(webhook_url)
            identity = get_me()
        except NotificationChannelError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {"error": "Could not reach Bale, please verify the bot token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = identity.get("username")
        if username:
            save_instance_configuration_value("BALE_BOT_USERNAME", username)
            invalidate_cache(path="/api/instances/configurations/", user=False)

        return Response(
            {
                "channel": "BALE",
                "is_registered": True,
                "webhook_url": webhook_url,
                "bot_username": f"@{username}" if username and not username.startswith("@") else username,
                "bot_id": str(identity.get("id")) if identity.get("id") else None,
                "bot_first_name": identity.get("first_name"),
            },
            status=status.HTTP_200_OK,
        )


class BaleWebhookUnregisterEndpoint(BaseAPIView):
    """Remove the webhook registration so the bot stops delivering updates"""

    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        try:
            delete_webhook()
        except NotificationChannelError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {"error": "Could not reach Bale, please verify the bot token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"channel": "BALE", "is_registered": False}, status=status.HTTP_200_OK)


class BaleWebhookStatusEndpoint(BaseAPIView):
    """Report the webhook the bot currently calls and the identity it answers to"""

    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        try:
            info = get_webhook_info()
        except NotificationChannelError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            return Response(
                {"error": "Could not reach Bale, please verify the bot token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = get_bale_bot_username()
        return Response(
            {
                "channel": "BALE",
                "is_registered": bool(info.get("url")),
                "webhook_url": info.get("url") or "",
                "bot_username": username,
            },
            status=status.HTTP_200_OK,
        )
