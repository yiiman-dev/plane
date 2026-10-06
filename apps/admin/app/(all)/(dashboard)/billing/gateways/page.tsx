/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { BillingService, BILLING_GATEWAYS } from "@plane/services";
import type {
  TPaymentGateway,
  TPaymentGatewayAmountUnit,
  TPaymentGatewayUpdate,
  TPaymentGatewayExtraConfig,
} from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { Select, SelectContent, SelectItem, SelectList, SelectTrigger } from "@makeplane/propel/components/select";
import { Switch } from "@makeplane/propel/components/switch";
import { setToast } from "@plane/blocks/toast";

import { AMOUNT_UNIT_OPTIONS, GATEWAY_CREDENTIAL_FIELDS, GATEWAY_LABELS } from "../constants";
import { BillingEmptyState, BillingNav, BillingRTLFrame } from "../components/billing-layout";
import { getErrorMessage, toSafeNumber } from "../utils";

type TCredentialDraft = Record<string, string>;

type TExtraConfigDraft = {
  amount_unit: TPaymentGatewayAmountUnit;
  base_url: string;
  callback_url: string;
  max_amount_toman: string;
  min_amount_toman: string;
  timeout: string;
};

const emptyExtraConfig = (gateway?: TPaymentGateway): TExtraConfigDraft => ({
  amount_unit: (gateway?.extra_config?.amount_unit as TPaymentGatewayAmountUnit) ?? "rial",
  base_url: gateway?.extra_config?.base_url ?? "",
  callback_url: gateway?.extra_config?.callback_url ?? "",
  max_amount_toman: gateway?.extra_config?.max_amount_toman?.toString() ?? "",
  min_amount_toman: gateway?.extra_config?.min_amount_toman?.toString() ?? "",
  timeout: gateway?.extra_config?.timeout?.toString() ?? "",
});

