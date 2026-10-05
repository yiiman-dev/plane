/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type {
  TInvoiceStatus,
  TPaymentGatewayAmountUnit,
  TPaymentGatewayCode,
  TPaymentGatewayCredentialKey,
  TPaymentGatewayRoutingStrategy,
  TPaymentTransactionStatus,
} from "@plane/types";
import { formatNumber } from "./utils";

/* gateways */

export const SUPPORTED_GATEWAY_CODES: TPaymentGatewayCode[] = ["zarinpal", "payping", "zibal", "digipay"];

export type TGatewayCredentialFieldType = "password" | "select" | "text";

export type TGatewayCredentialField = {
  key: TPaymentGatewayCredentialKey;
  label: string;
  placeholder: string;
  type: TGatewayCredentialFieldType;
  required: boolean;
  options?: { label: string; value: string }[];
  defaultValue?: string;
};

export const GATEWAY_CREDENTIAL_FIELDS: Record<TPaymentGatewayCode, TGatewayCredentialField[]> = {
  zarinpal: [
    {
      key: "merchant_id",
      label: "شناسه پذیرنده",
      placeholder: "00000000-0000-0000-0000-000000000000",
      type: "text",
      required: true,
    },
  ],
  payping: [
    {
      key: "api_token",
      label: "توکن API",
      placeholder: "توکن دریافتی از پنل پی‌پینگ",
      type: "password",
      required: true,
    },
  ],
  zibal: [
    {
      key: "merchant",
      label: "شناسه پذیرنده",
      placeholder: "zibal",
      type: "text",
      required: true,
    },
  ],
  digipay: [
    {
      key: "client_id",
      label: "شناسه کلاینت",
      placeholder: "client_id دیجی‌پی",
      type: "text",
      required: true,
    },
    {
      key: "client_secret",
      label: "رمز کلاینت",
      placeholder: "client_secret دیجی‌پی",
      type: "password",
      required: true,
    },
    {
      key: "username",
      label: "نام کاربری (اختیاری)",
      placeholder: "نام کاربری دریافت توکن",
      type: "text",
      required: false,
    },
    {
      key: "password",
      label: "رمز عبور (اختیاری)",
      placeholder: "رمز عبور دریافت توکن",
      type: "password",
      required: false,
    },
    {
      key: "grant_type",
      label: "نوع اعتبارسنجی",
      placeholder: "password",
      type: "select",
      required: false,
      defaultValue: "password",
      options: [
        { label: "password", value: "password" },
        { label: "client_credentials", value: "client_credentials" },
      ],
    },
  ],
};

export const GATEWAY_LABELS: Record<TPaymentGatewayCode, string> = {
  zarinpal: "زرین‌پال",
  payping: "پی‌پینگ",
  zibal: "زیبال",
  digipay: "دیجی‌پی",
};

/** Amount unit each provider expects, mirrored from the backend adapter defaults. */
export const GATEWAY_DEFAULT_AMOUNT_UNIT: Record<TPaymentGatewayCode, TPaymentGatewayAmountUnit> = {
  zarinpal: "rial",
  payping: "toman",
  zibal: "rial",
  digipay: "rial",
};

export const AMOUNT_UNIT_OPTIONS: { label: string; value: TPaymentGatewayAmountUnit }[] = [
  { label: "ریال", value: "rial" },
  { label: "تومان", value: "toman" },
];

export const EXTRA_CONFIG_KEYS = [
  "amount_unit",
  "timeout",
  "min_amount_toman",
  "max_amount_toman",
  "base_url",
  "callback_url",
] as const;

export const EXTRA_CONFIG_LABELS: Record<(typeof EXTRA_CONFIG_KEYS)[number], string> = {
  amount_unit: "واحد پول ورودی",
  timeout: "مهلت پاسخ درگاه (ثانیه)",
  min_amount_toman: "حداقل مبلغ (تومان)",
  max_amount_toman: "حداکثر مبلغ (تومان)",
  base_url: "آدرس پایه درگاه",
  callback_url: "آدرس بازگشت",
};

/* routing */

export const ROUTING_STRATEGIES: {
  description: string;
  label: string;
  value: TPaymentGatewayRoutingStrategy;
}[] = [
  {
    value: "schedule",
    label: "مبتنی بر زمان‌بندی",
    description: "در هر بازه زمانی از روز، یک درگاه مشخص فعال می‌شود. بازه‌ها می‌توانند از نیمه‌شب عبور کنند.",
  },
  {
    value: "random",
    label: "تصادفی",
    description: "یکی از درگاه‌های فعال به‌صورت تصادفی و بر اساس وزن انتخاب می‌شود.",
  },
  {
    value: "priority",
    label: "تکی با بقیه passive",
    description:
      "یک درگاه اصلی انتخاب می‌شود و بقیه به ترتیب اولویت، فقط هنگام در دسترس نبودن درگاه قبلی جایگزین می‌شوند.",
  },
];

export const ROUTING_STRATEGY_LABELS: Record<TPaymentGatewayRoutingStrategy, string> = {
  schedule: "مبتنی بر زمان‌بندی",
  random: "تصادفی",
  priority: "تکی با بقیه passive",
};

export const MIN_HOUR = 0;
export const MAX_HOUR = 24;

/* plans */

export const BILLING_CYCLE_LABELS: Record<"monthly" | "yearly", string> = {
  monthly: "ماهانه",
  yearly: "سالانه",
};

/* invoices */

export const INVOICE_STATUS_LABELS: Record<TInvoiceStatus, string> = {
  draft: "پیش‌نویس",
  issued: "صادر شده",
  paid: "پرداخت شده",
  cancelled: "لغو شده",
  expired: "منقضی شده",
  refund: "بازگشت وجه",
};

export const INVOICE_STATUS_VARIANTS: Record<
  TInvoiceStatus,
  "brand" | "danger" | "info" | "neutral" | "success" | "warning"
> = {
  draft: "neutral",
  issued: "info",
  paid: "success",
  cancelled: "danger",
  expired: "warning",
  refund: "brand",
};

export const INVOICE_STATUSES = Object.keys(INVOICE_STATUS_LABELS) as TInvoiceStatus[];

/* transactions */

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

export const TRANSACTION_STATUSES = Object.keys(TRANSACTION_STATUS_LABELS) as TPaymentTransactionStatus[];

/* pagination */

export const BILLING_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export const PAGINATION_LABELS = {
  root: "صفحه‌بندی",
  previous: "صفحه قبل",
  next: "صفحه بعد",
  page: (page: number) => `رفتن به صفحه ${formatNumber(page)}`,
  perPageValue: (pageSize: number) => formatNumber(pageSize),
  perPage: "در هر صفحه",
};
