/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo, useState } from "react";
import useSWR from "swr";
import { AreaChart } from "@plane/blocks/charts/area-chart";
import { PieChart } from "@plane/blocks/charts/pie-chart";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { BILLING_ANALYTICS, BillingService } from "@plane/services";
import type { TPaymentTransactionStatus } from "@plane/types";
import { CreditCard, RefreshCw, TrendingUp, Users, Wallet, Activity } from "lucide-react";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
import { GATEWAY_LABELS, TRANSACTION_STATUS_LABELS, TRANSACTION_STATUS_VARIANTS } from "../constants";
import { formatNumber, formatToman, getErrorMessage } from "../utils";

export default function BillingAnalyticsPage() {
  const [months, setMonths] = useState<number>(6);

  const { data, error, isLoading, mutate } = useSWR(BILLING_ANALYTICS(months), () =>
    BillingService.analytics({ months })
  );

  const trendChartData = useMemo(() => {
    if (!data?.monthly_trend) return [];
    return data.monthly_trend.map((item) => ({
      date: item.label,
      revenue: item.revenue,
      count: item.count,
    }));
  }, [data?.monthly_trend]);

  const areas = useMemo(
    () => [
      {
        key: "revenue" as const,
        label: "درآمد (تومان)",
        fill: "rgba(62, 99, 221, 0.2)",
        fillOpacity: 1,
        stackId: "revenue-stack",
        showDot: true,
        smoothCurves: true,
        strokeColor: "#3E63DD",
        strokeOpacity: 1,
      },
    ],
    []
  );

  const pieData = useMemo(() => {
    if (!data?.plan_distribution) return [];
    return data.plan_distribution.map((item) => ({
      id: item.key,
      key: item.key,
      value: item.count,
      name: item.name,
      color: item.color,
    }));
  }, [data?.plan_distribution]);

  const pieCells = useMemo(() => {
    if (!data?.plan_distribution) return [];
    return data.plan_distribution.map((item) => ({
      key: item.key,
      fill: item.color,
    }));
  }, [data?.plan_distribution]);

  const totalActivePlanSubs = useMemo(() => {
    if (!data?.plan_distribution) return 0;
    return data.plan_distribution.reduce((acc, curr) => acc + curr.count, 0);
  }, [data?.plan_distribution]);

  return (
    <BillingRTLFrame
      title="آمار و تحلیل درآمد"
      description="شاخص‌های کلیدی مالی، روند درآمد ماهیانه، سهم پلن‌ها و توزیع درگاه‌های پرداخت"
      actions={
        <div className="flex items-center gap-2">
          <div className="rounded-custom flex items-center border border-subtle bg-layer-1 p-0.5">
            <button
              type="button"
              onClick={() => setMonths(6)}
              className={`text-caption rounded-xs px-3 py-1 font-medium transition-colors ${
                months === 6
                  ? "bg-accent-subtle text-accent-primary"
                  : "text-secondary hover:bg-layer-2 hover:text-primary"
              }`}
            >
              ۶ ماه اخیر
            </button>
            <button
              type="button"
              onClick={() => setMonths(12)}
              className={`text-caption rounded-xs px-3 py-1 font-medium transition-colors ${
                months === 12
                  ? "bg-accent-subtle text-accent-primary"
                  : "text-secondary hover:bg-layer-2 hover:text-primary"
              }`}
            >
              ۱۲ ماه اخیر
            </button>
          </div>
          <Button
            variant="secondary"
            size="sm"
            stretch="auto"
            onClick={() => mutate()}
            disabled={isLoading}
            icon={<RefreshCw className={`size-3.5 ${isLoading ? "animate-spin" : ""}`} />}
            label="بروزرسانی"
          />
        </div>
      }
    >
      <BillingNav />

      {error ? (
        <div className="rounded-custom border-danger/30 bg-danger/10 text-danger border p-4 text-13">
          خطا در دریافت آمار مالی: {getErrorMessage(error, "لطفاً مجدداً تلاش کنید")}
        </div>
      ) : null}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {/* Card 1: Total Revenue */}
        <div className="rounded-custom shadow-xs flex flex-col justify-between border border-subtle bg-layer-1 p-4">
          <div className="flex items-center justify-between">
            <span className="text-body-sm-medium text-secondary">درآمد کل وصول‌شده</span>
            <div className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex size-8 items-center justify-center rounded-xs">
              <Wallet className="size-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-heading-md font-bold text-primary">
              {isLoading ? "..." : formatToman(data?.summary.total_revenue_toman)}
            </div>
            <div className="text-caption mt-1 text-tertiary">
              {isLoading ? "..." : `${formatNumber(data?.summary.paid_transactions)} تراکنش موفق پرداخت`}
            </div>
          </div>
        </div>

        {/* Card 2: MRR */}
        <div className="rounded-custom shadow-xs flex flex-col justify-between border border-subtle bg-layer-1 p-4">
          <div className="flex items-center justify-between">
            <span className="text-body-sm-medium text-secondary">درآمد تکرارشونده ماهیانه (MRR)</span>
            <div className="flex size-8 items-center justify-center rounded-xs bg-accent-subtle text-accent-primary">
              <TrendingUp className="size-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-heading-md font-bold text-primary">
              {isLoading ? "..." : formatToman(data?.summary.mrr_toman)}
            </div>
            <div className="text-caption mt-1 text-tertiary">بر مبنای اشتراک‌های دوره‌ای فعال</div>
          </div>
        </div>

        {/* Card 3: Active Subscriptions */}
        <div className="rounded-custom shadow-xs flex flex-col justify-between border border-subtle bg-layer-1 p-4">
          <div className="flex items-center justify-between">
            <span className="text-body-sm-medium text-secondary">اشتراک‌های فعال</span>
            <div className="bg-sky-500/10 text-sky-600 dark:text-sky-400 flex size-8 items-center justify-center rounded-xs">
              <Users className="size-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-heading-md font-bold text-primary">
              {isLoading ? "..." : `${formatNumber(data?.summary.active_subscriptions)} اشتراک`}
            </div>
            <div className="text-caption mt-1 text-tertiary">ورک‌اسپیس‌های دارای پلن خریداری‌شده</div>
          </div>
        </div>

        {/* Card 4: Success Rate */}
        <div className="rounded-custom shadow-xs flex flex-col justify-between border border-subtle bg-layer-1 p-4">
          <div className="flex items-center justify-between">
            <span className="text-body-sm-medium text-secondary">نرخ موفقیت پرداخت</span>
            <div className="bg-amber-500/10 text-amber-600 dark:text-amber-400 flex size-8 items-center justify-center rounded-xs">
              <Activity className="size-4" />
            </div>
          </div>
          <div className="mt-3">
            <div className="text-heading-md font-bold text-primary">
              {isLoading ? "..." : `${formatNumber(data?.summary.success_rate)}٪`}
            </div>
            <div className="text-caption mt-1 text-tertiary">
              {isLoading ? "..." : `از مجموع ${formatNumber(data?.summary.total_transactions)} تراکنش ثبت‌شده`}
            </div>
          </div>
        </div>
      </div>

      {/* Main Area Chart: Monthly Revenue Trend */}
      <BillingSection title={`روند درآمد ماهیانه (${formatNumber(months)} ماه اخیر)`}>
        {isLoading ? (
          <div className="flex h-64 items-center justify-center text-body-sm-regular text-secondary">
            در حال بارگذاری نمودار...
          </div>
        ) : trendChartData.length > 0 ? (
          <div className="h-72 w-full pt-4">
            <AreaChart
              className="size-full"
              data={trendChartData}
              areas={areas}
              xAxis={{
                key: "date",
                label: "ماه",
              }}
              yAxis={{
                key: "revenue",
                label: "تومان",
                allowDecimals: false,
              }}
              showTooltip
            />
          </div>
        ) : (
          <BillingEmptyState message="داده‌ای برای نمایش در این بازه زمانی وجود ندارد" />
        )}
      </BillingSection>

      {/* Two Column Grid: Plan Distribution and Gateway Breakdown */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left Column: Plan Distribution */}
        <BillingSection title="توزیع اشتراک‌ها بر اساس پلن">
          {isLoading ? (
            <div className="flex h-56 items-center justify-center text-body-sm-regular text-secondary">
              در حال بارگذاری...
            </div>
          ) : pieData.length > 0 && totalActivePlanSubs > 0 ? (
            <div className="grid grid-cols-1 items-center gap-4 sm:grid-cols-2">
              <div className="h-56 w-full">
                <PieChart
                  className="size-full"
                  dataKey="value"
                  data={pieData}
                  cells={pieCells}
                  showTooltip
                  tooltipLabel="تعداد اشتراک"
                  innerRadius="50%"
                  cornerRadius={4}
                  paddingAngle={4}
                  showLabel={false}
                />
              </div>
              <div className="flex flex-col gap-2.5">
                {data?.plan_distribution.map((item) => (
                  <div key={item.key} className="flex items-center justify-between text-body-sm-regular">
                    <div className="flex items-center gap-2">
                      <div className="size-3 shrink-0 rounded-xs" style={{ backgroundColor: item.color }} />
                      <span className="font-medium text-primary">{item.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-secondary">{formatNumber(item.count)} اشتراک</span>
                      <span className="text-caption font-mono text-tertiary">({formatToman(item.revenue_toman)})</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <BillingEmptyState message="هیچ اشتراک فعالی در سیستم ثبت نشده است" />
          )}
        </BillingSection>

        {/* Right Column: Gateway & Transaction Status Distribution */}
        <BillingSection title="عملکرد درگاه‌های پرداخت و وضعیت تراکنش‌ها">
          {isLoading ? (
            <div className="flex h-56 items-center justify-center text-body-sm-regular text-secondary">
              در حال بارگذاری...
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {/* Gateways Breakdown */}
              <div className="flex flex-col gap-2">
                <span className="text-caption font-semibold text-secondary">آمار درگاه‌ها</span>
                {data?.gateway_distribution && data.gateway_distribution.length > 0 ? (
                  data.gateway_distribution.map((gw) => {
                    const gwLabel = GATEWAY_LABELS[gw.key as keyof typeof GATEWAY_LABELS] || gw.name || gw.key;
                    const successPct = gw.count > 0 ? Math.round((gw.paid_count / gw.count) * 100) : 0;
                    return (
                      <div
                        key={gw.key}
                        className="rounded-custom flex items-center justify-between border border-subtle bg-layer-2 px-3 py-2 text-body-sm-regular"
                      >
                        <div className="flex items-center gap-2">
                          <CreditCard className="size-4 text-tertiary" />
                          <span className="font-medium text-primary">{gwLabel}</span>
                          <span className="text-caption font-mono text-tertiary">
                            ({formatNumber(gw.paid_count)} از {formatNumber(gw.count)} موفق)
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-caption font-medium text-secondary">
                            {formatToman(gw.revenue_toman)}
                          </span>
                          <Badge
                            variant={successPct >= 50 ? "success" : "neutral"}
                            size="xs"
                            label={`${formatNumber(successPct)}٪ موفق`}
                          />
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <span className="text-caption text-tertiary">درگاهی ثبت نشده است</span>
                )}
              </div>

              {/* Status Distribution */}
              <div className="flex flex-col gap-2 border-t border-subtle pt-2">
                <span className="text-caption font-semibold text-secondary">توزیع وضعیت تراکنش‌ها</span>
                <div className="flex flex-wrap gap-2">
                  {data?.status_distribution && data.status_distribution.length > 0 ? (
                    data.status_distribution.map((s) => {
                      const statusKey = s.status as TPaymentTransactionStatus;
                      const label = TRANSACTION_STATUS_LABELS[statusKey] || s.label || s.status;
                      const variant = TRANSACTION_STATUS_VARIANTS[statusKey] || "neutral";
                      return (
                        <div
                          key={s.status}
                          className="rounded-custom text-caption flex items-center gap-1.5 border border-subtle bg-layer-1 px-2.5 py-1"
                        >
                          <Badge variant={variant} size="xs" label={label} />
                          <span className="font-semibold text-primary">{formatNumber(s.count)}</span>
                        </div>
                      );
                    })
                  ) : (
                    <span className="text-caption text-tertiary">تراکنشی ثبت نشده است</span>
                  )}
                </div>
              </div>
            </div>
          )}
        </BillingSection>
      </div>
    </BillingRTLFrame>
  );
}
