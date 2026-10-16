# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Verification retries: beat registration, backoff selection and the broker-less path."""

# Python imports
from datetime import timedelta

# Third party imports
import pytest

# Django imports
from django.utils import timezone

# Module imports
from plane.billing.models import PaymentTransaction, TransactionStatus
from plane.billing.services import payment as payment_service
from plane.billing.services import tasks as billing_tasks

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(db):
    from django.contrib.auth import get_user_model

    return get_user_model().objects.create_user(
        email="retry-test@example.com", username="retry-test", password="password1234"
    )


def make_transaction(user, status, attempts=0, age=timedelta(hours=1)):
    transaction = PaymentTransaction.objects.create(
        user=user,
        gateway_code="zarinpal",
        gateway_token=f"TOK-{status}-{attempts}-{PaymentTransaction.objects.count()}",
        amount_toman=1_000_000,
        status=status,
        attempts=attempts,
    )
    # created_at is auto_now_add, so the age is written with a queryset update
    PaymentTransaction.objects.filter(pk=transaction.pk).update(created_at=timezone.now() - age)
    return transaction


@pytest.fixture
def recorded_retries(monkeypatch):
    """Replace the verify call so the retry loop can be observed without a gateway."""
    calls = []

    def fake_process_callback(gateway_code, payload, transaction=None):
        calls.append(transaction.pk)
        return {"status": transaction.status}

    monkeypatch.setattr(payment_service, "process_callback", fake_process_callback)
    return calls


def test_beat_schedule_registers_the_retry_task():
    from plane.celery import app

    entry = app.conf.beat_schedule["retry-pending-payment-verifications"]

    assert entry["task"] == billing_tasks.retry_pending_verifications.name
    assert entry["task"] == "plane.billing.services.tasks.retry_pending_verifications"


def test_only_due_processing_and_unavailable_transactions_are_retried(user, recorded_retries):
    due_processing = make_transaction(user, TransactionStatus.PROCESSING)
    due_unavailable = make_transaction(user, TransactionStatus.UNAVAILABLE, attempts=2)
    too_recent = make_transaction(user, TransactionStatus.PROCESSING, age=timedelta(seconds=1))
    exhausted = make_transaction(user, TransactionStatus.PROCESSING, attempts=billing_tasks.MAX_VERIFY_ATTEMPTS)
    make_transaction(user, TransactionStatus.PAID)
    make_transaction(user, TransactionStatus.FAILED)

    processed = billing_tasks.retry_pending_verifications()

    assert processed == 2
    assert sorted(recorded_retries) == sorted([due_processing.pk, due_unavailable.pk])
    assert too_recent.pk not in recorded_retries
    assert exhausted.pk not in recorded_retries


def test_one_failing_retry_does_not_stop_the_rest(user, monkeypatch):
    first = make_transaction(user, TransactionStatus.PROCESSING)
    second = make_transaction(user, TransactionStatus.PROCESSING)
    seen = []

    def flaky_process_callback(gateway_code, payload, transaction=None):
        seen.append(transaction.pk)
        if transaction.pk == first.pk:
            raise RuntimeError("gateway exploded")
        return {"status": transaction.status}

    monkeypatch.setattr(payment_service, "process_callback", flaky_process_callback)

    processed = billing_tasks.retry_pending_verifications()

    assert processed == 1
    assert sorted(seen) == sorted([first.pk, second.pk])


def test_retry_runs_from_beat_when_the_broker_is_down(user, monkeypatch, recorded_retries):
    """Beat calls the task body directly, so a dead broker cannot stop the retry."""
    transaction = make_transaction(user, TransactionStatus.UNAVAILABLE)

    def broker_down(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(billing_tasks.retry_pending_verifications, "delay", broker_down)

    assert billing_tasks.retry_pending_verifications() == 1
    assert recorded_retries == [transaction.pk]


def test_enqueue_swallows_a_broker_outage(user, monkeypatch):
    """A failed enqueue must not fail the callback; the beat schedule picks the row up."""
    transaction = make_transaction(user, TransactionStatus.PROCESSING)

    def broker_down(*args, **kwargs):
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(billing_tasks.retry_pending_verifications, "delay", broker_down)

    billing_tasks.schedule_verification_retry(transaction)
