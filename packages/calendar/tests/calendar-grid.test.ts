/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { generateCalendarData } from "@plane/utils";
import { persianCalendar } from "../src/adapters";

const fromPersian = (y: number, m: number, d: number) => persianCalendar.fromParts(y, m, d);

describe("generateCalendarData", () => {
  it("is byte-identical in Gregorian when no system is passed", () => {
    const payload = generateCalendarData(null, new Date(2025, 5, 1), 0);
    const month = payload["y-2025"]["m-5"];
    const weeks = Object.keys(month).toSorted();
    expect(weeks).toHaveLength(5); // June 2025 has 5 weeks from a Sunday start
    // Keys stay Gregorian yyyy-MM-dd — they are API payload, not display.
    const firstDay = Object.keys(month[weeks[0]])[0];
    expect(firstDay).toMatch(/^2025-06-/);
    // Each cell keeps a Gregorian Date.
    expect(month[weeks[0]][firstDay].date.getMonth()).toBe(5);
  });

  it("produces a Persian month when asked", () => {
    const payload = generateCalendarData(null, fromPersian(1403, 6, 1), 6, "persian");
    // 1 Shahrivar 1403 is 22 August 2024. The payload keys stay Gregorian — they are what
    // `issue_calendar_view.store.ts` and the API both read — so the bucket is August 2024.
    const month = payload["y-2024"]["m-7"];
    expect(month).toBeDefined();
    const days = Object.values(month).flatMap((w) => Object.keys(w));
    expect(days).toContain("2024-08-22");
  });

  it("uses the Persian month length, so Shahrivar has 31 cells not 30", () => {
    const payload = generateCalendarData(null, fromPersian(1403, 6, 1), 6, "persian");
    const month = payload["y-2024"]["m-7"];
    // A Persian month straddles the Gregorian month boundary, so the count cannot be read off the
    // Gregorian month. Count the cells the adapter places in Shahrivar 1403 instead: 31 means the
    // generator asked the adapter for the month length rather than a Gregorian table lookup keyed by
    // the Persian month index (which would have given 31 for a different reason — see below).
    const inMonth = Object.values(month)
      .flatMap((w) => Object.values(w))
      .filter((c) => {
        const p = persianCalendar.toParts(c.date);
        return p.year === 1403 && p.month === 6;
      });
    expect(inMonth.length).toBe(31);
    // ...and the last one really is 31 Shahrivar = 21 September 2024, so the grid spans the whole
    // month rather than a Gregorian August that stops at 31 August.
    const last = inMonth[inMonth.length - 1].date;
    expect([last.getMonth(), last.getDate()]).toEqual([8, 21]);
  });

  it("handles the leap Esfand, which is 30 days", () => {
    const esfandStart = fromPersian(1403, 12, 1);
    // 1 Esfand 1403 is 19 February 2025 (the brief's "20 Feb – 21 Mar 2024" is Esfand 1402), and
    // 1403 is a leap year, so the month is 30 days and crosses the Gregorian month boundary.
    expect(esfandStart.getFullYear()).toBe(2025);
    const payload = generateCalendarData(null, esfandStart, 6, "persian");
    const all = Object.values(payload)
      .flatMap((y) => Object.values(y))
      .flatMap((m) => Object.values(m))
      .flatMap((w) => Object.values(w));
    const esfandDays = all.filter((c) => {
      const p = persianCalendar.toParts(c.date);
      return p.year === 1403 && p.month === 12;
    });
    expect(esfandDays.length).toBe(30);
    // The grid must not stop at the end of February, which is what a Gregorian month length would do.
    expect(esfandDays.some((c) => c.date.getMonth() === 2)).toBe(true);
  });
});
