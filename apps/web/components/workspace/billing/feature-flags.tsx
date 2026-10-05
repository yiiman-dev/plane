/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import useSWR from "swr";
import { LockOutline } from "@makeplane/propel/icons";
import { Switch } from "@makeplane/propel/components/switch";
import { setPromiseToast, setToast } from "@plane/blocks/toast";
import { BILLING_WORKSPACE_FEATURE_FLAGS, BillingService } from "@plane/services";
import type { TBillingWorkspaceFeatureFlag } from "@plane/types";
// plane imports
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
// hooks
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import { getBillingErrorMessage, getFeatureCategoryLabel } from "./constants";

type Props = {
  workspaceSlug: string;
};

/**
 * Lists every capability the instance defines and states whether this workspace may use it.
 *
 * The list is readable by any active member, but only a workspace admin may switch a capability,
 * matching the server permission on the enable and disable endpoints.
 */
export function BillingFeatureFlags({ workspaceSlug }: Props) {
  // permissions
  const { allowPermissions } = useUserPermissions();
  const canManageFeatureFlags = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  // data
  const { data, error, mutate } = useSWR(BILLING_WORKSPACE_FEATURE_FLAGS(workspaceSlug), () =>
    BillingService.workspaceFeatureFlags(workspaceSlug)
  );
  // pending state, one flag code at a time, so the rest of the list stays usable
  const [pendingCode, setPendingCode] = useState<string | null>(null);

  if (error) return <ErrorState message={getBillingErrorMessage(error, "خطا در دریافت پرچم‌های قابلیت.")} />;
  if (!data) return <LoadingState />;

  const flags = data.results ?? [];
  if (!flags.length)
    return (
      <div className="flex w-full flex-col items-center gap-1 rounded-md border border-subtle bg-surface-1 px-4 py-10 text-center">
        <h3 className="text-content-on-surface text-sm font-medium">قابلیتی تعریف نشده است</h3>
        <p className="text-content-2 text-sm">هنوز پرچم قابلیتی برای این نمونه تعریف نشده است.</p>
      </div>
    );

  /** Switches one capability and refetches, because the server decides the resulting state. */
  const handleToggle = async (flag: TBillingWorkspaceFeatureFlag, nextEnabled: boolean) => {
    setPendingCode(flag.code);
    const mutation = nextEnabled
      ? BillingService.enableWorkspaceFeatureFlag(workspaceSlug, flag.code)
      : BillingService.disableWorkspaceFeatureFlag(workspaceSlug, flag.code);

    try {
      await setPromiseToast(mutation, {
        loading: nextEnabled ? "در حال فعال‌سازی قابلیت..." : "در حال غیرفعال‌سازی قابلیت...",
        success: {
          title: nextEnabled ? "قابلیت فعال شد" : "قابلیت غیرفعال شد",
          message: () =>
            nextEnabled ? "قابلیت انتخابی برای این ورک‌اسپیس فعال شد." : "قابلیت انتخابی برای این ورک‌اسپیس خاموش شد.",
        },
        error: {
          title: "تغییر وضعیت انجام نشد",
          message: () => "تغییر وضعیت قابلیت ناموفق بود. لطفاً دوباره تلاش کنید.",
        },
      });
    } catch (mutationError) {
      // The server message is already Persian, so it is shown as is instead of a generic message.
      setToast({
        type: "error",
        title: "تغییر وضعیت انجام نشد",
        message: getBillingErrorMessage(mutationError, "تغییر وضعیت قابلیت ناموفق بود. لطفاً دوباره تلاش کنید."),
      });
    } finally {
      setPendingCode(null);
      await mutate();
    }
  };

  /** Groups the flags by category so the page reads as sections instead of one long list. */
  const groupedFlags: Record<string, TBillingWorkspaceFeatureFlag[]> = {};
  for (const flag of flags) {
    const groupKey = getFeatureCategoryLabel(flag.category);
    groupedFlags[groupKey] = groupedFlags[groupKey] ?? [];
    groupedFlags[groupKey].push(flag);
  }

  return (
    <div className="flex flex-col gap-4">
      {!canManageFeatureFlags && (
        <p className="text-content-2 text-sm">فقط مدیر ورک‌اسپیس می‌تواند قابلیت‌ها را روشن یا خاموش کند.</p>
      )}

      {Object.entries(groupedFlags).map(([groupLabel, groupFlags]) => (
        <section key={groupLabel} className="flex flex-col gap-2 rounded-md border border-subtle bg-surface-1 p-4">
          <h3 className="text-content-2 text-sm font-medium">{groupLabel}</h3>
          {groupFlags.map((flag) => (
            <FeatureFlagRow
              key={flag.code}
              flag={flag}
              canManage={canManageFeatureFlags}
              isPending={pendingCode === flag.code}
              onToggle={handleToggle}
            />
          ))}
        </section>
      ))}
    </div>
  );
}

type RowProps = {
  canManage: boolean;
  flag: TBillingWorkspaceFeatureFlag;
  isPending: boolean;
  onToggle: (flag: TBillingWorkspaceFeatureFlag, nextEnabled: boolean) => Promise<void>;
};

/** One capability row. A capability the plan does not grant stays visible but locked. */
function FeatureFlagRow({ canManage, flag, isPending, onToggle }: RowProps) {
  const isLocked = !flag.has_access;

  return (
    <div className="flex items-start justify-between gap-3 border-t border-subtle pt-3 first:border-t-0 first:pt-0">
      <div className="flex flex-col gap-1">
        <span className="text-content-on-surface text-sm font-medium">{flag.name}</span>
        {flag.description && <span className="text-content-2 text-sm">{flag.description}</span>}
        {isLocked && (
          <span className="text-warning-600 text-xs flex items-center gap-1">
            <LockOutline className="size-3.5" />
            این قابلیت در پلن فعلی شما فعال نیست. برای استفاده باید پلن ورک‌اسپیس را ارتقا دهید.
          </span>
        )}
      </div>
      <Switch
        // The plan grant is the hard gate: without it the switch can never be turned on.
        size="sm"
        disabled={!flag.has_access || !canManage || isPending}
        checked={flag.is_enabled}
        onCheckedChange={(checked) => onToggle(flag, checked)}
        aria-label={flag.name}
      />
    </div>
  );
}

function LoadingState() {
  return (
    <div className="grid w-full place-items-center py-10">
      <LogoSpinner />
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="border-danger-200 bg-danger-50 text-danger-500 text-sm w-full rounded-md border p-4">{message}</div>
  );
}
