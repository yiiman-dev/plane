/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { getCalendarAdapter, resolveCalendarSystem } from "../src/adapters";
import type { CalendarAdapter } from "../src/types";

/**
 * Guards the contract the web app's clock helper depends on.
 *
 * `apps/web/helpers/calendar-display.ts` cannot be imported here — `@plane/calendar` has no path to
 * `apps/web`, and pointing one at it would create a dependency cycle (the reverse direction,
 * `@plane/utils` → `@plane/calendar`, is already avoided for this reason). So this test pins the
 * adapter property that helper reads instead: an adapter's `locale`/`system` pair must be a
 * combination `Intl.DateTimeFormat` accepts, because that pair is what makes a clock agree with the
 * adapter-rendered dates beside it.
 */
const clockThroughAdapter = (adapter: CalendarAdapter, date: Date, timeZone?: string): string =>
  new Intl.DateTimeFormat(adapter.locale, {
    timeZone,
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);

/**
 * `Intl` names the Gregorian calendar `"gregory"`, so forwarding `adapter.system` verbatim would
 * throw on every Gregorian render. This asserts the name really is wrong, so that removing the
 * option above cannot look like an oversight.
 */
describe("Intl calendar naming", () => {
  it("rejects the adapter's system string as a calendar name", () => {
    expect(() => new Intl.DateTimeFormat("en-US", { calendar: getCalendarAdapter("gregorian").system })).toThrow(
      RangeError
    );
  });
});

describe("adapter locale/system pairs drive clock formatting", () => {
  const afternoon = new Date(2025, 5, 15, 14, 30);

  it("keeps the Gregorian clock byte-identical to the en-US string it replaced", () => {
    // The component this replaced hardcoded "en-US" with these exact options, so a Persian user
    // saw an English clock. Anyone who never opted into Persian must see no change at all.
    expect(clockThroughAdapter(getCalendarAdapter("gregorian"), afternoon)).toBe("14:30");
  });

  it("renders the Persian clock with Persian digits, in the adapter's own calendar", () => {
    expect(clockThroughAdapter(getCalendarAdapter("persian"), afternoon)).toBe("۱۴:۳۰");
  });

  it("honours an explicit time zone in both systems", () => {
    const tokyo = "Asia/Tokyo";
    expect(clockThroughAdapter(getCalendarAdapter("gregorian"), afternoon, tokyo)).toBe("20:00");
    expect(clockThroughAdapter(getCalendarAdapter("persian"), afternoon, tokyo)).toBe("۲۰:۰۰");
  });

  it("renders midnight as hour zero rather than 24", () => {
    // The greeting component used to parse an `hour12: false` hour string, which yields "24" for
    // midnight in some locales and would have read as evening. The new helper reads `getHours()`,
    // so this only pins the clock itself staying 24-hour and zero-padded.
    expect(clockThroughAdapter(getCalendarAdapter("gregorian"), new Date(2025, 5, 15, 0, 5))).toBe("00:05");
    expect(clockThroughAdapter(getCalendarAdapter("persian"), new Date(2025, 5, 15, 0, 5))).toBe("۰۰:۰۵");
  });

  it("falls back to the Gregorian clock for an unknown system", () => {
    expect(clockThroughAdapter(getCalendarAdapter(resolveCalendarSystem("hijri")), afternoon)).toBe("14:30");
  });
});

describe("adapter locale/system pairs drive the greeting date line", () => {
  it("formats the short date and weekday through the adapter in both systems", () => {
    const date = new Date(2025, 5, 15);
    expect(getCalendarAdapter("gregorian").format(date, { month: "short", day: "numeric" })).toBe("Jun 15");
    expect(getCalendarAdapter("persian").format(date, { month: "short", day: "numeric" })).toBe("۲۵ خرداد");
  });
});
