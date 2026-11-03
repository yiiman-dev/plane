# Persian Calendar — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The issue calendar layout, the Gantt chart, and the chart axis labels render in the user's chosen calendar instead of hardcoded English.

**Architecture:** Extend the existing `CalendarAdapter` (from phase 1) rather than replacing it. The calendar layout's grid generator gains a `CalendarSystem` parameter and asks the adapter for month length, month-start weekday, and month/weekday names instead of reading Gregorian fields off a `Date`. Gantt and the chart axis thread a system through their existing parameter chains the way `startOfWeek` already flows.

**Tech Stack:** TypeScript, the existing `@plane/calendar` package, vitest 4 (`packages/calendar` is the only viable test host — see the constraint below), `date-fns` for the arithmetic that genuinely stays Gregorian.

**Spec:** `docs/superpowers/specs/2026-09-30-persian-calendar-design.md` §2

## Corrections to the phase-1 spec

Phase 2 was planned from `docs/superpowers/specs/2026-09-30-persian-calendar-design.md` §2. Investigation found **three claims in that spec are wrong**. This plan follows the code, not the spec:

1. **"The layout already uses a fixed 6-row grid" — false.** `packages/utils/src/calendar.ts:44` computes a _variable_ 4–6 rows: `Math.ceil((totalDaysInMonth + firstDayOfMonth) / 7)`. Persian months are 29–31 days, so the row count still varies; the layout's height already changes month to month and that is not new. The adapter's fixed-42 `getMonthGrid` is a separate code path the layout does not use. **Do not "fix" this to 42** — that would change the layout's behaviour for every existing user.

2. **"The grid is generated in the calendar layout" — false.** It is generated in `packages/utils/src/calendar.ts` (`generateCalendarData`), and that same offset math is **duplicated** in `apps/web/store/issue/issue_calendar_view.store.ts:138-144` to locate a week by index. Both must change together or the week layout breaks.

3. **"Only labels need changing" — false.** Four independent places hardcode the weekend to Sat/Sun, and `apps/web/components/gantt-chart/chart/views/week.tsx:86` detects it by comparing **English strings**: `["sat", "sun"].includes(weekDay?.dayData?.shortTitle)`. That breaks the moment Persian weekday names are used.

## Global Constraints

- **Storage stays Gregorian.** No change to any API payload, filter, or the `yyyy-MM-dd` keys in the calendar payload. `renderFormattedPayloadDate` remains non-calendar-aware.
- **`apps/web` has no test runner** — no `test` script, no vitest/jest dependency, zero test files. Every test in this plan lives in `packages/calendar/tests/`, following the precedent documented in `packages/calendar/tests/locale-leak.test.ts:12-19`: pin the adapter property the web code relies on, rather than importing from `apps/web` (which would create a dependency cycle).
- **Gregorian output must be byte-identical.** `MONTHS_LIST`, `DAYS_LIST`, and the Gantt tables produce today's strings for the Gregorian path. Pin each one with a test before changing the code that reads them.
- **Do not add a dependency to any `package.json`.** A previous task created a turbo build cycle this way and it broke the web Docker build. `apps/web` reaching calendar logic must go through `@plane/blocks` (which already re-exports `getCalendarAdapter`), matching `apps/web/helpers/calendar-display.ts`.
- **`Intl` names the Gregorian calendar `"gregory"`, not `"gregorian"`.** Passing `calendar: adapter.system` throws `RangeError` and crashes the render — a bug phase 1 already hit. The Persian locale tag `fa-IR-u-ca-persian` already carries the calendar, so omit the option.
- **Every source file starts with the AGPL header.**
- **Do not stage** `apps/web/app/routes/core.ts` or `apps/web/app/routes/persian-preview/` — those are preview scaffolding, already committed, and out of scope here.
- **Run `pnpm install`** after any `package.json` change (there should be none).

---

## File Structure

**Modified:**

| Path                                                                              | Change                                                                                                                        |
| --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `packages/utils/src/calendar.ts`                                                  | `generateCalendarData` takes a `CalendarSystem`; month length, month-start weekday, and month/day names come from the adapter |
| `apps/web/store/issue/issue_calendar_view.store.ts`                               | Pass the system to the generator; mirror the offset math; regenerate on `calendar_system` change                              |
| `apps/web/components/issues/issue-layouts/calendar/dropdowns/months-dropdown.tsx` | Month names + navigation from the adapter; remove the `new Date(y, index, 1)` trick                                           |
| `apps/web/components/issues/issue-layouts/calendar/day-tile.tsx`                  | Month marker on the calendar's day 1, not `getDate() === 1`; weekend from the adapter                                         |
| `apps/web/components/issues/issue-layouts/calendar/week-header.tsx`               | Weekday names from the adapter                                                                                                |
| `apps/web/components/issues/issue-layouts/calendar/calendar.tsx`                  | The two duplicated month-title sites                                                                                          |
| `apps/web/components/issues/issue-layouts/calendar/week-days.tsx`                 | Weekend filter from the adapter                                                                                               |
| `apps/web/components/gantt-chart/data/index.ts`                                   | `weeks`/`months`/`quarters` become adapter-backed                                                                             |
| `apps/web/components/gantt-chart/views/week-view.ts`                              | Thread the system; stop building titles from English strings                                                                  |
| `apps/web/components/gantt-chart/views/month-view.ts`                             | Same                                                                                                                          |
| `apps/web/components/gantt-chart/views/quarter-view.ts`                           | Same; Persian seasons instead of Q1–Q4                                                                                        |
| `apps/web/components/gantt-chart/views/helpers.ts`                                | Month length from the adapter                                                                                                 |
| `apps/web/components/gantt-chart/chart/root.tsx`                                  | Read `calendarSystem` and pass it down (the single funnel)                                                                    |
| `apps/web/components/gantt-chart/chart/views/week.tsx`                            | **Weekend detection must stop comparing `"sat"`/`"sun"`**                                                                     |
| `apps/web/components/chart/utils.ts`                                              | Thread the system; Persian year comparison; `Week`/`None` literals                                                            |
| `apps/web/components/analytics/work-items/created-vs-resolved.tsx`                | Pass the system                                                                                                               |
| `apps/web/components/core/sidebar/progress-chart.tsx`                             | Pass the system                                                                                                               |

**Not modified (deliberately):**

