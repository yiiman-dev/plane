/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { getWeekOfMonth } from "date-fns";
import { renderFormattedDate, renderFormattedDateWithoutYear } from "@plane/utils";
import { describe, expect, it } from "vitest";
import { getCalendarAdapter, gregorianCalendar, persianCalendar } from "../src/adapters";

/**
 * The chart axis labels come from these two formatters plus the adapters. Pin the pieces
 * `getDateGroupingName` composes, since the function itself is module-private in apps/web.
 */
describe("chart axis label building blocks", () => {
  it("renders a day label in both systems", () => {
    const date = new Date(2025, 5, 15);
    // CORRECTION to the brief: `renderFormattedDateWithoutYear` takes `(date, system)` — the
    // brief's three-argument call would have passed `"persian"` nowhere and silently tested
    // the Gregorian path twice.
    expect(renderFormattedDateWithoutYear(date)).toBe("Jun 15");
    expect(renderFormattedDateWithoutYear(date, "persian")).toBe("۲۵ خرداد");
  });

  it("renders the 'MMM' month token in both systems", () => {
    const date = new Date(2025, 5, 15);
    expect(renderFormattedDate(date, "MMM")).toBe("Jun");
    expect(renderFormattedDate(date, "MMM", "persian")).toBe("خرداد");
  });

  it("compares years in the active calendar, not the Gregorian one", () => {
    // A Persian year boundary is ~621 years off, so comparing `getFullYear()` against
    // `new Date().getFullYear()` picks the wrong branch in Persian.
    //
    // CORRECTION to the brief: the brief called 2025-03-20 "1404-01-01". Nowruz 1404 is
    // 2025-03-21; 2025-03-20 is the last day of 1403 (30 Esfand 1403). Either date straddles
    // the boundary, so the assertion below uses the real pair.
    const nowruz = new Date(2025, 2, 21);
    expect(gregorianCalendar.toParts(nowruz).year).toBe(2025);
    expect(persianCalendar.toParts(nowruz).year).toBe(1404);

    const lastDayOfPrevYear = new Date(2025, 2, 20);
    expect(gregorianCalendar.toParts(lastDayOfPrevYear).year).toBe(2025);
    expect(persianCalendar.toParts(lastDayOfPrevYear).year).toBe(1403);
  });

  it("formats a bare year through the adapter identically in both systems", () => {
    // The `YEAR` grouping must render the year the user actually sees. This is also the
    // byte-identity guard for the Gregorian path: the adapter must agree with `${year}`.
    const date = new Date(2025, 5, 15);
    expect(getCalendarAdapter("gregorian").format(date, { year: "numeric" })).toBe("2025");
    expect(getCalendarAdapter("persian").format(date, { year: "numeric" })).toBe("۱۴۰۴");
  });

  it("keeps the whole Gregorian label set byte-identical", () => {
    // Every string apps/web renders today for a Gregorian user, for all four groupings.
    const currentYear = new Date(2025, 5, 15);
    const otherYear = new Date(2024, 5, 15);

    expect(renderFormattedDateWithoutYear(currentYear)).toBe("Jun 15");
    expect(renderFormattedDate(otherYear)).toBe("Jun 15, 2024");
    expect(`${renderFormattedDate(currentYear, "MMM")}, Week ${getWeekOfMonth(currentYear)}`).toBe("Jun, Week 3");
    expect(renderFormattedDate(currentYear, "MMM")).toBe("Jun");
    expect(renderFormattedDate(otherYear, "MMM, yyyy")).toBe("Jun, 2024");
    expect(`${gregorianCalendar.toParts(currentYear).year}`).toBe("2025");
  });
});
