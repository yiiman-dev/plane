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
  return `${hrs.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
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
      await timeTrackingService.stopTimer(workspaceSlug, stoppingTimer.project_id, stoppingTimer.issue_id, stopNote);
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
        className="shadow-2xl fixed z-[9999] transition-shadow select-none"
      >
        {isMinimized ? (
          /* Minimized floating pill: Draggable, with direct Pause/Resume and Stop keys */
          <div
            onMouseDown={handleMouseDown}
            onClick={() => {
              if (hasMovedRef.current) return;
              handleToggleMinimize();
            }}
            className="shadow-lg hover:shadow-xl flex cursor-move items-center gap-2 rounded-full border border-subtle bg-surface-1/95 px-3 py-1.5 text-primary backdrop-blur-md transition-all"
          >
            <GripVertical className="size-3.5 shrink-0 cursor-grab text-secondary/60 active:cursor-grabbing" />

            <span className="relative flex h-2.5 w-2.5 shrink-0">
              {isPrimaryRunning ? (
                <>
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success-primary opacity-75"></span>
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-success-primary"></span>
                </>
              ) : (
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-warning-primary"></span>
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
                className="rounded-full p-1 text-warning-primary transition hover:bg-layer-2-hover"
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
                className="rounded-full p-1 text-success-primary transition hover:bg-layer-2-hover"
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
              className="rounded-full p-1 text-danger-primary transition hover:bg-layer-2-hover"
              title="ثبت و پایان"
            >
              <Square className="size-3 fill-current" />
            </button>

            {activeTimers.length > 1 && (
              <span className="py-0.2 rounded-full bg-warning-subtle px-1.5 text-[10px] font-bold text-success-primary">
                +{activeTimers.length - 1}
              </span>
            )}

            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                handleToggleMinimize();
              }}
              className="rounded p-0.5 text-secondary transition hover:text-primary"
              title="مشاهده جزئیات تایمرها"
            >
              <ChevronUp className="size-3.5" />
            </button>
          </div>
        ) : (
          /* Expanded multi-timer widget */
          <div className="shadow-2xl w-84 space-y-3 rounded-2xl border border-subtle bg-surface-1/95 p-3.5 backdrop-blur-md sm:w-96">
            {/* Header bar with grab handle */}
            <div
              onMouseDown={handleMouseDown}
              className="flex cursor-move items-center justify-between border-b border-subtle pb-2 text-secondary"
            >
              <div className="flex items-center gap-2">
                <GripVertical className="size-4 cursor-grab text-placeholder active:cursor-grabbing" />
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success-primary opacity-75"></span>
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-success-primary"></span>
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
                  className="rounded p-1 text-secondary transition hover:bg-layer-2 hover:text-primary"
                  title="کوچک‌کردن"
                >
                  <ChevronDown className="size-4" />
                </button>
              </div>
            </div>

            {/* List of active running timers */}
            <div className="max-h-72 space-y-2 overflow-y-auto pr-0.5">
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
                          className="font-mono flex items-center gap-1.5 text-[11px] font-medium text-success-primary hover:underline"
                        >
                          <span>
                            {timer.project_identifier}-{timer.issue_sequence_id}
                          </span>
                          <ExternalLink className="size-2.5 opacity-0 transition group-hover:opacity-100" />
                        </a>
                        <p className="text-xs mt-0.5 line-clamp-1 font-medium text-primary" title={timer.issue_name}>
                          {timer.issue_name}
                        </p>
                      </div>

                      {/* Live ticking counter */}
                      <div className="flex-shrink-0 text-right">
                        <span
                          className={cn(
                            "font-mono text-sm font-bold tracking-tight",
                            isTimerTicking ? "text-success-primary" : "text-warning-primary"
                          )}
                        >
                          {formatTime(timer.elapsed_seconds)}
                        </span>
                        {!isTimerTicking && (
                          <div className="text-[10px] font-medium text-warning-primary">متوقف موقت</div>
                        )}
                      </div>
                    </div>

                    {/* Actions bar for this timer */}
                    <div className="mt-2 flex items-center justify-between gap-2 border-t border-subtle/50 pt-2">
                      <div className="flex items-center gap-1.5">
                        {/* Pause / Resume Button */}
                        {isTimerTicking ? (
                          <button
                            type="button"
                            onClick={() => handlePauseTimer(timer)}
                            className="flex items-center gap-1 rounded-md bg-warning-subtle px-2.5 py-1 text-[11px] font-medium text-warning-primary transition hover:bg-layer-2-hover"
                          >
                            <Pause className="size-3 fill-current" />
                            <span>توقف موقت</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => handleResumeTimer(timer)}
                            className="shadow-xs flex items-center gap-1 rounded-md bg-accent-primary px-2.5 py-1 text-[11px] font-medium text-on-color transition hover:bg-accent-primary/80"
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
                          className="flex items-center gap-1 rounded-md bg-danger-subtle px-2.5 py-1 text-[11px] font-medium text-danger-primary transition hover:bg-danger-subtle-hover"
                        >
                          <Square className="size-3 fill-current" />
                          <span>ثبت و پایان</span>
                        </button>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleCancelTimer(timer)}
                        className="rounded p-1 text-placeholder transition hover:bg-layer-2-hover hover:text-danger-primary"
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
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-backdrop p-4 backdrop-blur-sm">
          <div className="shadow-2xl animate-in zoom-in-95 w-full max-w-sm space-y-4 rounded-2xl border border-subtle bg-surface-1 p-5">
            <div className="flex items-center justify-between border-b border-subtle pb-3">
              <div>
                <h3 className="text-sm font-semibold text-primary">ثبت و ذخیره تایم کاری</h3>
                <p className="text-xs mt-0.5 line-clamp-1 text-secondary">{stoppingTimer.issue_name}</p>
              </div>
              <button
                onClick={() => setStoppingTimer(null)}
                className="rounded p-1 text-placeholder hover:text-primary"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="space-y-1 rounded-xl border border-subtle bg-surface-2 p-3 text-center">
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
                className="text-xs focus:ring-accent-primary h-20 w-full rounded-xl border border-subtle bg-surface-2 p-2.5 text-primary focus:ring-1 focus:outline-none"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setStoppingTimer(null)}
                className="text-xs rounded-lg px-3 py-1.5 font-medium text-secondary hover:bg-layer-2"
              >
                انصراف
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handleConfirmStop}
                className="text-xs rounded-lg bg-accent-primary px-4 py-1.5 font-medium text-on-color transition hover:bg-accent-primary/80 disabled:opacity-50"
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
