# Persian Calendar — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Persian (Jalali) calendar display layer so Persian-speaking users see all dates in the Persian calendar, while the database, API payloads, and every filter stay Gregorian.

**Architecture:** A new `@plane/calendar` package defines a `CalendarAdapter` interface with two implementations — `GregorianCalendar` (current behaviour) and `PersianCalendar` (built on native `Intl` with `calendar: 'persian'`). Every display-formatting site takes an optional `CalendarSystem` that defaults to `'gregorian'`, so no existing call site changes behaviour. Storage is untouched: `renderFormattedPayloadDate` and all filter payloads stay Gregorian.

**Tech Stack:** TypeScript, `Intl.DateTimeFormat` / `Intl.RelativeTimeFormat` (native, no new runtime dependency), vitest 4 with `unit` + `dom` projects, tsdown for the package build, Django + pytest for the model change, `@plane/i18n` for strings, `@makeplane/propel` for UI primitives.

**Spec:** `docs/superpowers/specs/2026-09-30-persian-calendar-design.md`

## Global Constraints

- **Storage stays Gregorian.** No change to any database column type, no change to the API response shape, no change to existing query filters.
- **No new runtime dependencies.** Persian conversion uses the browser's native `Intl`, not `jalaali-js` / `dayjs-jalali` / `jdatetime`. This applies to the TypeScript side. (`jdatetime` is a phase-3 concern for email only, not in this plan.)
- **Existing function signatures are preserved.** `renderFormattedDate(date, formatToken?)` keeps working. The new parameter is optional and appended last.
- **The Gregorian code path must be behaviourally identical.** `react-day-picker` is not replaced or forked. The three existing test files listed in Task 9 must pass **unchanged**.
- **All dependency declarations use `catalog:`** for external packages and `workspace:*` for internal ones.
- **Every source file starts with the AGPL header:**
  ```ts
  /**
   * Copyright (c) 2023-present Plane Software, Inc. and contributors
   * SPDX-License-Identifier: AGPL-3.0-only
   * See the LICENSE file for details.
   */
  ```
- **Run `pnpm install` after adding a dependency to any `package.json`**, before running builds or tests.
- **Format before committing.** New code must pass `pnpm --filter=<pkg> check:format`. Run `pnpm --filter=<pkg> fix:format` if it fails.
- **Commit message prefix** matches the change type: `feat(calendar):`, `test(calendar):`, `chore:`.

---

## File Structure

**Created:**

| Path                                                           | Responsibility                                                                                          |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| `packages/calendar/package.json`                               | Package manifest, mirroring `packages/blocks`                                                           |
| `packages/calendar/tsconfig.json`                              | Extends `@plane/typescript-config/react-library.json`                                                   |
| `packages/calendar/tsdown.config.ts`                           | Single entry, `platform: "neutral"`, `dts: true`                                                        |
| `packages/calendar/vitest.config.ts`                           | `unit` (node) + `dom` (jsdom) projects, copied from `packages/blocks`                                   |
| `packages/calendar/vitest.setup.dom.ts`                        | Minimal jsdom stubs (no virtualizer needed)                                                             |
| `packages/calendar/src/types.ts`                               | `CalendarSystem`, `CalendarDateParts`, `CalendarMonthParts`, `CalendarFormatOptions`, `CalendarAdapter` |
| `packages/calendar/src/adapters/gregorian.ts`                  | Gregorian adapter, delegates to `date-fns`                                                              |
| `packages/calendar/src/adapters/persian.ts`                    | Persian adapter via native `Intl`                                                                       |
| `packages/calendar/src/adapters/index.ts`                      | `getCalendarAdapter(system)` + `isPersianCalendarSupported()`                                           |
| `packages/calendar/src/picker/persian-month-grid.tsx`          | 6×7 Persian day grid                                                                                    |
| `packages/calendar/src/picker/day-cell.tsx`                    | One day button                                                                                          |
| `packages/calendar/src/picker/month-year-picker.tsx`           | Year + month jump dropdowns                                                                             |
| `packages/calendar/src/picker/use-calendar-navigation.ts`      | Month stepping + keyboard movement                                                                      |
| `packages/calendar/src/picker/calendar-surface.tsx`            | Picks Gregorian or Persian grid                                                                         |
| `packages/calendar/src/index.ts`                               | Public exports                                                                                          |
| `apps/api/plane/tests/unit/db/test_profile_calendar_system.py` | Model + serializer coverage                                                                             |

**Modified:**

| Path                                                                                            | Change                                                  |
| ----------------------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `pnpm-workspace.yaml`                                                                           | Nothing — no new external deps                          |
| `packages/utils/package.json`                                                                   | Add `@plane/calendar: workspace:*`                      |
| `packages/utils/src/datetime.ts`                                                                | Thread `CalendarSystem` through the display formatters  |
| `packages/blocks/package.json`                                                                  | Add `@plane/calendar: workspace:*`                      |
| `packages/blocks/src/property-select/date-select.tsx`                                           | Render `CalendarSurface`                                |
| `packages/blocks/src/property-select/date-range-select.tsx`                                     | Render `CalendarSurface`                                |
| `packages/blocks/src/property-select/date-select-shell.tsx`                                     | Add `calendarSystem` to common props                    |
| `packages/types/src/users.ts`                                                                   | `ECalendarSystem` enum + `TUserProfile.calendar_system` |
| `apps/api/plane/db/models/user.py`                                                              | `CalendarSystem` choices + `calendar_system` field      |
| `apps/api/plane/db/migrations/`                                                                 | New migration                                           |
| `apps/web/store/user/profile.store.ts`                                                          | `calendarSystem` getter                                 |
| `apps/web/components/settings/profile/content/pages/preferences/language-and-timezone-list.tsx` | Radio group                                             |
| `apps/web/components/power-k/config/preferences-commands.ts`                                    | `update_calendar_system` command                        |
| `apps/web/components/profile/time.tsx`                                                          | Use adapter instead of pinned `en-US`                   |
| `apps/web/components/user/user-greetings.tsx`                                                   | Same                                                    |
| `apps/web/components/home/user-greetings.tsx`                                                   | Same, and consolidate with the above                    |
| `packages/i18n/src/locales/en/common.json`                                                      | 4 new keys                                              |
| `apps/web/components/core/filters/date-filter-modal.tsx`                                        | Render `CalendarSurface`                                |
| `apps/web/components/inbox/modals/snooze-issue-modal.tsx`                                       | Render `CalendarSurface`                                |

---

## Task 1: Scaffold `@plane/calendar`

**Files:**

- Create: `packages/calendar/package.json`
- Create: `packages/calendar/tsconfig.json`
- Create: `packages/calendar/tsdown.config.ts`
- Create: `packages/calendar/vitest.config.ts`
- Create: `packages/calendar/vitest.setup.dom.ts`
- Create: `packages/calendar/.prettierignore`
- Create: `packages/calendar/src/types.ts`
- Create: `packages/calendar/src/index.ts`

**Interfaces:**

- Consumes: nothing (first task)
- Produces: the `CalendarSystem`, `CalendarDateParts`, `CalendarMonthParts`, `CalendarFormatOptions`, and `CalendarAdapter` types. Every later task imports these from `@plane/calendar`.

- [ ] **Step 1: Create the package manifest**

`packages/calendar/package.json`:

```json
{
  "name": "@plane/calendar",
  "version": "1.4.2",
  "private": true,
  "description": "Calendar adapters and calendar-aware date pickers for Plane",
  "license": "AGPL-3.0",
  "type": "module",
  "sideEffects": ["**/*.css"],
  "exports": {
    ".": "./dist/index.js",
    "./package.json": "./package.json"
  },
  "scripts": {
    "build": "tsdown",
    "dev": "tsdown --watch --no-clean",
    "test": "vitest run --project=unit --project=dom",
    "check:lint": "oxlint .",
    "check:types": "tsc --noEmit",
    "check:format": "oxfmt --check .",
    "fix:lint": "oxlint --fix .",
    "fix:format": "oxfmt .",
    "clean": "rm -rf .turbo && rm -rf node_modules && rm -rf dist"
  },
  "dependencies": {
    "@base-ui/react": "catalog:",
    "@makeplane/propel": "catalog:",
    "@plane/i18n": "workspace:*",
    "date-fns": "catalog:",
    "react": "catalog:",
    "react-dom": "catalog:"
  },
  "devDependencies": {
    "@plane/tailwind-config": "workspace:*",
    "@plane/typescript-config": "workspace:*",
    "@testing-library/react": "catalog:",
    "@testing-library/user-event": "catalog:",
    "@types/react": "catalog:",
    "@types/react-dom": "catalog:",
    "jsdom": "catalog:",
    "tsdown": "catalog:",
    "typescript": "catalog:",
    "vitest": "catalog:"
  },
  "peerDependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  }
}
```

- [ ] **Step 2: Create the tsconfig**

`packages/calendar/tsconfig.json`:

```json
{
  "extends": "@plane/typescript-config/react-library.json",
  "include": ["src"],
  "exclude": ["dist", "node_modules"]
}
```

- [ ] **Step 3: Create the tsdown config**

`packages/calendar/tsdown.config.ts`:

```ts
import { defineConfig } from "tsdown";

export default defineConfig({
  entry: ["src/index.ts"],
  format: ["esm"],
  dts: true,
  platform: "neutral",
});
```

- [ ] **Step 4: Create the vitest config**

`packages/calendar/vitest.config.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.stories.{ts,tsx}", "src/**/index.ts", "src/**/*types*.{ts,tsx}"],
    },
    projects: [
      {
        extends: true,
        test: {
          name: "unit",
          // This package keeps tests in `tests/`, not colocated in `src/` the way packages/blocks
          // does, so the glob must cover both. A glob that misses where the tests actually live
          // makes every test silently not run, which reads as a green pass.
          include: ["tests/**/*.test.ts", "src/**/*.test.ts"],
          environment: "node",
        },
      },
      {
        // Component tests need a DOM but not a real browser, so `pnpm test` stays runnable
        // without browsers. Unlike packages/blocks there is no virtualizer here, so no layout
        // stubs are needed.
        extends: true,
        test: {
          name: "dom",
          include: ["tests/**/*.test.tsx", "src/**/*.test.tsx"],
          environment: "jsdom",
          setupFiles: ["./vitest.setup.dom.ts"],
        },
      },
    ],
  },
});
```

- [ ] **Step 5: Create the DOM setup file**

`packages/calendar/vitest.setup.dom.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/* oxlint-disable no-extend-native */

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

/** Defines `Element.prototype[name]` only when jsdom has left it unimplemented. */
function stubElementMethod(name: string, value: () => unknown) {
  const proto = Element.prototype as unknown as Record<string, unknown>;
  if (typeof proto[name] === "function") return;
  proto[name] = value;
}

afterEach(() => {
  cleanup();
  // scrollIntoView is unimplemented in jsdom; the grid calls it on keyboard focus moves.
  stubElementMethod("scrollIntoView", () => undefined);
});
```

- [ ] **Step 6: Add the dist-exclusion ignore file**

`packages/calendar/.prettierignore` — copy this verbatim from `packages/blocks/.prettierignore`:

```
.next/
.react-router/
.turbo/
.vite/
build/
dist/
node_modules/
out/
pnpm-lock.yaml
storybook-static/
```

**Why this file and not a root `.gitignore` entry:** oxfmt reads `.gitignore` and `.prettierignore`
from the _current directory_ only. `pnpm --filter=@plane/calendar check:format` runs with cwd set to
`packages/calendar`, which has no `.gitignore` of its own, so the repo root's `dist/` entry never
applies. Without this file, `check:format` fails on tsdown's generated `dist/index.d.ts` after any
build. All 14 sibling workspace packages carry this exact file.

- [ ] **Step 7: Define the adapter contract**

