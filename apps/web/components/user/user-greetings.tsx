/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane types
import { useTranslation } from "@plane/i18n";
import type { IUser } from "@plane/types";
// hooks
import { useCurrentTime } from "@/hooks/use-current-time";
import { useUserProfile } from "@/hooks/store/user";
// helpers
import { getClockTime, getGreetingBucket, getShortDate, getWeekdayName } from "@/helpers/calendar-display";

export interface IUserGreetingsView {
  user: IUser;
}

export function UserGreetingsView(props: IUserGreetingsView) {
  const { user } = props;
  // current time hook
  const { currentTime } = useCurrentTime();
  // store hooks
  const { t } = useTranslation();
  const { calendarSystem } = useUserProfile();

  // The greeting bucket is a local-time notion, so it reads the local hour directly. The clock and
  // the date line are localized, since they sit next to adapter-rendered Persian dates.
  const greeting = getGreetingBucket(currentTime.getHours());

  const weekDay = getWeekdayName(currentTime, calendarSystem);
  const date = getShortDate(currentTime, calendarSystem);
  const timeString = getClockTime(currentTime, calendarSystem, user?.user_timezone);

  return (
    <div className="my-6 flex flex-col items-center">
      <h2 className="text-center text-20 font-semibold">
        {t("good")} {t(greeting)}, {user?.first_name} {user?.last_name}
      </h2>
      <h5 className="flex items-center gap-2 font-medium text-placeholder">
        <div>{greeting === "morning" ? "🌤️" : greeting === "afternoon" ? "🌥️" : "🌙️"}</div>
        <div>
          {weekDay}, {date} {timeString}
        </div>
      </h5>
    </div>
  );
}
