/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { addDays, differenceInCalendarDays, startOfDay } from "date-fns";
import type { CalendarAdapter, CalendarDateParts, CalendarFormatOptions, CalendarMonthParts } from "../types";

/** Fixed 6-week grid height, matching the Gregorian adapter. */
const GRID_CELLS = 42;

const MONTHS_PER_YEAR = 12;

const PERSIAN_LOCALE = "fa-IR-u-ca-persian";

/**
 * The Gregorian year a Persian year is roughly 621 years ahead of, used to seed the inverse
 * conversion. Farvardin 1 (Nowruz) lands on 20 or 21 March, so Persian year Y begins in Gregorian
 * year Y + 621.
 */
const SEED_YEAR_OFFSET = 621;

/**
 * The Persian calendar's first year that CLDR's conversion is exact. `Intl` extrapolates
 * mathematically outside this range rather than failing, which silently produces wrong dates, so
 * the adapter refuses instead.
 */
const MIN_SUPPORTED_YEAR = 1178;
const MAX_SUPPORTED_YEAR = 1633;

/**
 * The starting bracket width, in days, for the inverse conversion's day-offset search.
 *
 * 64 is *not* wide enough to hold the answer and is not intended to be. Measured against the
 * supported range, every valid Persian date lands 79–113 days after its seed — Persian month M
 * starts roughly 2.5 months *after* Gregorian month M, because the Persian year begins at Nowruz in
 * March while the Gregorian month M seed lands in May of the same numbered year. The widening loops
 * in `invertToGregorian` are therefore load-bearing on every single call, not a safety net: they
 * always grow 64 → 128 before the bisection runs. Removing them would make every conversion return
 * a confidently wrong date rather than fail.
 */
const INITIAL_BRACKET_DAYS = 64;

/**
 * A hard ceiling on refinement steps, so a bug in the comparison cannot spin forever inside a
 * render path. Measured worst case is 10 steps; anything near this bound means the search is
 * broken, not that the input is exotic.
 */
const MAX_SEARCH_STEPS = 24;

/** Persian `fa-IR` emits Arabic-Indic digits (۰-۹); `parseInt` yields `NaN` on them. */
const toLatinDigits = (value: string): string =>
  value.replace(/[۰-۹]/g, (digit) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(digit)));

const dayFormatter = new Intl.DateTimeFormat(PERSIAN_LOCALE, {
  calendar: "persian",
  year: "numeric",
  month: "numeric",
  day: "numeric",
});

/** Pulls one numeric part out of `formatToParts`, normalizing Persian digits first. */
const readNumber = (date: Date, type: Intl.DateTimeFormatPartTypes): number => {
  const raw = dayFormatter.formatToParts(date).find((part) => part.type === type)?.value ?? "0";
  return Number.parseInt(toLatinDigits(raw), 10);
};

/**
 * Detects whether this runtime can actually convert to and from the Persian calendar.
 *
 * A host without `calendar: "persian"` silently falls back to the Gregorian calendar, which would
 * make the Persian adapter a lie that reports Persian month names over Gregorian dates. Callers use
 * this to degrade to the Gregorian adapter rather than render wrong dates.
 */
export const isPersianCalendarSupported = (): boolean => {
  try {
    // Persian 1403-06-01 is 22 August 2024. If the host converted it, it reports month 6.
    const parts = dayFormatter.formatToParts(new Date(2024, 7, 22));
    const month = parts.find((part) => part.type === "month")?.value;
    return month === "6" || month === "۶";
  } catch {
    return false;
  }
};

/**
 * Reads the Persian year+month+day out of an already-parsed Gregorian date.
 *
 * An `Invalid Date` yields `NaN` parts rather than throwing, matching what the Gregorian adapter
 * returns for the same input. `Intl.DateTimeFormat.formatToParts` throws on an invalid date, and
 * `toParts` sits in the render path behind the picker, so degrading is the right behavior here: a
 * comparison against `NaN` is simply false, exactly as with the Gregorian adapter's `NaN` parts.
 */
const readParts = (date: Date): CalendarDateParts => {
  if (Number.isNaN(date.getTime())) {
    return { year: Number.NaN, month: Number.NaN, day: Number.NaN };
  }
  return {
    year: readNumber(date, "year"),
    month: readNumber(date, "month"),
    day: readNumber(date, "day"),
  };
};

