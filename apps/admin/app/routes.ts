/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { index, layout, route } from "@react-router/dev/routes";
import type { RouteConfig } from "@react-router/dev/routes";

export default [
  layout("./(all)/(home)/layout.tsx", [index("./(all)/(home)/page.tsx")]),
  layout("./(all)/(dashboard)/layout.tsx", [
    route("general", "./(all)/(dashboard)/general/page.tsx"),
    route("workspace", "./(all)/(dashboard)/workspace/page.tsx"),
    route("workspace/create", "./(all)/(dashboard)/workspace/create/page.tsx"),
    route("email", "./(all)/(dashboard)/email/page.tsx"),
    route("notification-channels", "./(all)/(dashboard)/notification-channels/page.tsx"),
    // Every billing screen the tab strip links to has to be registered here:
    // react-router uses this explicit config, so a page file that is not listed
    // falls through to the catch-all 404 while the navigation still shows its
    // tab. The workspaces and feature-flag pages were linked but unregistered.
    route("billing/gateways", "./(all)/(dashboard)/billing/gateways/page.tsx"),
    route("billing/routing", "./(all)/(dashboard)/billing/routing/page.tsx"),
    route("billing/plans", "./(all)/(dashboard)/billing/plans/page.tsx"),
    route("billing/workspaces", "./(all)/(dashboard)/billing/workspaces/page.tsx"),
    route("billing/workspaces/:slug", "./(all)/(dashboard)/billing/workspaces/[slug]/page.tsx"),
    route("billing/feature-flags", "./(all)/(dashboard)/billing/feature-flags/page.tsx"),
    route("billing/access-log", "./(all)/(dashboard)/billing/access-log/page.tsx"),
    route("billing/transactions", "./(all)/(dashboard)/billing/transactions/page.tsx"),
    route("authentication", "./(all)/(dashboard)/authentication/page.tsx"),
    route("authentication/github", "./(all)/(dashboard)/authentication/github/page.tsx"),
    route("authentication/gitlab", "./(all)/(dashboard)/authentication/gitlab/page.tsx"),
    route("authentication/google", "./(all)/(dashboard)/authentication/google/page.tsx"),
    route("authentication/gitea", "./(all)/(dashboard)/authentication/gitea/page.tsx"),
    route("ai", "./(all)/(dashboard)/ai/page.tsx"),
    route("image", "./(all)/(dashboard)/image/page.tsx"),
  ]),
  // Catch-all route for 404 handling - must be last
  route("*", "./components/404.tsx"),
] satisfies RouteConfig;
