/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane utils
import { cn } from "@plane/utils";
// calendar labels come through `@plane/blocks` — `apps/web` has no `@plane/calendar` dependency
import { isWeekend } from "@plane/blocks/property-select";
// hooks
import { useTimeLineChartStore } from "@/hooks/use-timeline-chart";
import { useUserProfile } from "@/hooks/store/user";
//
import { HEADER_HEIGHT, SIDEBAR_WIDTH } from "../../constants";
import type { IWeekBlock } from "../../views";

export const WeekChartView = observer(function WeekChartView(_props: any) {
  const { currentViewData, renderView } = useTimeLineChartStore();
  const { data: userProfile } = useUserProfile();
  const startOfWeek = userProfile?.start_of_the_week;
  const weekBlocks: IWeekBlock[] = renderView;

  return (
    <div className={`absolute top-0 left-0 flex h-max min-h-full w-max`}>
      {currentViewData &&
        weekBlocks?.map((block) => (
          <div
            key={`month-${block?.startDate.toString()}-${block?.endDate.toString()}`}
            className="relative flex flex-col outline-[0.25px] outline-subtle-1"
          >
            {/** Header Div */}
            <div
              className="sticky top-0 z-[5] w-full flex-shrink-0 bg-surface-1 outline-[1px] outline-subtle-1"
              style={{
                height: `${HEADER_HEIGHT}px`,
              }}
            >
              {/** Main Months Title */}
              <div className="inline-flex h-7 w-full justify-between">
                <div
                  className="sticky z-[1] m-1 flex items-center bg-surface-1 px-3 py-1 text-13 font-regular whitespace-nowrap text-secondary capitalize"
                  style={{
                    left: `${SIDEBAR_WIDTH}px`,
                  }}
                >
                  {block?.title}
                </div>
                <div className="sticky px-3 py-2 text-11 whitespace-nowrap text-placeholder capitalize">
                  {block?.weekData?.title}
                </div>
              </div>
              {/** Days Sub title */}
              <div className="flex h-5 w-full">
                {/* The column's `Date` is a stable, unique identity for the day it renders — unlike
                    the array index, which changes if the week is re-cut at a different start day. */}
                {block?.children?.map((weekDay) => (
                  <div
                    key={`sub-title-${weekDay.date.getTime()}`}
                    className={cn(
                      "flex flex-shrink-0 justify-between p-1 text-center capitalize outline-[0.25px] outline-subtle-1",
                      {
                        "bg-accent-primary/20": weekDay.today,
                      }
                    )}
                    style={{ width: `${currentViewData?.data.dayWidth}px` }}
                  >
                    <div className="space-x-1 text-11 font-medium text-placeholder">{weekDay.dayData.abbreviation}</div>
                    <div className="space-x-1 text-11 font-medium">
                      <span
                        className={cn({
                          "rounded-sm bg-accent-primary px-1 text-on-color": weekDay.today,
                        })}
                      >
                        {weekDay.date.getDate()}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {/**
             * Day Columns. The weekend shading asks the shared `isWeekend` about the column's
             * `Date` rather than comparing `dayData.shortTitle` against `"sat"`/`"sun"` — a string
             * comparison that silently stopped shading weekends the moment the axis rendered Persian
             * weekday names, with no error and no failing test. The weekend is the two days at the
             * boundary of the user's week, so it moves with `startOfThe_week`.
             */}
            <div className="flex h-full w-full flex-grow bg-surface-1">
              {block?.children?.map((weekDay) => (
                <div
                  key={`column-${weekDay.date.getTime()}`}
                  className={cn("h-full overflow-hidden outline-[0.25px] outline-subtle", {
                    "bg-accent-primary/20": weekDay.today,
                  })}
                  style={{ width: `${currentViewData?.data.dayWidth}px` }}
                >
                  {isWeekend(weekDay.date, startOfWeek) && (
                    <div className="h-full bg-surface-2 outline-[0.25px] outline-strong" />
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
    </div>
  );
});
