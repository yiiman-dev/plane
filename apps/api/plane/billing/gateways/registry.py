# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Registry mapping a gateway code onto its adapter class."""

# Python imports
from typing import Dict, Type

# Module imports
from plane.billing.gateways.base import BaseGateway, GatewayError
from plane.billing.gateways.digipay import DigipayGateway
from plane.billing.gateways.payping import PayPingGateway
from plane.billing.gateways.zarinpal import ZarinPalGateway
from plane.billing.gateways.zibal import ZibalGateway

GATEWAY_ADAPTERS: Dict[str, Type[BaseGateway]] = {
    ZarinPalGateway.code: ZarinPalGateway,
    PayPingGateway.code: PayPingGateway,
    ZibalGateway.code: ZibalGateway,
    DigipayGateway.code: DigipayGateway,
}


class UnknownGatewayError(GatewayError):
    """Raised when a gateway code has no adapter registered."""


def get_adapter_class(code: str) -> Type[BaseGateway]:
    try:
        return GATEWAY_ADAPTERS[str(code)]
    except KeyError as exc:
        raise UnknownGatewayError(f"Unknown payment gateway: {code}") from exc


def build_adapter(gateway) -> BaseGateway:
    """Instantiate the adapter bound to a PaymentGateway row."""
    return get_adapter_class(gateway.code)(gateway)


def supported_codes() -> list:
    return sorted(GATEWAY_ADAPTERS.keys())
