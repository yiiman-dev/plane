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
 * Maps the adapter's semantic format options onto `date-fns` tokens.
 *
 * The Persian adapter reuses the *option-bag semantics* established here — which fields exist, how
 * `weekday` behaves as a leading clause, and what `2-digit` means — but must derive its own
 * punctuation and must never pass these token strings to an `Intl`-based formatter. The token
 * vocabulary below is date-fns-specific and has no Persian equivalent.
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
  // `do` after the width digit, never instead of it: `do` alone is the bare ordinal ("15th") and
  // loses the zero padding, so `2-digit` + ordinal is `ddo`.
  if (options.day)
    dayAndMonth.push(options.day === "2-digit" ? (options.dayOrdinal ? "ddo" : "dd") : options.dayOrdinal ? "do" : "d");

  const tokens: string[] = [];
  if (options.year) tokens.push(`${dayAndMonth.join(" ")}, ${YEAR_TOKENS[options.year]}`.replace(/^, /, ""));
  else tokens.push(...dayAndMonth);

  // `tokens` is only ever pushed from a date part, so an empty list means the bag named no date
  // field at all — which would make date-fns throw — and falls back to the picker trigger's shape.
  // A bare `weekday` is a present field, so it returns the weekday rather than being dropped.
  if (tokens.length === 0) return options.weekday ? WEEKDAY_TOKENS[options.weekday] : "MMM dd, yyyy";

  const body = tokens.join(" ");
  return options.weekday ? `${WEEKDAY_TOKENS[options.weekday]}, ${body}` : body;
};

/**
 * The `date-fns` tokens Plane actually passes to {@link toCalendarFormatOptions} today, mapped onto
 * the adapter's semantic options. This is the inverse of {@link toDatePartsToken}: that one turns
 * options into tokens for the Gregorian adapter, this one turns a token a caller wrote into the
 * options an adapter can honour, so a non-Gregorian adapter can respect the caller's intent.
 *
 * Keyed by the whole token string rather than derived by scanning for `M`/`d`/`y` runs. A scanner
 * cannot know that "MM" in `dd/MM/yyyy` is a month but "MMM" is a name, and it would happily accept
 * `"hello"` as a token whose `l` looks like nothing at all — the exact class of silent misreading
 * the explicit table prevents. Only the tokens that reach a call site are listed:
 *
 * - `"MMM dd, yyyy"` — `renderFormattedDate`'s default, and ~60 production call sites that pass no token
 * - `"MMM dd"` — compact form: `renderFormattedDateWithoutYear`, `formatDateRange`, chart axes
 * - `"MMM"`, `"MMM, yyyy"` — `apps/web/components/chart/utils.ts`
 * - `"MMMM dd, yyyy"`, `"MMMM dd"` — long month name, same two shapes
 * - `"dd/MM/yyyy"`, `"MM/dd/yyyy"`, `"yyyy/MM/dd"`, `"yyyy-MM-dd"` — the four date formats the
 *   date pickers ship (`MERGE_TOKENS` in `packages/blocks/src/property-select/date-range-select.tsx`)
 *
 * A token that is absent, or that names a field this table does not cover, maps to `undefined` and
 * the caller falls back — see {@link toCalendarFormatOptions}.
 */
const TOKEN_FORMAT_OPTIONS: Readonly<Record<string, CalendarFormatOptions>> = {
  "MMM dd, yyyy": { year: "numeric", month: "short", day: "numeric" },
  "MMM dd": { month: "short", day: "numeric" },
  "MMM, yyyy": { year: "numeric", month: "short" },
  MMM: { month: "short" },
  "MMMM dd, yyyy": { year: "numeric", month: "long", day: "numeric" },
  "MMMM dd": { month: "long", day: "numeric" },
  "dd/MM/yyyy": { year: "numeric", month: "2-digit", day: "2-digit" },
  "MM/dd/yyyy": { year: "numeric", month: "2-digit", day: "2-digit" },
  "yyyy/MM/dd": { year: "numeric", month: "2-digit", day: "2-digit" },
  "yyyy-MM-dd": { year: "numeric", month: "2-digit", day: "2-digit" },
};

/**
 * The semantic options a `date-fns` format token stands for, or `undefined` when the token names
 * something this table does not cover.
 *
 * Exported (and documented) rather than kept module-private because `@plane/utils` needs it: its
 * `renderFormattedDate` honours the caller's token for every adapter that cannot take tokens itself,
 * which is the only way a Persian render can omit the year a caller asked to omit. The token
 * vocabulary itself stays private — only the whole-token lookup is public, so the table cannot be
 * half-remembered and reimplemented by a caller.
 *
 * @param token a `date-fns` format token, e.g. `"MMM dd"`
 */
export const toCalendarFormatOptions = (token: string): CalendarFormatOptions | undefined =>
  // `Object.hasOwn` rather than a bare index: this table is a plain object, so a caller-supplied
  // token like `"toString"` or `"constructor"` would otherwise resolve to an inherited member.
  Object.hasOwn(TOKEN_FORMAT_OPTIONS, token) ? TOKEN_FORMAT_OPTIONS[token] : undefined;

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
