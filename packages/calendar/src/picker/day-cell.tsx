/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { CalendarAdapter } from "../types";

/**
 * The accessible name of a day cell, in whichever calendar the adapter speaks.
 *
 * Exported because it *is* the contract: `packages/blocks`' date-picker tests locate day buttons by
 * this exact string, so a test in this package can assert the same labels the shipped picker
 * produces rather than a re-derivation of them that could drift.
 *
 * `dayOrdinal` is what makes the labels match. `react-day-picker`'s default `labelDayButton`
 * formats with `PPPP`, which includes the ordinal ("Sunday, June 15th, 2025"); without the ordinal
 * flag the adapter produces "Sunday, June 15, 2025", which is a *different* string and would stop
 * every existing day-button query from matching. Persian has no ordinal day form, so its adapter
 * ignores the flag and produces its own equivalent.
 */
export const dayCellLabel = (date: Date, adapter: CalendarAdapter): string =>
  adapter.format(date, {
    weekday: "long",
    year: "numeric",
    month: "long",
    day: "numeric",
    dayOrdinal: true,
  });

type Props = {
  adapter: CalendarAdapter;
  date: Date;
  /** Whether this day belongs to the month on screen, as opposed to a padding cell. */
  isCurrentMonth: boolean;
  isSelected: boolean;
  isInRange: boolean;
  isToday: boolean;
  isDisabled: boolean;
  /** Whether the roving tabindex currently sits on this cell. Exactly one cell has it. */
  isFocused: boolean;
  onSelect: (date: Date) => void;
  onFocus: (date: Date) => void;
};

/**
 * One day in the grid.
 *
 * A plain `<button>` rather than propel's `Button`: a day cell is 42 instances of the same shape
 * whose whole appearance is per-cell state (selected / in range / today / padding month), and
 * propel's element `Button` deliberately omits `className` from its props so a consumer cannot
 * restyle it at all. The state below is exactly what those variants would encode anyway.
 *
 * The accessible name is built by the adapter rather than hardcoded English, which is what lets the
 * same grid speak Persian. It is the label the existing `date-picker` tests query day cells by, so
 * changing how it is derived changes that test surface.
 */
export const DayCell = ({
  adapter,
  date,
  isCurrentMonth,
  isSelected,
  isInRange,
  isToday,
  isDisabled,
  isFocused,
  onSelect,
  onFocus,
}: Props) => {
  return (
    // The `gridcell` wrapper carries `aria-selected`, the button inside carries the accessible name
    // and the tab stop. Splitting them is what `react-day-picker` does, and it is not incidental:
    // `aria-selected` is not a valid attribute on `role="button"`, and a `gridcell` is the element
    // ARIA defines as selectable within a `grid`.
    <div
      role="gridcell"
      aria-selected={isSelected}
      data-in-month={isCurrentMonth ? "true" : "false"}
      data-in-range={isInRange ? "true" : "false"}
    >
      <button
        type="button"
        aria-label={dayCellLabel(date, adapter)}
        aria-current={isToday ? "date" : undefined}
        // Roving tabindex: the grid is one tab stop, and the arrow keys move within it.
        tabIndex={isFocused ? 0 : -1}
        data-focused={isFocused ? "true" : "false"}
        disabled={isDisabled}
        onClick={() => onSelect(date)}
        onFocus={() => onFocus(date)}
        className={[
          "h-8 w-8 rounded-md text-11",
          isCurrentMonth ? "text-primary" : "text-tertiary",
          isInRange && "bg-accent-subtle",
          isSelected && "bg-accent-primary text-white",
          isToday && !isSelected && "ring-1 ring-accent-strong",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {/* Day numbers in Persian are Persian digits, so even the visible number comes from the
            adapter rather than from `date-fns`. */}
        {adapter.format(date, { day: "numeric" })}
      </button>
    </div>
  );
};

DayCell.displayName = "calendar.DayCell";