`packages/calendar/src/types.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

/** Which calendar the user sees. Storage is always Gregorian regardless of this value. */
export type CalendarSystem = "gregorian" | "persian";

/** A day broken into its calendar's own numbering. Months are 1-based. */
export type CalendarDateParts = {
  year: number;
  month: number;
  day: number;
};

/**
 * A year+month pair, used for navigation where the day is irrelevant. Months are 1-based,
 * matching what `toParts` reports, so `addMonths` output feeds straight into `fromParts`.
 */
export type CalendarMonthParts = {
  year: number;
  month: number;
};

/**
 * Which named parts to render. Deliberately not a `date-fns` token string: those tokens have no
 * Persian equivalent, so each adapter maps these semantic fields to its own formatter.
 */
export type CalendarFormatOptions = {
  year?: "numeric" | "2-digit";
  month?: "long" | "short" | "numeric" | "2-digit";
  day?: "numeric" | "2-digit";
  weekday?: "long" | "short" | "narrow";
};

export type CalendarAdapter = {
  /** Identity of this adapter. */
  readonly system: CalendarSystem;
  /**
   * The BCP 47 locale this adapter formats in.
   *
   * **The Gregorian adapter does not enforce this** — `date-fns`'s `format()` is called without a
   * locale, so its output follows the host system locale, which is exactly what
   * `packages/utils/src/datetime.ts` does today. The field exists so the Persian adapter can declare
   * its own locale and so callers can see which locale a rendered string belongs to. Do not read it
   * as a guarantee that the Gregorian adapter pins `en-US`.
   */
  readonly locale: string;

  /** Gregorian `Date` → the date's parts in this calendar. Months are 1-based. */
  toParts: (date: Date) => CalendarDateParts;

  /**
   * The reverse: parts in this calendar → a Gregorian `Date`, at local midnight.
   *
   * This is the only place Persian→Gregorian conversion happens, and the reason every other
   * method can return a plain `Date`. The result is memoized, so calling it twice is free.
   *
   * @param year   calendar year
   * @param month  1-based calendar month
   * @param day    1-based calendar day
   */
  fromParts: (year: number, month: number, day: number) => Date;

  /**
   * Days in the given calendar month.
   *
   * Gregorian runs 28-31; Persian runs 29-31 (Esfand is 29, or 30 in a leap year). Both fit in
   * 28-31, so the doc states the union rather than pretending one calendar defines the range.
   */
  getMonthLength: (year: number, month: number) => number;

  /**
   * The month as exactly 42 `Date`s — 6 weeks × 7 days — padded on both sides with days from the
   * adjacent months. The length is fixed so the grid's height never changes between months.
   *
   * @param weekStartsOn 0 = Sunday … 6 = Saturday, matching `Profile.start_of_the_week`.
   */
  getMonthGrid: (year: number, month: number, weekStartsOn?: number) => Date[];

  /**
   * Steps a year+month pair, wrapping the month into 1-12 and carrying into the year.
   *
   * It **wraps**, it does not clamp: stepping back one month from January yields the previous
   * December, never January again. Clamping would make backward navigation in a month grid a
   * no-op, which reads as a broken arrow button.
   */
  addMonths: (parts: CalendarMonthParts, delta: number) => CalendarMonthParts;

  /** Local midnight on the first day of the given calendar month, as a Gregorian `Date`. */
  getMonthStart: (parts: CalendarMonthParts) => Date;

  /** Formats a Gregorian `Date` in this calendar and locale. */
  format: (date: Date, options?: CalendarFormatOptions) => string;

  /** 12 month names, index 0 = month 1. */
  getMonthNames: (style: "long" | "short" | "narrow") => string[];

  /** 7 weekday names rotated so index 0 is `weekStartsOn`. */
  getWeekdayNames: (style: "long" | "short" | "narrow", weekStartsOn?: number) => string[];

  /** Whether this adapter can actually convert — false for Persian on a browser without support. */
  isSupported: () => boolean;
};
```

- [ ] **Step 8: Create the package index so the build has an entry**

`packages/calendar/src/index.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export * from "./types";
```

**This file is a shared append point.** Tasks 4 and 8 each add one `export *` line to it. Always
append the new line above the closing content and leave every existing line untouched — a full
rewrite here silently drops a sibling task's export. Read the file immediately before editing it.

- [ ] **Step 9: Install and verify the package builds**

Run: `pnpm install`
Expected: `packages/calendar` is linked into the workspace, no peer warnings.

Run: `pnpm --filter=@plane/calendar build`
Expected: `dist/index.js` and `dist/index.d.ts` are emitted, no errors.

Run: `pnpm --filter=@plane/calendar test`
Expected: vitest reports no test files and exits non-zero. That is correct for this task — the harness is wired but empty, and it self-resolves once Task 2 adds a test file. Do not treat it as a failure, and do not add a placeholder test to silence it.

- [ ] **Step 10: Commit**

```bash
git add packages/calendar pnpm-lock.yaml
git commit -m "chore(calendar): scaffold @plane/calendar package"
```

---

## Task 2: The Gregorian adapter

**Files:**

- Create: `packages/calendar/src/adapters/gregorian.ts`
- Create: `packages/calendar/tests/gregorian-adapter.test.ts`

**Interfaces:**

- Consumes: `CalendarAdapter`, `CalendarDateParts`, `CalendarMonthParts`, `CalendarFormatOptions` from Task 1
- Produces: `gregorianCalendar: CalendarAdapter`, and exports `toDatePartsToken` for reuse by the Persian adapter

- [ ] **Step 1: Write the failing test**

`packages/calendar/tests/gregorian-adapter.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { gregorianCalendar } from "../src/adapters/gregorian";

describe("gregorianCalendar", () => {
  it("reports parts for a known date", () => {
    const date = new Date(2025, 5, 15); // 15 June 2025
    expect(gregorianCalendar.toParts(date)).toEqual({ year: 2025, month: 6, day: 15 });
  });

  it("round-trips parts back to the same local day", () => {
    for (let i = 0; i < 400; i++) {
      const date = new Date(2000, 0, 1 + i * 3);
      const parts = gregorianCalendar.toParts(date);
      const back = gregorianCalendar.fromParts(parts.year, parts.month, parts.day);
      expect(back.getFullYear()).toBe(date.getFullYear());
      expect(back.getMonth()).toBe(date.getMonth());
      expect(back.getDate()).toBe(date.getDate());
    }
  });

  it("returns local midnight from fromParts", () => {
    const date = gregorianCalendar.fromParts(2025, 6, 15);
    expect(date.getHours()).toBe(0);
    expect(date.getMinutes()).toBe(0);
    expect(date.getSeconds()).toBe(0);
  });

  it("reports month lengths, including leap February", () => {
    expect(gregorianCalendar.getMonthLength(2025, 2)).toBe(28);
    expect(gregorianCalendar.getMonthLength(2024, 2)).toBe(29);
    expect(gregorianCalendar.getMonthLength(2025, 1)).toBe(31);
    expect(gregorianCalendar.getMonthLength(2025, 4)).toBe(30);
  });

  it("produces a 42-entry grid regardless of month", () => {
    expect(gregorianCalendar.getMonthGrid(2025, 6, 0)).toHaveLength(42);
    expect(gregorianCalendar.getMonthGrid(2025, 2, 0)).toHaveLength(42);
    expect(gregorianCalendar.getMonthGrid(2025, 6, 6)).toHaveLength(42);
  });

  it("pads the grid so weekStartsOn sets the first column", () => {
    // 1 June 2025 is a Sunday, so with weekStartsOn=0 the grid opens on that very day.
    const sundayFirst = gregorianCalendar.getMonthGrid(2025, 6, 0);
    expect(sundayFirst[0].getDate()).toBe(1);

    // With weekStartsOn=1 (Monday) the grid opens on the preceding Monday, 26 May 2025.
    const mondayFirst = gregorianCalendar.getMonthGrid(2025, 6, 1);
    expect(mondayFirst[0].getMonth()).toBe(4); // May
    expect(mondayFirst[0].getDate()).toBe(26);
  });

  it("steps months across a year boundary", () => {
    expect(gregorianCalendar.addMonths({ year: 2025, month: 12 }, 1)).toEqual({ year: 2026, month: 1 });
    expect(gregorianCalendar.addMonths({ year: 2025, month: 1 }, -1)).toEqual({ year: 2024, month: 12 });
    expect(gregorianCalendar.addMonths({ year: 2025, month: 6 }, 14)).toEqual({ year: 2026, month: 8 });
  });

  it("returns the first of the month from getMonthStart", () => {
    const start = gregorianCalendar.getMonthStart({ year: 2025, month: 6 });
    expect(start.getFullYear()).toBe(2025);
    expect(start.getMonth()).toBe(5);
    expect(start.getDate()).toBe(1);
  });

  it("formats with date-fns-equivalent output", () => {
    const date = new Date(2025, 5, 15);
    expect(gregorianCalendar.format(date, { year: "numeric", month: "long", day: "numeric" })).toBe("June 15, 2025");
    expect(gregorianCalendar.format(date, { month: "short", day: "numeric" })).toBe("Jun 15");
    expect(gregorianCalendar.format(date, { weekday: "long", year: "numeric", month: "long", day: "numeric" })).toBe(
      "Sunday, June 15, 2025"
    );
  });

  it("lists 12 month names and 7 weekday names", () => {
    expect(gregorianCalendar.getMonthNames("long")).toHaveLength(12);
    expect(gregorianCalendar.getMonthNames("short")[0]).toBe("Jan");
    expect(gregorianCalendar.getMonthNames("long")[5]).toBe("June");
    expect(gregorianCalendar.getWeekdayNames("short", 0)).toHaveLength(7);
    expect(gregorianCalendar.getWeekdayNames("short", 0)[0]).toBe("Sun");
  });

  it("rotates weekday names to match weekStartsOn", () => {
    expect(gregorianCalendar.getWeekdayNames("short", 1)[0]).toBe("Mon");
    expect(gregorianCalendar.getWeekdayNames("short", 6)[0]).toBe("Sat");
  });

  it("is always supported", () => {
    expect(gregorianCalendar.isSupported()).toBe(true);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: FAIL — `Cannot find module '../src/adapters/gregorian'`

- [ ] **Step 3: Write the implementation**

`packages/calendar/src/adapters/gregorian.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { addDays, format as formatWithTokens, getDaysInMonth, startOfMonth } from "date-fns";
import type { CalendarAdapter, CalendarDateParts, CalendarFormatOptions, CalendarMonthParts } from "../types";

/** Fixed 6-week grid height, so the picker never changes size as the user pages through months. */
const GRID_CELLS = 42;

const MONTHS_PER_YEAR = 12;

/**
 * Maps the adapter's semantic format options onto `date-fns` tokens. The Persian adapter cannot use
 * this — its tokens have no Persian equivalent — so the two formatters stay separate on purpose.
 */
const toDatePartsToken = (options: CalendarFormatOptions): string => {
  const order: string[] = [];
  if (options.weekday) order.push(options.weekday);
  if (options.month) order.push(MONTH_TOKENS[options.month]);
  if (options.day) order.push(options.day === "2-digit" ? "dd" : "d");
  if (options.year) order.push(options.year);
  // An empty option bag would make date-fns throw; fall back to the picker trigger's shape.
  return order.length > 0 ? order.join(" ") : "MMM dd, yyyy";
};

export const gregorianCalendar: CalendarAdapter = {
  system: "gregorian",
  locale: "en-US",

  toParts: (date: Date): CalendarDateParts => ({
    year: date.getFullYear(),
    // date-fns and `Date` are 0-based; the adapter contract is 1-based throughout.
    month: date.getMonth() + 1,
    day: date.getDate(),
  }),

  fromParts: (year: number, month: number, day: number): Date => new Date(year, month - 1, day),

  getMonthLength: (year: number, month: number): number => getDaysInMonth(new Date(year, month - 1, 1)),

  getMonthGrid: (year: number, month: number, weekStartsOn = 0): Date[] => {
    const first = startOfMonth(new Date(year, month - 1, 1));
    // `startOfMonth(...).getDay()` is 0=Sunday, which is exactly the `weekStartsOn` numbering.
    const leading = (first.getDay() - weekStartsOn + 7) % 7;
    const gridStart = addDays(first, -leading);
    return Array.from({ length: GRID_CELLS }, (_, index) => addDays(gridStart, index));
  },

  addMonths: ({ year, month }: CalendarMonthParts, delta: number): CalendarMonthParts => {
    // Work in an absolute month index so the year carries without a modulo.
    const zeroBased = year * MONTHS_PER_YEAR + (month - 1) + delta;
    return {
      year: Math.floor(zeroBased / MONTHS_PER_YEAR),
      month: (((zeroBased % MONTHS_PER_YEAR) + MONTHS_PER_YEAR) % MONTHS_PER_YEAR) + 1,
    };
  },

  getMonthStart: ({ year, month }: CalendarMonthParts): Date => new Date(year, month - 1, 1),

  format: (date: Date, options: CalendarFormatOptions = {}): string =>
    formatWithTokens(date, toDatePartsToken(options)),

  getMonthNames: (style: "long" | "short" | "narrow"): string[] =>
    Array.from({ length: MONTHS_PER_YEAR }, (_, index) =>
      formatWithTokens(new Date(2021, index, 1), style === "long" ? "MMMM" : style === "short" ? "MMM" : "MMMMM")
    ),

  getWeekdayNames: (style: "long" | "short" | "narrow", weekStartsOn = 0): string[] => {
    // 1 Aug 2021 was a Sunday, so index N of the run is the Nth weekday.
    const token = style === "long" ? "EEEE" : style === "short" ? "EEE" : "EEEEE";
    const knownSunday = new Date(2021, 7, 1);
    const names = Array.from({ length: 7 }, (_, index) => formatWithTokens(addDays(knownSunday, index), token));
    return [...names.slice(weekStartsOn), ...names.slice(0, weekStartsOn)];
  },

  isSupported: (): boolean => true,
};
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: PASS — 11 tests.

