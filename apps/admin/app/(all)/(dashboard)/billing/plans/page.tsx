/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { BillingService, BILLING_PLANS } from "@plane/services";
import type { TBillingPlan, TBillingPlanPayload } from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import { setToast } from "@plane/blocks/toast";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
import { formatNumber, formatToman, getErrorMessage, toSafeNumber } from "../utils";

type TPlanForm = {
  access_level: string;
  code: string;
  description: string;
  features: string;
  included_seats: string;
  is_active: boolean;
  max_seats: string;
  min_seats: string;
  monthly_price_toman: string;
  name: string;
  per_seat_price_toman: string;
  sort_order: string;
  yearly_price_toman: string;
};

const emptyForm = (): TPlanForm => ({
  access_level: "",
  code: "",
  description: "",
  features: "",
  included_seats: "1",
  is_active: true,
  max_seats: "100",
  min_seats: "1",
  monthly_price_toman: "0",
  name: "",
  per_seat_price_toman: "0",
  sort_order: "0",
  yearly_price_toman: "0",
});

const toForm = (plan?: TBillingPlan): TPlanForm =>
  plan
    ? {
        access_level: plan.access_level ?? "",
        code: plan.code,
        description: plan.description ?? "",
        features: (plan.features ?? []).join("، "),
        included_seats: plan.included_seats.toString(),
        is_active: plan.is_active,
        max_seats: plan.max_seats.toString(),
        min_seats: plan.min_seats.toString(),
        monthly_price_toman: plan.monthly_price_toman.toString(),
        name: plan.name,
        per_seat_price_toman: plan.per_seat_price_toman.toString(),
        sort_order: plan.sort_order.toString(),
        yearly_price_toman: plan.yearly_price_toman.toString(),
      }
    : emptyForm();

const toPayload = (form: TPlanForm): TBillingPlanPayload => ({
  access_level: form.access_level.trim(),
  code: form.code.trim(),
  currency: "IRT",
  description: form.description.trim(),
  features: form.features
    .split(/[،,\n]/)
    .map((feature) => feature.trim())
    .filter(Boolean),
  included_seats: toSafeNumber(form.included_seats),
  is_active: form.is_active,
  max_seats: toSafeNumber(form.max_seats),
  min_seats: toSafeNumber(form.min_seats),
  monthly_price_toman: toSafeNumber(form.monthly_price_toman),
  name: form.name.trim(),
  per_seat_price_toman: toSafeNumber(form.per_seat_price_toman),
  sort_order: toSafeNumber(form.sort_order),
  yearly_price_toman: toSafeNumber(form.yearly_price_toman),
});

