/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import {
  calculateTimeAgo,
  formatDateRange,
  renderFormattedDate,
  renderFormattedDateWithoutYear,
  renderFormattedPayloadDate,
} from "@plane/utils";
import { describe, expect, it } from "vitest";

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
    // CORRECTION to the brief: 22 August 2024 is 1 Shahrivar 1403, not 22 Shahrivar. The brief
    // asserted toContain("۲۲") for this date, which no correct implementation can satisfy.
    // Asserted as an exact string, which is strictly stronger than the three toContain checks
    // the brief used.
    expect(renderFormattedDate(g(2024, 7, 22), undefined, "persian")).toBe("۱ شهریور ۱۴۰۳");
  });

  it("renders a two-digit Persian day", () => {
    // Keeps the intent of the brief's "۲۲" check, on a date that really is 22 Shahrivar 1403.
    expect(renderFormattedDate(g(2024, 8, 12), undefined, "persian")).toBe("۲۲ شهریور ۱۴۰۳");
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

// The token is honoured in Persian mode. Before this, the Persian branch ignored the token entirely
// and always rendered the full year/month/day form, so `renderFormattedDate(d, "MMM dd")` and
// `renderFormattedDate(d)` produced the same Persian string — a caller asking for a compact date
// silently got a year, and the Persian layout stopped corresponding to the Gregorian one.
describe("renderFormattedDate honours the format token in Persian", () => {
  // 22 August 2024 is 1 Shahrivar 1403.
  const d = g(2024, 7, 22);

  it("omits the year for the compact token", () => {
    expect(renderFormattedDate(d, "MMM dd", "persian")).toBe("۱ شهریور");
    // The Gregorian rendering of the same token, for the shape this is meant to mirror.
    expect(renderFormattedDate(d, "MMM dd")).toBe("Aug 22");
  });

  it("leaves the default token's Persian output unchanged", () => {
    // The no-token call is what ~60 production call sites make. It must not drift.
    expect(renderFormattedDate(d, undefined, "persian")).toBe("۱ شهریور ۱۴۰۳");
    // The explicit default token must resolve to the same options, not a different branch.
    expect(renderFormattedDate(d, "MMM dd, yyyy", "persian")).toBe("۱ شهریور ۱۴۰۳");
  });

  it("falls back to the full form for an unmappable token", () => {
    // Mirrors the Gregorian `try/catch` on a bad token: a Persian caller with an unmappable token
    // gets the full form rather than a throw or an empty string.
    expect(renderFormattedDate(d, "not-a-token", "persian")).toBe("۱ شهریور ۱۴۰۳");
    // An inherited Object member is not a token: a bare table lookup would resolve this.
    expect(renderFormattedDate(d, "toString", "persian")).toBe("۱ شهریور ۱۴۰۳");
  });

  it("renders the chart-axis tokens", () => {
    // `apps/web/components/chart/utils.ts` passes exactly these two.
    expect(renderFormattedDate(d, "MMM", "persian")).toBe("شهریور");
    expect(renderFormattedDate(d, "MMM, yyyy", "persian")).toBe("شهریور ۱۴۰۳");
    // Regression pin for the Gregorian side of the same two call sites.
    expect(renderFormattedDate(d, "MMM")).toBe("Aug");
    expect(renderFormattedDate(d, "MMM, yyyy")).toBe("Aug, 2024");
  });

  it("renders the date-picker format tokens", () => {
    // `packages/blocks/src/property-select/date-range-select.tsx` ships these four as Plane's date
    // formats. In Persian the field set is honoured; the separator and the field *order* are the
    // locale's, since the adapter composes its own punctuation.
    expect(renderFormattedDate(d, "yyyy-MM-dd", "persian")).toBe("۱۴۰۳/۰۶/۰۱");
    expect(renderFormattedDate(d, "dd/MM/yyyy", "persian")).toBe("۱۴۰۳/۰۶/۰۱");
    // Regression pin: Gregorian keeps the token's own order and separator exactly.
    expect(renderFormattedDate(d, "yyyy-MM-dd")).toBe("2024-08-22");
    expect(renderFormattedDate(d, "dd/MM/yyyy")).toBe("22/08/2024");
  });

  it("agrees with renderFormattedDateWithoutYear", () => {
    // Two spellings of the same compact shape must not drift apart.
    expect(renderFormattedDate(d, "MMM dd", "persian")).toBe(renderFormattedDateWithoutYear(d, "persian"));
  });
});

describe("formatDateRange with a calendar system", () => {
  it("is unchanged in Gregorian", () => {
    expect(formatDateRange(g(2025, 0, 24), g(2025, 0, 28))).toBe("Jan 24 - 28, 2025");
  });

  it("keeps every Gregorian branch byte-for-byte", () => {
    // The Persian rewrite wraps the Gregorian branches in an `isPersian` guard; these pin all four
    // of them plus the two single-date branches so the refactor cannot silently reshape them.
    expect(formatDateRange(g(2025, 0, 24), g(2025, 1, 6))).toBe("Jan 24 - Feb 06, 2025");
    expect(formatDateRange(g(2024, 11, 28), g(2025, 0, 4))).toBe("Dec 28, 2024 - Jan 04, 2025");
    expect(formatDateRange(g(2025, 0, 24), null)).toBe("Jan 24, 2025");
    expect(formatDateRange(null, g(2025, 0, 24))).toBe("Jan 24, 2025");
    expect(formatDateRange(null, null)).toBe("");
  });

  it("renders a Persian same-month range", () => {
    // CORRECTION to the brief: 15–19 August 2024 is 25–29 *Mordad* 1403 (Persian month 5), not
    // "24–28 Shahrivar". The brief's toContain("شهریور") is unsatisfiable for these dates —
    // Shahrivar 1403 does not begin until 22 August 2024. The year ۱۴۰۳ was correct.
    const formatted = formatDateRange(g(2024, 7, 15), g(2024, 7, 19), "persian");
    expect(formatted).toBe("مرداد ۲۵ - ۲۹, ۱۴۰۳");
  });

  it("renders a Persian cross-month range", () => {
    // Guards the non-same-month branch, which the brief's implementation never got to run.
    expect(formatDateRange(g(2024, 7, 15), g(2024, 8, 6), "persian")).toBe("۲۵ مرداد - ۱۶ شهریور, ۱۴۰۳");
  });

  it("renders both years for a Persian range that crosses a new year", () => {
    // 20 Mar 2023 is 29 Esfand 1401; 25 Mar 2024 is 6 Farvardin 1403 — the range crosses Nowruz.
    // The old two-case implementation appended only the end's year, producing
    // "۲۹ اسفند - ۶ فروردین, ۱۴۰۳", which asserts the start is Esfand 29 *1403* — a date
    // 11 months after the range's own end. Each side now carries its own year.
    expect(formatDateRange(g(2023, 2, 20), g(2024, 2, 25), "persian")).toBe("۲۹ اسفند ۱۴۰۱ - ۶ فروردین ۱۴۰۳");
    // The Gregorian equivalent for the same range, for reference: "Mar 20, 2023 - Mar 25, 2024".
  });

  it("renders a Persian new-year range inside a single Gregorian year", () => {
    // 19 Mar 2025 is 29 Esfand 1403, 26 Mar 2025 is 6 Farvardin 1404.
    expect(formatDateRange(g(2025, 2, 19), g(2025, 2, 26), "persian")).toBe("۲۹ اسفند ۱۴۰۳ - ۶ فروردین ۱۴۰۴");
  });

  it("renders both years for a Persian range across two years in a different month", () => {
    // 5 Jan 2024 is 15 Dey 1402, 10 Jan 2025 is 21 Dey 1403. Same month, different years: the
    // month-only shortcut would have shown ۱۴۰۳ on both sides and hidden a full year.
    expect(formatDateRange(g(2024, 0, 5), g(2025, 0, 10), "persian")).toBe("۱۵ دی ۱۴۰۲ - ۲۱ دی ۱۴۰۳");
  });

  it("keeps the Persian same-year cross-month and same-month forms unchanged", () => {
    // The two pre-existing Persian shapes must survive the third branch being added.
    expect(formatDateRange(g(2024, 7, 15), g(2024, 8, 6), "persian")).toBe("۲۵ مرداد - ۱۶ شهریور, ۱۴۰۳");
    expect(formatDateRange(g(2024, 7, 15), g(2024, 7, 19), "persian")).toBe("مرداد ۲۵ - ۲۹, ۱۴۰۳");
  });

  it("keeps every Gregorian branch on a new-year range unchanged", () => {
    // The Persian third branch is a sibling of these, not a replacement: the Gregorian path that
    // ~100 call sites use must keep printing "MMM dd, yyyy" on both sides across a year boundary.
    expect(formatDateRange(g(2023, 2, 20), g(2024, 2, 25))).toBe("Mar 20, 2023 - Mar 25, 2024");
    expect(formatDateRange(g(2025, 2, 19), g(2025, 2, 26))).toBe("Mar 19 - 26, 2025");
    expect(formatDateRange(g(2024, 0, 5), g(2025, 0, 10))).toBe("Jan 05, 2024 - Jan 10, 2025");
    expect(formatDateRange(g(2024, 7, 15), g(2024, 8, 6))).toBe("Aug 15 - Sep 06, 2024");
  });
});

describe("renderFormattedDateWithoutYear with a calendar system", () => {
  it("is unchanged by default and in explicit Gregorian", () => {
    expect(renderFormattedDateWithoutYear("2024-01-01")).toBe("Jan 01");
    expect(renderFormattedDateWithoutYear("2024-01-01", "gregorian")).toBe("Jan 01");
  });

  it("renders Persian when asked", () => {
    expect(renderFormattedDateWithoutYear("2024-01-01", "persian")).toBe("۱۱ دی");
  });
});

// The boundary that keeps storage Gregorian. renderFormattedPayloadDate takes no `system` and
// must never gain one; this test is the tripwire for that.
describe("renderFormattedPayloadDate", () => {
  it("stays Gregorian yyyy-MM-dd", () => {
    expect(renderFormattedPayloadDate(g(2024, 7, 22))).toBe("2024-08-22");
    expect(renderFormattedPayloadDate("2024-08-22")).toBe("2024-08-22");
    // 1 Shahrivar 1403 in Persian, but the payload must carry the Gregorian instant.
    expect(renderFormattedPayloadDate(g(2024, 7, 22))).not.toContain("۱۴۰۳");
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