function GatewayCard({ gateway, onSaved }: { gateway: TPaymentGateway; onSaved: () => void }) {
  const credentialFields = GATEWAY_CREDENTIAL_FIELDS[gateway.code] ?? [];
  const [isEnabled, setIsEnabled] = useState(gateway.is_enabled);
  const [isSandbox, setIsSandbox] = useState(gateway.is_sandbox);
  const [priority, setPriority] = useState(gateway.priority.toString());
  const [credentials, setCredentials] = useState<TCredentialDraft>({});
  const [extraConfig, setExtraConfig] = useState<TExtraConfigDraft>(() => emptyExtraConfig(gateway));
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    setIsEnabled(gateway.is_enabled);
    setIsSandbox(gateway.is_sandbox);
    setPriority(gateway.priority.toString());
    setExtraConfig(emptyExtraConfig(gateway));
    setCredentials({});
  }, [gateway]);

  const handleSave = useCallback(async () => {
    const payload: TPaymentGatewayUpdate = {
      is_enabled: isEnabled,
      is_sandbox: isSandbox,
      priority: toSafeNumber(priority),
    };

    // The API replaces stored credentials only when a non empty object is sent, so untouched
    // secret fields stay masked on the server instead of being wiped.
    const submittedCredentials = Object.fromEntries(
      Object.entries(credentials).filter(([, value]) => value.trim().length > 0)
    );
    if (Object.keys(submittedCredentials).length) payload.credentials = submittedCredentials;

    const nextExtraConfig: TPaymentGatewayExtraConfig = {
      ...gateway.extra_config,
      amount_unit: extraConfig.amount_unit,
    };
    if (extraConfig.base_url.trim()) nextExtraConfig.base_url = extraConfig.base_url.trim();
    else delete nextExtraConfig.base_url;
    if (extraConfig.callback_url.trim()) nextExtraConfig.callback_url = extraConfig.callback_url.trim();
    else delete nextExtraConfig.callback_url;
    if (extraConfig.timeout.trim()) nextExtraConfig.timeout = toSafeNumber(extraConfig.timeout);
    else delete nextExtraConfig.timeout;
    if (extraConfig.min_amount_toman.trim())
      nextExtraConfig.min_amount_toman = toSafeNumber(extraConfig.min_amount_toman);
    else delete nextExtraConfig.min_amount_toman;
    if (extraConfig.max_amount_toman.trim())
      nextExtraConfig.max_amount_toman = toSafeNumber(extraConfig.max_amount_toman);
    else delete nextExtraConfig.max_amount_toman;
    payload.extra_config = nextExtraConfig;

    setIsSaving(true);
    try {
      await BillingService.updateGateway(gateway.id, payload);
      setCredentials({});
      setToast({ type: "success", title: "ذخیره شد", message: `درگاه ${GATEWAY_LABELS[gateway.code]} ذخیره شد.` });
      onSaved();
    } catch (error) {
      setToast({
        type: "error",
        title: "ذخیره نشد",
        message: getErrorMessage(error, "ذخیره تنظیمات درگاه ناموفق بود."),
      });
    } finally {
      setIsSaving(false);
    }
  }, [credentials, extraConfig, gateway, isEnabled, isSandbox, onSaved, priority]);

  const handleDelete = useCallback(async () => {
    setIsDeleting(true);
    try {
      await BillingService.deleteGateway(gateway.id);
      setToast({ type: "success", title: "حذف شد", message: `درگاه ${GATEWAY_LABELS[gateway.code]} حذف شد.` });
      onSaved();
    } catch (error) {
      setToast({
        type: "error",
        title: "حذف نشد",
        message: getErrorMessage(error, "حذف درگاه ناموفق بود."),
      });
    } finally {
      setIsDeleting(false);
    }
  }, [gateway.code, gateway.id, onSaved]);

  return (
    <section className="rounded-custom flex flex-col gap-4 border border-subtle p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <h3 className="text-body-md-semibold text-primary">{GATEWAY_LABELS[gateway.code]}</h3>
          <Badge size="xs" variant="neutral" label={gateway.code} />
          {gateway.is_sandbox && <Badge size="xs" variant="warning" label="حالت تست" />}
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-13 text-secondary">
            فعال
            <Switch
              size="sm"
              checked={isEnabled}
              onCheckedChange={(checked: boolean) => setIsEnabled(checked)}
              aria-label={`فعال بودن درگاه ${GATEWAY_LABELS[gateway.code]}`}
            />
          </div>
          <div className="flex items-center gap-2 text-13 text-secondary">
            حالت تست
            <Switch
              size="sm"
              checked={isSandbox}
              onCheckedChange={(checked: boolean) => setIsSandbox(checked)}
              aria-label={`حالت تست درگاه ${GATEWAY_LABELS[gateway.code]}`}
            />
          </div>
        </div>
      </header>

      {gateway.last_error_message && (
        <p className="rounded-custom bg-warning-subtle px-3 py-2 text-12 text-warning-primary">
          آخرین خطا: {gateway.last_error_message}
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1">
          <label className="text-13 text-tertiary" htmlFor={`${gateway.id}-priority`}>
            اولویت
          </label>
          <Input
            size="lg"
            id={`${gateway.id}-priority`}
            type="number"
            value={priority}
            onChange={(event) => setPriority(event.target.value)}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-13 text-tertiary" htmlFor={`${gateway.id}-amount-unit`}>
            واحد پول ورودی
          </label>
          <Select
            value={extraConfig.amount_unit}
            onValueChange={(value) => {
              if (!value) return;
              setExtraConfig((prev) => ({ ...prev, amount_unit: value as TPaymentGatewayAmountUnit }));
            }}
          >
            <SelectTrigger id={`${gateway.id}-amount-unit`} size="lg" placeholder="واحد پول" />
            <SelectContent>
              <SelectList>
                {AMOUNT_UNIT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} size="lg" value={option.value} label={option.label} />
                ))}
              </SelectList>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex flex-col gap-3">
        <h4 className="text-13 text-secondary">اطلاعات محرمانه درگاه</h4>
        {credentialFields.map((field) => (
          <div key={field.key} className="flex flex-col gap-1">
            <label className="text-13 text-tertiary" htmlFor={`${gateway.id}-${field.key}`}>
              {field.label}
              {gateway.credentials?.[field.key] ? ` (ذخیره شده: ${gateway.credentials[field.key]})` : ""}
            </label>
            <Input
              size="lg"
              id={`${gateway.id}-${field.key}`}
              name={field.key}
              type="password"
              autoComplete="off"
              placeholder={field.placeholder}
              value={credentials[field.key] ?? ""}
              onChange={(event) => setCredentials((prev) => ({ ...prev, [field.key]: event.target.value }))}
            />
          </div>
        ))}
        <p className="text-11 text-tertiary">
          مقادیر ذخیره‌شده رمزنگاری می‌شوند و هرگز به‌صورت کامل نمایش داده نمی‌شوند. برای تغییر، مقدار جدید را وارد کنید؛
          خالی گذاشتن یعنی مقدار قبلی دست‌نخورده بماند.
        </p>
      </div>

      <div className="flex flex-col gap-3">
        <h4 className="text-13 text-secondary">تنظیمات اختصاصی درگاه</h4>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {(
            [
              { key: "base_url", label: "آدرس پایه درگاه" },
              { key: "callback_url", label: "آدرس بازگشت" },
              { key: "timeout", label: "مهلت پاسخ (ثانیه)" },
              { key: "min_amount_toman", label: "حداقل مبلغ (تومان)" },
              { key: "max_amount_toman", label: "حداکثر مبلغ (تومان)" },
            ] as const
          ).map((field) => (
            <div key={field.key} className="flex flex-col gap-1">
              <label className="text-13 text-tertiary" htmlFor={`${gateway.id}-${field.key}`}>
                {field.label}
              </label>
              <Input
                size="lg"
                id={`${gateway.id}-${field.key}`}
                type={field.key === "base_url" || field.key === "callback_url" ? "text" : "number"}
                value={extraConfig[field.key]}
                placeholder={
                  field.key === "base_url"
                    ? "پیش‌فرض آدرس رسمی درگاه"
                    : field.key === "callback_url"
                      ? "پیش‌فرض آدرس کال‌بک همین نصب"
                      : ""
                }
                onChange={(event) => setExtraConfig((prev) => ({ ...prev, [field.key]: event.target.value }))}
              />
            </div>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <Button
          variant="primary"
          size="md"
          stretch="auto"
          loading={isSaving}
          onClick={handleSave}
          label="ذخیره تنظیمات"
        />
        <Button
          variant="secondary"
          size="md"
          stretch="auto"
          loading={isDeleting}
          onClick={handleDelete}
          label="حذف درگاه"
        />
      </div>
    </section>
  );
}

export default function BillingGatewaysPage() {
  const { data, error, isLoading, mutate } = useSWR(BILLING_GATEWAYS, () => BillingService.gateways({}));

  const gateways = useMemo<TPaymentGateway[]>(() => data?.results ?? [], [data]);

  return (
    <BillingRTLFrame
      title="درگاه‌های پرداخت"
      description="فعال‌سازی درگاه، انتخاب حالت تست و ثبت اطلاعات محرمانه هر درگاه. اطلاعات محرمانه سمت سرور رمزنگاری می‌شود."
    >
      <BillingNav />

      {isLoading && <BillingEmptyState message="در حال بارگذاری درگاه‌ها…" />}
      {!isLoading && error && (
        <BillingEmptyState message={getErrorMessage(error, "بارگذاری فهرست درگاه‌ها ناموفق بود.")} />
      )}
      {!isLoading && !error && gateways.length === 0 && (
        <BillingEmptyState message="هیچ درگاهی برای این نصب ساخته نشده است." />
      )}

      {gateways.map((gateway) => (
        <GatewayCard key={gateway.id} gateway={gateway} onSaved={() => mutate()} />
      ))}
    </BillingRTLFrame>
  );
}
