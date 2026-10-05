/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
// component
import { EUserPermissions, EUserPermissionsLevel } from "@plane/constants";
import { NotAuthorizedView } from "@/components/auth-screens/not-authorized-view";
import { PageHead } from "@/components/core/page-title";
import { SettingsContentWrapper } from "@/components/settings/content-wrapper";
import { BillingPlanSummary } from "@/components/workspace/billing/plan-summary";
import { BillingFeatureFlags } from "@/components/workspace/billing/feature-flags";
// hooks
import { useWorkspace } from "@/hooks/store/use-workspace";
import { useUserPermissions } from "@/hooks/store/user";
// local imports
import { BillingWorkspaceSettingsHeader } from "./header";

function BillingSettingsPage() {
  // store hooks
  const { workspaceUserInfo, allowPermissions } = useUserPermissions();
  const { currentWorkspace } = useWorkspace();
  // derived values
  const canPerformWorkspaceAdminActions = allowPermissions([EUserPermissions.ADMIN], EUserPermissionsLevel.WORKSPACE);
  // Browser title must stay Persian: the English fallback was visible in the tab.
  const pageTitle = currentWorkspace?.name ? `${currentWorkspace.name} - صورتحساب و پلن‌ها` : undefined;

  if (workspaceUserInfo && !canPerformWorkspaceAdminActions) {
    return <NotAuthorizedView section="settings" className="h-auto" />;
  }

  // Without a slug there is nothing to read; the panel would only fire a broken request.
  if (!currentWorkspace?.slug) return null;

  return (
    <SettingsContentWrapper header={<BillingWorkspaceSettingsHeader />} hugging>
      <PageHead title={pageTitle} />
      <div className="flex flex-col gap-4">
        <BillingPlanSummary workspaceSlug={currentWorkspace.slug} />
        <BillingFeatureFlags workspaceSlug={currentWorkspace.slug} />
      </div>
    </SettingsContentWrapper>
  );
}

export default observer(BillingSettingsPage);
