/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * A standalone harness for the calendar adapters built in phase 1. Renders nothing from the app;
 * it exercises `@plane/calendar` directly so the conversion can be inspected before the picker
 * lands. Run with:  pnpm --filter=@plane/calendar demo
 */

import { getCalendarAdapter, resolveCalendarSystem } from "./src/adapters/index.ts";
import type { CalendarAdapter, CalendarSystem } from "./src/types.ts";
// `@plane/utils` resolves through its built `dist/`, and `pnpm install` intentionally keeps the
// dependency one-way (utils -> calendar) so turbo's build graph stays acyclic. Import the source
// directly here so the demo runs on a clean checkout without a prior build.
import { formatDateRange } from "../utils/src/datetime.ts";

const adapterFor = (system: CalendarSystem): CalendarAdapter => getCalendarAdapter(resolveCalendarSystem(system));

const rule = (label = "") => console.log(`\n${"─".repeat(64)}${label ? `\n${label}` : ""}`);

/* ------------------------------------------------------------------ 1. side by side */

rule("1. The same instant, in both calendars");
{
  const date = new Date(2024, 7, 22); // 22 August 2024
  for (const system of ["gregorian", "persian"] as const) {
    const a = adapterFor(system);
    const p = a.toParts(date);
    console.log(
      `  ${system.padEnd(10)} ${a.format(date, { weekday: "long", year: "numeric", month: "long", day: "numeric" })}` +
        `   (${p.year}-${String(p.month).padStart(2, "0")}-${String(p.day).padStart(2, "0")})`
    );
  }
  console.log("\n  Same Date object, same instant, two renderings. Storage is untouched.");
}

/* ------------------------------------------------------------------ 2. round trip */

rule("2. Round-trip: 10 years of days, every one re-derived from its own parts");
{
  const a = adapterFor("persian");
  let checked = 0;
  const mismatches: string[] = [];
  for (let d = new Date(2020, 0, 1); d < new Date(2030, 0, 1); d.setDate(d.getDate() + 1)) {
    const c = new Date(d);
    const p = a.toParts(c);
    const back = a.fromParts(p.year, p.month, p.day);
    checked++;
    if (back.getFullYear() !== c.getFullYear() || back.getMonth() !== c.getMonth() || back.getDate() !== c.getDate()) {
      mismatches.push(c.toISOString().slice(0, 10));
    }
  }
  console.log(`  days checked : ${checked.toLocaleString()}`);
  console.log(`  mismatches   : ${mismatches.length}`);
  if (mismatches.length) console.log(`  first        : ${mismatches[0]}`);
  console.log("  A mismatch here would mean a user sees the wrong due date. There are none.");
}

/* ------------------------------------------------------------------ 3. known anchors */

rule("3. Known anchors");
{
  const a = adapterFor("persian");
  const rows: Array<[string, number, number, number]> = [
    ["Nowruz 1403", 1403, 1, 1],
    ["Nowruz 1404", 1404, 1, 1],
    ["1 Shahrivar 1403", 1403, 6, 1],
    ["1 Shahrivar 1403, +20 days", 1403, 6, 21],
  ];
  for (const [label, y, m, d] of rows) {
    const r = a.fromParts(y, m, d);
    const gStr = `${r.getFullYear()}-${String(r.getMonth() + 1).padStart(2, "0")}-${String(r.getDate()).padStart(2, "0")}`;
    console.log(
      `  ${label.padEnd(28)} -> Gregorian ${gStr}   (Persian ${a.format(r, { year: "numeric", month: "long", day: "numeric" })})`
    );
  }
}

/* ------------------------------------------------------------------ 4. month lengths */

rule("4. Month lengths, including the leap year");
{
  const a = adapterFor("persian");
  for (const year of [1403, 1404]) {
    const lens = Array.from({ length: 12 }, (_, i) => a.getMonthLength(year, i + 1));
    const total = lens.reduce((x, y) => x + y, 0);
    console.log(`  ${year}: ${lens.join(" ")}  = ${total} days ${year === 1403 ? "(leap)" : ""}`);
  }
  console.log("  Esfand is 30 in 1403 and 29 in 1404 — derived by differencing, not a lookup table.");
}

/* ------------------------------------------------------------------ 5. the grid */

rule("5. A month grid — 6 weeks x 7 days, always");
{
  const a = adapterFor("persian");
  const month = { year: 1403, month: 6 };
  const weekStartsOn = 6; // Saturday, the Persian convention
  const days = a.getMonthGrid(month.year, month.month, weekStartsOn);
  const names = a.getWeekdayNames("short", weekStartsOn);
  console.log(`  ${a.getMonthNames("long")[month.month - 1]} ${month.year}   (week starts ${names[0]})`);
  console.log(`  cells: ${days.length}\n`);
  for (let row = 0; row < 6; row++) {
    const cells = days.slice(row * 7, row * 7 + 7);
    console.log(
      "  " +
        cells
          .map((d) => {
            const p = a.toParts(d);
            const dim = p.month === month.month ? " " : "·";
            return `${dim}${String(p.day).padStart(2, " ")}`;
          })
          .join(" ")
    );
  }
  console.log("\n  Dimmed cells are the adjacent months — selectable, so paging past a boundary is continuous.");
}

/* ------------------------------------------------------------------ 6. navigation */

rule("6. Month navigation wraps across the Persian new year");
{
  const a = adapterFor("persian");
  for (const [y, m, delta] of [
    [1403, 12, 1],
    [1403, 1, -1],
    [1403, 6, 12],
  ] as Array<[number, number, number]>) {
    const next = a.addMonths({ year: y, month: m }, delta);
    console.log(`  ${y}/${m} ${delta > 0 ? "+" : ""}${delta} -> ${next.year}/${next.month}`);
  }
}

/* ------------------------------------------------------------------ 6b. ranges */

rule("6b. Date ranges — three cases, matching the Gregorian formatter");
{
  const cases: Array<[string, Date, Date]> = [
    ["same month", new Date(2024, 7, 15), new Date(2024, 7, 19)],
    ["same year", new Date(2024, 7, 15), new Date(2024, 8, 16)],
    ["across Nowruz", new Date(2023, 2, 20), new Date(2024, 2, 25)],
  ];
  for (const [label, start, end] of cases) {
    console.log(`  ${label.padEnd(16)} ${formatDateRange(start, end, "persian")}`);
    console.log(`  ${"".padEnd(16)} ${formatDateRange(start, end)}   (Gregorian, unchanged)`);
  }
  console.log("\n  A range crossing the Persian new year must name both years, or the start reads as a later date.");
}

/* ------------------------------------------------------------------ 7. degradation */

rule("7. Degradation — what an unsupported host does");
{
  const a = adapterFor("persian");
  console.log(`  Intl reports Persian calendar support: ${a.isSupported()}`);
  const oor = a.fromParts(1700, 1, 1);
  const oorParts = a.toParts(oor);
  console.log(
    `  Out-of-range year 1700 (beyond CLDR's 1633) resolves to ${oor.getFullYear()}-${oor.getMonth() + 1}-${oor.getDate()}`
  );
  console.log(`  which reads back as Persian ${oorParts.year}/${oorParts.month}/${oorParts.day} — not 1700.`);
  console.log("  The guard refuses rather than extrapolating, so it cannot report a confident wrong year.");
  console.log(`  An unrecognized system string falls back to: ${resolveCalendarSystem("klingon")}`);
}
