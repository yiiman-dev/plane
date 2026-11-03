/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR from "swr";
import { useParams } from "react-router";
import { BillingService, BILLING_ADMIN_WORKSPACE_BILLING } from "@plane/services";
import { Badge } from "@makeplane/propel/components/badge";
import { formatNumber, formatToman, getErrorMessage } from "../../utils";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../../components/billing-layout";
import { WorkspaceBillingTabs } from "../../components/workspace-billing-tabs";

type TWorkspaceBillingTab = "plan" | "subscription" | "seats" | "wallet";

type TLedgerEntry = {
  id: string;
  type: string;
  description: string;
  amount_toman: number;
  reference: string | null;
  created_at: string;
};

type TLedgerResponse = {
  results: TLedgerEntry[];
  total_results: number;
  total_pages: number;
};

export default function BillingWorkspaceDetailPage() {
  const { slug } = useParams<{ slug: string }>();
  const [activeTab, setActiveTab] = useState<TWorkspaceBillingTab>("plan");

  const {
    data: workspaceData,
    error: workspaceError,
    isLoading: isWorkspaceLoading,
  } = useSWR(slug ? BILLING_ADMIN_WORKSPACE_BILLING(slug) : null, () => BillingService.adminWorkspaceBilling(slug!));

  // Ledger uses the existing Phase 1 endpoint
  const {
    data: ledgerData,
    error: ledgerError,
    isLoading: isLedgerLoading,
  } = useSWR<TLedgerResponse>(slug ? `billing-admin-workspace-ledger-${slug}` : null, () =>
    BillingService.get(`/api/billing/admin/workspaces/${slug!}/wallet/ledger/`).then((response) => response.data)
  );

  const workspace = workspaceData;
  const ledger = ledgerData;

  if (isWorkspaceLoading) {
    return (
      <BillingRTLFrame title="بارگذاری…" description="در حال دریافت اطلاعات ورک‌اسپیس">
        <BillingNav />
        <BillingEmptyState message="در حال بارگذاری اطلاعات ورک‌اسپیس…" />
      </BillingRTLFrame>
    );
  }

  if (workspaceError || !workspace) {
    return (
      <BillingRTLFrame title="خطا" description="ورک‌اسپیس یافت نشد">
        <BillingNav />
        <BillingEmptyState message={getErrorMessage(workspaceError, "ورک‌اسپیس یافت نشد.")} />
      </BillingRTLFrame>
    );
  }

  return (
    <BillingRTLFrame title={workspace.name} description={workspace.slug}>
      <BillingNav />

      <WorkspaceBillingTabs activeTab={activeTab} onChange={setActiveTab} />

      {activeTab === "plan" && (
        <BillingSection title="پلن فعال">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">پلن</span>
              {workspace.plan_name ? (
                <span className="text-13 text-primary">{workspace.plan_name}</span>
              ) : (
                <span className="text-13 text-tertiary">—</span>
              )}
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">کد پلن</span>
              {workspace.plan_code ? (
                <Badge size="xs" variant="neutral" label={workspace.plan_code} />
              ) : (
                <span className="text-13 text-tertiary">—</span>
              )}
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">وضعیت اشتراک</span>
              {workspace.subscription_status ? (
                <Badge size="xs" variant="neutral" label={workspace.subscription_status} />
              ) : (
                <span className="text-13 text-tertiary">—</span>
              )}
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">شروع اشتراک</span>
              <span className="text-13 text-secondary">
                {workspace.starts_at ? new Date(workspace.starts_at).toLocaleDateString("fa-IR") : "—"}
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">انقضای اشتراک</span>
              <span className="text-13 text-secondary">
                {workspace.ends_at ? new Date(workspace.ends_at).toLocaleDateString("fa-IR") : "—"}
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">حالت پروریشن</span>
              {workspace.proration_mode ? (
                <Badge size="xs" variant="neutral" label={workspace.proration_mode} />
              ) : (
                <span className="text-13 text-tertiary">—</span>
              )}
            </div>
          </div>
        </BillingSection>
      )}

      {activeTab === "subscription" && (
        <BillingSection title="اشتراک و انقضا">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">وضعیت اشتراک</span>
              {workspace.subscription_status ? (
                <Badge size="xs" variant="neutral" label={workspace.subscription_status} />
              ) : (
                <span className="text-13 text-tertiary">—</span>
              )}
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">شروع اشتراک</span>
              <span className="text-13 text-secondary">
                {workspace.starts_at ? new Date(workspace.starts_at).toLocaleDateString("fa-IR") : "—"}
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">انقضای اشتراک</span>
              <span className="text-13 text-secondary">
                {workspace.ends_at ? new Date(workspace.ends_at).toLocaleDateString("fa-IR") : "—"}
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">قفل تمدید (روز)</span>
              <span className="text-13 text-secondary">
                {workspace.renew_lock_days !== null && workspace.renew_lock_days !== undefined
                  ? formatNumber(workspace.renew_lock_days)
                  : "—"}
              </span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">حالت پروریشن</span>
              {workspace.proration_mode ? (
                <Badge size="xs" variant="neutral" label={workspace.proration_mode} />
              ) : (
                <span className="text-13 text-tertiary">—</span>
              )}
            </div>
          </div>
        </BillingSection>
      )}

      {activeTab === "seats" && (
        <BillingSection title="صندلی و اعضا">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">تعداد صندلی</span>
              <span className="text-13 text-secondary">{formatNumber(workspace.seats)}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">اعضای فعال</span>
              <span className="text-13 text-secondary">{formatNumber(workspace.active_members)}</span>
            </div>
            <div className="flex flex-col gap-0.5">
              <span className="text-12 text-tertiary">موجودی در نگهداری</span>
              <span className="text-13 text-secondary">{formatToman(workspace.hold_balance_toman)}</span>
            </div>
          </div>
        </BillingSection>
      )}

      {activeTab === "wallet" && (
        <>
          <div className="rounded-custom border border-warning-subtle bg-warning-subtle px-4 py-3 text-13 text-warning-primary">
            این اطلاعات قابلیت مشاهدهٔ مشتری دارد و هر بار مشاهدهٔ آن ثبت می‌شود.
          </div>
          <BillingSection title="کیف پول و دفتر کل">
            {isLedgerLoading && <BillingEmptyState message="در حال بارگذاری دفتر کل…" />}
            {!isLedgerLoading && ledgerError && (
              <BillingEmptyState message={getErrorMessage(ledgerError, "بارگذاری دفتر کل ناموفق بود.")} />
            )}
            {!isLedgerLoading && !ledgerError && ledger && (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3">
                <div className="flex flex-col gap-0.5">
                  <span className="text-12 text-tertiary">موجودی فعلی</span>
                  <span className="text-13 text-primary">{formatToman(workspace.balance_toman)}</span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-12 text-tertiary">موجودی در نگهداری</span>
                  <span className="text-13 text-secondary">{formatToman(workspace.hold_balance_toman)}</span>
                </div>
                <div className="flex flex-col gap-0.5">
                  <span className="text-12 text-tertiary">موجودی قابل برداشت</span>
                  <span className="text-success text-13">
                    {formatToman(workspace.balance_toman - workspace.hold_balance_toman)}
                  </span>
                </div>
              </div>
            )}
            {!isLedgerLoading && !ledgerError && !ledger && <BillingEmptyState message="دفتر کل خالی است." />}
            {ledger && (
              <div className="mt-4">
                <span className="text-11 text-tertiary">تراکنش‌های اخیر</span>
                <ul className="mt-2 flex flex-col gap-2" role="list">
                  {ledger.results.slice(0, 10).map((entry: any) => (
                    <li key={entry.id} className="rounded-custom flex flex-col gap-1 border border-subtle p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="text-13 text-primary">{entry.description}</span>
                        <Badge
                          size="xs"
                          variant={entry.amount_toman >= 0 ? "success" : "danger"}
                          label={formatToman(entry.amount_toman)}
                        />
                      </div>
                      <div className="flex flex-wrap items-center gap-2 text-12 text-tertiary">
                        <span>{entry.type}</span>
                        <span>{new Date(entry.created_at).toLocaleString("fa-IR")}</span>
                        {entry.reference && <span>مرجع: {entry.reference}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
                {ledger.results.length > 10 && (
                  <p className="mt-2 text-12 text-tertiary">
                    و {formatNumber(ledger.results.length - 10)} تراکنش دیگر…
                  </p>
                )}
              </div>
            )}
          </BillingSection>
        </>
      )}
    </BillingRTLFrame>
  );
}
