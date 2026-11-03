/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { Toggle } from "@makeplane/propel/components/toggle";
import { useTranslation } from "@plane/i18n";
import { Popover, PopoverContent, PopoverTrigger } from "@makeplane/propel/components/popover";
import { ChevronLeftOutline, ChevronRightOutline } from "@makeplane/propel/icons";
//hooks
// icons
// constants
import { getDate } from "@plane/utils";
import { getCalendarAdapter, monthName, resolveCalendarSystem } from "@plane/blocks/property-select";
import { useCalendarView } from "@/hooks/store/use-calendar-view";
import { useUserProfile } from "@/hooks/store/user";
import type { ICycleIssuesFilter } from "@/store/issue/cycle";
import type { IModuleIssuesFilter } from "@/store/issue/module";
import type { IProjectIssuesFilter } from "@/store/issue/project";
import type { IProjectViewIssuesFilter } from "@/store/issue/project-views";
// helpers

interface Props {
  issuesFilterStore: IProjectIssuesFilter | IModuleIssuesFilter | ICycleIssuesFilter | IProjectViewIssuesFilter;
}
export const CalendarMonthsDropdown = observer(function CalendarMonthsDropdown(props: Props) {
  const { issuesFilterStore } = props;
  const { t } = useTranslation();

  const issueCalendarView = useCalendarView();

  const { data: userProfile } = useUserProfile();

  const calendarLayout = issuesFilterStore.issueFilters?.displayFilters?.calendar?.layout ?? "month";

  const { activeMonthDate } = issueCalendarView.calendarFilters;

  // Every label below, and every date this control navigates to, is expressed in the user's own
  // calendar. `activeMonthDate` stays a Gregorian `Date` — the payload it keys is Gregorian — but
  // reading it means going through the adapter, because `getMonth()`/`getFullYear()` are 0-based
  // Gregorian numbers and mean something entirely different in Persian.
  const adapter = getCalendarAdapter(resolveCalendarSystem(userProfile?.calendar_system));
  const activeMonthParts = adapter.toParts(activeMonthDate);

  const getWeekLayoutHeader = (): string => {
    const allDaysOfActiveWeek = issueCalendarView.allDaysOfActiveWeek;

    if (!allDaysOfActiveWeek) return "Week view";

    const daysList = Object.keys(allDaysOfActiveWeek);

    const firstDay = getDate(daysList[0]);
    const lastDay = getDate(daysList[daysList.length - 1]);

    if (!firstDay || !lastDay) return "Week view";

    const firstParts = adapter.toParts(firstDay);
    const lastParts = adapter.toParts(lastDay);

    if (firstParts.month === lastParts.month && firstParts.year === lastParts.year)
      return `${monthName(adapter, firstParts.month)} ${firstParts.year}`;

    if (firstParts.year !== lastParts.year) {
      return `${monthName(adapter, firstParts.month, "short")} ${firstParts.year} - ${monthName(
        adapter,
        lastParts.month,
        "short"
      )} ${lastParts.year}`;
    } else
      return `${monthName(adapter, firstParts.month, "short")} - ${monthName(
        adapter,
        lastParts.month,
        "short"
      )} ${lastParts.year}`;
  };

  const handleDateChange = (date: Date) => {
    issueCalendarView.updateCalendarFilters({
      activeMonthDate: date,
    });
  };

  return (
    <Popover>
      <PopoverTrigger
        disabled={calendarLayout === "week"}
        render={
          <button
            type="button"
            className="rounded-xs text-h5-semibold outline-none focus-visible:ring-2 focus-visible:ring-accent-strong"
          >
            {calendarLayout === "month"
              ? `${monthName(adapter, activeMonthParts.month)} ${activeMonthParts.year}`
              : getWeekLayoutHeader()}
          </button>
        }
      />
      <PopoverContent variant="rich" side="bottom" align="start" collisionPadding={12}>
        <div className="w-56 divide-y divide-subtle-1">
          <div className="flex items-center justify-between gap-2 pb-3">
            <IconButton
              variant="ghost"
              size="xs"
              aria-label={`${t("prev")} ${activeMonthDate.getFullYear() - 1}`}
              icon={<ChevronLeftOutline height={14} width={14} />}
              onClick={() => {
                handleDateChange(
                  adapter.getMonthStart({ year: activeMonthParts.year - 1, month: activeMonthParts.month })
                );
              }}
            />
            <span className="text-caption-sm-regular">{activeMonthDate.getFullYear()}</span>
            <IconButton
              variant="ghost"
              size="xs"
              aria-label={`${t("next")} ${activeMonthDate.getFullYear() + 1}`}
              icon={<ChevronRightOutline height={14} width={14} />}
              onClick={() => {
                handleDateChange(
                  adapter.getMonthStart({ year: activeMonthParts.year + 1, month: activeMonthParts.month })
                );
              }}
            />
          </div>
          <div className="grid grid-cols-4 items-stretch justify-items-stretch gap-4 pt-3">
            {Array.from({ length: 12 }, (_, index) => (
              <Toggle
                key={index}
                size="xs"
                label={monthName(adapter, index + 1, "short")}
                aria-label={`${monthName(adapter, index + 1)} ${activeMonthDate.getFullYear()}`}
                pressed={activeMonthDate.getMonth() === index}
                onClick={() => {
                  // The adapter's months are 1-based, which is what `fromParts` takes — the `+ 1`
                  // on this 0-based index is not an off-by-one fix, it is the translation between
                  // the two number spaces.
                  const newDate = adapter.fromParts(activeMonthParts.year, index + 1, 1);
                  handleDateChange(newDate);
                }}
              />
            ))}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
});