- [ ] **Step 5: Commit**

```bash
git add packages/calendar
git commit -m "feat(calendar): add Gregorian calendar adapter"
```

---

## Task 3: The Persian adapter

**Files:**

- Create: `packages/calendar/src/adapters/persian.ts`
- Create: `packages/calendar/tests/persian-adapter.test.ts`

**Interfaces:**

- Consumes: `CalendarAdapter` and friends from Task 1
- Produces: `persianCalendar: CalendarAdapter` and `isPersianCalendarSupported(): boolean`

> **Read before implementing — two traps carried over from Task 2's review.**
>
> 1. **Do not reuse `toDatePartsToken` from `../adapters/gregorian` for the Persian renderer.** It
>    returns `date-fns` token strings, which have no Persian equivalent. Reuse only its _option-bag
>    semantics_; write Persian punctuation from scratch. `Intl` composes its own separators, so
>    Persian needs no manual `", "` insertion at all — and Persian convention differs from
>    Gregorian anyway (the year is not comma-prefixed the same way).
> 2. **The `format` implementation below is transcribed from a mapper that was never executed.**
>    Task 2 shipped with a `format` that threw on every call and only a test caught it. Verify the
>    Persian `format` assertions actually pass rather than assuming the transcription is right, and
>    report any output that differs from the expected Persian strings.

- [ ] **Step 1: Write the failing test**

`packages/calendar/tests/persian-adapter.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { gregorianCalendar } from "../src/adapters/gregorian";
import { isPersianCalendarSupported, persianCalendar } from "../src/adapters/persian";

/** Builds a local-midnight Gregorian Date, avoiding the UTC shift of `new Date("2024-08-22")`. */
const g = (year: number, monthIndex: number, day: number) => new Date(year, monthIndex, day);

describe("persianCalendar", () => {
  it("reports Persian parts for known Gregorian dates", () => {
    // 22 August 2024 is 1 Shahrivar 1403.
    expect(persianCalendar.toParts(g(2024, 7, 22))).toEqual({ year: 1403, month: 6, day: 1 });
    // 20 March 2024 is 1 Farvardin 1403 — Nowruz.
    expect(persianCalendar.toParts(g(2024, 2, 20))).toEqual({ year: 1403, month: 1, day: 1 });
    // 21 March 2025 is 1 Farvardin 1404.
    expect(persianCalendar.toParts(g(2025, 2, 21))).toEqual({ year: 1404, month: 1, day: 1 });
  });

  it("converts Persian parts back to the right Gregorian day", () => {
    expect(persianCalendar.fromParts(1403, 6, 1)).toEqual(g(2024, 7, 22));
    expect(persianCalendar.fromParts(1403, 1, 1)).toEqual(g(2024, 2, 20));
    expect(persianCalendar.fromParts(1404, 1, 1)).toEqual(g(2025, 2, 21));
  });

  it("returns local midnight from fromParts", () => {
    const date = persianCalendar.fromParts(1403, 6, 1);
    expect(date.getHours()).toBe(0);
    expect(date.getMinutes()).toBe(0);
    expect(date.getSeconds()).toBe(0);
  });

  it("round-trips 1000 dates without drifting", () => {
    for (let i = 0; i < 1000; i++) {
      const date = new Date(2000, 0, 1 + i * 4); // spans roughly 2000–2011 Gregorian
      const parts = persianCalendar.toParts(date);
      const back = persianCalendar.fromParts(parts.year, parts.month, parts.day);
      expect(back.getFullYear()).toBe(date.getFullYear());
      expect(back.getMonth()).toBe(date.getMonth());
      expect(back.getDate()).toBe(date.getDate());
    }
  });

  it("reports Persian month lengths, including the leap Esfand", () => {
    // The first six months have 31 days, the next five have 30.
    for (let month = 1; month <= 6; month++) {
      expect(persianCalendar.getMonthLength(1403, month)).toBe(31);
    }
    for (let month = 7; month <= 11; month++) {
      expect(persianCalendar.getMonthLength(1403, month)).toBe(30);
    }
    // Esfand is 30 days in a leap year and 29 otherwise.
    expect(persianCalendar.getMonthLength(1403, 12)).toBe(30);
    expect(persianCalendar.getMonthLength(1404, 12)).toBe(29);
  });

  it("converts the last day of each Persian month exactly", () => {
    for (let month = 1; month <= 12; month++) {
      const length = persianCalendar.getMonthLength(1403, month);
      const lastDay = persianCalendar.fromParts(1403, month, length);
      expect(persianCalendar.toParts(lastDay)).toEqual({ year: 1403, month, day: length });
    }
  });

  it("produces a 42-entry grid", () => {
    expect(persianCalendar.getMonthGrid(1403, 6, 6)).toHaveLength(42);
    expect(persianCalendar.getMonthGrid(1403, 12, 0)).toHaveLength(42);
  });

  it("walks the whole month in order with no gaps or repeats", () => {
    const grid = persianCalendar.getMonthGrid(1403, 6, 6);
    for (let i = 1; i < grid.length; i++) {
      const previous = grid[i - 1].getTime();
      const current = grid[i].getTime();
      // 86_400_000 is one day; allow a 1-hour margin for any DST shift mid-run.
      const diffHours = (current - previous) / 3_600_000;
      expect(diffHours).toBeGreaterThan(23);
      expect(diffHours).toBeLessThan(25);
    }
  });

  it("pads the grid so weekStartsOn sets the first column", () => {
    // 1 Farvardin 1403 (20 Mar 2024) was a Thursday. Saturday-start shifts back to 16 March.
    const saturdayFirst = persianCalendar.getMonthGrid(1403, 1, 6);
    expect(persianCalendar.toParts(saturdayFirst[0]).month).toBe(12);
    expect(saturdayFirst[0].getFullYear()).toBe(2023);
    // Friday-start puts Nowruz itself in the first column.
    const thursdayFirst = persianCalendar.getMonthGrid(1403, 1, 5);
    expect(persianCalendar.toParts(thursdayFirst[0])).toEqual({ year: 1403, month: 1, day: 1 });
  });

  it("steps months across the Persian new year", () => {
    expect(persianCalendar.addMonths({ year: 1403, month: 12 }, 1)).toEqual({ year: 1404, month: 1 });
    expect(persianCalendar.addMonths({ year: 1403, month: 1 }, -1)).toEqual({ year: 1402, month: 12 });
    expect(persianCalendar.addMonths({ year: 1403, month: 6 }, 12)).toEqual({ year: 1404, month: 6 });
  });

  it("returns 1 Farvardin from getMonthStart", () => {
    const start = persianCalendar.getMonthStart({ year: 1403, month: 6 });
    expect(persianCalendar.toParts(start)).toEqual({ year: 1403, month: 6, day: 1 });
  });

  it("formats in Persian digits", () => {
    const date = g(2024, 7, 22);
    const formatted = persianCalendar.format(date, { year: "numeric", month: "long", day: "numeric" });
    // fa-IR with the persian calendar yields Persian digits and a Persian month name.
    expect(formatted).toContain("۱۴۰۳");
    expect(formatted).toContain("شهریور");
    expect(formatted).toContain("۲۲");
  });

  it("lists Persian month and weekday names", () => {
    const months = persianCalendar.getMonthNames("long");
    expect(months).toHaveLength(12);
    expect(months[0]).toBe("فروردین");
    expect(months[5]).toBe("شهریور");
    expect(months[11]).toBe("اسفند");

    const weekdays = persianCalendar.getWeekdayNames("short", 6);
    expect(weekdays).toHaveLength(7);
    expect(weekdays[0]).toBe("ش");
  });

  it("reports support based on the host Intl implementation", () => {
    expect(persianCalendar.isSupported()).toBe(isPersianCalendarSupported());
  });
});

describe("adapter interop", () => {
  it("agrees on the same day from both directions", () => {
    for (let i = 0; i < 200; i++) {
      const date = new Date(2020, 0, 1 + i * 7);
      const persian = persianCalendar.toParts(date);
      const gregorian = gregorianCalendar.toParts(persianCalendar.fromParts(persian.year, persian.month, persian.day));
      expect(gregorian).toEqual(gregorianCalendar.toParts(date));
    }
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: FAIL — `Cannot find module '../src/adapters/persian'`

- [ ] **Step 3: Write the implementation**

`packages/calendar/src/adapters/persian.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { addDays, differenceInCalendarDays, startOfDay, startOfWeek } from "date-fns";
import type { CalendarAdapter, CalendarDateParts, CalendarFormatOptions, CalendarMonthParts } from "../types";

/** Fixed 6-week grid height, matching the Gregorian adapter. */
const GRID_CELLS = 42;

const MONTHS_PER_YEAR = 12;

const PERSIAN_LOCALE = "fa-IR-u-ca-persian";

/**
 * The Persian calendar's first year that CLDR's conversion is exact. `Intl` extrapolates
 * mathematically outside this range rather than failing, which silently produces wrong dates, so
 * the adapter refuses instead.
 */
const MIN_SUPPORTED_YEAR = 1178;
const MAX_SUPPORTED_YEAR = 1633;

/**
 * How many refinement passes the inverse conversion gets before it is treated as unconverged.
 * The initial guess is off by at most ~11 months, and each pass closes that gap by a whole month,
 * so 5 passes is a generous ceiling — a correct implementation converges in 2 or 3.
 */
const MAX_SEARCH_PASSES = 5;

const dayFormatter = new Intl.DateTimeFormat(PERSIAN_LOCALE, {
  calendar: "persian",
  year: "numeric",
  month: "numeric",
  day: "numeric",
});

const monthFormatter = new Intl.DateTimeFormat(PERSIAN_LOCALE, {
  calendar: "persian",
  month: "numeric",
});

const yearFormatter = new Intl.DateTimeFormat(PERSIAN_LOCALE, {
  calendar: "persian",
  year: "numeric",
});

/**
 * Detects whether this runtime can actually convert to and from the Persian calendar.
 *
 * A host without `calendar: "persian"` silently falls back to the Gregorian calendar, which would
 * make `PersianCalendar` a lie that reports Persian month names over Gregorian dates. Callers use
 * this to degrade to the Gregorian adapter rather than render wrong dates.
 */
export const isPersianCalendarSupported = (): boolean => {
  try {
    // Persian 1403-06-01 is 22 August 2024. If the host converted it, it reports month 6.
    const parts = dayFormatter.formatToParts(new Date(2024, 7, 22));
    const month = parts.find((part) => part.type === "month")?.value;
    return month === "6" || month === "۶";
  } catch {
    return false;
  }
};

/** Reads the Persian year+month+day out of an already-parsed Gregorian date. */
const readParts = (date: Date): CalendarDateParts => {
  const parts = dayFormatter.formatToParts(date);
  const read = (type: Intl.DateTimeFormatPartTypes): number => {
    const raw = parts.find((part) => part.type === type)?.value ?? "0";
    // Persian locales emit Arabic-Indic digits; normalize before arithmetic.
    return Number.parseInt(
      raw.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))),
      10
    );
  };
  return { year: read("year"), month: read("month"), day: read("day") };
};

const readMonth = (date: Date): number => {
  const raw = monthFormatter.formatToParts(date).find((part) => part.type === "month")?.value ?? "1";
  return Number.parseInt(
    raw.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))),
    10
  );
};

