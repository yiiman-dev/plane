# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import serializers

# Django imports
from django.utils import timezone

# Module imports
from plane.billing.models import (
    BillingAccessLog,
    FeatureFlag,
    GatewayRoutingConfig,
    Invoice,
    LedgerEntry,
    PaymentGateway,
    PaymentTransaction,
    Plan,
    PlanFeatureFlag,
    RenewalNoticeSchedule,
    Subscription,
    Wallet,
)
from plane.billing.services import hold as hold_service
from plane.billing.services import ledger as ledger_service
from plane.billing.services import money as money_service
from plane.billing.services import renewal as renewal_service
from plane.billing.services.credentials import (
    CredentialEncryptionError,
    decrypt_credentials,
    encrypt_credentials,
    mask_credentials,
)


class PaymentGatewaySerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentGateway
        fields = [
            "id",
            "code",
            "title",
            "is_enabled",
            "is_sandbox",
            "extra_config",
            "priority",
            "last_error_at",
            "last_error_message",
            "created_at",
            "updated_at",
        ]
        # code is writable on create only, update() rejects a rename
        read_only_fields = ["id", "last_error_at", "last_error_message", "created_at", "updated_at"]

    def create(self, validated_data):
        credentials = validated_data.pop("credentials", None)
        try:
            instance = PaymentGateway.objects.create(
                credentials=encrypt_credentials(credentials or {}), **validated_data
            )
        except CredentialEncryptionError as exc:
            raise serializers.ValidationError({"credentials": str(exc)}) from exc
        return instance

    def update(self, instance, validated_data):
        if "code" in validated_data and validated_data.pop("code") != instance.code:
            raise serializers.ValidationError({"code": "The gateway code cannot be changed."})
        if "credentials" in validated_data:
            credentials = validated_data.pop("credentials")
            if credentials:
                try:
                    instance.credentials = encrypt_credentials(credentials)
                except CredentialEncryptionError as exc:
                    raise serializers.ValidationError({"credentials": str(exc)}) from exc
        return super().update(instance, validated_data)