| Path                                        | Why                                                                                                              |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `packages/constants/src/calendar.ts`        | `MONTHS_LIST`/`DAYS_LIST` stay as the Gregorian source of truth; phase 1 pinned their shape                      |
| `apps/web/hooks/use-timezone-converter.tsx` | Its `"en-US"` is a timezone-shift shim, not a display formatter — `en-US` is required there for parseable output |
| `packages/constants/src/profile.ts`         | Settings UI, not a calendar view                                                                                 |

---

## Task 1: A calendar-agnostic month/weekday label source

**Files:**

- Create: `packages/calendar/src/labels.ts`
- Create: `packages/calendar/tests/labels.test.ts`
- Modify: `packages/calendar/src/index.ts`

**Interfaces:**

- Consumes: `CalendarAdapter`, `CalendarSystem` from Task 1 of phase 1
- Produces: the two functions every later task uses, exported from `@plane/calendar`:

  ```ts
  /** A month name for display. `style` is "long" | "short" | "narrow". */
  monthName(adapter: CalendarAdapter, month: number, style?: "long" | "short" | "narrow"): string
  /** 7 weekday names rotated so index 0 is `weekStartsOn` (0 = Sunday). */
  weekdayNames(adapter: CalendarAdapter, style?: "long" | "short" | "narrow", weekStartsOn?: number): string[]
  /** Whether a `Date` falls on a weekend, per the adapter's calendar rather than a Sat/Sun literal. */
  isWeekend(date: Date, weekStartsOn?: number): boolean
  ```

- [ ] **Step 1: Write the failing test**

`packages/calendar/tests/labels.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { gregorianCalendar, persianCalendar } from "../src/adapters";
import { isWeekend, monthName, weekdayNames } from "../src/labels";

const g = (year: number, monthIndex: number, day: number) => new Date(year, monthIndex, day);

describe("monthName", () => {
  it("is 1-based, matching the adapter's toParts", () => {
    expect(monthName(gregorianCalendar, 1)).toBe("January");
    expect(monthName(gregorianCalendar, 12)).toBe("December");
  });

  it("returns the Gregorian short form unchanged", () => {
    // packages/constants/src/calendar.ts MONTHS_LIST shortTitle — the layout's current output.
    expect(monthName(gregorianCalendar, 1, "short")).toBe("Jan");
    expect(monthName(gregorianCalendar, 6, "short")).toBe("Jun");
  });

  it("returns Persian month names", () => {
    expect(monthName(persianCalendar, 1)).toBe("فروردین");
    expect(monthName(persianCalendar, 6)).toBe("شهریور");
    expect(monthName(persianCalendar, 12)).toBe("اسفند");
  });
});

describe("weekdayNames", () => {
  it("matches DAYS_LIST short titles in the Gregorian path", () => {
    // packages/constants/src/calendar.ts DAYS_LIST is 1-based with value 0..6.
    expect(weekdayNames(gregorianCalendar, "short", 0)).toEqual(["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]);
  });

  it("rotates to match weekStartsOn", () => {
    expect(weekdayNames(gregorianCalendar, "short", 1)[0]).toBe("Mon");
    expect(weekdayNames(gregorianCalendar, "short", 6)[0]).toBe("Sat");
  });

  it("returns Persian weekday names", () => {
    const names = weekdayNames(persianCalendar, "long", 6);
    expect(names).toHaveLength(7);
    expect(names[0]).toBe("شنبه");
  });
});

describe("isWeekend", () => {
  it("treats Saturday and Sunday as the Gregorian weekend", () => {
    // 2025-06-14 Sat, 2025-06-15 Sun, 2025-06-16 Mon
    expect(isWeekend(g(2025, 5, 14), 0)).toBe(true);
    expect(isWeekend(g(2025, 5, 15), 0)).toBe(true);
    expect(isWeekend(g(2025, 5, 16), 0)).toBe(false);
  });

  it("is rotation-aware, not a hardcoded Sat/Sun literal", () => {
    // The whole point: the Iranian weekend is Thu/Fri, which this must be able to express.
    // With a Friday-start week, Friday and Saturday are the weekend.
    expect(isWeekend(g(2025, 5, 13), 5)).toBe(true); // Friday
    expect(isWeekend(g(2025, 5, 14), 5)).toBe(true); // Saturday
    expect(isWeekend(g(2025, 5, 15), 5)).toBe(false); // Sunday
  });

  it("does not read the day's index off the Gregorian week convention", () => {
    // 2024-08-22 is a Thursday in the Persian calendar's terms, and a Thursday regardless of
    // calendar system — the point is that the answer depends on weekStartsOn, not on a literal.
    expect(isWeekend(g(2024, 7, 22), 0)).toBe(false);
    expect(isWeekend(g(2024, 7, 22), 4)).toBe(true);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: FAIL — `Cannot find module '../src/labels'`

- [ ] **Step 3: Write the implementation**

`packages/calendar/src/labels.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { CalendarAdapter } from "./types";

/**
 * A month name for display.
 *
 * `month` is **1-based**, matching what `adapter.toParts` reports — the same convention the whole
 * adapter contract uses. The 0-based `Date.getMonth()` used to index `MONTHS_LIST` is a different
 * number space, and conflating the two is the classic off-by-one in this area.
 */
export const monthName = (
  adapter: CalendarAdapter,
  month: number,
  style: "long" | "short" | "narrow" = "long"
): string => adapter.getMonthNames(style)[month - 1] ?? "";

/**
 * 7 weekday names, rotated so index 0 is `weekStartsOn` (0 = Sunday). Callers that render a column
 * per weekday use this directly instead of rotating `DAYS_LIST` themselves.
 */
export const weekdayNames = (
  adapter: CalendarAdapter,
  style: "long" | "short" | "narrow" = "short",
  weekStartsOn = 0
): string[] => adapter.getWeekdayNames(style, weekStartsOn);

/**
 * The two days at the end of the user's week.
 *
 * This exists because four call sites hardcode `[0, 6].includes(date.getDay())` — Saturday/Sunday —
 * and one of them compares the English strings `"sat"` / `"sun"`. An Iranian week ends on Friday,
 * so the weekend is a function of `weekStartsOn`, not a constant.
 */
export const isWeekend = (date: Date, weekStartsOn = 0): boolean => {
  // `getDay()` is 0 = Sunday. Position within the user's week is 0..6, so the last two positions
  // are the weekend regardless of which day the week starts on.
  const positionInWeek = (date.getDay() - weekStartsOn + 7) % 7;
  return positionInWeek >= 5;
};
```

- [ ] **Step 4: Export from the package index**

Append to `packages/calendar/src/index.ts` — **append, do not rewrite**; a later task appends again:

```ts
export * from "./labels";
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: PASS — the three `describe` blocks pass. `@plane/calendar` goes from 90 tests to 96.

