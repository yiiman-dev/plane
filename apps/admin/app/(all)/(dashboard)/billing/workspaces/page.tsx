/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
import { Link } from "react-router";
import { BillingService, BILLING_ADMIN_WORKSPACES } from "@plane/services";
import type { TAdminWorkspaceSummary } from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";
import { Input } from "@makeplane/propel/components/input";
import { Pagination } from "@makeplane/propel/components/pagination";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
import { DEFAULT_BILLING_PER_PAGE, formatNumber, formatToman, getErrorMessage, pageToCursor } from "../utils";

export default function BillingWorkspacesPage() {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(DEFAULT_BILLING_PER_PAGE);
  const debouncedSearch = search.trim() || undefined;

  const params = useMemo(
    () => ({
      cursor: pageToCursor(page, perPage),
      per_page: perPage,
      search: debouncedSearch,
    }),
    [debouncedSearch, page, perPage]
  );

  const { data, error, isLoading } = useSWR(BILLING_ADMIN_WORKSPACES(params), () =>
    BillingService.adminWorkspaces(params)
  );

  const workspaces = useMemo<TAdminWorkspaceSummary[]>(() => data?.results ?? [], [data]);
  const totalPages = Math.max(1, data?.total_pages ?? 1);
  const totalResults = data?.total_results ?? 0;
  const rangeStart = (page - 1) * perPage + 1;
  const rangeEnd = rangeStart + workspaces.length - 1;

  return (
    <BillingRTLFrame title="ورک‌اسپیس‌ها" description="لیست تمام ورک‌اسپیس‌ها با پلن، صندلی و موجودی کیف پول.">
      <BillingNav />

      <BillingSection title="فیلترها">
        <div className="flex flex-wrap items-end gap-3">
          <div className="flex min-w-56 flex-col gap-1">
            <label className="text-13 text-tertiary" htmlFor="workspace-search">
              جست‌وجو
            </label>
            <Input
              id="workspace-search"
              size="lg"
              placeholder="نام یا شناسه ورک‌اسپیس"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
      </BillingSection>

      {isLoading && <BillingEmptyState message="در حال بارگذاری ورک‌اسپیس‌ها…" />}
      {!isLoading && error && <BillingEmptyState message={getErrorMessage(error, "بارگذاری ورک‌اسپیس‌ها ناموفق بود.")} />}
      {!isLoading && !error && workspaces.length === 0 && (
        <BillingEmptyState message="ورک‌اسپیسی با این فیلترها یافت نشد." />
      )}

      <BillingSection title="ورک‌اسپیس‌ها">
        <ul className="flex flex-col gap-2" role="list">
          {workspaces.map((workspace) => (
            <li key={workspace.id} className="rounded-custom flex flex-col gap-2 border border-subtle p-3">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-5 md:grid-cols-6">
                <div className="flex flex-col gap-0.5">
                  <span className="text-12 text-tertiary">نام</span>
                  <Link to={`/billing/workspaces/${workspace.slug}/`} className="text-13 text-primary hover:underline">
                    {workspace.name}
                  </Link>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-12 text-tertiary">شناسه</span>
                  <span className="font-mono text-13 text-secondary">{workspace.slug}</span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-12 text-tertiary">پلن</span>
                  {workspace.plan_code ? (
                    <Badge size="xs" variant="neutral" label={workspace.plan_code} />
                  ) : (
                    <span className="text-13 text-tertiary">—</span>
                  )}
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-12 text-tertiary">صندلی</span>
                  <span className="text-13 text-secondary">{formatNumber(workspace.seats)}</span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-12 text-tertiary">موجودی کیف پول</span>
                  <span className="text-13 text-secondary">{formatToman(workspace.balance_toman)}</span>
                </div>
                <div className="flex flex-col gap-0.5 sm:col-span-2 md:col-span-1">
                  <span className="text-12 text-tertiary">عملیات</span>
                  <Link
                    to={`/billing/workspaces/${workspace.slug}/`}
                    className="text-13 text-accent-primary hover:underline"
                  >
                    مشاهده جزئیات
                  </Link>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </BillingSection>

      {totalResults > 0 && (
        <div className="flex flex-col gap-2">
          <p className="text-body-sm-regular text-secondary">
            نمایش {formatNumber(rangeStart)} تا {formatNumber(rangeEnd)} از {formatNumber(totalResults)} مورد
          </p>
          <Pagination
            page={page}
            pageCount={totalPages}
            onPageChange={setPage}
            labels={{
              root: "صفحه‌بندی",
              previous: "صفحه قبل",
              next: "صفحه بعد",
              page: (p: number) => `رفتن به صفحه ${formatNumber(p)}`,
              perPageValue: (pageSize: number) => formatNumber(pageSize),
              perPage: "در هر صفحه",
            }}
            pageSize={{
              value: perPage,
              options: [10, 20, 50, 100],
              onValueChange: (pageSize: number) => {
                setPerPage(pageSize);
                setPage(1);
              },
            }}
          />
        </div>
      )}
    </BillingRTLFrame>
  );
}
