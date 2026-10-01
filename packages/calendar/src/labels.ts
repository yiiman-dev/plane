/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { CalendarAdapter } from "./types";

/**
 * A month name for display.
 *
 * `month` is **1-based**, matching what `adapter.toParts` reports — the same convention the whole
 * adapter contract uses. The 0-based `Date.getMonth()` used to index `MONTHS_LIST` is a different
 * number space, and conflating the two is the classic off-by-one in this area.
 */
export const monthName = (
  adapter: CalendarAdapter,
  month: number,
  style: "long" | "short" | "narrow" = "long"
): string => adapter.getMonthNames(style)[month - 1] ?? "";

/**
 * 7 weekday names, rotated so index 0 is `weekStartsOn` (0 = Sunday). Callers that render a column
 * per weekday use this directly instead of rotating `DAYS_LIST` themselves.
 */
export const weekdayNames = (
  adapter: CalendarAdapter,
  style: "long" | "short" | "narrow" = "short",
  weekStartsOn = 0
): string[] => adapter.getWeekdayNames(style, weekStartsOn);

/**
 * The two days at the boundary of the user's week: the day the week starts and the day before it.
 *
 * This exists because four call sites hardcode `[0, 6].includes(date.getDay())` — Saturday/Sunday —
 * and one of them compares the English strings `"sat"` / `"sun"`. An Iranian week starts on Saturday
 * and ends on Friday, so the weekend is a function of `weekStartsOn`, not a constant.
 *
 * Counting *back* from `weekStartsOn` (rather than forward from it) is what keeps this
 * byte-compatible with the `[0, 6]` literal at the default `weekStartsOn` of 0, where the boundary
 * days are Saturday and Sunday.
 */
export const isWeekend = (date: Date, weekStartsOn = 0): boolean => {
  // `getDay()` is 0 = Sunday, so this is 0 when `date` is the day the week starts and 1 for the day
  // before it. Anything further back belongs to the previous week.
  const daysBeforeWeekStart = (weekStartsOn - date.getDay() + 7) % 7;
  return daysBeforeWeekStart < 2;
};