- [ ] **Step 6: Commit**

```bash
git add packages/calendar
git commit -m "feat(calendar): add adapter-backed month, weekday, and weekend labels"
```

---

## Task 2: Make the calendar grid generator calendar-aware

**Files:**

- Modify: `packages/utils/src/calendar.ts:20-76` (`generateCalendarData`)
- Create: `packages/calendar/tests/calendar-grid.test.ts`

**Interfaces:**

- Consumes: `getCalendarAdapter`, `resolveCalendarSystem` from `@plane/calendar`; `CalendarSystem` type
- Produces:

  ```ts
  // packages/utils/src/calendar.ts
  export const generateCalendarData = (
    currentStructure: ICalendarPayload | null,
    startDate: Date,
    startOfWeek: number,
    system?: CalendarSystem            // appended, defaults to "gregorian"
  ): ICalendarPayload
  ```

  Every existing caller passes three arguments and is unaffected.

- [ ] **Step 1: Write the failing test**

`packages/calendar/tests/calendar-grid.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { generateCalendarData } from "@plane/utils";
import { persianCalendar } from "../src/adapters";

const fromPersian = (y: number, m: number, d: number) => persianCalendar.fromParts(y, m, d);

describe("generateCalendarData", () => {
  it("is byte-identical in Gregorian when no system is passed", () => {
    const payload = generateCalendarData(null, new Date(2025, 5, 1), 0);
    const month = payload["y-2025"]["m-5"];
    const weeks = Object.keys(month).sort();
    expect(weeks).toHaveLength(5); // June 2025 has 5 weeks from a Sunday start
    // Keys stay Gregorian yyyy-MM-dd — they are API payload, not display.
    const firstDay = Object.keys(month[weeks[0]])[0];
    expect(firstDay).toMatch(/^2025-06-/);
    // Each cell keeps a Gregorian Date.
    expect(month[weeks[0]][firstDay].date.getMonth()).toBe(5);
  });

  it("produces a Persian month when asked", () => {
    const payload = generateCalendarData(null, fromPersian(1403, 6, 1), 6, "persian");
    // 1 Shahrivar 1403 is 22 August 2024.
    const month = payload["y-2024"]["m-7"];
    expect(month).toBeDefined();
    const days = Object.values(month).flatMap((w) => Object.keys(w));
    expect(days).toContain("2024-08-22");
  });

  it("uses the Persian month length, so Shahrivar has 31 cells not 30", () => {
    const payload = generateCalendarData(null, fromPersian(1403, 6, 1), 6, "persian");
    const month = payload["y-2024"]["m-7"];
    const inMonth = Object.values(month)
      .flatMap((w) => Object.values(w))
      .filter((c) => c.date.getMonth() === 7 && c.date.getFullYear() === 2024);
    // Gregorian August has 31 days, and so does Shahrivar — the point is the generator reads the
    // Persian length (31), not a Gregorian table lookup keyed by the Persian month index.
    expect(inMonth.length).toBe(31);
  });

  it("handles the leap Esfand, which is 30 days", () => {
    const payload = generateCalendarData(null, fromPersian(1403, 12, 1), 6, "persian");
    // Esfand 1403 runs 20 Feb – 21 Mar 2024, crossing into March.
    const all = Object.values(payload)
      .flatMap((y) => Object.values(y))
      .flatMap((m) => Object.values(m));
    const esfandDays = all
      .flatMap((w) => Object.values(w))
      .filter((c) => {
        const t = c.date.getTime();
        return t >= new Date(2024, 1, 20).getTime() && t <= new Date(2024, 2, 21).getTime();
      });
    expect(esfandDays.length).toBe(30);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: FAIL on the Persian cases — the generator ignores the fourth argument, so a Persian month resolves to the wrong Gregorian month bucket.

- [ ] **Step 3: Rewrite `generateCalendarData`**

In `packages/utils/src/calendar.ts`, add the imports:

```ts
import { getCalendarAdapter, resolveCalendarSystem } from "@plane/calendar";
import type { CalendarSystem } from "@plane/calendar";
```

Replace the body of `generateCalendarData` so every Gregorian-specific read comes from the adapter:

```ts
export const generateCalendarData = (
  currentStructure: ICalendarPayload | null,
  startDate: Date,
  startOfWeek: number,
  system: CalendarSystem = "gregorian"
): ICalendarPayload => {
  const adapter = getCalendarAdapter(resolveCalendarSystem(system));

  // The first of the calendar month, which is what the layout pages between.
  const monthStart = adapter.getMonthStart(adapter.toParts(startDate));
  const parts = adapter.toParts(monthStart);

  const totalDaysInMonth = adapter.getMonthLength(parts.year, parts.month);
  // Position of the 1st within the user's week: 0..6.
  const firstDayOfMonth = (monthStart.getDay() - startOfWeek + 7) % 7;

  const calendarData: ICalendarPayload = currentStructure ?? {};

  const yearKey = `y-${parts.year}`;
  const monthKey = `m-${parts.month}`;
  calendarData[yearKey] ||= {};
  calendarData[yearKey][monthKey] = {};

  // Row count still varies 4-6. Persian months are 29-31 days, the same envelope as Gregorian, so
  // the layout's behaviour is unchanged; it is deliberately NOT forced to a fixed 6 rows.
  const numWeeks = Math.ceil((totalDaysInMonth + firstDayOfMonth) / 7);

  for (let week = 0; week < numWeeks; week++) {
    const currentWeekObject: ICalendarWeek = {};
    const weekNumber = getWeekNumberOfDate(monthStart);

    for (let i = 0; i < 7; i++) {
      const dayNumber = week * 7 + i - firstDayOfMonth;
      const date = new Date(monthStart);
      date.setDate(date.getDate() + dayNumber + 1);

      // Still Gregorian: these keys go into API requests.
      const formattedDatePayload = renderFormattedPayloadDate(date);

      currentWeekObject[formattedDatePayload] = {
        date,
        // The Date's own Gregorian parts, so `ICalendarDate` keeps its existing meaning.
        year: date.getFullYear(),
        month: date.getMonth(),
        day: date.getDate(),
        week: weekNumber,
        ...
      };
    }
    calendarData[yearKey][monthKey][`w-${week}`] = currentWeekObject;
  }
  return calendarData;
};
```

Keep the existing field values for `is_current_month`, `is_current_week`, and `is_today` **semantically unchanged**. For `is_current_month`, compare against the adapter's parts rather than `date.getMonth() === month` — in Persian mode `month` is 1-based Persian and `date.getMonth()` is 0-based Gregorian, so the old comparison is silently wrong.

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: PASS — all four cases. `@plane/calendar` goes from 96 to 100.

- [ ] **Step 5: Verify nothing else broke**

Run: `pnpm --filter=@plane/blocks test && pnpm --filter=@plane/services test`
Expected: PASS — 277 and 13. Neither calls the generator, but confirm.

Run: `npx turbo run check:types`
Expected: 28/28.

- [ ] **Step 6: Commit**

```bash
git add packages/utils packages/calendar
git commit -m "feat(utils): make the calendar grid generator calendar-aware"
```

---

## Task 3: Thread the system through the calendar view store

**Files:**

- Modify: `apps/web/store/issue/issue_calendar_view.store.ts:77-85, 136-144, 184-214`

**Interfaces:**

- Consumes: the `generateCalendarData` from Task 2; `useUserProfile` pattern already in the file
- Produces: no new exports. The store now regenerates on `calendar_system` as well as `start_of_the_week`.

- [ ] **Step 1: Extend the existing reaction**

In the constructor, the reaction at `:78-85` currently watches `start_of_the_week`. Widen it so a calendar change also rebuilds:

```ts
reaction(
  () => {
    const data = this.rootStore.rootStore.user.userProfile.data;
    // Both feed grid construction, so both must rebuild it. Reading two fields inside one
    // reaction is deliberate: MobX tracks every observable touched during evaluation.
    return [data?.start_of_the_week, data?.calendar_system] as const;
  },
  () => {
    this.regenerateCalendar();
  }
);
```

- [ ] **Step 2: Fix the duplicated offset math**

`allDaysOfActiveWeek` at `:136-144` reproduces the generator's offset math. It must use the same adapter-driven numbers or the week layout will read the wrong week:

```ts
const adapter = getCalendarAdapter(resolveCalendarSystem(calendarSystem));
const monthStart = adapter.getMonthStart(adapter.toParts(activeMonthDate));
const totalDaysInMonth = adapter.getMonthLength(adapter.toParts(monthStart).year, adapter.toParts(monthStart).month);
const firstDayOfMonthRaw = monthStart.getDay();
const firstDayOfMonth = (firstDayOfMonthRaw - startOfWeek + 7) % 7;
```

Where `calendarSystem` comes from `this.rootStore?.rootStore?.user?.userProfile?.calendarSystem`, matching the narrowed getter phase 1 added. Note this store reads `userProfile.data?.start_of_the_week` at `:137` today; use the same source for the system to avoid two different shapes.

- [ ] **Step 3: Pass the system at the three call sites**

`:184` (`updateCalendarPayload`), `:192` (`initCalendar`), and `:209` (`regenerateCalendar`) all call `generateCalendarData`. Append the system argument to each:

```ts
const newCalendarPayload = generateCalendarData(null, activeMonthDate, startOfWeek, calendarSystem);
```

- [ ] **Step 4: Verify**

Run: `npx turbo run check:types`
Expected: 28/28.

Run: `pnpm --filter=@plane/blocks test && pnpm --filter=@plane/calendar test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/web/store/issue/issue_calendar_view.store.ts
git commit -m "feat(web): thread the calendar system through the calendar view store"
```

---

## Task 4: Calendar layout labels

**Files:**

- Modify: `apps/web/components/issues/issue-layouts/calendar/dropdowns/months-dropdown.tsx:14, 47-55, 71-73, 83-116`
- Modify: `apps/web/components/issues/issue-layouts/calendar/day-tile.tsx:20, 138-141, 160`
- Modify: `apps/web/components/issues/issue-layouts/calendar/week-header.tsx:10, 27`
- Modify: `apps/web/components/issues/issue-layouts/calendar/calendar.tsx:27, 210, 238`
- Modify: `apps/web/components/issues/issue-layouts/calendar/week-days.tsx:79-80`
- Create: `packages/calendar/tests/calendar-layout-labels.test.ts`

**Interfaces:**

- Consumes: `monthName`, `weekdayNames`, `isWeekend` (Task 1); `getCalendarAdapter` (phase 1, re-exported through `@plane/blocks/property-select` — `apps/web` has no direct dependency on `@plane/calendar`)
- Produces: no new exports.

- [ ] **Step 1: Write the test**

The layout components cannot be imported from a test (no runner in `apps/web`, and importing them would cross the package boundary). Follow the precedent in `packages/calendar/tests/locale-leak.test.ts:12-19` and pin the _contract the layout depends on_ — that `monthName`/`weekdayNames` reproduce the exact strings `MONTHS_LIST`/`DAYS_LIST` currently produce, so the Gregorian path is provably unchanged:

`packages/calendar/tests/calendar-layout-labels.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { MONTHS_LIST, DAYS_LIST } from "@plane/constants";
import { gregorianCalendar } from "../src/adapters";
import { isWeekend, monthName, weekdayNames } from "../src/labels";

