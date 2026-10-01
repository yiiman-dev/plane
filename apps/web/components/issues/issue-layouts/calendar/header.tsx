/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";

// components
import type { TSupportedFilterTypeForUpdate } from "@plane/constants";
import { useTranslation } from "@plane/i18n";
import { ChevronLeftOutline, ChevronRightOutline } from "@makeplane/propel/icons";
import type { TSupportedFilterForUpdate } from "@plane/types";
import { Row } from "@plane/blocks/layout";
import { getCalendarAdapter, resolveCalendarSystem } from "@plane/blocks/property-select";
// icons
import { useCalendarView } from "@/hooks/store/use-calendar-view";
import { useUserProfile } from "@/hooks/store/user";
import type { ICycleIssuesFilter } from "@/store/issue/cycle";
import type { IModuleIssuesFilter } from "@/store/issue/module";
import type { IProjectIssuesFilter } from "@/store/issue/project";
import type { IProjectViewIssuesFilter } from "@/store/issue/project-views";
import { CalendarMonthsDropdown, CalendarOptionsDropdown } from "./dropdowns";

interface ICalendarHeader {
  issuesFilterStore: IProjectIssuesFilter | IModuleIssuesFilter | ICycleIssuesFilter | IProjectViewIssuesFilter;
  updateFilters?: (
    projectId: string,
    filterType: TSupportedFilterTypeForUpdate,
    filters: TSupportedFilterForUpdate
  ) => Promise<void>;
  setSelectedDate: (date: Date) => void;
}

export const CalendarHeader = observer(function CalendarHeader(props: ICalendarHeader) {
  const { issuesFilterStore, updateFilters, setSelectedDate } = props;

  const { t } = useTranslation();

  const issueCalendarView = useCalendarView();

  const calendarLayout = issuesFilterStore.issueFilters?.displayFilters?.calendar?.layout ?? "month";

  const { activeMonthDate, activeWeekDate } = issueCalendarView.calendarFilters;

  const { data: userProfile } = useUserProfile();

  // `activeMonthDate` is a Gregorian `Date` because that is what the calendar payload is keyed by,
  // but the month the user is paging through is their own calendar's. Stepping it by hand with
  // `getMonth() === 0 ? 11 : getMonth() - 1` walks Gregorian months while the title beside these
  // arrows renders the calendar month's name, so the two disagree in every non-Gregorian mode.
  const adapter = getCalendarAdapter(resolveCalendarSystem(userProfile?.calendar_system));

  const stepActiveMonth = (delta: number) => {
    const nextParts = adapter.addMonths(adapter.toParts(activeMonthDate), delta);

    issueCalendarView.updateCalendarFilters({
      activeMonthDate: adapter.getMonthStart(nextParts),
    });
  };

  const handlePrevious = () => {
    if (calendarLayout === "month") {
      stepActiveMonth(-1);
    } else {
      const previousWeekDate = new Date(
        activeWeekDate.getFullYear(),
        activeWeekDate.getMonth(),
        activeWeekDate.getDate() - 7
      );

      issueCalendarView.updateCalendarFilters({
        activeWeekDate: previousWeekDate,
      });
    }
  };

  const handleNext = () => {
    if (calendarLayout === "month") {
      stepActiveMonth(1);
    } else {
      const nextWeekDate = new Date(
        activeWeekDate.getFullYear(),
        activeWeekDate.getMonth(),
        activeWeekDate.getDate() + 7
      );

      issueCalendarView.updateCalendarFilters({
        activeWeekDate: nextWeekDate,
      });
    }
  };

  const handleToday = () => {
    const today = new Date();
    // First day of the user's *current* month, not of the Gregorian month today falls in — the two
    // differ in Persian, and only the former is the month the grid is laid out over.
    const firstDayOfCurrentMonth = adapter.getMonthStart(adapter.toParts(today));

    issueCalendarView.updateCalendarFilters({
      activeMonthDate: firstDayOfCurrentMonth,
      activeWeekDate: today,
    });
    setSelectedDate(today);
  };

  return (
    <Row className="mb-4 flex items-center justify-between gap-2">
      <div className="flex items-center gap-1.5">
        <button type="button" className="grid place-items-center" onClick={handlePrevious}>
          <ChevronLeftOutline height={16} width={16} />
        </button>
        <button type="button" className="grid place-items-center" onClick={handleNext}>
          <ChevronRightOutline height={16} width={16} />
        </button>
        <CalendarMonthsDropdown issuesFilterStore={issuesFilterStore} />
      </div>
      <div className="flex items-center gap-1.5">
        <button
          type="button"
          className="rounded-sm bg-layer-transparent px-2.5 py-1 text-11 font-medium text-secondary hover:bg-layer-transparent-hover hover:text-primary"
          onClick={handleToday}
        >
          {t("common.today")}
        </button>
        <CalendarOptionsDropdown issuesFilterStore={issuesFilterStore} updateFilters={updateFilters} />
      </div>
    </Row>
  );
});
