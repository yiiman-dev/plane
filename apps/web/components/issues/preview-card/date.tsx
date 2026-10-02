/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { CalendarOutline, DueDateOutline, StartDateOutline } from "@makeplane/propel/icons";
// plane imports
import type { TStateGroups } from "@plane/types";
import { cn, renderFormattedDate, shouldHighlightIssueDueDate } from "@plane/utils";
// hooks
import { useUserProfile } from "@/hooks/store/user";

type Props = {
  startDate: string | null;
  stateGroup: TStateGroups;
  targetDate: string | null;
};

// Wrapped in `observer` because the profile store loads asynchronously: without a subscription this
// component reads `calendarSystem` once and would keep rendering Gregorian dates if the profile
// landed after this card mounted.
export const WorkItemPreviewCardDate = observer(function WorkItemPreviewCardDate(props: Props) {
  const { startDate, stateGroup, targetDate } = props;
  // store hooks
  const { calendarSystem } = useUserProfile();
  // derived values
  const isDateRangeEnabled = Boolean(startDate && targetDate);
  const shouldHighlightDate = shouldHighlightIssueDueDate(targetDate, stateGroup);

  if (!startDate && !targetDate) return null;

  return (
    <div className="h-full rounded-sm px-1 text-11 text-secondary">
      {isDateRangeEnabled ? (
        <div
          className={cn("flex h-full items-center gap-1", {
            "text-danger-primary": shouldHighlightDate,
          })}
        >
          <CalendarOutline className="size-3 shrink-0" />
          <span>
            {renderFormattedDate(startDate, undefined, calendarSystem)} -{" "}
            {renderFormattedDate(targetDate, undefined, calendarSystem)}
          </span>
        </div>
      ) : startDate ? (
        <div className="flex h-full items-center gap-1">
          <StartDateOutline className="size-3 shrink-0" />
          <span>{renderFormattedDate(startDate, undefined, calendarSystem)}</span>
        </div>
      ) : (
        <div
          className={cn("flex h-full items-center gap-1", {
            "text-danger-primary": shouldHighlightDate,
          })}
        >
          <DueDateOutline className="size-3 shrink-0" />
          <span>{renderFormattedDate(targetDate, undefined, calendarSystem)}</span>
        </div>
      )}
    </div>
  );
});
