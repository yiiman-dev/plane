/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { describe, expect, it, vi } from "vitest";

/**
 * Simulates a runtime whose ICU build has no `calendar: "persian"` — an older Safari, or a
 * stripped-down Node image. There the real `Intl` silently reports Gregorian month numbers for a
 * Persian locale, which would make the Persian adapter print Persian month names over Gregorian
 * dates. Only the exported predicate is replaced; the adapters themselves stay the real ones, so
 * the registry's own branch is what is under test.
 */
vi.mock("../src/adapters/persian", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../src/adapters/persian")>();
  return { ...actual, isPersianCalendarSupported: () => false };
});

const { getCalendarAdapter, gregorianCalendar, persianCalendar, resolveCalendarSystem } =
  await import("../src/adapters");

describe("getCalendarAdapter on a host without Intl Persian support", () => {
  it("returns the Gregorian adapter for a Persian request", () => {
    expect(getCalendarAdapter("persian").system).toBe("gregorian");
    // Identity, not just the same system label: callers cache on this object, so handing back a
    // look-alike would defeat the cache in a way `system` alone cannot show.
    expect(getCalendarAdapter("persian")).toBe(gregorianCalendar);
    expect(getCalendarAdapter("persian")).not.toBe(persianCalendar);
  });

  it("still leaves Gregorian requests on the Gregorian adapter", () => {
    expect(getCalendarAdapter("gregorian")).toBe(gregorianCalendar);
  });

  it("leaves the system itself unresolved as Persian — the guard belongs to the adapter lookup", () => {
    // Preference resolution is host-independent: the user's setting is Persian, and silently
    // rewriting it to "gregorian" here would persist the wrong preference on a shared device.
    expect(resolveCalendarSystem("persian")).toBe("persian");
  });
});
