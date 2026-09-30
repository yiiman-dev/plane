/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { KeyboardEvent } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isSameDay, isToday } from "date-fns";
import type { CalendarAdapter, CalendarMonthParts } from "../types";
import { DayCell } from "./day-cell";
import { MonthYearPicker } from "./month-year-picker";
import { useCalendarNavigation } from "./use-calendar-navigation";

/** Matches the shape `date-range-select.tsx` already uses, so a value passes straight through. */
export type DateRangeValue = { from: Date | null; to: Date | null };

export type PersianMonthGridProps = {
  adapter: CalendarAdapter;
  /** Selected value: a single day, a range, or nothing. */
  value: Date | null;
  range?: DateRangeValue;
  onSelect: (date: Date) => void;
  onRangeSelect?: (from: Date | null, to: Date | null) => void;
  month: CalendarMonthParts;
  onMonthChange: (month: CalendarMonthParts) => void;
  weekStartsOn?: number;
  minDate?: Date;
  maxDate?: Date;
  disabled?: boolean;
};

const sameDay = (a: Date | null, b: Date | null): boolean => Boolean(a && b && isSameDay(a, b));

/**
 * Whether a cell falls outside the pickable window.
 *
 * `minDate` is widened to the start of its day and `maxDate` to the end of its, so a caller passing
 * an arbitrary instant (a `Date` carrying a time, say) gets every day of that day rather than
 * losing both ends. `new Date(...)` copies, so neither argument is mutated. The comparisons are on
 * raw timestamps rather than `isAfter`/`isBefore` because grid cells are already at local midnight
 * and a DST day is 23 or 25 hours long.
 */
const isOutOfBounds = (date: Date, minDate?: Date, maxDate?: Date): boolean => {
  const time = date.getTime();
  if (minDate && time < new Date(minDate).setHours(0, 0, 0, 0)) return true;
  if (maxDate && time > new Date(maxDate).setHours(23, 59, 59, 999)) return true;
  return false;
};

/** The empty range, so the derived `shown` value keeps a stable identity across renders. */
const EMPTY_RANGE: DateRangeValue = { from: null, to: null };

/** Cells per week, and therefore rows in the fixed-height grid. */
const DAYS_PER_WEEK = 7;

const chunk = (days: Date[], size: number): Date[][] => {
  const rows: Date[][] = [];
  for (let index = 0; index < days.length; index += size) rows.push(days.slice(index, index + size));
  return rows;
};

/**
 * A 6×7 month grid in the adapter's calendar.
 *
 * The grid is always 42 cells, so its height never changes as the user pages; leading and trailing
 * cells come from the adjacent months and stay selectable, which is what makes stepping past a month
 * boundary feel continuous. Nothing in here branches on `adapter.system` — the adapter supplies the
 * parts, the names and the grid, so the same component drives either calendar.
 *
 * The visible month is controlled: `month` is what is on screen and `onMonthChange` is how the
 * parent changes it.
 */
