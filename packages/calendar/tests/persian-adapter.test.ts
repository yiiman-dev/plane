/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { gregorianCalendar } from "../src/adapters/gregorian";
import { isPersianCalendarSupported, persianCalendar } from "../src/adapters/persian";

/** Builds a local-midnight Gregorian Date, avoiding the UTC shift of `new Date("2024-08-22")`. */
const g = (year: number, monthIndex: number, day: number) => new Date(year, monthIndex, day);

describe("persianCalendar", () => {
  it("reports Persian parts for known Gregorian dates", () => {
    // 22 August 2024 is 1 Shahrivar 1403.
    expect(persianCalendar.toParts(g(2024, 7, 22))).toEqual({ year: 1403, month: 6, day: 1 });
    // 20 March 2024 is 1 Farvardin 1403 — Nowruz.
    expect(persianCalendar.toParts(g(2024, 2, 20))).toEqual({ year: 1403, month: 1, day: 1 });
    // 21 March 2025 is 1 Farvardin 1404.
    expect(persianCalendar.toParts(g(2025, 2, 21))).toEqual({ year: 1404, month: 1, day: 1 });
  });

  it("converts Persian parts back to the right Gregorian day", () => {
    expect(persianCalendar.fromParts(1403, 6, 1)).toEqual(g(2024, 7, 22));
    expect(persianCalendar.fromParts(1403, 1, 1)).toEqual(g(2024, 2, 20));
    expect(persianCalendar.fromParts(1404, 1, 1)).toEqual(g(2025, 2, 21));
  });

  it("returns local midnight from fromParts", () => {
    const date = persianCalendar.fromParts(1403, 6, 1);
    expect(date.getHours()).toBe(0);
    expect(date.getMinutes()).toBe(0);
    expect(date.getSeconds()).toBe(0);
  });

  it("round-trips 1000 dates without drifting", () => {
    for (let i = 0; i < 1000; i++) {
      const date = new Date(2000, 0, 1 + i * 4); // spans roughly 2000–2011 Gregorian
      const parts = persianCalendar.toParts(date);
      const back = persianCalendar.fromParts(parts.year, parts.month, parts.day);
      expect(back.getFullYear()).toBe(date.getFullYear());
      expect(back.getMonth()).toBe(date.getMonth());
      expect(back.getDate()).toBe(date.getDate());
    }
  });

  it("reports Persian month lengths, including the leap Esfand", () => {
    // The first six months have 31 days, the next five have 30.
    for (let month = 1; month <= 6; month++) {
      expect(persianCalendar.getMonthLength(1403, month)).toBe(31);
    }
    for (let month = 7; month <= 11; month++) {
      expect(persianCalendar.getMonthLength(1403, month)).toBe(30);
    }
    // Esfand is 30 days in a leap year and 29 otherwise.
    expect(persianCalendar.getMonthLength(1403, 12)).toBe(30);
    expect(persianCalendar.getMonthLength(1404, 12)).toBe(29);
  });

  it("converts the last day of each Persian month exactly", () => {
    for (let month = 1; month <= 12; month++) {
      const length = persianCalendar.getMonthLength(1403, month);
      const lastDay = persianCalendar.fromParts(1403, month, length);
      expect(persianCalendar.toParts(lastDay)).toEqual({ year: 1403, month, day: length });
    }
  });

  it("produces a 42-entry grid", () => {
    expect(persianCalendar.getMonthGrid(1403, 6, 6)).toHaveLength(42);
    expect(persianCalendar.getMonthGrid(1403, 12, 0)).toHaveLength(42);
  });

  it("walks the whole month in order with no gaps or repeats", () => {
    const grid = persianCalendar.getMonthGrid(1403, 6, 6);
    for (let i = 1; i < grid.length; i++) {
      const previous = grid[i - 1].getTime();
      const current = grid[i].getTime();
      // 86_400_000 is one day; allow a 1-hour margin for any DST shift mid-run.
      const diffHours = (current - previous) / 3_600_000;
      expect(diffHours).toBeGreaterThan(23);
      expect(diffHours).toBeLessThan(25);
    }
  });

  it("pads the grid so weekStartsOn sets the first column", () => {
    // 1 Farvardin 1403 (20 Mar 2024) was a *Wednesday* — `Date.getDay()` 3, not 4. Saturday-start
    // therefore shifts back 4 days to 16 March, which is 26 Esfand 1402 and still in 2024.
    const saturdayFirst = persianCalendar.getMonthGrid(1403, 1, 6);
    expect(persianCalendar.toParts(saturdayFirst[0])).toEqual({ year: 1402, month: 12, day: 26 });
    expect(saturdayFirst[0].getFullYear()).toBe(2024);
    // Wednesday-start puts Nowruz itself in the first column.
    const wednesdayFirst = persianCalendar.getMonthGrid(1403, 1, 3);
    expect(persianCalendar.toParts(wednesdayFirst[0])).toEqual({ year: 1403, month: 1, day: 1 });
  });

  it("steps months across the Persian new year", () => {
    expect(persianCalendar.addMonths({ year: 1403, month: 12 }, 1)).toEqual({ year: 1404, month: 1 });
    expect(persianCalendar.addMonths({ year: 1403, month: 1 }, -1)).toEqual({ year: 1402, month: 12 });
    expect(persianCalendar.addMonths({ year: 1403, month: 6 }, 12)).toEqual({ year: 1404, month: 6 });
  });

  it("returns 1 Farvardin from getMonthStart", () => {
    const start = persianCalendar.getMonthStart({ year: 1403, month: 6 });
    expect(persianCalendar.toParts(start)).toEqual({ year: 1403, month: 6, day: 1 });
  });

  it("formats in Persian digits", () => {
    const date = g(2024, 7, 22);
    const formatted = persianCalendar.format(date, { year: "numeric", month: "long", day: "numeric" });
    // fa-IR with the persian calendar yields Persian digits and a Persian month name, composed by
    // `Intl` itself — day-first, no comma. 22 August 2024 is Persian *1* Shahrivar, so the Persian
    // day is ۱; the Gregorian 22 never appears.
    expect(formatted).toBe("۱ شهریور ۱۴۰۳");
    expect(formatted).toContain("۱۴۰۳");
    expect(formatted).toContain("شهریور");
  });

  it("lists Persian month and weekday names", () => {
    const months = persianCalendar.getMonthNames("long");
    expect(months).toHaveLength(12);
    expect(months[0]).toBe("فروردین");
    expect(months[5]).toBe("شهریور");
    expect(months[11]).toBe("اسفند");

    // fa-IR has no abbreviated weekday form: "short" is the full name. Only "narrow" is the
    // single letter, so that is where "ش" (Saturday) lives.
    const shortWeekdays = persianCalendar.getWeekdayNames("short", 6);
    expect(shortWeekdays).toHaveLength(7);
    expect(shortWeekdays[0]).toBe("شنبه");

    const narrowWeekdays = persianCalendar.getWeekdayNames("narrow", 6);
    expect(narrowWeekdays[0]).toBe("ش");
  });

  it("reports support based on the host Intl implementation", () => {
    expect(persianCalendar.isSupported()).toBe(isPersianCalendarSupported());
  });

  it("measures Esfand in the last supported year without probing out of range", () => {
    // Regression: differencing Esfand against 1 Farvardin of year+1 asks for a year past CLDR's
    // exact range, where the range guard answers with a placeholder Gregorian year. That turned the
    // length into a large negative number. The length must still be a real month length.
    const esfand = persianCalendar.getMonthLength(1633, 12);
    expect(esfand === 29 || esfand === 30).toBe(true);
    // The last day must convert back to exactly that day.
    expect(persianCalendar.toParts(persianCalendar.fromParts(1633, 12, esfand))).toEqual({
      year: 1633,
      month: 12,
      day: esfand,
    });
  });

  it("formats every valid combination of CalendarFormatOptions without throwing", () => {
    // Regression: `format` shipped throwing on every call. Task 2 caught it only because a test
    // exercised it, so the guard is an exhaustive sweep of the option bag's real values rather than
    // one hand-picked combination — a future field added to `CalendarFormatOptions` and forwarded
    // to `Intl` wrong would otherwise go unnoticed. `Intl` rejects an unknown value by throwing.
    const date = g(2024, 7, 22); // 1 Shahrivar 1403
    const years = ["numeric", "2-digit"] as const;
    const months = ["long", "short", "numeric", "2-digit"] as const;
    const days = ["numeric", "2-digit"] as const;
    const weekdays = ["long", "short", "narrow"] as const;

    let combinations = 0;
    for (const year of years) {
      for (const month of months) {
        for (const day of days) {
          for (const weekday of weekdays) {
            combinations++;
            const formatted = persianCalendar.format(date, { year, month, day, weekday });
            expect(typeof formatted).toBe("string");
            expect(formatted.length).toBeGreaterThan(0);
          }
        }
      }
    }
    // Also each field alone, since a combination can be valid while a lone field is not.
    for (const option of [
      { year: "numeric" as const },
      { year: "2-digit" as const },
      { month: "long" as const },
      { month: "short" as const },
      { month: "numeric" as const },
      { month: "2-digit" as const },
      { day: "numeric" as const },
      { day: "2-digit" as const },
      { weekday: "long" as const },
      { weekday: "short" as const },
      { weekday: "narrow" as const },
    ]) {
      expect(persianCalendar.format(date, option).length).toBeGreaterThan(0);
    }
    // And the empty bag, which has its own fallback path.
    expect(persianCalendar.format(date).length).toBeGreaterThan(0);
    expect(combinations).toBe(48);
  });

  it("rejects non-integer parts instead of letting NaN reach the search", () => {
    // `NaN < MIN` and `NaN > MAX` are both false, so a range-only guard lets `NaN` through to the
    // seed and `Intl` then throws `RangeError: Invalid time value` from inside a render path.
    // `fromParts` must degrade to the same placeholder an out-of-range year gets, never throw.
    expect(() => persianCalendar.fromParts(Number.NaN, 1, 1)).not.toThrow();
    expect(() => persianCalendar.fromParts(1403.5, 1, 1)).not.toThrow();
    expect(() => persianCalendar.fromParts(1403, 1.5, 1)).not.toThrow();
    expect(() => persianCalendar.fromParts(1403, 1, Number.NaN)).not.toThrow();
    expect(() => persianCalendar.fromParts(Number.POSITIVE_INFINITY, 1, 1)).not.toThrow();

    // A rejected input must not read back as the input that was asked for — the same property the
    // out-of-range test above asserts. `NaN` degrades all the way to `NaN` parts (no invented
    // year); a fractional year falls out of range and gets the placeholder, so it is not month 1
    // of 1403 the way a silently-accepted float would be.
    expect(persianCalendar.toParts(persianCalendar.fromParts(Number.NaN, 1, 1)).year).toBeNaN();
    expect(persianCalendar.toParts(persianCalendar.fromParts(1403.5, 1, 1)).month).not.toBe(1);
  });

  it("never reports a zero or negative month length", () => {
    // `getMonthLength` feeds callers that divide by it, so a 0 fallback would surface as `Infinity`
    // rather than as a wrong-but-finite month. Probe across the whole supported range, and the
    // out-of-range years too — those make both difference probes return the same guard placeholder,
    // which is exactly how a 0 used to escape.
    for (const year of [1178, 1300, 1403, 1500, 1633, 1177, 1634, 9999]) {
      for (let month = 1; month <= 12; month++) {
        const length = persianCalendar.getMonthLength(year, month);
        expect(length).toBeGreaterThanOrEqual(28);
        expect(length).toBeLessThanOrEqual(31);
      }
    }
  });

  it("degrades to NaN parts on an Invalid Date like the Gregorian adapter does", () => {
    // Both adapters share one interface; the picker calls through it. A render path must not throw,
    // and the two must not diverge for the same input.
    const invalid = new Date(Number.NaN);
    expect(() => persianCalendar.toParts(invalid)).not.toThrow();
    const persian = persianCalendar.toParts(invalid);
    const gregorian = gregorianCalendar.toParts(invalid);
    expect(persian.year).toBeNaN();
    expect(persian.month).toBeNaN();
    expect(persian.day).toBeNaN();
    expect(gregorian).toEqual(persian);
  });

  it("refuses Persian years outside CLDR's exact range instead of extrapolating", () => {
    // Out of range the adapter must not claim a confident answer: `Intl` would happily extrapolate
    // and hand back a plausible-but-wrong date. The guard returns a placeholder that does not read
    // back as the year that was asked for.
    expect(persianCalendar.toParts(persianCalendar.fromParts(9999, 1, 1)).year).not.toBe(9999);
    expect(persianCalendar.toParts(persianCalendar.fromParts(500, 1, 1)).year).not.toBe(500);
  });
});

describe("adapter interop", () => {
  it("agrees on the same day from both directions", () => {
    for (let i = 0; i < 200; i++) {
      const date = new Date(2020, 0, 1 + i * 7);
      const persian = persianCalendar.toParts(date);
      const gregorian = gregorianCalendar.toParts(persianCalendar.fromParts(persian.year, persian.month, persian.day));
      expect(gregorian).toEqual(gregorianCalendar.toParts(date));
    }
  });
});
