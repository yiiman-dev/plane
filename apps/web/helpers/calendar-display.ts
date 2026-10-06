/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { getCalendarAdapter } from "@plane/blocks/property-select";
import type { CalendarSystem } from "@plane/blocks/property-select";

/**
 * Shared display formatting for the two places in the web app that render a wall clock or a bare
 * date next to calendar-aware content: the profile sidebar's timezone row and the home greeting
 * header.
 *
 * Both used to pin `Intl.DateTimeFormat` to `"en-US"`, which meant a Persian user saw Persian dates
 * from the adapter-backed surfaces next to an English clock rendered by these components. Everything
 * here therefore reads its locale from the adapter rather than naming one.
 */

/**
 * The clock, localized to the user's calendar.
 *
 * Built from the adapter's `locale` rather than passed to `adapter.format()`, because
 * `CalendarFormatOptions` describes *date* fields only — no hour, minute, or time zone — so the
 * adapter cannot express a clock. The adapter's `locale` is enough on its own: the Persian one is
 * `fa-IR-u-ca-persian`, whose Unicode extension already selects the Persian calendar and digits.
 *
 * No `calendar` option is passed. `CalendarSystem`'s `"gregorian"` is not `Intl`'s name for that
 * calendar (`"gregory"`), so forwarding `adapter.system` verbatim throws a `RangeError` on every
 * Gregorian render; the Gregorian locale's default is already the right calendar.
 *
 * @param timeZone IANA zone name, or `undefined` for the runtime's local zone. An invalid name
 *                 throws `RangeError` from `Intl`, exactly as it did at the original call site.
 */
export const getClockTime = (date: Date, system: CalendarSystem, timeZone?: string): string =>
  new Intl.DateTimeFormat(getCalendarAdapter(system).locale, {
    timeZone,
    hour12: false, // Use 24-hour format
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);

/**
 * A short date ("Jun 15" / "۲۵ خرداد"), via the adapter's own field vocabulary.
 */
export const getShortDate = (date: Date, system: CalendarSystem): string =>
  getCalendarAdapter(system).format(date, { month: "short", day: "numeric" });

/**
 * A full weekday name ("Sunday" / "یکشنبه"), via the adapter.
 */
export const getWeekdayName = (date: Date, system: CalendarSystem): string =>
  getCalendarAdapter(system).format(date, { weekday: "long" });

/**
 * Which greeting an hour falls into.
 *
 * Takes the plain local hour rather than an `Intl`-formatted string: greetings are a local-time
 * notion that neither calendar system changes, so routing it through a formatter would only add a
 * Persian-digit string to re-parse. Midnight is hour 0, which is why this reads `getHours()` rather
 * than the 24-hour string the old code parsed — `Intl` with `hour12: false` renders that hour as
 * "24" in some locales, which would have read as evening.
 */
export const getGreetingBucket = (hour: number): "morning" | "afternoon" | "evening" => {
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
};
