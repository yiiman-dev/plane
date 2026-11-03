/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import { Link } from "react-router";
import useSWR from "swr";
import { BillingService, BILLING_SMS_REPORT } from "@plane/services";
import type { TBillingSmsReportRow } from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";
import { Input } from "@makeplane/propel/components/input";
import { Pagination } from "@makeplane/propel/components/pagination";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
import { BILLING_PAGE_SIZE_OPTIONS, PAGINATION_LABELS, SMS_EVENT_LABELS } from "../constants";
import { useDebouncedValue } from "../hooks";
import { DEFAULT_BILLING_PER_PAGE, formatNumber, formatToman, getErrorMessage, pageToCursor } from "../utils";

/** One figure of the row, with the tone that marks a figure worth looking at. */
function CostFigure({ label, tone, value }: { label: string; tone?: "danger" | "warning"; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-12 text-tertiary">{label}</dt>
      <dd
        className={
          tone === "danger"
            ? "text-body-sm-semibold text-danger-primary"
            : tone === "warning"
              ? "text-body-sm-semibold text-warning-primary"
              : "text-body-sm-semibold text-primary"
        }
      >
        {value}
      </dd>
    </div>
  );
}

/**
 * One workspace's SMS spend. The five figures are the report: what left the
 * wallet, what was delivered for it, what was paid and not delivered, what was
 * refused for lack of balance, and what the wallet paid with no delivery row to
 * explain it. Only the last one is a discrepancy, so only it is alarmed on.
 */
