/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

//
import type { CalendarAdapter } from "@plane/blocks/property-select";
import type { ChartDataType } from "@plane/types";
import type { EStartOfTheWeek } from "@plane/types";
import { generateQuarters } from "../data";
import { defaultCalendarAdapter, getNumberOfDaysBetweenTwoDates } from "./helpers";
import type { IMonthBlock } from "./month-view";
import { getMonthsBetweenTwoDates } from "./month-view";

export interface IQuarterMonthBlock {
  children: IMonthBlock[];
  quarterNumber: number;
  shortTitle: string;
  title: string;
  year: number;
  today: boolean;
}

/**
 * Generate Quarter Chart data, which in turn are months in an array
 * @param quarterPayload
 * @param side
 * @returns
 */
const generateQuarterChart = (
  quarterPayload: ChartDataType,
  side: null | "left" | "right",
  targetDate?: Date,
  _startOfWeek?: EStartOfTheWeek,
  adapter: CalendarAdapter = defaultCalendarAdapter()
) => {
  let renderState = quarterPayload;

  const range: number = renderState.data.approxFilterRange || 12;
  let filteredDates: IMonthBlock[] = [];
  let minusDate: Date = new Date();
  let plusDate: Date = new Date();

  let startDate = new Date();
  let endDate = new Date();

  // if side is null generate months on both side of current date
  if (side === null) {
    const currentDate = renderState.data.currentDate;

    minusDate = new Date(currentDate.getFullYear(), currentDate.getMonth() - range, 1);
    plusDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + range, 0);

    if (minusDate && plusDate) filteredDates = getMonthsBetweenTwoDates(minusDate, plusDate, adapter);

    const startMonthBlock = filteredDates[0];
    const endMonthBlock = filteredDates[filteredDates.length - 1];
    startDate = new Date(startMonthBlock.year, startMonthBlock.month, 1);
    endDate = new Date(endMonthBlock.year, endMonthBlock.month + 1, 0);

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

    minusDate = new Date(currentDate.getFullYear(), currentDate.getMonth() - range / 2, 1);
    plusDate = new Date(chartStartDate.getFullYear(), chartStartDate.getMonth() - 1, 1);

    if (minusDate && plusDate) filteredDates = getMonthsBetweenTwoDates(minusDate, plusDate, adapter);

    const startMonthBlock = filteredDates[0];
    startDate = new Date(startMonthBlock.year, startMonthBlock.month, 1);
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

    minusDate = new Date(chartEndDate.getFullYear(), chartEndDate.getMonth() + 1, 1);
    plusDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + range / 2, 1);

    if (minusDate && plusDate) filteredDates = getMonthsBetweenTwoDates(minusDate, plusDate, adapter);

    const endMonthBlock = filteredDates[filteredDates.length - 1];
    startDate = new Date(chartEndDate.getFullYear(), chartEndDate.getMonth(), chartEndDate.getDate() + 1);
    endDate = new Date(endMonthBlock.year, endMonthBlock.month + 1, 0);
    renderState = {
      ...renderState,
      data: { ...renderState.data, endDate },
    };
  }

  const days = Math.abs(getNumberOfDaysBetweenTwoDates(startDate, endDate)) + 1;
  const scrollWidth = days * quarterPayload.data.dayWidth;

  return { state: renderState, payload: filteredDates, scrollWidth: scrollWidth };
};

/**
 * Merge two Quarter data payloads
 * @param a
 * @param b
 * @returns
 */
const mergeQuarterRenderPayloads = (a: IMonthBlock[], b: IMonthBlock[]) => [...a, ...b];

/**
 * Group array of Months into Quarters, returns an array og Quarters and it's children Months
 * @param monthBlocks
 * @returns
 */
export const groupMonthsToQuarters = (
  monthBlocks: IMonthBlock[],
  adapter: CalendarAdapter = defaultCalendarAdapter()
): IQuarterMonthBlock[] => {
  const quartersMap: { [key: string]: IQuarterMonthBlock } = {};

  // The three-month groups, rebuilt per call because they follow the adapter's month names.
  // Under Persian these are season names ("بهار - خرداد"), not "Q1".
  const quarters = generateQuarters(adapter);

  const today = new Date();
  // Adapter parts, so this is the current *calendar* quarter. `toParts` is 1-based, hence the
  // `- 1`: without it Persian month 1 (Farvardin) would fold into quarter 0 alongside month 0,
  // which does not exist. Under Gregorian `(getMonth() + 1 - 1) / 3` is exactly `getMonth() / 3`.
  const todayParts = adapter.toParts(today);
  const todayQuarterNumber = Math.floor((todayParts.month - 1) / 3);
  const todayYear = todayParts.year;

  for (const monthBlock of monthBlocks) {
    const { month, year } = monthBlock;

    // `monthBlock.month` is the 0-based row index into the adapter's month table, i.e. the
    // 1-based calendar month minus one. Restoring the 1-based month (`month + 1`) and subtracting
    // one again for the division is what makes the grouping follow the calendar: under Persian,
    // Farvardin (row 0) must be the first group, and reading the row index as a Gregorian month
    // would file it under whatever Gregorian month it happens to fall in.
    const quarterNumber = Math.floor((month + 1 - 1) / 3);

    const quarterKey = `Q${quarterNumber}-${year}`;

    if (quartersMap[quarterKey]) {
      quartersMap[quarterKey].children.push(monthBlock);
    } else {
      const quarterData = quarters[quarterNumber];
      quartersMap[quarterKey] = {
        children: [monthBlock],
        quarterNumber,
        shortTitle: quarterData.shortTitle,
        title: `${quarterData.title} ${year}`,
        year,
        today: todayQuarterNumber === quarterNumber && todayYear === year,
      };
    }
  }

  return Object.values(quartersMap);
};

export const quarterView = {
  generateChart: generateQuarterChart,
  mergeRenderPayloads: mergeQuarterRenderPayloads,
};
