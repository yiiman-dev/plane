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
  resource: "billing-invoices" | "billing-transactions",
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

/* workspace scoped reads */

/**
 * Entitlement and feature flags are read per workspace, so the cache key carries the slug. Two
 * workspaces in the same session must never share a cache entry.
 */
export const BILLING_WORKSPACE_ENTITLEMENT = (workspaceSlug: string) =>
  buildBillingListKey("billing-workspace-entitlement", { workspaceSlug });

export const BILLING_WORKSPACE_FEATURE_FLAGS = (workspaceSlug: string) =>
  buildBillingListKey("billing-workspace-feature-flags", { workspaceSlug });
