/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
import { BILLING_QUEUED_TRANSACTIONS, BillingService } from "@plane/services";
import type { TQueuedTransaction } from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { Pagination } from "@makeplane/propel/components/pagination";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
import { BILLING_PAGE_SIZE_OPTIONS, GATEWAY_LABELS, PAGINATION_LABELS } from "../constants";
import { useDebouncedValue } from "../hooks";
import {
  DEFAULT_BILLING_PER_PAGE,
  formatDateTime,
  formatNumber,
  formatToman,
  getErrorMessage,
  pageToCursor,
} from "../utils";

type TDecision = "release" | "reject" | "retry";

const DECISION_LABELS: Record<TDecision, string> = {
  release: "نهایی کردن برگشت",
  reject: "رد قفل (پرداخت نشده)",
  retry: "تلاش مجدد وریفای",
};

/** The two decisions that move or write off money need a written reason. */
const DECISION_NEEDS_REASON: Record<TDecision, boolean> = { release: true, reject: true, retry: false };

/**
 * One queued payment and the decisions an operator can take on it. The reason is
 * asked for before a money decision is sent: it is what the workspace and the
 * ledger keep as the explanation.
 */
function QueuedRow({ row, onDone }: { row: TQueuedTransaction; onDone: () => void }) {
  const [decision, setDecision] = useState<TDecision | null>(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (action: TDecision) => {
    if (DECISION_NEEDS_REASON[action] && !reason.trim()) {
      setError("نوشتن توضیح برای این تصمیم الزامی است.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      if (action === "release") await BillingService.releaseHold(row.id, reason.trim());
      if (action === "reject") await BillingService.rejectHold(row.id, reason.trim());
      if (action === "retry") await BillingService.retryTransaction(row.id);
      setDecision(null);
      setReason("");
      onDone();
    } catch (err) {
      setError(getErrorMessage(err, "ثبت تصمیم ناموفق بود. دوباره تلاش کنید."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <li className="rounded-custom flex flex-col gap-3 border border-subtle p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge size="xs" variant="warning" label={`${formatNumber(row.age_days ?? 0)} روز در صف`} />
        <span className="text-13 text-primary">{row.workspace_name || "بدون ورک‌اسپیس"}</span>
        {row.workspace_slug && <span className="font-mono text-12 text-tertiary">{row.workspace_slug}</span>}
        <span className="text-12 text-secondary">
          {GATEWAY_LABELS[row.gateway_code] ?? row.gateway_code} • {formatToman(row.amount_toman)}
        </span>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-12 text-secondary md:grid-cols-4">
        <div>
          <dt className="text-tertiary">فاکتور</dt>
          <dd>{row.invoice_number || "—"}</dd>
        </div>
        <div>
          <dt className="text-tertiary">شناسه تراکنش</dt>
          <dd className="font-mono" dir="ltr">
            {row.gateway_token || "—"}
          </dd>
        </div>
        <div>
          <dt className="text-tertiary">تلاش‌ها</dt>
          <dd>{formatNumber(row.attempts)}</dd>
        </div>
        <div>
          <dt className="text-tertiary">آزادسازی خودکار</dt>
          <dd>{formatDateTime(row.auto_release_at)}</dd>
        </div>
      </dl>

      {row.failure_reason && <p className="text-12 text-danger-primary">آخرین پاسخ درگاه: {row.failure_reason}</p>}

      {decision === null ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            stretch="auto"
            variant="secondary"
            label={DECISION_LABELS.retry}
            onClick={() => setDecision("retry")}
          />
          <Button
            size="sm"
            stretch="auto"
            variant="secondary"
            label={DECISION_LABELS.reject}
            onClick={() => setDecision("reject")}
          />
          <Button
            size="sm"
            stretch="auto"
            variant="primary"
            label={DECISION_LABELS.release}
            onClick={() => setDecision("release")}
          />
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          <span className="text-12 text-secondary">{DECISION_LABELS[decision]}</span>
          {DECISION_NEEDS_REASON[decision] && (
            <Input
              size="lg"
              placeholder="توضیح این تصمیم (الزامی)"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              aria-label="توضیح تصمیم"
            />
          )}
          {error && <p className="text-12 text-danger-primary">{error}</p>}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              size="sm"
              stretch="auto"
              variant="primary"
              label="ثبت تصمیم"
              disabled={submitting}
              onClick={() => submit(decision)}
            />
            <Button
              size="sm"
              stretch="auto"
              variant="secondary"
              label="انصراف"
              disabled={submitting}
              onClick={() => {
                setDecision(null);
                setReason("");
                setError(null);
              }}
            />
          </div>
        </div>
      )}
    </li>
  );
}

export default function BillingPaymentQueuePage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(DEFAULT_BILLING_PER_PAGE);
  const debouncedSearch = useDebouncedValue(search);

  const params = useMemo(
    () => ({
      cursor: pageToCursor(page, perPage),
      per_page: perPage,
      search: debouncedSearch.trim() || undefined,
    }),
    [debouncedSearch, page, perPage]
  );

  const { data, error, isLoading, mutate } = useSWR(BILLING_QUEUED_TRANSACTIONS(params), () =>
    BillingService.queuedTransactions(params)
  );

  const rows = useMemo<TQueuedTransaction[]>(() => data?.results ?? [], [data]);
  const total = data?.total_results ?? 0;
  const pageCount = Math.max(1, data?.total_pages ?? 1);

  return (
    <BillingRTLFrame
      title="صف پرداخت‌های مبهم"
      description="پرداخت‌هایی که درگاه پس از آخرین تلاش هنوز تأیید یا رد نکرده است. مبلغ این پرداخت‌ها تا تصمیم شما از کیف پول ورک‌اسپیس جدا است."
    >
      <BillingNav />

      <BillingSection title="پرداخت‌های در صف">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-56 flex-col gap-1">
            <label className="text-13 text-tertiary" htmlFor="queue-search">
              جستجو
            </label>
            <Input
              id="queue-search"
              size="lg"
              placeholder="شناسه تراکنش، شماره فاکتور"
              value={search}
              onChange={(event) => {
                setPage(1);
                setSearch(event.target.value);
              }}
            />
          </div>
          <span className="text-12 text-tertiary">{formatNumber(total)} پرداخت در صف</span>
        </div>

        {isLoading && <BillingEmptyState message="در حال بارگذاری صف…" />}
        {!isLoading && error && <BillingEmptyState message={getErrorMessage(error, "بارگذاری صف ناموفق بود.")} />}
        {!isLoading && !error && rows.length === 0 && <BillingEmptyState message="هیچ پرداخت مبهمی در صف نیست." />}

        {rows.length > 0 && (
          <ul className="flex flex-col gap-3" role="list">
            {rows.map((row) => (
              <QueuedRow key={row.id} row={row} onDone={() => mutate()} />
            ))}
          </ul>
        )}

        {total > 0 && (
          <Pagination
            page={page}
            pageCount={pageCount}
            onPageChange={setPage}
            labels={PAGINATION_LABELS}
            pageSize={{
              value: perPage,
              options: BILLING_PAGE_SIZE_OPTIONS,
              onValueChange: (pageSize: number) => {
                setPerPage(pageSize);
                setPage(1);
              },
            }}
          />
        )}
      </BillingSection>
    </BillingRTLFrame>
  );
}