function PlanFormFields({ form, onChange }: { form: TPlanForm; onChange: (next: TPlanForm) => void }) {
  const textFields: ReadonlyArray<{
    key: keyof Omit<TPlanForm, "is_active">;
    label: string;
    placeholder: string;
    type?: "number";
  }> = [
    { key: "name", label: "نام پلن", placeholder: "پلن حرفه‌ای" },
    { key: "access_level", label: "سطح دسترسی", placeholder: "pro" },
    { key: "monthly_price_toman", label: "قیمت ماهانه (تومان)", placeholder: "0", type: "number" },
    { key: "yearly_price_toman", label: "قیمت سالانه (تومان)", placeholder: "0", type: "number" },
    { key: "per_seat_price_toman", label: "قیمت هر صندلی (تومان)", placeholder: "0", type: "number" },
    { key: "included_seats", label: "صندلی شامل‌شده", placeholder: "1", type: "number" },
    { key: "min_seats", label: "حداقل صندلی", placeholder: "1", type: "number" },
    { key: "max_seats", label: "حداکثر صندلی", placeholder: "100", type: "number" },
    { key: "sort_order", label: "ترتیب نمایش", placeholder: "0", type: "number" },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {textFields.map((field) => (
        <div key={field.key} className="flex flex-col gap-1">
          <label className="text-13 text-tertiary" htmlFor={`plan-${field.key}`}>
            {field.label}
          </label>
          <Input
            id={`plan-${field.key}`}
            size="lg"
            type={field.type}
            placeholder={field.placeholder}
            value={form[field.key]}
            onChange={(event) => onChange({ ...form, [field.key]: event.target.value })}
          />
        </div>
      ))}
      <div className="flex flex-col gap-1 md:col-span-2">
        <label className="text-13 text-tertiary" htmlFor="plan-description">
          توضیح
        </label>
        <Input
          id="plan-description"
          size="lg"
          placeholder="توضیح کوتاه برای کاربر"
          value={form.description}
          onChange={(event) => onChange({ ...form, description: event.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1 md:col-span-2">
        <label className="text-13 text-tertiary" htmlFor="plan-features">
          قابلیت‌ها (هر قابلیت را با ویرگول جدا کنید)
        </label>
        <Input
          id="plan-features"
          size="lg"
          placeholder="گزارش پیشرفته، دسترسی API"
          value={form.features}
          onChange={(event) => onChange({ ...form, features: event.target.value })}
        />
      </div>
      <div className="flex items-center gap-2 text-13 text-secondary md:col-span-2">
        پلن فعال باشد
        <Switch
          size="sm"
          checked={form.is_active}
          onCheckedChange={(checked: boolean) => onChange({ ...form, is_active: checked })}
          aria-label="فعال بودن پلن"
        />
      </div>
    </div>
  );
}

export default function BillingPlansPage() {
  const { data, error, isLoading, mutate } = useSWR(BILLING_PLANS, () => BillingService.plans({}));
  const [isCreating, setIsCreating] = useState(false);
  const [createForm, setCreateForm] = useState<TPlanForm>(emptyForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<TPlanForm>(emptyForm);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const plans = useMemo<TBillingPlan[]>(() => data?.results ?? [], [data]);

  const createValid = useMemo(
    () => createForm.name.trim().length > 0 && createForm.code.trim().length > 0 && createForm.is_active !== null,
    [createForm]
  );

  const handleCreate = useCallback(async () => {
    try {
      await BillingService.createPlan(toPayload(createForm));
      setToast({ type: "success", title: "ایجاد شد", message: `پلن ${createForm.name} ساخته شد.` });
      setCreateForm(emptyForm());
      setIsCreating(false);
      mutate();
    } catch (err) {
      setToast({
        type: "error",
        title: "ایجاد نشد",
        message: getErrorMessage(err, "ایجاد پلن ناموفق بود."),
      });
    }
  }, [createForm, mutate]);

  const handleUpdate = useCallback(
    async (plan: TBillingPlan) => {
      setPendingId(plan.id);
      // The code is immutable after creation, so it is always taken from the stored plan.
      try {
        await BillingService.updatePlan(plan.id, { ...toPayload(editForm), code: plan.code });
        setToast({ type: "success", title: "ذخیره شد", message: `پلن ${plan.name} ذخیره شد.` });
        setEditingId(null);
        mutate();
      } catch (err) {
        setToast({
          type: "error",
          title: "ذخیره نشد",
          message: getErrorMessage(err, "ذخیره پلن ناموفق بود."),
        });
      } finally {
        setPendingId(null);
      }
    },
    [editForm, mutate]
  );

  const handleDelete = useCallback(
    async (plan: TBillingPlan) => {
      setPendingId(plan.id);
      try {
        await BillingService.deletePlan(plan.id);
        setToast({ type: "success", title: "حذف شد", message: `پلن ${plan.name} حذف شد.` });
        mutate();
      } catch (err) {
        setToast({
          type: "error",
          title: "حذف نشد",
          message: getErrorMessage(err, "حذف پلن ناموفق بود."),
        });
      } finally {
        setPendingId(null);
      }
    },
    [mutate]
  );

  const handleToggleActive = useCallback(
    async (plan: TBillingPlan) => {
      setPendingId(plan.id);
      try {
        await BillingService.updatePlan(plan.id, { ...toPayload(toForm(plan)), is_active: !plan.is_active });
        mutate();
      } catch (err) {
        setToast({
          type: "error",
          title: "تغییر وضعیت ناموفق",
          message: getErrorMessage(err, "تغییر وضعیت پلن ناموفق بود."),
        });
      } finally {
        setPendingId(null);
      }
    },
    [mutate]
  );

  return (
    <BillingRTLFrame
      title="پلن‌های مالی"
      description="پلن‌هایی که در اپ وب به کاربر نمایش داده می‌شوند و پرداخت per-seat بر اساس آن‌ها محاسبه می‌شود."
      actions={
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          label="افزودن پلن"
          onClick={() => setIsCreating((prev) => !prev)}
        />
      }
    >
      <BillingNav />

      {isLoading && <BillingEmptyState message="در حال بارگذاری پلن‌ها…" />}
      {!isLoading && error && <BillingEmptyState message={getErrorMessage(error, "بارگذاری پلن‌ها ناموفق بود.")} />}
      {!isLoading && !error && plans.length === 0 && <BillingEmptyState message="هنوز پلنی ساخته نشده است." />}

      {isCreating && (
        <BillingSection title="پلن جدید">
          <div className="flex flex-col gap-1">
            <label className="text-13 text-tertiary" htmlFor="plan-code">
              کد پلن
            </label>
            <Input
              id="plan-code"
              size="lg"
              placeholder="pro-monthly"
              value={createForm.code}
              onChange={(event) => setCreateForm((prev) => ({ ...prev, code: event.target.value }))}
            />
          </div>
          <PlanFormFields form={createForm} onChange={setCreateForm} />
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              label="ایجاد پلن"
              disabled={!createValid}
              onClick={handleCreate}
            />
            <Button
              variant="secondary"
              size="md"
              stretch="auto"
              label="انصراف"
              onClick={() => {
                setIsCreating(false);
                setCreateForm(emptyForm());
              }}
            />
          </div>
        </BillingSection>
      )}

      {plans.map((plan) => (
        <BillingSection key={plan.id} title={`${plan.name} (${plan.code})`}>
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              size="xs"
              variant={plan.is_active ? "success" : "neutral"}
              label={plan.is_active ? "فعال" : "غیرفعال"}
            />
            <Badge size="xs" variant="neutral" label={plan.currency} />
            <span className="text-12 text-tertiary">سطح دسترسی: {plan.access_level || "—"}</span>
          </div>

          {editingId !== plan.id ? (
            <>
              <div className="grid grid-cols-2 gap-2 text-12 text-secondary md:grid-cols-4">
                <span>ماهانه: {formatToman(plan.monthly_price_toman)}</span>
                <span>سالانه: {formatToman(plan.yearly_price_toman)}</span>
                <span>هر صندلی: {formatToman(plan.per_seat_price_toman)}</span>
                <span>
                  صندلی: {formatNumber(plan.min_seats)} تا {formatNumber(plan.max_seats)} (شامل{" "}
                  {formatNumber(plan.included_seats)})
                </span>
              </div>
              {plan.features?.length > 0 && (
                <p className="text-12 text-tertiary">قابلیت‌ها: {plan.features.join("، ")}</p>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  stretch="auto"
                  label="ویرایش"
                  onClick={() => {
                    setEditingId(plan.id);
                    setEditForm(toForm(plan));
                  }}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  stretch="auto"
                  label={plan.is_active ? "غیرفعال کردن" : "فعال کردن"}
                  loading={pendingId === plan.id}
                  onClick={() => handleToggleActive(plan)}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  stretch="auto"
                  label="حذف"
                  loading={pendingId === plan.id}
                  onClick={() => handleDelete(plan)}
                />
              </div>
              <p className="text-11 text-tertiary">
                اگر پلن در فاکتور یا اشتراکی در حال استفاده باشد، حذف آن رد می‌شود؛ در آن حالت پلن را غیرفعال کنید.
              </p>
            </>
          ) : (
            <>
              <PlanFormFields form={editForm} onChange={setEditForm} />
              <p className="text-11 text-tertiary">کد پلن پس از ایجاد قابل تغییر نیست: {plan.code}</p>
              <div className="flex items-center gap-2">
                <Button
                  variant="primary"
                  size="sm"
                  stretch="auto"
                  loading={pendingId === plan.id}
                  label="ذخیره"
                  onClick={() => handleUpdate(plan)}
                />
                <Button
                  variant="secondary"
                  size="sm"
                  stretch="auto"
                  label="انصراف"
                  onClick={() => setEditingId(null)}
                />
              </div>
            </>
          )}
        </BillingSection>
      ))}
    </BillingRTLFrame>
  );
}
