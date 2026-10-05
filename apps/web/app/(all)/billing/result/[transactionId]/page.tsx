/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useRef, useState } from "react";
import useSWR from "swr";
import { Button } from "@makeplane/propel/components/button";
import { BILLING_ORDER_STATUS, BillingService } from "@plane/services";
import type { TPaymentTransactionStatus } from "@plane/types";
// types
import type { Route } from "./+types/page";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
// local imports
import {
  GATEWAY_LABELS,
  POLL_INITIAL_DELAY_MS,
  POLL_MAX_ATTEMPTS,
  POLL_MAX_DELAY_MS,
  TERMINAL_TRANSACTION_STATUSES,
  TRANSACTION_STATUS_LABELS,
  TRANSACTION_STATUS_VARIANTS,
  formatDateTime,
  formatToman,
  getErrorMessage,
} from "../../constants";

/** Row of the order summary shown under the result headline. */
function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-sm flex items-center justify-between gap-3">
      <span className="text-content-2">{label}</span>
      <span className="text-content-on-surface font-medium">{value}</span>
    </div>
  );
}

/**
 * Headline for each settlement state.
 * - paid: the gateway confirmed the payment.
 * - failed / reversed: the payment did not go through and the payer was not charged.
 * - processing and the rest: still being verified, so the reason is not an error yet.
 */
function getResultCopy(status: TPaymentTransactionStatus | undefined): {
  title: string;
  description: string;
  tone: "danger" | "info" | "success" | "warning";
} {
  if (status === "paid")
    return {
      title: "پرداخت با موفقیت انجام شد",
      description: "پرداخت شما تأیید و پلن برای حساب شما فعال شد. رسید این پرداخت در فاکتورهای شما قابل مشاهده است.",
      tone: "success",
    };
  if (status === "failed")
    return {
      title: "پرداخت ناموفق بود",
      description: "پرداخت شما تأیید نشد و مبلغی از حساب شما کسر نشده است. می‌توانید دوباره تلاش کنید.",
      tone: "danger",
    };
  if (status === "reversed")
    return {
      title: "پرداخت بازگشت خورد",
      description: "این پرداخت توسط درگاه بازگشت داده شد. مبلغ پس از تأیید به حساب شما بازمی‌گردد.",
      tone: "warning",
    };
  if (status === "unavailable")
    return {
      title: "درگاه پرداخت در دسترس نبود",
      description: "درگاه انتخاب‌شده در حال حاضر پاسخگو نبود. می‌توانید دوباره تلاش کنید تا درگاه دیگری انتخاب شود.",
      tone: "warning",
    };
  if (status === "processing")
    return {
      title: "پرداخت در حال پردازش است",
      description:
        "درگاه پرداخت هنوز نتیجه را نهایی نکرده است. این صفحه به‌صورت خودکار وضعیت را بررسی می‌کند و لازم نیست صفحه را بازخوانی کنید.",
      tone: "info",
    };
  return {
    title: "در انتظار تأیید پرداخت",
    description: "وضعیت پرداخت شما هنوز نهایی نشده است. این صفحه به‌صورت خودکار وضعیت را بررسی می‌کند.",
    tone: "info",
  };
}

const TONE_CLASSES: Record<"danger" | "info" | "success" | "warning", string> = {
  success: "border-success-200 bg-success-50 text-success-500",
  danger: "border-danger-200 bg-danger-50 text-danger-500",
  warning: "border-warning-200 bg-warning-50 text-warning-500",
  info: "border-info-200 bg-info-50 text-info-500",
};

