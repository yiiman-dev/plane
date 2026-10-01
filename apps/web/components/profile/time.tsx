/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// hooks
import { useCurrentTime } from "@/hooks/use-current-time";
import { useUserProfile } from "@/hooks/store/user";
// helpers
import { getClockTime } from "@/helpers/calendar-display";

type Props = {
  timeZone: string | undefined;
};

export function ProfileSidebarTime(props: Props) {
  const { timeZone } = props;
  // current time hook
  const { currentTime } = useCurrentTime();
  const { calendarSystem } = useUserProfile();

  // Localized so the clock agrees with the adapter-rendered dates elsewhere on the profile.
  const timeString = getClockTime(currentTime, calendarSystem, timeZone);

  return (
    <span>
      {timeString} <span className="text-secondary">{timeZone}</span>
    </span>
  );
}
