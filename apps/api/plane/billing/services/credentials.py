# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Encryption helpers for gateway credentials.

``encrypt_data`` from plane.license logs the exception and returns an empty
string on failure, therefore the result is validated explicitly here.
"""

# Python imports
import json

# Module imports
from plane.license.utils.encryption import decrypt_data, encrypt_data


class CredentialEncryptionError(Exception):
    """Raised when credentials cannot be encrypted or decrypted."""


def encrypt_credentials(payload: dict) -> str:
    """Encrypt a credential mapping into the ``credentials`` text column."""
    raw = json.dumps(payload or {})
    encrypted = encrypt_data(raw)
    if not encrypted:
        raise CredentialEncryptionError("Unable to encrypt the gateway credentials.")
    return encrypted


def decrypt_credentials(encrypted: str) -> dict:
    """Decrypt the ``credentials`` text column back into a mapping."""
    if not encrypted:
        return {}
    try:
        decrypted = decrypt_data(encrypted)
    except Exception as exc:  # pragma: no cover - defensive
        raise CredentialEncryptionError("Unable to decrypt the gateway credentials.") from exc
    if not decrypted:
        return {}
    try:
        value = json.loads(decrypted)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def get_credential(gateway, key: str, default=None):
    """Read a single credential value off a gateway row."""
    return decrypt_credentials(gateway.credentials).get(key, default)


def mask_credentials(credentials: dict) -> dict:
    """Return a masked representation safe for API responses."""
    masked = {}
    for key, value in (credentials or {}).items():
        text = "" if value is None else str(value)
        if not text:
            masked[key] = ""
        elif len(text) <= 8:
            masked[key] = "*" * len(text)
        else:
            masked[key] = f"{text[:3]}{'*' * 6}{text[-2:]}"
    return masked
