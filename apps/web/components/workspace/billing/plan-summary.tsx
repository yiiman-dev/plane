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

  return <PlanSummaryContent entitlement={data} />;
}

/** Split out so the markup stays readable and the server data is passed down as one object. */
function PlanSummaryContent({ entitlement }: { entitlement: TBillingWorkspaceEntitlement }) {
  const { plan, seat_limit: seatLimit, seats_used: seatsUsed, seats_remaining: seatsRemaining } = entitlement;
  const isUnlimited = seatLimit === null;
  // The seat label reads differently when there is no ceiling, because "0 of unlimited" is a lie.
  const seatsUsedLabel = isUnlimited
    ? `${formatPersianNumber(seatsUsed)} از ${UNLIMITED_SEATS_LABEL}`
    : `${formatPersianNumber(seatsUsed)} از ${formatPersianNumber(seatLimit)}`;

  return (
    <div className="flex flex-col gap-4 rounded-md border border-subtle bg-surface-1 p-4">
      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="text-base text-content-on-surface font-medium">{plan?.name ?? "بدون پلن مشخص"}</h3>
          <span
            className={`text-xs rounded-md border border-subtle px-2 py-0.5 ${plan?.is_free ? "text-content-2" : "text-primary"}`}
          >
            {plan?.is_free ? "پلن رایگان" : "پلن غیر رایگان"}
          </span>
        </div>
        <p className="text-sm text-content-2">
          {plan?.description ?? "برای این ورک‌اسپیس پلنی ثبت نشده است؛ سقف صندلی اعمال نمی‌شود."}
        </p>
      </div>

      <div className="flex flex-col gap-3 border-t border-subtle pt-3">
        <SeatRow label="صندلی‌های مصرف‌شده" value={seatsUsedLabel} />
        <SeatRow label="سقف صندلی" value={isUnlimited ? UNLIMITED_SEATS_LABEL : formatPersianNumber(seatLimit)} />
        <SeatRow
          label="صندلی باقی‌مانده"
          value={seatsRemaining === null ? UNLIMITED_SEATS_LABEL : formatPersianNumber(seatsRemaining)}
        />
      </div>

      <div className="border-t border-subtle pt-3">
        {/* The checkout lives outside the workspace route, so the slug travels as a query parameter. */}
        <Link to={`/billing?workspace=${encodeURIComponent(entitlement.workspace.slug)}`}>
          <Button variant="primary" size="md" type="button" label="ارتقای پلن و خرید صندلی بیشتر" stretch="full" />
        </Link>
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
