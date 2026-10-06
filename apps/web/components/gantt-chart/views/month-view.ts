/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { cloneDeep, uniqBy } from "lodash-es";
// plane imports
import type { CalendarAdapter } from "@plane/blocks/property-select";
import type { ChartDataType } from "@plane/types";
import type { EStartOfTheWeek } from "@plane/types";
// local imports
import { generateMonths } from "../data";
import { defaultCalendarAdapter, getNumberOfDaysBetweenTwoDates, getNumberOfDaysInMonth } from "./helpers";
import type { IWeekBlock } from "./week-view";
import { getWeeksBetweenTwoDates } from "./week-view";

export interface IMonthBlock {
  today: boolean;
  month: number;
  days: number;
  monthData: {
    key: number;
    shortTitle: string;
    title: string;
  };
  title: string;
  year: number;
}

export interface IMonthView {
  months: IMonthBlock[];
  weeks: IWeekBlock[];
}

/**
 * Generate Month Chart data
 * @param monthPayload
 * @param side
 * @returns
 */
/**
 * `startOfWeek` is deliberately still not a parameter: this view has never passed the user's
 * `start_of_the_week` down, so it falls back to Sunday inside `getWeeksBetweenTwoDates`. That is a
 * pre-existing bug and not calendar-specific — fixing it here would fold an unrelated behaviour
 * change into the calendar threading.
 */
const generateMonthChart = (
  monthPayload: ChartDataType,
  side: null | "left" | "right",
  targetDate?: Date,
  _startOfWeek?: EStartOfTheWeek,
  adapter: CalendarAdapter = defaultCalendarAdapter()
) => {
  let renderState = cloneDeep(monthPayload);

  const range: number = renderState.data.approxFilterRange || 6;
  let filteredDates: IMonthView = { months: [], weeks: [] };
  let minusDate: Date = new Date();
  let plusDate: Date = new Date();

  let startDate = new Date();
  let endDate = new Date();

  // if side is null generate months on both side of current date
  if (side === null) {
    const currentDate = renderState.data.currentDate;

    minusDate = new Date(currentDate.getFullYear(), currentDate.getMonth() - range, currentDate.getDate());
    plusDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + range, currentDate.getDate());

    if (minusDate && plusDate) filteredDates = getMonthsViewBetweenTwoDates(minusDate, plusDate, adapter);

    startDate = filteredDates.weeks[0]?.startDate;
    endDate = filteredDates.weeks[filteredDates.weeks.length - 1]?.endDate;
    renderState = {
      ...renderState,
      data: {
        ...renderState.data,
        startDate,
        endDate,
      },
    };
  }
  // When side is left, generate more months on the left side of the start date
  else if (side === "left") {
    const chartStartDate = renderState.data.startDate;
    const currentDate = targetDate ? targetDate : chartStartDate;

    minusDate = new Date(currentDate.getFullYear(), currentDate.getMonth() - range, 1);
    plusDate = new Date(chartStartDate.getFullYear(), chartStartDate.getMonth(), chartStartDate.getDate() - 1);

    if (minusDate && plusDate) filteredDates = getMonthsViewBetweenTwoDates(minusDate, plusDate, adapter);

    startDate = filteredDates.weeks[0]?.startDate;
    endDate = new Date(chartStartDate.getFullYear(), chartStartDate.getMonth(), chartStartDate.getDate() - 1);
    renderState = {
      ...renderState,
      data: { ...renderState.data, startDate },
    };
  }
  // When side is right, generate more months on the right side of the end date
  else if (side === "right") {
    const chartEndDate = renderState.data.endDate;
    const currentDate = targetDate ? targetDate : chartEndDate;

    minusDate = new Date(chartEndDate.getFullYear(), chartEndDate.getMonth(), chartEndDate.getDate() + 1);
    plusDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + range, 1);

    if (minusDate && plusDate) filteredDates = getMonthsViewBetweenTwoDates(minusDate, plusDate, adapter);

    startDate = new Date(chartEndDate.getFullYear(), chartEndDate.getMonth(), chartEndDate.getDate() + 1);
    endDate = filteredDates.weeks[filteredDates.weeks.length - 1]?.endDate;
    renderState = {
      ...renderState,
      data: { ...renderState.data, endDate: filteredDates.weeks[filteredDates.weeks.length - 1]?.endDate },
    };
  }

  const days = Math.abs(getNumberOfDaysBetweenTwoDates(startDate, endDate)) + 1;
  const scrollWidth = days * monthPayload.data.dayWidth;

  return { state: renderState, payload: filteredDates, scrollWidth: scrollWidth };
};

