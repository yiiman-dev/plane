/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import { Play, Pause, Square, Clock } from "lucide-react";
import { cn } from "@plane/utils";
import { useTimeTracking } from "@/hooks/use-time-tracking";

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
  className?: string;
};

export const IssueCardTimerButton: React.FC<Props> = ({
  workspaceSlug,
  projectId,
  issueId,
  disabled = false,
  className,
}) => {
  const { getRunningTimer, startTimer, pauseTimer, stopTimer } = useTimeTracking(workspaceSlug);

  const runningTimer = getRunningTimer(issueId);
  const isTicking = Boolean(runningTimer && runningTimer.is_running && !runningTimer.is_paused);
  const isPaused = Boolean(runningTimer && runningTimer.is_paused);
  const hasActive = Boolean(runningTimer);

  const handleStartOrResume = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (disabled) return;
    await startTimer(projectId, issueId);
  };

  const handlePause = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (disabled) return;
    await pauseTimer(projectId, issueId);
  };

  const handleStop = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (disabled) return;
    await stopTimer(projectId, issueId);
  };

  if (hasActive) {
    return (
      <div
        className={cn(
          "flex h-5 items-center gap-1 rounded-full border px-1.5 py-0.5 font-mono text-[11px] font-semibold transition shadow-2xs",
          isTicking
            ? "border-subtle bg-warning-subtle text-success-primary"
            : "border-subtle bg-warning-subtle text-warning-primary",
          className
        )}
      >
        <span className="relative flex h-2 w-2">
          {isTicking ? (
            <>
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success-primary opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-success-primary"></span>
            </>
          ) : (
            <span className="relative inline-flex rounded-full h-2 w-2 bg-warning-primary"></span>
          )}
        </span>

        <span className="text-[10px] font-mono font-bold tracking-tight">
          {formatTimerClock(runningTimer?.elapsed_seconds ?? 0)}
        </span>

        {/* Pause or Resume button */}
        {!disabled && (
          <>
            {isTicking ? (
              <button
                type="button"
                onClick={handlePause}
                title="توقف موقت تایمر"
                className="p-0.5 rounded-full hover:bg-layer-2-hover text-warning-primary transition"
              >
                <Pause className="size-2.5 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleStartOrResume}
                title="ادامه تایمر"
                className="p-0.5 rounded-full hover:bg-layer-2-hover text-success-primary transition"
              >
                <Play className="size-2.5 fill-current" />
              </button>
            )}

            {/* Stop button */}
            <button
              type="button"
              onClick={handleStop}
              title="توقف و ثبت زمان"
              className="p-0.5 rounded-full hover:bg-layer-2-hover text-danger-primary transition"
            >
              <Square className="size-2 fill-current" />
            </button>
          </>
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={handleStartOrResume}
      title="شروع ثبت زمان برای این تسک"
      className={cn(
        "flex h-5 items-center gap-1 rounded-sm border-[0.5px] border-strong px-1.5 py-0.5 text-placeholder hover:text-primary hover:bg-layer-1 hover:border-subtle transition text-caption-sm-regular",
        className
      )}
    >
      <Clock className="size-3 text-placeholder" />
      <Play className="size-2.5 fill-current text-success-primary" />
    </button>
  );
};
