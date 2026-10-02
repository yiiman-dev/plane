/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import { observer } from "mobx-react";
// plane imports
import type { TNotification } from "@plane/types";
import {
  convertMinutesToHoursMinutesString,
  renderFormattedDate,
  sanitizeCommentForNotification,
  stripAndTruncateHTML,
} from "@plane/utils";
import type { CalendarSystem } from "@plane/blocks/property-select";
// hooks
import { useUserProfile } from "@/hooks/store/user";
// components
import { LiteTextEditor } from "@/components/editor/lite-text";
import {
  ADDITIONAL_NOTIFICATION_CONTENT_MAP,
  renderAdditionalAction,
  renderAdditionalValue,
  shouldShowConnector,
} from "../../notification-card/content";

// Types
export type TNotificationFieldData = {
  field: string | undefined;
  newValue: string | undefined;
  oldValue: string | undefined;
  verb: string | undefined;
};

export type TNotificationContentDetails = {
  action?: ReactNode;
  value?: ReactNode;
  showConnector?: boolean;
};

// Handlers are module-level constants, so the calendar system is threaded in as a trailing argument
// rather than read from the store. `renderCommentBox` already occupied the second slot, so the
// system goes third. Both are optional to keep existing CE/EE handlers assignable.
export type TNotificationContentHandler = (
  data: TNotificationFieldData,
  renderCommentBox?: boolean,
  calendarSystem?: CalendarSystem
) => TNotificationContentDetails | null;

export type TNotificationContentMap = {
  [key: string]: TNotificationContentHandler;
};

// Base notification content map for core fields
export const BASE_NOTIFICATION_CONTENT_MAP: TNotificationContentMap = {
  duplicate: ({ verb }) => ({
    action:
      verb === "created"
        ? "marked that this work item is a duplicate of"
        : "marked that this work item is not a duplicate",
    value: null,
    showConnector: false,
  }),
  assignees: ({ newValue, oldValue }) => ({
    action: newValue !== "" ? "added assignee" : "removed assignee",
    value: newValue !== "" ? newValue : oldValue,
    showConnector: false,
  }),
  start_date: ({ newValue }, renderCommentBox, calendarSystem) => ({
    action: newValue !== "" ? "set start date" : "removed the start date",
    value: renderFormattedDate(newValue, undefined, calendarSystem),
    showConnector: false,
  }),
  target_date: ({ newValue }, renderCommentBox, calendarSystem) => ({
    action: newValue !== "" ? "set due date" : "removed the due date",
    value: renderFormattedDate(newValue, undefined, calendarSystem),
    showConnector: false,
  }),
  labels: ({ newValue, oldValue }) => ({
    action: newValue !== "" ? "added label" : "removed label",
    value: newValue !== "" ? newValue : oldValue,
    showConnector: false,
  }),
  parent: ({ newValue, oldValue }) => ({
    action: newValue !== "" ? "added parent" : "removed parent",
    value: newValue !== "" ? newValue : oldValue,
    showConnector: false,
  }),
  relates_to: () => ({
    action: "marked that this work item is related to",
    value: null,
    showConnector: true,
  }),
  comment: ({ newValue }, renderCommentBox?: boolean) => ({
    action: "commented",
    value: renderCommentBox ? null : sanitizeCommentForNotification(newValue),
    showConnector: false,
  }),
  archived_at: ({ newValue }) => ({
    action: newValue === "restore" ? "restored the work item" : "archived the work item",
    value: null,
    showConnector: false,
  }),
  None: () => ({
    action: null,
    value: "the work item and assigned it to you.",
    showConnector: false,
  }),
  // Fields below only define value - action falls through to default handler
  attachment: () => ({
    action: null,
    value: "the work item",
    showConnector: true,
  }),
  description: ({ newValue }) => ({
    value: stripAndTruncateHTML(newValue || "", 55),
    showConnector: true,
  }),
  estimate_time: ({ newValue, oldValue }) => ({
    value:
      newValue !== ""
        ? convertMinutesToHoursMinutesString(Number(newValue))
        : convertMinutesToHoursMinutesString(Number(oldValue)),
    showConnector: true,
  }),
};

