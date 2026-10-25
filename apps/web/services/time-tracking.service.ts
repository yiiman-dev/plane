/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type {
  TProjectTimeTrackingSetting,
  TIssueWorklog,
  TIssueWorklogsResponse,
  TActiveTimer,
} from "@plane/types";
import { APIService } from "@/services/api.service";

export class TimeTrackingService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  async getTimeTrackingSettings(
    workspaceSlug: string,
    projectId: string
  ): Promise<TProjectTimeTrackingSetting> {
    return this.get(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/time-tracking-settings/`
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async updateTimeTrackingSettings(
    workspaceSlug: string,
    projectId: string,
    data: Partial<TProjectTimeTrackingSetting>
  ): Promise<TProjectTimeTrackingSetting> {
    return this.patch(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/time-tracking-settings/`,
      data
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async getIssueWorklogs(
    workspaceSlug: string,
    projectId: string,
    issueId: string
  ): Promise<TIssueWorklogsResponse> {
    return this.get(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/time-logs/`
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async createIssueWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    data: {
      duration_seconds?: number;
      hours?: number;
      minutes?: number;
      seconds?: number;
      description?: string;
      start_time?: string;
      end_time?: string;
    }
  ): Promise<TIssueWorklog> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/time-logs/`,
      data
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async updateIssueWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    worklogId: string,
    data: Partial<TIssueWorklog>
  ): Promise<TIssueWorklog> {
    return this.patch(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/time-logs/${worklogId}/`,
      data
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async deleteIssueWorklog(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    worklogId: string
  ): Promise<void> {
    return this.delete(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/time-logs/${worklogId}/`
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async startTimer(
    workspaceSlug: string,
    projectId: string,
    issueId: string
  ): Promise<{ worklog_id: string; started_at: string; duration_seconds: number }> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/time-logs/timer/start/`,
      {}
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async pauseTimer(
    workspaceSlug: string,
    projectId: string,
    issueId: string
  ): Promise<{ worklog_id: string; duration_seconds: number; elapsed_seconds: number; is_running: boolean; is_paused: boolean }> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/time-logs/timer/pause/`,
      {}
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async stopTimer(
    workspaceSlug: string,
    projectId: string,
    issueId: string,
    description?: string
  ): Promise<TIssueWorklog> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/time-logs/timer/stop/`,
      { description }
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async cancelTimer(
    workspaceSlug: string,
    projectId: string,
    issueId: string
  ): Promise<void> {
    return this.post(
      `/api/workspaces/${workspaceSlug}/projects/${projectId}/issues/${issueId}/time-logs/timer/cancel/`,
      {}
    )
      .then((res) => res?.data)
      .catch((err) => {
        throw err?.response?.data;
      });
  }

  async getActiveTimer(workspaceSlug: string): Promise<TActiveTimer | null> {
    return this.get(`/api/workspaces/${workspaceSlug}/time-logs/active-timer/`)
      .then((res) => res?.data?.active_timer ?? null)
      .catch(() => null);
  }

  async getActiveTimers(workspaceSlug: string): Promise<TActiveTimer[]> {
    return this.get(`/api/workspaces/${workspaceSlug}/time-logs/active-timer/`)
      .then((res) => {
        if (Array.isArray(res?.data?.active_timers)) {
          return res.data.active_timers;
        }
        if (res?.data?.active_timer) {
          return [res.data.active_timer];
        }
        return [];
      })
      .catch(() => []);
  }
}

export const timeTrackingService = new TimeTrackingService();
