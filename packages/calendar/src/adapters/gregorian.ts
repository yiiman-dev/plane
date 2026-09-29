/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { addDays, format as formatWithTokens, getDaysInMonth, startOfMonth } from "date-fns";
import type { CalendarAdapter, CalendarDateParts, CalendarFormatOptions, CalendarMonthParts } from "../types";

/** Fixed 6-week grid height, so the picker never changes size as the user pages through months. */
const GRID_CELLS = 42;

const MONTHS_PER_YEAR = 12;

const WEEKDAY_TOKENS = { long: "EEEE", short: "EEE", narrow: "EEEEE" } as const;
const MONTH_TOKENS = { long: "MMMM", short: "MMM", narrow: "MMMMM" } as const;
const YEAR_TOKENS = { numeric: "yyyy", "2-digit": "yy" } as const;

/**
 * Maps the adapter's semantic format options onto `date-fns` tokens. The Persian adapter cannot use
 * this — its tokens have no Persian equivalent — so the two formatters stay separate on purpose.
 *
 * The option values are `Intl.DateTimeFormat` names (`"long"`, `"numeric"`, …), not date-fns
 * tokens, so each one has to be translated rather than passed through.
 */
export const toDatePartsToken = (options: CalendarFormatOptions): string => {
  // Day and month sit side by side ("June 15"), the trailing year is set off by a comma
  // ("June 15, 2025"), and a leading weekday is a separate clause ("Sunday, June 15, 2025").
  const dayAndMonth: string[] = [];
  if (options.month) {
    if (options.month === "numeric") dayAndMonth.push("M");
    else if (options.month === "2-digit") dayAndMonth.push("MM");
    else dayAndMonth.push(MONTH_TOKENS[options.month]);
  }
  if (options.day) dayAndMonth.push(options.day === "2-digit" ? "dd" : "d");

  const tokens: string[] = [];
  if (options.year) tokens.push(`${dayAndMonth.join(" ")}, ${YEAR_TOKENS[options.year]}`.replace(/^, /, ""));
  else tokens.push(...dayAndMonth);

  // The guard tests the *option bag*, not the assembled tokens, so a bare `weekday` counts as a
  // present field instead of being silently dropped. An option bag with no date parts at all would
  // make date-fns throw, so it falls back to the picker trigger's shape.
  if (tokens.length === 0) return options.weekday ? WEEKDAY_TOKENS[options.weekday] : "MMM dd, yyyy";

  const body = tokens.join(" ");
  return options.weekday ? `${WEEKDAY_TOKENS[options.weekday]}, ${body}` : body;
};

export const gregorianCalendar: CalendarAdapter = {
  system: "gregorian",
  // Declared for the adapter contract, not enforced: every `format` below omits the locale argument,
  // so output follows the host system locale, exactly as `packages/utils/src/datetime.ts` does today.
  // Pinning `en-US` here would introduce output drift relative to current product behavior, which is
  // the one thing this reference adapter exists to prevent. The Persian adapter does use its own locale.
  locale: "en-US",

  toParts: (date: Date): CalendarDateParts => ({
    year: date.getFullYear(),
    // date-fns and `Date` are 0-based; the adapter contract is 1-based throughout.
    month: date.getMonth() + 1,
    day: date.getDate(),
  }),

  fromParts: (year: number, month: number, day: number): Date => new Date(year, month - 1, day),

  getMonthLength: (year: number, month: number): number => getDaysInMonth(new Date(year, month - 1, 1)),

  getMonthGrid: (year: number, month: number, weekStartsOn = 0): Date[] => {
    const first = startOfMonth(new Date(year, month - 1, 1));
    // `startOfMonth(...).getDay()` is 0=Sunday, which is exactly the `weekStartsOn` numbering.
    const leading = (first.getDay() - weekStartsOn + 7) % 7;
    const gridStart = addDays(first, -leading);
    return Array.from({ length: GRID_CELLS }, (_, index) => addDays(gridStart, index));
  },

  addMonths: ({ year, month }: CalendarMonthParts, delta: number): CalendarMonthParts => {
    // Work in an absolute month index so the year carries without a modulo.
    const zeroBased = year * MONTHS_PER_YEAR + (month - 1) + delta;
    return {
      year: Math.floor(zeroBased / MONTHS_PER_YEAR),
      month: (((zeroBased % MONTHS_PER_YEAR) + MONTHS_PER_YEAR) % MONTHS_PER_YEAR) + 1,
    };
  },

  getMonthStart: ({ year, month }: CalendarMonthParts): Date => new Date(year, month - 1, 1),

  format: (date: Date, options: CalendarFormatOptions = {}): string =>
    formatWithTokens(date, toDatePartsToken(options)),

  getMonthNames: (style: "long" | "short" | "narrow"): string[] =>
    Array.from({ length: MONTHS_PER_YEAR }, (_, index) =>
      formatWithTokens(new Date(2021, index, 1), style === "long" ? "MMMM" : style === "short" ? "MMM" : "MMMMM")
    ),

  getWeekdayNames: (style: "long" | "short" | "narrow", weekStartsOn = 0): string[] => {
    // 1 Aug 2021 was a Sunday, so stepping forward 7 days from it covers every weekday in order; the
    // rotation below then moves `weekStartsOn` to the front.
    const token = style === "long" ? "EEEE" : style === "short" ? "EEE" : "EEEEE";
    const knownSunday = new Date(2021, 7, 1);
    const names = Array.from({ length: 7 }, (_, index) => formatWithTokens(addDays(knownSunday, index), token));
    return [...names.slice(weekStartsOn), ...names.slice(0, weekStartsOn)];
  },

  isSupported: (): boolean => true,
};
