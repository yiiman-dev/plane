/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { gregorianCalendar, persianCalendar } from "../src/adapters";
import { isWeekend, monthName, weekdayNames } from "../src/labels";

const g = (year: number, monthIndex: number, day: number) => new Date(year, monthIndex, day);

describe("monthName", () => {
  it("is 1-based, matching the adapter's toParts", () => {
    expect(monthName(gregorianCalendar, 1)).toBe("January");
    expect(monthName(gregorianCalendar, 12)).toBe("December");
  });

  it("returns the Gregorian short form unchanged", () => {
    // packages/constants/src/calendar.ts MONTHS_LIST shortTitle — the layout's current output.
    expect(monthName(gregorianCalendar, 1, "short")).toBe("Jan");
    expect(monthName(gregorianCalendar, 6, "short")).toBe("Jun");
  });

  it("returns Persian month names", () => {
    expect(monthName(persianCalendar, 1)).toBe("فروردین");
    expect(monthName(persianCalendar, 6)).toBe("شهریور");
    expect(monthName(persianCalendar, 12)).toBe("اسفند");
  });
});

describe("weekdayNames", () => {
  it("matches DAYS_LIST short titles in the Gregorian path", () => {
    // packages/constants/src/calendar.ts DAYS_LIST is 1-based with value 0..6.
    expect(weekdayNames(gregorianCalendar, "short", 0)).toEqual(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]);
  });

  it("rotates to match weekStartsOn", () => {
    expect(weekdayNames(gregorianCalendar, "short", 1)[0]).toBe("Mon");
    expect(weekdayNames(gregorianCalendar, "short", 6)[0]).toBe("Sat");
  });

  it("returns Persian weekday names", () => {
    const names = weekdayNames(persianCalendar, "long", 6);
    expect(names).toHaveLength(7);
    expect(names[0]).toBe("شنبه");
  });
});

describe("isWeekend", () => {
  it("treats Saturday and Sunday as the Gregorian weekend", () => {
    // 2025-06-14 Sat, 2025-06-15 Sun, 2025-06-16 Mon
    expect(isWeekend(g(2025, 5, 14), 0)).toBe(true);
    expect(isWeekend(g(2025, 5, 15), 0)).toBe(true);
    expect(isWeekend(g(2025, 5, 16), 0)).toBe(false);
  });

  it("is rotation-aware, not a hardcoded Sat/Sun literal", () => {
    // The whole point: the weekend is a function of `weekStartsOn`, so it moves with the user's
    // week. The Iranian week starts on Saturday, so the weekend days are the two at the week
    // boundary — Friday (the last day) and Saturday (the day the week starts).
    expect(isWeekend(g(2025, 5, 13), 6)).toBe(true); // Friday, the last day of the Iranian week
    expect(isWeekend(g(2025, 5, 14), 6)).toBe(true); // Saturday, the day the Iranian week starts
    // The assertion that separates this from the `[0, 6]` literal: Sunday is mid-week here.
    expect(isWeekend(g(2025, 5, 15), 6)).toBe(false);
  });

  it("does not read the day's index off the Gregorian week convention", () => {
    // 2024-08-22 is a Thursday in the Gregorian week convention, and a Thursday regardless of
    // calendar system — the point is that the answer depends on weekStartsOn, not on a literal.
    expect(isWeekend(g(2024, 7, 22), 0)).toBe(false);
    expect(isWeekend(g(2024, 7, 22), 4)).toBe(true);
  });
});