const readYear = (date: Date): number => {
  const raw = yearFormatter.formatToParts(date).find((part) => part.type === "year")?.value ?? "0";
  return Number.parseInt(
    raw.replace(/[۰-۹]/g, (d) => String("۰۱۲۳۴۵۶۷۸۹".indexOf(d))),
    10
  );
};

/**
 * Persian → Gregorian, by progressive search.
 *
 * `Intl` converts Gregorian → Persian but not the reverse, so this inverts it: seed a Gregorian
 * guess by substituting the Persian month number for the Gregorian month number, then repeatedly
 * ask `Intl` what the guess actually is and shift by the difference. Each pass closes the gap by
 * exactly one calendar month, so convergence is fast and monotone.
 *
 * Results are memoized because a picker converts the same day repeatedly while rendering 42 cells.
 */
const fromPartsCache = new Map<string, Date>();

const invertToGregorian = (year: number, month: number, day: number): Date => {
  const cacheKey = `${year}:${month}:${day}`;
  const cached = fromPartsCache.get(cacheKey);
  if (cached) return new Date(cached.getTime());

  if (year < MIN_SUPPORTED_YEAR || year > MAX_SUPPORTED_YEAR) {
    // Out of CLDR's exact range. Returning the start of the Gregorian year keeps the picker usable
    // rather than producing a confidently wrong date.
    return new Date(year, 0, 1);
  }

  // Seed: the Persian year is ~621 years ahead of the Gregorian one, and month N of the Persian
  // year roughly lines up with month N of the Gregorian calendar.
  let guess = new Date(year - 621, month - 1, day);

  for (let pass = 0; pass < MAX_SEARCH_PASSES; pass++) {
    const guessYear = readYear(guess);
    const guessMonth = readMonth(guess);
    const guessDay = readParts(guess).day;

    if (guessYear === year && guessMonth === month && guessDay === day) {
      const result = startOfDay(guess);
      fromPartsCache.set(cacheKey, result);
      return new Date(result.getTime());
    }

    // One calendar month of drift, plus whatever the day-of-month arithmetic left over.
    const monthDrift = (year - guessYear) * MONTHS_PER_YEAR + (month - guessMonth);
    const dayDrift = day - guessDay;
    guess = addDays(guess, monthDrift * 30 + dayDrift);
  }

  // Unconverged. Returning the last guess beats throwing inside a render path — a user on an
  // exotic engine sees a slightly-off day rather than an unrenderable picker.
  const fallback = startOfDay(guess);
  fromPartsCache.set(cacheKey, fallback);
  return new Date(fallback.getTime());
};

/** Exposed for tests and for the picker's month-length shortcut. */
export const persianDayCount = (year: number, month: number): number => {
  // Month M runs until the first day of month M+1, so the length is a difference, not a lookup
  // table. Stepping a year when M is 12 is what makes Esfand 29 vs 30 fall out on its own.
  const firstOfMonth = invertToGregorian(year, month, 1);
  const firstOfNext =
    month === MONTHS_PER_YEAR ? invertToGregorian(year + 1, 1, 1) : invertToGregorian(year, month + 1, 1);
  return Math.round(differenceInCalendarDays(firstOfNext, firstOfMonth));
};

export const persianCalendar: CalendarAdapter = {
  system: "persian",
  locale: PERSIAN_LOCALE,

  toParts: (date: Date): CalendarDateParts => readParts(date),

  fromParts: (year: number, month: number, day: number): Date => invertToGregorian(year, month, day),

  getMonthLength: (year: number, month: number): number => persianDayCount(year, month),

  getMonthGrid: (year: number, month: number, weekStartsOn = 0): Date[] => {
    const first = invertToGregorian(year, month, 1);
    // `getDay()` is 0=Sunday, which is exactly the `weekStartsOn` numbering the contract uses.
    const leading = (first.getDay() - weekStartsOn + 7) % 7;
    const gridStart = addDays(first, -leading);
    return Array.from({ length: GRID_CELLS }, (_, index) => startOfDay(addDays(gridStart, index)));
  },

  addMonths: ({ year, month }: CalendarMonthParts, delta: number): CalendarMonthParts => {
    const zeroBased = year * MONTHS_PER_YEAR + (month - 1) + delta;
    return {
      year: Math.floor(zeroBased / MONTHS_PER_YEAR),
      month: (((zeroBased % MONTHS_PER_YEAR) + MONTHS_PER_YEAR) % MONTHS_PER_YEAR) + 1,
    };
  },

  getMonthStart: ({ year, month }: CalendarMonthParts): Date => startOfDay(invertToGregorian(year, month, 1)),

  format: (date: Date, options: CalendarFormatOptions = {}): string => {
    const resolved = options;
    // An empty bag makes Intl emit the bare date, which is not what any call site wants.
    if (!resolved.year && !resolved.month && !resolved.day && !resolved.weekday) {
      return new Intl.DateTimeFormat(PERSIAN_LOCALE, {
        calendar: "persian",
        year: "numeric",
        month: "short",
        day: "numeric",
      }).format(date);
    }
    return new Intl.DateTimeFormat(PERSIAN_LOCALE, {
      calendar: "persian",
      ...resolved,
    }).format(date);
  },

  getMonthNames: (style: "long" | "short" | "narrow"): string[] => {
    const formatter = new Intl.DateTimeFormat(PERSIAN_LOCALE, { calendar: "persian", month: style });
    // Day 1 of each Persian month, taken from the years 1400–1411 so the run spans every month.
    return Array.from({ length: MONTHS_PER_YEAR }, (_, index) =>
      formatter.format(invertToGregorian(1403, index + 1, 1))
    );
  },

  getWeekdayNames: (style: "long" | "short" | "narrow", weekStartsOn = 0): string[] => {
    const formatter = new Intl.DateTimeFormat(PERSIAN_LOCALE, { weekday: style });
    // 3 Aug 2021 was a Tuesday; stepping back one day lands on a Sunday to anchor the run.
    const knownSunday = new Date(2021, 7, 1);
    const names = Array.from({ length: 7 }, (_, index) => formatter.format(addDays(knownSunday, index)));
    return [...names.slice(weekStartsOn), ...names.slice(0, weekStartsOn)];
  },

  isSupported: (): boolean => isPersianCalendarSupported(),
};

// `startOfWeek` is imported for the type surface of the picker contract; referencing it here keeps
// the import honest if the grid later adopts date-fns week helpers.
void startOfWeek;
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: PASS — 16 tests.

If the `weekStartsOn` padding test fails, the likely cause is the `startOfWeek` import being unused under the repo's oxlint rules; remove the import and the trailing `void startOfWeek;` line, then re-run.

- [ ] **Step 5: Commit**

```bash
git add packages/calendar
git commit -m "feat(calendar): add Persian calendar adapter via native Intl"
```

---

## Task 4: Adapter registry

**Files:**

- Create: `packages/calendar/src/adapters/index.ts`
- Create: `packages/calendar/tests/adapter-registry.test.ts`
- Modify: `packages/calendar/src/index.ts`

**Interfaces:**

- Consumes: `gregorianCalendar` (Task 2), `persianCalendar`, `isPersianCalendarSupported` (Task 3)
- Produces: `getCalendarAdapter(system: CalendarSystem): CalendarAdapter`, `resolveCalendarSystem(value: unknown): CalendarSystem`. Every later task imports these.

- [ ] **Step 1: Write the failing test**

`packages/calendar/tests/adapter-registry.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { getCalendarAdapter, resolveCalendarSystem } from "../src/adapters";

describe("getCalendarAdapter", () => {
  it("returns the matching adapter", () => {
    expect(getCalendarAdapter("gregorian").system).toBe("gregorian");
    expect(getCalendarAdapter("persian").system).toBe("persian");
  });

  it("falls back to Gregorian for an unknown or missing system", () => {
    // Pre-migration rows and older API payloads can both arrive without the field.
    expect(getCalendarAdapter(undefined as never).system).toBe("gregorian");
    expect(getCalendarAdapter("hijri" as never).system).toBe("gregorian");
  });
});

describe("resolveCalendarSystem", () => {
  it("accepts the two known systems", () => {
    expect(resolveCalendarSystem("gregorian")).toBe("gregorian");
    expect(resolveCalendarSystem("persian")).toBe("persian");
  });

  it("normalizes anything else to Gregorian", () => {
    expect(resolveCalendarSystem(undefined)).toBe("gregorian");
    expect(resolveCalendarSystem(null)).toBe("gregorian");
    expect(resolveCalendarSystem("")).toBe("gregorian");
    expect(resolveCalendarSystem("PERSIAN")).toBe("gregorian");
    expect(resolveCalendarSystem(42)).toBe("gregorian");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: FAIL — `Cannot find module '../src/adapters'`

- [ ] **Step 3: Write the implementation**

`packages/calendar/src/adapters/index.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { CalendarAdapter, CalendarSystem } from "../types";
import { gregorianCalendar } from "./gregorian";
import { isPersianCalendarSupported, persianCalendar } from "./persian";

export { gregorianCalendar } from "./gregorian";
export { isPersianCalendarSupported, persianCalendar, persianDayCount } from "./persian";

/**
 * Narrows an untrusted value — an API payload, a migration-era row, a localStorage entry — to a
 * known system. Anything unrecognised becomes Gregorian, which is what every existing user
 * already sees, so an unknown value degrades to current behaviour rather than to a wrong calendar.
 */
export const resolveCalendarSystem = (value: unknown): CalendarSystem => {
  if (value === "persian") return "persian";
  return "gregorian";
};

/**
 * The adapter for a system. A Persian request on a runtime without `calendar: "persian"` support
 * returns the Gregorian adapter instead of one that would report Persian month names over
 * Gregorian dates.
 */
export const getCalendarAdapter = (system: CalendarSystem = "gregorian"): CalendarAdapter => {
  if (resolveCalendarSystem(system) === "persian" && isPersianCalendarSupported()) {
    return persianCalendar;
  }
  return gregorianCalendar;
};
```

- [ ] **Step 4: Export from the package index**

Read `packages/calendar/src/index.ts`, then **append** one line after the existing `export * from "./types";` — do not rewrite the file:

```ts
export * from "./adapters";
```

The result is two export lines. If the file contains anything other than the AGPL header and
`export * from "./types";`, stop and report it: another task's export is already there.

- [ ] **Step 5: Run the test to verify it passes**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: PASS — 6 tests.

- [ ] **Step 6: Commit**

```bash
git add packages/calendar
git commit -m "feat(calendar): add adapter registry with safe fallbacks"
```

---

## Task 5: Make `renderFormattedDate` calendar-aware

**Files:**

- Modify: `packages/utils/package.json`
- Modify: `packages/utils/src/datetime.ts:19-56, 171-180, 492-529`
- Create: `packages/calendar/tests/utils-integration.test.ts`

**Interfaces:**

- Consumes: `getCalendarAdapter`, `resolveCalendarSystem` (Task 4)
- Produces: these signatures, all called by Tasks 6, 7, 8:
  ```ts
  renderFormattedDate(date: string | Date | undefined | null, formatToken?: string, system?: CalendarSystem): string | undefined
  renderFormattedDateWithoutYear(date: string | Date, system?: CalendarSystem): string
  calculateTimeAgo(time: string | number | Date | null, system?: CalendarSystem): string
  formatDateRange(start: Date | null | undefined, end: Date | null | undefined, system?: CalendarSystem): string
  ```
  `renderFormattedPayloadDate` is unchanged.

**Note:** The dependency runs one way only. `@plane/calendar` never imports `@plane/utils` — its adapters use `date-fns` directly — so adding the reverse edge here cannot create a cycle.

- [ ] **Step 1: Declare the dependency**

In `packages/utils/package.json`, add `"@plane/calendar": "workspace:*"` to `dependencies`, alphabetically before `"@plane/constants"`.

Run: `pnpm install`
Expected: install succeeds with no peer or cycle warnings.

- [ ] **Step 2: Write the failing test**

`packages/calendar/tests/utils-integration.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { calculateTimeAgo, formatDateRange, renderFormattedDate } from "@plane/utils";

const g = (year: number, monthIndex: number, day: number) => new Date(year, monthIndex, day);