export const PersianMonthGrid = (props: PersianMonthGridProps) => {
  const {
    adapter,
    value,
    range,
    onSelect,
    onRangeSelect,
    month,
    onMonthChange,
    weekStartsOn = 0,
    minDate,
    maxDate,
    disabled = false,
  } = props;

  /**
   * The open end of a range being picked. Held here rather than read from `range` for the same
   * reason `date-range-select.tsx` holds a draft: the first click of a range is not a finished
   * range, and a caller that has not yet been told about it cannot be relied on to echo it back.
   * `shown` is what the grid highlights, so the in-progress pick is visible immediately.
   */
  const [draft, setDraft] = useState<DateRangeValue | null>(null);
  const shown = draft ?? range ?? EMPTY_RANGE;

  const [focused, setFocused] = useState<Date>(() => value ?? adapter.getMonthStart(month));
  // Moving the roving tabindex is a DOM focus change, which must not happen on the initial render —
  // the grid is usually mounted inside a popover that is opening, and stealing focus there would
  // move it out from under whatever opened it.
  const shouldFocusRef = useRef(false);

  const navigation = useCalendarNavigation({
    adapter,
    month,
    onMonthChange,
    focused,
    onFocusedChange: (date) => {
      shouldFocusRef.current = true;
      setFocused(date);
    },
    weekStartsOn,
  });

  const days = useMemo(
    () => adapter.getMonthGrid(month.year, month.month, weekStartsOn),
    [adapter, month.year, month.month, weekStartsOn]
  );

  const weekdayNames = useMemo(() => adapter.getWeekdayNames("short", weekStartsOn), [adapter, weekStartsOn]);

  // The cell carrying the roving tabindex is the one to focus after a keyboard move. Looked up by
  // its data attribute rather than by holding a ref per cell, so the grid stays a plain list.
  const gridRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!shouldFocusRef.current) return;
    shouldFocusRef.current = false;
    gridRef.current?.querySelector<HTMLButtonElement>('[data-focused="true"]')?.focus();
  }, [focused]);

  const handleSelect = useCallback(
    (date: Date) => {
      if (disabled || isOutOfBounds(date, minDate, maxDate)) return;
      setFocused(date);
      if (onRangeSelect) {
        // The first click opens a range, the second closes it. A click on a day while a range is
        // already complete (or before one has started) restarts rather than extending.
        if (!shown.from || shown.to) {
          setDraft({ from: date, to: null });
          onRangeSelect(date, null);
          return;
        }
        setDraft(null);
        onRangeSelect(shown.from, date);
        return;
      }
      onSelect(date);
    },
    [disabled, minDate, maxDate, onRangeSelect, onSelect, shown]
  );

  // Enter and Space are deliberately absent: a day cell is a `<button>`, so the browser already
  // activates it on those keys, and calling `handleSelect` here would select the same day twice.
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (navigation.handleKeyDown(event)) event.preventDefault();
    },
    [navigation]
  );

  return (
    <div className="w-64">
      <div className="flex items-center justify-between pb-2">
        <button type="button" aria-label="Previous month" onClick={() => navigation.step(-1)} className="px-2 text-11">
          ‹
        </button>
        <MonthYearPicker adapter={adapter} month={month} years={navigation.years} onChange={onMonthChange} />
        <button type="button" aria-label="Next month" onClick={() => navigation.step(1)} className="px-2 text-11">
          ›
        </button>
      </div>

      {/* `role="grid"` requires `row` children, and `gridcell` requires a `row` ancestor, so the
          rows are real elements rather than a flat list of cells. The weekday header is its own
          `row` of `columnheader`s, as `react-day-picker` renders it. The `grid-cols-7` lives on
          each row so the columns stay aligned while the rows themselves stack. */}
      <div ref={gridRef} role="grid" className="flex flex-col gap-0.5" onKeyDown={handleKeyDown}>
        <div role="row" className="grid grid-cols-7">
          {weekdayNames.map((name) => (
            <div key={name} role="columnheader" className="flex h-8 items-center justify-center text-10 text-tertiary">
              {name}
            </div>
          ))}
        </div>
        {chunk(days, DAYS_PER_WEEK).map((week) => (
          <div role="row" key={week[0]?.getTime()} className="grid grid-cols-7 gap-0.5">
            {week.map((date) => {
              const parts = adapter.toParts(date);
              const isCurrentMonth = parts.year === month.year && parts.month === month.month;
              // `shown` is the draft while one is open, so the open end of a half-picked range
              // already counts as in-range and needs no separate case here. Compared as timestamps
              // rather than by calendar day: a DST day is not 24 hours, so a same-day comparison
              // via timestamps would drop a cell on the far side of a transition.
              const inRange = Boolean(shown.from && date >= shown.from && (!shown.to || date <= shown.to));
              return (
                <DayCell
                  key={date.getTime()}
                  adapter={adapter}
                  date={date}
                  isCurrentMonth={isCurrentMonth}
                  isSelected={sameDay(date, value) || sameDay(date, shown.from) || sameDay(date, shown.to)}
                  isInRange={inRange}
                  isToday={isToday(date)}
                  isDisabled={disabled || isOutOfBounds(date, minDate, maxDate)}
                  isFocused={sameDay(date, focused)}
                  onSelect={handleSelect}
                  onFocus={setFocused}
                />
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
};

PersianMonthGrid.displayName = "calendar.PersianMonthGrid";
