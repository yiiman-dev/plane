/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { CalendarAdapter, CalendarSystem } from "../types";
import { gregorianCalendar } from "./gregorian";
import { isPersianCalendarSupported, persianCalendar } from "./persian";

export { gregorianCalendar } from "./gregorian";
export { isPersianCalendarSupported, persianCalendar, persianDayCount } from "./persian";

/**
 * Narrows an untrusted value — an API payload, a migration-era row, a localStorage entry — to a
 * known system. Anything unrecognised becomes Gregorian, which is what every existing user already
 * sees, so an unknown value degrades to current behaviour rather than to a wrong calendar.
 */
export const resolveCalendarSystem = (value: unknown): CalendarSystem => {
  if (value === "persian") return "persian";
  return "gregorian";
};

/**
 * The adapter for a system. A Persian request on a runtime without `calendar: "persian"` support
 * returns the Gregorian adapter instead of one that would report Persian month names over
 * Gregorian dates.
 */
export const getCalendarAdapter = (system: CalendarSystem = "gregorian"): CalendarAdapter => {
  if (resolveCalendarSystem(system) === "persian" && isPersianCalendarSupported()) {
    return persianCalendar;
  }
  return gregorianCalendar;
};
