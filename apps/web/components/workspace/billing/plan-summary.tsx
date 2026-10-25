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
  const progressColor =
    percentageUsed > 90 ? "bg-danger-primary" : percentageUsed > 75 ? "bg-warning-primary" : "bg-accent-primary";

  return (
    <div className="flex flex-col gap-5 rounded-lg border border-subtle bg-layer-2 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex flex-col gap-1.5">
          <div className="flex flex-wrap items-center gap-2">
            <h4 className="text-body-md-medium text-primary">{plan?.name ?? "بدون پلن مشخص"}</h4>
            <span
              className={`rounded-full px-2.5 py-0.5 text-caption-md-medium ${
                plan?.is_free ? "bg-layer-1 text-tertiary" : "bg-accent-primary/10 text-accent-primary"
              }`}
            >
              {plan?.is_free ? "پلن رایگان" : "پلن فعال (غیر رایگان)"}
            </span>
          </div>
          <p className="text-body-xs-regular text-tertiary">
            {plan?.description ?? "برای این ورک‌اسپیس پلنی ثبت نشده است؛ سقف صندلی اعمال نمی‌شود."}
          </p>
        </div>

        <Link to={`/billing?workspace=${encodeURIComponent(workspaceSlug)}`}>
          <Button variant="primary" size="md" type="button" stretch="auto" label="مشاهده و ارتقای پلن‌ها" />
        </Link>
      </div>

      {!isUnlimited && (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between text-caption-md-regular text-tertiary">
            <span>میزان مصرف صندلی‌ها</span>
            <span className="text-caption-md-medium text-primary">{formatPersianNumber(percentageUsed)}٪</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-layer-1">
            <div
              className={`h-full rounded-full transition-all duration-300 ${progressColor}`}
              style={{ width: `${percentageUsed}%` }}
            />
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="flex flex-col gap-1 rounded-md border border-subtle bg-layer-1 p-3.5">
          <span className="text-caption-md-regular text-tertiary">صندلی‌های مصرف‌شده</span>
          <span className="text-body-sm-medium text-primary">{seatsUsedLabel}</span>
        </div>
        <div className="flex flex-col gap-1 rounded-md border border-subtle bg-layer-1 p-3.5">
          <span className="text-caption-md-regular text-tertiary">سقف صندلی پلن</span>
          <span className="text-body-sm-medium text-primary">
            {isUnlimited ? UNLIMITED_SEATS_LABEL : formatPersianNumber(seatLimit)}
          </span>
        </div>
        <div className="flex flex-col gap-1 rounded-md border border-subtle bg-layer-1 p-3.5">
          <span className="text-caption-md-regular text-tertiary">صندلی باقی‌مانده</span>
          <span className="text-body-sm-medium text-primary">
            {seatsRemaining === null ? UNLIMITED_SEATS_LABEL : formatPersianNumber(seatsRemaining)}
          </span>
        </div>
      </div>
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
    <div className="w-full rounded-lg border border-subtle bg-danger-subtle p-4 text-body-xs-medium text-danger-primary">
      {message}
    </div>
  );
}
