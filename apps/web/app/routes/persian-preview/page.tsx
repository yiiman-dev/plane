/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
import { DateRangeSelect, DateSelect } from "@plane/blocks/property-select";

/**
 * A scratch route for eyeballing the calendar pickers without signing in. It mounts the real
 * `DateSelect` / `DateRangeSelect` from `@plane/blocks` — the same components the issue and cycle
 * forms use — so what appears here is the shipped picker, not a reconstruction.
 */
export default function PersianPreviewPage() {
  const [system, setSystem] = useState<"gregorian" | "persian">("persian");
  const [one, setOne] = useState<Date | null>(new Date(2024, 7, 22));
  const [range, setRange] = useState<{ from: Date | null; to: Date | null }>({
    from: new Date(2024, 7, 15),
    to: new Date(2024, 7, 19),
  });

  return (
    <div className="flex min-h-screen flex-col gap-8 bg-canvas p-10" dir="rtl">
      <div className="flex items-center gap-2">
        {(["persian", "gregorian"] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSystem(s)}
            className={[
              "rounded-md border px-4 py-2 text-13 font-medium",
              system === s ? "border-primary-custom bg-primary-custom/10 text-primary-custom" : "border-subtle",
            ].join(" ")}
          >
            {s === "persian" ? "شمسی" : "میلادی — رفتار امروز"}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap gap-12">
        <div className="flex flex-col gap-2">
          <span className="text-content-tertiary text-11">تاریخ سررسید — DateSelect</span>
          <DateSelect
            value={one}
            onChange={setOne}
            calendarSystem={system}
            weekStartsOn={6}
            formatToken="MMM dd, yyyy"
            variant="select-ghost-md"
            clearable
          />
          <span className="text-content-secondary text-11" dir="ltr">
            what gets stored: {one ? one.toISOString().slice(0, 10) : "null"}
          </span>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-content-tertiary text-11">بازهٔ سیکل — DateRangeSelect</span>
          <DateRangeSelect
            value={range}
            onChange={setRange}
            calendarSystem={system}
            weekStartsOn={6}
            variant="select-ghost-md"
            clearable
          />
        </div>
      </div>

      <p className="text-content-tertiary max-w-2xl text-12">
        هر دو کامپوننت واقعیِ <code>@plane/blocks</code> هستند. با تعویض حالت میلادی، خروجی دقیقاً همان چیزی است که کاربران
        امروز می‌بینند — تاریخ‌ها همیشه میلادی ذخیره می‌شوند و فقط لایهٔ نمایش عوض می‌شود.
      </p>
    </div>
  );
}
