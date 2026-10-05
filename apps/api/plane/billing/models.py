# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import uuid

# Django imports
from django.db import models
from django.utils import timezone

# Module imports
from plane.db.models.base import BaseModel


class GatewayCode(models.TextChoices):
    ZARINPAL = "zarinpal", "ZarinPal"
    PAYPING = "payping", "PayPing"
    ZIBAL = "zibal", "Zibal"
    DIGIPAY = "digipay", "Digipay"


class RoutingStrategy(models.TextChoices):
    SCHEDULE = "schedule", "Schedule"
    RANDOM = "random", "Random"
    PRIORITY = "priority", "Priority"


class BillingCycle(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    YEARLY = "yearly", "Yearly"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    PAID = "paid", "Paid"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"
    REFUND = "refund", "Refunded"


class TransactionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    REDIRECTED = "redirected", "Redirected"
    PROCESSING = "processing", "Processing"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"
    UNAVAILABLE = "unavailable", "Unavailable"
    REVERSED = "reversed", "Reversed"


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class PaymentGateway(BaseModel):
    """A payment gateway configuration row. Credentials are stored encrypted."""

    code = models.CharField(
        max_length=50,
        choices=GatewayCode.choices,
        unique=True,
        db_index=True,
        verbose_name="Gateway Code",
    )
    title = models.CharField(max_length=255, verbose_name="Title")
    is_enabled = models.BooleanField(default=False, verbose_name="Enabled")
    is_sandbox = models.BooleanField(default=True, verbose_name="Sandbox Mode")
    credentials = models.TextField(blank=True, default="", verbose_name="Encrypted Credentials")
    extra_config = models.JSONField(default=dict, blank=True, verbose_name="Extra Configuration")
    priority = models.IntegerField(default=0, verbose_name="Priority")
    last_error_at = models.DateTimeField(null=True, blank=True, verbose_name="Last Error At")
    last_error_message = models.TextField(blank=True, default="", verbose_name="Last Error Message")

    class Meta:
        verbose_name = "Payment Gateway"
        verbose_name_plural = "Payment Gateways"
        ordering = ("priority", "code")

    def __str__(self) -> str:
        return f"{self.code}"

    def credential_value(self, key: str, default=None):
        """Return a single decrypted credential value."""
        from plane.billing.services.credentials import get_credential

        return get_credential(self, key, default)

    def get_config(self, key: str, default=None):
        return (self.extra_config or {}).get(key, default)

    def mark_healthy(self) -> None:
        self.last_error_at = None
        self.last_error_message = ""
        self.save(update_fields=["last_error_at", "last_error_message", "updated_at"])

    def mark_unhealthy(self, message: str) -> None:
        self.last_error_at = timezone.now()
        self.last_error_message = (message or "")[:2000]
        self.save(update_fields=["last_error_at", "last_error_message", "updated_at"])


class GatewayRoutingConfig(BaseModel):
    """Singleton model holding the multi gateway routing strategy."""

    SINGLETON_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")

    strategy = models.CharField(
        max_length=20,
        choices=RoutingStrategy.choices,
        default=RoutingStrategy.PRIORITY,
        verbose_name="Strategy",
    )
    schedule_entries = models.JSONField(default=list, blank=True, verbose_name="Schedule Entries")
    priority_order = models.JSONField(default=list, blank=True, verbose_name="Priority Order")
    weights = models.JSONField(default=dict, blank=True, verbose_name="Weights")
    cooldown_seconds = models.PositiveIntegerField(default=120, verbose_name="Cooldown Seconds")
    max_attempts_per_gateway = models.PositiveIntegerField(default=2, verbose_name="Max Attempts Per Gateway")
    last_selected_code = models.CharField(max_length=50, blank=True, default="", verbose_name="Last Selected Code")
    last_selected_reason = models.CharField(max_length=255, blank=True, default="", verbose_name="Last Selected Reason")

    class Meta:
        verbose_name = "Gateway Routing Config"
        verbose_name_plural = "Gateway Routing Configs"

    def __str__(self) -> str:
        return f"GatewayRoutingConfig({self.strategy})"

    def save(self, *args, **kwargs):
        self.pk = self.SINGLETON_ID
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):  # pragma: no cover - singleton guard
        return None

    @classmethod
    def get_solo(cls):
        instance, _created = cls.objects.get_or_create(pk=cls.SINGLETON_ID)
        return instance


