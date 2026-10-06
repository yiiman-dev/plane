/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { differenceInCalendarDays, format } from "date-fns";
import { describe, expect, it, vi } from "vitest";
import { gregorianCalendar, persianCalendar } from "../src/adapters";
import { dayCellLabel } from "../src/picker/day-cell";
import { PersianMonthGrid } from "../src/picker/persian-month-grid";

const g = (year: number, monthIndex: number, day: number) => new Date(year, monthIndex, day);

/** The grid's aria-label for a day cell — the component's own builder, not a re-derivation. */
const labelFor = (date: Date) => dayCellLabel(date, persianCalendar);

const renderGrid = (props: Partial<ComponentProps<typeof PersianMonthGrid>> = {}) => {
  const onSelect = vi.fn();
  const onMonthChange = vi.fn();
  const result = render(
    <PersianMonthGrid
      adapter={persianCalendar}
      value={null}
      onSelect={onSelect}
      month={{ year: 1403, month: 6 }}
      onMonthChange={onMonthChange}
      weekStartsOn={6}
      {...props}
    />
  );
  return { ...result, onSelect, onMonthChange };
};

describe("PersianMonthGrid", () => {
  it("renders 42 day buttons", () => {
    renderGrid();
    // Every cell is a button carrying a full date label, plus the two month-stepping buttons.
    expect(screen.getAllByRole("button").length).toBeGreaterThanOrEqual(42);
  });

  it("labels days in Persian", () => {
    renderGrid();
    // 1 Shahrivar 1403 is 22 August 2024.
    expect(screen.getByRole("button", { name: labelFor(g(2024, 7, 22)) })).toBeTruthy();
  });

  it("calls onSelect with the Gregorian date for the clicked Persian day", async () => {
    const user = userEvent.setup();
    const { onSelect } = renderGrid();
    await user.click(screen.getByRole("button", { name: labelFor(g(2024, 7, 22)) }));
    expect(onSelect).toHaveBeenCalledTimes(1);
    const picked = onSelect.mock.calls[0][0] as Date;
    expect(picked.getFullYear()).toBe(2024);
    expect(picked.getMonth()).toBe(7);
    expect(picked.getDate()).toBe(22);
  });

  it("marks the selected day", () => {
    renderGrid({ value: g(2024, 7, 22) });
    // `aria-selected` sits on the `gridcell` wrapper, not the button — `aria-selected` is not a
    // valid attribute on `role="button"`, and `react-day-picker` puts it in the same place.
    const cell = screen.getByRole("gridcell", { selected: true });
    expect(cell.querySelector("button")?.getAttribute("aria-label")).toBe(labelFor(g(2024, 7, 22)));
  });

  it("steps to the next and previous month", async () => {
    const user = userEvent.setup();
    const { onMonthChange } = renderGrid();
    await user.click(screen.getByRole("button", { name: /next month/i }));
    expect(onMonthChange).toHaveBeenLastCalledWith({ year: 1403, month: 7 });
    await user.click(screen.getByRole("button", { name: /previous month/i }));
    expect(onMonthChange).toHaveBeenLastCalledWith({ year: 1403, month: 5 });
  });

  it("does not offer days outside minDate or maxDate", () => {
    renderGrid({ minDate: g(2024, 7, 20), maxDate: g(2024, 7, 25) });
    expect(screen.getByRole("button", { name: labelFor(g(2024, 7, 19)) }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: labelFor(g(2024, 7, 26)) }).hasAttribute("disabled")).toBe(true);
    expect(screen.getByRole("button", { name: labelFor(g(2024, 7, 22)) }).hasAttribute("disabled")).toBe(false);
  });

  it("selects a range across two clicks", async () => {
    const user = userEvent.setup();
    const onRangeSelect = vi.fn();
    renderGrid({ range: { from: null, to: null }, onRangeSelect });
    // 18 and 22 August 2024 are 5 and 1 Shahrivar 1403. Both are inside the grid but the first is a
    // padding cell from the previous month, so this also covers selecting across the boundary.
    await user.click(screen.getByRole("button", { name: labelFor(g(2024, 7, 18)) }));
    expect(onRangeSelect).toHaveBeenLastCalledWith(g(2024, 7, 18), null);
    await user.click(screen.getByRole("button", { name: labelFor(g(2024, 7, 22)) }));
    expect(onRangeSelect).toHaveBeenLastCalledWith(g(2024, 7, 18), g(2024, 7, 22));
  });

  it("moves focus with the arrow keys and steps months with PageDown", async () => {
    const user = userEvent.setup();
    const { onMonthChange } = renderGrid({ value: g(2024, 7, 22) });
    const cell = screen.getByRole("button", { name: labelFor(g(2024, 7, 22)) });
    cell.focus();
    await user.keyboard("{ArrowRight}");
    expect(document.activeElement?.getAttribute("aria-label")).toBe(labelFor(g(2024, 7, 23)));
    await user.keyboard("{PageDown}");
    expect(onMonthChange).toHaveBeenCalledWith({ year: 1403, month: 7 });
  });

  it("advances by one calendar day per cell, DST included", async () => {
    const user = userEvent.setup();
    const onRangeSelect = vi.fn();
    renderGrid({ range: { from: null, to: null }, onRangeSelect });
    // 1 Shahrivar 1403 is 22 August 2024. Clicking two adjacent cells reads their real instants
    // back out of the component, and the gap between them is asserted in *calendar* days rather
    // than hours: this host is `Asia/Tehran`, which has 33 DST transition days inside the
    // adapter's supported range where local midnight does not exist, so a cell pair straddling one
    // is 23 or 25 hours apart instead of 24. A strict hour-count assertion fails on those days
    // only, which makes it a flaky test rather than a sharper one.
    // One `gridcell` per day, which is what carries `data-in-month` (the button inside it is what
    // carries `data-focused`).
    const first = screen.getAllByRole("gridcell");
    expect(first).toHaveLength(42);
    await user.click(first[0]?.querySelector("button") as HTMLElement);
    await user.click(first[1]?.querySelector("button") as HTMLElement);
    const [from, to] = onRangeSelect.mock.lastCall as [Date, Date];
    expect(differenceInCalendarDays(to, from)).toBe(1);
    // `weekStartsOn: 6` (Saturday) and 1 Shahrivar 1403 falling on a Thursday means the grid opens
    // five padded days earlier, on 17 August 2024.
    expect(from.getDate()).toBe(17);
    expect(to.getDate()).toBe(18);
  });
});

describe("dayCellLabel", () => {
  it("matches react-day-picker's label byte for byte in Gregorian mode", () => {
    // `react-day-picker`'s default `labelDayButton` is `format(date, "PPPP")`. `packages/blocks`'
    // date-picker tests locate day buttons by strings like "June 15th, 2025", so this grid's labels
    // have to be the same string or those queries stop matching once this grid is wired in.
    // Checked against the real `date-fns` call rather than a literal, so the assertion breaks if
    // either side moves.
    for (const date of [new Date(2025, 5, 15), new Date(2025, 5, 1), new Date(2024, 7, 22), new Date(2025, 0, 1)]) {
      expect(dayCellLabel(date, gregorianCalendar)).toBe(format(date, "PPPP"));
    }
    // The string itself, so a failure here says what changed.
    expect(dayCellLabel(new Date(2025, 5, 15), gregorianCalendar)).toBe("Sunday, June 15th, 2025");
  });
});
