/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// plane imports
import { useTranslation } from "@plane/i18n";
import { CalendarOutline } from "@makeplane/propel/icons";
import { cn, renderFormattedDate, getDate } from "@plane/utils";
// hooks
import { useUserProfile } from "@/hooks/store/user";

export type TReadonlyDateProps = {
  className?: string;
  hideIcon?: boolean;
  value: Date | string | null;
  placeholder?: string;
  formatToken?: string;
};

export const ReadonlyDate = observer(function ReadonlyDate(props: TReadonlyDateProps) {
  const { className, hideIcon = false, value, placeholder, formatToken } = props;

  const { t } = useTranslation();
  const { calendarSystem } = useUserProfile();
  // `formatToken` occupies the second slot, so the calendar system is passed third.
  const formattedDate = value ? renderFormattedDate(getDate(value), formatToken, calendarSystem) : null;

  return (
    <div className={cn("flex items-center gap-1 text-13", className)}>
      {!hideIcon && <CalendarOutline className="size-4 flex-shrink-0" />}
      <span className="flex-grow truncate">{formattedDate ?? placeholder ?? t("common.none")}</span>
    </div>
  );
});
