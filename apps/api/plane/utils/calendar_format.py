# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""
Calendar-aware date formatting for server-generated content (emails).

All storage stays Gregorian. This module converts only for display: the
`activity_time` timestamp shown in issue-update emails, and raw ISO date
strings (like "2024-08-22") shown as due-date changes.

`jdatetime` is the only place Persian calendar logic lives in Python.
"""

from datetime import date, datetime


def _to_persian_numerals(s: str) -> str:
    table = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return s.translate(table)


def format_activity_datetime(dt_str: str, calendar_system: str) -> str:
    """
    Format a "%Y-%m-%d %H:%M:%S" datetime string for display in emails.

    Gregorian: "Aug 22, 2024, 02:30 PM"
    Persian:   "۱۴۰۳/۰۶/۰۱، ۱۴:۳۰"
    """
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    if calendar_system == "persian":
        import jdatetime  # local import — only pulled when the user needs Persian

        jdt = jdatetime.datetime.fromgregorian(datetime=dt)
        date_part = f"{jdt.year}/{jdt.month:02d}/{jdt.day:02d}"
        time_part = f"{jdt.hour:02d}:{jdt.minute:02d}"
        return _to_persian_numerals(f"{date_part}، {time_part}")
    return dt.strftime("%-d %b %Y, %I:%M %p")


def format_date_str(date_str: str | None, calendar_system: str) -> str:
    """
    Format a raw ISO date string ("2024-08-22") for display in emails.

    Gregorian: "Aug 22, 2024"
    Persian:   "۱۴۰۳/۰۶/۰۱"
    Returns the original string unchanged if it cannot be parsed.
    """
    if not date_str:
        return date_str or ""
    try:
        d = date.fromisoformat(date_str)
    except ValueError:
        return date_str
    if calendar_system == "persian":
        import jdatetime

        jd = jdatetime.date.fromgregorian(date=d)
        return _to_persian_numerals(f"{jd.year}/{jd.month:02d}/{jd.day:02d}")
    return d.strftime("%-d %b %Y")
