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

/** Both ends of the picked range. Either end may be unset. */
export type DateRangeValue = {
  from: Date | null;
  to: Date | null;
};

export type DateRangeSelectProps = DateSelectCommonProps & {
  value: DateRangeValue;
  /**
   * Emits the completed range — both ends at once, on the second click. The first click only opens
   * the range (it is held internally and shown in the calendar, but not emitted), so a caller never
   * has to persist a half-picked range. A one-day range comes through as `from === to`. Clearing
   * emits `{ from: null, to: null }`.
   */
  onChange: (range: DateRangeValue) => void;
  /**
   * Collapses the trigger label to the shared parts of the two dates — "Jun 10 - 24, 2025" for a
   * range inside one month, "Jan 24 - Feb 02, 2025" inside one year — instead of repeating the
   * whole date twice. Honoured for the four `formatToken` values Plane ships (`MMM dd, yyyy`,
   * `dd/MM/yyyy`, `MM/dd/yyyy`, `yyyy/MM/dd` — see `MERGE_TOKENS`); any other token keeps the whole
   * label on both ends. Ignored when {@link formatLabel} is given. @default false
   */
  mergeDates?: boolean;
  /**
   * Full control of the trigger label. Receives the committed range and both ends already formatted
   * with `formatToken`; return the string the trigger should show. Wins over {@link mergeDates}.
   */
  formatLabel?: (range: DateRangeValue, formatted: { from: string; to: string }) => string;
};

/** The tokens each end is formatted with, for one of the two merge cases. */
type MergeTokenPair = { from: string; to: string };

/**
 * How the merged label is built, per date format Plane ships (`TDateAttributeDisplayOptions` in
 * `packages/types/src/work-item-types/work-item-property-configurations.ts`). The parts the two
 * dates share are printed once, at whichever end of the token they sit:
 *
 * | `formatToken`  | same year, other month  | same month            |
 * | -------------- | ----------------------- | --------------------- |
 * | `MMM dd, yyyy` | `Jan 24 - Feb 02, 2025` | `Jun 10 - 24, 2025`   |
 * | `dd/MM/yyyy`   | `24/01 - 02/02/2025`    | `10 - 24/06/2025`     |
 * | `MM/dd/yyyy`   | `01/24 - 02/02/2025`    | `06/10 - 24/2025`     |
 * | `yyyy/MM/dd`   | `2025/01/24 - 02/02`    | `2025/06/10 - 24`     |
 *
 * Hand-written per token rather than derived by trimming segments off the caller's own token:
 * a regex that strips `y+` or `M+` with its separator leaves dangling and doubled slashes in every
 * token but the first ("dd/MM/yyyy" became "10/06/ - 24//2025"). An unlisted token keeps the whole
 * label on both ends.
 */
const MERGE_TOKENS: Record<string, { sameYear: MergeTokenPair; sameMonth: MergeTokenPair }> = {
  "MMM dd, yyyy": { sameYear: { from: "MMM dd", to: "MMM dd, yyyy" }, sameMonth: { from: "MMM dd", to: "dd, yyyy" } },
  "dd/MM/yyyy": { sameYear: { from: "dd/MM", to: "dd/MM/yyyy" }, sameMonth: { from: "dd", to: "dd/MM/yyyy" } },
  "MM/dd/yyyy": { sameYear: { from: "MM/dd", to: "MM/dd/yyyy" }, sameMonth: { from: "MM/dd", to: "dd/yyyy" } },
  "yyyy/MM/dd": { sameYear: { from: "yyyy/MM/dd", to: "MM/dd" }, sameMonth: { from: "yyyy/MM/dd", to: "dd" } },
};

/**
 * The merged label: drop from one end whatever the other repeats. Two days in one month give
 * "Jun 10 - 24, 2025"; two months in one year give "Jan 24 - Feb 02, 2025"; anything wider — or any
 * `formatToken` outside {@link MERGE_TOKENS} — stays whole.
 *
 * `formatOne` is `formatToken`-aware rather than a bare `date-fns` `format`, so both ends speak the
 * user's calendar. The merge is skipped when a narrowed token renders *identically* to the full one
 * — which is what a Persian adapter does for a token it cannot map, since it falls back to the full
 * form — so the Persian label collapses to the un-merged one rather than repeating a whole date
 * where a fragment was meant to go.
 */
