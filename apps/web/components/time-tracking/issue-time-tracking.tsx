/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React, { useCallback, useEffect, useState } from "react";
import {
  Clock,
  Play,
  Pause,
  Square,
  Plus,
  Calendar,
  Users,
  ListFilter,
  Trash2,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  X,
} from "lucide-react";
import { cn } from "@plane/utils";
import type { TIssueWorklogsResponse, TTimeTrackingDefaultView, TIssueWorklogItem } from "@plane/types";
import { timeTrackingService } from "@/services/time-tracking.service";
import { useTimeTracking } from "@/hooks/use-time-tracking";

const formatSeconds = (totalSecs: number) => {
  if (totalSecs <= 0) return "0 دقیقه";
  const hrs = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;
  if (hrs > 0) {
    return `${hrs} ساعت ${mins > 0 ? `و ${mins} دقیقه` : ""}`;
  }
  if (mins > 0) {
    return `${mins} دقیقه ${secs > 0 ? `و ${secs} ثانیه` : ""}`;
  }
  return `${secs} ثانیه`;
};

const formatTimerClock = (totalSecs: number) => {
  const hrs = Math.floor(totalSecs / 3600);
  const mins = Math.floor((totalSecs % 3600) / 60);
  const secs = totalSecs % 60;
  return `${hrs.toString().padStart(2, "0")}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
};

type Props = {
  workspaceSlug: string;
  projectId: string;
  issueId: string;
  disabled?: boolean;
};

export const IssueTimeTracking: React.FC<Props> = ({ workspaceSlug, projectId, issueId, disabled = false }) => {
  const [data, setData] = useState<TIssueWorklogsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeView, setActiveView] = useState<TTimeTrackingDefaultView>("grouped_by_date");
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [isManualModalOpen, setIsManualModalOpen] = useState<boolean>(false);
  const [isStopModalOpen, setIsStopModalOpen] = useState<boolean>(false);
  const [stopNote, setStopNote] = useState<string>("");
  const [hours, setHours] = useState<number>(0);
  const [minutes, setMinutes] = useState<number>(30);
  const [description, setDescription] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { isTimerRunning, isTimerPaused, getRunningTimer, startTimer, pauseTimer, stopTimer } =
    useTimeTracking(workspaceSlug);

  const runningTimer = getRunningTimer(issueId);
  const isRunning = Boolean(runningTimer && runningTimer.is_running && !runningTimer.is_paused);
  const isPaused = Boolean(runningTimer && runningTimer.is_paused);
  const hasActiveSession = Boolean(runningTimer);
  const currentSessionSeconds = runningTimer?.elapsed_seconds ?? 0;

  // Real-time synced total duration
  const baseCompletedSeconds = data?.completed_duration_seconds ?? data?.total_duration_seconds ?? 0;
  const liveTotalSeconds = baseCompletedSeconds + currentSessionSeconds;

  const fetchWorklogs = useCallback(async () => {
    if (!workspaceSlug || !projectId || !issueId) return;
    try {
      setLoading(true);
      const res = await timeTrackingService.getIssueWorklogs(workspaceSlug, projectId, issueId);
      setData(res);
      if (res.default_view) {
        setActiveView(res.default_view);
      }
    } catch (err: any) {
      if (err?.error) {
        setErrorMessage(err.error);
      }
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

  const handleStartOrResume = async () => {
    if (disabled) return;
    try {
      setErrorMessage(null);
      await startTimer(projectId, issueId);
      await fetchWorklogs();
    } catch (err: any) {
      setErrorMessage(err?.error || "خطا در شروع تایمر");
    }
  };

  const handlePause = async () => {
    if (disabled) return;
    try {
      setErrorMessage(null);
      await pauseTimer(projectId, issueId);
      await fetchWorklogs();
    } catch (err: any) {
      setErrorMessage(err?.error || "خطا در توقف موقت تایمر");
    }
  };

  const handleConfirmStop = async () => {
    if (disabled) return;
    try {
      setIsSubmitting(true);
      setErrorMessage(null);
      await stopTimer(projectId, issueId, stopNote);
      setIsStopModalOpen(false);
      setStopNote("");
      await fetchWorklogs();
    } catch (err: any) {
      setErrorMessage(err?.error || "خطا در پایان دادن به تایمر");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleManualLog = async (e: React.FormEvent) => {
    e.preventDefault();
    const durationSeconds = (Number(hours) || 0) * 3600 + (Number(minutes) || 0) * 60;
    if (durationSeconds <= 0) return;

    try {
      setIsSubmitting(true);
      setErrorMessage(null);
      await timeTrackingService.createIssueWorklog(workspaceSlug, projectId, issueId, {
        duration_seconds: durationSeconds,
        description,
      });
      setIsManualModalOpen(false);
      setHours(0);
      setMinutes(30);
      setDescription("");
      await fetchWorklogs();
      window.dispatchEvent(new CustomEvent("plane_timer_change"));
    } catch (err: any) {
      setErrorMessage(err?.error || "خطا در ثبت زمان");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteWorklog = async (logId: string) => {
    if (!window.confirm("آیا از حذف این لاگ زمانی اطمینان دارید؟")) return;
    try {
      await timeTrackingService.deleteIssueWorklog(workspaceSlug, projectId, issueId, logId);
      await fetchWorklogs();
      window.dispatchEvent(new CustomEvent("plane_timer_change"));
    } catch (err: any) {
      setErrorMessage(err?.error || "خطا در حذف لاگ");
    }
  };

  return (
    <div className="shadow-2xs w-full rounded-xl border border-subtle bg-surface-1 p-3.5 transition">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="flex size-7 items-center justify-center rounded-lg bg-warning-subtle text-success-primary">
            <Clock className="size-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-primary">ثبت زمان کاری</span>
              {/* Real-time synced badge */}
              <span className="font-mono text-xs rounded-full bg-warning-subtle px-2 py-0.5 font-bold text-success-primary">
                {formatSeconds(liveTotalSeconds)}
              </span>
            </div>
            {hasActiveSession && (
              <div className="font-mono mt-0.5 flex items-center gap-1.5 text-[11px] font-medium">
                <span className="relative flex h-2 w-2">
                  {isRunning ? (
                    <>
                      <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success-primary opacity-75"></span>
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-success-primary"></span>
                    </>
                  ) : (
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-warning-primary"></span>
                  )}
                </span>
                <span className={isRunning ? "text-success-primary" : "text-warning-primary"}>
                  {isRunning ? "تایمر در حال محاسبه: " : "تایمر متوقف موقت: "}
                  {formatTimerClock(currentSessionSeconds)}
                </span>
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Controls: Pause, Resume, Stop */}
          {!disabled && (
            <>
              {hasActiveSession ? (
                <>
                  {/* Pause or Resume button */}
                  {isRunning ? (
                    <button
                      type="button"
                      onClick={handlePause}
                      className="text-xs shadow-xs flex items-center gap-1.5 rounded-lg border border-subtle bg-layer-2 px-3 py-1.5 font-medium text-warning-primary transition hover:bg-layer-2-hover"
                      title="توقف موقت تایمر"
                    >
                      <Pause className="size-3 fill-current" />
                      <span>توقف موقت</span>
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={handleStartOrResume}
                      className="text-xs shadow-xs flex items-center gap-1.5 rounded-lg bg-accent-primary px-3 py-1.5 font-medium text-on-color transition hover:bg-accent-primary/80"
                      title="ادامه تایمر"
                    >
                      <Play className="size-3 fill-current" />
                      <span>ادامه تایمر</span>
                    </button>
                  )}

                  {/* Stop & Save button */}
                  <button
                    type="button"
                    onClick={() => {
                      setStopNote("");
                      setIsStopModalOpen(true);
                    }}
                    className="text-xs shadow-xs flex items-center gap-1.5 rounded-lg bg-danger-subtle px-3 py-1.5 font-medium text-danger-primary transition hover:bg-danger-subtle-hover"
                    title="پایان و ثبت زمان کار"
                  >
                    <Square className="size-3 fill-current" />
                    <span>ثبت و پایان</span>
                  </button>
                </>
              ) : (
                /* Start timer button */
                <button
                  type="button"
                  onClick={handleStartOrResume}
                  className="text-xs shadow-xs flex items-center gap-1.5 rounded-lg bg-accent-primary px-3 py-1.5 font-medium text-on-color transition hover:bg-accent-primary/80"
                  title="شروع تایمر زنده"
                >
                  <Play className="size-3 fill-current" />
                  <span>شروع تایمر</span>
                </button>
              )}
            </>
          )}

          {/* Manual log button */}
          {!disabled && (
            <button
              type="button"
              onClick={() => setIsManualModalOpen(true)}
              className="text-xs flex items-center gap-1 rounded-lg border border-subtle px-2.5 py-1.5 font-medium text-secondary transition hover:bg-layer-2"
            >
              <Plus className="size-3.5" />
              <span>ثبت دستی</span>
            </button>
          )}

          {/* Toggle details accordion */}
          <button
            type="button"
            onClick={() => setIsExpanded(!isExpanded)}
            className="rounded-lg p-1.5 text-placeholder transition hover:bg-layer-2 hover:text-primary"
            title={isExpanded ? "بستن جزئیات" : "مشاهده جزئیات گزارشات"}
          >
            {isExpanded ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          </button>
        </div>
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="text-xs mt-2.5 flex items-center gap-2 rounded-lg border border-subtle bg-warning-subtle p-2 text-danger-primary">
          <AlertCircle className="size-4 shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Expandable History and Breakdown */}
      {isExpanded && (
        <div className="animate-in fade-in-50 mt-3.5 space-y-3 border-t border-subtle pt-3.5">
          {/* Active Session Live Row */}
          {hasActiveSession && (
            <div className="space-y-1 rounded-xl border border-subtle bg-warning-subtle p-2.5">
              <div className="text-xs flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    {isRunning ? (
                      <>
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success-primary opacity-75"></span>
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-success-primary"></span>
                      </>
                    ) : (
                      <span className="relative inline-flex h-2 w-2 rounded-full bg-warning-primary"></span>
                    )}
                  </span>
                  <span className="font-semibold text-primary">
                    {isRunning ? "تایمر جاری در حال اجرا" : "تایمر جاری متوقف موقت"}
                  </span>
                </div>
                <div className="font-mono flex items-center gap-2 font-bold text-success-primary">
                  <span>{formatTimerClock(currentSessionSeconds)}</span>
                  <span className="font-normal text-[11px] text-secondary">
                    ({formatSeconds(currentSessionSeconds)})
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* View Mode Tabs */}
          <div className="text-xs flex items-center justify-between">
            <span className="font-medium text-secondary">نحوه نمایش لاگ‌ها:</span>
            <div className="flex items-center gap-1 rounded-lg border border-subtle bg-surface-2 p-1">
              <button
                type="button"
                onClick={() => setActiveView("grouped_by_date")}
                className={cn(
                  "flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium transition",
                  activeView === "grouped_by_date"
                    ? "shadow-2xs bg-surface-1 font-semibold text-primary"
                    : "text-secondary hover:text-primary"
                )}
              >
                <Calendar className="size-3" />
                <span>تاریخ</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveView("grouped_by_user")}
                className={cn(
                  "flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium transition",
                  activeView === "grouped_by_user"
                    ? "shadow-2xs bg-surface-1 font-semibold text-primary"
                    : "text-secondary hover:text-primary"
                )}
              >
                <Users className="size-3" />
                <span>اعضا</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveView("timeline_intervals")}
                className={cn(
                  "flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium transition",
                  activeView === "timeline_intervals"
                    ? "shadow-2xs bg-surface-1 font-semibold text-primary"
                    : "text-secondary hover:text-primary"
                )}
              >
                <ListFilter className="size-3" />
                <span>تمام لاگ‌ها</span>
              </button>
            </div>
          </div>

          {/* Grouped by Date View */}
          {activeView === "grouped_by_date" && (
            <div className="space-y-2">
              {data?.grouped_by_date && data.grouped_by_date.length > 0 ? (
                data.grouped_by_date.map((grp) => (
                  <div key={grp.date} className="space-y-1.5 rounded-lg border border-subtle bg-surface-2 p-2.5">
                    <div className="text-xs flex items-center justify-between">
                      <span className="font-semibold text-primary">{grp.date}</span>
                      <span className="font-mono font-bold text-success-primary">
                        {formatSeconds(grp.total_seconds)}
                      </span>
                    </div>
                    <div className="space-y-1 border-t border-subtle/50 pt-1">
                      {grp.logs.map((log) => (
                        <div key={log.id} className="flex items-center justify-between text-[11px] text-secondary">
                          <div className="flex items-center gap-2 truncate">
                            <span className="font-medium text-primary">{log.user?.display_name || "کاربر"}</span>
                            {log.description && <span className="truncate text-placeholder">— {log.description}</span>}
                          </div>
                          <div className="flex flex-shrink-0 items-center gap-2">
                            <span className="font-mono">{formatSeconds(log.duration_seconds)}</span>
                            {!disabled && (
                              <button
                                type="button"
                                onClick={() => handleDeleteWorklog(log.id)}
                                className="rounded p-0.5 text-placeholder transition hover:text-danger-primary"
                                title="حذف لاگ"
                              >
                                <Trash2 className="size-3" />
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-xs py-4 text-center text-placeholder">هنوز زمانی برای این تسک ثبت نشده است.</div>
              )}
            </div>
          )}

          {/* Grouped by User View */}
          {activeView === "grouped_by_user" && (
            <div className="space-y-2">
              {data?.grouped_by_user && data.grouped_by_user.length > 0 ? (
                data.grouped_by_user.map((grp, idx) => (
                  <div key={idx} className="space-y-1.5 rounded-lg border border-subtle bg-surface-2 p-2.5">
                    <div className="text-xs flex items-center justify-between">
                      <span className="font-semibold text-primary">{grp.user?.display_name || "کاربر"}</span>
                      <span className="font-mono font-bold text-success-primary">
                        {formatSeconds(grp.total_seconds)}
                      </span>
                    </div>
                    <div className="space-y-1 border-t border-subtle/50 pt-1">
                      {grp.logs.map((log) => (
                        <div key={log.id} className="flex items-center justify-between text-[11px] text-secondary">
                          <span className="truncate text-placeholder">{log.description || "بدون توضیح"}</span>
                          <div className="flex flex-shrink-0 items-center gap-2">
                            <span className="font-mono">{formatSeconds(log.duration_seconds)}</span>
                            {!disabled && (
                              <button
                                type="button"
                                onClick={() => handleDeleteWorklog(log.id)}
                                className="rounded p-0.5 text-placeholder transition hover:text-danger-primary"
                                title="حذف لاگ"
                              >
                                <Trash2 className="size-3" />
                              </button>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-xs py-4 text-center text-placeholder">هنوز زمانی برای این تسک ثبت نشده است.</div>
              )}
            </div>
          )}

          {/* Timeline / All intervals View */}
          {activeView === "timeline_intervals" && (
            <div className="space-y-1.5">
              {data?.intervals && data.intervals.length > 0 ? (
                data.intervals.map((log) => (
                  <div
                    key={log.id}
                    className="text-xs flex items-center justify-between rounded-lg border border-subtle bg-surface-2 p-2"
                  >
                    <div className="min-w-0 flex-1 space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-primary">{log.user?.display_name || "کاربر"}</span>
                        <span className="text-[10px] text-placeholder">
                          {new Date(log.created_at).toLocaleDateString("fa-IR")}
                        </span>
                      </div>
                      {log.description && <p className="truncate text-[11px] text-secondary">{log.description}</p>}
                    </div>

                    <div className="flex flex-shrink-0 items-center gap-2.5">
                      <span className="font-mono font-bold text-success-primary">
                        {formatSeconds(log.duration_seconds)}
                      </span>
                      {!disabled && (
                        <button
                          type="button"
                          onClick={() => handleDeleteWorklog(log.id)}
                          className="rounded p-1 text-placeholder transition hover:bg-layer-2-hover hover:text-danger-primary"
                          title="حذف لاگ"
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-xs py-4 text-center text-placeholder">هنوز زمانی برای این تسک ثبت نشده است.</div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Stop & Save Modal */}
      {isStopModalOpen && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-backdrop p-4 backdrop-blur-sm">
          <div className="shadow-2xl animate-in zoom-in-95 w-full max-w-sm space-y-4 rounded-2xl border border-subtle bg-surface-1 p-5">
            <div className="flex items-center justify-between border-b border-subtle pb-3">
              <h3 className="text-sm font-semibold text-primary">ثبت و پایان کارکرد تایمر</h3>
              <button
                onClick={() => setIsStopModalOpen(false)}
                className="rounded p-1 text-placeholder hover:text-primary"
              >
                <X className="size-4" />
              </button>
            </div>

            <div className="space-y-1 rounded-xl border border-subtle bg-surface-2 p-3 text-center">
              <div className="text-xs text-secondary">مدت زمان این جلسه کاری:</div>
              <div className="font-mono text-2xl font-bold text-success-primary">
                {formatTimerClock(currentSessionSeconds)}
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
                onClick={() => setIsStopModalOpen(false)}
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
                {isSubmitting ? "در حال ثبت..." : "ثبت لاگ و پایان"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Manual Time Log Modal */}
      {isManualModalOpen && (
        <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-backdrop p-4 backdrop-blur-sm">
          <div className="shadow-2xl animate-in zoom-in-95 w-full max-w-sm space-y-4 rounded-2xl border border-subtle bg-surface-1 p-5">
            <div className="flex items-center justify-between border-b border-subtle pb-3">
              <h3 className="text-sm font-semibold text-primary">ثبت دستی زمان کارکرد</h3>
              <button
                onClick={() => setIsManualModalOpen(false)}
                className="rounded p-1 text-placeholder hover:text-primary"
              >
                <X className="size-4" />
              </button>
            </div>

            <form onSubmit={handleManualLog} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs font-medium text-secondary">ساعت:</label>
                  <input
                    type="number"
                    min={0}
                    max={24}
                    value={hours}
                    onChange={(e) => setHours(Math.max(0, parseInt(e.target.value) || 0))}
                    className="text-sm focus:ring-accent-primary w-full rounded-xl border border-subtle bg-surface-2 p-2 text-center font-bold text-primary focus:ring-1 focus:outline-none"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs font-medium text-secondary">دقیقه:</label>
                  <input
                    type="number"
                    min={0}
                    max={59}
                    value={minutes}
                    onChange={(e) => setMinutes(Math.max(0, Math.min(59, parseInt(e.target.value) || 0)))}
                    className="text-sm focus:ring-accent-primary w-full rounded-xl border border-subtle bg-surface-2 p-2 text-center font-bold text-primary focus:ring-1 focus:outline-none"
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-secondary">شرح فعالیت (اختیاری):</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="مختصری درباره کار انجام شده بنویسید..."
                  className="text-xs focus:ring-accent-primary h-20 w-full rounded-xl border border-subtle bg-surface-2 p-2.5 text-primary focus:ring-1 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsManualModalOpen(false)}
                  className="text-xs rounded-lg px-3 py-1.5 font-medium text-secondary hover:bg-layer-2"
                >
                  انصراف
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || (hours === 0 && minutes === 0)}
                  className="text-xs rounded-lg bg-accent-primary px-4 py-1.5 font-medium text-on-color transition hover:bg-accent-primary/80 disabled:opacity-50"
                >
                  {isSubmitting ? "در حال ثبت..." : "ثبت کارکرد"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
