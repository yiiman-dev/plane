/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import useSWR from "swr";
import {
  ArrowRight,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  Minus,
  Plus,
  ShieldCheck,
  Sparkles,
  Zap,
} from "lucide-react";
import { Button } from "@makeplane/propel/components/button";
import {
  BILLING_PLAN_QUOTE,
  BILLING_PUBLIC_PLANS,
  BILLING_WORKSPACE_ENTITLEMENT,
  BillingService,
} from "@plane/services";
import type { TBillingCycle, TBillingFreePlanResult, TPublicPlan } from "@plane/types";
// components
import { LogoSpinner } from "@/components/common/logo-spinner";
// local imports
import { formatNumber, formatToman, getErrorMessage } from "./constants";

export default function BillingPage() {
  const [searchParams] = useSearchParams();
  const workspaceSlug = searchParams.get("workspace") ?? undefined;

  const [selectedPlanCode, setSelectedPlanCode] = useState<string | null>(null);
  const [cycle, setCycle] = useState<TBillingCycle>("monthly");
  const [seatsCount, setSeatsCount] = useState<number>(1);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [freeResult, setFreeResult] = useState<TBillingFreePlanResult | null>(null);

  const checkoutRef = useRef<HTMLDivElement>(null);

  // Fetch plans
  const {
    data: plansData,
    error: plansError,
    isLoading: plansLoading,
  } = useSWR(BILLING_PUBLIC_PLANS, () => BillingService.publicPlans());

  // Fetch workspace entitlement if workspaceSlug is present
  const { data: entitlement, mutate: mutateEntitlement } = useSWR(
    workspaceSlug ? BILLING_WORKSPACE_ENTITLEMENT(workspaceSlug) : null,
    () => (workspaceSlug ? BillingService.workspaceEntitlement(workspaceSlug) : null)
  );

  const plans = useMemo<TPublicPlan[]>(() => plansData?.results ?? [], [plansData]);

  // Set default selected plan once plans load if none is selected
  useEffect(() => {
    if (!selectedPlanCode && plans.length > 0) {
      // Prefer the first non-free plan or first available
      const candidate = plans.find((p) => p.access_level !== "free" && p.access_level !== "0") ?? plans[0];
      setSelectedPlanCode(candidate.code);
      setSeatsCount(candidate.included_seats || 1);
    }
  }, [plans, selectedPlanCode]);

  const selectedPlan: TPublicPlan | null = useMemo(
    () => plans.find((p) => p.code === selectedPlanCode) ?? null,
    [plans, selectedPlanCode]
  );

  // Keep seat count within current plan bounds when plan changes
  const handleSelectPlan = (plan: TPublicPlan) => {
    setSelectedPlanCode(plan.code);
    const initialSeats = Math.max(plan.min_seats, Math.min(plan.max_seats, plan.included_seats || 1));
    setSeatsCount(initialSeats);
    setSubmitError(null);

    // Smooth scroll to checkout if on mobile or if needed
    if (checkoutRef.current) {
      checkoutRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  };

  const minSeats = selectedPlan?.min_seats ?? 1;
  const maxSeats = selectedPlan?.max_seats ?? 9999;
  const isSeatsValid = seatsCount >= minSeats && seatsCount <= maxSeats;
  const canCheckout = Boolean(selectedPlan) && isSeatsValid && !isSubmitting;

  const handleSeatChange = (delta: number) => {
    setSeatsCount((prev) => {
      const next = prev + delta;
      return Math.max(minSeats, Math.min(maxSeats, next));
    });
  };

  const handleCheckout = async () => {
    if (!selectedPlan || !canCheckout) return;
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const order = await BillingService.createPaymentOrder({
        cycle,
        plan_code: selectedPlan.code,
        seats: seatsCount,
        workspace_slug: workspaceSlug,
      });
      if (!order?.redirect_url) throw new Error("آدرس درگاه پرداخت دریافت نشد.");
      window.location.href = order.redirect_url;
    } catch (checkoutError) {
      setIsSubmitting(false);
      setSubmitError(getErrorMessage(checkoutError, "شروع پرداخت ناموفق بود. لطفاً دوباره تلاش کنید."));
    }
  };

  // A plan with no price for the chosen cycle is free: nothing to pay, only a change to record.
  const selectedPrice = selectedPlan
    ? cycle === "yearly"
      ? selectedPlan.yearly_price_toman
      : selectedPlan.monthly_price_toman
    : null;
  const isFreeSelection = selectedPrice === 0;
  const isSelectedCurrent = Boolean(selectedPlan && entitlement?.plan?.code === selectedPlan.code);

  const handleApplyFree = async () => {
    if (!workspaceSlug) return;
    setIsSubmitting(true);
    setSubmitError(null);
    setFreeResult(null);
    try {
      const result = await BillingService.applyFreePlan(workspaceSlug);
      setFreeResult(result);
      await mutateEntitlement();
    } catch (applyError) {
      setSubmitError(getErrorMessage(applyError, "ثبت پلن رایگان ناموفق بود. لطفاً دوباره تلاش کنید."));
    } finally {
      setIsSubmitting(false);
    }
  };

  if (plansLoading) {
    return (
      <div className="grid min-h-screen w-full place-items-center py-20">
        <LogoSpinner />
      </div>
    );
  }

  if (plansError) {
    return (
      <div dir="rtl" className="mx-auto w-full max-w-4xl p-6">
        <div className="rounded-lg border border-subtle bg-danger-subtle p-6 text-center">
          <h2 className="text-body-md-medium text-danger-primary">خطا در بارگذاری پلن‌ها</h2>
          <p className="mt-2 text-body-xs-regular text-danger-primary">
            {getErrorMessage(plansError, "امکان دریافت فهرست پلن‌های مالی وجود ندارد.")}
          </p>
        </div>
      </div>
    );
  }

  const currentPlanCode = entitlement?.plan?.code;

  return (
    <div dir="rtl" className="mx-auto flex w-full max-w-7xl flex-col gap-10 px-4 py-8 text-start sm:px-6 lg:px-8">
      {/* Top navigation & workspace header */}
      <div className="flex flex-col gap-4 border-b border-subtle pb-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-3">
          {workspaceSlug && (
            <Link
              to={`/${workspaceSlug}/settings/billing`}
              className="inline-flex items-center gap-1.5 rounded-md border border-subtle bg-layer-1 px-3 py-1.5 text-body-xs-medium text-secondary transition-colors hover:bg-layer-1-hover hover:text-primary"
            >
              <ArrowRight className="size-4" />
              بازگشت به تنظیمات ورک‌اسپیس
            </Link>
          )}
          {entitlement?.workspace && (
            <div className="flex items-center gap-2 rounded-full border border-subtle bg-layer-1 px-3 py-1 text-caption-md-regular">
              <span className="text-tertiary">ورک‌اسپیس:</span>
              <span className="text-caption-md-medium text-primary">{entitlement.workspace.name}</span>
            </div>
          )}
        </div>

        {entitlement?.plan && (
          <div className="flex items-center gap-2 text-caption-md-regular">
            <span className="text-tertiary">پلن فعلی ورک‌اسپیس:</span>
            <span className="rounded-md bg-accent-subtle px-2 py-0.5 text-caption-md-medium text-accent-primary">
              {entitlement.plan.name}
            </span>
          </div>
        )}
      </div>

      {/* Hero */}
      <div className="flex flex-col items-center text-center">
        <div className="inline-flex items-center gap-1.5 rounded-full bg-accent-subtle px-3 py-1 text-caption-md-medium text-accent-primary">
          <Sparkles className="size-3.5" />
          پلن‌های منعطف و قیمت‌گذاری شفاف
        </div>
        <h1 className="mt-4 text-h3-medium text-primary">انتخاب پلن مناسب برای تیم شما</h1>
        <p className="mt-3 max-w-2xl text-body-sm-regular text-tertiary">
          امکانات حرفه‌ای مدیریت پروژه، وابستگی تسک‌ها، هوش مصنوعی، و ظرفیت صندلی مورد نیاز تیم خود را به سادگی فعال کنید.
        </p>

        {/* Billing cycle switcher */}
        <div className="mt-8 inline-flex items-center gap-1 rounded-full border border-subtle bg-layer-2 p-1">
          <button
            type="button"
            onClick={() => setCycle("monthly")}
            className={`rounded-full px-5 py-1.5 text-body-xs-medium transition-colors ${
              cycle === "monthly" ? "bg-layer-1 text-primary shadow-raised-100" : "text-tertiary hover:text-secondary"
            }`}
          >
            پرداخت ماهانه
          </button>
          <button
            type="button"
            onClick={() => setCycle("yearly")}
            className={`flex items-center gap-1.5 rounded-full px-5 py-1.5 text-body-xs-medium transition-colors ${
              cycle === "yearly" ? "bg-layer-1 text-primary shadow-raised-100" : "text-tertiary hover:text-secondary"
            }`}
          >
            <span>پرداخت سالانه</span>
            <span className="rounded-full bg-success-subtle px-2 py-0.5 text-caption-sm-medium text-success-primary">
              ۲۰٪ تخفیف
            </span>
          </button>
        </div>
      </div>

      {/* Plans grid */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
        {plans.map((plan) => {
          const isSelected = selectedPlanCode === plan.code;
          const isCurrent = currentPlanCode === plan.code;
          const isPopular = plan.access_level === "pro" || plan.access_level === "business";

          const price = cycle === "yearly" ? plan.yearly_price_toman : plan.monthly_price_toman;

          return (
            <div
              key={plan.code}
              className={`relative flex flex-col justify-between rounded-lg border bg-layer-2 p-6 transition-colors ${
                isSelected ? "border-accent-strong" : "border-subtle hover:border-strong-1"
              }`}
            >
              {isPopular && (
                <div className="absolute start-1/2 -top-3 -translate-x-1/2 rounded-full border border-subtle bg-accent-subtle px-3 py-0.5 text-caption-sm-medium text-accent-primary">
                  پیشنهاد ویژه
                </div>
              )}

              <div>
                {/* Header */}
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-h5-medium text-primary">{plan.name}</h3>
                  {isCurrent && (
                    <span className="rounded-md bg-layer-1 px-2 py-0.5 text-caption-md-regular text-tertiary">
                      پلن فعلی شما
                    </span>
                  )}
                </div>

                {plan.description && (
                  <p className="mt-2 min-h-8 text-body-xs-regular text-tertiary">{plan.description}</p>
                )}

                {/* Pricing */}
                <div className="mt-5 border-t border-subtle pt-4">
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-h3-medium text-primary">{price === 0 ? "رایگان" : formatNumber(price)}</span>
                    {price > 0 && (
                      <span className="text-caption-md-regular text-tertiary">
                        تومان / {cycle === "yearly" ? "سالانه" : "ماهانه"}
                      </span>
                    )}
                  </div>

                  <div className="mt-2 text-caption-md-regular text-tertiary">
                    {plan.per_seat_price_toman > 0 ? (
                      <span>{formatToman(plan.per_seat_price_toman)} به ازای هر صندلی اضافه</span>
                    ) : (
                      <span>شامل {formatNumber(plan.included_seats)} صندلی</span>
                    )}
                  </div>
                </div>

                {/* Features */}
                <div className="mt-6 border-t border-subtle pt-4">
                  <h4 className="text-body-xs-medium text-secondary">امکانات و ویژگی‌ها:</h4>
                  <ul className="mt-3 flex flex-col gap-2.5 text-body-xs-regular text-tertiary">
                    <li className="flex items-center gap-2">
                      <Check className="size-4 shrink-0 text-success-primary" />
                      <span>
                        شامل <strong className="text-secondary">{formatNumber(plan.included_seats)} صندلی</strong> اولیه
                        (حداکثر {formatNumber(plan.max_seats)})
                      </span>
                    </li>
                    {plan.features.map((feature) => (
                      <li key={feature} className="flex items-center gap-2">
                        <Check className="size-4 shrink-0 text-success-primary" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Action */}
              <div className="mt-8 pt-4">
                <Button
                  variant={isSelected ? "primary" : "secondary"}
                  size="md"
                  stretch="full"
                  type="button"
                  onClick={() => handleSelectPlan(plan)}
                  label={isSelected ? "پلن انتخابی شما" : "انتخاب و ادامه خرید"}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected plan: configuration and checkout */}
      {selectedPlan && (
        <div ref={checkoutRef} className="rounded-lg border border-subtle bg-layer-2 p-6">
          <div className="flex flex-col gap-2 border-b border-subtle pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-accent-subtle text-accent-primary">
                  <Zap className="size-3.5" />
                </span>
                <h2 className="text-h5-medium text-primary">پیکربندی و تسویه‌حساب: پلن {selectedPlan.name}</h2>
              </div>
              <p className="mt-1 text-caption-md-regular text-tertiary">
                تعداد صندلی و دوره پرداخت را تعیین کنید؛ مبلغ فاکتور به صورت رسمی و بلادرنگ محاسبه می‌شود.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-caption-md-regular text-tertiary">دوره پرداخت:</span>
              <span className="rounded-full border border-subtle bg-layer-1 px-3 py-1 text-caption-md-medium text-secondary">
                {cycle === "yearly" ? "سالانه (۲۰٪ تخفیف)" : "ماهانه"}
              </span>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* Seats & trust */}
            <div className="flex flex-col gap-5 lg:col-span-6">
              <div className="rounded-lg border border-subtle bg-layer-1 p-4">
                <label htmlFor="seats-input" className="text-body-sm-medium text-primary">
                  تعداد صندلی‌های مورد نیاز (کاربران تیم)
                </label>
                <p className="mt-1 text-caption-md-regular text-tertiary">
                  شامل {formatNumber(selectedPlan.included_seats)} صندلی پایه. حداقل {formatNumber(minSeats)} و حداکثر{" "}
                  {formatNumber(maxSeats)} صندلی مجاز است.
                </p>

                <div className="mt-4 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => handleSeatChange(-1)}
                    disabled={seatsCount <= minSeats}
                    aria-label="کاهش صندلی"
                    className="flex size-9 items-center justify-center rounded-md border border-subtle bg-layer-2 text-secondary transition-colors hover:bg-layer-2-hover disabled:opacity-40"
                  >
                    <Minus className="size-4" />
                  </button>
                  <input
                    id="seats-input"
                    type="number"
                    min={minSeats}
                    max={maxSeats}
                    value={seatsCount}
                    onChange={(e) => {
                      const val = Number.parseInt(e.target.value, 10);
                      if (Number.isFinite(val)) setSeatsCount(val);
                    }}
                    className="h-9 w-24 rounded-md border border-subtle bg-layer-2 text-center text-body-sm-medium text-primary outline-none focus:border-accent-strong"
                  />
                  <button
                    type="button"
                    onClick={() => handleSeatChange(1)}
                    disabled={seatsCount >= maxSeats}
                    aria-label="افزایش صندلی"
                    className="flex size-9 items-center justify-center rounded-md border border-subtle bg-layer-2 text-secondary transition-colors hover:bg-layer-2-hover disabled:opacity-40"
                  >
                    <Plus className="size-4" />
                  </button>
                  <span className="text-caption-md-regular text-tertiary">صندلی فعال</span>
                </div>

                {!isSeatsValid && (
                  <p className="mt-2 text-caption-md-medium text-danger-primary">
                    تعداد صندلی باید بین {formatNumber(minSeats)} و {formatNumber(maxSeats)} باشد.
                  </p>
                )}
              </div>

              <div className="grid grid-cols-1 gap-3 text-caption-md-regular text-tertiary sm:grid-cols-2">
                <div className="flex items-center gap-2 rounded-md border border-subtle bg-layer-1 p-3">
                  <ShieldCheck className="size-4 shrink-0 text-success-primary" />
                  <span>پرداخت امن از طریق درگاه شاپرک</span>
                </div>
                <div className="flex items-center gap-2 rounded-md border border-subtle bg-layer-1 p-3">
                  <CheckCircle2 className="size-4 shrink-0 text-success-primary" />
                  <span>فعال‌سازی آنی پس از پرداخت</span>
                </div>
              </div>
            </div>

            {/* Quote & checkout */}
            <div className="flex flex-col justify-between gap-4 rounded-lg border border-subtle bg-layer-1 p-5 lg:col-span-6">
              <OrderQuote plan={selectedPlan} seats={seatsCount} cycle={cycle} />

              {submitError && (
                <div className="rounded-md bg-danger-subtle p-3 text-caption-md-medium text-danger-primary">
                  {submitError}
                </div>
              )}

              {isFreeSelection ? (
                <div className="flex flex-col gap-3">
                  {freeResult && (
                    <div className="rounded-md bg-success-subtle p-3 text-caption-md-medium text-success-primary">
                      {freeResult.status === "already_free" || !freeResult.effective_at
                        ? "پلن رایگان برای این ورک‌اسپیس ثبت شد."
                        : `پلن رایگان از ${new Date(freeResult.effective_at).toLocaleDateString("fa-IR", {
                            year: "numeric",
                            month: "long",
                            day: "numeric",
                          })} فعال می‌شود.`}
                    </div>
                  )}
                  {workspaceSlug ? (
                    <Button
                      variant="primary"
                      size="lg"
                      stretch="full"
                      type="button"
                      loading={isSubmitting}
                      disabled={isSubmitting || isSelectedCurrent}
                      onClick={handleApplyFree}
                      label={isSelectedCurrent ? "این پلن هم‌اکنون فعال است" : "اعمال پلن رایگان"}
                    />
                  ) : (
                    <p className="text-caption-md-regular text-tertiary">
                      برای اعمال پلن رایگان، این صفحه را از تنظیمات صورتحساب ورک‌اسپیس باز کنید.
                    </p>
                  )}
                </div>
              ) : (
                <Button
                  variant="primary"
                  size="lg"
                  stretch="full"
                  type="button"
                  loading={isSubmitting}
                  disabled={!canCheckout}
                  onClick={handleCheckout}
                  label="پرداخت و اتصال به درگاه بانکی"
                />
              )}
            </div>
          </div>
        </div>
      )}

      <FeatureComparisonSection plans={plans} />

      <BillingFAQSection />
    </div>
  );
}

/** Real-time server quote breakdown */
function OrderQuote({ plan, seats, cycle }: { plan: TPublicPlan; seats: number; cycle: TBillingCycle }) {
  const { data, error, isLoading } = useSWR(BILLING_PLAN_QUOTE(plan.code, seats, cycle), () =>
    BillingService.planQuote(plan.code, { cycle, seats })
  );

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-6 text-caption-md-regular text-tertiary">
        <LogoSpinner />
        <span className="mt-2">در حال محاسبه فاکتور رسمی...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-caption-md-regular text-danger-primary">
        {getErrorMessage(error, "امکان محاسبه فاکتور وجود ندارد. لطفاً صندلی مجاز انتخاب کنید.")}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-body-sm-medium text-primary">خلاصه فاکتور پرداخت</h3>

      <div className="flex flex-col gap-2 border-t border-subtle pt-3 text-caption-md-regular">
        <div className="flex items-center justify-between">
          <span className="text-tertiary">قیمت پایه پلن ({cycle === "yearly" ? "سالانه" : "ماهانه"}):</span>
          <span className="text-secondary">{formatToman(data.base_price_toman)}</span>
        </div>

        {data.extra_seats > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-tertiary">هزینه صندلی‌های اضافه ({formatNumber(data.extra_seats)} صندلی):</span>
            <span className="text-secondary">{formatToman(data.extra_seats_total_toman)}</span>
          </div>
        )}

        <div className="mt-2 flex items-center justify-between border-t border-subtle pt-3">
          <span className="text-body-xs-medium text-secondary">مبلغ کل قابل پرداخت:</span>
          <span className="text-body-md-medium text-accent-primary">{formatToman(data.total_toman)}</span>
        </div>
      </div>
    </div>
  );
}

/** Feature comparison table */
function FeatureComparisonSection({ plans }: { plans: TPublicPlan[] }) {
  const [isOpen, setIsOpen] = useState(true);

  const capabilities = [
    { title: "مدیریت تسک‌ها و پروژه‌ها", key: "projects", standard: "نامحدود" },
    { title: "قفل و وابستگی تسک‌ها (Task Blocking)", key: "task_blocking", standard: "شامل پلن‌های غیر رایگان" },
    { title: "اسناد و مستندات پروژه (Pages)", key: "pages", standard: "کامل" },
    { title: "دستیار هوش مصنوعی (AI Assistant)", key: "ai_features", standard: "پلن‌های ویژه" },
    { title: "اسپرینت‌ها و دوره‌ها (Cycles)", key: "cycles", standard: "کامل" },
    { title: "ماژول‌ها و زیرپروژه‌ها (Modules)", key: "modules", standard: "کامل" },
    { title: "گزارش‌ها و تحلیل آماری (Analytics)", key: "analytics", standard: "گزارش‌های پیشرفته" },
    { title: "نماهای سفارشی (Custom Views)", key: "views", standard: "کامل" },
    { title: "سیستم تخمین کارها (Estimates)", key: "estimates", standard: "Story Points" },
    { title: "صندوق ورودی و تریژ (Intake / Triage)", key: "intake", standard: "کامل" },
    { title: "وب‌هوک‌ها و ادغام‌ها (Webhooks)", key: "webhooks", standard: "پشتیبانی کامل" },
  ];

  return (
    <div className="flex flex-col rounded-lg border border-subtle bg-layer-2 p-6">
      <button type="button" onClick={() => setIsOpen(!isOpen)} className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-h5-medium text-primary">جدول مقایسه جامع قابلیت‌های پلن‌ها</h3>
          <span className="rounded-full bg-layer-1 px-2.5 py-0.5 text-caption-md-regular text-tertiary">
            {plans.length} پلن فعال
          </span>
        </div>
        {isOpen ? <ChevronUp className="size-5 text-tertiary" /> : <ChevronDown className="size-5 text-tertiary" />}
      </button>

      {isOpen && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-start text-caption-md-regular">
            <thead>
              <tr className="border-b border-subtle">
                <th className="py-3 pe-4 text-start text-caption-md-medium text-tertiary">ویژگی و قابلیت</th>
                {plans.map((p) => (
                  <th key={p.code} className="px-4 py-3 text-center text-caption-md-medium text-secondary">
                    {p.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-subtle">
              {capabilities.map((cap) => (
                <tr key={cap.key} className="transition-colors hover:bg-layer-1">
                  <td className="py-3.5 pe-4 text-body-xs-medium text-secondary">{cap.title}</td>
                  {plans.map((p) => {
                    const isFree = p.access_level === "free" || p.access_level === "0";
                    const isAvailable = !isFree || cap.key === "projects" || cap.key === "pages";
                    return (
                      <td key={p.code} className="px-4 py-3.5 text-center">
                        {isAvailable ? (
                          <Check className="mx-auto size-4 text-success-primary" />
                        ) : (
                          <span className="text-placeholder">—</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/** FAQ accordion */
function BillingFAQSection() {
  const faqs = [
    {
      q: "تعداد صندلی‌ها در هر پلن چگونه محاسبه می‌شود؟",
      a: "هر کاربر فعال یا دعوتنامه ارسال‌شده معلق در ورک‌اسپیس به عنوان یک صندلی در نظر گرفته می‌شود. با ارتقای تعداد صندلی‌ها در هر زمان، اعضای جدید می‌توانند بدون محدودیت به تیم اضافه شوند.",
    },
    {
      q: "آیا امکان تغییر پلن یا خرید صندلی بیشتر در میانه دوره وجود دارد؟",
      a: "بله، سیستم به صورت هوشمند مابه‌التفاوت روزهای باقیمانده از اشتراک فعلی شما را کسر می‌کند تا فقط مبلغ اضافی را برای روزهای باقیمانده پرداخت نمایید.",
    },
    {
      q: "پرداخت از طریق چه درگاه‌هایی انجام می‌شود؟",
      a: "پرداخت‌ها از طریق درگاه‌های شاپرکی معتبر (زرین‌پال، پی‌پینگ، زیبال یا دیجی‌پی) با تمام کارت‌های عضو شتاب امکان‌پذیر است.",
    },
    {
      q: "پس از پایان دوره اشتراک، چه بر سر اطلاعات تیم می‌آید؟",
      a: "اطلاعات پروژه‌ها، اسناد و تسک‌های شما همیشه محفوظ می‌ماند؛ در پایان اشتراک فقط قابلیت‌های خاص پلن قفل شده و امکان مشاهده داده‌ها پابرجا خواهد بود.",
    },
  ];

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-subtle bg-layer-2 p-6">
      <div className="flex items-center gap-2">
        <HelpCircle className="size-5 text-tertiary" />
        <h3 className="text-h5-medium text-primary">سوالات متداول</h3>
      </div>

      <div className="divide-y divide-subtle">
        {faqs.map((faq) => (
          <FAQItem key={faq.q} question={faq.q} answer={faq.a} />
        ))}
      </div>
    </div>
  );
}

function FAQItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  const contentId = useId();

  return (
    <div className="py-3.5">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between text-start text-body-xs-medium text-secondary transition-colors hover:text-primary"
      >
        <span>{question}</span>
        {open ? (
          <ChevronUp className="size-4 shrink-0 text-tertiary" />
        ) : (
          <ChevronDown className="size-4 shrink-0 text-tertiary" />
        )}
      </button>
      {open && (
        <p id={contentId} className="mt-2 text-caption-md-regular leading-relaxed text-tertiary">
          {answer}
        </p>
      )}
    </div>
  );
}