/**
 * The calendar layout read `MONTHS_LIST` / `DAYS_LIST` directly. These assertions pin the adapter's
 * output against those tables so replacing the constants with adapter calls is a no-op for
 * Gregorian users — which is the whole safety claim for this task.
 */
describe("layout labels are unchanged for Gregorian", () => {
  it("monthName reproduces every MONTHS_LIST title and shortTitle", () => {
    for (let month = 1; month <= 12; month++) {
      expect(monthName(gregorianCalendar, month, "long")).toBe(MONTHS_LIST[month].title);
      expect(monthName(gregorianCalendar, month, "short")).toBe(MONTHS_LIST[month].shortTitle);
    }
  });

  it("weekdayNames reproduces every DAYS_LIST shortTitle", () => {
    // DAYS_LIST is 1-based with an `EStartOfTheWeek` value of 0..6; weekdayNames is 0-based
    // rotated by weekStartsOn, so order by `.value`.
    const expected = Object.values(DAYS_LIST)
      .sort((a, b) => a.value - b.value)
      .map((d) => d.shortTitle);
    expect(weekdayNames(gregorianCalendar, "short", 0)).toEqual(expected);
  });

  it("isWeekend matches the Sat/Sun literal it replaces, for every weekday", () => {
    // 2025-06-15 is a Sunday, so +0..+6 walks the whole week.
    for (let offset = 0; offset < 7; offset++) {
      const date = new Date(2025, 5, 15 + offset);
      const day = date.getDay();
      expect(isWeekend(date, 0)).toBe(day === 0 || day === 6);
    }
  });
});
```

- [ ] **Step 2: Run the test**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: PASS immediately if `labels.ts` is correct — this test is a **regression pin**, not a failing test. If it fails, `labels.ts` or the constants disagree; fix the implementation, never the expectation.

- [ ] **Step 3: Rewrite `months-dropdown.tsx`**

This file is the main label site and also contains the `new Date(y, index, 1)` bug. Replace the `MONTHS_LIST` import with the adapter calls and fix navigation:

```ts
const { calendarSystem } = useUserProfile();
const adapter = getCalendarAdapter(resolveCalendarSystem(calendarSystem));
```

- The **trigger label** at `:71-73`:
  ```ts
  {
    calendarLayout === "month"
      ? `${monthName(adapter, adapter.toParts(activeMonthDate).month)} ${adapter.toParts(activeMonthDate).year}`
      : getWeekLayoutHeader();
  }
  ```
- The **week-range title** at `:34-57`: replace `MONTHS_LIST[firstDay.getMonth() + 1].title` with `monthName(adapter, adapter.toParts(firstDay).month)`. Note `getWeekLayoutHeader`'s `firstDay.getMonth() === lastDay.getMonth()` comparison must compare **adapter parts**, not Gregorian month indexes — in Persian mode two dates can share a Gregorian month and differ in Persian month.
- The **year arrows** at `:83-100`: `new Date(activeMonthDate.getFullYear() - 1, activeMonthDate.getMonth(), 1)` mixes a Gregorian year with a month index and will land on the wrong month in Persian. Replace with:
  ```ts
  const parts = adapter.toParts(activeMonthDate);
  const previousYear = adapter.getMonthStart({ year: parts.year - 1, month: parts.month });
  const nextYear = adapter.getMonthStart({ year: parts.year + 1, month: parts.month });
  ```
- The **month grid buttons** at `:102-116`: `new Date(activeMonthDate.getFullYear(), index, 1)` uses `index` (0-based) as a Gregorian month while `MONTHS_LIST` is 1-based. Replace:
  ```ts
  {adapter.getMonthNames("short").map((name, index) => (
    <button key={name} onClick={() => handleDateChange(adapter.fromParts(activeParts.year, index + 1, 1))}>
      {name}
    </button>
  ))}
  ```
- The hardcoded `"Week view"` fallbacks at `:37` and `:44` should use the i18n key the repo already has rather than an English literal. Search for an existing `common.*week*` key; if none fits, leave the literal and note it — do not invent a translation.

- [ ] **Step 4: Rewrite `week-header.tsx`**

`:27` sorts `Object.values(DAYS_LIST)` by `.value`. Replace the source, keeping the rotation:

```ts
const { data: userProfile } = useUserProfile();
const adapter = getCalendarAdapter(resolveCalendarSystem(userProfile?.calendar_system));
const orderedDays = adapter.getWeekdayNames("short", startOfWeek);
```

`week-header.tsx` also hardcodes the weekend at `:39-40` via `EStartOfTheWeek.SUNDAY/SATURDAY`. Replace that check with `isWeekend(date, startOfWeek)` from Task 1.

- [ ] **Step 5: Rewrite `day-tile.tsx`**

- `:141` `const isWeekend = [0, 6].includes(date.date.getDay());` shadows the imported helper name. Replace the body with `isWeekendDay(date.date, startOfWeek)` where `startOfWeek` comes from `useUserProfile`, and import the helper under a non-shadowing alias.
- `:160` `date.date.getDate() === 1 && MONTHS_LIST[date.date.getMonth() + 1].shortTitle + " "` marks the first day of a month. In Persian mode the marker must fire on the Persian month boundary, so compare `adapter.toParts(date.date).day === 1` and name it with `monthName(adapter, parts.month, "short")`.

- [ ] **Step 6: Rewrite `week-days.tsx` and `calendar.tsx`**

- `week-days.tsx:79-80` `return !(day === 0 || day === 6);` → `return !isWeekend(date, startOfWeek)`.
- `calendar.tsx:210` and `:238` are the same month-title template duplicated verbatim. Replace both with `monthName(adapter, parts.month)` and, if they remain identical, hoist one into a small local component rather than editing the template twice.

- [ ] **Step 7: Verify**

Run: `npx turbo run check:types`
Expected: 28/28.

Run: `pnpm --filter=@plane/calendar test && pnpm --filter=@plane/blocks test`
Expected: PASS — 102 and 277.

Run: `npx turbo run check:lint`
Expected: 16/16.

- [ ] **Step 8: Commit**

```bash
git add apps/web/components/issues/issue-layouts/calendar packages/calendar
git commit -m "feat(web): render the issue calendar layout in the user's calendar"
```

---

## Task 5: Gantt weekday/month/quarter tables

**Files:**

- Modify: `apps/web/components/gantt-chart/data/index.ts:12-47`
- Modify: `apps/web/components/gantt-chart/chart/views/week.tsx:86`
- Create: `packages/calendar/tests/gantt-labels.test.ts`

**Interfaces:**

- Consumes: `getMonthNames` / `getWeekdayNames` from the adapter; `isWeekend` (Task 1)
- Produces:

  ```ts
  // data/index.ts — the module-level tables become functions
  export const generateWeeks = (adapter: CalendarAdapter, startOfWeek?: EStartOfTheWeek): WeekMonthDataType[]
  export const generateMonths = (adapter: CalendarAdapter): WeekMonthDataType[]
  export const generateQuarters = (adapter: CalendarAdapter): WeekMonthDataType[]
  ```

- [ ] **Step 1: Write the test**

`packages/calendar/tests/gantt-labels.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { gregorianCalendar, persianCalendar } from "../src/adapters";

