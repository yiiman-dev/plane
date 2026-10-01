/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// The calendar-aware month grid, re-exported rather than reached for at `@plane/calendar`
// directly: `apps/web` depends on this package, not on `@plane/calendar`, and the dependency edge
// runs blocks → calendar so a web file importing it from here adds no package dependency of its own.
// The label helpers and the system resolver ride along for the same reason: the issue calendar
// layout renders its own month titles and weekday columns rather than reusing `CalendarSurface`,
// and it must read those names from the same adapter the grid is drawn in.
export {
  CalendarSurface,
  getCalendarAdapter,
  isWeekend,
  monthName,
  resolveCalendarSystem,
  weekdayNames,
} from "@plane/calendar";
export type { CalendarMonthParts, CalendarSurfaceProps, CalendarSystem } from "@plane/calendar";
export { CycleSelect } from "./cycle-select";
export type { CycleOption, CycleSelectProps } from "./cycle-select";
export { DateSelect } from "./date-select";
export type { DateSelectProps } from "./date-select";
export { DateRangeSelect } from "./date-range-select";
export type { DateRangeSelectProps, DateRangeValue } from "./date-range-select";
export type { DateSelectCommonProps, WeekStart } from "./date-select-shell";
export { EstimateSelect } from "./estimate-select";
export type { EstimateOption, EstimateSelectProps } from "./estimate-select";
export { IntakeStateSelect } from "./intake-state-select";
export type { IntakeStateOption, IntakeStateSelectProps } from "./intake-state-select";
export { LabelSelect } from "./label-select/label-select";
export type { LabelOption, LabelSelectProps } from "./label-select/label-select";
export { MemberSelect, MAX_TRIGGER_AVATARS } from "./member-select";
export type { MemberOption, MemberSelectProps, MemberSelectVariant } from "./member-select";
export { ModuleSelect } from "./module-select";
export type { ModuleOption, ModuleSelectProps } from "./module-select";
export { PrioritySelect } from "./priority-select";
export type { PriorityOption, PrioritySelectProps } from "./priority-select";
export { ProjectSelect } from "./project-select";
export type { ProjectOption, ProjectSelectProps } from "./project-select";
export { StateSelect } from "./state-select";
export type { StateOption, StateSelectProps } from "./state-select";
