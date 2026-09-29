/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { gregorianCalendar } from "../src/adapters/gregorian";

describe("gregorianCalendar", () => {
  it("reports parts for a known date", () => {
    const date = new Date(2025, 5, 15); // 15 June 2025
    expect(gregorianCalendar.toParts(date)).toEqual({ year: 2025, month: 6, day: 15 });
  });

  it("round-trips parts back to the same local day", () => {
    for (let i = 0; i < 400; i++) {
      const date = new Date(2000, 0, 1 + i * 3);
      const parts = gregorianCalendar.toParts(date);
      const back = gregorianCalendar.fromParts(parts.year, parts.month, parts.day);
      expect(back.getFullYear()).toBe(date.getFullYear());
      expect(back.getMonth()).toBe(date.getMonth());
      expect(back.getDate()).toBe(date.getDate());
    }
  });

  it("returns local midnight from fromParts", () => {
    const date = gregorianCalendar.fromParts(2025, 6, 15);
    expect(date.getHours()).toBe(0);
    expect(date.getMinutes()).toBe(0);
    expect(date.getSeconds()).toBe(0);
  });

  it("reports month lengths, including leap February", () => {
    expect(gregorianCalendar.getMonthLength(2025, 2)).toBe(28);
    expect(gregorianCalendar.getMonthLength(2024, 2)).toBe(29);
    expect(gregorianCalendar.getMonthLength(2025, 1)).toBe(31);
    expect(gregorianCalendar.getMonthLength(2025, 4)).toBe(30);
  });

  it("produces a 42-entry grid regardless of month", () => {
    expect(gregorianCalendar.getMonthGrid(2025, 6, 0)).toHaveLength(42);
    expect(gregorianCalendar.getMonthGrid(2025, 2, 0)).toHaveLength(42);
    expect(gregorianCalendar.getMonthGrid(2025, 6, 6)).toHaveLength(42);
  });

  it("pads the grid so weekStartsOn sets the first column", () => {
    // 1 June 2025 is a Sunday, so with weekStartsOn=0 the grid opens on that very day.
    const sundayFirst = gregorianCalendar.getMonthGrid(2025, 6, 0);
    expect(sundayFirst[0].getDate()).toBe(1);

    // With weekStartsOn=1 (Monday) the grid opens on the preceding Monday, 26 May 2025.
    const mondayFirst = gregorianCalendar.getMonthGrid(2025, 6, 1);
    expect(mondayFirst[0].getMonth()).toBe(4); // May
    expect(mondayFirst[0].getDate()).toBe(26);
  });

  it("steps months across a year boundary", () => {
    expect(gregorianCalendar.addMonths({ year: 2025, month: 12 }, 1)).toEqual({ year: 2026, month: 1 });
    expect(gregorianCalendar.addMonths({ year: 2025, month: 1 }, -1)).toEqual({ year: 2024, month: 12 });
    expect(gregorianCalendar.addMonths({ year: 2025, month: 6 }, 14)).toEqual({ year: 2026, month: 8 });
  });

  it("returns the first of the month from getMonthStart", () => {
    const start = gregorianCalendar.getMonthStart({ year: 2025, month: 6 });
    expect(start.getFullYear()).toBe(2025);
    expect(start.getMonth()).toBe(5);
    expect(start.getDate()).toBe(1);
  });

  it("formats with date-fns-equivalent output", () => {
    const date = new Date(2025, 5, 15);
    expect(gregorianCalendar.format(date, { year: "numeric", month: "long", day: "numeric" })).toBe("June 15, 2025");
    expect(gregorianCalendar.format(date, { month: "short", day: "numeric" })).toBe("Jun 15");
    expect(gregorianCalendar.format(date, { weekday: "long", year: "numeric", month: "long", day: "numeric" })).toBe(
      "Sunday, June 15, 2025"
    );
  });

  it("lists 12 month names and 7 weekday names", () => {
    expect(gregorianCalendar.getMonthNames("long")).toHaveLength(12);
    expect(gregorianCalendar.getMonthNames("short")[0]).toBe("Jan");
    expect(gregorianCalendar.getMonthNames("long")[5]).toBe("June");
    expect(gregorianCalendar.getWeekdayNames("short", 0)).toHaveLength(7);
    expect(gregorianCalendar.getWeekdayNames("short", 0)[0]).toBe("Sun");
  });

  it("rotates weekday names to match weekStartsOn", () => {
    expect(gregorianCalendar.getWeekdayNames("short", 1)[0]).toBe("Mon");
    expect(gregorianCalendar.getWeekdayNames("short", 6)[0]).toBe("Sat");
  });

  it("is always supported", () => {
    expect(gregorianCalendar.isSupported()).toBe(true);
  });
});
