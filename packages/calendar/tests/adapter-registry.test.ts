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
