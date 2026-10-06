/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/**
 * Numbers reach this screen from the server as plain integers, so they are converted here once.
 * Persian digits are used everywhere in this panel, including inside sentences.
 */
const persianNumberFormatter = new Intl.NumberFormat("fa-IR");

export const formatPersianNumber = (value: number): string => {
  if (!Number.isFinite(value)) return persianNumberFormatter.format(0);
  return persianNumberFormatter.format(value);
};

/** A missing seat limit means unlimited seats, and must never be rendered as zero. */
export const UNLIMITED_SEATS_LABEL = "نامحدود";

/** Feature categories are free text on the instance, so known ones get a Persian label. */
export const FEATURE_CATEGORY_LABELS: Record<string, string> = {
  automation: "اتوماسیون",
  reporting: "گزارش‌گیری",
  integrations: "یکپارچه‌سازی‌ها",
  security: "امنیت",
  storage: "ذخیره‌سازی",
  support: "پشتیبانی",
};

/** Unknown categories keep the server value instead of showing an empty section. */
export const getFeatureCategoryLabel = (category?: string | null): string => {
  const normalized = (category ?? "").trim();
  if (!normalized) return "سایر قابلیت‌ها";
  return FEATURE_CATEGORY_LABELS[normalized.toLowerCase()] ?? normalized;
};

/** Unwraps the server error envelope, whose Persian message is already safe to show. */
export const getBillingErrorMessage = (error: unknown, fallback: string): string => {
  const candidate = error as { error?: string; detail?: string; message?: string } | undefined;
  const message = candidate?.error ?? candidate?.detail ?? candidate?.message;
  return typeof message === "string" && message.trim() ? message : fallback;
};
