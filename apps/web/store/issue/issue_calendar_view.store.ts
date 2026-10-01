/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observable, action, makeObservable, runInAction, computed, reaction } from "mobx";

// helpers
import { computedFn } from "mobx-utils";
import type { ICalendarPayload, ICalendarWeek } from "@plane/types";
import { EStartOfTheWeek } from "@plane/types";
import { generateCalendarData, getWeekNumberOfDate, renderFormattedPayloadDate } from "@plane/utils";
// types
import type { IIssueRootStore } from "./root.store";

/**
 * The 4th argument of `generateCalendarData`. Named structurally rather than imported from
 * `@plane/calendar`, which `apps/web` deliberately does not depend on.
 */
type CalendarSystemArg = Parameters<typeof generateCalendarData>[3];

export interface ICalendarStore {
  calendarFilters: {
    activeMonthDate: Date;
    activeWeekDate: Date;
  };
  calendarPayload: ICalendarPayload | null;

  // action
  updateCalendarFilters: (filters: Partial<{ activeMonthDate: Date; activeWeekDate: Date }>) => void;
  updateCalendarPayload: (date: Date) => void;
  regenerateCalendar: () => void;

  // computed
  allWeeksOfActiveMonth:
    | {
        [weekNumber: string]: ICalendarWeek;
      }
    | undefined;
  activeWeekNumber: number;
  allDaysOfActiveWeek: ICalendarWeek | undefined;
  getStartAndEndDate: (layout: "week" | "month") => { startDate: string; endDate: string } | undefined;
}

export class CalendarStore implements ICalendarStore {
  loader: boolean = false;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  error: any | null = null;

  // observables
  calendarFilters: { activeMonthDate: Date; activeWeekDate: Date } = {
    activeMonthDate: new Date(),
    activeWeekDate: new Date(),
  };
  calendarPayload: ICalendarPayload | null = null;
  // root store
  rootStore;

  constructor(_rootStore: IIssueRootStore) {
    makeObservable(this, {
      loader: observable.ref,
      error: observable.ref,

      // observables
      calendarFilters: observable.ref,
      calendarPayload: observable.ref,

      // actions
      updateCalendarFilters: action,
      updateCalendarPayload: action,
      regenerateCalendar: action,

      //computed
      allWeeksOfActiveMonth: computed,
      activeWeekNumber: computed,
      allDaysOfActiveWeek: computed,
    });

    this.rootStore = _rootStore;
    this.initCalendar();

    // Watch for changes in startOfWeek preference and the user's calendar system, and regenerate
    // the calendar. Reading both inside one data function is deliberate: MobX tracks every
    // observable touched while the data function evaluates, so this reaction now depends on
    // `start_of_the_week` *and* on `calendar_system` (read through the profile store's narrowed
    // getter, which reads `data.calendar_system`). The returned array is a new reference on every
    // evaluation, so the default identity comparer fires the effect whenever either input changes
    // and never otherwise — the reaction only re-evaluates when a tracked observable changes.
    reaction(
      () => [this.rootStore.rootStore.user.userProfile.data?.start_of_the_week, this.calendarSystem] as const,
      () => {
        // Regenerate calendar when the startOfWeek preference or the calendar system changes
        this.regenerateCalendar();
      }
    );
  }

  /**
   * The calendar the grid is laid out in. Narrowed by the profile store, so a malformed or
   * pre-migration API value degrades to Gregorian instead of reaching an adapter as garbage.
   *
   * Only ever forwarded to `generateCalendarData`. The payload is API-facing and stays keyed
   * Gregorian and 0-based (`y-${getFullYear()}` / `m-${getMonth()}`), which is what the lookups
   * above read, so this value must never be used to key or locate a cell.
   */
  private get calendarSystem(): CalendarSystemArg {
    return this.rootStore?.rootStore?.user?.userProfile?.calendarSystem as CalendarSystemArg;
  }

  get allWeeksOfActiveMonth() {
    if (!this.calendarPayload) return undefined;

    const { activeMonthDate } = this.calendarFilters;

    const year = activeMonthDate.getFullYear();
    const month = activeMonthDate.getMonth();

    // Get the weeks for the current month
    const weeks = this.calendarPayload[`y-${year}`][`m-${month}`];

    // If no weeks exist, return undefined
    if (!weeks) return undefined;

    // Create a new object to store the reordered weeks
    const reorderedWeeks: { [weekNumber: string]: ICalendarWeek } = {};

    // Get all week numbers and sort them
    const weekNumbers = Object.keys(weeks).map((key) => parseInt(key.replace("w-", "")));
    weekNumbers.sort((a, b) => a - b);

    // Reorder weeks based on start_of_week
    weekNumbers.forEach((weekNumber) => {
      const weekKey = `w-${weekNumber}`;
      reorderedWeeks[weekKey] = weeks[weekKey];
    });

    return reorderedWeeks;
  }

