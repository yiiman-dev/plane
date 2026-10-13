/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";
import { BillingService, BILLING_PLANS, BILLING_FEATURE_FLAGS } from "@plane/services";
import type { TBillingPlan, TBillingPlanPayload, TFeatureFlag, TPlanFeatureFlag } from "@plane/types";
import {
  AlertDialog,
  AlertDialogActions,
  AlertDialogBody,
  AlertDialogClose,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogHeader,
  AlertDialogIcon,
  AlertDialogIntro,
  AlertDialogTitle,
} from "@makeplane/propel/components/alert-dialog";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogHeading,
  DialogHeader,
  DialogMain,
  DialogTitle,
} from "@makeplane/propel/components/dialog";
import { Icon } from "@makeplane/propel/components/icon";
import { Input } from "@makeplane/propel/components/input";
import { Switch } from "@makeplane/propel/components/switch";
import { TextArea, TextAreaGroup } from "@makeplane/propel/components/text-area";
import { AddOutline } from "@makeplane/propel/icons";
import { setToast } from "@plane/blocks/toast";

import { BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
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

type TFeatureFlagGrant = {
  feature_flag_code: string;
  is_enabled: boolean;
  limit_value?: number | null;
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

const TEXT_FIELDS: ReadonlyArray<{
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

/**
 * The create and edit forms are the exact same field set, so both dialogs render this component and
 * only differ in whether the plan code stays editable.
 */
function PlanFormFields({
  form,
  idPrefix,
  onChange,
}: {
  form: TPlanForm;
  idPrefix: string;
  onChange: (next: TPlanForm) => void;
}) {
  const fieldId = (key: string) => `${idPrefix}-plan-${key}`;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {TEXT_FIELDS.map((field) => (
        <div key={field.key} className="flex flex-col gap-1">
          <label className="text-13 text-tertiary" htmlFor={fieldId(field.key)}>
            {field.label}
          </label>
          <Input
            id={fieldId(field.key)}
            name={field.key}
            size="lg"
            type={field.type}
            placeholder={field.placeholder}
            value={form[field.key]}
            onChange={(event) => onChange({ ...form, [field.key]: event.target.value })}
          />
        </div>
      ))}

      <div className="flex flex-col gap-1 sm:col-span-2">
        <label className="text-13 text-tertiary" htmlFor={fieldId("description")}>
          توضیح
        </label>
        <TextAreaGroup resize="none">
          <TextArea
            id={fieldId("description")}
            name="description"
            size="lg"
            surface="field"
            autoResize
            maxRows={4}
            placeholder="توضیح کوتاه برای کاربر"
            value={form.description}
            onChange={(event) => onChange({ ...form, description: event.target.value })}
          />
        </TextAreaGroup>
      </div>

      <div className="flex flex-col gap-1 sm:col-span-2">
        <label className="text-13 text-tertiary" htmlFor={fieldId("features")}>
          قابلیت‌ها (هر قابلیت را با ویرگول یا خط جدید جدا کنید)
        </label>
        <TextAreaGroup resize="none">
          <TextArea
            id={fieldId("features")}
            name="features"
            size="lg"
            surface="field"
            autoResize
            maxRows={5}
            placeholder="گزارش پیشرفته، دسترسی API"
            value={form.features}
            onChange={(event) => onChange({ ...form, features: event.target.value })}
          />
        </TextAreaGroup>
      </div>

      <div className="flex items-center gap-2 text-13 text-secondary sm:col-span-2">
        <Switch
          id={fieldId("is-active")}
          size="sm"
          checked={form.is_active}
          onCheckedChange={(checked: boolean) => onChange({ ...form, is_active: checked })}
          aria-label="فعال بودن پلن"
        />
        <label className="cursor-pointer" htmlFor={fieldId("is-active")}>
          پلن فعال باشد
        </label>
      </div>
    </div>
  );
}

function FeatureFlagsSection({
  flags,
  grants,
  onUpdateGrant,
  isPending,
}: {
  flags: TFeatureFlag[];
  grants: TFeatureFlagGrant[];
  onUpdateGrant: (flag: TFeatureFlag, grant: Partial<TFeatureFlagGrant>) => void;
  isPending: boolean;
}) {
  // Group by category preserving backend order
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

  const grantMap = useMemo(() => new Map(grants.map((g) => [g.feature_flag_code, g])), [grants]);

  return (
    <BillingSection title="پرچم‌های قابلیت">
      <div className="rounded-custom mb-4 border border-warning-subtle bg-warning-subtle px-4 py-3 text-13 text-warning-primary">
        تغییر پرچم‌ها روی اشتراک‌های فعال بلافاصله اعمال می‌شود.
      </div>
      {Array.from(categories.entries()).map(([category, categoryFlags]) => (
        <div key={category} className="mb-4">
          <h3 className="mb-2 text-12 text-tertiary">{category}</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {categoryFlags.map((flag) => {
              const grant = grantMap.get(flag.code);
              const isDisabled = !flag.is_active;

              return (
                <div
                  key={flag.id}
                  className={`rounded-custom flex flex-col gap-1.5 border border-subtle p-3 ${isDisabled ? "opacity-50" : ""}`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                      <span className="truncate text-13 text-primary">{flag.name}</span>
                      <span className="font-mono text-11 text-tertiary">{flag.code}</span>
                    </div>
                    <Badge
                      size="xs"
                      variant="info"
                      label={
                        flag.limit_type === "boolean" ? "روشن/خاموش" : flag.limit_type === "number" ? "عددی" : "نامحدود"
                      }
                    />
                  </div>

                  {isDisabled ? (
                    <span className="text-12 text-tertiary">این پرچم غیرفعال است و قابل تغییر نیست.</span>
                  ) : flag.limit_type === "boolean" ? (
                    <Switch
                      size="sm"
                      checked={grant?.is_enabled ?? false}
                      onCheckedChange={(checked) => onUpdateGrant(flag, { is_enabled: checked })}
                      disabled={isPending}
                      aria-label={flag.name}
                    />
                  ) : flag.limit_type === "number" ? (
                    <div className="flex items-center gap-2">
                      <Input
                        type="number"
                        min={0}
                        size="lg"
                        value={
                          grant?.limit_value !== null && grant?.limit_value !== undefined
                            ? grant.limit_value.toString()
                            : ""
                        }
                        onChange={(event) => {
                          const value = event.target.value;
                          if (value === "") {
                            onUpdateGrant(flag, { limit_value: null });
                          } else {
                            const num = Number(value);
                            if (!Number.isNaN(num)) {
                              onUpdateGrant(flag, { limit_value: num });
                            }
                          }
                        }}
                        disabled={isPending}
                        placeholder="مقدار محدودیت"
                        aria-label={`${flag.name} - مقدار محدودیت`}
                      />
                      {flag.unit_label && <span className="text-13 text-tertiary">{flag.unit_label}</span>}
                      {(grant?.limit_value === null || grant?.limit_value === undefined) && (
                        <span className="text-12 text-danger-primary">برای پرچم عددی، مقدار محدودیت الزامی است.</span>
                      )}
                    </div>
                  ) : flag.limit_type === "unlimited" ? (
                    <span className="text-13 text-tertiary">نامحدود</span>
                  ) : null}
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </BillingSection>
  );
}

function PlanStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <dt className="text-12 text-tertiary">{label}</dt>
      <dd className="text-body-sm-semibold break-words text-primary">{value}</dd>
    </div>
  );
}

function PlanCard({
  plan,
  isPending,
  onDelete,
  onEdit,
  onToggleActive,
}: {
  plan: TBillingPlan;
  isPending: boolean;
  onDelete: (plan: TBillingPlan) => void;
  onEdit: (plan: TBillingPlan) => void;
  onToggleActive: (plan: TBillingPlan) => void;
}) {
  // De-duplicated so each chip keeps a stable, data-derived key even when a feature was entered twice.
  const features = Array.from(new Set(plan.features ?? []));

  return (
    <article className="flex h-full flex-col gap-3 rounded-lg border border-subtle bg-layer-1 p-4 transition-colors hover:bg-layer-1-hover">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <h2 className="text-h5-semibold text-primary">{plan.name}</h2>
          <Badge
            size="xs"
            variant={plan.is_active ? "success" : "neutral"}
            label={plan.is_active ? "فعال" : "غیرفعال"}
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge size="xs" variant="neutral" label={`سطح دسترسی: ${plan.access_level || "—"}`} />
          <Badge size="xs" variant="neutral" label={plan.currency} />
        </div>
        {plan.description && <p className="text-body-sm-regular text-secondary">{plan.description}</p>}
      </div>

      <dl className="grid grid-cols-2 gap-3 rounded-md bg-layer-2 p-3">
        <PlanStat label="قیمت ماهانه" value={formatToman(plan.monthly_price_toman)} />
        <PlanStat label="قیمت سالانه" value={formatToman(plan.yearly_price_toman)} />
        <PlanStat label="قیمت هر صندلی" value={formatToman(plan.per_seat_price_toman)} />
        <PlanStat label="بازه صندلی" value={`${formatNumber(plan.min_seats)} تا ${formatNumber(plan.max_seats)}`} />
        <div className="col-span-2 flex flex-col gap-0.5 border-t border-subtle pt-2">
          <dt className="text-12 text-tertiary">صندلی شامل‌شده</dt>
          <dd className="text-body-sm-semibold text-primary">{formatNumber(plan.included_seats)}</dd>
        </div>
      </dl>

      {features.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <h3 className="text-12 text-tertiary">قابلیت‌ها</h3>
          <ul className="flex flex-wrap gap-1.5">
            {features.map((feature) => (
              <li key={feature} className="rounded-full bg-layer-2 px-2 py-1 text-12 text-secondary">
                {feature}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-auto grid grid-cols-3 gap-2">
        <Button variant="primary" size="sm" stretch="full" label="ویرایش" onClick={() => onEdit(plan)} />
        <Button
          variant="secondary"
          size="sm"
          stretch="full"
          label={plan.is_active ? "غیرفعال" : "فعال"}
          loading={isPending}
          onClick={() => onToggleActive(plan)}
        />
        <Button variant="danger-outline" size="sm" stretch="full" label="حذف" onClick={() => onDelete(plan)} />
      </div>
    </article>
  );
}

function PlansSummary({ activeCount, total }: { activeCount: number; total: number }) {
  const stats = [
    { label: "کل پلن‌ها", value: formatNumber(total) },
    { label: "پلن‌های فعال", value: formatNumber(activeCount) },
    { label: "پلن‌های غیرفعال", value: formatNumber(Math.max(total - activeCount, 0)) },
  ];

  return (
    <section
      aria-label="خلاصه پلن‌ها"
      aria-live="polite"
      role="status"
      className="grid grid-cols-1 gap-3 rounded-lg border border-subtle bg-layer-1 p-4 sm:grid-cols-3"
    >
      {stats.map((stat) => (
        <div key={stat.label} className="flex flex-col gap-0.5">
          <span className="text-12 text-tertiary">{stat.label}</span>
          <span className="text-h5-semibold text-primary">{stat.value}</span>
        </div>
      ))}
    </section>
  );
}

function PlansPlaceholder({ label }: { label: string }) {
  return (
    <>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3" aria-hidden="true">
        {[0, 1, 2].map((index) => (
          <div key={index} className="h-56 animate-pulse rounded-lg border border-subtle bg-layer-1" />
        ))}
      </div>
      <p className="sr-only" role="status">
        {label}
      </p>
    </>
  );
}

export default function BillingPlansPage() {
  const { data, error, isLoading, mutate } = useSWR(BILLING_PLANS, () => BillingService.plans({}));
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<TPlanForm>(emptyForm);
  const [editPlan, setEditPlan] = useState<TBillingPlan | null>(null);
  const [editForm, setEditForm] = useState<TPlanForm>(emptyForm);
  const [_editGrants, setEditGrants] = useState<TFeatureFlagGrant[]>([]);
  const [deletePlan, setDeletePlan] = useState<TBillingPlan | null>(null);
  const [isPending, setIsPending] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Fetch feature flags catalogue
  const { data: flagsData } = useSWR(BILLING_FEATURE_FLAGS({}), () => BillingService.featureFlags({}));
  const allFlags = useMemo<TFeatureFlag[]>(() => flagsData?.results ?? [], [flagsData]);

  // Fetch grants for the plan being edited
  const grantsKey = editPlan ? `billing-plan-grants-${editPlan.id}` : null;
  const { data: grantsData } = useSWR(grantsKey, () =>
    BillingService.get(`/api/billing/admin/plans/${editPlan!.id}/feature-flags/`).then((r) => r.data)
  );

  const plans = useMemo<TBillingPlan[]>(() => data?.results ?? [], [data]);
  const activeCount = useMemo(() => plans.filter((plan) => plan.is_active).length, [plans]);

  const grants = useMemo<TFeatureFlagGrant[]>(() => {
    if (!grantsData) return [];
    return (
      grantsData.results?.map((g: TPlanFeatureFlag) => ({
        feature_flag_code: g.feature_flag_code,
        is_enabled: g.is_enabled,
        limit_value: g.limit_value,
      })) ?? []
    );
  }, [grantsData]);

  // Sync editGrants with grants from server when they load
  useMemo(() => {
    if (grants.length > 0) {
      setEditGrants(grants);
    } else if (!editPlan) {
      setEditGrants([]);
    }
  }, [grants, editPlan]);

  const updateGrant = useCallback((flag: TFeatureFlag, patch: Partial<TFeatureFlagGrant>) => {
    setEditGrants((prev) => {
      const existingIndex = prev.findIndex((g) => g.feature_flag_code === flag.code);
      const merged = { ...prev[existingIndex], ...patch, feature_flag_code: flag.code };
      // Never send limit_value for boolean or unlimited
      if (flag.limit_type === "boolean" || flag.limit_type === "unlimited") {
        const { limit_value, ...rest } = merged;
        return existingIndex >= 0
          ? [...prev.slice(0, existingIndex), rest, ...prev.slice(existingIndex + 1)]
          : [...prev, rest];
      }
      if (existingIndex >= 0) {
        const next = [...prev];
        next[existingIndex] = merged;
        return next;
      }
      return [...prev, merged];
    });
  }, []);

  const createValid = useMemo(
    () => createForm.name.trim().length > 0 && createForm.code.trim().length > 0 && createForm.is_active !== null,
    [createForm]
  );

  const closeCreateDialog = useCallback(() => {
    setIsCreateOpen(false);
    setCreateForm(emptyForm());
  }, []);

  const handleCreate = useCallback(async () => {
    try {
      await BillingService.createPlan(toPayload(createForm));
      setToast({ type: "success", title: "ایجاد شد", message: `پلن ${createForm.name} ساخته شد.` });
      closeCreateDialog();
      mutate();
    } catch (err) {
      setToast({
        type: "error",
        title: "ایجاد نشد",
        message: getErrorMessage(err, "ایجاد پلن ناموفق بود."),
      });
    }
  }, [closeCreateDialog, createForm, mutate]);

  const handleUpdate = useCallback(async () => {
    if (!editPlan) return;
    setIsPending(true);
    // The code is immutable after creation, so it is always taken from the stored plan.
    try {
      await BillingService.updatePlan(editPlan.id, { ...toPayload(editForm), code: editPlan.code });
      // Also update feature flag grants
      if (grants.length > 0) {
        await BillingService.patch(`/api/billing/admin/plans/${editPlan.id}/feature-flags/`, {
          grants: grants.map((g) => ({
            feature_flag_code: g.feature_flag_code,
            is_enabled: g.is_enabled,
            limit_value: g.limit_value,
          })),
        });
      }
      setToast({ type: "success", title: "ذخیره شد", message: `پلن ${editPlan.name} ذخیره شد.` });
      setEditPlan(null);
      mutate();
    } catch (err) {
      setToast({
        type: "error",
        title: "ذخیره نشد",
        message: getErrorMessage(err, "ذخیره پلن ناموفق بود."),
      });
    } finally {
      setIsPending(false);
    }
  }, [editForm, editPlan, grants, mutate]);

  const handleDelete = useCallback(async () => {
    if (!deletePlan) return;
    setIsDeleting(true);
    try {
      await BillingService.deletePlan(deletePlan.id);
      setToast({ type: "success", title: "حذف شد", message: `پلن ${deletePlan.name} حذف شد.` });
      setDeletePlan(null);
      mutate();
    } catch (err) {
      setToast({
        type: "error",
        title: "حذف نشد",
        message: getErrorMessage(err, "حذف پلن ناموفق بود."),
      });
    } finally {
      setIsDeleting(false);
    }
  }, [deletePlan, mutate]);

  const handleToggleActive = useCallback(
    async (plan: TBillingPlan) => {
      setIsPending(true);
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
        setIsPending(false);
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
          icon={<Icon icon={AddOutline} />}
          onClick={() => setIsCreateOpen(true)}
        />
      }
    >
      <BillingNav />

      {isLoading && <PlansPlaceholder label="در حال بارگذاری پلن‌ها…" />}

      {!isLoading && error && (
        <div
          role="alert"
          className="rounded-lg border border-subtle bg-layer-1 p-4 text-body-sm-regular text-secondary"
        >
          {getErrorMessage(error, "بارگذاری پلن‌ها ناموفق بود.")}
        </div>
      )}

      {!isLoading && !error && plans.length === 0 && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-subtle px-4 py-10 text-center">
          <h2 className="text-body-sm-semibold text-primary">هنوز پلنی ساخته نشده است</h2>
          <p className="max-w-md text-body-sm-regular text-tertiary">
            برای نمایش پلن‌ها در اپ وب و محاسبه پرداخت per-seat، حداقل یک پلن بسازید. کد پلن پس از ایجاد قابل تغییر نیست.
          </p>
          <Button
            variant="primary"
            size="md"
            stretch="auto"
            label="ساخت اولین پلن"
            icon={<Icon icon={AddOutline} />}
            onClick={() => setIsCreateOpen(true)}
          />
        </div>
      )}

      {!isLoading && !error && plans.length > 0 && (
        <>
          <PlansSummary activeCount={activeCount} total={plans.length} />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {plans.map((plan) => (
              <PlanCard
                key={plan.id}
                plan={plan}
                isPending={isPending}
                onDelete={setDeletePlan}
                onEdit={(target) => {
                  setEditPlan(target);
                  setEditForm(toForm(target));
                }}
                onToggleActive={handleToggleActive}
              />
            ))}
          </div>
        </>
      )}

      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent size="lg">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>پلن جدید</DialogTitle>
                <DialogDescription>
                  کد پلن پس از ایجاد قابل تغییر نیست؛ آن را کوتاه و یکتا انتخاب کنید.
                </DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody tabIndex={0}>
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-1">
                  <label className="text-13 text-tertiary" htmlFor="create-plan-code">
                    کد پلن
                  </label>
                  <Input
                    id="create-plan-code"
                    name="code"
                    size="lg"
                    placeholder="pro-monthly"
                    value={createForm.code}
                    onChange={(event) => setCreateForm((prev) => ({ ...prev, code: event.target.value }))}
                  />
                </div>
                <PlanFormFields form={createForm} idPrefix="create" onChange={setCreateForm} />
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button
              variant="primary"
              size="sm"
              stretch="auto"
              label="ایجاد پلن"
              disabled={!createValid}
              onClick={handleCreate}
            />
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              label="انصراف"
              render={<DialogClose />}
              onClick={closeCreateDialog}
            />
          </DialogActions>
        </DialogContent>
      </Dialog>

      <Dialog
        open={editPlan !== null}
        onOpenChange={(open) => {
          if (!open) setEditPlan(null);
        }}
      >
        <DialogContent size="lg">
          <DialogMain>
            <DialogHeader>
              <DialogHeading>
                <DialogTitle>ویرایش پلن</DialogTitle>
                <DialogDescription>تغییرات پس از ذخیره بلافاصله در اپ وب اعمال می‌شود.</DialogDescription>
              </DialogHeading>
            </DialogHeader>
            <DialogBody tabIndex={0}>
              <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-1">
                  <label className="text-13 text-tertiary" htmlFor="edit-plan-code">
                    کد پلن
                  </label>
                  <Input id="edit-plan-code" size="lg" value={editPlan?.code ?? ""} readOnly disabled />
                  <span className="text-12 text-tertiary">کد پلن پس از ایجاد قابل تغییر نیست.</span>
                </div>
                <PlanFormFields form={editForm} idPrefix="edit" onChange={setEditForm} />
                {editPlan && (
                  <FeatureFlagsSection
                    flags={allFlags}
                    grants={grants}
                    onUpdateGrant={updateGrant}
                    isPending={isPending}
                  />
                )}
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button
              variant="primary"
              size="sm"
              stretch="auto"
              label="ذخیره"
              loading={isPending}
              onClick={handleUpdate}
            />
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              label="انصراف"
              render={<DialogClose />}
              onClick={() => setEditPlan(null)}
            />
          </DialogActions>
        </DialogContent>
      </Dialog>

      <AlertDialog
        open={deletePlan !== null}
        onOpenChange={(open) => {
          if (!open) setDeletePlan(null);
        }}
      >
        <AlertDialogContent data-prevent-outside-click>
          <AlertDialogBody>
            <AlertDialogHeader>
              <AlertDialogIcon variant="danger" />
              <AlertDialogIntro>
                <AlertDialogTitle>حذف پلن</AlertDialogTitle>
                <AlertDialogDescription>
                  پلن «{deletePlan?.name}» برای همیشه حذف می‌شود. اگر در فاکتور یا اشتراکی در حال استفاده باشد، حذف رد
                  می‌شود و در آن حالت باید پلن را غیرفعال کنید.
                </AlertDialogDescription>
              </AlertDialogIntro>
            </AlertDialogHeader>
          </AlertDialogBody>
          <AlertDialogActions>
            <Button
              variant="secondary"
              size="sm"
              stretch="auto"
              label="انصراف"
              disabled={isDeleting}
              render={<AlertDialogClose />}
              onClick={() => setDeletePlan(null)}
            />
            <Button
              variant="danger"
              size="sm"
              stretch="auto"
              label="حذف پلن"
              loading={isDeleting}
              onClick={handleDelete}
            />
          </AlertDialogActions>
        </AlertDialogContent>
      </AlertDialog>
    </BillingRTLFrame>
  );
}