function SmsReportRow({ row }: { row: TBillingSmsReportRow }) {
  return (
    <li className="rounded-custom flex flex-col gap-3 border border-subtle p-4">
      <div className="flex flex-wrap items-center gap-2">
        {/* Linking to the detail page rather than showing the wallet here: that
            page is the audited read of one tenant's money. */}
        <Link
          to={`/billing/workspaces/${row.workspace_slug}/`}
          className="text-13 text-primary underline-offset-2 hover:underline"
        >
          {row.workspace_name}
        </Link>
        <span className="font-mono text-12 text-tertiary">{row.workspace_slug}</span>
        {row.plan_code && <Badge size="xs" variant="neutral" label={row.plan_code} />}
      </div>

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <CostFigure label="کسر شده از کیف پول" value={formatToman(row.charged_toman)} />
        <CostFigure label="تحویل‌شده" value={formatToman(row.delivered_toman)} />
        <CostFigure
          label="کسر شده، تحویل نشده"
          tone={row.lost_toman > 0 ? "warning" : undefined}
          value={formatToman(row.lost_toman)}
        />
        <CostFigure label="ردشده (بدون موجودی)" value={formatToman(row.refused_toman)} />
        <CostFigure
          label="بی‌حساب"
          tone={row.unexplained_toman === 0 ? undefined : "danger"}
          value={formatToman(row.unexplained_toman)}
        />
      </dl>

      <div className="flex flex-wrap items-center gap-2">
        <Badge size="xs" variant="success" label={`ارسال‌شده: ${formatNumber(row.sent_count)}`} />
        <Badge
          size="xs"
          variant={row.failed_count > 0 ? "danger" : "neutral"}
          label={`ناموفق: ${formatNumber(row.failed_count)}`}
        />
        <Badge
          size="xs"
          variant={row.skipped_count > 0 ? "warning" : "neutral"}
          label={`ردشده: ${formatNumber(row.skipped_count)}`}
        />
        <Badge size="xs" variant="neutral" label={`در جریان: ${formatNumber(row.pending_count)}`} />
      </div>

      {row.events.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <span className="text-12 text-tertiary">هزینه به تفکیک رویداد</span>
          <ul className="flex flex-col gap-1" role="list">
            {row.events.map((event) => (
              <li key={event.event} className="flex flex-wrap items-center gap-2 text-12 text-secondary">
                <span className="text-primary">{SMS_EVENT_LABELS[event.event] ?? event.event}</span>
                <span>{formatNumber(event.count)} پیام</span>
                <span>هزینهٔ ثبت‌شده: {formatToman(event.snapshotted_toman)}</span>
                <span>نرخ امروز پلن: {formatToman(event.current_rate_toman)}</span>
                {/* The snapshot is the sum of what each message was priced at when
                    it went out, so it stops matching count times today's rate the
                    moment the plan's price changes. Saying so is the point of
                    showing both numbers. */}
                {event.snapshotted_toman !== event.count * event.current_rate_toman && (
                  <Badge size="xs" variant="warning" label="نرخ پلن از زمان ارسال تغییر کرده" />
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </li>
  );
}

export default function BillingSmsReportPage() {
  const [workspaceSlug, setWorkspaceSlug] = useState("");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(DEFAULT_BILLING_PER_PAGE);

  const debouncedWorkspaceSlug = useDebouncedValue(workspaceSlug);

  const params = useMemo(
    () => ({
      cursor: pageToCursor(page, perPage),
      per_page: perPage,
      workspace_slug: debouncedWorkspaceSlug.trim() || undefined,
    }),
    [debouncedWorkspaceSlug, page, perPage]
  );

  const { data, error, isLoading } = useSWR(BILLING_SMS_REPORT(params), () => BillingService.smsReport(params));

  const rows = useMemo<TBillingSmsReportRow[]>(() => data?.results ?? [], [data]);
  const total = data?.total_results ?? 0;
  const pageCount = Math.max(1, data?.total_pages ?? 1);
  const rangeStart = (page - 1) * perPage + 1;
  const rangeEnd = rangeStart + rows.length - 1;

  const heading = "گزارش هزینهٔ پیامک";
  const description =
    "برای هر ورک‌اسپیس: آنچه از کیف پول کسر شده، آنچه تحویل داده شده، و آنچه کسر شده ولی پیامکی برایش نیست. «بی‌حساب» تفاضل این دو است و هر مقدار غیر از صفر یعنی لازم است دفتر کل باز شود. خواندن این صفحه برای هر ورک‌اسپیس نمایش‌داده‌شده یک سطر در رد دسترسی‌ها ثبت می‌کند.";

  if (isLoading) {
    return (
      <BillingRTLFrame title={heading} description={description}>
        <BillingNav />
        <BillingEmptyState message="در حال بارگذاری گزارش هزینهٔ پیامک…" />
      </BillingRTLFrame>
    );
  }

  if (error) {
    return (
      <BillingRTLFrame title={heading} description={description}>
        <BillingNav />
        <BillingEmptyState message={getErrorMessage(error, "بارگذاری گزارش هزینهٔ پیامک ناموفق بود.")} />
      </BillingRTLFrame>
    );
  }

  return (
    <BillingRTLFrame title={heading} description={description}>
      <BillingNav />

      <BillingSection title="صافی‌ها">
        <div className="flex min-w-56 flex-col gap-1">
          <label className="text-13 text-tertiary" htmlFor="sms-report-workspace">
            شناسه ورک‌اسپیس (slug)
          </label>
          <Input
            id="sms-report-workspace"
            size="lg"
            placeholder="workspace-slug"
            value={workspaceSlug}
            onChange={(event) => {
              setWorkspaceSlug(event.target.value);
              setPage(1);
            }}
          />
        </div>
      </BillingSection>

      {rows.length === 0 ? (
        <BillingEmptyState message="برای این صافی‌ها پیامکی ثبت نشده است." />
      ) : (
        <BillingSection title="هزینه به تفکیک ورک‌اسپیس">
          <ul className="flex flex-col gap-3" role="list">
            {rows.map((row) => (
              <SmsReportRow key={row.workspace_id} row={row} />
            ))}
          </ul>

          <div className="flex flex-col gap-2">
            <p className="text-body-sm-regular text-secondary">
              نمایش {formatNumber(rangeStart)} تا {formatNumber(rangeEnd)} از {formatNumber(total)} ورک‌اسپیس
            </p>
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
          </div>
        </BillingSection>
      )}
    </BillingRTLFrame>
  );
}
