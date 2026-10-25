/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useState } from "react";
import type { TActiveTimer } from "@plane/types";
import { timeTrackingService } from "@/services/time-tracking.service";

const TIMER_STORAGE_KEY = "plane_active_timers_cache";

export function useTimeTracking(workspaceSlug?: string) {
  const [activeTimers, setActiveTimers] = useState<TActiveTimer[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const cached = localStorage.getItem(TIMER_STORAGE_KEY);
        if (cached) return JSON.parse(cached);
      } catch {
        // ignore
      }
    }
    return [];
  });

  const [isLoading, setIsLoading] = useState(false);

  const fetchTimers = useCallback(async () => {
    if (!workspaceSlug) return;
    try {
      setIsLoading(true);
      const timers = await timeTrackingService.getActiveTimers(workspaceSlug);
      setActiveTimers(timers);
      if (typeof window !== "undefined") {
        localStorage.setItem(TIMER_STORAGE_KEY, JSON.stringify(timers));
      }
    } catch {
      // ignore
    } finally {
      setIsLoading(false);
    }
  }, [workspaceSlug]);

  // Tick every second to increment elapsed_seconds on active timers that are running (not paused)
  useEffect(() => {
    const hasRunningTimers = activeTimers.some((t) => t.is_running && !t.is_paused);
    if (!hasRunningTimers) return;

    const interval = setInterval(() => {
      setActiveTimers((prev) =>
        prev.map((timer) => {
          if (timer.is_running && !timer.is_paused) {
            return {
              ...timer,
              elapsed_seconds: timer.elapsed_seconds + 1,
            };
          }
          return timer;
        })
      );
    }, 1000);

    return () => clearInterval(interval);
  }, [activeTimers]);

  // Sync on mount and on global timer events
  useEffect(() => {
    fetchTimers();

    const handleTimerChange = () => {
      fetchTimers();
    };

    window.addEventListener("plane_timer_change", handleTimerChange);
    const syncInterval = setInterval(fetchTimers, 25000);

    return () => {
      window.removeEventListener("plane_timer_change", handleTimerChange);
      clearInterval(syncInterval);
    };
  }, [fetchTimers]);

  const startTimer = useCallback(
    async (projectId: string, issueId: string) => {
      if (!workspaceSlug) return;
      await timeTrackingService.startTimer(workspaceSlug, projectId, issueId);
      window.dispatchEvent(new CustomEvent("plane_timer_change", { detail: { action: "start", issueId } }));
      await fetchTimers();
    },
    [workspaceSlug, fetchTimers]
  );

  const pauseTimer = useCallback(
    async (projectId: string, issueId: string) => {
      if (!workspaceSlug) return;
      await timeTrackingService.pauseTimer(workspaceSlug, projectId, issueId);
      window.dispatchEvent(new CustomEvent("plane_timer_change", { detail: { action: "pause", issueId } }));
      await fetchTimers();
    },
    [workspaceSlug, fetchTimers]
  );

  const stopTimer = useCallback(
    async (projectId: string, issueId: string, description?: string) => {
      if (!workspaceSlug) return;
      await timeTrackingService.stopTimer(workspaceSlug, projectId, issueId, description);
      window.dispatchEvent(new CustomEvent("plane_timer_change", { detail: { action: "stop", issueId } }));
      await fetchTimers();
    },
    [workspaceSlug, fetchTimers]
  );

  const cancelTimer = useCallback(
    async (projectId: string, issueId: string) => {
      if (!workspaceSlug) return;
      await timeTrackingService.cancelTimer(workspaceSlug, projectId, issueId);
      window.dispatchEvent(new CustomEvent("plane_timer_change", { detail: { action: "cancel", issueId } }));
      await fetchTimers();
    },
    [workspaceSlug, fetchTimers]
  );

  const isTimerRunning = useCallback(
    (issueId: string) => activeTimers.some((t) => t.issue_id === issueId && t.is_running && !t.is_paused),
    [activeTimers]
  );

  const isTimerPaused = useCallback(
    (issueId: string) => activeTimers.some((t) => t.issue_id === issueId && t.is_paused),
    [activeTimers]
  );

  const getRunningTimer = useCallback(
    (issueId: string) => activeTimers.find((t) => t.issue_id === issueId),
    [activeTimers]
  );

  return {
    activeTimers,
    isLoading,
    isTimerRunning,
    isTimerPaused,
    getRunningTimer,
    startTimer,
    pauseTimer,
    stopTimer,
    cancelTimer,
    refetchTimers: fetchTimers,
  };
}
