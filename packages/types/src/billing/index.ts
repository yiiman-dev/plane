/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TPaginatedResponse } from "../pagination";

/* payment gateways */

export type TPaymentGatewayCode = "digipay" | "payping" | "zarinpal" | "zibal";

export type TPaymentGatewayAmountUnit = "rial" | "toman";

export type TPaymentGatewayCredentialKey =
  | "api_token"
  | "client_id"
  | "client_secret"
  | "grant_type"
  | "merchant"
  | "merchant_id"
  | "password"
  | "username";

export type TPaymentGatewayCredentials = Partial<Record<TPaymentGatewayCredentialKey, string>>;

/**
 * Free form per gateway overrides. Unknown keys are preserved because the backend stores
 * the payload as a plain JSON blob.
 */
export type TPaymentGatewayExtraConfig = {
  amount_unit?: TPaymentGatewayAmountUnit;
  base_url?: string;
  callback_url?: string;
  max_amount_toman?: number;
  min_amount_toman?: number;
  timeout?: number;
  [key: string]: unknown;
};

export type TPaymentGateway = {
  created_at: string;
  extra_config: TPaymentGatewayExtraConfig;
  id: string;
  is_enabled: boolean;
  is_sandbox: boolean;
  last_error_at: string | null;
  last_error_message: string;
  priority: number;
  /** Masked on read, write only on create/update. */
  credentials: TPaymentGatewayCredentials;
  code: TPaymentGatewayCode;
  title: string;
  updated_at: string;
};

export type TPaymentGatewayPayload = {
  code: TPaymentGatewayCode;
  credentials?: TPaymentGatewayCredentials;
  extra_config: TPaymentGatewayExtraConfig;
  is_enabled: boolean;
  is_sandbox: boolean;
  priority: number;
  title: string;
};

/** Every field is optional on update so a partial form never wipes unrelated settings. */
export type TPaymentGatewayUpdate = Partial<TPaymentGatewayPayload>;

/* gateway routing */

export type TPaymentGatewayRoutingStrategy = "priority" | "random" | "schedule";

export type TPaymentGatewayScheduleEntry = {
  end_hour: number;
  gateway_code: TPaymentGatewayCode;
  start_hour: number;
};

export type TPaymentGatewayRoutingConfig = {
  cooldown_seconds: number;
  id: string;
  last_selected_code: string;
  last_selected_reason: string;
  max_attempts_per_gateway: number;
  priority_order: TPaymentGatewayCode[];
  schedule_entries: TPaymentGatewayScheduleEntry[];
  strategy: TPaymentGatewayRoutingStrategy;
  updated_at: string;
  weights: Partial<Record<TPaymentGatewayCode, number>>;
};

export type TPaymentGatewayRoutingConfigPayload = {
  cooldown_seconds: number;
  max_attempts_per_gateway: number;
  priority_order: TPaymentGatewayCode[];
  schedule_entries: TPaymentGatewayScheduleEntry[];
  strategy: TPaymentGatewayRoutingStrategy;
  weights: Partial<Record<TPaymentGatewayCode, number>>;
};

/* plans */

export type TBillingPlan = {
  access_level: string;
  code: string;
  created_at: string;
  currency: string;
  description: string;
  features: string[];
  id: string;
  included_seats: number;
  is_active: boolean;
  max_seats: number;
  min_seats: number;
  monthly_price_toman: number;
  name: string;
  per_seat_price_toman: number;
  sort_order: number;
  updated_at: string;
  yearly_price_toman: number;
};

export type TBillingPlanPayload = Omit<TBillingPlan, "created_at" | "id" | "updated_at">;

/* public checkout (web app) */

/**
 * Projection of an active plan exposed to the workspace user by GET /api/billing/plans/.
 * The instance admin owns every value, so the checkout renders whatever is configured and never
 * falls back to a plan that is hardcoded in the browser.
 */
export type TPublicPlan = {
  access_level: string;
  code: string;
  currency: string;
  description: string;
  features: string[];
  included_seats: number;
  max_seats: number;
  min_seats: number;
  monthly_price_toman: number;
  name: string;
  per_seat_price_toman: number;
  yearly_price_toman: number;
};

export type TPublicPlanListResponse = {
  results: TPublicPlan[];
  total_results: number;
};

export type TPlanQuoteParams = {
  cycle: TBillingCycle;
  seats: number;
};

/**
 * Server side pricing of a plan. The checkout displays these numbers verbatim: the same
 * Plan.calculate_subtotal() that invoices the order computes the quote, so the shown total and the
 * charged total cannot drift apart.
 */
export type TPlanQuote = {
  base_price_toman: number;
  currency: string;
  cycle: TBillingCycle;
  extra_seats: number;
  extra_seats_total_toman: number;
  included_seats: number;
  max_seats: number;
  min_seats: number;
  per_seat_price_toman: number;
  plan_code: string;
  plan_name: string;
  seats: number;
  subtotal_toman: number;
  total_toman: number;
};

