# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""God mode (instance admin) endpoints for gateways, routing, plans and billing records."""

# Python imports

# Django imports

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.billing.api.serializers import (
    FeatureFlagSerializer,
    GatewayRoutingConfigSerializer,
    InvoiceSerializer,
    PaymentGatewayDetailSerializer,
    PaymentTransactionSerializer,
    PlanFeatureFlagSerializer,
    PlanSerializer,
)
from plane.billing.gateways.registry import supported_codes
from plane.billing.models import (
    FeatureFlag,
    GatewayRoutingConfig,
    Invoice,
    PaymentGateway,
    PaymentTransaction,
    Plan,
    PlanFeatureFlag,
)
from plane.license.api.permissions import InstanceAdminPermission
from plane.license.api.views.base import BaseAPIView


class BillingAdminAPIView(BaseAPIView):
    """Shared pagination helper for the billing god mode endpoints."""

    permission_classes = [InstanceAdminPermission]

    def paginated(self, request, queryset, serializer, **kwargs):
        queryset = self.filter_queryset(queryset)
        kwargs.setdefault("default_per_page", 50)
        return self.paginate(
            request,
            queryset=queryset,
            on_results=lambda results: serializer(results, many=True).data,
            **kwargs,
        )


class GatewayListCreateEndpoint(BillingAdminAPIView):
    """List or create payment gateways. Credentials are never returned in clear."""

    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        queryset = PaymentGateway.objects.all().order_by("priority", "code")
        return self.paginated(request, queryset, PaymentGatewayDetailSerializer)

    def post(self, request):
        if request.data.get("code") not in supported_codes():
            return Response(
                {"error": f"code must be one of {supported_codes()}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PaymentGatewayDetailSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class GatewayDetailEndpoint(BillingAdminAPIView):
    permission_classes = [InstanceAdminPermission]

    def get_object(self, pk):
        return PaymentGateway.objects.filter(pk=pk).first()

    def get(self, request, pk):
        gateway = self.get_object(pk)
        if gateway is None:
            return Response({"error": "Gateway not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaymentGatewayDetailSerializer(gateway).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        gateway = self.get_object(pk)
        if gateway is None:
            return Response({"error": "Gateway not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = PaymentGatewayDetailSerializer(gateway, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        gateway = self.get_object(pk)
        if gateway is None:
            return Response({"error": "Gateway not found"}, status=status.HTTP_404_NOT_FOUND)
        if PaymentTransaction.objects.filter(gateway_code=gateway.code).exists():
            return Response(
                {"error": "Gateways with transactions cannot be deleted, disable them instead."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        gateway.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GatewayRoutingConfigEndpoint(BillingAdminAPIView):
    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        config = GatewayRoutingConfig.get_solo()
        return Response(GatewayRoutingConfigSerializer(config).data, status=status.HTTP_200_OK)

    def patch(self, request):
        config = GatewayRoutingConfig.get_solo()
        serializer = GatewayRoutingConfigSerializer(config, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)


class PlanListCreateEndpoint(BillingAdminAPIView):
    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        queryset = Plan.objects.all().order_by("sort_order", "code")
        return self.paginated(request, queryset, PlanSerializer)

    def post(self, request):
        serializer = PlanSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PlanDetailEndpoint(BillingAdminAPIView):
    permission_classes = [InstanceAdminPermission]

    def get_object(self, pk):
        return Plan.objects.filter(pk=pk).first()

    def get(self, request, pk):
        plan = self.get_object(pk)
        if plan is None:
            return Response({"error": "Plan not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PlanSerializer(plan).data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        plan = self.get_object(pk)
        if plan is None:
            return Response({"error": "Plan not found"}, status=status.HTTP_404_NOT_FOUND)
        serializer = PlanSerializer(plan, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        plan = self.get_object(pk)
        if plan is None:
            return Response({"error": "Plan not found"}, status=status.HTTP_404_NOT_FOUND)
        if plan.invoices.exists():
            plan.is_active = False
            plan.save(update_fields=["is_active", "updated_at"])
            return Response(PlanSerializer(plan).data, status=status.HTTP_200_OK)
        plan.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvoiceListEndpoint(BillingAdminAPIView):
    permission_classes = [InstanceAdminPermission]
    filterset_fields = ["status", "cycle", "plan", "user", "number"]
    search_fields = ["number", "user__email"]

    def get(self, request):
        queryset = Invoice.objects.select_related("plan", "user").all()
        status_filter = request.GET.get("status")
        if status_filter:
            queryset = queryset.filter(status__in=str(status_filter).split(","))
        plan_code = request.GET.get("plan_code")
        if plan_code:
            queryset = queryset.filter(plan__code=plan_code)
        return self.paginated(request, queryset, InvoiceSerializer)


class InvoiceDetailEndpoint(BillingAdminAPIView):
    permission_classes = [InstanceAdminPermission]

    def get(self, request, pk):
        invoice = Invoice.objects.filter(pk=pk).first()
        if invoice is None:
            return Response({"error": "Invoice not found"}, status=status.HTTP_404_NOT_FOUND)
        data = InvoiceSerializer(invoice).data
        data["transactions"] = PaymentTransactionSerializer(invoice.transactions.all(), many=True).data
        return Response(data, status=status.HTTP_200_OK)


class TransactionListEndpoint(BillingAdminAPIView):
    filterset_fields = ["status", "gateway_code", "invoice", "user"]
    search_fields = ["gateway_token", "gateway_ref_id", "invoice__number"]

    def get(self, request):
        queryset = PaymentTransaction.objects.select_related("invoice", "user").all()
        gateway_code = request.GET.get("gateway_code")
        if gateway_code:
            queryset = queryset.filter(gateway_code=gateway_code)
        # the cycle lives on the invoice, a transaction row has no own column
        cycle = request.GET.get("cycle")
        if cycle:
            queryset = queryset.filter(invoice__cycle=cycle)
        return self.paginated(request, queryset, PaymentTransactionSerializer)


class TransactionDetailEndpoint(BillingAdminAPIView):
    permission_classes = [InstanceAdminPermission]

    def get(self, request, pk):
        transaction = PaymentTransaction.objects.filter(pk=pk).first()
        if transaction is None:
            return Response({"error": "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(PaymentTransactionSerializer(transaction).data, status=status.HTTP_200_OK)


class FeatureFlagListCreateEndpoint(BillingAdminAPIView):
    """List the feature flag catalogue or add a new capability."""

    permission_classes = [InstanceAdminPermission]
    search_fields = ["code", "name", "description"]

    def get(self, request):
        queryset = FeatureFlag.objects.all().order_by("category", "code")
        return self.paginated(request, queryset, FeatureFlagSerializer)

    def post(self, request):
        serializer = FeatureFlagSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class FeatureFlagDetailEndpoint(BillingAdminAPIView):
    permission_classes = [InstanceAdminPermission]

    def get_object(self, pk):
        return FeatureFlag.objects.filter(pk=pk).first()

    def get(self, request, pk):
        feature_flag = self.get_object(pk)
        if feature_flag is None:
            return Response({"error": "پرچم قابلیت یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        data = FeatureFlagSerializer(feature_flag).data
        data["granted_plan_count"] = PlanFeatureFlag.objects.filter(feature_flag=feature_flag, is_enabled=True).count()
        data["enabled_workspace_count"] = feature_flag.workspace_activations.filter(is_enabled=True).count()
        return Response(data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        feature_flag = self.get_object(pk)
        if feature_flag is None:
            return Response({"error": "پرچم قابلیت یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        serializer = FeatureFlagSerializer(feature_flag, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        feature_flag = self.get_object(pk)
        if feature_flag is None:
            return Response({"error": "پرچم قابلیت یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        # Turning the master switch off already invalidates every grant and
        # activation, so a flag that is still in use is retired instead.
        if PlanFeatureFlag.objects.filter(feature_flag=feature_flag).exists():
            feature_flag.is_active = False
            feature_flag.save(update_fields=["is_active", "updated_at"])
            return Response(FeatureFlagSerializer(feature_flag).data, status=status.HTTP_200_OK)
        feature_flag.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlanFeatureFlagEndpoint(BillingAdminAPIView):
    """Attach or detach the feature flags a plan is allowed to unlock."""

    permission_classes = [InstanceAdminPermission]

    def get_plan(self, pk):
        return Plan.objects.filter(pk=pk).first()

    def get(self, request, pk):
        plan = self.get_plan(pk)
        if plan is None:
            return Response({"error": "پلن یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        queryset = PlanFeatureFlag.objects.filter(plan=plan).select_related("feature_flag")
        return self.paginated(request, queryset, PlanFeatureFlagSerializer)

    def post(self, request, pk):
        plan = self.get_plan(pk)
        if plan is None:
            return Response({"error": "پلن یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        serializer = PlanFeatureFlagSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        feature_flag = serializer.validated_data["feature_flag"]
        # the pair is unique, so re-adding an existing grant flips it back on
        # instead of failing on a duplicate key
        grant, _ = PlanFeatureFlag.objects.update_or_create(
            plan=plan,
            feature_flag=feature_flag,
            defaults={
                "is_enabled": serializer.validated_data.get("is_enabled", True),
                "config": serializer.validated_data.get("config", {}),
            },
        )
        return Response(PlanFeatureFlagSerializer(grant).data, status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        plan = self.get_plan(pk)
        if plan is None:
            return Response({"error": "پلن یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        feature_flag_id = request.GET.get("feature_flag")
        if not feature_flag_id:
            return Response({"error": "شناسهٔ پرچم قابلیت لازم است."}, status=status.HTTP_400_BAD_REQUEST)
        deleted, _ = PlanFeatureFlag.objects.filter(plan=plan, feature_flag_id=feature_flag_id).delete()
        if not deleted:
            return Response({"error": "این پرچم به پلن متصل نیست."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
