/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { BillingService as BillingServiceClass } from "./billing.service";

export * from "./billing.service";

/**
 * Ready to use billing service. The API resources are singleton in practice, so the instance is
 * created once here instead of in every screen that talks to the billing endpoints.
 */
export const BillingService = new BillingServiceClass();

/* SWR cache keys */

/** Static keys for the singleton and non filtered billing resources. */
export const BILLING_GATEWAYS = "billing-gateways";
export const BILLING_ROUTING = "billing-routing";
export const BILLING_PLANS = "billing-plans";

/**
 * Transactions and invoices are server side filtered and paginated, so their cache key has to
 * include the whole query. The parameter object is serialised in declaration order to keep the
 * key stable across renders.
 */
export const buildBillingListKey = (
  resource:
    | "billing-access-log"
    | "billing-admin-workspaces"
    | "billing-feature-flags"
    | "billing-invoices"
    | "billing-plan-quote"
    | "billing-sms-report"
    | "billing-transactions"
    | "billing-workspace-entitlement"
    | "billing-workspace-feature-flags",
  params: Record<string, string | number | undefined> = {}
): string => {
  const query = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== "" && value !== null)
    .toSorted(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${String(value)}`)
    .join("&");

  return query ? `${resource}?${query}` : resource;
};

export const BILLING_TRANSACTIONS = (params: Record<string, string | number | undefined> = {}) =>
  buildBillingListKey("billing-transactions", params);

export const BILLING_INVOICES = (params: Record<string, string | number | undefined> = {}) =>
  buildBillingListKey("billing-invoices", params);

/* public checkout */

/** The active plan list is a plain, unfiltered read. */
export const BILLING_PUBLIC_PLANS = "billing-public-plans";

/**
 * A quote is priced per plan, seat count and cycle, so the cache key carries all three. The
 * backend rejects an out of range seat count with a 400, so seats is part of the key rather than
 * being folded into the fetch body.
 */
export const BILLING_PLAN_QUOTE = (planCode: string, seats: number, cycle: string) =>
  buildBillingListKey("billing-plan-quote", { cycle, planCode, seats });

/** One cache key per order, used by the result screen while it polls the verification state. */
export const BILLING_ORDER_STATUS = (transactionId: string) => `billing-order-status-${transactionId}`;

/**
 * A plan's grant set belongs to the plan, not to the screen that edits it, so the
 * key is the plan id and two plans edited in one session never share an entry.
 */
export const BILLING_PLAN_FEATURE_FLAGS = (planId: string) => `billing-plan-feature-flags-${planId}`;

/**
 * The audit trail is filtered by view, workspace and page, so its key carries the
 * whole query: one entry per filter combination, never one entry for every filter.
 */
export const BILLING_ACCESS_LOG = (params: Record<string, string | number | undefined> = {}) =>
  buildBillingListKey("billing-access-log", params);

/**
 * The SMS cost report is filtered by workspace and paged, so its key carries the
 * whole query for the same reason the other filtered lists do.
 */
export const BILLING_SMS_REPORT = (params: Record<string, string | number | undefined> = {}) =>
  buildBillingListKey("billing-sms-report", params);

/* workspace scoped reads */

/**
 * Entitlement and feature flags are read per workspace, so the cache key carries the slug. Two
 * workspaces in the same session must never share a cache entry.
 */
export const BILLING_WORKSPACE_ENTITLEMENT = (workspaceSlug: string) =>
  buildBillingListKey("billing-workspace-entitlement", { workspaceSlug });

export const BILLING_WORKSPACE_FEATURE_FLAGS = (workspaceSlug: string) =>
  buildBillingListKey("billing-workspace-feature-flags", { workspaceSlug });

/* admin workspace billing */

/**
 * One key per workspace, because two tenants must never share a cache entry
 * for their money. The slug is the whole key: a detail page is read for one
 * workspace at a time.
 */
export const BILLING_ADMIN_WORKSPACE_BILLING = (workspaceSlug: string) =>
  `billing-admin-workspace-billing-${workspaceSlug}`;

/* instance wide reads */

/**
 * The workspace list and the flag catalogue are server filtered and paginated, so
 * their key carries the whole query the same way the invoice and transaction keys
 * do. Task 7 passes the list params through these functions rather than using a
 * bare string, otherwise paging and searching would read from one shared entry.
 */
export const BILLING_ADMIN_WORKSPACES = (params: Record<string, string | number | undefined> = {}) =>
  buildBillingListKey("billing-admin-workspaces", params);

export const BILLING_FEATURE_FLAGS = (params: Record<string, string | number | undefined> = {}) =>
  buildBillingListKey("billing-feature-flags", params);
