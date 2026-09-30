/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useState } from "react";
// ui
import { useTranslation } from "@plane/i18n";
import { CalendarSurface, getCalendarAdapter } from "@plane/blocks/property-select";
import type { CalendarMonthParts } from "@plane/blocks/property-select";
import { Button } from "@makeplane/propel/components/button";
import { Dialog, DialogActions, DialogBody, DialogContent, DialogMain } from "@makeplane/propel/components/dialog";
// hooks
import { useUserProfile } from "@/hooks/store/user";

export type InboxIssueSnoozeModalProps = {
  isOpen: boolean;
  value: Date | undefined;
  onConfirm: (value: Date) => void;
  handleClose: () => void;
};

export function InboxIssueSnoozeModal(props: InboxIssueSnoozeModalProps) {
  const { isOpen, handleClose, value, onConfirm } = props;
  // store hooks
  const { data: userProfile } = useUserProfile();
  const calendarSystem = userProfile?.calendar_system ?? "gregorian";
  // states
  const [date, setDate] = useState(value || new Date());
  // The month the Persian grid shows. The Gregorian branch re-seeds itself from `defaultMonth` on
  // every mount, so this only steers the Persian one.
  const [visibleMonth, setVisibleMonth] = useState<CalendarMonthParts>(() => {
    const { year, month } = getCalendarAdapter(calendarSystem).toParts(value || new Date());
    return { year, month };
  });
  //hooks
  const { t } = useTranslation();

  return (
    <Dialog
      open={isOpen}
      onOpenChange={(open) => {
        if (!open) handleClose();
      }}
    >
      <DialogContent size="xs" aria-label={t("inbox_issue.actions.snooze")}>
        <DialogMain>
          <DialogBody>
            <CalendarSurface
              system={calendarSystem}
              mode="single"
              value={date ? new Date(date) : null}
              onSelect={(next) => {
                if (!next) return;
                setDate(next);
              }}
              month={visibleMonth}
              onMonthChange={setVisibleMonth}
              defaultMonth={date ? new Date(date) : undefined}
              showOutsideDays
              minDate={new Date()}
            />
          </DialogBody>
        </DialogMain>
        <DialogActions>
          <Button
            variant="primary"
            size="sm"
            stretch="auto"
            onClick={() => {
              handleClose();
              onConfirm(date);
            }}
            label={t("inbox_issue.actions.snooze")}
          />
        </DialogActions>
      </DialogContent>
    </Dialog>
  );
}