/**
 * Persian → Gregorian, by progressive search.
 *
 * `Intl` converts Gregorian → Persian but not the reverse, so this inverts it: seed a Gregorian
 * guess from the Persian year and month, then repeatedly ask `Intl` what the guess actually is and
 * narrow toward the answer.
 *
 * The narrowing is a bisection over whole calendar days, not arithmetic on a "month drift". A drift
 * step cannot work here: moving from day 31 of a 31-day month to day 1 of the next computes to
 * `1 * 30 + (1 - 31) === 0` days, so the guess freezes one day short and never converges. Bisecting
 * on `readParts` is well-founded instead — see `compareParts` — and cannot stall.
 *
 * Results are memoized because a picker converts the same day repeatedly while rendering 42 cells.
 */
const fromPartsCache = new Map<string, Date>();

/**
 * Orders two Persian dates. Because the Persian calendar is a contiguous day count, comparing
 * (year, month, day) lexicographically is exactly the same as comparing the instants they name —
 * which is what makes the search below well-founded.
 */
const compareParts = (parts: CalendarDateParts, target: CalendarDateParts): number =>
  parts.year - target.year || parts.month - target.month || parts.day - target.day;

const invertToGregorian = (year: number, month: number, day: number): Date => {
  const cacheKey = `${year}:${month}:${day}`;
  const cached = fromPartsCache.get(cacheKey);
  if (cached) return new Date(cached.getTime());

  // `Number.isInteger` rather than a plain range comparison: `NaN` fails both `NaN < MIN` and
  // `NaN > MAX`, so a range-only guard lets it through to the seed and the eventual
  // `formatToParts` throws `RangeError: Invalid time value` from inside a render path.
  if (
    !Number.isInteger(year) ||
    !Number.isInteger(month) ||
    !Number.isInteger(day) ||
    year < MIN_SUPPORTED_YEAR ||
    year > MAX_SUPPORTED_YEAR
  ) {
    // Out of CLDR's exact range, or not a date at all. Returning the start of the Gregorian year
    // keeps the picker usable rather than producing a confidently wrong date. Not memoized: it is a
    // rejected input, not a conversion result. A non-integer year flows through the same line, which
    // for `NaN` yields an `Invalid Date` — and `toParts` degrades that to `NaN` parts rather than
    // inventing a year, so a caller comparing against `NaN` simply highlights nothing.
    return new Date(year, 0, 1);
  }

  const target: CalendarDateParts = { year, month, day };
  // Seed: Persian year Y begins in Gregorian year Y + 621, but Persian month M is *not* at the same
  // point in that Gregorian year as month M — the Persian year starts at Nowruz (20/21 March), so
  // month M lands roughly 2.5 months later than the Gregorian month M seed. Measured, the target is
  // 79–113 days after this seed; see `INITIAL_BRACKET_DAYS`.
  const seed = startOfDay(new Date(year + SEED_YEAR_OFFSET, month - 1, 1));

  // Establish the invariant "low is before the target, high is not" as day offsets from the seed.
  // These loops are required, not defensive: `INITIAL_BRACKET_DAYS` is narrower than every real
  // offset, so they always widen 64 → 128 before the bisection below. Deleting them makes every
  // call return a wrong date silently, because the bisection would still converge — to a plausible
  // neighbouring day rather than the requested one.
  let span = INITIAL_BRACKET_DAYS;
  while (compareParts(readParts(addDays(seed, -span)), target) >= 0 && span < 4096) span *= 2;
  while (compareParts(readParts(addDays(seed, span)), target) < 0 && span < 4096) span *= 2;

  let low = -span;
  let high = span;
  for (let step = 0; step < MAX_SEARCH_STEPS && high - low > 1; step++) {
    const midpoint = Math.floor((low + high) / 2);
    if (compareParts(readParts(addDays(seed, midpoint)), target) < 0) low = midpoint;
    else high = midpoint;
  }

  // `low` is the last day before the target and `high` the first day at or after it, so `high` is
  // the answer. `startOfDay` then drops any residue from a mid-bracket instant.
  const result = startOfDay(addDays(seed, high));
  fromPartsCache.set(cacheKey, result);
  return new Date(result.getTime());
};

/** Longest a Persian month can be, used only to bound the Esfand rollover probe below. */
const MAX_MONTH_LENGTH = 31;

/**
 * Shortest a Persian month can be, and the fallback when the rollover probe finds no match. Also
 * the length every non-Esfand month is ≥ 29.
 */
const MIN_MONTH_LENGTH = 29;

