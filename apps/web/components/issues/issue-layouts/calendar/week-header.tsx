/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { getCalendarAdapter, isWeekend, resolveCalendarSystem, weekdayNames } from "@plane/blocks/property-select";
// helpers
// hooks
import { useUserProfile } from "@/hooks/store/user";

type Props = {
  isLoading: boolean;
  showWeekends: boolean;
};

/**
 * A `Date` whose `getDay()` is `dayIndex`, so a weekday index can be asked about with the shared
 * weekend helper. 15 June 2025 is a Sunday, which pins the offset.
 */
const dateForWeekday = (dayIndex: number) => new Date(2025, 5, 15 + dayIndex);

export const CalendarWeekHeader = observer(function CalendarWeekHeader(props: Props) {
  const { isLoading, showWeekends } = props;
  // hooks
  const { data: userProfile } = useUserProfile();
  const startOfWeek = userProfile?.start_of_the_week;

  const adapter = getCalendarAdapter(resolveCalendarSystem(userProfile?.calendar_system));

  // The adapter already rotates the names so column 0 is the user's first day of the week, so the
  // rotation that used to happen here — sorting `DAYS_LIST` by `EStartOfTheWeek.value` — is part of
  // the lookup. The weekday index is recovered from the column position, which is the only place
  // it is needed: to decide which two columns are the weekend.
  const orderedDays = weekdayNames(adapter, "short", startOfWeek).map((name, index) => ({
    name,
    dayIndex: (startOfWeek + index) % 7,
  }));

  return (
    <div
      className={`relative sticky top-0 z-[1] grid divide-subtle-1 text-13 font-medium md:divide-x-[0.5px] ${
        showWeekends ? "grid-cols-7" : "grid-cols-5"
      }`}
    >
      {isLoading && (
        <div className="absolute h-[1.5px] w-3/4 animate-[bar-loader_2s_linear_infinite] bg-accent-primary" />
      )}
      {orderedDays.map((day) => {
        if (!showWeekends && isWeekend(dateForWeekday(day.dayIndex), startOfWeek)) return null;

        return (
          <div key={day.name} className="flex h-11 items-center justify-center bg-layer-1 px-4 md:justify-end">
            {day.name}
          </div>
        );
      })}
    </div>
  );
});
