# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Gateway selection engine. Free of any gateway specific logic."""

# Python imports
import random as random_module
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import List, Optional

# Module imports
from plane.billing.gateways.registry import build_adapter
from plane.billing.models import GatewayRoutingConfig, PaymentGateway, RoutingStrategy

ROUTING_TIMEZONE = dt_timezone(timedelta(hours=3, minutes=30))  # Asia/Tehran


@dataclass
class Candidate:
    gateway: PaymentGateway
    reason: str

    @property
    def code(self) -> str:
        return self.gateway.code

    def adapter(self):
        return build_adapter(self.gateway)


def _matches_hour(entry: dict, current_hour: int) -> bool:
    try:
        start_hour = int(entry.get("start_hour"))
        end_hour = int(entry.get("end_hour"))
    except (TypeError, ValueError):
        return False
    start_hour %= 24
    # 24 is the end of the day, only a larger value is wrapped
    end_hour = 24 if end_hour == 24 else end_hour % 24
    if start_hour == end_hour:
        return current_hour == start_hour
    if start_hour < end_hour:
        return start_hour <= current_hour < end_hour
    # window wraps across midnight, e.g. 22 -> 6
    return current_hour >= start_hour or current_hour < end_hour


class GatewayRouter:
    """Builds the ordered list of gateways to try for one payment attempt."""

    def __init__(self, config: Optional[GatewayRoutingConfig] = None, now: Optional[datetime] = None):
        self.config = config or GatewayRoutingConfig.get_solo()
        self.now = now or datetime.now(tz=ROUTING_TIMEZONE)

    # ------------------------------------------------------------- utilities
    @property
    def active_gateways(self) -> List[PaymentGateway]:
        return list(PaymentGateway.objects.filter(is_enabled=True).order_by("priority", "code"))

    def _in_cooldown(self, gateway: PaymentGateway) -> bool:
        if not gateway.last_error_at or self.config.cooldown_seconds <= 0:
            return False
        age = (self.now - gateway.last_error_at).total_seconds()
        return age < int(self.config.cooldown_seconds)

    def _by_priority(self, gateways: List[PaymentGateway]) -> List[PaymentGateway]:
        order = [str(code) for code in (self.config.priority_order or [])]
        rank = {code: index for index, code in enumerate(order)}
        return sorted(
            gateways,
            key=lambda gateway: (rank.get(gateway.code, len(rank)), -gateway.priority, gateway.code),
        )

    def _apply_cooldown(self, candidates: List[Candidate], reason_prefix: str) -> List[Candidate]:
        if not candidates:
            return candidates
        fresh = [item for item in candidates if not self._in_cooldown(item.gateway)]
        if not fresh:
            return candidates
        result = []
        for index, item in enumerate(fresh):
            suffix = f"{reason_prefix};cooldown-skip" if index else reason_prefix
            result.append(Candidate(gateway=item.gateway, reason=f"{item.reason}|{suffix}"))
        return result

    # ------------------------------------------------------------ strategies
    def schedule_candidates(self) -> List[Candidate]:
        gateways = {gateway.code: gateway for gateway in self.active_gateways}
        for entry in self.config.schedule_entries or []:
            if not isinstance(entry, dict):
                continue
            code = str(entry.get("gateway_code") or "")
            if code in gateways and _matches_hour(entry, self.now.hour):
                return [
                    Candidate(
                        gateway=gateways[code],
                        reason=f"schedule:matched:{entry.get('start_hour')}-{entry.get('end_hour')}",
                    )
                ]
        return self._apply_cooldown(
            [
                Candidate(gateway=gateway, reason="schedule:priority-fallback")
                for gateway in self._by_priority(list(gateways.values()))
            ],
            "schedule:priority-fallback",
        )

    def random_candidates(self, rng=None) -> List[Candidate]:
        gateways = self.active_gateways
        if not gateways:
            return []
        weights = [float((self.config.weights or {}).get(gateway.code, 1) or 0) for gateway in gateways]
        generator = rng or random_module
        first = (
            generator.choices(gateways, weights=weights, k=1)[0]
            if hasattr(generator, "choices")
            else generator.choice(gateways)
        )
        rest = [gateway for gateway in gateways if gateway.code != first.code]
        return self._apply_cooldown(
            [Candidate(gateway=first, reason="random:weighted-pick")]
            + [Candidate(gateway=gateway, reason="random:weighted-order") for gateway in rest],
            "random:weighted-pick",
        )

    def priority_candidates(self) -> List[Candidate]:
        gateways = self.active_gateways
        return self._apply_cooldown(
            [Candidate(gateway=gateway, reason="priority:order") for gateway in self._by_priority(gateways)],
            "priority:order",
        )

    # ------------------------------------------------------------------ api
    def candidates(self, rng=None) -> List[Candidate]:
        strategy = self.config.strategy
        if strategy == RoutingStrategy.SCHEDULE:
            return self.schedule_candidates()
        if strategy == RoutingStrategy.RANDOM:
            return self.random_candidates(rng=rng)
        return self.priority_candidates()

    def record_selection(self, candidate: Candidate, reason: str = "") -> None:
        self.config.last_selected_code = candidate.code
        self.config.last_selected_reason = (reason or candidate.reason)[:255]
        self.config.save(update_fields=["last_selected_code", "last_selected_reason", "updated_at"])