/** Exposed for tests and for the picker's month-length shortcut. */
export const persianDayCount = (year: number, month: number): number => {
  const firstOfMonth = invertToGregorian(year, month, 1);
  if (month !== MONTHS_PER_YEAR) {
    // Month M runs until the first day of month M+1, so the length is a difference, not a lookup
    // table.
    return Math.round(differenceInCalendarDays(invertToGregorian(year, month + 1, 1), firstOfMonth));
  }

  // Esfand cannot be differenced against 1 Farvardin of year+1: for the last supported year that
  // probe falls outside CLDR's exact range and the guard would return a placeholder Gregorian year,
  // turning the length into a nonsense negative number. Walk forward instead and let `Intl` report
  // the rollover — still derived from a real conversion rather than a hardcoded table, and it keeps
  // Esfand 29-vs-30 falling out on its own.
  for (let length = MAX_MONTH_LENGTH; length >= 28; length--) {
    const candidate = addDays(firstOfMonth, length - 1);
    const parts = readParts(candidate);
    if (parts.year === year && parts.month === month) return length;
  }
  // Unreachable while `Intl` is answering: Esfand always ends within 29–30 days of its start. Not
  // returning 0 regardless — callers divide by this value, and 0 would turn an internal
  // inconsistency into `Infinity` in a render path instead of a wrong-but-finite month length.
  return MIN_MONTH_LENGTH;
};

export const persianCalendar: CalendarAdapter = {
  system: "persian",
  locale: PERSIAN_LOCALE,

  toParts: (date: Date): CalendarDateParts => readParts(date),

  fromParts: (year: number, month: number, day: number): Date => invertToGregorian(year, month, day),

  getMonthLength: (year: number, month: number): number => persianDayCount(year, month),

  getMonthGrid: (year: number, month: number, weekStartsOn = 0): Date[] => {
    const first = invertToGregorian(year, month, 1);
    // `getDay()` is 0=Sunday, which is exactly the `weekStartsOn` numbering the contract uses.
    const leading = (first.getDay() - weekStartsOn + 7) % 7;
    const gridStart = addDays(first, -leading);
    return Array.from({ length: GRID_CELLS }, (_, index) => startOfDay(addDays(gridStart, index)));
  },

  addMonths: ({ year, month }: CalendarMonthParts, delta: number): CalendarMonthParts => {
    const zeroBased = year * MONTHS_PER_YEAR + (month - 1) + delta;
    return {
      year: Math.floor(zeroBased / MONTHS_PER_YEAR),
      month: (((zeroBased % MONTHS_PER_YEAR) + MONTHS_PER_YEAR) % MONTHS_PER_YEAR) + 1,
    };
  },

  getMonthStart: ({ year, month }: CalendarMonthParts): Date => startOfDay(invertToGregorian(year, month, 1)),

  // The option bag maps straight onto `Intl.DateTimeFormat`'s own vocabulary, so no token
  // translation is needed — and `Intl` composes its own separators, so no manual punctuation here.
  // This is the Persian half of the contract established by `toDatePartsToken` in the Gregorian
  // adapter: same fields, same `2-digit` meaning, but a formatter that takes semantic options
  // rather than `date-fns` tokens.
  format: (date: Date, options: CalendarFormatOptions = {}): string => {
    // An empty bag makes `Intl` emit the bare date, which is not what any call site wants.
    if (!options.year && !options.month && !options.day && !options.weekday) {
      return new Intl.DateTimeFormat(PERSIAN_LOCALE, {
        calendar: "persian",
        year: "numeric",
        month: "short",
        day: "numeric",
      }).format(date);
    }
    return new Intl.DateTimeFormat(PERSIAN_LOCALE, {
      calendar: "persian",
      ...options,
    }).format(date);
  },

  getMonthNames: (style: "long" | "short" | "narrow"): string[] => {
    const formatter = new Intl.DateTimeFormat(PERSIAN_LOCALE, { calendar: "persian", month: style });
    // Day 1 of each Persian month of 1403, so the run is derived from real conversions rather
    // than a hardcoded table.
    return Array.from({ length: MONTHS_PER_YEAR }, (_, index) =>
      formatter.format(invertToGregorian(1403, index + 1, 1))
    );
  },

  getWeekdayNames: (style: "long" | "short" | "narrow", weekStartsOn = 0): string[] => {
    const formatter = new Intl.DateTimeFormat(PERSIAN_LOCALE, { weekday: style });
    // 1 Aug 2021 was a Sunday, so stepping forward one day at a time covers every weekday in order;
    // the rotation below then moves `weekStartsOn` to the front.
    const knownSunday = new Date(2021, 7, 1);
    const names = Array.from({ length: 7 }, (_, index) => formatter.format(addDays(knownSunday, index)));
    return [...names.slice(weekStartsOn), ...names.slice(0, weekStartsOn)];
  },

  isSupported: (): boolean => isPersianCalendarSupported(),
};