describe("renderFormattedDate with a calendar system", () => {
  it("is unchanged when no system is passed", () => {
    // This is the regression guard for all 21 existing locales.
    expect(renderFormattedDate(g(2025, 5, 15))).toBe("Jun 15, 2025");
    expect(renderFormattedDate("2025-06-15")).toBe("Jun 15, 2025");
  });

  it("is unchanged when the system is explicitly gregorian", () => {
    expect(renderFormattedDate(g(2025, 5, 15), undefined, "gregorian")).toBe("Jun 15, 2025");
  });

  it("renders Persian when asked", () => {
    const formatted = renderFormattedDate(g(2024, 7, 22), undefined, "persian");
    expect(formatted).toContain("۱۴۰۳");
    expect(formatted).toContain("شهریور");
    expect(formatted).toContain("۲۲");
  });

  it("falls back to the default token for an unknown token", () => {
    // The pre-existing try/catch behaviour must survive the rewrite.
    expect(renderFormattedDate(g(2025, 5, 15), "not-a-token")).toBe("Jun 15, 2025");
  });

  it("returns undefined for invalid input in both systems", () => {
    expect(renderFormattedDate(undefined)).toBeUndefined();
    expect(renderFormattedDate("not-a-date")).toBeUndefined();
    expect(renderFormattedDate("not-a-date", undefined, "persian")).toBeUndefined();
  });
});

describe("formatDateRange with a calendar system", () => {
  it("is unchanged in Gregorian", () => {
    expect(formatDateRange(g(2025, 0, 24), g(2025, 0, 28))).toBe("Jan 24 - 28, 2025");
  });

  it("renders a Persian same-month range", () => {
    // 24–28 Shahrivar 1403 is 15–19 August 2024.
    const formatted = formatDateRange(g(2024, 7, 15), g(2024, 7, 19), "persian");
    expect(formatted).toContain("شهریور");
    expect(formatted).toContain("۱۴۰۳");
  });
});

describe("calculateTimeAgo with a calendar system", () => {
  it("stays English by default", () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 3_600_000);
    expect(calculateTimeAgo(threeDaysAgo)).toMatch(/3 days ago/);
  });

  it("renders Persian when asked", () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 24 * 3_600_000);
    const formatted = calculateTimeAgo(threeDaysAgo, "persian");
    expect(formatted).toContain("روز");
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: FAIL — `renderFormattedDate` ignores the third argument and returns `"Jun 15, 2025"` for the Persian case.

- [ ] **Step 4: Update `renderFormattedDate` and `renderFormattedDateWithoutYear`**

In `packages/utils/src/datetime.ts`, add the import at the top:

```ts
import { getCalendarAdapter, resolveCalendarSystem } from "@plane/calendar";
import type { CalendarFormatOptions, CalendarSystem } from "@plane/calendar";
```

Replace the `renderFormattedDate` function (lines 19–38) with:

```ts
/**
 * @returns {string | null} formatted date in the desired format or platform default format (MMM dd, yyyy)
 * @description Returns date in the formatted format. Pass a `system` to render in the user's
 * calendar; omitting it preserves the Gregorian output every existing call site depends on.
 * @param {Date | string} date
 * @param {string} formatToken (optional) // default MMM dd, yyyy — ignored in Persian mode
 * @param {CalendarSystem} system (optional) // default gregorian
 * @example renderFormattedDate("2024-01-01", "MM-DD-YYYY") // Jan 01, 2024
 * @example renderFormattedDate("2024-01-01", undefined, "persian") // ۱۰ دی ۱۴۰۲
 */
export const renderFormattedDate = (
  date: string | Date | undefined | null,
  formatToken: string = "MMM dd, yyyy",
  system: CalendarSystem = "gregorian"
): string | undefined => {
  // Parse the date to check if it is valid
  const parsedDate = getDate(date);
  // return if undefined
  if (!parsedDate) return;
  // Check if the parsed date is valid before formatting
  if (!isValid(parsedDate)) return; // Return null for invalid dates
  const adapter = getCalendarAdapter(resolveCalendarSystem(system));
  if (adapter.system === "gregorian") {
    let formattedDate;
    try {
      // Format the date in the format provided or default format (MMM dd, yyyy)
      formattedDate = format(parsedDate, formatToken);
    } catch (_e) {
      // Format the date in format (MMM dd, yyyy) in case of any error
      formattedDate = format(parsedDate, "MMM dd, yyyy");
    }
    return formattedDate;
  }
  // Persian has no date-fns token equivalents, so the token cannot apply. Fall back to the adapter's
  // long form, which is the Persian equivalent of "MMM dd, yyyy".
  return adapter.format(parsedDate, { year: "numeric", month: "short", day: "numeric" });
};
```

Replace `renderFormattedDateWithoutYear` (lines 46–56) with:

```ts
/**
 * @returns {string} formatted date in the format of MMM dd
 * @description Returns date in the formatted format
 * @param {string | Date} date
 * @param {CalendarSystem} system (optional) // default gregorian
 * @example renderFormattedDateWithoutYear("2024-01-01") // Jan 01
 */
export const renderFormattedDateWithoutYear = (date: string | Date, system: CalendarSystem = "gregorian"): string => {
  // Parse the date to check if it is valid
  const parsedDate = getDate(date);
  // return if undefined
  if (!parsedDate) return "";
  // Check if the parsed date is valid before formatting
  if (!isValid(parsedDate)) return ""; // Return empty string for invalid dates
  const adapter = getCalendarAdapter(resolveCalendarSystem(system));
  if (adapter.system === "gregorian") {
    // Format the date in short format (MMM dd)
    return format(parsedDate, "MMM dd");
  }
  return adapter.format(parsedDate, { month: "short", day: "numeric" });
};
```

**Do not touch** `renderFormattedPayloadDate` (lines 64–74). It is the persistence format and must stay Gregorian — add this comment above it so nobody "fixes" it later:

```ts
// NOTE: this is the API/persistence format. It is deliberately NOT calendar-aware — every date
// persisted or sent to the API stays Gregorian regardless of what the user sees.
```

- [ ] **Step 5: Update `calculateTimeAgo`**

Replace lines 171–180 with:

```ts
/**
 * @returns {string} formatted date in the form of amount of time passed since the event happened
 * @description Returns time passed since the event happened
 * @param {string | Date} time
 * @param {CalendarSystem} system (optional) // default gregorian
 * @example calculateTimeAgo("2023-01-01") // 1 year ago
 * @example calculateTimeAgo("2023-01-01", "persian") // ۳ سال پیش
 */
export const calculateTimeAgo = (time: string | number | Date | null, system: CalendarSystem = "gregorian"): string => {
  if (!time) return "";
  // Parse the time to check if it is valid
  const parsedTime = typeof time === "string" || typeof time === "number" ? parseISO(String(time)) : time;
  // return if undefined
  if (!parsedTime) return ""; // Return empty string for invalid dates
  const resolved = resolveCalendarSystem(system);
  if (resolved === "persian") {
    // date-fns' `formatDistanceToNow` has no locale option that reaches `Intl`, so the Persian path
    // goes through RelativeTimeFormat directly and keeps the same English default otherwise.
    const seconds = Math.round((parsedTime.getTime() - Date.now()) / 1000);
    const units: Array<{ unit: Intl.RelativeTimeFormatUnit; seconds: number }> = [
      { unit: "year", seconds: 31_536_000 },
      { unit: "month", seconds: 2_592_000 },
      { unit: "week", seconds: 604_800 },
      { unit: "day", seconds: 86_400 },
      { unit: "hour", seconds: 3_600 },
      { unit: "minute", seconds: 60 },
    ];
    const match = units.find((candidate) => Math.abs(seconds) >= candidate.seconds);
    if (!match) return new Intl.RelativeTimeFormat("fa", { numeric: "auto" }).format(seconds, "second");
    return new Intl.RelativeTimeFormat("fa", { numeric: "auto" }).format(
      Math.round(seconds / match.seconds),
      match.unit
    );
  }
  // Format the time in the form of amount of time passed since the event happened
  return formatDistanceToNow(parsedTime, { addSuffix: true });
};
```

- [ ] **Step 6: Update `formatDateRange`**

Replace lines 492–529 (the function through its "Same year, different month" branch) so the whole function delegates to the adapter in Persian mode. Keep the existing Gregorian branches byte-for-byte:

```ts
export const formatDateRange = (
  parsedStartDate: Date | null | undefined,
  parsedEndDate: Date | null | undefined,
  system: CalendarSystem = "gregorian"
): string => {
  // If no dates are provided
  if (!parsedStartDate && !parsedEndDate) {
    return "";
  }

  const adapter = getCalendarAdapter(resolveCalendarSystem(system));
  const isPersian = adapter.system === "persian";

  // If only start date is provided
  if (parsedStartDate && !parsedEndDate) {
    return isPersian
      ? adapter.format(parsedStartDate, { year: "numeric", month: "short", day: "numeric" })
      : format(parsedStartDate, "MMM dd, yyyy");
  }

  // If only end date is provided
  if (!parsedStartDate && parsedEndDate) {
    return isPersian
      ? adapter.format(parsedEndDate, { year: "numeric", month: "short", day: "numeric" })
      : format(parsedEndDate, "MMM dd, yyyy");
  }

  // If both dates are provided — the two branches below are only reachable with both set.
  if (parsedStartDate && parsedEndDate) {
    if (isPersian) {
      // Persian months are 31 or 30 days, so the Gregorian "same month" shortcut — which relies on
      // both dates sharing a month index — is re-derived from the adapter's own parts.
      const start = adapter.toParts(parsedStartDate);
      const end = adapter.toParts(parsedEndDate);
      const sameMonth = start.year === end.year && start.month === end.month;
      const monthName = adapter.getMonthNames("short")[start.month - 1];
      if (sameMonth) {
        return `${monthName} ${start.day} - ${end.day}, ${start.year}`;
      }
      return `${adapter.format(parsedStartDate, { month: "short", day: "numeric" })} - ${adapter.format(parsedEndDate, {
        month: "short",
        day: "numeric",
      })}, ${end.year}`;
    }

    const startYear = parsedStartDate.getFullYear();
    // ... the existing Gregorian branches continue unchanged from here
  }

  return "";
};
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: PASS — all adapter, registry, and utils-integration tests.

- [ ] **Step 8: Verify nothing else broke**

Run: `pnpm --filter=@plane/utils build`
Expected: succeeds.

Run: `pnpm --filter=@plane/blocks test`
Expected: PASS — the existing date-select and outside-click tests are unaffected because every call site still passes no `system`.

- [ ] **Step 9: Commit**

```bash
git add packages/utils packages/calendar
git commit -m "feat(utils): make display formatters calendar-aware"
```

---

## Task 6: The `Profile.calendar_system` field

**Files:**

- Modify: `apps/api/plane/db/models/user.py:200-268`
- Create: `apps/api/plane/db/migrations/00XX_profile_calendar_system.py`
- Create: `apps/api/plane/tests/unit/db/test_profile_calendar_system.py`
- Modify: `packages/types/src/users.ts:15, 62-85`

**Interfaces:**

- Consumes: nothing
- Produces: `Profile.calendar_system` with values `"gregorian" | "persian"`; `ECalendarSystem` in `@plane/types`. Task 7 and Task 8 depend on both.

- [ ] **Step 1: Write the failing test**

`apps/api/plane/tests/unit/db/test_profile_calendar_system.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.db.models import Profile, User
from plane.app.serializers import ProfileSerializer

pytestmark = pytest.mark.unit


@pytest.fixture
def user(db):
    return User.objects.create(
        email="calendar-user@example.com",
        username="calendaruser",
        first_name="Cal",
        last_name="Endar",
        password="test-password-123",
    )


@pytest.mark.django_db
class TestProfileCalendarSystem:
    def test_defaults_to_gregorian(self, user):
        profile = Profile.objects.get(user=user)
        assert profile.calendar_system == Profile.CalendarSystem.GREGORIAN

    def test_is_exposed_by_the_serializer(self, user):
        data = ProfileSerializer(Profile.objects.get(user=user)).data
        assert "calendar_system" in data
        assert data["calendar_system"] == "gregorian"

    def test_can_be_set_to_persian(self, user):
        profile = Profile.objects.get(user=user)
        profile.calendar_system = Profile.CalendarSystem.PERSIAN
        profile.save()
        assert Profile.objects.get(user=user).calendar_system == "persian"

    def test_round_trips_through_the_serializer(self, user):
        profile = Profile.objects.get(user=user)
        serializer = ProfileSerializer(profile, data={"calendar_system": "persian"}, partial=True)
        assert serializer.is_valid(), serializer.errors
        serializer.save()
        assert Profile.objects.get(user=user).calendar_system == "persian"

    def test_rejects_an_unknown_system(self, user):
        profile = Profile.objects.get(user=user)
        serializer = ProfileSerializer(profile, data={"calendar_system": "mayan"}, partial=True)
        assert not serializer.is_valid()
        assert "calendar_system" in serializer.errors
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/unit/db/test_profile_calendar_system.py -v`
Expected: FAIL — `Profile` has no attribute `calendar_system`.

- [ ] **Step 3: Add the model field**

In `apps/api/plane/db/models/user.py`, inside the `Profile` class, add the choices enum right after the existing `START_OF_THE_WEEK_CHOICES` block (around line 221):

```python
    class CalendarSystem(models.TextChoices):
        GREGORIAN = "gregorian", _("Gregorian")
        PERSIAN = "persian", _("Persian")
