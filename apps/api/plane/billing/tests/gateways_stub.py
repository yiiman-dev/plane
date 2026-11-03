# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Scripted adapter used by the payment service tests.

It implements the same surface as ``plane.billing.gateways.base.BaseGateway``
so the routing and callback code can be exercised without any HTTP call.
"""

# Python imports
from typing import Optional


class StubAdapter:
    code = "stub"

    def __init__(
        self,
        code: str,
        redirect_url: str = "",
        token: str = "TOKEN",
        meta: Optional[dict] = None,
        raw: Optional[dict] = None,
        create_error: Optional[Exception] = None,
        verify_result=None,
        verify_error: Optional[Exception] = None,
    ):
        self.code = code
        self.redirect_url = redirect_url or f"https://pay.example/{code}"
        self.token = token
        self.meta = meta or {}
        self.raw = raw or {}
        self.create_error = create_error
        self.verify_result = verify_result
        self.verify_error = verify_error
        # per instance behaviour the tests tweak
        self.callback_indicator = None
        self.callback_meta: dict = {}
        self.create_calls = 0
        self.verify_calls = 0
        self.inquiry_result = None

    def create_payment(self, amount_toman, description, order_id, callback, mobile=""):
        self.create_calls += 1
        if self.create_error is not None:
            raise self.create_error
        # Local imports
        from plane.billing.gateways.base import CreatePaymentResult

        return CreatePaymentResult(redirect_url=self.redirect_url, token=self.token, raw=self.raw, meta=self.meta)

    def verify(self, token, amount_toman, callback_payload):
        self.verify_calls += 1
        if self.verify_error is not None:
            raise self.verify_error
        return self.verify_result

    def reverse(self, token):
        # Local imports
        from plane.billing.gateways.base import GatewayStatus, ReverseResult

        return ReverseResult(status=GatewayStatus.UNAVAILABLE, message="not supported")

    def inquiry(self, token):
        return self.inquiry_result

    def callback_indicates_payment(self, payload):
        return self.callback_indicator

    def extract_callback_token(self, payload):
        for key in ("Authority", "trackId", "paymentCode", "Ticket", "ticket", "trackingCode"):
            if payload.get(key):
                return str(payload[key])
        return ""

    def extract_callback_meta(self, payload):
        return dict(self.callback_meta)

    def extract_callback_refs(self, payload):
        return [str(value) for value in self.callback_meta.values() if value]

    def mark_unhealthy(self, message, *_args, **_kwargs):
        return None

    def mark_healthy(self):
        return None
