# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared helpers for the billing tests. No test performs a real HTTP call."""

# Python imports
import json
from typing import Any, Dict, List, Optional

# Third party imports
import pytest
from rest_framework.test import APIClient

# Django imports
from django.utils import timezone

# Module imports
from plane.billing.gateways import base as gateways_base
from plane.billing.gateways import digipay as digipay_module
from plane.billing.models import PaymentGateway
from plane.billing.services.credentials import encrypt_credentials
from plane.db.models import User
from plane.license.models import Instance, InstanceAdmin

# Test credentials only, never a real merchant account.
CREDENTIALS = {
    "zarinpal": {"merchant_id": "00000000-0000-0000-0000-000000000001"},
    "payping": {"api_token": "test-token-1234567890"},
    "zibal": {"merchant": "zibal"},
    "digipay": {
        "client_id": "client-id",
        "client_secret": "client-secret",
        "username": "user",
        "password": "pass",
    },
}


class FakeHTTP:
    """Scripted stand in for ``plane.billing.gateways.base.http_request``."""

    def __init__(self):
        self.responses: List[Any] = []
        self.calls: List[Dict[str, Any]] = []

    def queue(self, *responses: Any) -> "FakeHTTP":
        self.responses.extend(responses)
        return self

    def __call__(self, method, url, headers=None, json_body=None, form=None, timeout=None):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "json_body": json_body,
                "form": form,
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError(f"unexpected HTTP call: {method} {url}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def last_body(self) -> Dict[str, Any]:
        return self.calls[-1]["json_body"] or {}

    def last_form(self) -> Dict[str, Any]:
        return self.calls[-1]["form"] or {}

    def last_url(self) -> str:
        return self.calls[-1]["url"]


class FakeCache:
    """Minimal in memory cache used for the Digipay OAuth access token."""

    def __init__(self):
        self.store: Dict[str, Any] = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, timeout=None):
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)
        return True


class FakeRNG:
    """Deterministic replacement for ``random.choices``."""

    def __init__(self, pick):
        self.pick = pick

    def choices(self, population, weights=None, k=1, **kwargs):
        assert len(weights) == len(population)
        assert sum(weights) > 0
        return [next(item for item in population if item.code == self.pick)]


@pytest.fixture
def http(monkeypatch):
    """Replace the gateway transport with a scripted fake."""
    fake = FakeHTTP()
    monkeypatch.setattr(gateways_base, "http_request", fake)
    return fake


@pytest.fixture
def instance(db):
    """The single instance the admin permission classes read from."""
    existing = Instance.objects.first()
    if existing is not None:
        return existing
    return Instance.objects.create(
        instance_name="Plane Test Instance",
        instance_id="plane-test-instance",
        current_version="v0.0.0-test",
        last_checked_at=timezone.now(),
    )


@pytest.fixture
def instance_admin(db, instance):
    """A real user holding an InstanceAdmin role above the required level 15."""
    user = User.objects.create(
        email="instance-admin@example.com",
        first_name="Instance",
        last_name="Admin",
    )
    user.set_password("password1234")
    user.save()
    InstanceAdmin.objects.create(instance=instance, user=user, role=20)
    return user


@pytest.fixture
def client(db):
    """Unauthenticated API client, tests log the user in themselves."""
    return APIClient()


@pytest.fixture
def fake_cache(monkeypatch):
    """Replace the Django cache the Digipay adapter reads its token from."""
    cache = FakeCache()
    monkeypatch.setattr(digipay_module, "cache", cache)
    return cache


def make_gateway(code: str, **kwargs) -> PaymentGateway:
    """Create an enabled PaymentGateway row with encrypted test credentials."""
    extra_config = kwargs.pop("extra_config", None)
    credentials = kwargs.pop("credentials", CREDENTIALS.get(code, {}))
    defaults = {
        "title": code.title(),
        "is_enabled": True,
        "is_sandbox": True,
        "priority": 0,
        "extra_config": {} if extra_config is None else extra_config,
    }
    defaults.update(kwargs)
    return PaymentGateway.objects.create(code=code, credentials=encrypt_credentials(credentials), **defaults)


def dumps(value: Any) -> str:
    return json.dumps(value)


def payping_callback_data(**overrides) -> Dict[str, Any]:
    """A PayPing merchant callback, the merchant side ids live in ``data``."""
    data = {
        "clientRefId": "INV-1",
        "paymentCode": "PP-CODE-1",
        "paymentRefId": 987,
        "amount": 50000,
    }
    data.update(overrides)
    return {
        "status": "PAID",
        "errorCode": 0,
        "data": json.dumps(data),
        "message": "",
        "errorMessage": "",
        "paymentRefId": data["paymentRefId"],
        "clientRefId": data["clientRefId"],
        "paymentCode": data["paymentCode"],
    }


def payping_callback(value: Any = None):
    return dumps(value) if value is not None else None


def optional_int(value) -> Optional[int]:
    return None if value is None else int(value)