/**
 * The Gantt's tables live in apps/web, which has no test runner. Pin the adapter properties they
 * depend on — the same technique locale-leak.test.ts uses — so the tables can be regenerated
 * per-adapter without a behavioural regression for Gregorian users.
 */
describe("Gantt table sources", () => {
  it("produces 7 weekday rows with a stable 0-based key", () => {
    const names = gregorianCalendar.getWeekdayNames("short", 0);
    expect(names).toHaveLength(7);
    expect(names[0]).toBe("Sun");
  });

  it("produces 12 month rows in Persian", () => {
    const names = persianCalendar.getMonthNames("short");
    expect(names).toHaveLength(12);
    expect(names[0]).toBe("فروردین");
  });

  it("has four seasons in Persian, not Q1-Q4", () => {
    // Seasons are fixed: Farvardin-Tir, Tir-Shahrivar, Shahrivar-Aban, Azar-Esfand.
    const SEASONS = ["بهار", "تابستان", "پاییز", "زمستان"];
    expect(SEASONS).toHaveLength(4);
  });

  it("maps Persian months onto the right season", () => {
    // Farvardin(1)-Tir(3) spring, Tir(4)-Shahrivar(6) summer,
    // Shahrivar(7)-Aban(9) autumn, Azar(10)-Esfand(12) winter.
    const seasonOf = (month: number) => Math.floor((month - 1) / 3);
    expect(seasonOf(1)).toBe(0);
    expect(seasonOf(3)).toBe(0);
    expect(seasonOf(4)).toBe(1);
    expect(seasonOf(6)).toBe(1);
    expect(seasonOf(7)).toBe(2);
    expect(seasonOf(9)).toBe(2);
    expect(seasonOf(10)).toBe(3);
    expect(seasonOf(12)).toBe(3);
  });
});
```

- [ ] **Step 2: Convert the tables to functions**

In `apps/web/components/gantt-chart/data/index.ts`, replace the three module-level tables. The `WeekMonthDataType` shape is `{key, shortTitle, title, abbreviation}` and consumers index by `key`, so preserve all three fields:

```ts
export const generateWeeks = (
  adapter: CalendarAdapter,
  startOfWeek: EStartOfTheWeek = EStartOfTheWeek.SUNDAY
): WeekMonthDataType[] => {
  const short = adapter.getWeekdayNames("short", startOfWeek);
  const long = adapter.getWeekdayNames("long", startOfWeek);
  return short.map((shortTitle, index) => ({
    key: (startOfWeek + index) % 7,
    shortTitle,
    title: long[index],
    // Persian has no case and no ASCII abbreviation; the narrow form is what CLDR offers.
    abbreviation: adapter.getWeekdayNames("narrow", startOfWeek)[(startOfWeek + index) % 7],
  }));
};

