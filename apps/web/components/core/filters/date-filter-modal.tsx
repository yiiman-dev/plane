/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { Button } from "@makeplane/propel/components/button";
import {
  Dialog,
  DialogActions,
  DialogBody,
  DialogClose,
  DialogCloseGroup,
  DialogContent,
  DialogMain,
} from "@makeplane/propel/components/dialog";
import { Icon } from "@makeplane/propel/components/icon";
import { IconButton } from "@makeplane/propel/components/icon-button";
import { CloseOutline } from "@makeplane/propel/icons";
import { useTranslation } from "@plane/i18n";
import { CalendarSurface, getCalendarAdapter } from "@plane/blocks/property-select";
import type { CalendarMonthParts } from "@plane/blocks/property-select";
import { renderFormattedPayloadDate, renderFormattedDate, getDate } from "@plane/utils";
// hooks
import { useUserProfile } from "@/hooks/store/user";
// local imports
import { DateFilterSelect } from "./date-filter-select";
type Props = {
  title: string;
  handleClose: () => void;
  isOpen: boolean;
  onSelect: (val: string[]) => void;
};

type TFormValues = {
  filterType: "before" | "after" | "range";
  date1: Date;
  date2: Date;
};

const defaultValues: TFormValues = {
  filterType: "range",
  date1: new Date(),
  date2: new Date(new Date().getFullYear(), new Date().getMonth() + 1, new Date().getDate()),
};

export function DateFilterModal({ title, handleClose, isOpen, onSelect }: Props) {
  // plane hooks
  const { t } = useTranslation();
  const { data: userProfile } = useUserProfile();
  const calendarSystem = userProfile?.calendar_system ?? "gregorian";
  const { handleSubmit, watch, control } = useForm<TFormValues>({
    defaultValues,
  });
  // Each end of the range gets its own visible month, as it gets its own calendar. The Gregorian
  // branch re-seeds itself from `defaultMonth` when react-day-picker mounts, so this state only
  // steers the Persian grid; seeding once matches react-day-picker's own behaviour, which does not
  // follow `selected` as it changes.
  const [month1, setMonth1] = useState<CalendarMonthParts>(() => {
    const { year, month } = getCalendarAdapter(calendarSystem).toParts(defaultValues.date1);
    return { year, month };
  });
  const [month2, setMonth2] = useState<CalendarMonthParts>(() => {
    const { year, month } = getCalendarAdapter(calendarSystem).toParts(defaultValues.date2);
    return { year, month };
  });

  const handleFormSubmit = (formData: TFormValues) => {
    const { filterType, date1, date2 } = formData;

    if (filterType === "range")
      onSelect([`${renderFormattedPayloadDate(date1)};after`, `${renderFormattedPayloadDate(date2)};before`]);
    else onSelect([`${renderFormattedPayloadDate(date1)};${filterType}`]);

    handleClose();
  };

  const date1 = getDate(watch("date1"));
  const date2 = getDate(watch("date1"));

  const isInvalid = watch("filterType") === "range" && date1 && date2 ? date1 > date2 : false;

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogContent size="md">
        <DialogCloseGroup>
          <IconButton
            variant="ghost"
            size="xs"
            icon={<Icon icon={CloseOutline} />}
            aria-label={t("close")}
            render={<DialogClose />}
          />
        </DialogCloseGroup>
        <form className="flex min-h-0 flex-1 flex-col">
          <DialogMain>
            <DialogBody tabIndex={0}>
              <div className="space-y-4">
                <div className="flex w-full justify-between">
                  <Controller
                    control={control}
                    name="filterType"
                    render={({ field: { value, onChange } }) => (
                      <DateFilterSelect title={title} value={value} onChange={onChange} />
                    )}
                  />
                </div>
                <div className="flex w-full justify-between gap-4">
                  <Controller
                    control={control}
                    name="date1"
                    render={({ field: { value, onChange } }) => {
                      const dateValue = getDate(value);
                      const date2Value = getDate(watch("date2"));
                      return (
                        <CalendarSurface
                          system={calendarSystem}
                          mode="single"
                          value={dateValue ?? null}
                          onSelect={(date) => {
                            if (!date) return;
                            onChange(date);
                          }}
                          month={month1}
                          onMonthChange={setMonth1}
                          defaultMonth={dateValue ?? undefined}
                          showOutsideDays
                          maxDate={date2Value ?? undefined}
                        />
                      );
                    }}
                  />
                  {watch("filterType") === "range" && (
                    <Controller
                      control={control}
                      name="date2"
                      render={({ field: { value, onChange } }) => {
                        const dateValue = getDate(value);
                        const date1Value = getDate(watch("date1"));
                        return (
                          <CalendarSurface
                            system={calendarSystem}
                            mode="single"
                            value={dateValue ?? null}
                            onSelect={(date) => {
                              if (!date) return;
                              onChange(date);
                            }}
                            month={month2}
                            onMonthChange={setMonth2}
                            defaultMonth={dateValue ?? undefined}
                            showOutsideDays
                            minDate={date1Value ?? undefined}
                          />
                        );
                      }}
                    />
                  )}
                </div>
                {watch("filterType") === "range" && (
                  <h6 className="flex items-center gap-1 text-11">
                    <span className="text-secondary">After:</span>
                    <span>{renderFormattedDate(watch("date1"))}</span>
                    <span className="ml-1 text-secondary">Before:</span>
                    {!isInvalid && <span>{renderFormattedDate(watch("date2"))}</span>}
                  </h6>
                )}
              </div>
            </DialogBody>
          </DialogMain>
          <DialogActions>
            <Button variant="secondary" size="md" stretch="auto" label="Cancel" onClick={handleClose} />
            <Button
              variant="primary"
              size="md"
              stretch="auto"
              type="button"
              label="Apply"
              onClick={() => {
                void handleSubmit(handleFormSubmit)();
              }}
              disabled={isInvalid}
            />
          </DialogActions>
        </form>
      </DialogContent>
    </Dialog>
  );
}
