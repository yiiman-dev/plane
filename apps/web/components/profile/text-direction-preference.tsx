/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { Select, SelectDropdownPlacementContext } from "@plane/blocks/select";
import { setToast } from "@plane/blocks/toast";
import { ETextDirection } from "@plane/types";
// components
import { SettingsControlItem } from "@/components/settings/control-item";
// hooks
import { useUserProfile } from "@/hooks/store/user";

type TTextDirectionOption = {
  value: ETextDirection;
  label: string;
};

// A dropdown rather than a radio group, matching `CalendarSystemPreference` in the same
// settings list: every control there is a single right-aligned `Select`.
const TEXT_DIRECTION_OPTIONS: TTextDirectionOption[] = [
  { value: ETextDirection.RTL, label: "Right-to-left (راست‌چین)" },
  { value: ETextDirection.LTR, label: "Left-to-right (چپ‌چین)" },
];

// The dropdown opens flush with the control's right edge, matching `StartOfWeekPreference`.
const DROPDOWN_PLACEMENT = { side: "bottom", align: "end" } as const;

export const TextDirectionPreference = observer(function TextDirectionPreference(props: {
  option: { title: string; description: string };
}) {
  // hooks
  const { textDirection, updateUserProfile } = useUserProfile();

  const handleTextDirectionChange = async (val: ETextDirection) => {
    try {
      // The store reverts and swallows a failed profile update, resolving to undefined. Treating
      // that as success would tell the user their preference is saved when it is not, and the
      // next reload would silently flip the content back.
      const updatedProfile = await updateUserProfile({ text_direction: val });
      if (!updatedProfile) throw new Error("Profile update failed");
      setToast({ type: "success", title: "Success", message: "Text direction updated successfully" });
    } catch (_error) {
      setToast({ type: "error", title: "Update failed", message: "Please try again later." });
    }
  };

  // derived values
  const selectedOption = TEXT_DIRECTION_OPTIONS.find((option) => option.value === textDirection) ?? null;

  return (
    <SettingsControlItem
      title={props.option.title}
      description={props.option.description}
      control={
        <SelectDropdownPlacementContext.Provider value={DROPDOWN_PLACEMENT}>
          <Select<TTextDirectionOption>
            getValues={() => TEXT_DIRECTION_OPTIONS}
            value={selectedOption}
            onChange={(val) => void handleTextDirectionChange(val as ETextDirection)}
            getOptionValue={(option) => option.value}
            getOptionLabel={(option) => option.label}
            showSearch={false}
            pinSelected={false}
            contentSizing="anchor"
          >
            <Select.Trigger<TTextDirectionOption> variant="select-md" className="w-42 max-w-full border-subtle-1">
              {(options) => <span className="min-w-0 grow truncate text-left">{options[0]?.label}</span>}
            </Select.Trigger>
          </Select>
        </SelectDropdownPlacementContext.Provider>
      }
    />
  );
});
