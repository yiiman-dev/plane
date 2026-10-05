/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

// plane imports
import { API_BASE_URL } from "@plane/constants";
import type {
  TBillingWorkspaceEntitlement,
  TBillingWorkspaceFeatureFlagListResponse,
  TBillingWorkspaceFeatureFlagMutationResponse,
  TBillingPlan,
  TBillingPlanListResponse,
  TBillingPlanPayload,
  TInvoiceDetail,
  TInvoiceListResponse,
  TPaymentGateway,
  TPaymentGatewayListResponse,
  TPaymentGatewayPayload,
  TPaymentGatewayRoutingConfig,
  TPaymentGatewayRoutingConfigPayload,
  TPaymentTransaction,
  TPaymentTransactionListResponse,
  TPaymentOrderCreatePayload,
  TPaymentOrderCreateResponse,
  TPlanQuote,
  TPlanQuoteParams,
  TPublicPlanListResponse,
  TUserPaymentTransaction,
} from "@plane/types";
// api service
import { APIService } from "../api.service";

export type TBillingListParams = {
  cursor?: string;
  per_page?: number;
  search?: string;
  [key: string]: string | number | undefined;
};

/**
 * Service class for the instance level billing and payment gateway administration.
 * Every endpoint lives under /api/billing/ and is guarded by the instance admin permission.
 * @extends {APIService}
 */
export class BillingService extends APIService {
  constructor() {
    super(API_BASE_URL);
  }

  /* payment gateways */

