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
import type { TBillingCycle, TPublicPlan } from "@plane/types";
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

  const checkoutRef = useRef<HTMLDivElement>(null);

  // Fetch plans
  const { data: plansData, error: plansError, isLoading: plansLoading } = useSWR(
    BILLING_PUBLIC_PLANS,
    () => BillingService.publicPlans()
  );

  // Fetch workspace entitlement if workspaceSlug is present
  const { data: entitlement } = useSWR(
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

  if (plansLoading) {
    return (
      <div className="grid min-h-screen w-full place-items-center py-20">
        <LogoSpinner />
      </div>
    );
  }

  if (plansError) {
    return (
      <div className="mx-auto w-full max-w-4xl p-6">
        <div className="rounded-xl border border-danger-200 bg-danger-50 p-6 text-center text-danger-600">
          <h2 className="text-base font-semibold">خطا در بارگذاری پلن‌ها</h2>
          <p className="mt-2 text-sm">{getErrorMessage(plansError, "امکان دریافت فهرست پلن‌های مالی وجود ندارد.")}</p>
        </div>
      </div>
    );
  }

  const currentPlanCode = entitlement?.plan?.code;

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-col gap-10 px-4 py-8 sm:px-6 lg:px-8">
      {/* Top Navigation & Workspace Header */}
      <div className="flex flex-col gap-4 border-b border-subtle pb-6 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          {workspaceSlug && (
            <Link
              to={`/${workspaceSlug}/settings/billing`}
              className="inline-flex items-center gap-1.5 rounded-lg border border-subtle bg-surface-1 px-3 py-1.5 text-xs font-medium text-content-2 hover:bg-surface-2 hover:text-content-on-surface transition-colors"
            >
              <ArrowRight className="size-4" />
              بازگشت به تنظیمات ورک‌اسپیس
            </Link>
          )}
          {entitlement?.workspace && (
            <div className="flex items-center gap-2 rounded-full border border-subtle bg-surface-1 px-3 py-1 text-xs">
              <span className="text-content-2">ورک‌اسپیس:</span>
              <span className="font-semibold text-content-on-surface">{entitlement.workspace.name}</span>
            </div>
          )}
        </div>

        {entitlement?.plan && (
          <div className="flex items-center gap-2 text-xs">
            <span className="text-content-2">پلن فعلی ورک‌اسپیس:</span>
            <span className="rounded-md border border-primary/20 bg-primary/10 px-2 py-0.5 font-semibold text-primary">
              {entitlement.plan.name}
            </span>
          </div>
        )}
      </div>

      {/* Hero Section */}
      <div className="flex flex-col items-center text-center">
        <div className="inline-flex items-center gap-1.5 rounded-full border border-primary/20 bg-primary/10 px-3.5 py-1 text-xs font-medium text-primary">
          <Sparkles className="size-3.5" />
          پلن‌های منعطف و قیمت‌گذاری شفاف
        </div>
        <h1 className="mt-3 text-3xl font-extrabold tracking-tight text-content-on-surface sm:text-4xl">
          انتخاب پلن مناسب برای تیم شما
        </h1>
        <p className="mt-3 max-w-2xl text-sm sm:text-base text-content-2">
          امکانات حرفه‌ای مدیریت پروژه، وابستگی تسک‌ها، هوش مصنوعی، و ظرفیت صندلی مورد نیاز تیم خود را به سادگی فعال کنید.
        </p>

        {/* Billing Cycle Switcher */}
        <div className="mt-8 flex items-center gap-3 rounded-full border border-subtle bg-surface-1 p-1 shadow-xs">
          <button
            type="button"
            onClick={() => setCycle("monthly")}
            className={`rounded-full px-5 py-2 text-sm font-medium transition-all ${
              cycle === "monthly"
                ? "bg-primary text-white shadow-sm"
                : "text-content-2 hover:text-content-on-surface"
            }`}
          >
            پرداخت ماهانه
          </button>
          <button
            type="button"
            onClick={() => setCycle("yearly")}
            className={`flex items-center gap-1.5 rounded-full px-5 py-2 text-sm font-medium transition-all ${
              cycle === "yearly"
                ? "bg-primary text-white shadow-sm"
                : "text-content-2 hover:text-content-on-surface"
            }`}
          >
            <span>پرداخت سالانه</span>
            <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-10 font-bold text-emerald-600 dark:text-emerald-400">
              ۲۰٪ تخفیف
            </span>
          </button>
        </div>
      </div>

      {/* Plans Grid */}
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {plans.map((plan) => {
          const isSelected = selectedPlanCode === plan.code;
          const isCurrent = currentPlanCode === plan.code;
          const isPopular = plan.access_level === "pro" || plan.access_level === "business";

          const price = cycle === "yearly" ? plan.yearly_price_toman : plan.monthly_price_toman;

          return (
            <div
              key={plan.code}
              onClick={() => handleSelectPlan(plan)}
              className={`relative flex flex-col justify-between rounded-2xl border p-6 transition-all cursor-pointer ${
                isSelected
                  ? "border-primary bg-surface-1 shadow-md ring-2 ring-primary/20"
                  : "border-subtle bg-surface-1 hover:border-primary/50 hover:shadow-sm"
              }`}
            >
              {isPopular && (
                <div className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-primary px-3 py-0.5 text-11 font-bold text-white shadow-xs">
                  پیشنهاد ویژه
                </div>
              )}

              <div>
                {/* Header */}
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-xl font-bold text-content-on-surface">{plan.name}</h3>
                  {isCurrent && (
                    <span className="rounded-md border border-subtle bg-surface-2 px-2 py-0.5 text-xs text-content-2">
                      پلن فعلی شما
                    </span>
                  )}
                </div>

                {plan.description && <p className="mt-2 text-xs text-content-2 min-h-8">{plan.description}</p>}

                {/* Pricing */}
                <div className="mt-5 border-t border-subtle pt-4">
                  <div className="flex items-baseline gap-1">
                    <span className="text-3xl font-extrabold text-content-on-surface">
                      {price === 0 ? "رایگان" : formatNumber(price)}
                    </span>
                    {price > 0 && <span className="text-xs text-content-2">تومان / {cycle === "yearly" ? "سالانه" : "ماهانه"}</span>}
                  </div>

                  <div className="mt-2 text-xs text-content-2">
                    {plan.per_seat_price_toman > 0 ? (
                      <span>{formatToman(plan.per_seat_price_toman)} به ازای هر صندلی اضافه</span>
                    ) : (
                      <span>شامل {formatNumber(plan.included_seats)} صندلی</span>
                    )}
                  </div>
                </div>

                {/* Features List */}
                <div className="mt-6 border-t border-subtle pt-4">
                  <h4 className="text-xs font-semibold text-content-1">امکانات و ویژگی‌ها:</h4>
                  <ul className="mt-3 flex flex-col gap-2.5 text-xs text-content-2">
                    <li className="flex items-center gap-2">
                      <Check className="size-4 shrink-0 text-emerald-500" />
                      <span>
                        شامل <strong>{formatNumber(plan.included_seats)} صندلی</strong> اولیه (حداکثر {formatNumber(plan.max_seats)})
                      </span>
                    </li>
                    {plan.features.map((feature) => (
                      <li key={feature} className="flex items-center gap-2">
                        <Check className="size-4 shrink-0 text-emerald-500" />
                        <span>{feature}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>

              {/* Action Button */}
              <div className="mt-8 pt-4">
                <Button
                  variant={isSelected ? "primary" : "secondary"}
                  size="md"
                  stretch="full"
                  type="button"
                  label={isSelected ? "پلن انتخابی شما ✓" : "انتخاب و ادامه خرید"}
                />
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected Plan Checkout & Quote Section */}
      {selectedPlan && (
        <div
          ref={checkoutRef}
          className="rounded-2xl border border-primary/30 bg-surface-1 p-6 shadow-md transition-all"
        >
          <div className="flex flex-col gap-2 border-b border-subtle pb-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="flex size-6 items-center justify-center rounded-full bg-primary/10 text-primary">
                  <Zap className="size-3.5" />
                </span>
                <h2 className="text-lg font-bold text-content-on-surface">
                  پیکربندی و تسویه‌حساب: پلن {selectedPlan.name}
                </h2>
              </div>
              <p className="mt-1 text-xs text-content-2">
                تعداد صندلی و دوره پرداخت را تعیین کنید؛ مبلغ فاکتور به صورت رسمی و بلادرنگ محاسبه می‌شود.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs text-content-2">دوره پرداخت:</span>
              <span className="rounded-full border border-subtle bg-surface-2 px-3 py-1 text-xs font-medium text-content-on-surface">
                {cycle === "yearly" ? "سالانه (۲۰٪ تخفیف)" : "ماهانه"}
              </span>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-12">
            {/* Controls (Seats & Options) */}
            <div className="flex flex-col gap-5 lg:col-span-6">
              <div className="rounded-xl border border-subtle bg-surface-2 p-4">
                <label htmlFor="seats-input" className="text-sm font-semibold text-content-on-surface">
                  تعداد صندلی‌های مورد نیاز (کاربران تیم)
                </label>
                <p className="mt-1 text-xs text-content-2">
                  شامل {formatNumber(selectedPlan.included_seats)} صندلی پایه. حداقل {formatNumber(minSeats)} و حداکثر {formatNumber(maxSeats)} صندلی مجاز است.
                </p>

                <div className="mt-4 flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => handleSeatChange(-1)}
                    disabled={seatsCount <= minSeats}
                    className="flex size-10 items-center justify-center rounded-lg border border-subtle bg-surface-1 text-content-on-surface hover:bg-surface-3 disabled:opacity-40 transition-colors"
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
                    className="h-10 w-24 rounded-lg border border-subtle bg-surface-1 text-center font-bold text-content-on-surface outline-none focus:border-primary"
                  />
                  <button
                    type="button"
                    onClick={() => handleSeatChange(1)}
                    disabled={seatsCount >= maxSeats}
                    className="flex size-10 items-center justify-center rounded-lg border border-subtle bg-surface-1 text-content-on-surface hover:bg-surface-3 disabled:opacity-40 transition-colors"
                  >
                    <Plus className="size-4" />
                  </button>
                  <span className="text-xs text-content-2">صندلی فعال</span>
                </div>

                {!isSeatsValid && (
                  <p className="mt-2 text-xs text-danger-500 font-medium">
                    تعداد صندلی باید بین {formatNumber(minSeats)} و {formatNumber(maxSeats)} باشد.
                  </p>
                )}
              </div>

              {/* Security & Peace of Mind */}
              <div className="grid grid-cols-2 gap-3 text-xs text-content-2">
                <div className="flex items-center gap-2 rounded-lg border border-subtle bg-surface-1 p-3">
                  <ShieldCheck className="size-4 text-emerald-500 shrink-0" />
                  <span>پرداخت امن از طریق درگاه شاپرک</span>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-subtle bg-surface-1 p-3">
                  <CheckCircle2 className="size-4 text-emerald-500 shrink-0" />
                  <span>فعال‌سازی آنی پس از پرداخت</span>
                </div>
              </div>
            </div>

            {/* Server Quote & Checkout CTA */}
            <div className="flex flex-col justify-between gap-4 rounded-xl border border-subtle bg-surface-2 p-5 lg:col-span-6">
              <OrderQuote plan={selectedPlan} seats={seatsCount} cycle={cycle} />

              {submitError && (
                <div className="rounded-lg border border-danger-200 bg-danger-50 p-3 text-xs text-danger-600">
                  {submitError}
                </div>
              )}

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
            </div>
          </div>
        </div>
      )}

      {/* Feature Comparison Matrix */}
      <FeatureComparisonSection plans={plans} />

      {/* FAQ Section */}
      <BillingFAQSection />
    </div>
  );
}

/** Real-time server quote breakdown */
function OrderQuote({ plan, seats, cycle }: { plan: TPublicPlan; seats: number; cycle: TBillingCycle }) {
  const { data, error, isLoading } = useSWR(
    BILLING_PLAN_QUOTE(plan.code, seats, cycle),
    () => BillingService.planQuote(plan.code, { cycle, seats })
  );

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-6 text-xs text-content-2">
        <LogoSpinner />
        <span className="mt-2">در حال محاسبه فاکتور رسمی...</span>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="text-xs text-danger-500">
        {getErrorMessage(error, "امکان محاسبه فاکتور وجود ندارد. لطفاً صندلی مجاز انتخاب کنید.")}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-content-on-surface">خلاصه فاکتور پرداخت</h3>

      <div className="flex flex-col gap-2 border-t border-subtle pt-3 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-content-2">قیمت پایه پلن ({cycle === "yearly" ? "سالانه" : "ماهانه"}):</span>
          <span className="font-medium text-content-on-surface">{formatToman(data.base_price_toman)}</span>
        </div>

        {data.extra_seats > 0 && (
          <div className="flex items-center justify-between">
            <span className="text-content-2">
              هزینه صندلی‌های اضافه ({formatNumber(data.extra_seats)} صندلی):
            </span>
            <span className="font-medium text-content-on-surface">{formatToman(data.extra_seats_total_toman)}</span>
          </div>
        )}

        <div className="mt-2 flex items-center justify-between border-t border-subtle pt-3 text-sm">
          <span className="font-bold text-content-on-surface">مبلغ کل قابل پرداخت:</span>
          <span className="text-base font-extrabold text-primary">{formatToman(data.total_toman)}</span>
        </div>
      </div>
    </div>
  );
}

/** Feature Comparison Table */
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
    <div className="mt-6 flex flex-col rounded-2xl border border-subtle bg-surface-1 p-6">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between text-right"
      >
        <div className="flex items-center gap-2">
          <h3 className="text-lg font-bold text-content-on-surface">جدول مقایسه جامع قابلیت‌های پلن‌ها</h3>
          <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-xs text-content-2">
            {plans.length} پلن فعال
          </span>
        </div>
        {isOpen ? <ChevronUp className="size-5 text-content-2" /> : <ChevronDown className="size-5 text-content-2" />}
      </button>

      {isOpen && (
        <div className="mt-6 overflow-x-auto">
          <table className="w-full text-right text-xs">
            <thead>
              <tr className="border-b border-subtle">
                <th className="py-3 pr-4 font-semibold text-content-2">ویژگی و قابلیت</th>
                {plans.map((p) => (
                  <th key={p.code} className="py-3 px-4 font-bold text-content-on-surface text-center">
                    {p.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-subtle">
              {capabilities.map((cap) => (
                <tr key={cap.key} className="hover:bg-surface-2 transition-colors">
                  <td className="py-3.5 pr-4 font-medium text-content-on-surface">{cap.title}</td>
                  {plans.map((p) => {
                    const isFree = p.access_level === "free" || p.access_level === "0";
                    const isAvailable = !isFree || cap.key === "projects" || cap.key === "pages";
                    return (
                      <td key={p.code} className="py-3.5 px-4 text-center">
                        {isAvailable ? (
                          <Check className="mx-auto size-4 text-emerald-500" />
                        ) : (
                          <span className="text-content-3">—</span>
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

/** FAQ Accordion */
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
    <div className="flex flex-col gap-4 rounded-2xl border border-subtle bg-surface-1 p-6">
      <div className="flex items-center gap-2">
        <HelpCircle className="size-5 text-primary" />
        <h3 className="text-lg font-bold text-content-on-surface">سوالات متداول</h3>
      </div>

      <div className="mt-2 divide-y divide-subtle">
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
        className="flex w-full items-center justify-between text-right text-sm font-semibold text-content-on-surface hover:text-primary transition-colors"
      >
        <span>{question}</span>
        {open ? <ChevronUp className="size-4 shrink-0 text-content-2" /> : <ChevronDown className="size-4 shrink-0 text-content-2" />}
      </button>
      {open && <p id={contentId} className="mt-2 text-xs leading-relaxed text-content-2">{answer}</p>}
    </div>
  );
}
