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
          "font-mono shadow-2xs flex h-5 items-center gap-1 rounded-full border px-1.5 py-0.5 text-[11px] font-semibold transition",
          isTicking
            ? "border-subtle bg-warning-subtle text-success-primary"
            : "border-subtle bg-warning-subtle text-warning-primary",
          className
        )}
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

        <span className="font-mono text-[10px] font-bold tracking-tight">
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
                className="rounded-full p-0.5 text-warning-primary transition hover:bg-layer-2-hover"
              >
                <Pause className="size-2.5 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleStartOrResume}
                title="ادامه تایمر"
                className="rounded-full p-0.5 text-success-primary transition hover:bg-layer-2-hover"
              >
                <Play className="size-2.5 fill-current" />
              </button>
            )}

            {/* Stop button */}
            <button
              type="button"
              onClick={handleStop}
              title="توقف و ثبت زمان"
              className="rounded-full p-0.5 text-danger-primary transition hover:bg-layer-2-hover"
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
        "flex h-5 items-center gap-1 rounded-sm border-[0.5px] border-strong px-1.5 py-0.5 text-caption-sm-regular text-placeholder transition hover:border-subtle hover:bg-layer-1 hover:text-primary",
        className
      )}
    >
      <Clock className="size-3 text-placeholder" />
      <Play className="size-2.5 fill-current text-success-primary" />
    </button>
  );
};
