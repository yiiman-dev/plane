# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""God mode (instance admin) endpoints for gateways, routing, plans and billing records."""

# Python imports

# Django imports

# Third party imports
from django.db import transaction
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.billing.api.views.base import WORKSPACE_NOT_FOUND, WorkspaceContextMixin
from plane.billing.api.serializers import (
    AdminWorkspaceBillingSerializer,
    BillingAccessLogSerializer,
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
    BillingAccessLog,
    FeatureFlag,
    GatewayRoutingConfig,
    Invoice,
    PaymentGateway,
    PaymentTransaction,
    Plan,
    PlanFeatureFlag,
    Subscription,
    SubscriptionStatus,
)
from plane.billing.services import ledger as ledger_service
from plane.billing.services import money as money_service
from plane.db.models import Workspace, WorkspaceMember
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
    """Attach, detach or edit the feature flags a plan is allowed to unlock.

    Two write shapes, because the two admin screens are not the same screen.
    ``POST`` changes one grant and is what a per-flag toggle needs; ``PATCH``
    saves the whole grant set of the plan form in one request, which is what the
    plan editor actually sends. A per-flag screen posting N times cannot report
    a half-saved plan, but the batch has to: one invalid item refuses the whole
    payload and writes nothing, or the catalogue ends up disagreeing with the
    form the administrator is looking at.

    ``PATCH`` deliberately never writes ``config``. It is free-form data other
    code owns, and the ``POST`` path's habit of defaulting it to ``{}`` on every
    upsert is a known pre-existing bug that this path does not copy.
    """

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
        # This endpoint is an upsert, so an existing grant is validated as a
        # partial update: the admin flipping ``is_enabled`` back on must not have
        # to resend the limit. On a genuinely new grant the write is full, and a
        # ``number`` flag then has to arrive with its bound.
        feature_flag_id = request.data.get("feature_flag")
        existing = (
            feature_flag_id is not None
            and PlanFeatureFlag.objects.filter(plan=plan, feature_flag_id=feature_flag_id).exists()
        )
        serializer = PlanFeatureFlagSerializer(data=request.data, partial=existing)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        feature_flag = serializer.validated_data["feature_flag"]
        defaults = {
            "is_enabled": serializer.validated_data.get("is_enabled", True),
            # KNOWN, PRE-EXISTING, NOT FIXED HERE: unlike ``limit_value`` below,
            # an omitted ``config`` is wiped rather than left alone. Out of scope
            # for the limit work; recorded so it reads as known, not overlooked.
            "config": serializer.validated_data.get("config", {}),
        }
        # Only when a limit was actually supplied. ``update_or_create`` ignores
        # keys absent from ``defaults``, so omitting the field means "leave the
        # stored limit alone"; a bare ``get`` here would clear it instead.
        if "limit_value" in serializer.validated_data:
            defaults["limit_value"] = serializer.validated_data["limit_value"]
        # the pair is unique, so re-adding an existing grant flips it back on
        # instead of failing on a duplicate key
        grant, _ = PlanFeatureFlag.objects.update_or_create(
            plan=plan,
            feature_flag=feature_flag,
            defaults=defaults,
        )
        return Response(PlanFeatureFlagSerializer(grant).data, status=status.HTTP_201_CREATED)

    def patch(self, request, pk):
        """Save the plan form's entire grant set. All of it, or none of it."""
        plan = self.get_plan(pk)
        if plan is None:
            return Response({"error": "پلن یافت نشد."}, status=status.HTTP_404_NOT_FOUND)

        raw_grants = request.data.get("grants")
        if not isinstance(raw_grants, list):
            return Response(
                {"grants": ["فهرست grants باید یک آرایه باشد."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        codes = [item.get("feature_flag_code") for item in raw_grants if isinstance(item, dict)]
        flags_by_code = {flag.code: flag for flag in FeatureFlag.objects.filter(code__in=codes)}

        # First pass: validate every item and write nothing. A single bad row
        # must not leave the earlier rows saved -- the form would then show a
        # state the database does not hold.
        errors = {}
        prepared = []
        for index, item in enumerate(raw_grants):
            if not isinstance(item, dict):
                errors[index] = "هر مورد باید یک شیء باشد."
                continue

            code = item.get("feature_flag_code")
            flag = flags_by_code.get(code)
            if flag is None:
                errors[code or index] = {"feature_flag_code": "پرچم قابلیت با این کد یافت نشد."}
                continue

            existing = PlanFeatureFlag.objects.filter(plan=plan, feature_flag=flag).first()
            payload = {"feature_flag": str(flag.pk), "is_enabled": item.get("is_enabled", True)}
            # Only when supplied: an omitted limit means "leave the stored one",
            # and a null in the payload is not the same request as no key at all.
            if "limit_value" in item:
                payload["limit_value"] = item["limit_value"]

            serializer = PlanFeatureFlagSerializer(existing, data=payload, partial=existing is not None)
            if not serializer.is_valid():
                errors[code] = serializer.errors
                continue
            prepared.append((flag, serializer))

        if errors:
            return Response({"grants": errors}, status=status.HTTP_400_BAD_REQUEST)

        saved = []
        with transaction.atomic():
            for flag, serializer in prepared:
                defaults = {"is_enabled": serializer.validated_data.get("is_enabled", True)}
                if "limit_value" in serializer.validated_data:
                    defaults["limit_value"] = serializer.validated_data["limit_value"]
                grant, _ = PlanFeatureFlag.objects.update_or_create(
                    plan=plan,
                    feature_flag=flag,
                    defaults=defaults,
                )
                saved.append(grant)

        # The payload's order, so the screen can re-render rows without sorting
        # them again and a second save of the same form is byte-identical.
        return Response({"grants": PlanFeatureFlagSerializer(saved, many=True).data})

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


class AdminAccessLogEndpoint(BillingAdminAPIView):
    """Who read which tenant's money: the accountability side of the audit trail.

    Instance admins only, and that is the point of the table rather than a
    limitation of this view. ``BillingAccessLog`` exists because an operator can
    see any workspace's wallet and ledger; "who looked at me" has no meaning to a
    workspace admin, and exposing it to one would widen the surface the log is
    there to narrow.

    This read writes no row of its own. The log records reads that returned a
    balance or a ledger, and this page returns neither -- if it audited itself,
    the trail would fill with entries about operators reading the trail.
    """

    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        # ``Meta.ordering`` is ``-created_at``, so the newest read comes first
        # without a second order_by here that could disagree with it.
        queryset = BillingAccessLog.objects.select_related("workspace", "viewer").all()

        # A query parameter here narrows an instance-wide list the caller is
        # already entitled to read in full, so it cannot widen what they see the
        # way a forged ``?slug=`` on a workspace-scoped route could. It is a
        # filter, like the invoice status filter, and not a scope.
        workspace_slug = request.GET.get("workspace_slug")
        if workspace_slug:
            queryset = queryset.filter(workspace__slug=workspace_slug)

        # Comma separated like the invoice status filter, so one request can ask
        # for both kinds of money read at once. An unknown value matches nothing
        # rather than failing: a filter typo is an empty screen, not a 500.
        view_filter = request.GET.get("view")
        if view_filter:
            queryset = queryset.filter(view__in=str(view_filter).split(","))

        return self.paginated(request, queryset, BillingAccessLogSerializer)


class AdminWorkspaceListEndpoint(BillingAdminAPIView):
    """Every workspace with the three numbers an operator triages by.

    Reads the plan, the seat count and the wallet balance of every tenant. This
    page is deliberately NOT audited row by row: it exists to decide which
    workspace to open, and one log row per tenant per page view would bury the
    deliberate money reads of the detail page in noise. The detail page is where
    money is actually inspected.

    ``on_results`` receives only the page's rows (``paginator.py:714``), so the
    two lookups below cost one query each for the whole page rather than one per
    row.

    The rows are plain dicts rather than a serializer's output because
    ``paginate`` hands the page to ``on_results`` and serialises whatever comes
    back; a ``ModelSerializer`` for a shape no model has would be dead code.
    """

    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        # ``id`` breaks the tie so the ordering is total: the paginator pages by
        # a cursor, and two workspaces sharing a name would otherwise have no
        # stable order between them.
        queryset = Workspace.objects.order_by("name", "id")

        def build(page):
            workspaces = list(page)
            ids = [workspace.pk for workspace in workspaces]
            if not ids:
                return []

            plan_by_workspace = {
                row["workspace_id"]: row
                for row in Subscription.objects.filter(workspace_id__in=ids, status=SubscriptionStatus.ACTIVE).values(
                    "workspace_id", "plan__code", "seats"
                )
            }
            # Read-only by construction: ``wallet_balances`` never creates the
            # ledger account, so paging this list leaves no rows behind it.
            balances = money_service.wallet_balances(ids)

            return [
                {
                    "id": str(workspace.pk),
                    "name": workspace.name,
                    "slug": workspace.slug,
                    "plan_code": (plan_by_workspace.get(workspace.pk) or {}).get("plan__code"),
                    "seats": (plan_by_workspace.get(workspace.pk) or {}).get("seats", 0),
                    # An absent account, not a stored zero balance: the account
                    # simply does not exist yet for this workspace.
                    "balance_toman": balances.get(workspace.pk, 0),
                }
                for workspace in workspaces
            ]

        return self.paginate(request, queryset=queryset, on_results=build, default_per_page=50)


class AdminWorkspaceBillingEndpoint(WorkspaceContextMixin, BillingAdminAPIView):
    """The billing picture of one workspace: plan, subscription, seats and money.

    Returns the wallet balance, so it writes an access-log row exactly as the
    wallet endpoint does. The audit trail has to follow the money, not a
    particular URL.

    The workspace is the one the URL resolved. Nothing in this module reads a
    workspace, a slug or a scope out of the query string, so a forged
    ``?slug=other`` has nowhere to land.
    """

    permission_classes = [InstanceAdminPermission]

    def get(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            # Before the audit row, never after: a row must name a read that
            # actually happened.
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        ledger_service.record_admin_read(workspace=workspace, view=BillingAccessLog.VIEW_WALLET, request=request)

        subscription = (
            Subscription.objects.filter(workspace=workspace, status=SubscriptionStatus.ACTIVE)
            .select_related("plan")
            .first()
        )
        plan = subscription.plan if subscription else None

        return Response(
            AdminWorkspaceBillingSerializer(
                {
                    "id": workspace.pk,
                    "name": workspace.name,
                    "slug": workspace.slug,
                    "plan_code": plan.code if plan else None,
                    "plan_name": plan.name if plan else None,
                    "seats": subscription.seats if subscription else 0,
                    "balance_toman": money_service.wallet_balance(workspace),
                    "hold_balance_toman": money_service.wallet_hold_balance(workspace),
                    "subscription_status": subscription.status if subscription else None,
                    "starts_at": subscription.starts_at if subscription else None,
                    "ends_at": subscription.ends_at if subscription else None,
                    "renew_lock_days": plan.renew_lock_days if plan else None,
                    "proration_mode": plan.proration_mode if plan else None,
                    "active_members": WorkspaceMember.objects.filter(workspace=workspace, is_active=True).count(),
                }
            ).data
        )
