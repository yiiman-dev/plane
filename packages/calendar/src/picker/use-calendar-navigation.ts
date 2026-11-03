/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { KeyboardEvent } from "react";
import { useCallback, useMemo } from "react";
import { addDays } from "date-fns";
import type { CalendarAdapter, CalendarMonthParts } from "../types";

/** Days of movement per arrow key, in grid cells rather than days. */
const ARROW_KEYS: Record<string, number> = {
  ArrowLeft: -1,
  ArrowRight: 1,
  ArrowUp: -7,
  ArrowDown: 7,
};

/** Years offered in the jump dropdown, centred on the visible year. */
const YEAR_WINDOW_RADIUS = 10;

type Args = {
  adapter: CalendarAdapter;
  month: CalendarMonthParts;
  onMonthChange: (month: CalendarMonthParts) => void;
  /** The currently focused day, so keyboard moves stay on the grid rather than jumping months. */
  focused: Date;
  onFocusedChange: (date: Date) => void;
  /** 0 = Sunday … 6 = Saturday, the same numbering the adapter's grid takes. */
  weekStartsOn: number;
};

/**
 * Month stepping and keyboard movement for a month grid. Navigation rules live here rather than in
 * the grid component so they can be reasoned about (and later unit-tested) without a DOM walk.
 *
 * The visible month is *not* mirrored into local state: `month` is the single source of truth and
 * the parent is expected to feed the value back through `onMonthChange`. A local mirror is worse
 * than useless here — stepping back from a month the parent has not adopted yet would step from the
 * mirror rather than from what is on screen, so two "previous month" clicks would skip two months.
 */
export const useCalendarNavigation = ({
  adapter,
  month,
  onMonthChange,
  focused,
  onFocusedChange,
  weekStartsOn,
}: Args) => {
  /** Steps the visible month, always relative to the month the parent last handed down. */
  const step = useCallback(
    (delta: number) => onMonthChange(adapter.addMonths(month, delta)),
    [adapter, month, onMonthChange]
  );

  /** Moves the focused day by `delta` days and follows it into an adjacent month when it leaves. */
  const moveFocus = useCallback(
    (delta: number) => {
      const next = addDays(focused, delta);
      onFocusedChange(next);
      const parts = adapter.toParts(next);
      if (parts.year !== month.year || parts.month !== month.month) {
        onMonthChange({ year: parts.year, month: parts.month });
      }
    },
    [adapter, focused, month, onFocusedChange, onMonthChange]
  );

  /**
   * Cells between `focused` and the first cell of its row, given the grid's week start. Home and
   * End land on the *visible* row edge, which is not Sunday/Saturday unless the grid happens to
   * start the week there — so this cannot be hardcoded the way a Sunday-first grid can.
   */
  const offsetIntoWeek = useCallback((date: Date) => (date.getDay() - weekStartsOn + 7) % 7, [weekStartsOn]);

  /** Handles a key press, returning true when it was consumed so the caller can preventDefault. */
  const handleKeyDown = useCallback(
    (event: KeyboardEvent): boolean => {
      if (event.key in ARROW_KEYS) {
        moveFocus(ARROW_KEYS[event.key]);
        return true;
      }
      if (event.key === "PageDown") {
        step(1);
        return true;
      }
      if (event.key === "PageUp") {
        step(-1);
        return true;
      }
      if (event.key === "Home") {
        moveFocus(-offsetIntoWeek(focused));
        return true;
      }
      if (event.key === "End") {
        moveFocus(6 - offsetIntoWeek(focused));
        return true;
      }
      return false;
    },
    [focused, moveFocus, offsetIntoWeek, step]
  );

  const years = useMemo(
    () => Array.from({ length: YEAR_WINDOW_RADIUS * 2 + 1 }, (_, index) => month.year - YEAR_WINDOW_RADIUS + index),
    [month.year]
  );

  return { step, moveFocus, handleKeyDown, years };
};
