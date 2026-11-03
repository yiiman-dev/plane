/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { IUserLite } from "./users";

export type TTimeTrackingLoggingPermission = "all_members" | "assignee_only" | "custom_members";
export type TTimeTrackingDefaultView = "grouped_by_date" | "grouped_by_user" | "timeline_intervals";

export type TProjectTimeTrackingSetting = {
  id: string;
  project: string;
  workspace: string;
  is_enabled: boolean;
  allow_overlap: boolean;
  overlap_allowed_members: string[];
  overlap_allowed_member_details?: IUserLite[];
  breaks_enabled: boolean;
  focus_duration_minutes: number;
  break_duration_minutes: number;
  logging_permission: TTimeTrackingLoggingPermission;
  custom_allowed_members: string[];
  custom_allowed_member_details?: IUserLite[];
  default_view: TTimeTrackingDefaultView;
  created_at: string;
  updated_at: string;
};

export type TIssueWorklog = {
  id: string;
  issue: string;
  project: string;
  workspace: string;
  user: string;
  user_detail?: IUserLite;
  start_time: string | null;
  end_time: string | null;
  duration_seconds: number;
  is_running: boolean;
  is_paused?: boolean;
  started_at: string | null;
  description: string;
  created_at: string;
  updated_at?: string;
};

export type TIssueWorklogItem = {
  id: string;
  user: IUserLite;
  duration_seconds: number;
  is_running: boolean;
  is_paused?: boolean;
  started_at: string | null;
  start_time: string | null;
  end_time: string | null;
  description: string;
  created_at: string;
};

export type TIssueWorklogsResponse = {
  completed_duration_seconds?: number;
  total_duration_seconds: number;
  can_log_time: boolean;
  default_view: TTimeTrackingDefaultView;
  is_time_tracking_enabled: boolean;
  active_timer?: {
    id: string;
    started_at: string | null;
    duration_seconds: number;
    elapsed_seconds?: number;
    is_running?: boolean;
    is_paused?: boolean;
  } | null;
  logs: TIssueWorklogItem[];
  grouped_by_date: {
    date: string;
    total_seconds: number;
    logs: TIssueWorklogItem[];
  }[];
  grouped_by_user: {
    user: IUserLite;
    total_seconds: number;
    logs: TIssueWorklogItem[];
  }[];
  intervals: TIssueWorklogItem[];
};

export type TActiveTimer = {
  id: string;
  issue_id: string;
  issue_name: string;
  issue_sequence_id: number;
  project_id: string;
  project_name: string;
  project_identifier: string;
  started_at: string | null;
  base_duration_seconds: number;
  elapsed_seconds: number;
  server_time: string;
  is_running: boolean;
  is_paused?: boolean;
  breaks_enabled: boolean;
  focus_duration_minutes: number;
  break_duration_minutes: number;
};
