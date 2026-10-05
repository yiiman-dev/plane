/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { useSearchParams } from "react-router";
import useSWR from "swr";
import { Button } from "@makeplane/propel/components/button";
import { Select, SelectContent, SelectItem, SelectList, SelectTrigger } from "@makeplane/propel/components/select";
import { BILLING_PLAN_QUOTE, BILLING_PUBLIC_PLANS, BillingService } from "@plane/services";
import type { TBillingCycle, TPublicPlan } from "@plane/types";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
// local imports
import { BILLING_CYCLES, formatNumber, formatToman, getErrorMessage } from "./constants";

/** Reads the plan list. Every price shown on this page comes from the admin configured plan. */
function BillingPlans() {
  const { data, error } = useSWR(BILLING_PUBLIC_PLANS, () => BillingService.publicPlans());
  if (error) return <ErrorState message={getErrorMessage(error, "خطا در دریافت فهرست پلن‌ها.")} />;
  if (!data) return <LoadingState />;

  const plans = data?.results ?? [];
  if (!plans.length)
    return (
      <EmptyState
        title="پلن فعالی وجود ندارد"
        description="هنوز پلنی برای خرید تعریف نشده است. لطفاً بعداً مراجعه کنید."
      />
    );

  return (
    <div className="grid w-full grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {plans.map((plan) => (
        <PlanCard key={plan.code} plan={plan} />
      ))}
    </div>
  );
}

/**
 * One plan card. The card only states what the plan is; the payable amount is decided by the
 * seat and cycle selector above it so that the same quote drives every card.
 */