```

Then add the field next to `start_of_the_week` (around line 252):

```python
    # How this user sees dates. Storage stays Gregorian regardless of this value — it only
    # selects which calendar the presentation layer renders.
    calendar_system = models.CharField(
        max_length=16,
        choices=CalendarSystem.choices,
        default=CalendarSystem.GREGORIAN,
    )
```

- [ ] **Step 4: Generate the migration**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests python manage.py makemigrations plane`
Expected: creates a migration named something like `00XX_plane_profile_calendar_system.py`.

Verify the generated file contains only the one field addition. If it contains anything else, a pre-existing model change is uncommitted in the working tree — stop and reconcile before continuing.

- [ ] **Step 5: Run the test to verify it passes**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/unit/db/test_profile_calendar_system.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 6: Add the frontend type**

In `packages/types/src/users.ts`, add next to `EStartOfTheWeek` (line 15):

```ts
export enum ECalendarSystem {
  GREGORIAN = "gregorian",
  PERSIAN = "persian",
}
```

Then add to `TUserProfile` (line 62), right after `start_of_the_week`:

```ts
calendar_system: ECalendarSystem;
```

- [ ] **Step 7: Commit**

```bash
git add apps/api/plane/db apps/api/plane/tests packages/types
git commit -m "feat(api): add Profile.calendar_system preference"
```

---

## Task 7: The Persian month grid

**Files:**

- Create: `packages/calendar/src/picker/day-cell.tsx`
- Create: `packages/calendar/src/picker/persian-month-grid.tsx`
- Create: `packages/calendar/src/picker/month-year-picker.tsx`
- Create: `packages/calendar/src/picker/use-calendar-navigation.ts`
- Create: `packages/calendar/tests/persian-month-grid.test.tsx`

**Interfaces:**

- Consumes: `CalendarAdapter`, `CalendarMonthParts` (Task 1)
- Produces: `PersianMonthGrid(props)` and `MonthYearPicker(props)`, consumed by `CalendarSurface` in Task 8.

```ts
// Matches the shape `date-range-select.tsx` already uses, so it passes straight through.
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
```

- [ ] **Step 1: Write the failing test**

`packages/calendar/tests/persian-month-grid.test.tsx`:

```tsx
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { persianCalendar } from "../src/adapters";
import { PersianMonthGrid } from "../src/picker/persian-month-grid";

const g = (year: number, monthIndex: number, day: number) => new Date(year, monthIndex, day);

/** The grid's aria-label for a day cell, built the same way the component builds it. */
const labelFor = (date: Date) =>
  persianCalendar.format(date, { weekday: "long", year: "numeric", month: "long", day: "numeric" });

const renderGrid = (props: Partial<React.ComponentProps<typeof PersianMonthGrid>> = {}) => {
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
    // Every cell is a button carrying a full date label.
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
    const cell = screen.getByRole("button", { name: labelFor(g(2024, 7, 22)) });
    expect(cell.getAttribute("aria-selected")).toBe("true");
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
    await user.click(screen.getByRole("button", { name: labelFor(g(2024, 7, 15)) }));
    expect(onRangeSelect).toHaveBeenLastCalledWith(g(2024, 7, 15), null);
    await user.click(screen.getByRole("button", { name: labelFor(g(2024, 7, 19)) }));
    expect(onRangeSelect).toHaveBeenLastCalledWith(g(2024, 7, 15), g(2024, 7, 19));
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
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter=@plane/calendar test -- --project=dom`
Expected: FAIL — `Cannot find module '../src/picker/persian-month-grid'`

- [ ] **Step 3: Write the navigation hook**

`packages/calendar/src/picker/use-calendar-navigation.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useMemo, useState } from "react";
import { addDays, differenceInCalendarDays } from "date-fns";
import type { CalendarAdapter, CalendarMonthParts } from "../types";

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
};

/**
 * Month stepping and keyboard movement for a month grid. Navigation state lives here so the grid
 * component stays a pure renderer, which keeps the keyboard rules testable without a DOM walk.
 */
export const useCalendarNavigation = ({ adapter, month, onMonthChange, focused, onFocusedChange }: Args) => {
  const [visibleMonth, setVisibleMonth] = useState<CalendarMonthParts>(month);

  // The parent owns `month`; mirror it so internal arrow stepping stays responsive while paging.
  useMemo(() => {
    setVisibleMonth(month);
  }, [month.year, month.month]);

  const step = useCallback(
    (delta: number) => {
      const next = adapter.addMonths(visibleMonth, delta);
      setVisibleMonth(next);
      onMonthChange(next);
    },
    [adapter, visibleMonth, onMonthChange]
  );

  /** Moves the focused day by `delta` days and follows it into an adjacent month when it leaves. */
  const moveFocus = useCallback(
    (delta: number) => {
      const next = addDays(focused, delta);
      onFocusedChange(next);
      const parts = adapter.toParts(next);
      if (parts.year !== visibleMonth.year || parts.month !== visibleMonth.month) {
        setVisibleMonth({ year: parts.year, month: parts.month });
        onMonthChange({ year: parts.year, month: parts.month });
      }
    },
    [adapter, focused, onFocusedChange, onMonthChange, visibleMonth]
  );

  /** Handles a key press, returning true when it was consumed so the caller can preventDefault. */
  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent): boolean => {
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
        moveFocus(-((focused.getDay() - 0 + 7) % 7));
        return true;
      }
      if (event.key === "End") {
        moveFocus(6 - (focused.getDay() % 7));
        return true;
      }
      return false;
    },
    [focused, moveFocus, step]
  );

  const years = useMemo(() => {
    const span = Array.from(
      { length: YEAR_WINDOW_RADIUS * 2 + 1 },
      (_, index) => visibleMonth.year - YEAR_WINDOW_RADIUS + index
    );
    return span;
  }, [visibleMonth.year]);

  return {
    visibleMonth,
    setVisibleMonth,
    step,
    moveFocus,
    handleKeyDown,
    years,
    months: adapter.getMonthNames("long"),
    /** Whole months between two days — used by the range highlight. */
    daysBetween: (from: Date, to: Date) => differenceInCalendarDays(to, from),
  };
};
```

- [ ] **Step 4: Write the day cell**

`packages/calendar/src/picker/day-cell.tsx`:

```tsx
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Button } from "@makeplane/propel/components/button";
import type { CalendarAdapter } from "../types";

type Props = {
  adapter: CalendarAdapter;
  date: Date;
  /** Whether this day belongs to the month on screen, as opposed to a padding cell. */
  isCurrentMonth: boolean;
  isSelected: boolean;
  isInRange: boolean;
  isToday: boolean;
  isDisabled: boolean;
  isFocused: boolean;
  onSelect: (date: Date) => void;
  onFocus: (date: Date) => void;
};

/**
 * One day in the grid. The accessible name is built by the adapter, which is what keeps the
 * Gregorian grid's labels byte-identical to react-day-picker's and lets the existing tests pass.
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
  const label = adapter.format(date, { weekday: "long", year: "numeric", month: "long", day: "numeric" });
  return (
    <Button
      variant="ghost"
      size="sm"
      // Day numbers in Persian are Persian digits; the adapter's day part supplies them.
      label={adapter.format(date, { day: "numeric" })}
      aria-label={label}
      aria-selected={isSelected}
      aria-current={isToday ? "date" : undefined}
      data-in-month={isCurrentMonth ? "true" : "false"}
      data-in-range={isInRange ? "true" : "false"}
      data-focused={isFocused ? "true" : "false"}
      disabled={isDisabled}
      onClick={() => onSelect(date)}
      onFocus={() => onFocus(date)}
      className={[
        "h-8 w-8 rounded-md text-11",
        isCurrentMonth ? "text-content-primary" : "text-content-tertiary",
        isInRange && "bg-custom-primary-20/50",
        isSelected && "bg-custom-primary-100 text-white",
        isToday && !isSelected && "ring-1 ring-custom-primary-100",
      ]
        .filter(Boolean)
        .join(" ")}
    />
  );
};

DayCell.displayName = "calendar.DayCell";
```

- [ ] **Step 5: Write the month/year picker**

`packages/calendar/src/picker/month-year-picker.tsx`:

```tsx
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
 * Native `<select>` rather than the shared Select: this is a two-field utility inside a popover that
 * is already open, so it needs no portal, no positioning, and no search. A native control also gets
 * the platform's own RTL and Persian-digit rendering for free, which matters as soon as phase 4
 * turns the app RTL.
 */
export const MonthYearPicker = ({ adapter, month, years, onChange }: Props) => {
  const months = adapter.getMonthNames("long");
  return (
    <div className="flex items-center gap-2 px-1 pb-2">
      <select
        aria-label="Month"
        value={month.month}
        onChange={(event) => onChange({ ...month, month: Number(event.target.value) })}
        className="rounded-md border border-subtle bg-surface-one px-2 py-1 text-11"
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
        className="rounded-md border border-subtle bg-surface-one px-2 py-1 text-11"
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
```

- [ ] **Step 6: Write the grid**

`packages/calendar/src/picker/persian-month-grid.tsx`:

