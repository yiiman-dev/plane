# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.billing.api.views.admin_views import (
    FeatureFlagDetailEndpoint,
    FeatureFlagListCreateEndpoint,
    GatewayDetailEndpoint,
    GatewayListCreateEndpoint,
    GatewayRoutingConfigEndpoint,
    InvoiceDetailEndpoint,
    InvoiceListEndpoint,
    PlanDetailEndpoint,
    PlanFeatureFlagEndpoint,
    PlanListCreateEndpoint,
    TransactionDetailEndpoint,
    TransactionListEndpoint,
)
from plane.billing.api.views.callback_views import (
    PayPingCallbackEndpoint,
    PaymentCallbackEndpoint,
    ZibalStartEndpoint,
)
from plane.billing.api.views.user_views import (
    PaymentOrderCreateEndpoint,
    PaymentOrderStatusEndpoint,
    PlanQuoteEndpoint,
    PlanListEndpoint,
    SubscriptionListEndpoint,
)
from plane.billing.api.views.workspace_views import (
    WorkspaceEntitlementEndpoint,
    WorkspaceFeatureFlagDisableEndpoint,
    WorkspaceFeatureFlagEnableEndpoint,
    WorkspaceFeatureFlagListEndpoint,
)

urlpatterns = [
    # instance admin (god mode)
    path("admin/gateways/", GatewayListCreateEndpoint.as_view(), name="billing-gateways"),
    path("admin/gateways/<uuid:pk>/", GatewayDetailEndpoint.as_view(), name="billing-gateway-detail"),
    path("admin/routing/", GatewayRoutingConfigEndpoint.as_view(), name="billing-routing"),
    path("admin/plans/", PlanListCreateEndpoint.as_view(), name="billing-plans"),
    path("admin/plans/<uuid:pk>/", PlanDetailEndpoint.as_view(), name="billing-plan-detail"),
    path(
        "admin/feature-flags/",
        FeatureFlagListCreateEndpoint.as_view(),
        name="billing-feature-flags",
    ),
    path(
        "admin/feature-flags/<uuid:pk>/",
        FeatureFlagDetailEndpoint.as_view(),
        name="billing-feature-flag-detail",
    ),
    path(
        "admin/plans/<uuid:pk>/feature-flags/",
        PlanFeatureFlagEndpoint.as_view(),
        name="billing-plan-feature-flags",
    ),
    path("admin/invoices/", InvoiceListEndpoint.as_view(), name="billing-invoices"),
    path("admin/invoices/<uuid:pk>/", InvoiceDetailEndpoint.as_view(), name="billing-invoice-detail"),
    path("admin/transactions/", TransactionListEndpoint.as_view(), name="billing-transactions"),
    path(
        "admin/transactions/<uuid:pk>/",
        TransactionDetailEndpoint.as_view(),
        name="billing-transaction-detail",
    ),
    # user facing
    path("plans/", PlanListEndpoint.as_view(), name="billing-public-plans"),
    path("plans/<str:code>/quote/", PlanQuoteEndpoint.as_view(), name="billing-plan-quote"),
    path("orders/", PaymentOrderCreateEndpoint.as_view(), name="billing-create-order"),
    path("orders/<uuid:pk>/", PaymentOrderStatusEndpoint.as_view(), name="billing-order-status"),
    path("subscriptions/", SubscriptionListEndpoint.as_view(), name="billing-subscriptions"),
    # workspace scoped, the prefix of this urlconf keeps every billing route together
    path(
        "workspaces/<slug:slug>/billing/entitlement/",
        WorkspaceEntitlementEndpoint.as_view(),
        name="billing-workspace-entitlement",
    ),
    path(
        "workspaces/<slug:slug>/feature-flags/",
        WorkspaceFeatureFlagListEndpoint.as_view(),
        name="billing-workspace-feature-flags",
    ),
    path(
        "workspaces/<slug:slug>/feature-flags/<str:code>/enable/",
        WorkspaceFeatureFlagEnableEndpoint.as_view(),
        name="billing-workspace-feature-flag-enable",
    ),
    path(
        "workspaces/<slug:slug>/feature-flags/<str:code>/disable/",
        WorkspaceFeatureFlagDisableEndpoint.as_view(),
        name="billing-workspace-feature-flag-disable",
    ),
    # gateway callbacks, the path must match the URL registered in each panel
    path("callback/<str:gateway_code>/", PaymentCallbackEndpoint.as_view(), name="billing-callback"),
    path(
        "callback/payping/paid/<str:ref_id>/<str:payment_code>/",
        PayPingCallbackEndpoint.as_view(),
        name="billing-callback-payping",
    ),
    path(
        "callback/zibal/start/<str:track_id>/",
        ZibalStartEndpoint.as_view(),
        name="billing-callback-zibal-start",
    ),
]
