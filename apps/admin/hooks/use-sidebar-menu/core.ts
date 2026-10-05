/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { BrainCog, CreditCard } from "lucide-react";
// plane imports
import {
  ImageOutline,
  LockOutline,
  MailOutline,
  PhoneOutline,
  SettingsOutline,
  WorkspaceOutline,
} from "@makeplane/propel/icons";
// types
import type { TSidebarMenuItem } from "./types";

export type TCoreSidebarMenuKey =
  | "general"
  | "email"
  | "notification-channels"
  | "billing"
  | "workspace"
  | "authentication"
  | "ai"
  | "image";

export const coreSidebarMenuLinks: Record<TCoreSidebarMenuKey, TSidebarMenuItem> = {
  general: {
    Icon: SettingsOutline,
    name: "General",
    description: "Identify your instances and get key details.",
    href: `/general/`,
  },
  email: {
    Icon: MailOutline,
    name: "Email",
    description: "Configure your SMTP controls.",
    href: `/email/`,
  },
  "notification-channels": {
    Icon: PhoneOutline,
    name: "Notification channels",
    description: "Configure SMS and Bale delivery for notifications.",
    href: `/notification-channels/`,
  },
  billing: {
    Icon: CreditCard,
    name: "Billing & payments",
    description: "Configure Iranian payment gateways, routing, plans and invoices.",
    href: `/billing/gateways/`,
  },
  workspace: {
    Icon: WorkspaceOutline,
    name: "Workspaces",
    description: "Manage all workspaces on this instance.",
    href: `/workspace/`,
  },
  authentication: {
    Icon: LockOutline,
    name: "Authentication",
    description: "Configure authentication modes.",
    href: `/authentication/`,
  },
  ai: {
    Icon: BrainCog,
    name: "Artificial intelligence",
    description: "Configure your OpenAI creds.",
    href: `/ai/`,
  },
  image: {
    Icon: ImageOutline,
    name: "Images in Plane",
    description: "Allow third-party image libraries.",
    href: `/image/`,
  },
};