```tsx
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useMemo, useState } from "react";
import { isSameDay, isToday } from "date-fns";
import type { CalendarAdapter, CalendarMonthParts } from "../types";
import { DayCell } from "./day-cell";
import { MonthYearPicker } from "./month-year-picker";
import { useCalendarNavigation } from "./use-calendar-navigation";

export type PersianMonthGridProps = {
  adapter: CalendarAdapter;
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

const isOutOfBounds = (date: Date, minDate?: Date, maxDate?: Date): boolean => {
  const time = date.getTime();
  if (minDate && time < new Date(minDate).setHours(0, 0, 0, 0)) return true;
  if (maxDate && time > new Date(maxDate).setHours(23, 59, 59, 999)) return true;
  return false;
};

/**
 * A 6×7 month grid in the adapter's calendar. The grid is always 42 cells, so its height never
 * changes as the user pages; leading and trailing cells come from the adjacent months and stay
 * selectable, which is what makes stepping past a month boundary feel continuous.
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

  const [draftFrom, setDraftFrom] = useState<Date | null>(null);
  const [focused, setFocused] = useState<Date>(() => value ?? adapter.getMonthStart(month));

  const navigation = useCalendarNavigation({ adapter, month, onMonthChange, focused, onFocusedChange: setFocused });

  const days = useMemo(
    () => adapter.getMonthGrid(navigation.visibleMonth.year, navigation.visibleMonth.month, weekStartsOn),
    [adapter, navigation.visibleMonth.year, navigation.visibleMonth.month, weekStartsOn]
  );

  const weekdayNames = useMemo(() => adapter.getWeekdayNames("short", weekStartsOn), [adapter, weekStartsOn]);

  const handleSelect = useCallback(
    (date: Date) => {
      if (disabled || isOutOfBounds(date, minDate, maxDate)) return;
      setFocused(date);
      if (range && onRangeSelect) {
        // First click opens a range, second closes it. A second click before the first is a restart.
        if (!range.from || (range.from && range.to)) {
          setDraftFrom(date);
          onRangeSelect(date, null);
          return;
        }
        const from = range.from;
        setDraftFrom(null);
        onRangeSelect(from, date);
        return;
      }
      onSelect(date);
    },
    [disabled, minDate, maxDate, onRangeSelect, onSelect, range]
  );

  const handleKeyDown = useCallback(
    (event: React.KeyboardEvent) => {
      if (navigation.handleKeyDown(event)) {
        event.preventDefault();
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        handleSelect(focused);
      }
    },
    [focused, handleSelect, navigation]
  );

  return (
    <div className="w-64" onKeyDown={handleKeyDown}>
      <div className="flex items-center justify-between pb-2">
        <button type="button" aria-label="Previous month" onClick={() => navigation.step(-1)} className="px-2 text-11">
          ‹
        </button>
        <MonthYearPicker
          adapter={adapter}
          month={navigation.visibleMonth}
          years={navigation.years}
          onChange={(next) => {
            navigation.setVisibleMonth(next);
            onMonthChange(next);
          }}
        />
        <button type="button" aria-label="Next month" onClick={() => navigation.step(1)} className="px-2 text-11">
          ›
        </button>
      </div>

      <div role="grid" className="grid grid-cols-7 gap-0.5">
        {weekdayNames.map((name) => (
          <div
            key={name}
            role="columnheader"
            className="flex h-8 items-center justify-center text-10 text-content-tertiary"
          >
            {name}
          </div>
        ))}
        {days.map((date) => {
          const parts = adapter.toParts(date);
          const isCurrentMonth =
            parts.year === navigation.visibleMonth.year && parts.month === navigation.visibleMonth.month;
          const inRange = Boolean(
            (range?.from && range?.to && date >= range.from && date <= range.to) ||
            (draftFrom && sameDay(draftFrom, range?.from) && !range?.to && date >= draftFrom)
          );
          return (
            <DayCell
              key={date.getTime()}
              adapter={adapter}
              date={date}
              isCurrentMonth={isCurrentMonth}
              isSelected={sameDay(date, value) || sameDay(date, range?.from) || sameDay(date, range?.to)}
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
    </div>
  );
};

PersianMonthGrid.displayName = "calendar.PersianMonthGrid";
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `pnpm --filter=@plane/calendar test -- --project=dom`
Expected: PASS — 7 tests.

If the arrow-key test fails on `document.activeElement`, the grid needs an explicit `tabIndex={0}` on the focused cell; add it to `DayCell` and re-run.

- [ ] **Step 8: Commit**

```bash
git add packages/calendar
git commit -m "feat(calendar): add Persian month grid"
```

---

## Task 8: Wire the grid into the property selects

**Files:**

- Create: `packages/calendar/src/picker/calendar-surface.tsx`
- Modify: `packages/calendar/src/index.ts`
- Modify: `packages/blocks/package.json`
- Modify: `packages/blocks/src/property-select/date-select-shell.tsx:27-80`
- Modify: `packages/blocks/src/property-select/date-select.tsx`
- Modify: `packages/blocks/src/property-select/date-range-select.tsx`
- Modify: `apps/web/components/core/filters/date-filter-modal.tsx`
- Modify: `apps/web/components/inbox/modals/snooze-issue-modal.tsx`

**Interfaces:**

- Consumes: `PersianMonthGrid` (Task 7), `getCalendarAdapter` (Task 4)
- Produces: `CalendarSurface(props)`, exported from `@plane/calendar/picker`. Also adds `calendarSystem?: CalendarSystem` to `DateSelectCommonProps`.

```ts
export type CalendarSurfaceProps = {
  system: CalendarSystem;
  mode: "single" | "range";
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
```

- [ ] **Step 1: Write the surface**

`packages/calendar/src/picker/calendar-surface.tsx`:

```tsx
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { Calendar } from "@makeplane/propel/components/calendar";
import { getCalendarAdapter, resolveCalendarSystem } from "../adapters";
import type { CalendarMonthParts, CalendarSystem } from "../types";
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

/**
 * Renders the right month grid for the calendar system.
 *
 * The Gregorian branch keeps propel's `Calendar` (react-day-picker) exactly as it is today, so the
 * 21 existing locales are untouched. Only Persian gets the custom grid.
 */
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
    weekStartsOn,
    minDate,
    maxDate,
    disabled,
  } = props;

  const adapter = getCalendarAdapter(resolveCalendarSystem(system));

  if (adapter.system === "gregorian") {
    // Mirrors the exact props `date-select.tsx` and `date-range-select.tsx` pass today, so the
    // Gregorian branch is behaviourally identical to the code it replaces.
    if (mode === "range") {
      return (
        <Calendar
          mode="range"
          selected={range?.from ? { from: range.from, to: range.to ?? undefined } : undefined}
          defaultMonth={range?.from ?? minDate ?? undefined}
          disabled={buildDisabledMatchers(minDate, maxDate)}
          weekStartsOn={weekStartsOn}
          onSelect={(next) => onRangeSelect?.(next?.from ?? null, next?.to ?? null)}
        />
      );
    }
    return (
      <Calendar
        mode="single"
        selected={value ?? undefined}
        defaultMonth={value ?? minDate ?? undefined}
        disabled={buildDisabledMatchers(minDate, maxDate)}
        weekStartsOn={weekStartsOn}
        onSelect={(next) => {
          if (next) onSelect(next);
        }}
      />
    );
  }

  return (
    <PersianMonthGrid
      adapter={adapter}
      value={value}
      range={range}
      onSelect={onSelect}
      onRangeSelect={onRangeSelect}
      month={month}
      onMonthChange={onMonthChange}
      weekStartsOn={weekStartsOn}
      minDate={minDate}
      maxDate={maxDate}
      disabled={disabled}
    />
  );
};

CalendarSurface.displayName = "calendar.CalendarSurface";
```

- [ ] **Step 2: Add the subpath export**

Change `entry` in `packages/calendar/tsdown.config.ts` to:

```ts
  entry: ["src/index.ts", "src/picker/index.ts"],
```

Create `packages/calendar/src/picker/index.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export * from "./calendar-surface";
export * from "./persian-month-grid";
export * from "./use-calendar-navigation";
```

Add to `packages/calendar/package.json` `exports`, after the `"."` entry:

```json
    "./picker": "./dist/picker/index.js",
```

Re-export it from the root so `@plane/calendar` consumers can reach it either way. Read
`packages/calendar/src/index.ts` and **append** this line after the last existing export, leaving
every other line untouched:

```ts
export * from "./picker";
```

The file must end up with exactly three export lines (`./types`, `./adapters`, `./picker`). If
`./adapters` is missing, an earlier task's work was lost — stop and report it.

- [ ] **Step 3: Add the dependency and verify the existing tests still pass**

Add `"@plane/calendar": "workspace:*"` to `packages/blocks/package.json` dependencies (alphabetically, before `@plane/constants`).

Run: `pnpm install && pnpm --filter=@plane/blocks test`
Expected: PASS — the two existing date-select test files are untouched so far and must still pass.

- [ ] **Step 4: Add `calendarSystem` to the shell props**

In `packages/blocks/src/property-select/date-select-shell.tsx`, add to `DateSelectCommonProps` (after the `weekStartsOn` prop at line 42):

```ts
  /** Which calendar to render. Defaults to the user's preference, resolved by the app wrapper. */
  calendarSystem?: CalendarSystem;
```

and add the type import at the top:

```ts
import type { CalendarSystem } from "@plane/calendar";
```

`DateSelectShell` itself does not read the prop — the leaf components do — so no other change to that file.

- [ ] **Step 5: Switch `date-select.tsx` to the surface**

In `packages/blocks/src/property-select/date-select.tsx`, add the imports:

```ts
import { useState } from "react";
import { format } from "date-fns";
import { CalendarSurface } from "@plane/calendar/picker";
import { getCalendarAdapter, resolveCalendarSystem } from "@plane/calendar";
import { renderFormattedDate } from "@plane/utils";
import type { CalendarMonthParts } from "@plane/calendar";
```

Add `calendarSystem = "gregorian"` to the component's props destructure (alongside `formatToken`, `minDate`, `weekStartsOn`), then add the visible-month state right after the existing `isOpen` state:

```ts
// Which month the grid is showing. Seeded from the picked value so reopening a populated field
// lands on the right month; the parent owns it from then on.
const [visibleMonth, setVisibleMonth] = useState<CalendarMonthParts>(() => {
  const parts = getCalendarAdapter(resolveCalendarSystem(calendarSystem)).toParts(value ?? new Date());
  return { year: parts.year, month: parts.month };
});
```

Replace the `<Calendar … />` element that is currently a child of `DateSelectShell` with:

```tsx
<CalendarSurface
  system={calendarSystem}
  mode="single"
  value={value}
  onSelect={(next) => onChange(next)}
  month={visibleMonth}
  onMonthChange={setVisibleMonth}
  weekStartsOn={weekStartsOn}
  minDate={minDate}
  maxDate={maxDate}
  disabled={disabled}