export default function BillingResultPage(props: Route.ComponentProps) {
  const { transactionId } = props.params;
  // poll bookkeeping
  const attemptRef = useRef(0);
  const [hasGivenUp, setHasGivenUp] = useState(false);

  const { data, error } = useSWR(
    BILLING_ORDER_STATUS(transactionId),
    () => BillingService.paymentOrderStatus(transactionId),
    {
      // A slow gateway can keep the transaction unresolved, so the status is re-read on a growing
      // interval until it settles instead of being fetched only once.
      refreshInterval: (latest) => {
        if (!latest) return 0;
        if (TERMINAL_TRANSACTION_STATUSES.includes(latest.status)) return 0;
        const delay = Math.min(POLL_INITIAL_DELAY_MS * 2 ** attemptRef.current, POLL_MAX_DELAY_MS);
        attemptRef.current += 1;
        if (attemptRef.current > POLL_MAX_ATTEMPTS) {
          setHasGivenUp(true);
          return 0;
        }
        return delay;
      },
    }
  );

  if (error)
    return (
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-4">
        <ResultPanel
          title="سفارش یافت نشد"
          description={getErrorMessage(error, "اطلاعات این سفارش در دسترس نیست.")}
          tone="danger"
        />
        <Button
          variant="secondary"
          size="md"
          stretch="auto"
          onClick={() => (window.location.href = "/billing")}
          label="بازگشت به خرید پلن"
        />
      </div>
    );

  if (!data)
    return (
      <div className="grid w-full place-items-center py-20">
        <LogoSpinner />
      </div>
    );

  const copy = getResultCopy(data.status);
  const isTerminal = TERMINAL_TRANSACTION_STATUSES.includes(data.status);

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-4">
      <ResultPanel title={copy.title} description={copy.description} tone={copy.tone} />

      {hasGivenUp && !isTerminal && (
        <p className="text-xs text-content-2">
          {`پیگیری خودکار متوقف شد. اگر مبلغی از حساب شما کسر شده باشد، وضعیت نهایی پس از تأیید درگاه ثبت می‌شود و از بخش فاکتورهای حساب خود می‌توانید آن را ببینید.`}
        </p>
      )}

      <div className="flex flex-col gap-2 rounded-md border border-subtle bg-surface-1 p-4">
        <h2 className="text-sm text-content-on-surface font-medium">جزئیات سفارش</h2>
        <SummaryRow label="شماره فاکتور" value={data.invoice_number || "—"} />
        <SummaryRow label="پلن" value={data.plan_name || "—"} />
        {data.seats !== null ? <SummaryRow label="تعداد صندلی" value={String(data.seats)} /> : null}
        <SummaryRow label="مبلغ" value={formatToman(data.amount_toman)} />
        <SummaryRow label="درگاه" value={GATEWAY_LABELS[data.gateway_code] || data.gateway_code} />
        <SummaryRow label="وضعیت" value={TRANSACTION_STATUS_LABELS[data.status]} />
        <SummaryRow label="تاریخ ثبت" value={formatDateTime(data.created_at)} />
        {data.paid_at && <SummaryRow label="زمان تأیید پرداخت" value={formatDateTime(data.paid_at)} />}
        {data.failure_reason && <SummaryRow label="علت ناموفقی" value={data.failure_reason} />}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          onClick={() => (window.location.href = "/billing")}
          label={isTerminal && data.status !== "paid" ? "تلاش دوباره" : "بازگشت به پلن‌ها"}
        />
        {!isTerminal && (
          <span className={`text-xs rounded-md border px-2 py-1 ${TONE_CLASSES[copy.tone]}`}>
            {TRANSACTION_STATUS_VARIANTS[data.status] ? TRANSACTION_STATUS_LABELS[data.status] : ""}
          </span>
        )}
      </div>
    </div>
  );
}

/** The bordered panel carrying the result headline and its explanation. */
function ResultPanel({
  title,
  description,
  tone,
}: {
  title: string;
  description: string;
  tone: "danger" | "info" | "success" | "warning";
}) {
  return (
    <div className={`flex flex-col gap-1 rounded-md border p-4 ${TONE_CLASSES[tone]}`}>
      <h1 className="text-base font-medium">{title}</h1>
      <p className="text-sm">{description}</p>
    </div>
  );
}