  get activeWeekNumber() {
    return getWeekNumberOfDate(this.calendarFilters.activeWeekDate);
  }

  get allDaysOfActiveWeek() {
    if (!this.calendarPayload) return undefined;

    const { activeWeekDate } = this.calendarFilters;
    // The payload is keyed Gregorian and 0-based, so the bucket is the Gregorian month
    // `activeWeekDate` falls in — the same bucket the store navigates by everywhere else.
    const year = activeWeekDate.getFullYear();
    const month = activeWeekDate.getMonth();

    // Check if calendar data exists for this year and month
    const yearData = this.calendarPayload[`y-${year}`];
    if (!yearData) return undefined;

    const monthData = yearData[`m-${month}`];
    if (!monthData) return undefined;

    // Find the week by the date's own key instead of recomputing the week index from an offset.
    // The generator pages between `adapter.getMonthStart(...)`, so in a non-Gregorian calendar its
    // first day is not the 1st of the *Gregorian* month — duplicating that offset math here silently
    // picked the wrong week for about half of the Persian year (Esfand 1403 at startOfWeek 0:
    // generator 2, this 4). The weeks are the generator's own cells, so asking them which one holds
    // the date cannot drift from the layout. At most 6x7 entries, so the scan is free at render time.
    const dateKey = renderFormattedPayloadDate(activeWeekDate);
    if (!dateKey) return undefined;

    for (const week of Object.values(monthData)) {
      if (dateKey in week) return week;
    }

    // The date is outside this month's grid, which is a legitimate state (e.g. the filters are
    // mid-navigation), so return undefined rather than throwing.
    return undefined;
  }

  getStartAndEndDate = computedFn((layout: "week" | "month") => {
    switch (layout) {
      case "week": {
        if (!this.allDaysOfActiveWeek) return;
        const dates = Object.keys(this.allDaysOfActiveWeek);
        return { startDate: dates[0], endDate: dates[dates.length - 1] };
      }
      case "month": {
        if (!this.allWeeksOfActiveMonth) return;
        const weeks = Object.keys(this.allWeeksOfActiveMonth);
        const firstWeekDates = Object.keys(this.allWeeksOfActiveMonth[weeks[0]]);
        const lastWeekDates = Object.keys(this.allWeeksOfActiveMonth[weeks[weeks.length - 1]]);

        return { startDate: firstWeekDates[0], endDate: lastWeekDates[lastWeekDates.length - 1] };
      }
    }
  });

  updateCalendarFilters = (filters: Partial<{ activeMonthDate: Date; activeWeekDate: Date }>) => {
    this.updateCalendarPayload(filters.activeMonthDate || filters.activeWeekDate || new Date());

    runInAction(() => {
      this.calendarFilters = {
        ...this.calendarFilters,
        ...filters,
      };
    });
  };

  updateCalendarPayload = (date: Date) => {
    if (!this.calendarPayload) return null;

    const nextDate = new Date(date);
    const startOfWeek = this.rootStore.rootStore.user.userProfile.data?.start_of_the_week ?? EStartOfTheWeek.SUNDAY;

    runInAction(() => {
      this.calendarPayload = generateCalendarData(this.calendarPayload, nextDate, startOfWeek, this.calendarSystem);
    });
  };

  initCalendar = () => {
    const startOfWeek = this.rootStore.rootStore.user.userProfile.data?.start_of_the_week ?? EStartOfTheWeek.SUNDAY;
    const newCalendarPayload = generateCalendarData(null, new Date(), startOfWeek, this.calendarSystem);

    runInAction(() => {
      this.calendarPayload = newCalendarPayload;
    });
  };

  /**
   * Force complete regeneration of calendar data
   * This should be called when the startOfWeek preference or the calendar system changes
   */
  regenerateCalendar = () => {
    const startOfWeek = this.rootStore.rootStore.user.userProfile.data?.start_of_the_week ?? EStartOfTheWeek.SUNDAY;
    const { activeMonthDate } = this.calendarFilters;

    // Force complete regeneration by passing null to clear all cached data
    const newCalendarPayload = generateCalendarData(null, activeMonthDate, startOfWeek, this.calendarSystem);

    runInAction(() => {
      this.calendarPayload = newCalendarPayload;
    });
  };
}