class PaymentGatewayDetailSerializer(PaymentGatewaySerializer):
    credentials = serializers.JSONField(required=False, write_only=True)

    class Meta(PaymentGatewaySerializer.Meta):
        fields = PaymentGatewaySerializer.Meta.fields + ["credentials"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data["credentials"] = mask_credentials(decrypt_credentials(instance.credentials))
        return data


class GatewayRoutingConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = GatewayRoutingConfig
        fields = [
            "id",
            "strategy",
            "schedule_entries",
            "priority_order",
            "weights",
            "cooldown_seconds",
            "max_attempts_per_gateway",
            "last_selected_code",
            "last_selected_reason",
            "updated_at",
        ]
        read_only_fields = ["id", "last_selected_code", "last_selected_reason", "updated_at"]


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name",
            "description",
            "access_level",
            "monthly_price_toman",
            "yearly_price_toman",
            "per_seat_price_toman",
            "included_seats",
            "min_seats",
            "max_seats",
            "features",
            "is_active",
            "sort_order",
            "currency",
            "renew_lock_days",
            "proration_mode",
            "sms_prices",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class PublicPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = [
            "code",
            "name",
            "description",
            "access_level",
            "monthly_price_toman",
            "yearly_price_toman",
            "per_seat_price_toman",
            "included_seats",
            "min_seats",
            "max_seats",
            "features",
            "currency",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    plan_code = serializers.CharField(source="plan.code", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "user",
            "user_detail",
            "plan",
            "plan_code",
            "seats",
            "cycle",
            "subtotal_toman",
            "discount_toman",
            "total_toman",
            "status",
            "issued_at",
            "due_at",
            "paid_at",
            "notes",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    user_detail = serializers.SerializerMethodField()

    def get_user_detail(self, instance):
        user = instance.user
        return {"id": str(user.id), "email": user.email, "display_name": user.display_name}


class PaymentTransactionSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.number", read_only=True, default=None)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "user",
            "user_detail",
            "gateway_code",
            "gateway_token",
            "gateway_ref_id",
            "amount_toman",
            "status",
            "gateway_fee",
            "gateway_amount",
            "callback_payload",
            "verify_payload",
            "failure_reason",
            "attempts",
            "verified_at",
            "paid_at",
            "meta",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    user_detail = serializers.SerializerMethodField()

    def get_user_detail(self, instance):
        user = instance.user
        return {"id": str(user.id), "email": user.email, "display_name": user.display_name}


class QueuedTransactionSerializer(PaymentTransactionSerializer):
    """One row of the ambiguous payment queue: the transaction plus what the decision needs.

    The raw payloads of the parent projection stay in, because "why did the
    gateway keep saying maybe" is answered from them; the age, the automatic
    release date and the workspace are added because that is what an operator
    triages on.
    """

    age_days = serializers.SerializerMethodField()
    auto_release_at = serializers.SerializerMethodField()
    workspace_slug = serializers.SerializerMethodField()
    workspace_name = serializers.SerializerMethodField()

    class Meta(PaymentTransactionSerializer.Meta):
        fields = PaymentTransactionSerializer.Meta.fields + [
            "held_at",
            "age_days",
            "auto_release_at",
            "workspace_slug",
            "workspace_name",
        ]
        read_only_fields = fields

    def get_age_days(self, instance):
        if instance.held_at is None:
            return None
        return max(0, (timezone.now() - instance.held_at).days)

    def get_auto_release_at(self, instance):
        return hold_service.auto_release_at(instance)

    def _workspace(self, instance):
        cache = self.context.setdefault("_queued_workspaces", {})
        if instance.pk not in cache:
            cache[instance.pk] = hold_service.workspace_of(instance)
        return cache[instance.pk]

    def get_workspace_slug(self, instance):
        workspace = self._workspace(instance)
        return workspace.slug if workspace is not None else None

    def get_workspace_name(self, instance):
        workspace = self._workspace(instance)
        return workspace.name if workspace is not None else None


class UserPaymentTransactionSerializer(serializers.ModelSerializer):
    """Owner scoped read only projection of a payment transaction.

    The in app result screen polls this after the gateway redirects the browser
    back, so it carries only what a payer may see about their own payment and
    never the gateway credentials, the raw callbacks or another user data.
    """

    invoice_number = serializers.SerializerMethodField()
    plan_name = serializers.SerializerMethodField()
    plan_code = serializers.SerializerMethodField()
    seats = serializers.SerializerMethodField()
    cycle = serializers.SerializerMethodField()

    class Meta:
        model = PaymentTransaction
        fields = [
            "id",
            "invoice_number",
            "plan_name",
            "plan_code",
            "seats",
            "cycle",
            "gateway_code",
            "amount_toman",
            "status",
            "failure_reason",
            "attempts",
            "verified_at",
            "paid_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    @staticmethod
    def _invoice(instance):
        return instance.invoice

    def get_invoice_number(self, instance):
        invoice = self._invoice(instance)
        return invoice.number if invoice else None

    def get_plan_name(self, instance):
        invoice = self._invoice(instance)
        return invoice.plan.name if invoice else None

    def get_plan_code(self, instance):
        invoice = self._invoice(instance)
        return invoice.plan.code if invoice else None

    def get_seats(self, instance):
        invoice = self._invoice(instance)
        return invoice.seats if invoice else None

    def get_cycle(self, instance):
        invoice = self._invoice(instance)
        return invoice.cycle if invoice else None


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class PaymentOrderCreateSerializer(serializers.Serializer):
    plan_code = serializers.CharField(max_length=50)
    seats = serializers.IntegerField(min_value=1, default=1)
    cycle = serializers.ChoiceField(choices=["monthly", "yearly"], default="monthly")
    mobile = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    # A plan is a workspace entitlement, so an order raised from a workspace settings screen
    # names the workspace it is bought for. It stays optional: a purchase that is not tied to
    # one workspace keeps working exactly as before and lands on the owner level subscription.
    workspace_slug = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class FeatureFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeatureFlag
        fields = [
            "id",
            "code",
            "name",
            "description",
            "category",
            "is_active",
            "is_public",
            "limit_type",
            "unit_label",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        # The code is the stable key features are wired against, so a rename
        # would silently detach every grant.
        if "code" in validated_data and validated_data.pop("code") != instance.code:
            raise serializers.ValidationError({"code": "The feature flag code cannot be changed."})
        return super().update(instance, validated_data)


class PlanFeatureFlagSerializer(serializers.ModelSerializer):
    """A plan's grant of one feature flag, with the typed limit when there is one.

    The validation here is the whole reason ``limit_value`` is a column and not
    a key inside ``config``: the flag's own ``limit_type`` decides whether a
    limit means anything, and the serializer is the only place that knows both
    sides. A limit on a boolean flag is refused rather than dropped, because a
    silently dropped value shows the administrator a form that saved and does
    nothing.
    """

    feature_flag_code = serializers.CharField(source="feature_flag.code", read_only=True)
    feature_flag_name = serializers.CharField(source="feature_flag.name", read_only=True)
    limit_type = serializers.CharField(source="feature_flag.limit_type", read_only=True)
    unit_label = serializers.CharField(source="feature_flag.unit_label", read_only=True)

    class Meta:
        model = PlanFeatureFlag
        fields = [
            "id",
            "feature_flag",
            "feature_flag_code",
            "feature_flag_name",
            "limit_type",
            "unit_label",
            "is_enabled",
            "limit_value",
            "config",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "limit_type", "unit_label", "created_at", "updated_at"]

    def validate(self, attrs):
        """Check the limit against the flag's declared shape.

        ``feature_flag`` may be a pk on create and absent on a partial update,
        in which case the instance's own flag is the one that decides.
        """
        flag = attrs.get("feature_flag") or getattr(self.instance, "feature_flag", None)
        supplied = "limit_value" in attrs
        limit_value = attrs.get("limit_value")

        if flag is None:
            return attrs

        if flag.limit_type == FeatureFlag.LIMIT_TYPE_NUMBER:
            # A countable bound with no bound stored is a lie, so a full write
            # without one is refused. A partial update that simply omits the
            # field is not: the stored value still stands.
            if limit_value is None and (supplied or not self.partial):
                raise serializers.ValidationError({"limit_value": "برای پرچم عددی، مقدار محدودیت الزامی است."})
            return attrs

        if limit_value is not None:
            raise serializers.ValidationError({"limit_value": "این پرچم محدودیت عددی ندارد."})
        return attrs


class BillingAccessLogSerializer(serializers.ModelSerializer):
    """One operator read of a tenant's money, as the accountability screen shows it.

    The workspace and the viewer are flattened rather than nested: the page exists
    to answer "who read which tenant, and when" at a glance, and both of those are
    nullable -- ``viewer`` is ``SET_NULL``, so a deleted admin's rows stay behind
    unattributed, and ``workspace`` is the tenant whose money was read.
    """

    workspace_slug = serializers.SerializerMethodField()
    workspace_name = serializers.SerializerMethodField()
    viewer_email = serializers.SerializerMethodField()
    viewer_name = serializers.SerializerMethodField()
    view_label = serializers.SerializerMethodField()

    class Meta:
        model = BillingAccessLog
        fields = [
            "id",
            "view",
            "view_label",
            "workspace_slug",
            "workspace_name",
            "viewer_email",
            "viewer_name",
            "ip_address",
            "user_agent",
            "created_at",
        ]
        read_only_fields = fields

    def get_view_label(self, instance) -> str:
        # The label comes from the model's own choices, so a new view type gets a
        # Persian name in one place instead of a second map here that drifts.
        return instance.get_view_display()

    @staticmethod
    def _workspace(instance):
        return instance.workspace

    def get_workspace_slug(self, instance):
        workspace = self._workspace(instance)
        return workspace.slug if workspace else None

    def get_workspace_name(self, instance):
        workspace = self._workspace(instance)
        return workspace.name if workspace else None

    def get_viewer_email(self, instance):
        return instance.viewer.email if instance.viewer else None

    def get_viewer_name(self, instance):
        viewer = instance.viewer
        if viewer is None:
            return None
        return f"{viewer.first_name} {viewer.last_name}".strip() or viewer.email


class AdminLedgerEntrySerializer(serializers.ModelSerializer):
    """Full ledger entry for an instance administrator.

    The audience is an operator who has to reconcile the books, so the actor,
    both account legs, the invoice and transaction links and the idempotency
    key are all present. Nothing here is redacted: that is the point of this
    projection existing alongside ``WorkspaceLedgerEntrySerializer``.
    """

    created_by = serializers.SerializerMethodField()
    workspace = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    source_label = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "amount_toman",
            "source",
            "source_label",
            "description",
            "created_by",
            "workspace",
            "invoice",
            "transaction",
            "debit_account",
            "credit_account",
            "idempotency_key",
            "reversal_of",
            "created_at",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        if obj.created_by is None:
            return None
        return {"id": str(obj.created_by.id), "display_name": obj.created_by.display_name}

    def get_source_label(self, obj):
        return obj.get_source_display()


class WorkspaceLedgerEntrySerializer(serializers.ModelSerializer):
    """Ledger entry for a workspace admin.

    Omits the actor, the invoice and the transaction link so that one
    workspace cannot infer anything about another customer's billing, and
    replaces the internal grant description with a public label.

    ``source`` is dropped rather than merely relabelled: the raw
    ``LedgerSource`` member is internal vocabulary, and a tenant facing
    projection carrying both a code and a label trains the frontend to switch
    on the code.
    """

    source_label = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = ["id", "amount_toman", "source_label", "description", "created_at"]
        read_only_fields = fields

    def get_source_label(self, obj):
        return ledger_service.public_source_label(obj)

    def get_description(self, obj):
        return ledger_service.public_description(obj)


class WalletSerializer(serializers.ModelSerializer):
    """A workspace wallet as its owner sees it.

    ``balance_toman`` and ``hold_balance_toman`` are computed by
    ``services.money`` rather than read off the ``Wallet`` row, which is only
    a pointer at the workspace: the balance only exists as the sum of ledger
    entries. ``admin_grant_cap_toman`` is readable but not writable -- the cap
    is the guard against a mistyped grant, and the view that uses this
    projection is not the one that sets it.
    """

    balance_toman = serializers.SerializerMethodField()
    hold_balance_toman = serializers.SerializerMethodField()
    workspace_slug = serializers.SlugRelatedField(source="workspace", slug_field="slug", read_only=True)

    class Meta:
        model = Wallet
        fields = ["id", "workspace_slug", "balance_toman", "hold_balance_toman", "admin_grant_cap_toman", "created_at"]
        read_only_fields = ["id", "workspace_slug", "balance_toman", "hold_balance_toman", "created_at"]

    def get_balance_toman(self, obj) -> int:
        return money_service.wallet_balance(obj.workspace)

    def get_hold_balance_toman(self, obj) -> int:
        return money_service.wallet_hold_balance(obj.workspace)


# The biggest amount a bigint column can hold. Any larger would raise a
# DataError at the database, which the project's exception handler does not
# treat as a client error, so the bound is applied in the serializer.
MAX_MONEY_TOMAN = 2**63 - 1


class WalletGrantSerializer(serializers.Serializer):
    """Input for an instance admin crediting a workspace by hand.

    Instance admin only. There is deliberately no ``workspace`` field: the
    workspace comes from the URL the view resolved, so it cannot be pointed
    at another tenant from the request body.
    """

    # The upper bound matters: amount_toman is a bigint column, and an amount
    # past 2**63-1 raises DataError rather than IntegrityError, which the
    # project's exception handler does not catch. Without this a client could
    # trigger a 500 with a number instead of getting a 400.
    amount_toman = serializers.IntegerField(min_value=1, max_value=MAX_MONEY_TOMAN)
    description = serializers.CharField(min_length=10)

    def validate_description(self, value: str) -> str:
        stripped = value.strip()
        # ``min_length`` above counts the untrimmed string, so "         x"
        # passes it while carrying no explanation at all. Re-checked on the
        # stripped value because this note is the only record of why an
        # operator minted money.
        if len(stripped) < 10:
            raise serializers.ValidationError("توضیح اعتبار دستی باید حداقل ۱۰ کاراکتر باشد.")
        return stripped


class WalletRevokeSerializer(serializers.Serializer):
    """Input for an instance admin reversing a grant.

    Same shape of argument as ``WalletGrantSerializer``, with a pk instead of
    an amount: ``entry`` names WHICH grant to undo and ``description`` says
    why. There is no ``workspace`` field for the same reason there is none on
    the grant -- the workspace is the one the URL resolved.

    The pk is validated as a UUID here purely so a typo is a 400 rather than
    a database error. It is deliberately NOT looked up: the view resolves it
    scoped by the workspace, so a pk from another tenant cannot be turned
    into a foreign ``LedgerEntry`` however well formed it is.
    """

    entry = serializers.UUIDField()
    description = serializers.CharField(min_length=10)

    def validate_description(self, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 10:
            raise serializers.ValidationError("توضیح ابطال اعتبار باید حداقل ۱۰ کاراکتر باشد.")
        return stripped


class AdminWorkspaceBillingSerializer(serializers.Serializer):
    """The whole billing picture of one workspace for the admin detail page.

    A hand-written ``Serializer`` rather than a ``ModelSerializer`` because no
    single model holds these fields: the plan, the subscription, the workspace
    and the derived balances are four sources. It declares no writable field,
    so a POST body against the detail route is rejected rather than ignored.

    This projection carries the balance, so the view that serves it must write
    an access-log row: returning money to an operator is a money read whatever
    the response shape looks like.
    """

    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    plan_code = serializers.CharField(allow_null=True)
    plan_name = serializers.CharField(allow_null=True)
    seats = serializers.IntegerField()
    balance_toman = serializers.IntegerField()
    hold_balance_toman = serializers.IntegerField()
    subscription_status = serializers.CharField(allow_null=True)
    starts_at = serializers.DateTimeField(allow_null=True)
    ends_at = serializers.DateTimeField(allow_null=True)
    renew_lock_days = serializers.IntegerField(allow_null=True)
    proration_mode = serializers.CharField(allow_null=True)
    active_members = serializers.IntegerField()


class RenewalNoticeScheduleSerializer(serializers.ModelSerializer):
    """The reminder days. The list is checked by the service, the one place that knows the bounds."""

    class Meta:
        model = RenewalNoticeSchedule
        fields = ["days_before", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate_days_before(self, value):
        try:
            return renewal_service.validate_days(value)
        except renewal_service.InvalidSchedule as exc:
            raise serializers.ValidationError(str(exc))
