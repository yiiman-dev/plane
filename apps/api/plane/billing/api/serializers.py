# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from rest_framework import serializers

# Module imports
from plane.billing.models import (
    FeatureFlag,
    GatewayRoutingConfig,
    Invoice,
    PaymentGateway,
    PaymentTransaction,
    Plan,
    PlanFeatureFlag,
    Subscription,
)
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
    feature_flag_code = serializers.CharField(source="feature_flag.code", read_only=True)
    feature_flag_name = serializers.CharField(source="feature_flag.name", read_only=True)

    class Meta:
        model = PlanFeatureFlag
        fields = [
            "id",
            "feature_flag",
            "feature_flag_code",
            "feature_flag_name",
            "is_enabled",
            "config",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
