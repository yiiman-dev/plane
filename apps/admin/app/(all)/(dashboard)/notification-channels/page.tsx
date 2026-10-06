/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import useSWR from "swr";
// components
import { PageWrapper } from "@/components/common/page-wrapper";
import { Skeleton } from "@/components/common/skeleton";
// hooks
import { useInstance } from "@/hooks/store";
// types
import type { Route } from "./+types/page";
// local
import { InstanceBaleConfigForm } from "./bale-config-form";
import { InstanceKavenegarConfigForm } from "./kavenegar-config-form";

const InstanceNotificationChannelsPage = observer(function InstanceNotificationChannelsPage(
  _props: Route.ComponentProps
) {
  // store
  const { config, formattedConfig, fetchInstanceConfigurations } = useInstance();

  const { isLoading } = useSWR("INSTANCE_CONFIGURATIONS", () => fetchInstanceConfigurations());

  // the instance payload is the source of truth, the stored configuration is only a fallback
  const isKavenegarConfigured =
    config?.has_kavenegar_configured ??
    Boolean(formattedConfig?.KAVENEGAR_API_KEY && formattedConfig?.KAVENEGAR_SENDER_LINE);
  const isBaleConfigured = config?.has_bale_configured ?? Boolean(formattedConfig?.BALE_BOT_TOKEN);

  return (
    <PageWrapper
      header={{
        title: "Notification channels",
        description:
          "Configure the providers that deliver notifications to your members. Members pick the events they want" +
          " per channel in their own profile settings.",
      }}
    >
      {!isLoading && formattedConfig ? (
        <div className="space-y-10">
          <InstanceKavenegarConfigForm config={formattedConfig} isConfigured={isKavenegarConfigured} />
          <InstanceBaleConfigForm config={formattedConfig} isConfigured={isBaleConfigured} />
        </div>
      ) : (
        <Skeleton className="space-y-10">
          <Skeleton.Item height="50px" width="75%" />
          <Skeleton.Item height="50px" width="75%" />
          <Skeleton.Item height="50px" width="40%" />
          <Skeleton.Item height="50px" width="40%" />
          <Skeleton.Item height="50px" width="20%" />
        </Skeleton>
      )}
    </PageWrapper>
  );
});

export const meta: Route.MetaFunction = () => [{ title: "Notification Channels - God Mode" }];

export default InstanceNotificationChannelsPage;
