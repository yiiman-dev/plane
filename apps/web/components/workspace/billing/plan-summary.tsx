/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Link } from "react-router";
import useSWR from "swr";
import { Button } from "@makeplane/propel/components/button";
import { BILLING_WORKSPACE_ENTITLEMENT, BillingService } from "@plane/services";
import type { TBillingWorkspaceEntitlement } from "@plane/types";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
// local imports
import { formatPersianNumber, getBillingErrorMessage, UNLIMITED_SEATS_LABEL } from "./constants";

type Props = {
  workspaceSlug: string;
};

/**
 * States the workspace's own billing facts: which plan is bound to it, how much of the seat budget
 * is spent, and the way to buy more. Every number comes from the server entitlement read, so the
 * panel never computes a price or a limit on its own.
 */
export function BillingPlanSummary({ workspaceSlug }: Props) {
  const { data, error } = useSWR(BILLING_WORKSPACE_ENTITLEMENT(workspaceSlug), () =>
    BillingService.workspaceEntitlement(workspaceSlug)
  );

  if (error) return <ErrorState message={getBillingErrorMessage(error, "خطا در دریافت وضعیت پلن این ورک‌اسپیس.")} />;
  if (!data) return <LoadingState />;

  return <PlanSummaryContent entitlement={data} workspaceSlug={workspaceSlug} />;
}

/** Split out so the markup stays readable and the server data is passed down as one object. */
function PlanSummaryContent({
  entitlement,
  workspaceSlug,
}: {
  entitlement: TBillingWorkspaceEntitlement;
  workspaceSlug: string;
}) {
  const { plan, seat_limit: seatLimit, seats_used: seatsUsed, seats_remaining: seatsRemaining } = entitlement;
  const isUnlimited = seatLimit === null;
  // The seat label reads differently when there is no ceiling, because "0 of unlimited" is a lie.
  const seatsUsedLabel = isUnlimited
    ? `${formatPersianNumber(seatsUsed)} از ${UNLIMITED_SEATS_LABEL}`
    : `${formatPersianNumber(seatsUsed)} از ${formatPersianNumber(seatLimit)}`;

  const percentageUsed = !isUnlimited && seatLimit > 0 ? Math.min(100, Math.round((seatsUsed / seatLimit) * 100)) : 0;

  return (
    <div className="flex flex-col gap-4 rounded-xl border border-subtle bg-surface-1 p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg text-content-on-surface font-semibold">{plan?.name ?? "بدون پلن مشخص"}</h3>
            <span
              className={`text-xs rounded-full border px-2.5 py-0.5 font-medium ${
                plan?.is_free
                  ? "border-subtle bg-surface-2 text-content-2"
                  : "border-primary/20 bg-primary/10 text-primary"
              }`}
            >
              {plan?.is_free ? "پلن رایگان" : "پلن فعال (غیر رایگان)"}
            </span>
          </div>
          <p className="text-sm text-content-2">
            {plan?.description ?? "برای این ورک‌اسپیس پلنی ثبت نشده است؛ سقف صندلی اعمال نمی‌شود."}
          </p>
        </div>

        <Link to={`/billing?workspace=${encodeURIComponent(workspaceSlug)}`}>
          <Button variant="primary" size="md" type="button" stretch="auto" label="مشاهده و ارتقای پلن‌ها" />
        </Link>
      </div>

      <div className="flex flex-col gap-3 border-t border-subtle pt-4">
        {!isUnlimited && (
          <div className="flex flex-col gap-1.5 pb-2">
            <div className="flex items-center justify-between text-xs text-content-2">
              <span>میزان مصرف صندلی‌ها</span>
              <span className="font-medium text-content-on-surface">{formatPersianNumber(percentageUsed)}٪</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-surface-2">
              <div
                className={`h-full transition-all duration-300 ${
                  percentageUsed > 90 ? "bg-danger-500" : percentageUsed > 75 ? "bg-warning-500" : "bg-primary"
                }`}
                style={{ width: `${percentageUsed}%` }}
              />
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="flex flex-col rounded-lg bg-surface-2 p-3">
            <span className="text-xs text-content-2">صندلی‌های مصرف‌شده</span>
            <span className="mt-1 text-base font-semibold text-content-on-surface">{seatsUsedLabel}</span>
          </div>
          <div className="flex flex-col rounded-lg bg-surface-2 p-3">
            <span className="text-xs text-content-2">سقف صندلی پلن</span>
            <span className="mt-1 text-base font-semibold text-content-on-surface">
              {isUnlimited ? UNLIMITED_SEATS_LABEL : formatPersianNumber(seatLimit)}
            </span>
          </div>
          <div className="flex flex-col rounded-lg bg-surface-2 p-3">
            <span className="text-xs text-content-2">صندلی باقی‌مانده</span>
            <span className="mt-1 text-base font-semibold text-content-on-surface">
              {seatsRemaining === null ? UNLIMITED_SEATS_LABEL : formatPersianNumber(seatsRemaining)}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function SeatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-sm flex items-center justify-between gap-3">
      <span className="text-content-2">{label}</span>
      <span className="text-content-on-surface font-medium">{value}</span>
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
