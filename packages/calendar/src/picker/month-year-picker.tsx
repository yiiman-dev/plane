/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { CalendarAdapter, CalendarMonthParts } from "../types";

type Props = {
  adapter: CalendarAdapter;
  month: CalendarMonthParts;
  years: number[];
  onChange: (month: CalendarMonthParts) => void;
};

/**
 * The month and year jump controls shown above the grid.
 *
 * Native `<select>` rather than the shared `Select`: this is a two-field utility inside a popover
 * that is already open, so it needs no portal, no positioning, and no search. A native control also
 * gets the platform's own RTL and Persian-digit rendering for free, which matters as soon as the
 * app turns RTL.
 *
 * Month values are the adapter's own 1-based numbering, so the `<option>` index is the month — the
 * same numbering `toParts` and `addMonths` use.
 */
export const MonthYearPicker = ({ adapter, month, years, onChange }: Props) => {
  const months = adapter.getMonthNames("long");
  return (
    <div className="flex items-center gap-2 px-1 pb-2">
      <select
        aria-label="Month"
        value={month.month}
        onChange={(event) => onChange({ ...month, month: Number(event.target.value) })}
        className="rounded-md border border-subtle bg-surface-1 px-2 py-1 text-11"
      >
        {months.map((name, index) => (
          <option key={name} value={index + 1}>
            {name}
          </option>
        ))}
      </select>
      <select
        aria-label="Year"
        value={month.year}
        onChange={(event) => onChange({ ...month, year: Number(event.target.value) })}
        className="rounded-md border border-subtle bg-surface-1 px-2 py-1 text-11"
      >
        {years.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>
    </div>
  );
};

MonthYearPicker.displayName = "calendar.MonthYearPicker";
