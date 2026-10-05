# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import os

# Django imports
from django.conf import settings

# Module imports
from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import decrypt_data


# Helper function to return value from the passed key
def get_configuration_value(keys):
    environment_list = []
    if settings.SKIP_ENV_VAR:
        # Get the configurations
        instance_configuration = InstanceConfiguration.objects.values("key", "value", "is_encrypted")

        for key in keys:
            for item in instance_configuration:
                if key.get("key") == item.get("key"):
                    if item.get("is_encrypted", False):
                        environment_list.append(decrypt_data(item.get("value")))
                    else:
                        environment_list.append(item.get("value"))

                    break
            else:
                environment_list.append(key.get("default"))
    else:
        # Get the configuration from os
        for key in keys:
            environment_list.append(os.environ.get(key.get("key"), key.get("default")))

    return tuple(environment_list)


def get_workspace_free_seat_limit():
    """Raw value of the free plan seat limit configured on this instance.

    The value is returned unparsed on purpose: an empty or malformed value has
    to stay distinguishable from a real number so the billing entitlements
    service can treat it as "no limit" instead of silently capping seats.
    """
    return get_configuration_value(
        [
            {
                "key": "WORKSPACE_FREE_SEAT_LIMIT",
                "default": os.environ.get("WORKSPACE_FREE_SEAT_LIMIT"),
            },
        ]
    )


def get_kavenegar_configuration():
    return get_configuration_value(
        [
            {"key": "KAVENEGAR_API_KEY", "default": os.environ.get("KAVENEGAR_API_KEY")},
            {"key": "KAVENEGAR_SENDER_LINE", "default": os.environ.get("KAVENEGAR_SENDER_LINE")},
        ]
    )


def get_bale_configuration():
    return get_configuration_value(
        [
            {"key": "BALE_BOT_TOKEN", "default": os.environ.get("BALE_BOT_TOKEN")},
        ]
    )


def get_bale_bot_configuration():
    """Return the full bot configuration of the bale channel

    The token is the only value that is required, every other key degrades to a safe
    default so a partially configured instance can still serve the pairing endpoints.
    """
    token, username, base_url, secret = get_configuration_value(
        [
            {"key": "BALE_BOT_TOKEN", "default": os.environ.get("BALE_BOT_TOKEN")},
            {"key": "BALE_BOT_USERNAME", "default": os.environ.get("BALE_BOT_USERNAME")},
            {"key": "BALE_WEBHOOK_BASE_URL", "default": os.environ.get("BALE_WEBHOOK_BASE_URL")},
            {"key": "BALE_WEBHOOK_SECRET", "default": os.environ.get("BALE_WEBHOOK_SECRET")},
        ]
    )
    return (
        (token or "").strip(),
        (username or "").strip(),
        (base_url or "").strip() or (settings.WEB_URL or "").strip(),
        (secret or "").strip() or (os.environ.get("BALE_WEBHOOK_SECRET") or "").strip(),
    )


def get_email_configuration():
    return get_configuration_value(
        [
            {"key": "EMAIL_HOST", "default": os.environ.get("EMAIL_HOST")},
            {"key": "EMAIL_HOST_USER", "default": os.environ.get("EMAIL_HOST_USER")},
            {
                "key": "EMAIL_HOST_PASSWORD",
                "default": os.environ.get("EMAIL_HOST_PASSWORD"),
            },
            {"key": "EMAIL_PORT", "default": os.environ.get("EMAIL_PORT", 587)},
            {"key": "EMAIL_USE_TLS", "default": os.environ.get("EMAIL_USE_TLS", "1")},
            {"key": "EMAIL_USE_SSL", "default": os.environ.get("EMAIL_USE_SSL", "0")},
            {
                "key": "EMAIL_FROM",
                "default": os.environ.get("EMAIL_FROM", "Team Plane <team@mailer.plane.so>"),
            },
        ]
    )
