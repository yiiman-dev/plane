# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Routing engine tests: schedule, random and priority strategies."""

# Python imports
import datetime

# Third party imports
import pytest

# Module imports
from plane.billing.models import GatewayRoutingConfig, PaymentGateway, RoutingStrategy
from plane.billing.services.router import ROUTING_TIMEZONE, GatewayRouter, _matches_hour

# Local imports
from plane.billing.tests.conftest import FakeRNG, make_gateway

pytestmark = pytest.mark.django_db


def at(hour: int, minute: int = 0) -> datetime.datetime:
    """A Tehran local timestamp on a fixed day."""
    return datetime.datetime(2026, 1, 15, hour, minute, tzinfo=ROUTING_TIMEZONE)


def configure(strategy: str, **config_kwargs) -> GatewayRoutingConfig:
    config = GatewayRoutingConfig.get_solo()
    config.strategy = strategy
    for key, value in config_kwargs.items():
        setattr(config, key, value)
    config.save()
    return config


def router(strategy: str, hour: int = 12, **config_kwargs) -> GatewayRouter:
    return GatewayRouter(configure(strategy, **config_kwargs), now=at(hour))


def selected_codes(instance: GatewayRouter, **kwargs) -> list:
    return [candidate.code for candidate in instance.candidates(**kwargs)]


# -------------------------------------------------------------- window helper
def test_schedule_window_crossing_midnight_is_a_single_window():
    entry = {"start_hour": 22, "end_hour": 6}

    assert [hour for hour in range(24) if _matches_hour(entry, hour)] == [
        0,
        1,
        2,
        3,
        4,
        5,
        22,
        23,
    ]


def test_schedule_window_normal_range_excludes_the_end_hour():
    entry = {"start_hour": 8, "end_hour": 12}

    assert _matches_hour(entry, 8) is True
    assert _matches_hour(entry, 11) is True
    assert _matches_hour(entry, 12) is False


def test_schedule_window_covers_the_whole_day():
    entry = {"start_hour": 0, "end_hour": 24}

    assert [hour for hour in range(24) if _matches_hour(entry, hour)] == list(range(24))


# --------------------------------------------------------------------- schedule
def test_schedule_selects_the_gateway_of_the_current_window():
    make_gateway("zarinpal")
    make_gateway("payping")
    make_gateway("zibal")
    entries = [
        {"start_hour": 0, "end_hour": 8, "gateway_code": "zarinpal"},
        {"start_hour": 8, "end_hour": 20, "gateway_code": "payping"},
        {"start_hour": 20, "end_hour": 24, "gateway_code": "zibal"},
    ]

    for hour, expected in (
        (0, "zarinpal"),
        (7, "zarinpal"),
        (8, "payping"),
        (12, "payping"),
        (19, "payping"),
        (20, "zibal"),
        (23, "zibal"),
    ):
        assert selected_codes(router(RoutingStrategy.SCHEDULE, hour, schedule_entries=entries)) == [expected], hour


def test_schedule_window_crossing_midnight_is_matched_end_to_end():
    make_gateway("zarinpal")
    make_gateway("payping")
    entries = [
        {"start_hour": 22, "end_hour": 6, "gateway_code": "zarinpal"},
        {"start_hour": 6, "end_hour": 22, "gateway_code": "payping"},
    ]

    for hour, expected in (
        (21, "payping"),
        (22, "zarinpal"),
        (23, "zarinpal"),
        (0, "zarinpal"),
        (3, "zarinpal"),
        (5, "zarinpal"),
        (6, "payping"),
        (12, "payping"),
    ):
        assert selected_codes(router(RoutingStrategy.SCHEDULE, hour, schedule_entries=entries)) == [expected], hour


def test_schedule_without_a_match_falls_back_to_priority_order():
    make_gateway("zarinpal", priority=5)
    make_gateway("payping", priority=1)
    instance = router(
        RoutingStrategy.SCHEDULE,
        12,
        schedule_entries=[{"start_hour": 1, "end_hour": 2, "gateway_code": "zarinpal"}],
        priority_order=["payping", "zarinpal"],
    )

    candidates = instance.candidates()

    assert candidates[0].code == "payping"
    assert "priority-fallback" in candidates[0].reason


def test_schedule_skips_a_disabled_or_unknown_gateway():
    make_gateway("zarinpal", is_enabled=False)
    make_gateway("payping")
    instance = router(
        RoutingStrategy.SCHEDULE,
        12,
        schedule_entries=[
            {"start_hour": 0, "end_hour": 24, "gateway_code": "zarinpal"},
            {"start_hour": 0, "end_hour": 24, "gateway_code": "does-not-exist"},
        ],
        priority_order=["payping"],
    )

    assert selected_codes(instance) == ["payping"]


def test_schedule_ignores_a_malformed_entry():
    make_gateway("payping")
    instance = router(
        RoutingStrategy.SCHEDULE,
        12,
        schedule_entries=["not-a-dict", {"start_hour": "x", "end_hour": None, "gateway_code": "payping"}],
        priority_order=["payping"],
    )

    assert selected_codes(instance) == ["payping"]