function PlanCard({ plan }: { plan: TPublicPlan }) {
  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle bg-surface-1 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-base text-content-on-surface font-medium">{plan.name}</h3>
        {plan.access_level && (
          <span className="text-xs text-content-1 rounded-md border border-subtle px-2 py-0.5">
            {plan.access_level}
          </span>
        )}
      </div>
      {plan.description && <p className="text-sm text-content-2">{plan.description}</p>}
      <div className="text-sm flex flex-col gap-1 border-t border-subtle pt-3">
        <PriceRow label="قیمت ماهانه" value={formatToman(plan.monthly_price_toman)} />
        <PriceRow label="قیمت سالانه" value={formatToman(plan.yearly_price_toman)} />
        <PriceRow
          label="قیمت هر صندلی"
          value={
            plan.per_seat_price_toman > 0
              ? `${formatToman(plan.per_seat_price_toman)} به ازای هر صندلی اضافه`
              : "شامل پلن"
          }
        />
        <PriceRow label="صندلی‌های شامل‌شده" value={`${formatNumber(plan.included_seats)} صندلی`} />
        <PriceRow
          label="محدوده مجاز"
          value={`${formatNumber(plan.min_seats)} تا ${formatNumber(plan.max_seats)} صندلی`}
        />
      </div>
      {plan.features.length > 0 && (
        <ul className="text-sm text-content-2 flex flex-col gap-1 border-t border-subtle pt-3">
          {plan.features.map((feature) => (
            <li key={feature} className="flex items-center gap-2">
              <span className="bg-content-3 size-1.5 shrink-0 rounded-full" />
              <span>{feature}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Prices the selected plan on the server for the current seat count and cycle. */
function BillingQuote({ plan, seats, cycle }: { plan: TPublicPlan; seats: number; cycle: TBillingCycle }) {
  const { data, error } = useSWR(BILLING_PLAN_QUOTE(plan.code, seats, cycle), () =>
    BillingService.planQuote(plan.code, { cycle, seats })
  );

  if (error) return <ErrorState message={getErrorMessage(error, "خطا در محاسبه مبلغ پرداخت.")} />;
  if (!data) return <LoadingState />;

  return (
    <div className="flex flex-col gap-3 rounded-md border border-subtle bg-surface-1 p-4">
      <h3 className="text-sm text-content-on-surface font-medium">مبلغ پرداختی</h3>
      <div className="text-sm flex flex-col gap-2">
        <PriceRow
          label={`قیمت پایه پلن (${cycle === "yearly" ? "سالانه" : "ماهانه"})`}
          value={formatToman(data.base_price_toman)}
        />
        <PriceRow
          label={`صندلی‌های اضافه (${formatNumber(data.extra_seats)})`}
          value={formatToman(data.extra_seats_total_toman)}
        />
        <PriceRow label="جمع کل" value={formatToman(data.total_toman)} />
      </div>
    </div>
  );
}

function PriceRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-content-2">{label}</span>
      <span className="text-content-on-surface font-medium">{value}</span>
    </div>
  );
}

/** Centered spinner used while a request is in flight. */
function LoadingState() {
  return (
    <div className="grid w-full place-items-center py-10">
      <LogoSpinner />
    </div>
  );
}

function ErrorState({ message }: { message: string }) {
  return (
    <div className="border-danger-200 bg-danger-50 text-sm text-danger-500 w-full rounded-md border p-4">{message}</div>
  );
}

function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="flex w-full flex-col items-center gap-1 rounded-md border border-subtle bg-surface-1 px-4 py-10 text-center">
      <h3 className="text-sm text-content-on-surface font-medium">{title}</h3>
      <p className="text-sm text-content-2">{description}</p>
    </div>
  );
}

export default function BillingPage() {
  const [selectedPlanCode, setSelectedPlanCode] = useState<string | null>(null);
  const [cycle, setCycle] = useState<TBillingCycle>("monthly");
  const [seatsInput, setSeatsInput] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  // The checkout sits outside the workspace route, so the workspace comes as a query parameter.
  // The server re-checks active membership and binds the subscription to it, never to a guess here.
  const [searchParams] = useSearchParams();
  const workspaceSlug = searchParams.get("workspace") ?? undefined;

  const { data, error } = useSWR(BILLING_PUBLIC_PLANS, () => BillingService.publicPlans());
  const plans = data?.results ?? [];
  const selectedPlan: TPublicPlan | null = plans.find((plan) => plan.code === selectedPlanCode) ?? null;

  // The seat count is only meaningful once a plan is picked, because min/max/included are per plan.
  const seats = seatsInput.trim() === "" ? (selectedPlan?.included_seats ?? 1) : Number.parseInt(seatsInput, 10);
  const minSeats = selectedPlan?.min_seats ?? 1;
  const maxSeats = selectedPlan?.max_seats ?? Number.MAX_SAFE_INTEGER;
  const isSeatsValid = Number.isFinite(seats) && seats >= minSeats && seats <= maxSeats;
  const canCheckout = Boolean(selectedPlan) && isSeatsValid && !isSubmitting;

  /**
   * Creates the order and hands the browser to the gateway the routing engine chose. The gateway
   * name is announced first, so the payer knows which provider is about to open.
   */
  const handleCheckout = async () => {
    if (!selectedPlan || !canCheckout) return;
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const order = await BillingService.createPaymentOrder({
        cycle,
        plan_code: selectedPlan.code,
        seats,
        workspace_slug: workspaceSlug,
      });
      if (!order?.redirect_url) throw new Error("آدرس درگاه پرداخت دریافت نشد.");
      window.location.href = order.redirect_url;
    } catch (checkoutError) {
      setIsSubmitting(false);
      setSubmitError(getErrorMessage(checkoutError, "شروع پرداخت ناموفق بود. لطفاً دوباره تلاش کنید."));
    }
  };

  if (error)
    return (
      <div className="mx-auto w-full max-w-4xl p-4">
        <ErrorState message={getErrorMessage(error, "خطا در دریافت فهرست پلن‌ها.")} />
      </div>
    );

  if (!data)
    return (
      <div className="mx-auto w-full max-w-4xl p-4">
        <LoadingState />
      </div>
    );

  const planOptions = plans.map((plan) => ({ label: plan.name, value: plan.code }));

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-6 p-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl text-content-on-surface font-medium">خرید پلن</h1>
        <p className="text-sm text-content-2">پلن مورد نظر را انتخاب کنید، تعداد صندلی و دوره پرداخت را مشخص کنید.</p>
      </header>

      <BillingPlans />

      {selectedPlan && (
        <div className="flex flex-col gap-4 rounded-md border border-subtle bg-surface-1 p-4">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="text-sm flex flex-col gap-1">
              <span className="text-content-2">پلن</span>
              <Select<string>
                items={planOptions}
                value={selectedPlan.code}
                onValueChange={(value) => {
                  setSelectedPlanCode(value);
                  setSeatsInput("");
                }}
              >
                <SelectTrigger size="md" placeholder="انتخاب پلن" />
                <SelectContent side="bottom" align="start">
                  <SelectList>
                    {planOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value} size="md" label={option.label} />
                    ))}
                  </SelectList>
                </SelectContent>
              </Select>
            </div>

            <div className="text-sm flex flex-col gap-1">
              <span className="text-content-2">دوره پرداخت</span>
              <Select<string>
                items={BILLING_CYCLES}
                value={cycle}
                onValueChange={(value) => setCycle(value as TBillingCycle)}
              >
                <SelectTrigger size="md" placeholder="انتخاب دوره" />
                <SelectContent side="bottom" align="start">
                  <SelectList>
                    {BILLING_CYCLES.map((option) => (
                      <SelectItem key={option.value} value={option.value} size="md" label={option.label} />
                    ))}
                  </SelectList>
                </SelectContent>
              </Select>
            </div>

            <div className="text-sm flex flex-col gap-1">
              <span className="text-content-2">تعداد صندلی</span>
              <input
                id="billing-seats"
                aria-label="تعداد صندلی"
                type="number"
                min={minSeats}
                max={maxSeats === Number.MAX_SAFE_INTEGER ? undefined : maxSeats}
                value={seatsInput}
                onChange={(event) => setSeatsInput(event.target.value)}
                placeholder={`${formatNumber(selectedPlan.included_seats)}`}
                className="border-subtle-strong text-sm text-content-on-surface border bg-surface-2 px-2 py-1.5 outline-none"
              />
              <span className="text-xs text-content-3">
                {`مجاز: ${formatNumber(minSeats)} تا ${formatNumber(maxSeats)} صندلی`}
              </span>
            </div>
          </div>

          {!isSeatsValid && (
            <p className="text-sm text-danger-500">
              {`تعداد صندلی باید بین ${formatNumber(minSeats)} تا ${formatNumber(maxSeats)} باشد.`}
            </p>
          )}

          {submitError && <ErrorState message={submitError} />}

          <BillingQuote plan={selectedPlan} seats={seats} cycle={cycle} />

          <Button
            variant="primary"
            size="md"
            stretch="auto"
            type="button"
            loading={isSubmitting}
            disabled={!canCheckout}
            onClick={handleCheckout}
            label="پرداخت و انتقال به درگاه"
          />
          {isSubmitting && <p className="text-xs text-content-2">در حال اتصال به درگاه پرداخت، لطفاً صفحه را نبندید.</p>}
        </div>
      )}
    </div>
  );
}
