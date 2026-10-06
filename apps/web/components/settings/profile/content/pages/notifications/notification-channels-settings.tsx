/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useEffect, useState } from "react";
import useSWR from "swr";
// plane imports
import { useTranslation } from "@plane/i18n";
import type { IUserNotificationChannel, IUserNotificationChannels } from "@plane/types";
// services
import { UserService } from "@/services/user.service";
// local imports
import { NotificationChannelForm } from "./notification-channel-form";

const NOTIFICATION_CHANNELS_SWR_KEY = "CURRENT_USER_NOTIFICATION_CHANNELS";

// services
const userService = new UserService();

/**
 * Renders one independent section per delivery channel returned by
 * GET /api/users/me/notification-channels/. The aggregate is mirrored into local state so a
 * mutation that answers with the fresh aggregate updates the UI without waiting for a refetch.
 */
export function NotificationChannelsSettings() {
  const { t } = useTranslation();
  const [channels, setChannels] = useState<IUserNotificationChannel[]>([]);

  const { data, error, mutate } = useSWR(NOTIFICATION_CHANNELS_SWR_KEY, () =>
    userService.currentUserNotificationChannels()
  );

  useEffect(() => {
    if (!data?.channels) return;
    setChannels(data.channels);
  }, [data]);

  const handleAggregateUpdate = (aggregate: IUserNotificationChannels) => {
    setChannels(aggregate?.channels ?? []);
  };

  // a failing channels fetch must not take the email channel down with it
  if (error) {
    return (
      <p className="text-caption-md-regular text-danger-primary">
        {t("account_settings.notifications.channels.channels_load_failed")}
      </p>
    );
  }

  if (!data?.channels) return null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-1">
        <h3 className="text-body-md-medium text-primary">{t("account_settings.notifications.channels.heading")}</h3>
        <p className="text-caption-md-regular text-secondary">
          {t("account_settings.notifications.channels.description")}
        </p>
      </div>
      {channels.map((channel) => (
        <NotificationChannelForm
          key={channel.channel}
          channel={channel}
          onAggregateUpdate={handleAggregateUpdate}
          onRevalidate={() => mutate()}
        />
      ))}
    </div>
  );
}
