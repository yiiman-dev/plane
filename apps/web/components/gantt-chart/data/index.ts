/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// types
import type { WeekMonthDataType, ChartDataType, TGanttViews } from "@plane/types";
import { EStartOfTheWeek } from "@plane/types";
// plane utils
import { getCalendarAdapter } from "@plane/blocks/property-select";
import type { CalendarAdapter } from "@plane/blocks/property-select";

/**
 * The default adapter for the axis tables.
 *
 * Every generator below takes an adapter, but defaults to Gregorian so the call sites in
 * `views/week-view.ts`, `views/month-view.ts` and `views/quarter-view.ts` keep compiling while the
 * user's calendar system is still threaded down from the store. Until that happens the Gantt axis
 * renders English names over Gregorian dates — the behaviour every user has today, and no worse.
 * `blocks → calendar` is the dependency edge that lets `apps/web` reach these symbols at all; it
 * deliberately does not depend on `@plane/calendar` itself.
 */
const GREGORIAN_ADAPTER = getCalendarAdapter("gregorian");

/**
 * The seven Gregorian weekday abbreviations the Gantt has always rendered, indexed by the absolute
 * weekday (`Date.getDay()`). An explicit lookup, not a formula: CLDR offers no style that
 * regenerates these. `narrow` is only 5 distinct values — "S" is both Sunday and Saturday, "T" is both
 * Tuesday and Thursday — so Sunday/Saturday and Tuesday/Thursday would render as identical columns.
 * `short` is wider still ("Sun", "Mon"). The originals were hand-tuned to fit the ~60px day columns,
 * and the standing rule for this feature is that the Gregorian path renders byte-identically to before,
 * so they are pinned here rather than derived.
 */
const GREGORIAN_WEEKDAY_ABBREVIATIONS = ["Su", "M", "T", "W", "Th", "F", "Sa"] as const;

/**
 * The one Gregorian month abbreviation CLDR disagrees with: the hand-written table used "Sept" for
 * September, `getMonthNames("short")` gives "Sep". Both `week-view.ts` (the week header, "Sept 2025")
 * and `generateQuarters` (the "Jul - Sept" quarter title) print `abbreviation`, so this is visible.
 * Every other month matches the CLDR short form exactly, which is why this is a single-entry override
 * rather than a second twelve-element table.
 */
const GREGORIAN_SEPTEMBER_ABBREVIATION = "Sept";

/**
 * Seven weekday rows, rotated so column 0 is the user's first day of the week.
 *
 * `key` stays the **absolute** weekday index (`Date.getDay()`'s 0 = Sunday … 6 = Saturday) rather
 * than the column position. Consumers index columns by array position, but the weekend check in
 * `chart/views/week.tsx` has to know which *day* a column is, and a key that tracked the position
 * would report Saturday for the first column the moment the week started on Saturday.
 *
 * `abbreviation` is the CLDR short form for Persian ("شن"), but for Gregorian it stays the hand-tuned
 * table this Gantt has always rendered. The old literals were "Su", "M", "T", "W", "Th", "F", "Sa" —
 * narrower than even the short form, because the Gantt's day columns are ~60px wide and "Sunday" does
 * not fit. CLDR cannot regenerate them: the narrow style collapses to five distinct values ("S" for
 * both Sunday and Saturday, "T" for both Tuesday and Thursday), so two columns would render
 * identically, and the short style is what the table already replaced. Hence the explicit lookup,
 * indexed by the absolute weekday, with the position-independent `key` doing the rotation.
 *
 * Persian has no case and no narrower ASCII form, so its short names are also all CLDR offers.
 */
export const generateWeeks = (
  startOfWeek: EStartOfTheWeek = EStartOfTheWeek.SUNDAY,
  adapter: CalendarAdapter = GREGORIAN_ADAPTER
): WeekMonthDataType[] => {
  const shortTitles = adapter.getWeekdayNames("short", startOfWeek);
  const titles = adapter.getWeekdayNames("long", startOfWeek);

  return shortTitles.map((shortTitle, index) => {
    const key = (startOfWeek + index) % 7;

    return {
      key,
      shortTitle,
      title: titles[index] ?? shortTitle,
      abbreviation: adapter.system === "persian" ? shortTitle : (GREGORIAN_WEEKDAY_ABBREVIATIONS[key] ?? shortTitle),
    };
  });
};