export type TPaymentOrderCreatePayload = {
  cycle: TBillingCycle;
  mobile?: string;
  plan_code: string;
  seats: number;
  /**
   * The workspace the plan is bought for. Optional so an order raised outside a workspace
   * keeps behaving like before and lands on the owner level subscription.
   */
  workspace_slug?: string;
};

/* workspace entitlement */

export type TBillingWorkspaceFeatureFlag = {
  category: string;
  code: string;
  description: string;
  /** The plan grants this capability, so an admin may switch it on. */
  has_access: boolean;
  is_enabled: boolean;
  /** A publicly documented capability, so it may be listed even without a plan grant. */
  is_public: boolean;
  name: string;
};

export type TBillingWorkspaceFeatureFlagListResponse = {
  results: TBillingWorkspaceFeatureFlag[];
};

export type TBillingWorkspaceFeatureFlagMutationResponse = {
  code: string;
  /** Only the enable endpoint reports access; a disable never needs it. */
  has_access?: boolean;
  is_enabled: boolean;
};

export type TBillingWorkspacePlan = {
  access_level: string;
  code: string;
  description: string;
  is_free: boolean;
  name: string;
};

export type TBillingWorkspaceRef = {
  id: string;
  name: string;
  slug: string;
};

export type TBillingWorkspaceEntitlement = {
  feature_flags: TBillingWorkspaceFeatureFlag[];
  /** Null when no plan could be resolved at all, which also means an unlimited seat budget. */
  plan: TBillingWorkspacePlan | null;
  /** Null means unlimited, never zero. */
  seat_limit: number | null;
  seats_remaining: number | null;
  seats_used: number;
  workspace: TBillingWorkspaceRef;
};

/**
 * Result of POST /api/billing/orders/. `gateway_code` is the gateway the routing engine picked,
 * so the checkout can name it before leaving the app, and `result_url` is the in app screen the
 * gateway callback redirects back to.
 */
export type TPaymentOrderCreateResponse = {
  amount_toman: number;
  gateway_code: TPaymentGatewayCode;
  invoice_number: string;
  invoice_status: TInvoiceStatus;
  redirect_url: string;
  result_url: string;
  transaction_id: string;
};

/**
 * Owner scoped view of one payment transaction, returned by GET /api/billing/orders/<id>/.
 * It intentionally omits the raw callback/verify payloads and the gateway identifiers so the
 * polled result screen can never leak provider internals to the payer.
 */
export type TUserPaymentTransaction = {
  amount_toman: number;
  attempts: number;
  created_at: string;
  cycle: TBillingCycle | null;
  failure_reason: string;
  gateway_code: TPaymentGatewayCode;
  id: string;
  invoice_number: string;
  paid_at: string | null;
  plan_code: string | null;
  plan_name: string | null;
  seats: number | null;
  status: TPaymentTransactionStatus;
  updated_at: string;
  verified_at: string | null;
};

/* invoices */

export type TBillingCycle = "monthly" | "yearly";

export type TInvoiceStatus = "cancelled" | "draft" | "expired" | "issued" | "paid" | "refund";

export type TBillingUserDetail = {
  display_name: string;
  email: string;
  id: string;
};

export type TInvoice = {
  created_at: string;
  cycle: TBillingCycle;
  discount_toman: number;
  due_at: string | null;
  id: string;
  issued_at: string | null;
  metadata: Record<string, unknown>;
  notes: string;
  number: string;
  paid_at: string | null;
  plan: string;
  plan_code: string;
  seats: number;
  status: TInvoiceStatus;
  subtotal_toman: number;
  total_toman: number;
  updated_at: string;
  user: string;
  user_detail: TBillingUserDetail;
};

export type TInvoiceDetail = TInvoice & {
  transactions: TPaymentTransaction[];
};

/* payment transactions */

export type TPaymentTransactionStatus =
  | "failed"
  | "paid"
  | "pending"
  | "processing"
  | "redirected"
  | "reversed"
  | "unavailable";

export type TPaymentTransaction = {
  amount_toman: number;
  attempts: number;
  callback_payload: Record<string, unknown>;
  created_at: string;
  failure_reason: string;
  gateway_amount: number | null;
  gateway_code: TPaymentGatewayCode;
  gateway_fee: number | null;
  gateway_ref_id: string;
  gateway_token: string;
  id: string;
  invoice: string | null;
  invoice_number: string;
  meta: Record<string, unknown>;
  paid_at: string | null;
  status: TPaymentTransactionStatus;
  updated_at: string;
  user: string;
  user_detail: TBillingUserDetail;
  verified_at: string | null;
  verify_payload: Record<string, unknown>;
};

/* list envelopes */

export type TBillingPaginatedResponse<T> = TPaginatedResponse<T>;

export type TPaymentGatewayListResponse = TPaginatedResponse<TPaymentGateway[]>;
export type TBillingPlanListResponse = TPaginatedResponse<TBillingPlan[]>;
export type TInvoiceListResponse = TPaginatedResponse<TInvoice[]>;
export type TPaymentTransactionListResponse = TPaginatedResponse<TPaymentTransaction[]>;
