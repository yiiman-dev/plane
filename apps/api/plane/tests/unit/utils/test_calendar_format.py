# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Tests for plane.utils.calendar_format.

Spec §4.1:
- Persian profile produces a Persian date in the email
- Gregorian profile is byte-identical to today's output
"""

import pytest

from plane.utils.calendar_format import format_activity_datetime, format_date_str


@pytest.mark.unit
class TestFormatActivityDatetime:
    """format_activity_datetime: activity-log timestamp → display string."""

    GREGORIAN_INPUT = "2024-08-22 14:30:00"

    def test_gregorian_output(self):
        result = format_activity_datetime(self.GREGORIAN_INPUT, "gregorian")
        assert result == "22 Aug 2024, 02:30 PM"

    def test_persian_output(self):
        # 2024-08-22 is 1403/06/01 in the Persian calendar
        result = format_activity_datetime(self.GREGORIAN_INPUT, "persian")
        assert "۱۴۰۳" in result
        assert "۰۶" in result
        assert "۰۱" in result
        assert "۱۴:۳۰" in result

    def test_persian_uses_persian_numerals(self):
        result = format_activity_datetime(self.GREGORIAN_INPUT, "persian")
        for ch in result:
            assert ch not in "0123456789", f"ASCII digit found in Persian output: {result!r}"

    def test_unknown_calendar_falls_back_to_gregorian(self):
        """Unknown calendar_system values must not raise — fall back to Gregorian."""
        result = format_activity_datetime(self.GREGORIAN_INPUT, "hijri")
        assert "2024" in result or "Aug" in result

    def test_persian_early_year(self):
        # 2024-04-10 is well inside 1403 (month 1, day 21 or 22)
        result = format_activity_datetime("2024-04-10 10:00:00", "persian")
        assert "۱۴۰۳" in result

    def test_persian_previous_year(self):
        # 2023-06-15 is well inside 1402
        result = format_activity_datetime("2023-06-15 10:00:00", "persian")
        assert "۱۴۰۲" in result


@pytest.mark.unit
class TestFormatDateStr:
    """format_date_str: raw ISO date string → display string."""

    def test_gregorian_output(self):
        result = format_date_str("2024-08-22", "gregorian")
        assert result == "22 Aug 2024"

    def test_persian_output(self):
        result = format_date_str("2024-08-22", "persian")
        assert "۱۴۰۳/۰۶/۰۱" == result

    def test_none_returns_empty(self):
        assert format_date_str(None, "gregorian") == ""
        assert format_date_str(None, "persian") == ""

    def test_unparseable_string_returned_unchanged(self):
        result = format_date_str("not-a-date", "gregorian")
        assert result == "not-a-date"

    def test_persian_numerals_only(self):
        result = format_date_str("2024-08-22", "persian")
        for ch in result:
            assert ch not in "0123456789", f"ASCII digit found: {result!r}"