// Helper to get content details from maps
const getNotificationContentDetails = (
  fieldData: TNotificationFieldData,
  renderCommentBox?: boolean,
  calendarSystem?: CalendarSystem
): TNotificationContentDetails | null => {
  const { field } = fieldData;
  if (!field) return null;

  // Check base map first. Every handler now takes the same trailing arguments — `renderCommentBox`
  // (used by `comment`) and `calendarSystem` (used by the date fields) — so no per-field special
  // casing is needed.
  const baseHandler = BASE_NOTIFICATION_CONTENT_MAP[field];
  if (baseHandler) {
    return baseHandler(fieldData, renderCommentBox, calendarSystem);
  }

  // Check additional map from plane-web (EE extensions)
  const additionalHandler = ADDITIONAL_NOTIFICATION_CONTENT_MAP[field];
  if (additionalHandler) {
    return additionalHandler(fieldData, renderCommentBox, calendarSystem);
  }

  return null;
};

// Wrapped in `observer` because the profile store loads asynchronously: `NotificationContent` reads
// `calendarSystem` to build the date fields' `value`, and without a subscription it would keep
// rendering Gregorian dates if the profile landed after the notification list mounted.
export const NotificationContent = observer(function NotificationContent({
  notification,
  workspaceId,
  workspaceSlug,
  projectId,
  renderCommentBox = false,
}: {
  notification: TNotification;
  workspaceId: string;
  workspaceSlug: string;
  projectId: string;
  renderCommentBox?: boolean;
}) {
  const { calendarSystem } = useUserProfile();
  const { data, triggered_by_details: triggeredBy } = notification;
  const notificationField = data?.issue_activity.field;
  const newValue = data?.issue_activity.new_value;
  const oldValue = data?.issue_activity.old_value;
  const verb = data?.issue_activity.verb;

  const fieldData: TNotificationFieldData = {
    field: notificationField,
    newValue,
    oldValue,
    verb,
  };

  const renderTriggerName = () => (
    <span className="font-medium text-primary">
      {triggeredBy?.is_bot ? triggeredBy.first_name : triggeredBy?.display_name}{" "}
    </span>
  );

  // Get content details from map
  const contentDetails = getNotificationContentDetails(fieldData, renderCommentBox, calendarSystem);

  // Render action - use map value if defined, otherwise fall through to default handler
  // Note: undefined = fall through to default, null = explicitly no action text
  const renderAction = (): ReactNode => {
    if (!notificationField) return "";
    // Check if action is explicitly defined in map (including null)
    if (contentDetails && "action" in contentDetails) return contentDetails.action;
    // Fallback to default action handler for fields not in map or without action defined
    return renderAdditionalAction(notificationField, verb);
  };

  // Render value - use map value if defined, otherwise fall through to default handler
  const renderValue = (): ReactNode => {
    // Check if value is explicitly defined in map
    if (contentDetails && "value" in contentDetails) return contentDetails.value;
    // Fallback to default value handler for fields not in map or without value defined
    return renderAdditionalValue(notificationField, newValue, oldValue);
  };

  // Determine if connector should be shown - prefer map value, fallback to function
  const showConnector =
    contentDetails?.showConnector !== undefined ? contentDetails.showConnector : shouldShowConnector(notificationField);

  return (
    <>
      {renderTriggerName()}
      <span className="text-tertiary">{renderAction()} </span>
      {verb !== "deleted" && (
        <>
          {showConnector && <span className="text-tertiary">to </span>}
          <span className="font-medium text-primary">{renderValue()}</span>
          {notificationField === "comment" && renderCommentBox && (
            <div className="origin-left scale-75">
              <LiteTextEditor
                editable={false}
                id=""
                initialValue={newValue ?? ""}
                workspaceId={workspaceId}
                workspaceSlug={workspaceSlug}
                projectId={projectId}
                displayConfig={{
                  fontSize: "small-font",
                }}
              />
            </div>
          )}
          {"."}
        </>
      )}
    </>
  );
});
