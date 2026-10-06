/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { CalendarSurface, getCalendarAdapter } from "@plane/calendar";
import type { CalendarMonthParts } from "@plane/calendar";
import { renderFormattedDate } from "@plane/utils";
import type { DateSelectCommonProps } from "./date-select-shell";
import { DateSelectShell } from "./date-select-shell";
import { DEFAULT_DATE_FORMAT_TOKEN } from "./date-select.utils";

export type DateSelectProps = DateSelectCommonProps & {
  /** The picked day, or `null` when nothing is set. */
  value: Date | null;
  /** Emits the newly picked day, or `null` when cleared. */
  onChange: (date: Date | null) => void;
};

/**
 * Presentational, data-source-agnostic single-day picker: the `Select` trigger chrome over a month
 * grid in a popover. The client owns the value and supplies the user's `weekStartsOn`,
 * `calendarSystem` and `formatToken` — this block owns only the picker.
 */
export function DateSelect(props: DateSelectProps) {
  const {
    value,
    onChange,
    formatToken = DEFAULT_DATE_FORMAT_TOKEN,
    minDate,
    maxDate,
    weekStartsOn,
    calendarSystem = "gregorian",
    defaultMonth,
    placeholder = "",
    clearable = false,
    onClose,
  } = props;
  // states
  const [isOpen, setIsOpen] = useState(props.defaultOpen ?? false);
  /**
   * Which month the Persian grid is showing. Only the Persian branch reads it — the Gregorian branch
   * hands `defaultMonth` to `react-day-picker` and lets it re-seed on every mount — but it is
   * seeded here from the same inputs so the two branches open on the same month.
   */
  const [visibleMonth, setVisibleMonth] = useState<CalendarMonthParts>(() => {
    const seed = value ?? defaultMonth ?? new Date();
    const { year, month } = getCalendarAdapter(calendarSystem).toParts(seed);
    return { year, month };
  });
  // derived values
  const formatted = renderFormattedDate(value, formatToken, calendarSystem) ?? "";

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open);
    // Re-seed the Persian grid's month on open, the way `react-day-picker` re-seeds from
    // `defaultMonth` every time the popover remounts it. Without this, a value changed elsewhere
    // while the popover was shut would leave the grid on a stale month.
    if (open) {
      const seed = value ?? defaultMonth ?? new Date();
      const { year, month } = getCalendarAdapter(calendarSystem).toParts(seed);
      setVisibleMonth({ year, month });
    }
    if (!open) onClose?.();
  };

  return (
    <DateSelectShell
      {...props}
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
      label={formatted || placeholder}
      isEmpty={!value}
      tooltipContent={props.tooltipContent ?? formatted}
      canClear={clearable && value !== null}
      onClear={() => {
        onChange(null);
        handleOpenChange(false);
      }}
    >
      <CalendarSurface
        system={calendarSystem}
        mode="single"
        value={value}
        onSelect={(date) => {
          // A repeat click on the selected day deselects it in react-day-picker; treat that as a
          // clear only when the caller allows one, otherwise keep the current value.
          if (!date && !clearable) return;
          onChange(date);
          handleOpenChange(false);
        }}
        month={visibleMonth}
        onMonthChange={setVisibleMonth}
        defaultMonth={defaultMonth}
        weekStartsOn={weekStartsOn}
        minDate={minDate}
        maxDate={maxDate}
      />
    </DateSelectShell>
  );
}

DateSelect.displayName = "blocks.DateSelect";