function mergeRangeLabel(
  range: DateRangeValue,
  from: string,
  to: string,
  formatToken: string,
  formatOne: (date: Date, token: string) => string
): string {
  const joined = from && to ? `${from} - ${to}` : from || to;
  if (!range.from || !range.to || !from || !to) return joined;
  if (range.from.getFullYear() !== range.to.getFullYear()) return joined;
  const tokens = MERGE_TOKENS[formatToken];
  if (!tokens) return joined;
  const pair = range.from.getMonth() === range.to.getMonth() ? tokens.sameMonth : tokens.sameYear;
  const mergedFrom = formatOne(range.from, pair.from);
  const mergedTo = formatOne(range.to, pair.to);
  if (mergedFrom === from && mergedTo === to) return joined;
  return `${mergedFrom} - ${mergedTo}`;
}

/**
 * Presentational, data-source-agnostic range picker: the `Select` trigger chrome over a month grid
 * in range mode. The grid shows a single month and the user pages through it — the two-month
 * side-by-side layout needs an upstream prop before it can come back.
 */
export function DateRangeSelect(props: DateRangeSelectProps) {
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
  // The grid answers the FIRST click of a range with an open end rather than a finished one-day
  // range. That half-picked range is held here — shown in the calendar, withheld from `onChange` —
  // until the second click completes it, so a caller never sees a range it did not ask for.
  const [draft, setDraft] = useState<DateRangeValue | null>(null);
  /**
   * Which month the Persian grid is showing. Only the Persian branch reads it — the Gregorian branch
   * hands `defaultMonth` to `react-day-picker` and lets it re-seed on every mount — but it is
   * seeded here from the same inputs so the two branches open on the same month.
   */
  const [visibleMonth, setVisibleMonth] = useState<CalendarMonthParts>(() => {
    const seed = value.from ?? defaultMonth ?? new Date();
    const { year, month } = getCalendarAdapter(calendarSystem).toParts(seed);
    return { year, month };
  });
  // derived values
  const formatOne = (date: Date, token: string): string => renderFormattedDate(date, token, calendarSystem) ?? "";
  const from = value.from ? formatOne(value.from, formatToken) : "";
  const to = value.to ? formatOne(value.to, formatToken) : "";
  const joined = from && to ? `${from} - ${to}` : from || to;
  const formatted = props.formatLabel
    ? props.formatLabel(value, { from, to })
    : props.mergeDates
      ? mergeRangeLabel(value, from, to, formatToken, formatOne)
      : joined;
  const isEmpty = !value.from && !value.to;
  // The calendar shows the in-progress pick; the trigger keeps showing the committed value.
  const shown = draft ?? value;

  const handleOpenChange = (open: boolean) => {
    setIsOpen(open);
    setDraft(null);
    // Re-seed the Persian grid's month on open, the way `react-day-picker` re-seeds from
    // `defaultMonth` every time the popover remounts it.
    if (open) {
      const seed = value.from ?? defaultMonth ?? new Date();
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
      isEmpty={isEmpty}
      tooltipContent={props.tooltipContent ?? joined}
      canClear={clearable && !isEmpty}
      onClear={() => {
        onChange({ from: null, to: null });
        handleOpenChange(false);
      }}
    >
      <CalendarSurface
        system={calendarSystem}
        mode="range"
        value={null}
        range={shown}
        onSelect={() => {
          // A range is picked through `onRangeSelect`; the grid never reports a single day.
        }}
        onRangeSelect={(pickedFrom, pickedTo) => {
          const next = { from: pickedFrom, to: pickedTo };
          // Deselecting the open end restarts the range without emitting.
          if (!next.from) {
            setDraft(null);
            return;
          }
          if (draft) {
            // Second click: the range is complete, so commit it and close (which clears the draft).
            onChange(next);
            handleOpenChange(false);
            return;
          }
          // First click: an open end waiting for the next click, not a finished range.
          setDraft({ from: next.from, to: null });
        }}
        month={visibleMonth}
        onMonthChange={setVisibleMonth}
        defaultMonth={defaultMonth}
        weekStartsOn={weekStartsOn}
        minDate={minDate}
        maxDate={maxDate}
        disabled={props.disabled}
      />
    </DateSelectShell>
  );
}

DateRangeSelect.displayName = "blocks.DateRangeSelect";
