/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export const DEFAULT_BILLING_PER_PAGE = 50;

/**
 * The billing API paginates with a `per_page:offset:is_prev` cursor. Propel Pagination is
 * 1 based, so the offset is always derived from the visible page number.
 */
export const makeBillingCursor = (perPage: number, offset: number) => `${perPage}:${offset}:0`;

export const parseBillingCursor = (
  cursor: string | undefined,
  fallbackPerPage: number = DEFAULT_BILLING_PER_PAGE
): { offset: number; perPage: number } => {
  if (!cursor) return { offset: 0, perPage: fallbackPerPage };

  const [limitPart, offsetPart] = cursor.split(":");
  const parsedLimit = Number.parseInt(limitPart, 10);
  const parsedOffset = Number.parseInt(offsetPart, 10);

  return {
    offset: Number.isFinite(parsedOffset) && parsedOffset > 0 ? parsedOffset : 0,
    perPage: Number.isFinite(parsedLimit) && parsedLimit > 0 ? parsedLimit : fallbackPerPage,
  };
};

export const pageToCursor = (page: number, perPage: number) => makeBillingCursor(perPage, (page - 1) * perPage);

export const formatNumber = (value: number | null | undefined): string =>
  value === null || value === undefined || Number.isNaN(Number(value))
    ? "—"
    : new Intl.NumberFormat("fa-IR").format(Number(value));

export const formatToman = (value: number | null | undefined): string =>
  value === null || value === undefined ? "—" : `${formatNumber(value)} تومان`;

export const formatDateTime = (value: string | null | undefined): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
};

export const toSafeNumber = (value: string | number | undefined | null, fallback = 0): number => {
  if (value === undefined || value === null || value === "") return fallback;
  const parsed = typeof value === "number" ? value : Number.parseInt(value, 10);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export const getErrorMessage = (error: unknown, fallback: string): string => {
  if (typeof error === "string" && error.trim()) return error;
  if (error && typeof error === "object") {
    const candidate = error as { detail?: unknown; error?: unknown; message?: unknown };
    for (const value of [candidate.detail, candidate.error, candidate.message]) {
      if (typeof value === "string" && value.trim()) return value;
    }
    if (Array.isArray(candidate.detail)) {
      const first = candidate.detail.find((item) => typeof item === "string");
      if (typeof first === "string") return first;
    }
  }
  return fallback;
};

/** Formats a schedule entry as a human readable range, marking ranges that wrap past midnight. */
export const formatHourRange = (startHour: number, endHour: number): string => {
  const start = `${String(startHour).padStart(2, "0")}:00`;
  const end = `${String(endHour).padStart(2, "0")}:00`;
  const wraps = endHour <= startHour;
  return `${start} تا ${end}${wraps ? " (فراتر از نیمه‌شب)" : ""}`;
};

export const formatJsonValue = (value: unknown): string => {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (!entries.length) return "—";
    return entries.map(([key, item]) => `${key}: ${String(item)}`).join(" • ");
  }
  return String(value);
};
