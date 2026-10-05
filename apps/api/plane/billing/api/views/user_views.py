# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Authenticated workspace user endpoints: plans and payment orders."""

# Third party imports
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# Module imports
from plane.billing.api.serializers import (
    PaymentOrderCreateSerializer,
    PublicPlanSerializer,
    UserPaymentTransactionSerializer,
)
from plane.billing.models import BillingCycle, PaymentTransaction, Plan, Subscription
from plane.billing.services.payment import BillingError, create_payment_order
from plane.db.models import Workspace, WorkspaceMember
from plane.license.api.views.base import BaseAPIView

WORKSPACE_NOT_FOUND = "ورک‌اسپیس یافت نشد."
WORKSPACE_MEMBERSHIP_REQUIRED = "برای خرید پلن این ورک‌اسپیس باید عضو فعال آن باشید."


class PlanListEndpoint(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Plan.objects.filter(is_active=True).order_by("sort_order", "code")
        return Response(
            {
                "results": PublicPlanSerializer(queryset, many=True).data,
                "total_results": queryset.count(),
            },
            status=status.HTTP_200_OK,
        )


class PlanQuoteEndpoint(BaseAPIView):
    """Server side pricing of a plan for a seat count and a billing cycle.

    The web checkout renders a live total, and that total must not be a browser
    side guess: the same Plan.calculate_subtotal() that prices the invoice is
    used here, so the displayed amount and the charged amount cannot diverge.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, code: str):
        plan = Plan.objects.filter(code=code, is_active=True).first()
        if plan is None:
            return Response({"error": "The requested plan is not available."}, status=status.HTTP_404_NOT_FOUND)

        cycle = request.query_params.get("cycle", "monthly")
        if cycle not in (BillingCycle.MONTHLY, BillingCycle.YEARLY):
            return Response({"error": "Invalid billing cycle."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            seats = int(request.query_params.get("seats", plan.included_seats))
        except (TypeError, ValueError):
            return Response({"error": "Invalid seat count."}, status=status.HTTP_400_BAD_REQUEST)

        if seats < plan.min_seats:
            return Response(
                {"error": f"The plan requires at least {plan.min_seats} seat(s)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if seats > plan.max_seats:
            return Response(
                {"error": f"The plan allows at most {plan.max_seats} seat(s)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        base = plan.price_for(cycle)
        extra_seats = max(0, seats - plan.included_seats)
        subtotal = plan.calculate_subtotal(seats, cycle)
        return Response(
            {
                "plan_code": plan.code,
                "plan_name": plan.name,
                "cycle": cycle,
                "seats": seats,
                "included_seats": plan.included_seats,
                "extra_seats": extra_seats,
                "min_seats": plan.min_seats,
                "max_seats": plan.max_seats,
                "base_price_toman": int(base),
                "per_seat_price_toman": int(plan.per_seat_price_toman),
                "extra_seats_total_toman": int(plan.per_seat_price_toman) * extra_seats,
                "subtotal_toman": int(subtotal),
                "total_toman": int(subtotal),
                "currency": plan.currency,
            },
            status=status.HTTP_200_OK,
        )


class PaymentOrderCreateEndpoint(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PaymentOrderCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        data = serializer.validated_data
        workspace_slug = (data.get("workspace_slug") or "").strip()
        if workspace_slug:
            # buying a plan for a workspace requires being a live member of that same
            # workspace, otherwise the payer could fund an entitlement they cannot read
            workspace = Workspace.objects.filter(slug=workspace_slug).first()
            if workspace is None:
                return Response({"error": WORKSPACE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
            is_active_member = WorkspaceMember.objects.filter(
                workspace=workspace, user=request.user, is_active=True
            ).exists()
            if not is_active_member:
                return Response(
                    {"error": WORKSPACE_MEMBERSHIP_REQUIRED},
                    status=status.HTTP_403_FORBIDDEN,
                )
        try:
            result = create_payment_order(
                user=request.user,
                plan_code=data["plan_code"],
                seats=data["seats"],
                cycle=data["cycle"],
                mobile=data.get("mobile") or "",
                workspace_slug=workspace_slug,
            )
        except BillingError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "invoice_number": result["invoice"].number,
                "invoice_status": result["invoice"].status,
                "transaction_id": str(result["transaction"].id),
                "gateway_code": result["transaction"].gateway_code,
                "amount_toman": result["transaction"].amount_toman,
                "redirect_url": result["redirect_url"],
                "result_url": f"/billing/result/{result['transaction'].id}/",
            },
            status=status.HTTP_201_CREATED,
        )


class PaymentOrderStatusEndpoint(BaseAPIView):
    """Owner scoped status of one order, polled by the in app result screen.

    PayPing and Digipay confirm asynchronously, so the browser that comes back
    from the gateway cannot read the final outcome from the redirect itself and
    has to ask again until the backend verification task settles the row.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        transaction = PaymentTransaction.objects.filter(pk=pk, user=request.user).select_related("invoice").first()
        if transaction is None:
            return Response({"error": "Order not found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(UserPaymentTransactionSerializer(transaction).data, status=status.HTTP_200_OK)


class SubscriptionListEndpoint(BaseAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        queryset = Subscription.objects.filter(user=request.user).select_related("plan")
        from plane.billing.api.serializers import SubscriptionSerializer

        return Response(
            {"results": SubscriptionSerializer(queryset, many=True).data, "total_results": queryset.count()},
            status=status.HTTP_200_OK,
        )
