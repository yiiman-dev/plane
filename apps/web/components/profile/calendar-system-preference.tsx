/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { Select, SelectDropdownPlacementContext } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { ECalendarSystem } from "@plane/types";
// components
import { SettingsControlItem } from "@/components/settings/control-item";
// hooks
import { useUserProfile } from "@/hooks/store/user";

type TCalendarSystemOption = {
  value: ECalendarSystem;
  label: string;
};

// A dropdown rather than a radio group: this settings list is a column of `SettingsControlItem`s,
// each with a single right-aligned control, and a two-option radio pair breaks that rhythm.
const CALENDAR_SYSTEM_OPTIONS: TCalendarSystemOption[] = [
  { value: ECalendarSystem.PERSIAN, label: "Persian (شمسی)" },
  { value: ECalendarSystem.GREGORIAN, label: "Gregorian (میلادی)" },
];

// The dropdown opens flush with the control's right edge, matching `StartOfWeekPreference`.
const DROPDOWN_PLACEMENT = { side: "bottom", align: "end" } as const;

export const CalendarSystemPreference = observer(function CalendarSystemPreference(props: {
  option: { title: string; description: string };
}) {
  // hooks
  const { calendarSystem, updateUserProfile } = useUserProfile();

  const handleCalendarSystemChange = async (val: ECalendarSystem) => {
    try {
      await updateUserProfile({ calendar_system: val });
      setToast({ type: "success", title: "Success", message: "Calendar system updated successfully" });
    } catch (_error) {
      setToast({ type: "error", title: "Update failed", message: "Please try again later." });
    }
  };

  // derived values
  const selectedOption = CALENDAR_SYSTEM_OPTIONS.find((option) => option.value === calendarSystem) ?? null;

  return (
    <SettingsControlItem
      title={props.option.title}
      description={props.option.description}
      control={
        <SelectDropdownPlacementContext.Provider value={DROPDOWN_PLACEMENT}>
          <Select<TCalendarSystemOption>
            getValues={() => CALENDAR_SYSTEM_OPTIONS}
            value={selectedOption}
            onChange={(val) => void handleCalendarSystemChange(val as ECalendarSystem)}
            getOptionValue={(option) => option.value}
            getOptionLabel={(option) => option.label}
            showSearch={false}
            pinSelected={false}
            contentSizing="anchor"
          >
            <Select.Trigger<TCalendarSystemOption> variant="select-md" className="w-42 max-w-full border-subtle-1">
              {(options) => <span className="min-w-0 grow truncate text-left">{options[0]?.label}</span>}
            </Select.Trigger>
          </Select>
        </SelectDropdownPlacementContext.Provider>
      }
    />
  );
});
