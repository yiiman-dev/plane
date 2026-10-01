/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import React from "react";
import { Command } from "cmdk";
// plane imports
import { ECalendarSystem } from "@plane/types";
// local imports
import { PowerKModalCommandItem } from "../../modal/command-item";

const CALENDAR_SYSTEM_OPTIONS = [
  { value: ECalendarSystem.PERSIAN, label: "Persian (شمسی)" },
  { value: ECalendarSystem.GREGORIAN, label: "Gregorian (میلادی)" },
];

type Props = {
  onSelect: (calendarSystem: ECalendarSystem) => void;
};

export function PowerKPreferencesCalendarSystemMenu(props: Props) {
  const { onSelect } = props;

  return (
    <Command.Group>
      {CALENDAR_SYSTEM_OPTIONS.map((option) => (
        <PowerKModalCommandItem key={option.value} onSelect={() => onSelect(option.value)} label={option.label} />
      ))}
    </Command.Group>
  );
}