  /**
   * Retrieves the configured payment gateways
   */
  async gateways(params: TBillingListParams): Promise<TPaymentGatewayListResponse> {
    return this.get("/api/billing/admin/gateways/", { params })
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Creates a new payment gateway
   */
  async createGateway(data: TPaymentGatewayPayload): Promise<TPaymentGateway> {
    return this.post("/api/billing/admin/gateways/", data)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Retrieves a single payment gateway
   */
  async gateway(gatewayId: string): Promise<TPaymentGateway> {
    return this.get(`/api/billing/admin/gateways/${gatewayId}/`)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Updates a payment gateway. The gateway code is immutable after creation and the
   * credentials are write only, they are replaced only when a truthy object is sent.
   */
  async updateGateway(gatewayId: string, data: Partial<TPaymentGatewayPayload>): Promise<TPaymentGateway> {
    return this.patch(`/api/billing/admin/gateways/${gatewayId}/`, data)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Deletes a payment gateway. Gateways that already have transactions can only be disabled.
   */
  async deleteGateway(gatewayId: string): Promise<void> {
    return this.delete(`/api/billing/admin/gateways/${gatewayId}/`)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /* gateway routing */

  /**
   * Retrieves the singleton gateway routing configuration
   */
  async routing(): Promise<TPaymentGatewayRoutingConfig> {
    return this.get("/api/billing/admin/routing/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Updates the singleton gateway routing configuration
   */
  async updateRouting(data: Partial<TPaymentGatewayRoutingConfigPayload>): Promise<TPaymentGatewayRoutingConfig> {
    return this.patch("/api/billing/admin/routing/", data)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /* plans */

  /**
   * Retrieves the subscription plans
   */
  async plans(params: TBillingListParams): Promise<TBillingPlanListResponse> {
    return this.get("/api/billing/admin/plans/", { params })
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Creates a new subscription plan
   */
  async createPlan(data: TBillingPlanPayload): Promise<TBillingPlan> {
    return this.post("/api/billing/admin/plans/", data)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Retrieves a single subscription plan
   */
  async plan(planId: string): Promise<TBillingPlan> {
    return this.get(`/api/billing/admin/plans/${planId}/`)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Updates a subscription plan
   */
  async updatePlan(planId: string, data: Partial<TBillingPlanPayload>): Promise<TBillingPlan> {
    return this.patch(`/api/billing/admin/plans/${planId}/`, data)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Deletes a subscription plan. Plans that are already referenced by an invoice are
   * deactivated instead of being removed.
   */
  async deletePlan(planId: string): Promise<TBillingPlan | null> {
    return this.delete(`/api/billing/admin/plans/${planId}/`)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /* invoices */

  /**
   * Retrieves the billing invoices
   */
  async invoices(params: TBillingListParams): Promise<TInvoiceListResponse> {
    return this.get("/api/billing/admin/invoices/", { params })
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Retrieves a single invoice along with its payment transactions
   */
  async invoice(invoiceId: string): Promise<TInvoiceDetail> {
    return this.get(`/api/billing/admin/invoices/${invoiceId}/`)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /* payment transactions */

  /**
   * Retrieves the payment transactions
   */
  async transactions(params: TBillingListParams): Promise<TPaymentTransactionListResponse> {
    return this.get("/api/billing/admin/transactions/", { params })
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Retrieves a single payment transaction
   */
  async transaction(transactionId: string): Promise<TPaymentTransaction> {
    return this.get(`/api/billing/admin/transactions/${transactionId}/`)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /* public checkout, used by the workspace user in the web app */

  /**
   * Retrieves the active plans. This is the single source of truth for the checkout, the prices
   * come from the instance admin configuration and are never hardcoded in the browser.
   */
  async publicPlans(): Promise<TPublicPlanListResponse> {
    return this.get("/api/billing/plans/")
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Prices a plan for a seat count and a cycle on the server. The displayed total must come from
   * here instead of a browser side calculation, otherwise the shown amount and the charged amount
   * can diverge.
   */
  async planQuote(planCode: string, params: TPlanQuoteParams): Promise<TPlanQuote> {
    return this.get(`/api/billing/plans/${planCode}/quote/`, { params })
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Creates the payment order and returns the redirect URL of the gateway that the routing engine
   * selected. The browser is sent there, so the payer never leaves the app before the gateway.
   */
  async createPaymentOrder(data: TPaymentOrderCreatePayload): Promise<TPaymentOrderCreateResponse> {
    return this.post("/api/billing/orders/", data)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Reads the status of one order. Scoped to the owner on the server, and polled by the result
   * screen because PayPing and Digipay verify asynchronously after the browser comes back.
   */
  async paymentOrderStatus(transactionId: string): Promise<TUserPaymentTransaction> {
    return this.get(`/api/billing/orders/${transactionId}/`)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /* workspace entitlement */

  /**
   * Current plan, seat budget and feature access of one workspace. Open to every active member
   * on the server, so the workspace settings screen can show the budget without an admin role.
   */
  async workspaceEntitlement(workspaceSlug: string): Promise<TBillingWorkspaceEntitlement> {
    return this.get(`/api/billing/workspaces/${workspaceSlug}/billing/entitlement/`)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Every capability the instance defines, each one carrying this workspace's access and
   * activation state. Reading it is a plain list read like the plan entitlement.
   */
  async workspaceFeatureFlags(workspaceSlug: string): Promise<TBillingWorkspaceFeatureFlagListResponse> {
    return this.get(`/api/billing/workspaces/${workspaceSlug}/feature-flags/`)
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Switches a capability on for the workspace. The server refuses it when the plan does not
   * grant the capability, so the client only has to reflect the refusal.
   */
  async enableWorkspaceFeatureFlag(
    workspaceSlug: string,
    code: string
  ): Promise<TBillingWorkspaceFeatureFlagMutationResponse> {
    return this.post(`/api/billing/workspaces/${workspaceSlug}/feature-flags/${code}/enable/`, {})
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }

  /**
   * Switches a capability off. The plan grant survives, so the capability can be switched back
   * on without buying again.
   */
  async disableWorkspaceFeatureFlag(
    workspaceSlug: string,
    code: string
  ): Promise<TBillingWorkspaceFeatureFlagMutationResponse> {
    return this.post(`/api/billing/workspaces/${workspaceSlug}/feature-flags/${code}/disable/`, {})
      .then((response) => response.data)
      .catch((error) => {
        throw error?.response?.data;
      });
  }
}
