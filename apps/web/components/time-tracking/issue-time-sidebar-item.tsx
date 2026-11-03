/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useCallback, useEffect, useState } from "react";
import { Play, Pause, Square, History, Clock } from "lucide-react";
import { cn } from "@plane/utils";
import type { TIssueWorklogsResponse } from "@plane/types";
import { timeTrackingService } from "@/services/time-tracking.service";
import { useTimeTracking } from "@/hooks/use-time-tracking";

const formatSecondsCompact = (totalSecs: number) => {
  if (totalSecs <= 0) return "0 دقیقه";
  const hrs = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  if (hrs > 0) return `${hrs}س ${mins}د`;
  return `${mins} دقیقه`;
};

const formatTimerClock = (totalSecs: number) => {
  const hrs = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;
  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
  onOpenDetails?: () => void;
};

export const IssueTimeSidebarItem: React.FC<Props> = ({
  workspaceSlug,
  projectId,
  issueId,
  disabled = false,
  onOpenDetails,
}) => {
  const [data, setData] = useState<TIssueWorklogsResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const { getRunningTimer, startTimer, pauseTimer, stopTimer } = useTimeTracking(workspaceSlug);

  const runningTimer = getRunningTimer(issueId);
  const isTicking = Boolean(runningTimer && runningTimer.is_running && !runningTimer.is_paused);
  const isPaused = Boolean(runningTimer && runningTimer.is_paused);
  const hasActive = Boolean(runningTimer);

  const fetchWorklogs = useCallback(async () => {
    if (!workspaceSlug || !projectId || !issueId) return;
    try {
      setLoading(true);
      const res = await timeTrackingService.getIssueWorklogs(workspaceSlug, projectId, issueId);
      setData(res);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [workspaceSlug, projectId, issueId]);

  useEffect(() => {
    fetchWorklogs();

    const handleTimerChange = () => {
      fetchWorklogs();
    };
    window.addEventListener("plane_timer_change", handleTimerChange);

    return () => {
      window.removeEventListener("plane_timer_change", handleTimerChange);
    };
  }, [fetchWorklogs]);

  const handleStartOrResume = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (disabled) return;
    await startTimer(projectId, issueId);
    await fetchWorklogs();
  };

  const handlePause = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (disabled) return;
    await pauseTimer(projectId, issueId);
    await fetchWorklogs();
  };

  const handleStop = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (disabled) return;
    await stopTimer(projectId, issueId);
    await fetchWorklogs();
  };

  const baseCompletedSeconds = data?.completed_duration_seconds ?? data?.total_duration_seconds ?? 0;
  const currentSessionSeconds = runningTimer?.elapsed_seconds ?? 0;
  const totalDisplaySeconds = baseCompletedSeconds + currentSessionSeconds;

  return (
    <div className="flex w-full items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-1.5">
        {hasActive ? (
          <div
            className={cn(
              "font-mono text-xs flex items-center gap-1.5 rounded-full px-2 py-0.5 font-semibold",
              isTicking
                ? "border border-subtle bg-warning-subtle text-success-primary"
                : "border border-subtle bg-warning-subtle text-warning-primary"
            )}
            title={isTicking ? "تایمر در حال محاسبه است" : "تایمر متوقف موقت است"}
          >
            <span className="relative flex h-2 w-2">
              {isTicking ? (
                <>
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success-primary opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-success-primary"></span>
                </>
              ) : (
                <span className="relative inline-flex h-2 w-2 rounded-full bg-warning-primary"></span>
              )}
            </span>
            <span>{formatTimerClock(currentSessionSeconds)}</span>
          </div>
        ) : (
          <span className="text-body-xs truncate font-medium text-secondary">
            {formatSecondsCompact(totalDisplaySeconds)}
          </span>
        )}
      </div>

      <div className="flex items-center gap-1">
        {!disabled && (
          <>
            {hasActive ? (
              <>
                {/* Pause / Resume Button */}
                {isTicking ? (
                  <button
                    type="button"
                    onClick={handlePause}
                    title="توقف موقت تایمر"
                    className="shadow-2xs flex size-6 items-center justify-center rounded-md bg-warning-subtle text-warning-primary transition hover:opacity-80"
                  >
                    <Pause className="size-2.5 fill-current" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={handleStartOrResume}
                    title="ادامه تایمر"
                    className="shadow-2xs flex size-6 items-center justify-center rounded-md bg-success-subtle text-success-primary transition hover:opacity-80"
                  >
                    <Play className="ml-0.5 size-2.5 fill-current" />
                  </button>
                )}

                {/* Stop & Save Button */}
                <button
                  type="button"
                  onClick={handleStop}
                  title="ثبت و پایان تایمر"
                  className="shadow-2xs flex size-6 items-center justify-center rounded-md bg-danger-subtle text-danger-primary transition hover:bg-danger-subtle-hover"
                >
                  <Square className="size-2.5 fill-current" />
                </button>
              </>
            ) : (
              /* Start Button */
              <button
                type="button"
                onClick={handleStartOrResume}
                title="شروع تایمر زنده"
                className="shadow-2xs flex size-6 items-center justify-center rounded-md bg-success-subtle text-success-primary transition hover:opacity-80"
              >
                <Play className="ml-0.5 size-2.5 fill-current" />
              </button>
            )}
          </>
        )}

        {onOpenDetails && (
          <button
            type="button"
            onClick={onOpenDetails}
            title="مشاهده گزارشات و ثبت دستی"
            className="flex size-6 items-center justify-center rounded-md text-placeholder transition hover:bg-layer-2 hover:text-primary"
          >
            <History className="size-3.5" />
          </button>
        )}
      </div>
    </div>
  );
};
