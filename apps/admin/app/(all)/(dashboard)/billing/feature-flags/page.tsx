/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useMemo } from "react";
import useSWR from "swr";
import { BillingService, BILLING_FEATURE_FLAGS } from "@plane/services";
import type { TFeatureFlag, TBillingLimitType } from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
import { getErrorMessage } from "../utils";

const LIMIT_TYPE_LABELS: Record<TBillingLimitType, string> = {
  boolean: "روشن یا خاموش",
  number: "محدودیت عددی",
  unlimited: "نامحدود",
};

export default function BillingFeatureFlagsPage() {
  const { data, error, isLoading } = useSWR(BILLING_FEATURE_FLAGS({}), () => BillingService.featureFlags({}));

  const flags = useMemo<TFeatureFlag[]>(() => data?.results ?? [], [data]);

  // Group by category preserving backend order (category, code)
  const categories = useMemo(() => {
    const map = new Map<string, TFeatureFlag[]>();
    for (const flag of flags) {
      if (!map.has(flag.category)) {
        map.set(flag.category, []);
      }
      map.get(flag.category)!.push(flag);
    }
    return map;
  }, [flags]);

  if (isLoading) {
    return (
      <BillingRTLFrame title="پرچم‌های قابلیت" description="کاتالوگ تمام پرچم‌های قابلیت تعریف‌شده در سیستم.">
        <BillingNav />
        <BillingEmptyState message="در حال بارگذاری پرچم‌های قابلیت…" />
      </BillingRTLFrame>
    );
  }

  if (error) {
    return (
      <BillingRTLFrame title="پرچم‌های قابلیت" description="کاتالوگ تمام پرچم‌های قابلیت تعریف‌شده در سیستم.">
        <BillingNav />
        <BillingEmptyState message={getErrorMessage(error, "بارگذاری پرچم‌های قابلیت ناموفق بود.")} />
      </BillingRTLFrame>
    );
  }

  if (flags.length === 0) {
    return (
      <BillingRTLFrame title="پرچم‌های قابلیت" description="کاتالوگ تمام پرچم‌های قابلیت تعریف‌شده در سیستم.">
        <BillingNav />
        <BillingEmptyState message="پرچم قابلیتی تعریف نشده است." />
      </BillingRTLFrame>
    );
  }

  return (
    <BillingRTLFrame
      title="پرچم‌های قابلیت"
      description="کاتالوگ تمام پرچم‌های قابلیت تعریف‌شده در سیستم. پرچم‌های غیرفعال(outline) بدون کنترل نمایش داده می‌شوند."
    >
      <BillingNav />

      {Array.from(categories.entries()).map(([category, categoryFlags]) => (
        <BillingSection key={category} title={category}>
          <ul className="flex flex-col gap-2" role="list">
            {categoryFlags.map((flag) => (
              <li
                key={flag.id}
                className={
                  "rounded-custom flex flex-col gap-2 border border-subtle p-3 " + (flag.is_active ? "" : "opacity-50")
                }
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className="truncate text-13 text-primary">{flag.name}</span>
                    <span className="font-mono text-12 text-tertiary">{flag.code}</span>
                    {flag.description && <span className="truncate text-11 text-tertiary">{flag.description}</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge
                      size="xs"
                      variant={flag.is_active ? "success" : "neutral"}
                      label={flag.is_active ? "فعال" : "غیرفعال"}
                    />
                    <Badge size="xs" variant="info" label={LIMIT_TYPE_LABELS[flag.limit_type]} />
                    {flag.limit_type === "number" && flag.unit_label && (
                      <span className="text-12 text-tertiary">واحد: {flag.unit_label}</span>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </BillingSection>
      ))}
    </BillingRTLFrame>
  );
}
