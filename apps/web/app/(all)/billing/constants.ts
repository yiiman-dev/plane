/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TPaymentGatewayCode, TPaymentTransactionStatus } from "@plane/types";

/* checkout */

export const BILLING_CYCLES: { label: string; value: "monthly" | "yearly" }[] = [
  { label: "ماهانه", value: "monthly" },
  { label: "سالانه", value: "yearly" },
];

export const BILLING_CYCLE_LABELS: Record<"monthly" | "yearly", string> = {
  monthly: "ماهانه",
  yearly: "سالانه",
};

/**
 * The gateway that actually processed the payment. Kept in the web app because the admin
 * application is a separate bundle and its constants are not importable from here.
 */
export const GATEWAY_LABELS: Record<TPaymentGatewayCode, string> = {
  zarinpal: "زرین‌پال",
  payping: "پی‌پینگ",
  zibal: "زیبال",
  digipay: "دیجی‌پی",
};

/* payment result */

export const TRANSACTION_STATUS_LABELS: Record<TPaymentTransactionStatus, string> = {
  pending: "در انتظار",
  redirected: "هدایت شده",
  processing: "در حال پردازش",
  paid: "پرداخت شده",
  failed: "ناموفق",
  unavailable: "در دسترس نیست",
  reversed: "بازگشت وجه",
};

export const TRANSACTION_STATUS_VARIANTS: Record<
  TPaymentTransactionStatus,
  "brand" | "danger" | "info" | "neutral" | "success" | "warning"
> = {
  pending: "neutral",
  redirected: "info",
  processing: "info",
  paid: "success",
  failed: "danger",
  unavailable: "warning",
  reversed: "brand",
};

/**
 * Statuses that must not be polled again: either the payment reached a final state or it failed in
 * a way that retrying cannot fix.
 */
export const TERMINAL_TRANSACTION_STATUSES: TPaymentTransactionStatus[] = ["paid", "failed", "reversed"];

/* polling */

/** First delay before re-checking a pending verification, then it grows up to the ceiling. */
export const POLL_INITIAL_DELAY_MS = 3000;
/** Upper bound of the polling backoff, so a slow gateway is not hammered. */
export const POLL_MAX_DELAY_MS = 15000;
/** Give up after ~3 minutes; the payer is told to check back later instead of waiting forever. */
export const POLL_MAX_ATTEMPTS = 12;

/* formatting */

export const formatNumber = (value: number | null | undefined): string =>
  value === null || value === undefined || Number.isNaN(Number(value))
    ? "—"
    : new Intl.NumberFormat("fa-IR").format(Number(value));

export const formatToman = (value: number | null | undefined): string =>
  value === null || value === undefined ? "— تومان" : `${formatNumber(value)} تومان`;

export const formatDateTime = (value: string | null | undefined): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("fa-IR", { dateStyle: "medium", timeStyle: "short" }).format(date);
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