/>
```

`DateSelectShell` renders `children` inside its popover, so the element replaces `<Calendar />` in place with no other change to the file.

The trigger label is built with `date-fns`' `format` today. Replace it so it respects the calendar:

```ts
// before
const label = value ? format(value, formatToken) : "";
// after
const label = renderFormattedDate(value, formatToken, calendarSystem) ?? "";
```

Keep `format` imported only if something else in the file still uses it; otherwise drop the import.

- [ ] **Step 6: Switch `date-range-select.tsx` to the surface**

In `packages/blocks/src/property-select/date-range-select.tsx`, add the same imports and the `calendarSystem = "gregorian"` prop default, plus:

```ts
const [visibleMonth, setVisibleMonth] = useState<CalendarMonthParts>(() => {
  const parts = getCalendarAdapter(resolveCalendarSystem(calendarSystem)).toParts(value.from ?? new Date());
  return { year: parts.year, month: parts.month };
});
```

Replace the `<Calendar mode="range" … />` element with:

```tsx
<CalendarSurface
  system={calendarSystem}
  mode="range"
  value={null}
  range={shown}
  onRangeSelect={(from, to) => {
    const next = { from, to };
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
  weekStartsOn={weekStartsOn}
  minDate={minDate}
  maxDate={maxDate}
  disabled={props.disabled}
/>
```

The `shown = draft ?? value` line above it is what feeds `range`, so the existing half-picked-range behaviour is preserved verbatim. `onChange` is typed `(range: DateRangeValue) => void`, so pass `next` directly.

For the trigger label, this file builds `from` / `to` with `format(value.from, formatToken)` at lines 115–116. Thread `calendarSystem` through `renderFormattedDate` there so the two ends of the range match, keeping the existing `joined` / `mergeRangeLabel` logic as is.

- [ ] **Step 6: Switch `date-range-select.tsx` to the surface**

In `packages/blocks/src/property-select/date-range-select.tsx`, add the same imports and `calendarSystem` prop default, then replace its `<Calendar mode="range" … />` with:

```tsx
<CalendarSurface
  system={calendarSystem}
  mode="range"
  value={null}
  range={shown}
  onRangeSelect={(from, to) => {
    if (!from) return;
    if (!to) {
      setDraft({ from, to: null });
      return;
    }
    setDraft(null);
    onChange({ from, to });
  }}
  month={visibleMonth}
  onMonthChange={setVisibleMonth}
  weekStartsOn={weekStartsOn}
  minDate={minDate}
  maxDate={maxDate}
  disabled={disabled}
/>
```

The existing `shown = draft ?? value` at line 124 is what feeds `range`, so the draft behaviour is preserved.

Update its trigger label to pass `calendarSystem` through as in Step 5.

- [ ] **Step 7: Switch the two direct `Calendar` consumers**

In `apps/web/components/core/filters/date-filter-modal.tsx` and `apps/web/components/inbox/modals/snooze-issue-modal.tsx`, replace the `<Calendar … />` element with `<CalendarSurface … />` using the same mapping as Steps 5 and 6. Both read `calendarSystem` from the profile store:

```ts
import { useUserProfile } from "@/hooks/store/user";
// inside the component
const { calendarSystem } = useUserProfile();
```

- [ ] **Step 8: Run every affected test suite**

Run: `pnpm --filter=@plane/blocks test`
Expected: PASS — both existing files pass **unchanged**. This is the regression gate for the whole task.

Run: `pnpm --filter=@plane/calendar test`
Expected: PASS.

Run: `pnpm check:types`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add packages/calendar packages/blocks apps/web
git commit -m "feat(blocks): render the Persian grid in date pickers"
```

---

## Task 9: The settings UI

**Files:**

- Modify: `apps/web/store/user/profile.store.ts:35-69`
- Modify: `apps/web/components/settings/profile/content/pages/preferences/language-and-timezone-list.tsx:80-116`
- Create: `apps/web/components/settings/profile/content/pages/preferences/calendar-system-preference.tsx`
- Modify: `apps/web/components/power-k/config/preferences-commands.ts:137-165`
- Modify: `packages/i18n/src/locales/en/common.json`

**Interfaces:**

- Consumes: `ECalendarSystem` (Task 6), `useUserProfile` / `updateUserProfile` (existing)
- Produces: `useUserProfile().calendarSystem`, a user-facing control, and the `update_calendar_system` palette command.

- [ ] **Step 1: Add the store getter**

`ProfileStore` holds a single `data: TUserProfile` observable (see `apps/web/store/user/profile.store.ts:46`) — there is no `profile` property and no computed accessors. Add a getter to the class, and add the field to the store's initial `data` so consumers see a defined value before the profile request resolves.

Add to the initial `data` object, after `start_of_the_week: EStartOfTheWeek.SUNDAY,`:

```ts
    calendar_system: ECalendarSystem.GREGORIAN,
```

Add the getter to the class:

```ts
  /**
   * Narrowed so a malformed or pre-migration API response cannot put the UI into a state no
   * adapter handles — `getCalendarAdapter` also falls back, but components read this directly.
   */
  get calendarSystem(): ECalendarSystem {
    return this.data.calendar_system === ECalendarSystem.PERSIAN ? ECalendarSystem.PERSIAN : ECalendarSystem.GREGORIAN;
  }
```

Add the value import next to the existing `EStartOfTheWeek` import at line 15:

```ts
import { ECalendarSystem, EStartOfTheWeek } from "@plane/types";
```

- [ ] **Step 2: Add the translation keys**

In `packages/i18n/src/locales/en/common.json`, add next to the existing `"clear"` key (around line 654):

```json
    "calendar": "Calendar",
    "calendar_persian": "Persian (شمسی)",
    "calendar_gregorian": "Gregorian (میلادی)",
    "calendar_description": "Dates are stored in Gregorian format and displayed in your chosen calendar.",
```

Run: `pnpm --filter=@plane/i18n check:types`
Expected: clean.

Note: only the `en` locale gains these keys. `packages/i18n/scripts/sync-check.ts` flags locales missing keys, and i18next falls back to `en`, so other locales render English until phase 4. Do not run the sync script to "fix" this — copying English into 20 locales is not a translation.

- [ ] **Step 3: Write the preference control**

`apps/web/components/settings/profile/content/pages/preferences/calendar-system-preference.tsx`:

```tsx
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useTranslation } from "@plane/i18n";
import { ECalendarSystem } from "@plane/types";
import { useUserProfile } from "@/hooks/store/user";

const OPTIONS = [
  { value: ECalendarSystem.PERSIAN, labelKey: "calendar_persian" },
  { value: ECalendarSystem.GREGORIAN, labelKey: "calendar_gregorian" },
] as const;

/**
 * Picks which calendar the user sees. A radio group rather than a dropdown: there are exactly two
 * choices and comparing them is the whole decision.
 */
export const CalendarSystemPreference = () => {
  const { t } = useTranslation();
  const { calendarSystem, updateUserProfile } = useUserProfile();

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        {OPTIONS.map((option) => {
          const isActive = calendarSystem === option.value;
          return (
            <label
              key={option.value}
              className={[
                "flex cursor-pointer items-center gap-2 rounded-md border border-subtle px-3 py-2 text-11",
                isActive && "border-custom-primary-100 bg-custom-primary-20/50",
              ]
                .filter(Boolean)
                .join(" ")}
            >
              <input
                type="radio"
                name="calendar-system"
                className="accent-custom-primary-100"
                checked={isActive}
                onChange={() => updateUserProfile({ calendar_system: option.value })}
              />
              {t(`common.${option.labelKey}`)}
            </label>
          );
        })}
      </div>
      <p className="text-11 text-content-tertiary">{t("common.calendar_description")}</p>
    </div>
  );
};
```

- [ ] **Step 4: Place the control**

In `apps/web/components/settings/profile/content/pages/preferences/language-and-timezone-list.tsx`, import `CalendarSystemPreference` and render it between the Language select and the existing `StartOfWeekPreference` (around line 110):

```tsx
<CalendarSystemPreference />
```

- [ ] **Step 5: Add the palette command**

In `apps/web/components/power-k/config/preferences-commands.ts`, add a command next to `update_start_of_week` (around line 137) following the same shape:

```ts
  {
    group: "preferences",
    key: "update_calendar_system",
    title: "Set calendar system",
    render: () => {
      // Follows the existing pattern: only execute after the user picks an option.
      return [
        { label: "Persian (شمسی)", onClick: () => executeCommand("update_calendar_system", ECalendarSystem.PERSIAN) },
        { label: "Gregorian (میلادی)", onClick: () => executeCommand("update_calendar_system", ECalendarSystem.GREGORIAN) },
      ];
    },
  },
```

Match the exact `executeCommand` / `render` shape already used by the sibling commands in that file rather than inventing a new one.

- [ ] **Step 6: Verify types and the existing suites**

Run: `pnpm check:types`
Expected: clean.

Run: `pnpm --filter=@plane/blocks test && pnpm --filter=@plane/calendar test`
Expected: PASS.

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest plane/tests/unit/db/test_profile_calendar_system.py -v`
Expected: PASS — 5 tests.

- [ ] **Step 7: Commit**

```bash
git add apps/web packages/i18n
git commit -m "feat(web): add calendar system preference setting"
```

---

## Task 10: Fix the hardcoded-locale leaks

**Files:**

- Create: `apps/web/helpers/greeting.ts`
- Modify: `apps/web/components/user/user-greetings.tsx:25,30,35,39`
- Modify: `apps/web/components/home/user-greetings.tsx:25,30,35,39`
- Modify: `apps/web/components/profile/time.tsx:20`
- Create: `packages/calendar/tests/locale-leak.test.ts`

**Interfaces:**

- Consumes: `getCalendarAdapter`, `resolveCalendarSystem` (Task 4), `useUserProfile().calendarSystem` (Task 9)
- Produces: `getGreetingParts(date, hour)` and `getClockTime(date, system)`, both shared by all three call sites.

- [ ] **Step 1: Write the failing test**

`packages/calendar/tests/locale-leak.test.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it } from "vitest";
import { getCalendarAdapter, resolveCalendarSystem } from "../src/adapters";
import type { CalendarFormatOptions, CalendarSystem } from "../src/types";

/** Mirrors the adapter call each of the three leaking components will make. */
const formatThroughAdapter = (date: Date, options: CalendarFormatOptions, system?: CalendarSystem) =>
  getCalendarAdapter(resolveCalendarSystem(system)).format(date, options);

describe("locale leaks are routed through the adapter", () => {
  it("formats the clock in both systems", () => {
    const date = new Date(2025, 5, 15, 14, 30);
    expect(formatThroughAdapter(date, { hour: "numeric", minute: "2-digit" })).toBe("02:30 PM");
    expect(formatThroughAdapter(date, { hour: "numeric", minute: "2-digit" }, "persian")).toContain("۲");
  });

  it("formats a greeting hour in both systems", () => {
    const date = new Date(2025, 5, 15, 9);
    expect(formatThroughAdapter(date, { hour: "numeric" })).toBe("9 AM");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: FAIL — the helper functions this test is meant to cover do not exist yet. Write the helpers in Step 3, then re-run.

- [ ] **Step 3: Write the shared helpers**

`apps/web/helpers/greeting.ts`:

```ts
/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { getCalendarAdapter, resolveCalendarSystem } from "@plane/calendar";
import type { CalendarFormatOptions, CalendarSystem } from "@plane/calendar";

/**
 * The greeting bucket a given hour falls into. The hour is read in local time because greetings are
 * a local-time notion — the adapter never touches this, so it is shared by both systems.
 */
export const getGreetingBucket = (hour: number): "morning" | "afternoon" | "evening" => {
  if (hour < 12) return "morning";
  if (hour < 18) return "afternoon";
  return "evening";
};

/**
 * The clock, formatted through the adapter. This replaces three call sites that each pinned
 * `Intl.DateTimeFormat` to `"en-US"`, which is why a Persian user would have seen an English clock
 * next to Persian dates.
 */
export const getClockTime = (date: Date, system: CalendarSystem = "gregorian"): string =>
  getCalendarAdapter(resolveCalendarSystem(system)).format(date, { hour: "numeric", minute: "2-digit" });

/** Escape hatch for a component that needs a specific set of named parts. */
export const formatThroughAdapter = (date: Date, options: CalendarFormatOptions, system?: CalendarSystem): string =>
  getCalendarAdapter(resolveCalendarSystem(system)).format(date, options);
```

- [ ] **Step 4: Update `profile/time.tsx`**

In `apps/web/components/profile/time.tsx`, replace the `Intl.DateTimeFormat` construction at line 20 with a call to the helper:

```ts
const { calendarSystem } = useUserProfile();
const formatted = getClockTime(date, calendarSystem);
```

Delete the now-unused `Intl` construction and its `en-US` literal.

- [ ] **Step 5: Update both greeting components and consolidate**

`apps/web/components/user/user-greetings.tsx` and `apps/web/components/home/user-greetings.tsx` are near-identical, each calling `Intl` with `en-US` at lines 25, 30, 35, and 39. Replace all four calls in each with `formatThroughAdapter` from the shared helper, reading `calendarSystem` from `useUserProfile()`.

Then delete `apps/web/components/home/user-greetings.tsx` and re-point its importers at `apps/web/components/user/user-greetings.tsx`:

```bash
grep -rln "components/home/user-greetings" apps/web | tee /tmp/greeting-importers.txt
```

For each file listed, change the import path to `components/user/user-greetings`. Confirm the two components render the same props before deleting — if they diverge, keep both files and only apply the `Intl` fix, noting the duplication as follow-up rather than expanding this task.

- [ ] **Step 6: Verify**

Run: `pnpm --filter=@plane/calendar test -- --project=unit`
Expected: PASS.

Run: `pnpm check:types`
Expected: clean.

Run: `pnpm check:lint`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add apps/web packages/calendar
git commit -m "fix(web): route clock and greeting Intl calls through the calendar adapter"
```

---

## Task 11: Full verification pass

**Files:**

- No new files. This task is the phase-1 gate.

- [ ] **Step 1: Run every test suite**

Run: `pnpm --filter=@plane/calendar test && pnpm --filter=@plane/blocks test && pnpm --filter=@plane/services test`
Expected: all PASS.

Run: `docker compose -f docker-compose-test.yml run --rm api-tests pytest -m unit -q`
Expected: PASS, including the pre-existing `test_issue_datetime_filters.py`.

- [ ] **Step 2: Run lint, types, and format**

Run: `pnpm check`
Expected: clean across format, lint, and types.

- [ ] **Step 3: Build every package that changed**

Run: `pnpm --filter=@plane/calendar build && pnpm --filter=@plane/utils build && pnpm --filter=@plane/blocks build`
Expected: all succeed.

- [ ] **Step 4: Verify the migration is reversible**

Run: `docker compose -f docker-compose-test.yml run --rm api-tests python manage.py migrate plane zero`
Expected: the `calendar_system` column is dropped without error.

Run: `docker compose -f docker-compose-test.yml run --rm api-tests python manage.py migrate plane`
Expected: it is restored.

- [ ] **Step 5: Walk the manual QA checklist**

Work through the Persian-mode list in the spec's §4.3 with the app running:

- [ ] Today's date is correct on the dashboard, an issue detail page, and the calendar view
- [ ] A 31-day Persian month renders all 31 days
- [ ] Esfand 30 in 1403 and Esfand 29 in 1404 both render correctly
- [ ] Picking a Persian date stores the correct Gregorian value — confirm in the database with `SELECT start_date FROM issues ORDER BY created_at DESC LIMIT 1;`
- [ ] Switching to Gregorian restores today's behaviour everywhere
- [ ] Every existing locale still shows English month names

- [ ] **Step 6: Commit any fixes found in the QA pass**

```bash
git add -A
git commit -m "fix(calendar): address phase 1 QA findings"
```

If the QA pass is clean, skip this step.

---

## Out of scope

Phase 1 deliberately stops here. Not part of this plan:

- **The issue calendar layout, Gantt, and chart axis labels** — phase 2. The `MONTHS_LIST` / `DAYS_LIST` constants in `packages/constants/src/calendar.ts` are still English, so the calendar _layout_ will keep showing `Jun` until then. This is a known, visible gap; it is called out here so it is not mistaken for a bug.
- **Relative filter boundaries and Persian email dates** — phase 3.
- **The `fa-IR` locale and RTL layout** — phase 4, a separate project.