class Plan(BaseModel):
    """A subscription plan."""

    code = models.CharField(max_length=50, unique=True, db_index=True, verbose_name="Plan Code")
    name = models.CharField(max_length=255, verbose_name="Name")
    description = models.TextField(blank=True, default="", verbose_name="Description")
    access_level = models.CharField(max_length=100, default="", blank=True, verbose_name="Access Level")
    monthly_price_toman = models.BigIntegerField(default=0, verbose_name="Monthly Price Toman")
    yearly_price_toman = models.BigIntegerField(default=0, verbose_name="Yearly Price Toman")
    per_seat_price_toman = models.BigIntegerField(default=0, verbose_name="Per Seat Price Toman")
    included_seats = models.PositiveIntegerField(default=1, verbose_name="Included Seats")
    min_seats = models.PositiveIntegerField(default=1, verbose_name="Minimum Seats")
    max_seats = models.PositiveIntegerField(default=100, verbose_name="Maximum Seats")
    features = models.JSONField(default=list, blank=True, verbose_name="Features")
    is_active = models.BooleanField(default=True, verbose_name="Active")
    sort_order = models.IntegerField(default=0, verbose_name="Sort Order")
    currency = models.CharField(max_length=8, default="IRT", verbose_name="Currency")

    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Plans"
        ordering = ("sort_order", "code")

    def __str__(self) -> str:
        return f"{self.code}"

    def price_for(self, cycle: str) -> int:
        return self.yearly_price_toman if cycle == BillingCycle.YEARLY else self.monthly_price_toman

    def calculate_subtotal(self, seats: int, cycle: str) -> int:
        """Return the subtotal in toman. Discounts and taxes are zero for now."""
        seats = max(self.min_seats, min(int(seats or 0), self.max_seats))
        base = self.price_for(cycle)
        extra_seats = max(0, seats - self.included_seats)
        return int(base) + (int(self.per_seat_price_toman) * extra_seats)


class Invoice(BaseModel):
    """A billing invoice."""

    number = models.CharField(max_length=64, unique=True, db_index=True, verbose_name="Invoice Number")
    user = models.ForeignKey("db.User", on_delete=models.PROTECT, related_name="billing_invoices", verbose_name="User")
    plan = models.ForeignKey("billing.Plan", on_delete=models.PROTECT, related_name="invoices", verbose_name="Plan")
    seats = models.PositiveIntegerField(default=1, verbose_name="Seats")
    cycle = models.CharField(
        max_length=20, choices=BillingCycle.choices, default=BillingCycle.MONTHLY, verbose_name="Cycle"
    )
    subtotal_toman = models.BigIntegerField(default=0, verbose_name="Subtotal Toman")
    discount_toman = models.BigIntegerField(default=0, verbose_name="Discount Toman")
    total_toman = models.BigIntegerField(default=0, verbose_name="Total Toman")
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
        db_index=True,
        verbose_name="Status",
    )
    issued_at = models.DateTimeField(null=True, blank=True, verbose_name="Issued At")
    due_at = models.DateTimeField(null=True, blank=True, verbose_name="Due At")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Paid At")
    notes = models.TextField(blank=True, default="", verbose_name="Notes")
    metadata = models.JSONField(default=dict, blank=True, verbose_name="Metadata")

    class Meta:
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.number}"

    @classmethod
    def generate_number(cls) -> str:
        stamp = timezone.now().strftime("%Y%m")
        suffix = uuid.uuid4().hex[:10].upper()
        return f"INV-{stamp}-{suffix}"

    @property
    def amount_toman(self) -> int:
        return int(self.total_toman)


class PaymentTransaction(BaseModel):
    """A single payment attempt against one gateway."""

    invoice = models.ForeignKey(
        "billing.Invoice",
        on_delete=models.PROTECT,
        related_name="transactions",
        null=True,
        blank=True,
        verbose_name="Invoice",
    )
    user = models.ForeignKey(
        "db.User", on_delete=models.PROTECT, related_name="billing_transactions", verbose_name="User"
    )
    gateway_code = models.CharField(max_length=50, choices=GatewayCode.choices, verbose_name="Gateway Code")
    gateway_token = models.CharField(max_length=255, verbose_name="Gateway Token")
    gateway_ref_id = models.CharField(max_length=255, blank=True, default="", verbose_name="Gateway Reference Id")
    amount_toman = models.BigIntegerField(default=0, verbose_name="Amount Toman")
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
        db_index=True,
        verbose_name="Status",
    )
    gateway_fee = models.BigIntegerField(null=True, blank=True, verbose_name="Gateway Fee")
    gateway_amount = models.BigIntegerField(null=True, blank=True, verbose_name="Gateway Amount")
    callback_payload = models.JSONField(default=dict, blank=True, verbose_name="Callback Payload")
    verify_payload = models.JSONField(default=dict, blank=True, verbose_name="Verify Payload")
    failure_reason = models.TextField(blank=True, default="", verbose_name="Failure Reason")
    attempts = models.PositiveIntegerField(default=0, verbose_name="Attempts")
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name="Verified At")
    paid_at = models.DateTimeField(null=True, blank=True, verbose_name="Paid At")
    meta = models.JSONField(default=dict, blank=True, verbose_name="Meta")

    class Meta:
        verbose_name = "Payment Transaction"
        verbose_name_plural = "Payment Transactions"
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["gateway_code", "gateway_token"],
                name="unique_gateway_token_per_gateway",
            )
        ]

    def __str__(self) -> str:
        return f"{self.gateway_code}:{self.gateway_token}"

    def mark_paid(self, ref_id: str = "", amount_toman: int = 0, fee=None) -> None:
        now = timezone.now()
        self.status = TransactionStatus.PAID
        self.paid_at = self.paid_at or now
        self.verified_at = self.verified_at or now
        self.failure_reason = ""
        if ref_id:
            self.gateway_ref_id = ref_id
        if amount_toman:
            self.amount_toman = int(amount_toman)
        if fee is not None:
            self.gateway_fee = fee

    def mark_status(self, status: str, reason: str = "") -> None:
        self.status = status
        self.failure_reason = (reason or "")[:2000]
        if status in (TransactionStatus.PAID, TransactionStatus.PROCESSING, TransactionStatus.FAILED):
            self.verified_at = self.verified_at or timezone.now()


