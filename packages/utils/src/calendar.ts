/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { addDays } from "date-fns";
import { getCalendarAdapter, resolveCalendarSystem } from "@plane/calendar";
import type { CalendarAdapter, CalendarMonthParts, CalendarSystem } from "@plane/calendar";
import type { ICalendarDate, ICalendarPayload } from "@plane/types";
import { EStartOfTheWeek } from "@plane/types";
// local imports
import { getWeekNumberOfDate, renderFormattedPayloadDate } from "./datetime";

/**
 * Whether a cell falls inside the calendar month the grid is being generated for.
 *
 * Deliberately not `date.getMonth() === month`: the grid's month is the adapter's, and its numbering
 * is 1-based while `getMonth()` is 0-based Gregorian. That comparison only happens to work in
 * Gregorian mode, and is silently wrong everywhere else.
 */
const isInMonth = (adapter: CalendarAdapter, date: Date, monthParts: CalendarMonthParts): boolean => {
  const parts = adapter.toParts(date);
  return parts.year === monthParts.year && parts.month === monthParts.month;
};

/**
 * @returns {ICalendarPayload} calendar payload to render the calendar
 * @param {ICalendarPayload | null} currentStructure current calendar payload
 * @param {Date} startDate date of the month to render
 * @param {EStartOfTheWeek} startOfWeek the day to start the week on
 * @param {CalendarSystem} system calendar the grid is laid out in; the month is *measured* in this
 * calendar but every key and cell stays Gregorian, because the payload is API-facing
 * @description Returns calendar payload to render the calendar, if currentStructure is null, it will generate the payload for the month of startDate, else it will construct the payload for the month of startDate and append it to the currentStructure
 */
export const generateCalendarData = (
  currentStructure: ICalendarPayload | null,
  startDate: Date,
  startOfWeek: EStartOfTheWeek = EStartOfTheWeek.SUNDAY,
  system: CalendarSystem = "gregorian"
): ICalendarPayload => {
  const calendarData: ICalendarPayload = currentStructure ?? {};

  const adapter = getCalendarAdapter(resolveCalendarSystem(system));

  // The first of the *calendar* month, which is what the layout pages between. In Persian this is
  // 22 August for Shahrivar, not 1 August, so the grid has to be measured from here rather than
  // from `startDate`'s own Gregorian month.
  const monthStart = adapter.getMonthStart(adapter.toParts(startDate));
  const monthParts = adapter.toParts(monthStart);

  // The payload is keyed Gregorian — `issue_calendar_view.store.ts` reads it back with
  // `activeMonthDate.getFullYear()` / `.getMonth()`, and the day keys are API request dates — so the
  // bucket stays the Gregorian month the calendar month starts in, 0-based. A Persian month that
  // straddles the Gregorian boundary is therefore bucketed under the month it starts in, which is
  // what the store already navigates by.
  const year = monthStart.getFullYear();
  const month = monthStart.getMonth();

  // Month length in the user's calendar: 28-31 for Gregorian, 29-31 (Esfand 29, or 30 in a leap
  // year) for Persian. Both fit the same envelope, so nothing downstream has to special-case it.
  const totalDaysInMonth = adapter.getMonthLength(monthParts.year, monthParts.month);
  const firstDayOfMonthRaw = monthStart.getDay(); // Sunday is 0, Monday is 1, ..., Saturday is 6

  // Adjust firstDayOfMonth based on startOfWeek preference
  // This calculates how many empty cells we need at the start of the calendar
  const firstDayOfMonth = (firstDayOfMonthRaw - startOfWeek + 7) % 7;

  calendarData[`y-${year}`] ||= {};
  // Always reset the month data to ensure clean regeneration with correct startOfWeek
  calendarData[`y-${year}`][`m-${month}`] = {};

  // Row count still varies 4-6. Persian months are 29-31 days, the same envelope as Gregorian, so
  // the layout's behaviour is unchanged; it is deliberately NOT forced to the adapter's fixed 6x7
  // `getMonthGrid`, which is a different code path this layout does not use.
  const numWeeks = Math.ceil((totalDaysInMonth + firstDayOfMonth) / 7);

  for (let week = 0; week < numWeeks; week++) {
    const currentWeekObject: { [date: string]: ICalendarDate } = {};

    const weekNumber = getWeekNumberOfDate(addDays(monthStart, week * 7 - firstDayOfMonth));

    for (let i = 0; i < 7; i++) {
      const dayNumber = week * 7 + i - firstDayOfMonth;

      // Offset from the calendar month's first day, so a Persian month that spans two Gregorian
      // months still lands on consecutive days instead of being clamped to one Gregorian month.
      const date = addDays(monthStart, dayNumber);

      const formattedDatePayload = renderFormattedPayloadDate(date);
      if (formattedDatePayload)
        currentWeekObject[formattedDatePayload] = {
          date,
          // The grid's own position, not the cell's: `year`/`month` describe the payload bucket and
          // `day` is the cell's offset within the calendar month (0 and 31+ for the leading and
          // trailing days of the adjacent months). This is what these fields have always meant, and
          // nothing reads them, so changing it would be a gratuitous break. `date` stays the single
          // source of truth for the cell's real position.
          year,
          month,
          day: dayNumber + 1,
          week: weekNumber,
          // Compared in the adapter's own numbering, where months are 1-based. `date.getMonth()`
          // would be a 0-based Gregorian month and silently wrong in Persian mode.
          is_current_month: isInMonth(adapter, date, monthParts),
          is_current_week: getWeekNumberOfDate(date) === getWeekNumberOfDate(new Date()),
          is_today: date.toDateString() === new Date().toDateString(),
        };
    }

    // Use sequential week index instead of calculated week number for the key
    // This ensures weeks are grouped correctly regardless of startOfWeek preference
    calendarData[`y-${year}`][`m-${month}`][`w-${week}`] = currentWeekObject;
  }

  return calendarData;
};

/**
 * Returns a new array sorted by the startOfWeek.
 * @param items Array of items to sort.
 * @param getDayIndex Function to get the day index (0-6) from an item.
 * @param startOfWeek The day to start the week on.
 */
export const getOrderedDays = <T>(
  items: T[],
  getDayIndex: (item: T) => number,
  startOfWeek: EStartOfTheWeek = EStartOfTheWeek.SUNDAY
): T[] =>
  [...items].toSorted((a, b) => {
    const dayA = (7 + getDayIndex(a) - startOfWeek) % 7;
    const dayB = (7 + getDayIndex(b) - startOfWeek) % 7;
    return dayA - dayB;
  });
