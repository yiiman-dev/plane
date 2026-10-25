/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Play,
  Pause,
  Square,
  X,
  GripVertical,
  Clock,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  ExternalLink,
} from "lucide-react";
import { cn, generateWorkItemLink } from "@plane/utils";
import type { TActiveTimer } from "@plane/types";
import { timeTrackingService } from "@/services/time-tracking.service";

// Format seconds to HH:MM:SS
const formatTime = (totalSecs: number) => {
  const hrs = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;
  return `${hrs.toString().padStart(2, "0")}:${mins
    .toString()
    .padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

type Props = {
  workspaceSlug: string;
};

export const FloatingTimerWidget: React.FC<Props> = ({ workspaceSlug }) => {
  const [activeTimers, setActiveTimers] = useState<TActiveTimer[]>([]);
  const [isMinimized, setIsMinimized] = useState<boolean>(() => {
    if (typeof window !== "undefined") {
      return localStorage.getItem("plane_floating_timer_minimized") === "true";
    }
    return false;
  });

  const [stoppingTimer, setStoppingTimer] = useState<TActiveTimer | null>(null);
  const [stopNote, setStopNote] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Draggable position
  const [position, setPosition] = useState<{ x: number; y: number }>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("plane_floating_timer_pos");
      if (saved) {
        try {
          return JSON.parse(saved);
        } catch {
          // fallback
        }
      }
      return { x: Math.max(20, window.innerWidth - 380), y: Math.max(20, window.innerHeight - 280) };
    }
    return { x: 50, y: 50 };
  });

  const isDraggingRef = useRef(false);
  const hasMovedRef = useRef(false);
  const dragStartRef = useRef<{ startX: number; startY: number; posX: number; posY: number }>({
    startX: 0,
    startY: 0,
    posX: 0,
    posY: 0,
  });

  // Fetch active timers from server
  const fetchActiveTimers = useCallback(async () => {
    if (!workspaceSlug) return;
    try {
      const timers = await timeTrackingService.getActiveTimers(workspaceSlug);
      setActiveTimers(timers);
    } catch {
      // ignore
    }
  }, [workspaceSlug]);

  // Tick elapsed seconds every 1s for running timers that are not paused
  useEffect(() => {
    const hasRunning = activeTimers.some((t) => t.is_running && !t.is_paused);
    if (!hasRunning) return;

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

  // Sync timers with backend on mount, custom event, and polling
  useEffect(() => {
    fetchActiveTimers();

    const handleTimerChange = () => {
      fetchActiveTimers();
    };

    window.addEventListener("plane_timer_change", handleTimerChange);
    const syncInterval = setInterval(fetchActiveTimers, 20000);

    return () => {
      window.removeEventListener("plane_timer_change", handleTimerChange);
      clearInterval(syncInterval);
    };
  }, [fetchActiveTimers]);

  // Save minimize state
  const handleToggleMinimize = () => {
    setIsMinimized((prev) => {
      const next = !prev;
      if (typeof window !== "undefined") {
        localStorage.setItem("plane_floating_timer_minimized", String(next));
      }
      return next;
    });
  };

  // Drag handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    isDraggingRef.current = true;
    hasMovedRef.current = false;
    dragStartRef.current = {
      startX: e.clientX,
      startY: e.clientY,
      posX: position.x,
      posY: position.y,
    };

    const handleMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const deltaX = moveEvent.clientX - dragStartRef.current.startX;
      const deltaY = moveEvent.clientY - dragStartRef.current.startY;

      if (Math.hypot(deltaX, deltaY) > 4) {
        hasMovedRef.current = true;
      }

      const widgetWidth = isMinimized ? 240 : 380;
      const widgetHeight = isMinimized ? 44 : 340;

      const newX = Math.max(10, Math.min(window.innerWidth - widgetWidth, dragStartRef.current.posX + deltaX));
      const newY = Math.max(10, Math.min(window.innerHeight - widgetHeight, dragStartRef.current.posY + deltaY));

      setPosition({ x: newX, y: newY });
    };

    const handleMouseUp = () => {
      isDraggingRef.current = false;
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      localStorage.setItem("plane_floating_timer_pos", JSON.stringify(position));
    };

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  };

  // Pause a timer
  const handlePauseTimer = async (timer: TActiveTimer) => {
    try {
      await timeTrackingService.pauseTimer(workspaceSlug, timer.project_id, timer.issue_id);
      window.dispatchEvent(new CustomEvent("plane_timer_change"));
      await fetchActiveTimers();
    } catch {
      // ignore
    }
  };

  // Resume a paused timer
  const handleResumeTimer = async (timer: TActiveTimer) => {
    try {
      await timeTrackingService.startTimer(workspaceSlug, timer.project_id, timer.issue_id);
      window.dispatchEvent(new CustomEvent("plane_timer_change"));
      await fetchActiveTimers();
    } catch {
      // ignore
    }
  };

  // Stop a specific timer
  const handleConfirmStop = async () => {
    if (!stoppingTimer) return;
    try {
      setIsSubmitting(true);
      await timeTrackingService.stopTimer(
        workspaceSlug,
        stoppingTimer.project_id,
        stoppingTimer.issue_id,
        stopNote
      );
      setStoppingTimer(null);
      setStopNote("");
      window.dispatchEvent(new CustomEvent("plane_timer_change"));
      await fetchActiveTimers();
    } catch {
      // ignore
    } finally {
      setIsSubmitting(false);
    }
  };

  // Cancel / delete a timer
  const handleCancelTimer = async (timer: TActiveTimer) => {
    if (!window.confirm(`آیا از لغو تایمر تسک «${timer.issue_name}» اطمینان دارید؟`)) return;
    try {
      await timeTrackingService.cancelTimer(workspaceSlug, timer.project_id, timer.issue_id);
      window.dispatchEvent(new CustomEvent("plane_timer_change"));
      await fetchActiveTimers();
    } catch {
      // ignore
    }
  };

  if (activeTimers.length === 0) {
    return null;
  }

  const primaryTimer = activeTimers[0];
  const isPrimaryRunning = primaryTimer.is_running && !primaryTimer.is_paused;

  return (
    <>
      <div
        style={{ left: `${position.x}px`, top: `${position.y}px` }}
        className="fixed z-[9999] select-none shadow-2xl transition-shadow"
      >
        {isMinimized ? (
          /* Minimized floating pill: Draggable, with direct Pause/Resume and Stop keys */
          <div
            onMouseDown={handleMouseDown}
            onClick={() => {
              if (hasMovedRef.current) return;
              handleToggleMinimize();
            }}
            className="flex items-center gap-2 px-3 py-1.5 rounded-full border border-subtle bg-surface-1/95 backdrop-blur-md shadow-lg cursor-move hover:shadow-xl transition-all text-primary"
          >
            <GripVertical className="size-3.5 text-secondary/60 cursor-grab active:cursor-grabbing shrink-0" />

            <span className="relative flex h-2.5 w-2.5 shrink-0">
              {isPrimaryRunning ? (
                <>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success-primary opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-success-primary"></span>
                </>
              ) : (
                <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-warning-primary"></span>
              )}
            </span>

            <span className="font-mono text-xs font-semibold tracking-wide">
              {formatTime(primaryTimer.elapsed_seconds)}
            </span>

            {/* Quick Pause / Resume Button */}
            {isPrimaryRunning ? (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handlePauseTimer(primaryTimer);
                }}
                className="p-1 rounded-full hover:bg-layer-2-hover text-warning-primary transition"
                title="توقف موقت"
              >
                <Pause className="size-3.5 fill-current" />
              </button>
            ) : (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleResumeTimer(primaryTimer);
                }}
                className="p-1 rounded-full hover:bg-layer-2-hover text-success-primary transition"
                title="ادامه تایمر"
              >
                <Play className="size-3.5 fill-current" />
              </button>
            )}

            {/* Quick Stop Button */}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setStoppingTimer(primaryTimer);
                setStopNote("");
              }}
              className="p-1 rounded-full hover:bg-layer-2-hover text-danger-primary transition"
              title="ثبت و پایان"
            >
              <Square className="size-3 fill-current" />
            </button>

            {activeTimers.length > 1 && (
              <span className="rounded-full bg-warning-subtle px-1.5 py-0.2 text-[10px] font-bold text-success-primary">
                +{activeTimers.length - 1}
              </span>
            )}

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleToggleMinimize();
              }}
              className="p-0.5 rounded text-secondary hover:text-primary transition"
              title="مشاهده جزئیات تایمرها"
            >
              <ChevronUp className="size-3.5" />
            </button>
          </div>
        ) : (
          /* Expanded multi-timer widget */
          <div className="w-84 sm:w-96 rounded-2xl border border-subtle bg-surface-1/95 backdrop-blur-md p-3.5 shadow-2xl space-y-3">
            {/* Header bar with grab handle */}
            <div
              onMouseDown={handleMouseDown}
              className="flex items-center justify-between cursor-move pb-2 border-b border-subtle text-secondary"
            >
              <div className="flex items-center gap-2">
                <GripVertical className="size-4 text-placeholder cursor-grab active:cursor-grabbing" />
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success-primary opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-success-primary"></span>
                </span>
                <span className="text-xs font-semibold text-primary">تایمرهای فعال</span>
                <span className="rounded-full bg-warning-subtle px-1.5 py-0.5 text-[10px] font-bold text-success-primary">
                  {activeTimers.length}
                </span>
              </div>

              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={handleToggleMinimize}
                  className="p-1 rounded hover:bg-layer-2 text-secondary hover:text-primary transition"
                  title="کوچک‌کردن"
                >
                  <ChevronDown className="size-4" />
                </button>
              </div>
            </div>

            {/* List of active running timers */}
            <div className="max-h-72 overflow-y-auto space-y-2 pr-0.5">
              {activeTimers.map((timer) => {
                const workItemUrl = generateWorkItemLink({
                  workspaceSlug,
                  projectId: timer.project_id,
                  issueId: timer.issue_id,
                  projectIdentifier: timer.project_identifier,
                  sequenceId: timer.issue_sequence_id,
                });

                const isTimerTicking = timer.is_running && !timer.is_paused;

                return (
                  <div
                    key={timer.id}
                    className="group rounded-xl border border-subtle bg-surface-2 p-2.5 transition hover:border-subtle"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <a
                          href={workItemUrl}
                          className="flex items-center gap-1.5 text-[11px] font-mono font-medium text-success-primary hover:underline"
                        >
                          <span>
                            {timer.project_identifier}-{timer.issue_sequence_id}
                          </span>
                          <ExternalLink className="size-2.5 opacity-0 group-hover:opacity-100 transition" />
                        </a>
                        <p className="line-clamp-1 text-xs font-medium text-primary mt-0.5" title={timer.issue_name}>
                          {timer.issue_name}
                        </p>
                      </div>

                      {/* Live ticking counter */}
                      <div className="text-right flex-shrink-0">
                        <span
                          className={cn(
                            "font-mono text-sm font-bold tracking-tight",
                            isTimerTicking
                              ? "text-success-primary"
                              : "text-warning-primary"
                          )}
                        >
                          {formatTime(timer.elapsed_seconds)}
                        </span>
                        {!isTimerTicking && (
                          <div className="text-[10px] text-warning-primary font-medium">متوقف موقت</div>
                        )}
                      </div>
                    </div>

                    {/* Actions bar for this timer */}
                    <div className="flex items-center justify-between gap-2 mt-2 pt-2 border-t border-subtle/50">
                      <div className="flex items-center gap-1.5">
                        {/* Pause / Resume Button */}
                        {isTimerTicking ? (
                          <button
                            type="button"
                            onClick={() => handlePauseTimer(timer)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-warning-subtle hover:bg-layer-2-hover text-warning-primary text-[11px] font-medium transition"
                          >
                            <Pause className="size-3 fill-current" />
                            <span>توقف موقت</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleResumeTimer(timer)}
                            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-accent-primary hover:bg-accent-primary/80 text-on-color text-[11px] font-medium transition shadow-xs"
                          >
                            <Play className="size-3 fill-current" />
                            <span>ادامه</span>
                          </button>
                        )}

                        {/* Stop & Save Button */}
                        <button
                          type="button"
                          onClick={() => {
                            setStoppingTimer(timer);
                            setStopNote("");
                          }}
                          className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-danger-subtle hover:bg-danger-subtle-hover text-danger-primary text-[11px] font-medium transition"
                        >
                          <Square className="size-3 fill-current" />
                          <span>ثبت و پایان</span>
                        </button>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleCancelTimer(timer)}
                        className="p-1 rounded text-placeholder hover:text-danger-primary hover:bg-layer-2-hover transition"
                        title="لغو تایمر بدون ذخیره"
                      >
                        <RotateCcw className="size-3.5" />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Stop & Save Modal */}
      {stoppingTimer && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-backdrop backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl border border-subtle bg-surface-1 p-5 shadow-2xl space-y-4 animate-in zoom-in-95">
            <div className="flex items-center justify-between border-b border-subtle pb-3">
              <div>
                <h3 className="text-sm font-semibold text-primary">ثبت و ذخیره تایم کاری</h3>
                <p className="text-xs text-secondary mt-0.5 line-clamp-1">{stoppingTimer.issue_name}</p>
              </div>
              <button
                onClick={() => setStoppingTimer(null)}
                className="p-1 rounded text-placeholder hover:text-primary"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="rounded-xl border border-subtle bg-surface-2 p-3 text-center space-y-1">
              <div className="text-xs text-secondary">مدت زمان سپری شده:</div>
              <div className="font-mono text-2xl font-bold text-success-primary">
                {formatTime(stoppingTimer.elapsed_seconds)}
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-medium text-secondary">یادداشت / گزارش کار (اختیاری):</label>
              <textarea
                value={stopNote}
                onChange={(e) => setStopNote(e.target.value)}
                placeholder="توضیح مختصری درباره کار انجام‌شده بنویسید..."
                className="w-full h-20 rounded-xl border border-subtle bg-surface-2 p-2.5 text-xs text-primary focus:outline-none focus:ring-1 focus:ring-accent-primary"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setStoppingTimer(null)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-secondary hover:bg-layer-2"
              >
                انصراف
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleConfirmStop}
                className="px-4 py-1.5 rounded-lg bg-accent-primary hover:bg-accent-primary/80 text-on-color text-xs font-medium transition disabled:opacity-50"
              >
                {isSubmitting ? "در حال ذخیره..." : "ثبت لاگ زمان"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
