/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { observer } from "mobx-react";
import { HierarchyOutline } from "@makeplane/propel/icons";
// plane imports
import { ActivityTimelineItem, ActivityTimelineTimestamp } from "@plane/blocks/activity";
import { renderFormattedTime, renderFormattedDate, calculateTimeAgo } from "@plane/utils";
import { useIssueDetail } from "@/hooks/store/use-issue-detail";
import { usePlatformOS } from "@/hooks/use-platform-os";
import { useUserProfile } from "@/hooks/store/user";
// local imports
import { IssueUser } from "../";
import { IssueCreatorDisplay } from "./issue-creator";

type TIssueActivityBlockComponent = {
  icon?: ReactNode;
  activityId: string;
  ends: "top" | "bottom" | undefined;
  children: ReactNode;
  customUserName?: string;
};

// Wrapped in `observer` because the profile store loads asynchronously: without a subscription this
// component reads `calendarSystem` once and would keep rendering Gregorian dates if the profile
// landed after this block mounted.
export const IssueActivityBlockComponent = observer(function IssueActivityBlockComponent(
  props: TIssueActivityBlockComponent
) {
  const { icon, activityId, ends, children, customUserName } = props;
  // hooks
  const {
    activity: { getActivityById },
  } = useIssueDetail();
  const { calendarSystem } = useUserProfile();

  const activity = getActivityById(activityId);
  const { isMobile } = usePlatformOS();
  if (!activity) return <></>;
  return (
    <ActivityTimelineItem
      icon={icon ?? <HierarchyOutline />}
      showConnector={ends !== "bottom"}
      actor={
        !activity?.field && activity?.verb === "created" ? (
          <IssueCreatorDisplay activityId={activityId} customUserName={customUserName} />
        ) : (
          <IssueUser activityId={activityId} customUserName={customUserName} />
        )
      }
      timestamp={
        <ActivityTimelineTimestamp
          tooltip={`${renderFormattedDate(activity.created_at, undefined, calendarSystem)}, ${renderFormattedTime(activity.created_at)}`}
          disableTooltip={isMobile}
        >
          {calculateTimeAgo(activity.created_at, calendarSystem)}
        </ActivityTimelineTimestamp>
      }
    >
      {children}
    </ActivityTimelineItem>
  );
});
