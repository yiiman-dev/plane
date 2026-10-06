/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { BillingService, BILLING_ROUTING } from "@plane/services";
import type {
  TPaymentGatewayCode,
  TPaymentGatewayRoutingConfig,
  TPaymentGatewayRoutingConfigPayload,
  TPaymentGatewayRoutingStrategy,
  TPaymentGatewayScheduleEntry,
} from "@plane/types";
import { Badge } from "@makeplane/propel/components/badge";
import { Button } from "@makeplane/propel/components/button";
import { Input } from "@makeplane/propel/components/input";
import { RadioGroupField, RadioGroupFieldOption } from "@makeplane/propel/components/radio-group-field";
import { Select, SelectContent, SelectItem, SelectList, SelectTrigger } from "@makeplane/propel/components/select";
import { setToast } from "@plane/blocks/toast";

import { BillingEmptyState, BillingNav, BillingRTLFrame, BillingSection } from "../components/billing-layout";
import { GATEWAY_LABELS, ROUTING_STRATEGIES } from "../constants";
import { formatDateTime, formatHourRange, getErrorMessage, toSafeNumber } from "../utils";

const GATEWAY_CODES = Object.keys(GATEWAY_LABELS) as TPaymentGatewayCode[];

const emptyScheduleEntry = (): TPaymentGatewayScheduleEntry => ({
  start_hour: 0,
  end_hour: 8,
  gateway_code: "zarinpal",
});

const emptyConfigPayload = (): TPaymentGatewayRoutingConfigPayload => ({
  cooldown_seconds: 60,
  max_attempts_per_gateway: 2,
  priority_order: [...GATEWAY_CODES],
  schedule_entries: [emptyScheduleEntry()],
  strategy: "priority",
  weights: Object.fromEntries(GATEWAY_CODES.map((code) => [code, 1])),
});