/**
 * Get Month View data between two dates, i.e., Months and Weeks between two dates
 * @param startDate
 * @param endDate
 * @returns
 */
const getMonthsViewBetweenTwoDates = (
  startDate: Date,
  endDate: Date,
  adapter: CalendarAdapter = defaultCalendarAdapter()
): IMonthView => ({
  months: getMonthsBetweenTwoDates(startDate, endDate, adapter),
  // `shouldPopulateDaysForWeek` is false and no `startOfWeek` is passed — see `generateMonthChart`.
  weeks: getWeeksBetweenTwoDates(startDate, endDate, false, undefined, adapter),
});

/**
 * generate array of months between two dates
 * @param startDate
 * @param endDate
 * @returns
 */
export const getMonthsBetweenTwoDates = (
  startDate: Date,
  endDate: Date,
  adapter: CalendarAdapter = defaultCalendarAdapter()
): IMonthBlock[] => {
  const monthBlocks = [];

  // The month rows, rebuilt per call because they follow the adapter's month names.
  // `generateMonths` is 0-based, so a 1-based calendar month `m` indexes row `m - 1`.
  const months = generateMonths(adapter);

  const startYear = startDate.getFullYear();
  const startMonth = startDate.getMonth();

  const today = new Date();
  // "Is this the current month" is a calendar question, not a Gregorian one — under Persian it must
  // compare Persian months, or the "Current" badge lands on the wrong column.
  const todayParts = adapter.toParts(today);
  const todayMonth = todayParts.month - 1;
  const todayYear = todayParts.year;

  const currentDate = new Date(startYear, startMonth);

  // `currentDate` is advanced by `setDate` at the bottom of the loop, so the rule's "not modified
  // in this loop" reading is a false positive — it does not track mutation through method calls.
  // oxlint-disable-next-line no-unmodified-loop-condition
  while (currentDate <= endDate) {
    // Adapter numbering: `parts.month` is 1-based and `parts.year` is the calendar year. Under
    // Gregorian `toParts` reports `getMonth() + 1` / `getFullYear()`, so `month - 1` and `year`
    // are exactly the values the old `Date.getMonth()` / `getFullYear()` reads produced — which
    // makes the title string below byte-identical for a Gregorian user.
    const parts = adapter.toParts(currentDate);
    const currentYear = parts.year;
    const currentMonth = parts.month - 1;

    monthBlocks.push({
      year: currentYear,
      month: currentMonth,
      monthData: months[currentMonth],
      title: `${months[currentMonth].title} ${currentYear}`,
      // 1-based calendar month, not the 0-based row index.
      days: getNumberOfDaysInMonth(adapter, currentYear, parts.month),
      today: todayMonth === currentMonth && todayYear === currentYear,
    });

    // Stepping stays a Gregorian month advance. This loop walks *real* time so that each block
    // lines up with the Gregorian week columns below it; only the labels and lengths above it are
    // calendar-aware.
    currentDate.setMonth(currentDate.getMonth() + 1);
  }

  return monthBlocks;
};

/**
 * Merge two MonthView data payloads
 * @param a
 * @param b
 * @returns
 */
const mergeMonthRenderPayloads = (a: IMonthView, b: IMonthView): IMonthView => ({
  months: uniqBy([...a.months, ...b.months], (monthBlock) => `${monthBlock.month}_${monthBlock.year}`),
  weeks: uniqBy(
    [...a.weeks, ...b.weeks],
    (weekBlock) => `${weekBlock.startDate.getTime()}_${weekBlock.endDate.getTime()}`
  ),
});

export const monthView = {
  generateChart: generateMonthChart,
  mergeRenderPayloads: mergeMonthRenderPayloads,
};
