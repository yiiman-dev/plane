# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Public callback endpoints. One URL per gateway, shared across all four."""

# Python imports
import logging

# Third party imports
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

# Module imports
from plane.billing.gateways.registry import supported_codes
from plane.billing.services.payment import BillingError, build_zibal_start_url, process_callback

logger = logging.getLogger("plane.billing")

RESULT_REDIRECT = True


def _payload_from_request(request) -> dict:
    payload = {key: value for key, value in request.data.items()}
    for key, value in request.query_params.items():
        payload.setdefault(key, value)
    return {key: value for key, value in payload.items()}


class BaseCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def handle(self, request, gateway_code: str, payload: dict):
        if gateway_code not in supported_codes():
            return Response({"error": "Unknown gateway"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = process_callback(gateway_code, payload)
        except BillingError as exc:
            logger.warning("billing: callback rejected for %s: %s", gateway_code, exc)
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        if RESULT_REDIRECT and result.get("result_url"):
            from django.http import HttpResponseRedirect

            return HttpResponseRedirect(result["result_url"])
        return Response(result, status=status.HTTP_200_OK)


class PaymentCallbackEndpoint(BaseCallbackView):
    """ZarinPal, Zibal and Digipay callbacks (GET and POST)."""

    def get(self, request, gateway_code):
        return self.handle(request, gateway_code, dict(request.query_params.items()))

    def post(self, request, gateway_code):
        return self.handle(request, gateway_code, _payload_from_request(request))


class PayPingCallbackEndpoint(BaseCallbackView):
    """PayPing merchant callback: /v3/pay/paid/{refId}/{paymentCode} equivalent."""

    def get(self, request, gateway_code, ref_id, payment_code):
        payload = dict(request.query_params.items())
        payload.setdefault("paymentCode", payment_code)
        payload.setdefault("paymentRefId", ref_id)
        return self.handle(request, "payping", payload)

    def post(self, request, gateway_code, ref_id, payment_code):
        payload = _payload_from_request(request)
        payload.setdefault("paymentCode", payment_code)
        payload.setdefault("paymentRefId", ref_id)
        return self.handle(request, "payping", payload)


class ZibalStartEndpoint(APIView):
    """Intermediate redirect so the browser hits Zibal with a valid Referer.

    Zibal compares the Referer of the start request with the domain that is
    registered in its panel, therefore the caller supplied target is ignored
    and the redirect is rebuilt from the stored gateway configuration.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, track_id):
        from django.http import HttpResponseRedirect

        try:
            target = build_zibal_start_url(track_id)
        except BillingError as exc:
            logger.warning("billing: zibal start rejected: %s", exc)
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return HttpResponseRedirect(target)