/**
 * Twelve month rows, 0-based to match the `Date.getMonth()` index the Gantt still uses to look a
 * month up (`views/week-view.ts` reads `months[monthAtStartOfTheWeek].abbreviation`). Note the
 * adapter's own month names are **1-based** — `monthName(adapter, 1)` is January — so this is the
 * one place the two number spaces meet, and the 0-based index is deliberate.
 */
export const generateMonths = (adapter: CalendarAdapter = GREGORIAN_ADAPTER): WeekMonthDataType[] => {
  const shortTitles = adapter.getMonthNames("short");
  const titles = adapter.getMonthNames("long");

  return shortTitles.map((shortTitle, index) => ({
    key: index,
    shortTitle,
    title: titles[index] ?? shortTitle,
    // The Gantt's month titles read the short form: the header prints `abbreviation` next to the
    // year ("Jan 2025"), and the short form is what the hand-written table used. September is the
    // one month CLDR abbreviates differently from the old table — "Sep" vs the "Sept" users see in
    // the week header and in the "Jul - Sept" quarter title — so it is restored for Gregorian only.
    abbreviation: adapter.system === "persian" || index !== 8 ? shortTitle : GREGORIAN_SEPTEMBER_ABBREVIATION,
  }));
};

/**
 * Persian season names, in calendar order. These four labels are literals, unlike the month names
 * beside them, which come from the adapter.
 *
 * NOT i18n'd. If a `fa` locale ever covers the Gantt axis, these must move to translation keys —
 * do not assume they went through i18n because they sit next to strings that did.
 */
const PERSIAN_SEASONS = ["بهار", "تابستان", "پاییز", "زمستان"];
const GREGORIAN_QUARTERS = ["Q1", "Q2", "Q3", "Q4"];

/**
 * Four three-month groups. The boundary math is identical in both calendars — `index * 3` into the
 * month rows — because the Persian year also starts at its first month, so Farvardin–Tir is the
 * first group. What differs is the label: a Persian Gantt axis reads "بهار - خرداد" (spring –
 * Khordad), not "Q1", because the Persian year is divided into seasons rather than numbered
 * quarters.
 *
 * The group titles are composed from the adapter's own month names, so the Persian titles follow the
 * calendar rather than a hardcoded transliteration of it.
 */
export const generateQuarters = (adapter: CalendarAdapter = GREGORIAN_ADAPTER): WeekMonthDataType[] => {
  const monthRows = generateMonths(adapter);
  const labels = adapter.system === "persian" ? PERSIAN_SEASONS : GREGORIAN_QUARTERS;

  return labels.map((label, index) => ({
    key: index,
    shortTitle: label,
    title: `${monthRows[index * 3]?.abbreviation ?? ""} - ${monthRows[index * 3 + 2]?.abbreviation ?? ""}`,
    abbreviation: label,
  }));
};

// context data
export const VIEWS_LIST: ChartDataType[] = [
  {
    key: "week",
    i18n_title: "common.week",
    data: {
      startDate: new Date(),
      currentDate: new Date(),
      endDate: new Date(),
      approxFilterRange: 4, // it will preview week dates with weekends highlighted with 1 week limitations ex: title (Wed 1, Thu 2, Fri 3)
      dayWidth: 60,
    },
  },
  {
    key: "month",
    i18n_title: "common.month",
    data: {
      startDate: new Date(),
      currentDate: new Date(),
      endDate: new Date(),
      approxFilterRange: 6, // it will preview monthly all dates with weekends highlighted with no limitations ex: title (1, 2, 3)
      dayWidth: 20,
    },
  },
  {
    key: "quarter",
    i18n_title: "common.quarter",
    data: {
      startDate: new Date(),
      currentDate: new Date(),
      endDate: new Date(),
      approxFilterRange: 24, // it will preview week starting dates all months data and there is 3 months limitation for preview ex: title (2, 9, 16, 23, 30)
      dayWidth: 5,
    },
  },
];

export const currentViewDataWithView = (view: TGanttViews = "month") =>
  VIEWS_LIST.find((_viewData) => _viewData.key === view);
