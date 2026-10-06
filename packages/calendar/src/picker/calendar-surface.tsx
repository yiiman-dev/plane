/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Calendar } from "@makeplane/propel/components/calendar";
import { getCalendarAdapter } from "../adapters";
import type { CalendarMonthParts, CalendarSystem } from "../types";
import type { DateRangeValue } from "./persian-month-grid";
import { PersianMonthGrid } from "./persian-month-grid";

/**
 * Both bounds inclusive, so they become exclusions rather than the bounds themselves. This is the
 * same logic as `buildDisabledMatchers` in `@plane/blocks`; it is duplicated here rather than
 * imported because that would make `@plane/calendar` depend on `@plane/blocks`, which already
 * depends on this package.
 */
const buildDisabledMatchers = (minDate?: Date, maxDate?: Date): ({ before: Date } | { after: Date })[] | undefined => {
  if (!minDate && !maxDate) return undefined;
  const matchers: ({ before: Date } | { after: Date })[] = [];
  if (minDate) matchers.push({ before: minDate });
  if (maxDate) matchers.push({ after: maxDate });
  return matchers;
};

export type CalendarSurfaceProps = {
  system: CalendarSystem;
  mode: "single" | "range";
  value: Date | null;
  /**
   * `undefined` is written out rather than left implicit because the props are forwarded straight
   * to `PersianMonthGrid`, which this package compiles with `exactOptionalPropertyTypes`.
   */
  range?: DateRangeValue | undefined;
  /** Receives the picked day, or `null` when the user deselected it. Unused in `range` mode. */
  onSelect: (date: Date | null) => void;
  onRangeSelect?: ((from: Date | null, to: Date | null) => void) | undefined;
  /** The month the grid shows, in the adapter's own 1-based numbering. Owned by the caller. */
  month: CalendarMonthParts;
  onMonthChange: (month: CalendarMonthParts) => void;
  /**
   * Month shown on open while nothing is picked. The Gregorian branch hands this to
   * `react-day-picker` as its uncontrolled `defaultMonth`; the Persian grid ignores it, because its
   * month is controlled through `month` instead.
   */
  defaultMonth?: Date;
  /**
   * First day of the week, 0 = Sunday. The same numbering `Profile.start_of_the_week` and
   * `react-day-picker` use; narrowed to the seven valid values so this prop is assignable straight
   * from a profile value.
   */
  weekStartsOn?: 0 | 1 | 2 | 3 | 4 | 5 | 6;
  minDate?: Date;
  maxDate?: Date;
  /**
   * Whether the adjacent months' days are drawn. Honoured by the Gregorian branch only: the Persian
   * grid is a fixed 6×7 of which the leading and trailing cells are always the neighbouring months',
   * so its outside days cannot be hidden.
   */
  showOutsideDays?: boolean;
  /**
   * Disables every cell. A `DateSelect` that is `disabled` cannot open its popover at all, so this
   * only reaches the grid when a caller renders one directly.
   */
  disabled?: boolean;
};

/**
 * Renders the right month grid for the calendar system.
 *
 * The Gregorian branch keeps propel's `Calendar` (react-day-picker) exactly as it is today, so the
 * 21 existing locales and every day-button accessible name are untouched. Only Persian gets the
 * custom grid. `getCalendarAdapter` already answers with the Gregorian adapter on a runtime whose
 * `Intl` has no Persian calendar, so an unsupported host degrades to the branch below rather than
 * rendering Persian month names over Gregorian dates.
 *
 * `month` / `onMonthChange` are required even though only the Persian branch reads them. Making the
 * visible month a controlled prop is what lets one component serve both branches; the Gregorian
 * branch simply keeps its own month internally, as it does today.
 */
/**
 * This package compiles with `exactOptionalPropertyTypes`, under which an absent prop and a prop
 * explicitly set to `undefined` are different types. `defined` turns an optional value into a
 * spread that is simply absent when it has nothing to pass, which is what both downstream
 * components expect.
 */
const defined = <T,>(key: string, value: T | undefined) => (value === undefined ? {} : { [key]: value });

export const CalendarSurface = (props: CalendarSurfaceProps) => {
  const {
    system,
    mode,
    value,
    range,
    onSelect,
    onRangeSelect,
    month,
    onMonthChange,
    defaultMonth,
    weekStartsOn,
    minDate,
    maxDate,
    showOutsideDays,
    disabled,
  } = props;

  const adapter = getCalendarAdapter(system);

  if (adapter.system === "gregorian") {
    // Mirrors the exact props the date pickers pass today, so the Gregorian branch is behaviourally
    // identical to the code it replaces — including react-day-picker's own `defaultMonth`
    // re-seeding every time the popover remounts it.
    if (mode === "range") {
      return (
        <Calendar
          mode="range"
          {...defined("selected", range?.from ? { from: range.from, to: range.to ?? undefined } : undefined)}
          {...defined("defaultMonth", range?.from ?? defaultMonth)}
          {...defined("disabled", buildDisabledMatchers(minDate, maxDate))}
          {...defined("showOutsideDays", showOutsideDays)}
          {...defined("weekStartsOn", weekStartsOn)}
          onSelect={(next) => onRangeSelect?.(next?.from ?? null, next?.to ?? null)}
        />
      );
    }
    return (
      <Calendar
        mode="single"
        {...defined("selected", value ?? undefined)}
        {...defined("defaultMonth", value ?? defaultMonth)}
        {...defined("disabled", buildDisabledMatchers(minDate, maxDate))}
        {...defined("showOutsideDays", showOutsideDays)}
        {...defined("weekStartsOn", weekStartsOn)}
        onSelect={(next) => onSelect(next ?? null)}
      />
    );
  }

  return (
    <PersianMonthGrid
      adapter={adapter}
      value={value}
      {...defined("range", range)}
      {...defined("onRangeSelect", onRangeSelect)}
      onSelect={onSelect}
      month={month}
      onMonthChange={onMonthChange}
      {...defined("weekStartsOn", weekStartsOn)}
      {...defined("minDate", minDate)}
      {...defined("maxDate", maxDate)}
      {...defined("disabled", disabled)}
    />
  );
};

CalendarSurface.displayName = "calendar.CalendarSurface";