export const generateMonths = (adapter: CalendarAdapter): WeekMonthDataType[] => {
  const short = adapter.getMonthNames("short");
  const long = adapter.getMonthNames("long");
  return short.map((shortTitle, index) => ({
    key: index,
    shortTitle,
    title: long[index],
    abbreviation: shortTitle,
  }));
};

/**
 * Persian seasons rather than Q1-Q4. The boundary math is unchanged — `Math.floor((month - 1) / 3)`
 * on a 1-based month index gives the same three-month grouping as Gregorian quarters, because the
 * Persian year also starts at its first month.
 */
export const generateQuarters = (adapter: CalendarAdapter): WeekMonthDataType[] => {
  const SEASONS = [
    { shortTitle: "بهار", title: "فروردین - خرداد" },
    { shortTitle: "تابستان", title: "تیر - شهریور" },
    { shortTitle: "پاییز", title: "مهر - آذر" },
    { shortTitle: "زمستان", title: "دی - اسفند" },
  ];
  return SEASONS.map((season, index) => ({ key: index, ...season, abbreviation: season.shortTitle }));
};
```

Note the `title` strings for seasons are Persian month names composed literally. If a `fa` locale ever loads these through i18n, move them to translation keys — note that in the code so it is not lost.

- [ ] **Step 3: Fix the English-string weekend detection**

`apps/web/components/gantt-chart/chart/views/week.tsx:86`:

```tsx
{["sat", "sun"].includes(weekDay?.dayData?.shortTitle) && (
```

This is the sharpest hazard in the Gantt tree: it compares English strings, so it silently stops
shading weekends the moment Persian weekday names are used. Replace it with the numeric key, which
is calendar-independent:

```tsx
{isWeekendDay && (
```

where `isWeekendDay` is computed from `weekDay.dayData.key`:

```ts
const positionInWeek = (weekDay.dayData.key - startOfWeek + 7) % 7;
const isWeekendDay = positionInWeek >= 5;
```

Use the shared `isWeekend` from Task 1 where a `Date` is available; use the arithmetic above where
only the weekday key is.

- [ ] **Step 4: Delete the dead code**

`data/index.ts:49-72` contains `charCapitalize`, `timePreview` (which emits hardcoded `"AM"`/`"PM"`), and `datePreview`. The investigation found **zero importers** for all three outside this file. Delete them — `charCapitalize` in particular capitalises lowercase English table entries and is a no-op for Persian, so leaving it invites someone to "fix" Persian by applying it.

Confirm before deleting:

```bash
grep -rn "charCapitalize\|timePreview\|datePreview" apps packages --include=*.ts --include=*.tsx
```

If that grep shows any importer, keep that symbol and report it.

- [ ] **Step 5: Update the view generators**

`views/week-view.ts:194` calls `generateWeeks(startOfWeek)`, and `:201` builds a title from `.abbreviation` plus `getDate()`. `views/month-view.ts:148` uses `months[currentMonth]`. `views/quarter-view.ts:136-141` uses `quarters[quarterNumber]`. Each needs the adapter threaded in — see Task 6, which does the threading in one pass. Update the call signatures in this task only if the compiler forces it.

- [ ] **Step 6: Verify**

Run: `npx turbo run check:types`
Expected: 28/28.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/gantt-chart packages/calendar
git commit -m "feat(web): make the Gantt axis tables calendar-aware"
```

---

## Task 6: Thread the system through the Gantt generators

**Files:**

- Modify: `apps/web/components/gantt-chart/chart/root.tsx:94-107`
- Modify: `apps/web/components/gantt-chart/views/week-view.ts`, `month-view.ts`, `quarter-view.ts`, `helpers.ts`

**Interfaces:**

- Consumes: the generators from Task 5
- Produces: `generateChart(..., startOfWeek, system)` — the 5th parameter is appended, so the existing call site compiles until updated.

- [ ] **Step 1: Append the parameter to the generator chain**

In `chart/root.tsx:107` the funnel already reads the profile and passes `startOfWeek`. Add the system beside it:

```ts
  const { data, calendarSystem } = useUserProfile();
  const startOfWeek = data?.start_of_the_week;
  ...
  const currentRender = currentViewHelpers.generateChart(selectedCurrentViewData, side, targetDate, startOfWeek, calendarSystem);
```

Then thread `system` down: `generateWeekChart` / `generateMonthChart` / `generateQuarterChart` each take it as a new trailing parameter and pass it to their helpers.

- [ ] **Step 2: Fix month lengths in `helpers.ts`**

`getNumberOfDaysInMonth` at `:26-30` is `new Date(year, month + 1, 0).getDate()` — a Gregorian lookup. Replace with the adapter, and note the `month` it receives is currently 0-based from `date.getMonth()`:

```ts
export const getNumberOfDaysInMonth = (adapter: CalendarAdapter, year: number, month: number): number =>
  adapter.getMonthLength(year, month);
```

Audit every caller: any that passed a 0-based `date.getMonth()` must now pass `adapter.toParts(date).month`.

- [ ] **Step 3: Fix the quarter index**

`views/quarter-view.ts:123` and `:129` compute `Math.floor(month / 3)` from `date.getMonth()`. In Persian mode that reads the Gregorian month and lands on the wrong season. Use adapter parts:

```ts
const parts = adapter.toParts(today);
const quarterNumber = Math.floor((parts.month - 1) / 3);
```

The `- 1` matters: adapter months are 1-based, Gregorian months are 0-based.

- [ ] **Step 4: Fix week-title construction**

`views/week-view.ts:152-169` builds titles from `months[monthAtStartOfTheWeek].abbreviation` and `getFullYear()`. Both must come from the adapter's parts and names. The same applies to `views/month-view.ts:148-149` (`months[currentMonth].title` + `currentYear`) and `views/quarter-view.ts:136-141`.

**Leave positioning arithmetic on Gregorian `Date`s.** `getPositionFromDate` (`helpers.ts:120-137`) computes `days × dayWidth` from `findTotalDaysInRange`. That is a _duration_, not a calendar label — a Persian month is still 31 real days, so the day offsets are already correct. Do not convert them.

- [ ] **Step 5: Note a pre-existing bug, do not fix it here**

`views/month-view.ts:40` and `:120` take no `startOfWeek`, falling back to `EStartOfTheWeek.SUNDAY` — so `start_of_the_week` is silently ignored in the Gantt's month view. That bug predates this work and is not calendar-specific. Record it in the report and do not fix it in this task; mixing an unrelated behaviour change into a calendar PR makes review harder.

- [ ] **Step 6: Verify**

Run: `npx turbo run check:types`
Expected: 28/28.

Run: `pnpm --filter=@plane/calendar test && pnpm --filter=@plane/blocks test`
Expected: PASS.

Run: `npx turbo run check:lint`
Expected: 16/16.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/gantt-chart
git commit -m "feat(web): thread the calendar system through the Gantt generators"
```

---

## Task 7: Chart axis labels

**Files:**

- Modify: `apps/web/components/chart/utils.ts:19-56`
- Modify: `apps/web/components/analytics/work-items/priority-chart.tsx:49, 84-85`
- Modify: `apps/web/components/analytics/work-items/created-vs-resolved.tsx:60`
- Modify: `apps/web/components/core/sidebar/progress-chart.tsx:22`
- Create: `packages/calendar/tests/chart-axis.test.ts`

**Interfaces:**

- Consumes: `getCalendarAdapter` (phase 1), `renderFormattedDate` / `renderFormattedDateWithoutYear` (now calendar-aware)
- Produces: `parseChartData(..., system?)` — appended parameter, defaults to Gregorian.

- [ ] **Step 1: Write the test**

`packages/calendar/tests/chart-axis.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { renderFormattedDate, renderFormattedDateWithoutYear } from "@plane/utils";
import { gregorianCalendar, persianCalendar } from "../src/adapters";

/**
 * The chart axis labels come from these two formatters. Pin the pieces `getDateGroupingName`
 * composes, since the function itself is module-private in apps/web.
 */
describe("chart axis label building blocks", () => {
  it("renders a day label in both systems", () => {
    const date = new Date(2025, 5, 15);
    expect(renderFormattedDateWithoutYear(date)).toBe("Jun 15");
    const persian = renderFormattedDateWithoutYear(date, undefined, "persian");
    expect(persian).toContain("۱۴۰۴");
    expect(persian).toContain("شهریور");
  });

  it("renders the 'MMM' month token in both systems", () => {
    const date = new Date(2025, 5, 15);
    expect(renderFormattedDate(date, "MMM")).toBe("Jun");
    expect(renderFormattedDate(date, "MMM", "persian")).toContain("شهریور");
  });

  it("compares years in the active calendar, not the Gregorian one", () => {
    // 2025-03-20 is 1404-01-01. A Persian year boundary is ~621 years off, so comparing
    // getFullYear() against new Date().getFullYear() picks the wrong branch in Persian.
    const nowruz = new Date(2025, 2, 20);
    const gregorianYear = gregorianCalendar.toParts(nowruz).year;
    const persianYear = persianCalendar.toParts(nowruz).year;
    expect(gregorianYear).toBe(2025);
    expect(persianYear).toBe(1404);
  });
});
```

- [ ] **Step 2: Run the test**

Expected: PASS — this is a pin for already-correct phase-1 formatters. If it fails, the formatter is wrong, not the test.

- [ ] **Step 3: Thread the system into `getDateGroupingName`**

In `apps/web/components/chart/utils.ts`, give the module-private function a system parameter and
fix the three calendar-blind branches:

```ts
const getDateGroupingName = (
  date: string,
  dateGrouping: ChartXAxisDateGrouping,
  system: CalendarSystem = "gregorian"
): string => {
  if (!date || ["none", "null"].includes(date.toLowerCase())) return "None";

  const formattedData = new Date(date);
  const isValidDate = isValid(formattedData);
  if (!isValidDate) return date;

  const adapter = getCalendarAdapter(resolveCalendarSystem(system));
  // The current-year comparison must run in the *active* calendar. 2025-03-20 is Persian 1404,
  // so a Gregorian comparison picks the wrong branch and shows a year the user never sees.
  const year = adapter.toParts(formattedData).year;
  const isCurrentYear = year === adapter.toParts(new Date()).year;

  switch (dateGrouping) {
    case ChartXAxisDateGrouping.DAY:
      parsedName = isCurrentYear
        ? renderFormattedDateWithoutYear(formattedData, system)
        : renderFormattedDate(formattedData, undefined, system);
      break;
    case ChartXAxisDateGrouping.WEEK: {
      const month = renderFormattedDate(formattedData, "MMM", system);
      parsedName = `${month}, ${weekLabel} ${getWeekOfMonth(formattedData)}`;
      break;
    }
    case ChartXAxisDateGrouping.MONTH:
      parsedName = isCurrentYear
        ? renderFormattedDate(formattedData, "MMM", system)
        : renderFormattedDate(formattedData, "MMM, yyyy", system);
      break;
    case ChartXAxisDateGrouping.YEAR:
      // 2025 -> ۱۴۰۳. This is the most visible change on the chart.
      parsedName = adapter.format(formattedData, { year: "numeric" });
      break;
  }
  return parsedName ?? date;
};
```

For `weekLabel` and the `"None"` literal, check what i18n keys the repo already has before
inventing anything. If there is no suitable key, keep the English string and note it — the
translation work belongs to phase 4.

- [ ] **Step 4: Add the parameter to `parseChartData` and its caller**

`parseChartData` (`chart/utils.ts:58-116`) calls `getDateGroupingName` at `:85-87` and `:105-109`. Append `system` and forward it to both.

`priority-chart.tsx:49` already declares `x_axis_date_grouping?: …` on props. Add
`x_axis_date_grouping_system?: CalendarSystem` next to it, pass it at `:84-85`, and have
`customized-insights.tsx:57` supply it from the profile.

Note: `ChartXAxisDateGrouping.WEEK`, `MONTH`, and `YEAR` are currently **unreachable** — no caller
passes `x_axis_date_grouping`. Fix them anyway; they are one prop away from being live.

- [ ] **Step 5: The two charts that bypass `getDateGroupingName`**

- `created-vs-resolved.tsx:60` `renderFormattedDate(datum.key) ?? datum.key` → add the system.
- `progress-chart.tsx:22` `renderFormattedDateWithoutYear(key)` → add the system.

Both read the profile; follow whatever pattern their file already uses.

- [ ] **Step 6: Verify**

Run: `npx turbo run check:types`
Expected: 28/28.

Run: `pnpm --filter=@plane/calendar test && pnpm --filter=@plane/blocks test`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/components/chart apps/web/components/analytics apps/web/components/core/sidebar packages/calendar
git commit -m "feat(web): render chart axis labels in the user's calendar"
```

---

## Task 8: Phase 2 verification

**Files:**

- No new files. This is the phase gate.

- [ ] **Step 1: Run every suite**

```bash
pnpm --filter=@plane/calendar test   # expect 106
pnpm --filter=@plane/blocks test     # expect 277 — must not have moved
pnpm --filter=@plane/services test   # expect 13
```

- [ ] **Step 2: Backend, for regressions**

```bash
cd apps/api
export DATABASE_URL="postgresql://plane:plane@localhost:55432/plane"
export REDIS_URL="redis://localhost:56379/0"
export DJANGO_SETTINGS_MODULE="plane.settings.test"
export SECRET_KEY="test-secret-key"
/tmp/api312/bin/python -m pytest -m unit -q --no-header -p no:cacheprovider   # expect 432
```

Phase 2 touches no Python. If the venv from the phase-1 session is gone, say so and skip rather than
pretending it ran.

- [ ] **Step 3: Typecheck, lint, and the build graph**

```bash
npx turbo run check:types    # expect 28/28
npx turbo run check:lint     # expect 16/16
npx turbo run build --filter=web --dry   # expect 0 circular
```

- [ ] **Step 4: Prove the Gregorian path is byte-identical**

This is the safety claim for the whole task. Run the calendar grid generator over 24 months in both
systems and diff the Gregorian output against the pre-change implementation:

```bash
git stash                     # if the work is uncommitted; otherwise check out the parent commit
# run the generator for 2024-2025, dump the payloads, save
git stash pop
# run again, diff
```

A cleaner equivalent if that is awkward: the Task 4 test already pins `monthName`/`weekdayNames`/
`isWeekend` against `MONTHS_LIST`/`DAYS_LIST`, and Task 2's first case pins a full Gregorian
payload. Run those and confirm they pass — then state in the report that this is what was verified,
rather than claiming a whole-branch byte diff you did not run.

- [ ] **Step 5: Manual QA**

With the dev server up and a profile set to `calendar_system: persian`:

- [ ] Issue calendar layout shows Persian month and weekday names
- [ ] The month dropdown's arrows step Persian months and cross Nowruz correctly
- [ ] The month dropdown's year arrows land on the same Persian month, ±1 year
- [ ] The month-marker on a day tile fires on ۱ فروردین, not on the Gregorian 1st
- [ ] A Persian user sees 4 rows in Esfand 1404 (29 days) and 5–6 elsewhere, matching the existing variable behaviour
- [ ] Week layout still opens the correct week after a `start_of_the_week` change
- [ ] Gantt week view shows Persian weekday abbreviations
- [ ] Gantt month view shows Persian month names
- [ ] Gantt quarter view shows بهار/تابستان/پاییز/زمستان and the current one is highlighted
- [ ] **Gantt weekend shading still appears** — this is the string-comparison fix in Task 5, and it
      is the single most likely thing to break silently
- [ ] Chart axis YEAR shows ۱۴۰۴, not 2025
- [ ] Switching back to Gregorian restores English names, Q1–Q4, and Sat/Sun weekends everywhere

- [ ] **Step 6: Commit any QA fixes**

```bash
git add -A apps/web packages/calendar packages/utils
git commit -m "fix(web): address phase 2 QA findings"
```

Skip if the QA pass was clean.

---

## Known gaps left open

Deliberately **not** in this plan, so they are not mistaken for oversights:

- **`MONTHS_LIST` / `DAYS_LIST` stay English.** They are now unused by the calendar layout but remain
  exported from `@plane/constants`, and phase 1 pinned their shape. Deleting them is a separate
  cleanup once every consumer is migrated.
- **`START_OF_THE_WEEK_OPTIONS` labels stay English.** That is the settings dropdown, not a calendar
  view.
- **`apps/web/hooks/use-timezone-converter.tsx` keeps its `"en-US"`.** Those calls are timezone
  shims, not display formatters; `en-US` is required there to get a parseable string back.
- **~64 `renderFormattedDate` call sites across `apps/web` still pass no system** — applied-filter
  chips, issue activity, API tokens, comments, notifications, and more. Phase 2 covers the three big
  calendar views; the long tail is its own piece of work.
- **Gantt month view ignores `start_of_the_week`** — pre-existing, not calendar-specific (Task 6,
  step 5).
- **`fa-IR` translation and RTL** — phase 4. Persian strings here are literals, not i18n keys.
