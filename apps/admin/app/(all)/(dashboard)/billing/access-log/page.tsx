/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
import { BillingService, BILLING_ACCESS_LOG } from "@plane/services";
import type { TBillingAccessLogRow, TBillingAccessLogView } from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";
import { Input } from "@makeplane/propel/components/input";
import { Pagination } from "@makeplane/propel/components/pagination";
import { Select, SelectContent, SelectItem, SelectList, SelectTrigger } from "@makeplane/propel/components/select";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
import { BILLING_PAGE_SIZE_OPTIONS, PAGINATION_LABELS } from "../constants";
import { useDebouncedValue } from "../hooks";
import { DEFAULT_BILLING_PER_PAGE, formatDateTime, formatNumber, getErrorMessage, pageToCursor } from "../utils";

const VIEW_FILTERS: { label: string; value: TBillingAccessLogView | "all" }[] = [
  { label: "همه خواندن‌ها", value: "all" },
  { label: "کیف پول", value: "wallet" },
  { label: "دفتر کل", value: "ledger" },
];

/** One row of the trail. A read by an admin who has since been deleted names nobody. */
function AccessLogRow({ row }: { row: TBillingAccessLogRow }) {
  const viewer = row.viewer_name || row.viewer_email || "کاربر حذف‌شده";

  return (
    <li className="rounded-custom flex flex-col gap-1 border border-subtle p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge size="xs" variant="info" label={row.view_label} />
        <span className="text-13 text-primary">{row.workspace_name ?? "ورک‌اسپیس حذف‌شده"}</span>
        {row.workspace_slug && <span className="font-mono text-12 text-tertiary">{row.workspace_slug}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-3 text-11 text-tertiary">
        <span>خواننده: {viewer}</span>
        {row.viewer_email && row.viewer_name && <span className="font-mono">{row.viewer_email}</span>}
        <span>{formatDateTime(row.created_at)}</span>
        {row.ip_address && <span className="font-mono">{row.ip_address}</span>}
        {row.user_agent && <span className="max-w-80 truncate">{row.user_agent}</span>}
      </div>
    </li>
  );
}

export default function BillingAccessLogPage() {
  const [view, setView] = useState<TBillingAccessLogView | "all">("all");
  const [workspaceSlug, setWorkspaceSlug] = useState("");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(DEFAULT_BILLING_PER_PAGE);

  const debouncedWorkspaceSlug = useDebouncedValue(workspaceSlug);

  const params = useMemo(
    () => ({
      cursor: pageToCursor(page, perPage),
      per_page: perPage,
      // A single view value is sent: the endpoint splits on commas, so this is a
      // filter narrow enough to be readable on screen, not a set.
      view: view === "all" ? undefined : view,
      workspace_slug: debouncedWorkspaceSlug.trim() || undefined,
    }),
    [debouncedWorkspaceSlug, page, perPage, view]
  );

  const { data, error, isLoading } = useSWR(BILLING_ACCESS_LOG(params), () => BillingService.accessLog(params));

  const rows = useMemo<TBillingAccessLogRow[]>(() => data?.results ?? [], [data]);
  const total = data?.total_results ?? 0;
  const pageCount = Math.max(1, data?.total_pages ?? 1);
  const rangeStart = (page - 1) * perPage + 1;
  const rangeEnd = rangeStart + rows.length - 1;

  const heading = "رد دسترسی‌ها";
  const description =
    "هر بار که مدیر کلان موجودی یا دفتر کل یک ورک‌اسپیس را می‌خواند، یک سطر اینجا ثبت می‌شود. خواندن همین صفحه سطری ثبت نمی‌کند، چون موجودی یا دفتری برنمی‌گرداند.";

  if (isLoading) {
    return (
      <BillingRTLFrame title={heading} description={description}>
        <BillingNav />
        <BillingEmptyState message="در حال بارگذاری رد دسترسی‌ها…" />
      </BillingRTLFrame>
    );
  }

  if (error) {
    return (
      <BillingRTLFrame title={heading} description={description}>
        <BillingNav />
        <BillingEmptyState message={getErrorMessage(error, "بارگذاری رد دسترسی‌ها ناموفق بود.")} />
      </BillingRTLFrame>
    );
  }

  return (
    <BillingRTLFrame title={heading} description={description}>
      <BillingNav />

      <BillingSection title="صافی‌ها">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-48 flex-col gap-1">
            <label className="text-13 text-tertiary" htmlFor="access-log-view">
              نوع خواندن
            </label>
            <Select
              value={view}
              onValueChange={(value) => {
                if (!value) return;
                setView(value as TBillingAccessLogView | "all");
                setPage(1);
              }}
            >
              <SelectTrigger id="access-log-view" size="lg" placeholder="همه خواندن‌ها" />
              <SelectContent>
                <SelectList>
                  {VIEW_FILTERS.map((option) => (
                    <SelectItem key={option.value} size="lg" value={option.value} label={option.label} />
                  ))}
                </SelectList>
              </SelectContent>
            </Select>
          </div>

          <div className="flex min-w-56 flex-col gap-1">
            <label className="text-13 text-tertiary" htmlFor="access-log-workspace">
              شناسه ورک‌اسپیس (slug)
            </label>
            <Input
              id="access-log-workspace"
              size="lg"
              placeholder="workspace-slug"
              value={workspaceSlug}
              onChange={(event) => {
                setWorkspaceSlug(event.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
      </BillingSection>

      {rows.length === 0 ? (
        <BillingEmptyState message="سطری با این صافی‌ها ثبت نشده است." />
      ) : (
        <BillingSection title="خواندن‌های ثبت‌شده">
          <ul className="flex flex-col gap-2" role="list">
            {rows.map((row) => (
              <AccessLogRow key={row.id} row={row} />
            ))}
          </ul>

          <div className="flex flex-col gap-2">
            <p className="text-body-sm-regular text-secondary">
              نمایش {formatNumber(rangeStart)} تا {formatNumber(rangeEnd)} از {formatNumber(total)} مورد
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
