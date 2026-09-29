/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Which calendar the user sees. Storage is always Gregorian regardless of this value. */
export type CalendarSystem = "gregorian" | "persian";

/** A day broken into its calendar's own numbering. Months are 1-based. */
export type CalendarDateParts = {
  year: number;
  month: number;
  day: number;
};

/**
 * A year+month pair, used for navigation where the day is irrelevant. Months are 1-based,
 * matching what `toParts` reports, so `addMonths` output feeds straight into `fromParts`.
 */
export type CalendarMonthParts = {
  year: number;
  month: number;
};

/**
 * Which named parts to render. Deliberately not a `date-fns` token string: those tokens have no
 * Persian equivalent, so each adapter maps these semantic fields to its own formatter.
 */
export type CalendarFormatOptions = {
  year?: "numeric" | "2-digit";
  month?: "long" | "short" | "numeric" | "2-digit";
  day?: "numeric" | "2-digit";
  weekday?: "long" | "short" | "narrow";
};

export type CalendarAdapter = {
  /** Identity of this adapter. */
  readonly system: CalendarSystem;
  /** The BCP 47 locale this adapter formats in, for month/weekday name lookups. */
  readonly locale: string;

  /** Gregorian `Date` → the date's parts in this calendar. Months are 1-based. */
  toParts: (date: Date) => CalendarDateParts;

  /**
   * The reverse: parts in this calendar → a Gregorian `Date`, at local midnight.
   *
   * This is the only place Persian→Gregorian conversion happens, and the reason every other
   * method can return a plain `Date`. The result is memoized, so calling it twice is free.
   *
   * @param year   calendar year
   * @param month  1-based calendar month
   * @param day    1-based calendar day
   */
  fromParts: (year: number, month: number, day: number) => Date;

  /** Days in the given calendar month: 28–31. */
  getMonthLength: (year: number, month: number) => number;

  /**
   * The month as exactly 42 `Date`s — 6 weeks × 7 days — padded on both sides with days from the
   * adjacent months. The length is fixed so the grid's height never changes between months.
   *
   * @param weekStartsOn 0 = Sunday … 6 = Saturday, matching `Profile.start_of_the_week`.
   */
  getMonthGrid: (year: number, month: number, weekStartsOn?: number) => Date[];

  /** Steps a year+month pair, clamping the month into 1–12 and carrying into the year. */
  addMonths: (parts: CalendarMonthParts, delta: number) => CalendarMonthParts;

  /** Local midnight on the first day of the given calendar month, as a Gregorian `Date`. */
  getMonthStart: (parts: CalendarMonthParts) => Date;

  /** Formats a Gregorian `Date` in this calendar and locale. */
  format: (date: Date, options?: CalendarFormatOptions) => string;

  /** 12 month names, index 0 = month 1. */
  getMonthNames: (style: "long" | "short" | "narrow") => string[];

  /** 7 weekday names rotated so index 0 is `weekStartsOn`. */
  getWeekdayNames: (style: "long" | "short" | "narrow", weekStartsOn?: number) => string[];

  /** Whether this adapter can actually convert — false for Persian on a browser without support. */
  isSupported: () => boolean;
};
