/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { BillingService, BILLING_FEATURE_FLAGS } from "@plane/services";
import type { TFeatureFlag, TBillingLimitType } from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";
import { Switch } from "@makeplane/propel/components/switch";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
import { getErrorMessage } from "../utils";

const LIMIT_TYPE_LABELS: Record<TBillingLimitType, string> = {
  boolean: "روشن یا خاموش",
  number: "محدودیت عددی",
  unlimited: "نامحدود",
};

export default function BillingFeatureFlagsPage() {
  const { data, error, isLoading, mutate } = useSWR(BILLING_FEATURE_FLAGS({}), () => BillingService.featureFlags({}));
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const flags = useMemo<TFeatureFlag[]>(() => data?.results ?? [], [data]);

  const handleToggleActive = useCallback(
    async (flag: TFeatureFlag) => {
      setUpdatingId(flag.id);
      try {
        await BillingService.updateFeatureFlag(flag.id, { is_active: !flag.is_active });
        await mutate();
      } catch (err) {
        console.error("Failed to toggle feature flag", err);
      } finally {
        setUpdatingId(null);
      }
    },
    [mutate]
  );

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
                  <div className="flex items-center gap-3">
                    <Badge size="xs" variant="info" label={LIMIT_TYPE_LABELS[flag.limit_type]} />
                    {flag.limit_type === "number" && flag.unit_label && (
                      <span className="text-12 text-tertiary">واحد: {flag.unit_label}</span>
                    )}
                    <div className="flex items-center gap-1.5 border-r border-subtle pr-3">
                      <span className="text-12 text-tertiary">{flag.is_active ? "فعال در سیستم" : "غیرفعال"}</span>
                      <Switch
                        size="sm"
                        checked={flag.is_active}
                        disabled={updatingId === flag.id}
                        onCheckedChange={() => handleToggleActive(flag)}
                        aria-label={`وضعیت ${flag.name}`}
                      />
                    </div>
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