export default function BillingRoutingPage() {
  const { data, error, isLoading, mutate } = useSWR(BILLING_ROUTING, () => BillingService.routing());
  const [draft, setDraft] = useState<TPaymentGatewayRoutingConfigPayload>(emptyConfigPayload);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    const config = data as unknown as TPaymentGatewayRoutingConfig | undefined;
    if (!config) return;
    setDraft({
      cooldown_seconds: config.cooldown_seconds,
      max_attempts_per_gateway: config.max_attempts_per_gateway,
      priority_order: config.priority_order?.length ? config.priority_order : [...GATEWAY_CODES],
      schedule_entries: config.schedule_entries?.length ? config.schedule_entries : [emptyScheduleEntry()],
      strategy: config.strategy,
      weights: { ...Object.fromEntries(GATEWAY_CODES.map((code) => [code, 1])), ...config.weights },
    });
  }, [data]);

  const isValid = useMemo(() => {
    if (!draft.strategy) return false;
    if (!Number.isFinite(draft.cooldown_seconds) || draft.cooldown_seconds < 0) return false;
    if (!Number.isFinite(draft.max_attempts_per_gateway) || draft.max_attempts_per_gateway < 1) return false;
    if (draft.strategy === "schedule")
      return draft.schedule_entries.every(
        (entry) =>
          entry.start_hour >= 0 &&
          entry.end_hour >= 0 &&
          entry.start_hour <= 24 &&
          entry.end_hour <= 24 &&
          Boolean(entry.gateway_code)
      );
    if (draft.strategy === "priority") return draft.priority_order.length > 0;
    return Object.values(draft.weights).every((weight) => weight === undefined || weight >= 0);
  }, [draft]);

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    try {
      await BillingService.updateRouting(draft);
      setToast({ type: "success", title: "ذخیره شد", message: "پیکربندی انتخاب درگاه ذخیره شد." });
      mutate();
    } catch (err) {
      setToast({
        type: "error",
        title: "ذخیره نشد",
        message: getErrorMessage(err, "ذخیره پیکربندی انتخاب درگاه ناموفق بود."),
      });
    } finally {
      setIsSaving(false);
    }
  }, [draft, mutate]);

  const movePriority = useCallback((index: number, direction: -1 | 1) => {
    setDraft((prev) => {
      const target = index + direction;
      if (target < 0 || target >= prev.priority_order.length) return prev;
      const order = [...prev.priority_order];
      [order[index], order[target]] = [order[target], order[index]];
      return { ...prev, priority_order: order };
    });
  }, []);

  const config = data as unknown as TPaymentGatewayRoutingConfig | undefined;

  return (
    <BillingRTLFrame
      title="انتخاب درگاه"
      description="تعیین کنید هر پرداخت با کدام درگاه آغاز شود. پرداخت ناموفق کاربر هرگز درگاه را عوض نمی‌کند و فقط خطای عدم دسترسی یا پردازش ناتمام باعث رفتن به درگاه بعدی می‌شود."
    >
      <BillingNav />

      {isLoading && <BillingEmptyState message="در حال بارگذاری پیکربندی…" />}
      {!isLoading && error && (
        <BillingEmptyState message={getErrorMessage(error, "بارگذاری پیکربندی انتخاب درگاه ناموفق بود.")} />
      )}

      {!isLoading && !error && (
        <>
          {config?.last_selected_code && (
            <div className="flex flex-wrap items-center gap-2 text-13 text-secondary">
              <span>آخرین درگاه انتخاب‌شده:</span>
              <Badge
                size="xs"
                variant="neutral"
                label={GATEWAY_LABELS[config.last_selected_code as TPaymentGatewayCode] ?? config.last_selected_code}
              />
              {config.last_selected_reason && <span>({config.last_selected_reason})</span>}
              {config.updated_at && <span>آخرین به‌روزرسانی: {formatDateTime(config.updated_at)}</span>}
            </div>
          )}

          <BillingSection title="روش انتخاب درگاه">
            <RadioGroupField
              name="billing-routing-strategy"
              label="یکی از روش‌های زیر را انتخاب کنید"
              size="md"
              density="compact"
              value={draft.strategy}
              onValueChange={(value) =>
                setDraft((prev) => ({ ...prev, strategy: value as TPaymentGatewayRoutingStrategy }))
              }
            >
              {ROUTING_STRATEGIES.map((strategy) => (
                <RadioGroupFieldOption
                  key={strategy.value}
                  value={strategy.value}
                  label={strategy.label}
                  description={strategy.description}
                />
              ))}
            </RadioGroupField>
          </BillingSection>

          {draft.strategy === "schedule" && (
            <BillingSection title="بازه‌های زمانی روز">
              <div className="flex flex-col gap-3">
                {draft.schedule_entries.map((entry, index) => (
                  <div
                    key={`schedule-${entry.gateway_code}-${entry.start_hour}-${entry.end_hour}`}
                    className="grid grid-cols-1 items-end gap-3 md:grid-cols-4"
                  >
                    <div className="flex flex-col gap-1">
                      <label className="text-13 text-tertiary" htmlFor={`schedule-start-${index}`}>
                        ساعت شروع
                      </label>
                      <Input
                        id={`schedule-start-${index}`}
                        size="lg"
                        type="number"
                        min={0}
                        max={24}
                        value={entry.start_hour.toString()}
                        onChange={(event) =>
                          setDraft((prev) => ({
                            ...prev,
                            schedule_entries: prev.schedule_entries.map((item, itemIndex) =>
                              itemIndex === index
                                ? { ...item, start_hour: Math.min(24, Math.max(0, toSafeNumber(event.target.value))) }
                                : item
                            ),
                          }))
                        }
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-13 text-tertiary" htmlFor={`schedule-end-${index}`}>
                        ساعت پایان
                      </label>
                      <Input
                        id={`schedule-end-${index}`}
                        size="lg"
                        type="number"
                        min={0}
                        max={24}
                        value={entry.end_hour.toString()}
                        onChange={(event) =>
                          setDraft((prev) => ({
                            ...prev,
                            schedule_entries: prev.schedule_entries.map((item, itemIndex) =>
                              itemIndex === index
                                ? { ...item, end_hour: Math.min(24, Math.max(0, toSafeNumber(event.target.value))) }
                                : item
                            ),
                          }))
                        }
                      />
                    </div>
                    <div className="flex flex-col gap-1">
                      <label className="text-13 text-tertiary" htmlFor={`schedule-gateway-${index}`}>
                        درگاه
                      </label>
                      <Select
                        value={entry.gateway_code}
                        onValueChange={(value) => {
                          if (!value) return;
                          setDraft((prev) => ({
                            ...prev,
                            schedule_entries: prev.schedule_entries.map((item, itemIndex) =>
                              itemIndex === index ? { ...item, gateway_code: value as TPaymentGatewayCode } : item
                            ),
                          }));
                        }}
                      >
                        <SelectTrigger id={`schedule-gateway-${index}`} size="lg" placeholder="درگاه" />
                        <SelectContent>
                          <SelectList>
                            {GATEWAY_CODES.map((code) => (
                              <SelectItem key={code} size="lg" value={code} label={GATEWAY_LABELS[code]} />
                            ))}
                          </SelectList>
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-11 text-tertiary">{formatHourRange(entry.start_hour, entry.end_hour)}</span>
                      <Button
                        variant="secondary"
                        size="sm"
                        stretch="auto"
                        label="حذف"
                        onClick={() =>
                          setDraft((prev) => ({
                            ...prev,
                            schedule_entries: prev.schedule_entries.filter((_, itemIndex) => itemIndex !== index),
                          }))
                        }
                      />
                    </div>
                  </div>
                ))}
                <div>
                  <Button
                    variant="secondary"
                    size="md"
                    stretch="auto"
                    label="افزودن بازه"
                    onClick={() =>
                      setDraft((prev) => ({
                        ...prev,
                        schedule_entries: [...prev.schedule_entries, emptyScheduleEntry()],
                      }))
                    }
                  />
                </div>
                <p className="text-11 text-tertiary">
                  اگر ساعت پایان از ساعت شروع کوچک‌تر یا مساوی باشد، بازه از نیمه‌شب عبور می‌کند. زمان بر اساس ساعت تهران
                  محاسبه می‌شود و در صورت نبود بازه منطبق، ترتیب اولویت به‌عنوان جایگزین استفاده می‌شود.
                </p>
              </div>
            </BillingSection>
          )}

          {draft.strategy === "random" && (
            <BillingSection title="وزن هر درگاه">
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                {GATEWAY_CODES.map((code) => (
                  <div key={code} className="flex flex-col gap-1">
                    <label className="text-13 text-tertiary" htmlFor={`weight-${code}`}>
                      وزن {GATEWAY_LABELS[code]}
                    </label>
                    <Input
                      id={`weight-${code}`}
                      size="lg"
                      type="number"
                      min={0}
                      value={(draft.weights[code] ?? 0).toString()}
                      onChange={(event) =>
                        setDraft((prev) => ({
                          ...prev,
                          weights: { ...prev.weights, [code]: Math.max(0, toSafeNumber(event.target.value)) },
                        }))
                      }
                    />
                  </div>
                ))}
              </div>
              <p className="mt-3 text-11 text-tertiary">
                وزن‌ها نسبت احتمال انتخاب هستند. وزن صفر یعنی آن درگاه در انتخاب تصادفی شرکت نکند.
              </p>
            </BillingSection>
          )}

          {draft.strategy === "priority" && (
            <BillingSection title="ترتیب اولویت درگاه‌ها">
              <div className="flex flex-col gap-2">
                {draft.priority_order.map((code, index) => (
                  <div
                    key={`priority-${code}`}
                    className="rounded-custom flex items-center justify-between border border-subtle px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <Badge size="xs" variant={index === 0 ? "brand" : "neutral"} label={`اولویت ${index + 1}`} />
                      <span className="text-13 text-primary">{GATEWAY_LABELS[code] ?? code}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Button
                        variant="secondary"
                        size="sm"
                        stretch="auto"
                        label="بالا"
                        onClick={() => movePriority(index, -1)}
                      />
                      <Button
                        variant="secondary"
                        size="sm"
                        stretch="auto"
                        label="پایین"
                        onClick={() => movePriority(index, 1)}
                      />
                    </div>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-11 text-tertiary">
                اولویت اول درگاه اصلی است؛ بقیه به‌صورت passive و فقط هنگام در دسترس نبودن درگاه قبلی فعال می‌شوند.
              </p>
            </BillingSection>
          )}

          <BillingSection title="محدودیت‌های جایگزینی">
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div className="flex flex-col gap-1">
                <label className="text-13 text-tertiary" htmlFor="cooldown-seconds">
                  مدت خنک‌سازی پس از خطا (ثانیه)
                </label>
                <Input
                  id="cooldown-seconds"
                  size="lg"
                  type="number"
                  min={0}
                  value={draft.cooldown_seconds.toString()}
                  onChange={(event) =>
                    setDraft((prev) => ({ ...prev, cooldown_seconds: Math.max(0, toSafeNumber(event.target.value)) }))
                  }
                />
              </div>
              <div className="flex flex-col gap-1">
                <label className="text-13 text-tertiary" htmlFor="max-attempts">
                  حداکثر تلاش روی هر درگاه
                </label>
                <Input
                  id="max-attempts"
                  size="lg"
                  type="number"
                  min={1}
                  value={draft.max_attempts_per_gateway.toString()}
                  onChange={(event) =>
                    setDraft((prev) => ({
                      ...prev,
                      max_attempts_per_gateway: Math.max(1, toSafeNumber(event.target.value)),
                    }))
                  }
                />
              </div>
            </div>
          </BillingSection>

          <div>
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              loading={isSaving}
              disabled={!isValid}
              onClick={handleSave}
              label="ذخیره پیکربندی"
            />
          </div>
        </>
      )}
    </BillingRTLFrame>
  );
}
