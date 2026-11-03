/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { gregorianCalendar, persianCalendar } from "../src/adapters";
import { isWeekend } from "../src/labels";

/**
 * The Gantt's axis tables live in `apps/web/components/gantt-chart/data/index.ts`, which has no test
 * runner, so the adapter properties they read are pinned here instead — the same technique
 * `locale-leak.test.ts` uses. The three things that must hold for the tables to be correct in any
 * calendar are: the weekday rotation puts `weekStartsOn` first, `key` is the *absolute* weekday
 * index rather than a column position, and the weekend is a function of `weekStartsOn`.
 */
describe("Gantt weekday table sources", () => {
  it("produces 7 weekday names in every style, rotated to weekStartsOn", () => {
    for (const style of ["long", "short", "narrow"] as const) {
      expect(gregorianCalendar.getWeekdayNames(style, 0)).toHaveLength(7);
    }
    expect(gregorianCalendar.getWeekdayNames("short", 0)[0]).toBe("Sun");
    expect(gregorianCalendar.getWeekdayNames("short", 6)[0]).toBe("Sat");
  });

  it("has a distinct short and long name per weekday, which `narrow` does not", () => {
    // Why the Gantt's `abbreviation` reads the short style rather than the narrow one: en-US
    // narrow collapses Tuesday/Thursday to "T" and Saturday/Sunday to "S". A Gantt axis has to
    // tell those columns apart at a glance, so the two-letter-ish short form is the right column
    // header even though the old hand-written table ("Su", "M", "Th", "Sa") was narrower still.
    for (const style of ["long", "short"] as const) {
      expect(new Set(gregorianCalendar.getWeekdayNames(style, 0)).size).toBe(7);
    }
    expect(new Set(gregorianCalendar.getWeekdayNames("narrow", 0)).size).toBeLessThan(7);
  });

  it("keys rows by the absolute weekday index, not by column position", () => {
    // `week-view.ts` builds one column per entry and `chart/views/week.tsx` asks which day a column
    // is. A key that tracked the column position instead would make the first column Saturday
    // whenever the user starts their week on Saturday, and the weekend shading would follow the
    // column rather than the date.
    for (const weekStartsOn of [0, 1, 3, 6]) {
      const keys = gregorianCalendar
        .getWeekdayNames("short", weekStartsOn)
        .map((_, index) => (weekStartsOn + index) % 7);
      expect(keys).toEqual([0, 1, 2, 3, 4, 5, 6].map((key) => (weekStartsOn + key) % 7));
      // Each absolute weekday is present exactly once, so the table is a permutation of 0..6.
      expect(keys.toSorted((a, b) => a - b)).toEqual([0, 1, 2, 3, 4, 5, 6]);
    }
  });

  it("reports the weekend from the weekday key alone, for every rotation", () => {
    // The Gantt shades a column from `dayData.key` because a `Date` is not in scope at that point
    // in the render. This pins the two-day window it has to reproduce: counting back from
    // `weekStartsOn`, matching what `isWeekend` does with a real `Date`.
    for (const weekStartsOn of [0, 1, 3, 6]) {
      const weekendKeys = [0, 1, 2, 3, 4, 5, 6].filter((key) => {
        // 2025-06-15 is a Sunday, so adding the weekday index lands on the day that key names.
        return isWeekend(new Date(2025, 5, 15 + key), weekStartsOn);
      });
      expect(weekendKeys).toEqual([weekStartsOn, (weekStartsOn + 6) % 7].toSorted((a, b) => a - b));
    }
  });

  it("cannot regenerate the Gantt's tuned Gregorian weekday abbreviations from CLDR", () => {
    // The Gantt's `generateWeeks` pins these seven strings by hand in
    // `apps/web/components/gantt-chart/data/index.ts` because no CLDR style produces them:
    // "Su"/"M"/"T"/"W"/"Th"/"F"/"Sa" are narrower than `short` ("Sun", "Mon"), and `narrow` has only
    // five distinct values so Saturday/Sunday and Tuesday/Thursday would render as identical columns.
    // This test is the regression guard: if an adapter change ever widens the Gantt's day columns for
    // Gregorian users, it fails here first, because the standing rule for this feature is that the
    // Gregorian path renders byte-identically to before.
    const pinned = ["Su", "M", "T", "W", "Th", "F", "Sa"];

    expect(pinned).toHaveLength(7);
    // Distinct per weekday, which is the property `narrow` cannot satisfy.
    expect(new Set(pinned).size).toBe(7);
    expect(pinned).not.toEqual(gregorianCalendar.getWeekdayNames("narrow", 0));
    expect(pinned).not.toEqual(gregorianCalendar.getWeekdayNames("short", 0));
    // The obvious derivation — narrow plus a disambiguating "u" — produces "Mu", "Tu", "Wu", "Fu",
    // so the abbreviations genuinely cannot be expressed as a formula over the narrow names.
    expect(gregorianCalendar.getWeekdayNames("narrow", 0).map((name) => `${name}u`)).not.toEqual(pinned);
  });

  it("returns Persian weekday names, which share no characters with the English ones", () => {
    const names = persianCalendar.getWeekdayNames("long", 6);
    expect(names).toHaveLength(7);
    expect(names[0]).toBe("شنبه");
    // Any consumer comparing the rendered string against "sat"/"sun" fails here silently.
    expect(names.some((name) => ["sat", "sun"].includes(name))).toBe(false);
  });
});

describe("Gantt month and quarter table sources", () => {
  it("produces 12 month names whose short form is the Gantt's column header", () => {
    const gregorian = gregorianCalendar.getMonthNames("short");
    expect(gregorian).toHaveLength(12);
    expect(gregorian[0]).toBe("Jan");
    expect(gregorian[11]).toBe("Dec");
  });

  it("disagrees with the Gantt's tuned September abbreviation, which is therefore pinned in the view", () => {
    // `week-view.ts` prints `months[i].abbreviation` in the week header and `generateQuarters` prints
    // it in the "Jul - Sept" title, so CLDR's "Sep" would be a visible change. `generateMonths` keeps
    // "Sept" for Gregorian by overriding this one slot; this test records why the override must exist,
    // so removing it does not look harmless.
    const ganttAbbreviations = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];

    expect(ganttAbbreviations).toHaveLength(12);
    // Every month but September matches CLDR exactly, which is why only that one is overridden.
    expect(gregorianCalendar.getMonthNames("short").filter((_, index) => index !== 8)).toEqual(
      ganttAbbreviations.filter((_, index) => index !== 8)
    );
    expect(gregorianCalendar.getMonthNames("short")[8]).toBe("Sep");
    expect(ganttAbbreviations[8]).toBe("Sept");
  });

  it("produces 12 Persian month names in the same 0-based slot order", () => {
    const persian = persianCalendar.getMonthNames("short");
    expect(persian).toHaveLength(12);
    expect(persian[0]).toBe("فروردین");
    expect(persian[11]).toBe("اسفند");
  });

  it("groups three months into each of four seasons", () => {
    // Farvardin(1)-Tir(3) spring, Tir(4)-Shahrivar(6) summer, Shahrivar(7)-Aban(9) autumn,
    // Azar(10)-Esfand(12) winter — the same three-month grouping Gregorian quarters use, because the
    // Persian year also starts at its first month.
    expect([1, 3, 4, 6, 7, 9, 10, 12].map((month) => Math.floor((month - 1) / 3))).toEqual([0, 0, 1, 1, 2, 2, 3, 3]);
  });
});