class Subscription(BaseModel):
    """An active (or historic) subscription bound to a paid invoice."""

    user = models.ForeignKey(
        "db.User", on_delete=models.CASCADE, related_name="billing_subscriptions", verbose_name="User"
    )
    plan = models.ForeignKey(
        "billing.Plan", on_delete=models.PROTECT, related_name="subscriptions", verbose_name="Plan"
    )
    # Plans are workspace entitlements, so the subscription records which
    # workspace it was bought for. It stays nullable because a purchase made
    # before this field existed has no workspace to point at.
    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="billing_subscriptions",
        null=True,
        blank=True,
        verbose_name="Workspace",
    )
    seats = models.PositiveIntegerField(default=1, verbose_name="Seats")
    cycle = models.CharField(
        max_length=20, choices=BillingCycle.choices, default=BillingCycle.MONTHLY, verbose_name="Cycle"
    )
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.ACTIVE,
        verbose_name="Status",
    )
    starts_at = models.DateTimeField(null=True, blank=True, verbose_name="Starts At")
    ends_at = models.DateTimeField(null=True, blank=True, verbose_name="Ends At")
    auto_renew = models.BooleanField(default=False, verbose_name="Auto Renew")
    source_transaction = models.ForeignKey(
        "billing.PaymentTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
        verbose_name="Source Transaction",
    )

    class Meta:
        verbose_name = "Subscription"
        verbose_name_plural = "Subscriptions"
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.user_id}:{self.plan_id}"


class FeatureFlag(BaseModel):
    """A capability that a plan can grant and a workspace can turn on.

    The row is the catalogue only. A feature needs three layers before it is
    actually usable: this row has to be globally active, the workspace plan has
    to grant it through ``PlanFeatureFlag``, and the workspace itself has to
    switch it on through ``WorkspaceFeatureFlag``.
    """

    code = models.CharField(max_length=100, unique=True, db_index=True, verbose_name="Feature Flag Code")
    name = models.CharField(max_length=255, verbose_name="Name")
    description = models.TextField(blank=True, default="", verbose_name="Description")
    category = models.CharField(max_length=100, blank=True, default="general", verbose_name="Category")
    is_active = models.BooleanField(default=True, db_index=True, verbose_name="Active")
    is_public = models.BooleanField(default=True, verbose_name="Public")

    class Meta:
        verbose_name = "Feature Flag"
        verbose_name_plural = "Feature Flags"
        ordering = ("category", "code")

    def __str__(self) -> str:
        return self.code


class PlanFeatureFlag(BaseModel):
    """Links a plan to a feature flag it is allowed to unlock."""

    plan = models.ForeignKey(
        "billing.Plan", on_delete=models.CASCADE, related_name="feature_flags", verbose_name="Plan"
    )
    feature_flag = models.ForeignKey(
        "billing.FeatureFlag",
        on_delete=models.CASCADE,
        related_name="plan_grants",
        verbose_name="Feature Flag",
    )
    is_enabled = models.BooleanField(default=True, verbose_name="Enabled")
    config = models.JSONField(default=dict, blank=True, verbose_name="Config")

    class Meta:
        verbose_name = "Plan Feature Flag"
        verbose_name_plural = "Plan Feature Flags"
        ordering = ("plan__code", "feature_flag__code")
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "feature_flag"],
                name="unique_plan_feature_flag",
            )
        ]

    def __str__(self) -> str:
        return f"{self.plan_id}:{self.feature_flag_id}"


class WorkspaceFeatureFlag(BaseModel):
    """The workspace level switch that turns a granted feature on or off."""

    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="billing_feature_flags",
        verbose_name="Workspace",
    )
    feature_flag = models.ForeignKey(
        "billing.FeatureFlag",
        on_delete=models.CASCADE,
        related_name="workspace_activations",
        verbose_name="Feature Flag",
    )
    is_enabled = models.BooleanField(default=False, verbose_name="Enabled")
    enabled_by = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        related_name="enabled_billing_feature_flags",
        null=True,
        blank=True,
        verbose_name="Enabled By",
    )
    enabled_at = models.DateTimeField(null=True, blank=True, verbose_name="Enabled At")
    config = models.JSONField(default=dict, blank=True, verbose_name="Config")

    class Meta:
        verbose_name = "Workspace Feature Flag"
        verbose_name_plural = "Workspace Feature Flags"
        ordering = ("feature_flag__category", "feature_flag__code")
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "feature_flag"],
                name="unique_workspace_feature_flag",
            )
        ]

    def __str__(self) -> str:
        return f"{self.workspace_id}:{self.feature_flag_id}"