# ----------------------------------------------------------------------- random
def test_random_honours_a_fixed_rng_and_returns_the_rest_as_backup():
    make_gateway("zarinpal")
    make_gateway("payping")
    make_gateway("zibal")
    instance = router(
        RoutingStrategy.RANDOM,
        12,
        weights={"zarinpal": 70, "payping": 20, "zibal": 10},
    )

    for expected in ("zarinpal", "payping", "zibal"):
        codes = selected_codes(instance, rng=FakeRNG(expected))
        assert codes[0] == expected
        # the other gateways remain available as fallback, exactly once each
        assert sorted(codes) == ["payping", "zarinpal", "zibal"]


def test_random_without_weights_picks_equally():
    make_gateway("zarinpal")
    make_gateway("payping")
    instance = router(RoutingStrategy.RANDOM, 12, weights={})

    assert selected_codes(instance, rng=FakeRNG("payping"))[0] == "payping"


def test_random_with_no_enabled_gateway_returns_nothing():
    make_gateway("zarinpal", is_enabled=False)
    instance = router(RoutingStrategy.RANDOM, 12, weights={})

    assert instance.candidates(FakeRNG("zarinpal")) == []


# --------------------------------------------------------------------- priority
def test_priority_follows_the_admin_order():
    make_gateway("zarinpal", priority=9)
    make_gateway("payping", priority=0)
    make_gateway("zibal", priority=5)
    instance = router(RoutingStrategy.PRIORITY, 12, priority_order=["zibal", "payping", "zarinpal"])

    assert selected_codes(instance) == ["zibal", "payping", "zarinpal"]


def test_priority_order_falls_back_to_the_row_priority_column():
    make_gateway("zarinpal", priority=9)
    make_gateway("payping", priority=0)
    instance = router(RoutingStrategy.PRIORITY, 12, priority_order=[])

    assert selected_codes(instance) == ["zarinpal", "payping"]


def test_priority_order_honours_a_disabled_gateway_exclusion():
    make_gateway("zarinpal", is_enabled=False)
    make_gateway("payping")
    instance = router(RoutingStrategy.PRIORITY, 12, priority_order=["zarinpal", "payping"])

    assert selected_codes(instance) == ["payping"]


# --------------------------------------------------------------------- cooldown
def test_cooldown_marks_the_untried_gateways():
    make_gateway("zarinpal")
    make_gateway("payping")
    make_gateway("zibal")
    config = configure(RoutingStrategy.PRIORITY, priority_order=["zarinpal", "payping"], cooldown_seconds=900)
    zarinpal = PaymentGateway.objects.get(code="zarinpal")
    zarinpal.last_error_at = at(11, 59)
    zarinpal.save()

    instance = GatewayRouter(config, now=at(12))

    # the cooled down gateway is dropped, the rest keep the admin order
    assert selected_codes(instance) == ["payping", "zibal"]
    # the first surviving gateway leads, the ones behind it are marked as skips
    assert "cooldown-skip" not in instance.candidates()[0].reason
    assert "cooldown-skip" in instance.candidates()[1].reason


def test_cooldown_expires():
    make_gateway("zarinpal")
    make_gateway("payping")
    config = configure(RoutingStrategy.PRIORITY, priority_order=["zarinpal", "payping"], cooldown_seconds=900)
    zarinpal = PaymentGateway.objects.get(code="zarinpal")
    zarinpal.last_error_at = at(12) - datetime.timedelta(seconds=901)
    zarinpal.save()

    assert selected_codes(GatewayRouter(config, now=at(12))) == ["zarinpal", "payping"]


def test_cooldown_of_zero_is_ignored():
    make_gateway("zarinpal")
    config = configure(RoutingStrategy.PRIORITY, priority_order=["zarinpal"], cooldown_seconds=0)
    zarinpal = PaymentGateway.objects.get(code="zarinpal")
    zarinpal.last_error_at = at(12)
    zarinpal.save()

    assert selected_codes(GatewayRouter(config, now=at(12))) == ["zarinpal"]


# -------------------------------------------------------------------- ordering
def test_every_strategy_returns_a_stable_ordered_candidate_list():
    make_gateway("zarinpal")
    make_gateway("payping")
    instance = router(RoutingStrategy.PRIORITY, 12, priority_order=["payping", "zarinpal"])

    assert selected_codes(instance) == selected_codes(instance)
    for candidate in instance.candidates():
        assert candidate.reason
        assert candidate.adapter().code == candidate.code


def test_record_selection_is_written_back_for_observability():
    make_gateway("zarinpal")
    config = configure(RoutingStrategy.PRIORITY, priority_order=["zarinpal"])
    instance = GatewayRouter(config, now=at(12))
    candidate = instance.candidates()[0]

    instance.record_selection(candidate)

    config.refresh_from_db()
    assert config.last_selected_code == "zarinpal"


def test_no_candidate_when_every_gateway_is_disabled():
    make_gateway("zarinpal", is_enabled=False)
    instance = router(RoutingStrategy.PRIORITY, 12, priority_order=["zarinpal"])

    assert instance.candidates() == []
