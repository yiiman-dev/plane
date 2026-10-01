/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { DAYS_LIST, MONTHS_LIST } from "@plane/constants";
import { gregorianCalendar } from "../src/adapters";
import { isWeekend, monthName, weekdayNames } from "../src/labels";

/**
 * The calendar layout read `MONTHS_LIST` / `DAYS_LIST` directly. These assertions pin the adapter's
 * output against those tables so replacing the constants with adapter calls is a no-op for
 * Gregorian users — which is the whole safety claim for this task.
 *
 * `@plane/constants` is not a dependency of this package (see `vitest.config.ts` for why the
 * import is aliased to source rather than declared): the test only needs the two tables, and
 * depending on it would tie this package to a build of a package it does not ship against.
 */
describe("layout labels are unchanged for Gregorian", () => {
  it("monthName reproduces every MONTHS_LIST title and shortTitle", () => {
    for (let month = 1; month <= 12; month++) {
      expect(monthName(gregorianCalendar, month, "long")).toBe(MONTHS_LIST[month].title);
      expect(monthName(gregorianCalendar, month, "short")).toBe(MONTHS_LIST[month].shortTitle);
    }
  });

  it("weekdayNames reproduces every DAYS_LIST shortTitle", () => {
    // DAYS_LIST is 1-based with an `EStartOfTheWeek` value of 0..6; weekdayNames is 0-based
    // rotated by weekStartsOn, so order by `.value`.
    const expected = Object.values(DAYS_LIST)
      .toSorted((a, b) => a.value - b.value)
      .map((d) => d.shortTitle);
    expect(weekdayNames(gregorianCalendar, "short", 0)).toEqual(expected);
  });

  it("isWeekend matches the Sat/Sun literal it replaces, for every weekday", () => {
    // 2025-06-15 is a Sunday, so +0..+6 walks the whole week.
    for (let offset = 0; offset < 7; offset++) {
      const date = new Date(2025, 5, 15 + offset);
      const day = date.getDay();
      expect(isWeekend(date, 0)).toBe(day === 0 || day === 6);
    }
  });
});
