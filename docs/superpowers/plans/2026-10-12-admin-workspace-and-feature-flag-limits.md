# Admin Workspace Detail and Feature Flag Limits — Implementation Plan (Phase 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an instance administrator one page per workspace showing its plan, seats, wallet and ledger, and give each feature flag a typed limit so a plan form can render a switch, a number or "unlimited" from the catalogue instead of hardcoding.

**Architecture:** Four new model columns (`FeatureFlag.limit_type`, `FeatureFlag.unit_label`, `PlanFeatureFlag.limit_value`, and three `Plan` policy fields) land in a single migration. An audit trail (`BillingAccessLog`) records every instance-admin read of a tenant wallet or ledger, because the admin may see everything and the risk that creates is managed by traceability rather than by hiding data. A new `feature_limit()` reader makes the stored limit reachable by code, so this phase does not repeat the mistake `has_feature()` already made by storing data nothing read.

**Tech Stack:** Django 5.x, Django REST Framework, PostgreSQL, pytest-django; Next.js 15 / React 19 for the admin panel, SWR, `@plane/types`, `@plane/services`.

**Spec:** `docs/superpowers/specs/2026-10-07-billing-wallet-upgrade-design.md` — §3 (model changes), §8.5 (access log), §9 (UI), §10 (AGENTS.md rule).

---

## Global Constraints

- **`amount_toman` is always positive Toman.** Never Rial. Never introduce a balance column — `services/money.py` computes every balance from ledger entries.
- **Copy is Persian.** Every user-facing string, every admin-facing label, every error message added here is Persian, matching `apps/api/plane/billing`.
- **`FeatureFlag.code` is immutable.** It is the stable key features are wired against; a rename silently detaches every grant. `FeatureFlagSerializer.update()` already enforces this — keep it.
- **`PlanFeatureFlag.config` is NOT restructured.** It stays a free JSONField and is left untouched. The typed limit is the new `limit_value` column. A later migration may retire `config`; this phase does not.
- **A `limit_value` sent for a `boolean` flag is a 400, not silently ignored.** Silently dropping it means the admin's UI appears to save and does not work.
- **Admin money reads are audited.** Any new instance-admin view that reads a tenant wallet or ledger calls the logging service before returning.
- **`WorkspaceBillingLedgerPermission` (role 20 only) must never guard instance-admin data.** The two families stay separate: `InstanceAdminPermission` for `/admin/…`, `WorkspaceBillingLedgerPermission` for `/workspaces/…`.
- **No endpoint may read a workspace, slug or scope from the query string.** A workspace comes from the URL kwarg only.
- Python files start with the existing copyright header, then section comments (`# Python imports`, `# Django imports`, `# Module imports`) as in `apps/api/plane/billing/models.py:1-13`.
- TypeScript files start with the existing copyright header as in `apps/admin/app/(all)/(dashboard)/billing/plans/page.tsx:1-5`.
- **Backend tests run in Docker, never locally:**
  ```bash
  docker compose -f docker-compose-test.yml up -d test-db test-redis
  docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest <path> -v
  ```
  Never drop `--no-deps --pull never`. If EVERY test errors at setup with `OperationalError` or "failed to resolve host", the DB is down rather than your code — run the `up -d test-db test-redis` line and re-run.
- **After any model change, run tests with `--create-db`.** `apps/api/pytest.ini:15` sets `--reuse-db`, which keeps a stale schema and silently validates the OLD model instead of the new one. This was measured: removing `unique=True` from `LedgerEntry.idempotency_key` broke no test under `--reuse-db` and did break it under `--create-db`. A constraint is only proven by a run that rebuilt the schema.
- **`pytest.ini` sets `--nomigrations`**, so no test ever applies a migration. `makemigrations --check --dry-run` is the only automated validation; a real `migrate` has never been run against these migrations.

### Fixture rules that break tests when forgotten

- `Workspace.owner` is NOT NULL with no default. Always build workspaces with the `workspace_factory` fixture in `apps/api/plane/billing/tests/conftest.py:152`, which creates a distinct `User` per call.
- `User.email` and `User.username` are both unique and neither is auto-populated. The fixture feeds both from one `uuid4` hex, so two calls in one test never collide.
- `SoftDeleteModel` is on every billing model: `delete()` only stamps `deleted_at`, and the default manager hides the row while the unique column stays occupied. To reuse a deleted row, go through `all_objects` and revive it.
- `QuerySet.create()` never forwards kwargs to `save()`, so `BaseModel.save` (`apps/api/plane/db/models/base.py:22`) overwrites `created_by`. To persist a specific `created_by`, call `save(force_insert=True, disable_auto_set_user=...)`.

---

## File Structure

**Backend — created**

| File                                                 | Responsibility                                                                                       |
| ---------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `apps/api/plane/billing/tests/test_phase2_limits.py` | Tests for the model columns, the serializer validation, and `feature_limit()`                        |
| `apps/api/plane/billing/tests/test_access_log.py`    | Tests that every admin money read writes an audit row, and that a workspace role cannot read the log |

**Backend — modified**

| File                                                            | Responsibility                                                                                                                     |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `apps/api/plane/billing/models.py`                              | Add `limit_type`, `unit_label`, `limit_value`, `renew_lock_days`, `proration_mode`, `sms_prices`, and the `BillingAccessLog` model |
| `apps/api/plane/billing/migrations/0006_feature_flag_limits.py` | One migration for all of the above                                                                                                 |
| `apps/api/plane/billing/services/entitlements.py`               | Add `feature_limit(workspace, code)`                                                                                               |
| `apps/api/plane/billing/services/ledger.py`                     | Add `record_admin_read(...)`                                                                                                       |
| `apps/api/plane/billing/api/serializers.py`                     | Extend `PlanSerializer`, `FeatureFlagSerializer`, `PlanFeatureFlagSerializer`; add `AdminWorkspaceBillingSerializer`               |
| `apps/api/plane/billing/api/views/admin_views.py`               | Add `AdminWorkspaceListEndpoint`, `AdminWorkspaceBillingOverviewEndpoint`, `AdminFeatureFlagListEndpoint`                          |
| `apps/api/plane/billing/api/views/wallet_views.py`              | Call `record_admin_read` in the two existing admin money views                                                                     |
| `apps/api/plane/billing/api/urls.py`                            | Register the three new routes                                                                                                      |
| `apps/api/plane/billing/tests/test_api_views.py`                | Extend `ADMIN_URLS` so the non-admin canary covers the new routes                                                                  |
| `AGENTS.md`                                                     | Add the mandatory feature-flag registration rule                                                                                   |

**Frontend — created**

| File                                                                             | Responsibility                          |
| -------------------------------------------------------------------------------- | --------------------------------------- |
| `apps/admin/app/(all)/(dashboard)/billing/workspaces/page.tsx`                   | The workspace list table                |
| `apps/admin/app/(all)/(dashboard)/billing/workspaces/[slug]/page.tsx`            | The per-workspace detail page with tabs |
| `apps/admin/app/(all)/(dashboard)/billing/feature-flags/page.tsx`                | The flag catalogue, grouped by category |
| `apps/admin/app/(all)/(dashboard)/billing/components/workspace-billing-tabs.tsx` | The tab strip on the detail page        |

**Frontend — modified**

| File                                                                     | Responsibility                                                                                    |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `packages/types/src/billing/index.ts`                                    | Add `TFeatureFlag`, `TPlanFeatureFlag`, `TAdminWorkspaceBilling`, and the three new `Plan` fields |
| `packages/services/src/billing/billing.service.ts`                       | Add `adminWorkspaces`, `adminWorkspaceBilling`, `featureFlags`, `planFeatureFlags`                |
| `packages/services/src/billing/index.ts`                                 | Add the SWR cache keys                                                                            |
| `apps/admin/app/(all)/(dashboard)/billing/components/billing-layout.tsx` | Extend `BILLING_TABS` with the three new routes                                                   |
| `apps/admin/app/(all)/(dashboard)/billing/plans/page.tsx`                | Render the typed flag controls in the plan form                                                   |

**Task order.** Tasks 1–4 are backend and independently testable. Tasks 5–6 are frontend. Task 7 is whole-feature verification. Task 1 must land before 2 (the serializer validates against `limit_type`, which 1 creates), and 2 before 4 (`feature_limit` reads `limit_value`).

---

## Task 1: Model columns and the audit table

**Files:**

- Modify: `apps/api/plane/billing/models.py`
- Create: `apps/api/plane/billing/migrations/0006_feature_flag_limits.py` (generated, not hand-written)

**Interfaces:**

- Consumes: nothing. This is the first task.
- Produces:
  - `FeatureFlag.limit_type: str` — one of `FeatureFlag.LIMIT_TYPE_BOOLEAN` (`"boolean"`), `FeatureFlag.LIMIT_TYPE_NUMBER` (`"number"`), `FeatureFlag.LIMIT_TYPE_UNLIMITED` (`"unlimited"`). Default `"boolean"`.
  - `FeatureFlag.unit_label: str` — blank, default `""`. Persian noun such as «نمودار» or «پروژه».
  - `PlanFeatureFlag.limit_value: Optional[int]` — `PositiveIntegerField`, `null=True, blank=True`.
  - `Plan.renew_lock_days: int` — `PositiveIntegerField`, default `0`.
  - `Plan.proration_mode: str` — `CharField`, default `"credit_remaining"`, choices `credit_remaining | no_extension`.
  - `Plan.sms_prices: dict` — `JSONField`, default `dict`.
  - `BillingAccessLog` — fields `viewer` (FK `db.User`, `CASCADE`, related_name `"billing_access_logs"`), `workspace` (FK `db.Workspace`, `CASCADE`, related_name `"billing_access_logs"`), `view` (CharField `max_length=16`, choices `BillingAccessLog.VIEW_WALLET = "wallet"` / `VIEW_LEDGER = "ledger"`), `ip_address` (CharField `max_length=45`, blank, default `""`), `user_agent` (CharField `max_length=512`, blank, default `""`), `created_at`. Meta `ordering = ("-created_at",)`, and a `db_index` on `workspace`.

**Note on field widths.** `ip_address` is `max_length=45`, the length of the longest textual IPv6 form. `user_agent` is 512 because real user agents exceed 256 and a truncated agent makes an audit trail useless.

- [ ] **Step 1: Write the failing test**

Create `apps/api/plane/billing/tests/test_phase2_limits.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Phase 2: typed feature flag limits and the three Plan policy fields."""

import pytest
from django.db import transaction

from plane.billing.models import (
    BillingAccessLog,
    FeatureFlag,
    Plan,
    PlanFeatureFlag,
)


def test_a_new_flag_defaults_to_a_boolean_limit(db):
    flag = FeatureFlag.objects.create(code="charts", name="نمودارها")
    assert flag.limit_type == FeatureFlag.LIMIT_TYPE_BOOLEAN
    assert flag.unit_label == ""


@pytest.mark.parametrize("limit_type", ["boolean", "number", "unlimited"])
def test_every_limit_type_is_accepted(db, limit_type):
    flag = FeatureFlag.objects.create(code=f"flag-{limit_type}", name="پرچم", limit_type=limit_type)
    flag.refresh_from_db()
    assert flag.limit_type == limit_type


def test_an_unknown_limit_type_is_refused_by_the_database(db):
    """choices is enforced by Django's validator, not by the column type."""
    from django.core.exceptions import ValidationError

    flag = FeatureFlag(code="bad", name="بد", limit_type="infinite")
    with pytest.raises(ValidationError):
        flag.full_clean()


def test_a_plan_carries_its_three_policy_fields(db):
    plan = Plan.objects.create(code="pro", name="حرفه‌ای", monthly_price_toman=1000)
    assert plan.renew_lock_days == 0
    assert plan.proration_mode == Plan.PRORATION_CREDIT_REMAINING
    assert plan.sms_prices == {}


def test_sms_prices_round_trip_as_a_dict(db):
    plan = Plan.objects.create(code="pro2", name="حرفه‌ای", sms_prices={"send_sms": 120})
    plan.refresh_from_db()
    assert plan.sms_prices == {"send_sms": 120}


def test_a_granted_number_flag_carries_its_limit(db):
    plan = Plan.objects.create(code="p3", name="پلن")
    flag = FeatureFlag.objects.create(code="projects", name="پروژه", limit_type="number", unit_label="پروژه")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, limit_value=10)
    grant.refresh_from_db()
    assert grant.limit_value == 10


def test_a_limit_is_optional(db):
    plan = Plan.objects.create(code="p4", name="پلن")
    flag = FeatureFlag.objects.create(code="boolflag", name="پرچم")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag)
    assert grant.limit_value is None


def test_config_survives_the_migration_untouched(db):
    """The decision: config stays a free JSONField. Retiring it is a later migration."""
    plan = Plan.objects.create(code="p5", name="پلن")
    flag = FeatureFlag.objects.create(code="legacy", name="قدیمی")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, config={"anything": [1, 2]})
    grant.refresh_from_db()
    assert grant.config == {"anything": [1, 2]}


def test_an_access_log_row_records_the_viewer_and_the_workspace(db, workspace_factory):
    from plane.db.models import User

    workspace = workspace_factory(name="تیم لاگ")
    viewer = User.objects.create(username="auditor", email="auditor@example.com")

    BillingAccessLog.objects.create(
        viewer=viewer, workspace=workspace, view=BillingAccessLog.VIEW_LEDGER, ip_address="127.0.0.1"
    )

    row = BillingAccessLog.objects.get()
    assert row.viewer_id == viewer.pk
    assert row.workspace_id == workspace.pk
    assert row.view == "ledger"


def test_deleting_a_workspace_takes_its_access_log_with_it(db, workspace_factory):
    workspace = workspace_factory(name="تیم حذف")
    BillingAccessLog.objects.create(workspace=workspace, view=BillingAccessLog.VIEW_WALLET)
    workspace.delete()
    assert BillingAccessLog.objects.count() == 0
```

`BillingAccessLog.viewer` must be nullable — a background job or a deleted admin can still produce a read, and losing the row would erase the very evidence the row exists to keep. Adjust the model field to `null=True, blank=True` and drop the `viewer=` argument in `test_an_access_log_row_records_the_viewer_and_the_workspace` if you make it required; the test above already omits it in `test_deleting_a_workspace_takes_its_access_log_with_it`, so make `viewer` nullable to match.

- [ ] **Step 2: Run the test to verify it fails**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_phase2_limits.py -v
```

Expected: `ImportError` / `AttributeError` — `BillingAccessLog`, `limit_type` and `limit_value` do not exist.

- [ ] **Step 3: Add the model changes**

In `apps/api/plane/billing/models.py`, inside `class Plan`, after `currency`:

```python
    # Phase 2: policy fields the Phase 3 and Phase 4 code reads. They land together
    # so neither of those phases needs a migration of its own.
    renew_lock_days = models.PositiveIntegerField(
        default=0, verbose_name="Renew Lock Days", help_text="Days before expiry that a renewal of the same plan is refused."
    )
    proration_mode = models.CharField(
        max_length=32,
        default=PRORATION_CREDIT_REMAINING,
        choices=PRORATION_MODE_CHOICES,
        verbose_name="Proration Mode",
    )
    sms_prices = models.JSONField(
        default=dict, blank=True, verbose_name="SMS Prices", help_text="Event code to price in Toman."
    )
```

Add the choices above the `Plan` class:

```python
# How an upgrade in the middle of a paid cycle treats the unused remainder.
PRORATION_CREDIT_REMAINING = "credit_remaining"
PRORATION_NO_EXTENSION = "no_extension"
PRORATION_MODE_CHOICES = (
    (PRORATION_CREDIT_REMAINING, "اعتبار باقیمانده"),
    (PRORATION_NO_EXTENSION, "بدون تمدید دوره"),
)
```

Inside `class FeatureFlag`, after `is_public`:

```python
    # A flag either switches on or carries a countable limit. One global number
    # across all flags does not work: "5 charts" and "10 projects" are not the
    # same constraint, so each flag declares its own shape.
    limit_type = models.CharField(
        max_length=16,
        default=LIMIT_TYPE_BOOLEAN,
        choices=LIMIT_TYPE_CHOICES,
        verbose_name="Limit Type",
    )
    unit_label = models.CharField(
        max_length=64, blank=True, default="", verbose_name="Unit Label", help_text="Persian noun for a numeric limit."
    )
```

Add above `class FeatureFlag`:

```python
# A flag is either a switch, a number with a unit, or explicitly unlimited.
LIMIT_TYPE_BOOLEAN = "boolean"
LIMIT_TYPE_NUMBER = "number"
LIMIT_TYPE_UNLIMITED = "unlimited"
LIMIT_TYPE_CHOICES = (
    (LIMIT_TYPE_BOOLEAN, "روشن یا خاموش"),
    (LIMIT_TYPE_NUMBER, "محدودیت عددی"),
    (LIMIT_TYPE_UNLIMITED, "نامحدود"),
)
```

Inside `class PlanFeatureFlag`, after `config`:

```python
    # The typed limit, kept beside the free-form ``config`` rather than inside it.
    # ``config`` is writable today through the admin plan-flag endpoint and accepts
    # arbitrary JSON, so restructuring it would turn valid writes into 400s. Only
    # meaningful when the flag's limit_type is "number"; the serializer rejects it
    # otherwise rather than storing a value nothing reads.
    limit_value = models.PositiveIntegerField(null=True, blank=True, verbose_name="Limit Value")
```

Then append the new model at the end of the file:

```python
class BillingAccessLog(BaseModel):
    """Every time an instance administrator reads a tenant's money.

    An instance admin can see any workspace's wallet and ledger, and hiding that
    would leave them unable to answer a customer's billing question. The risk
    that creates -- a customer's financial data ending up in the wrong hands --
    is managed by traceability rather than by pretending the operator does not
    exist: every read leaves a row naming who looked, at which workspace and
    when.

    Only instance admins read this table. ``WorkspaceBillingLedgerPermission``
    must never be given access: "who looked at me" has no meaning to a
    workspace admin and only widens the surface.
    """

    VIEW_WALLET = "wallet"
    VIEW_LEDGER = "ledger"
    VIEW_CHOICES = (
        (VIEW_WALLET, "کیف پول"),
        (VIEW_LEDGER, "دفتر کل"),
    )

    # Nullable: a background job or a since-deleted admin can still produce a
    # read, and dropping the row would erase the evidence it exists to keep.
    viewer = models.ForeignKey(
        "db.User",
        on_delete=models.SET_NULL,
        related_name="billing_access_logs",
        null=True,
        blank=True,
        verbose_name="Viewer",
    )
    workspace = models.ForeignKey(
        "db.Workspace",
        on_delete=models.CASCADE,
        related_name="billing_access_logs",
        verbose_name="Workspace",
    )
    view = models.CharField(max_length=16, choices=VIEW_CHOICES, verbose_name="View")
    ip_address = models.CharField(max_length=45, blank=True, default="", verbose_name="IP Address")
    user_agent = models.CharField(max_length=512, blank=True, default="", verbose_name="User Agent")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Created At")

    class Meta:
        verbose_name = "Billing Access Log"
        verbose_name_plural = "Billing Access Logs"
        ordering = ("-created_at",)
        indexes = [models.Index(fields=["workspace", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.view}:{self.workspace_id}"
```

Note: `created_at` is declared explicitly because `BaseModel` may already provide it — if `BaseModel` supplies `created_at`, **delete the explicit `created_at` line above** rather than shadowing it, and confirm the model still imports.

- [ ] **Step 4: Generate the migration and verify**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests python manage.py makemigrations billing --name feature_flag_limits
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests python manage.py makemigrations --check --dry-run
```

Expected: `0006_feature_flag_limits.py` written, then `No changes detected`.

Read the generated file. Every operation must be `AddField` or `CreateModel`. **If it contains a `RemoveField` or an `AlterField` that rewrites `PlanFeatureFlag.config`, stop** — that means the migration would rewrite existing data and the decision was violated.

- [ ] **Step 5: Run the tests**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_phase2_limits.py -v --create-db
```

Expected: all pass. `--create-db` is required: without it `--reuse-db` keeps the old schema and the new columns are silently absent.

- [ ] **Step 6: Verify the rest of the suite did not regress**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest -m unit -q --create-db
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff check plane/billing/
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff format plane/billing/
```

Expected: `432 passed` (the pre-existing baseline), `All checks passed!`.

- [ ] **Step 7: Commit**

```bash
git add apps/api/plane/billing/models.py apps/api/plane/billing/migrations/ apps/api/plane/billing/tests/test_phase2_limits.py
git commit -m "feat(billing): typed feature flag limits and the admin access log"
```

---

## Task 2: Serializers that reject an invalid limit

**Files:**

- Modify: `apps/api/plane/billing/api/serializers.py` (`PlanSerializer` ~line 103, `FeatureFlagSerializer` ~line 297, `PlanFeatureFlagSerializer` ~line 321)
- Modify: `apps/api/plane/billing/tests/test_phase2_limits.py`

**Interfaces:**

- Consumes: `FeatureFlag.limit_type`, `FeatureFlag.unit_label`, `PlanFeatureFlag.limit_value`, `Plan.renew_lock_days`, `Plan.proration_mode`, `Plan.sms_prices` from Task 1.
- Produces:
  - `PlanSerializer.Meta.fields` gains `renew_lock_days`, `proration_mode`, `sms_prices`.
  - `FeatureFlagSerializer` gains writable `limit_type` and `unit_label`.
  - `PlanFeatureFlagSerializer` gains writable `limit_value` and raises `serializers.ValidationError({"limit_value": ...})` when a `limit_value` is supplied for a flag whose `limit_type` is not `number`, or when a `number` flag is saved with no `limit_value`.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/plane/billing/tests/test_phase2_limits.py`:

```python
def _plan_with_flag(limit_type: str, **flag_kwargs):
    plan = Plan.objects.create(code=f"sp-{limit_type}-{flag_kwargs}", name="پلن")
    flag = FeatureFlag.objects.create(code=f"f-{limit_type}-{flag_kwargs}", name="پرچم", limit_type=limit_type, **flag_kwargs)
    return plan, flag


def test_a_number_flag_stores_its_limit(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="پروژه")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True, "limit_value": 25})

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["limit_value"] == 25


def test_a_limit_on_a_boolean_flag_is_refused_not_ignored(db):
    """Silently dropping it would let the admin's UI appear to save and do nothing."""
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("boolean")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True, "limit_value": 5})

    assert serializer.is_valid() is False
    assert "limit_value" in serializer.errors


def test_a_limit_on_an_unlimited_flag_is_refused(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("unlimited")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True, "limit_value": 5})

    assert serializer.is_valid() is False
    assert "limit_value" in serializer.errors


def test_a_number_flag_saved_without_a_limit_is_refused(db):
    """The whole point of limit_type=number is a countable bound. Without it the flag is a lie."""
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="نمودار")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True})

    assert serializer.is_valid() is False
    assert "limit_value" in serializer.errors


def test_a_boolean_flag_saved_without_a_limit_is_fine(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("boolean")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True})

    assert serializer.is_valid(), serializer.errors


def test_an_explicit_null_limit_on_a_number_flag_is_refused(db):
    from plane.billing.api.serializers import PlanFeatureFlagSerializer

    plan, flag = _plan_with_flag("number", unit_label="پروژه")
    serializer = PlanFeatureFlagSerializer(data={"feature_flag": flag.pk, "is_enabled": True, "limit_value": None})

    assert serializer.is_valid() is False
    assert "limit_value" in serializer.errors


def test_the_flag_catalogue_exposes_the_typed_limit(db):
    from plane.billing.api.serializers import FeatureFlagSerializer

    flag = FeatureFlag.objects.create(code="charts", name="نمودارها", limit_type="number", unit_label="نمودار")
    body = FeatureFlagSerializer(flag).data

    assert body["limit_type"] == "number"
    assert body["unit_label"] == "نمودار"


def test_the_plan_projection_exposes_the_three_policy_fields(db):
    from plane.billing.api.serializers import PlanSerializer

    plan = Plan.objects.create(
        code="pp", name="پلن", renew_lock_days=7, proration_mode="no_extension", sms_prices={"send_sms": 250}
    )
    body = PlanSerializer(plan).data

    assert body["renew_lock_days"] == 7
    assert body["proration_mode"] == "no_extension"
    assert body["sms_prices"] == {"send_sms": 250}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_phase2_limits.py -v
```

Expected: the four new validation tests fail; the two read-only tests fail on a missing key.

- [ ] **Step 3: Extend the serializers**

In `apps/api/plane/billing/api/serializers.py`, add `renew_lock_days`, `proration_mode` and `sms_prices` to `PlanSerializer.Meta.fields`, after `"currency"`.

Add `limit_type` and `unit_label` to `FeatureFlagSerializer.Meta.fields`, after `"is_public"`.

Replace `PlanFeatureFlagSerializer` with:

```python
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
            if supplied and limit_value is None:
                raise serializers.ValidationError(
                    {"limit_value": "برای پرچم عددی، مقدار محدودیت الزامی است."}
                )
            if not supplied and not self.partial and limit_value is None:
                raise serializers.ValidationError(
                    {"limit_value": "برای پرچم عددی، مقدار محدودیت الزامی است."}
                )
            return attrs

        if supplied and limit_value is not None:
            raise serializers.ValidationError(
                {"limit_value": "این پرچم محدودیت عددی ندارد."}
            )
        return attrs
```

Confirm `FeatureFlag` is imported in `serializers.py`. If not, add it to the existing `from plane.billing.models import (...)` block.

**Note on the partial-update branch.** The second `if` in the number branch fires only on a full create. On a partial update of a grant that already has a stored `limit_value`, omitting the field must not fail — the stored value still stands. That is why the check is `not self.partial`.

- [ ] **Step 4: Make the view pass the limit through**

`PlanFeatureFlagEndpoint.post` (`apps/api/plane/billing/api/views/admin_views.py:303`) currently writes `defaults={...}` without `limit_value`, so the validated value would be dropped. Change it to:

```python
        defaults = {
            "is_enabled": serializer.validated_data.get("is_enabled", True),
            "config": serializer.validated_data.get("config", {}),
        }
        if "limit_value" in serializer.validated_data:
            defaults["limit_value"] = serializer.validated_data["limit_value"]
```

The `if` is required rather than a bare `defaults["limit_value"] = serializer.validated_data.get("limit_value")`: `update_or_create` with a missing key must not clear a stored limit. Omitting the field means "leave it alone"; only an explicit value changes it. Since a `number` flag always sends a value, the "clear a number flag's limit" case is unreachable by validation.

- [ ] **Step 5: Run the tests**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_phase2_limits.py -v --create-db
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing -q
```

Expected: all of Task 1's tests still pass plus the new ones; then the whole billing suite passes with no regression.

- [ ] **Step 6: Lint and commit**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff check plane/billing/
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff format --check plane/billing/
git add apps/api/plane/billing/api/serializers.py apps/api/plane/billing/api/views/admin_views.py apps/api/plane/billing/tests/test_phase2_limits.py
git commit -m "feat(billing): validate a feature limit against the flag's own type"
```

---

## Task 3: The access log service and the two admin money views

**Files:**

- Modify: `apps/api/plane/billing/services/ledger.py`
- Modify: `apps/api/plane/billing/api/views/wallet_views.py` (`AdminWorkspaceWalletView.get` ~line 225, `AdminWorkspaceLedgerView.get` ~line 246)
- Create: `apps/api/plane/billing/tests/test_access_log.py`

**Interfaces:**

- Consumes: `BillingAccessLog` from Task 1; `AdminWorkspaceWalletView` / `AdminWorkspaceLedgerView` from Phase 1.
- Produces:
  - `ledger.record_admin_read(*, workspace, view: str, request) -> BillingAccessLog | None`. Writes one row. Returns `None` when `request.user` is not authenticated (so an anonymous request, which the permission already rejected, leaves no row). **Never raises** — an audit failure must not break the read the operator is entitled to.

- [ ] **Step 1: Write the failing tests**

Create `apps/api/plane/billing/tests/test_access_log.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Every instance-admin read of a tenant wallet or ledger leaves an audit row."""

import pytest

from plane.billing.models import BillingAccessLog
from plane.billing.services import ledger


def test_reading_a_wallet_as_admin_writes_one_row(client, funded_workspace, instance_admin):
    workspace, _operator = funded_workspace
    client.force_login(instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/")

    assert response.status_code == 200
    row = BillingAccessLog.objects.get()
    assert row.viewer_id == instance_admin.pk
    assert row.workspace_id == workspace.pk
    assert row.view == BillingAccessLog.VIEW_WALLET


def test_reading_the_ledger_as_admin_writes_one_row(client, funded_workspace, instance_admin):
    workspace, _operator = funded_workspace
    client.force_login(instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/ledger/")

    assert response.status_code == 200
    assert BillingAccessLog.objects.get().view == BillingAccessLog.VIEW_LEDGER


def test_every_repeated_read_is_recorded(client, funded_workspace, instance_admin):
    """A log that collapses repeats cannot show a pattern."""
    workspace, _operator = funded_workspace
    client.force_login(instance_admin)

    for _ in range(3):
        client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/ledger/")

    assert BillingAccessLog.objects.filter(view=BillingAccessLog.VIEW_LEDGER).count() == 3


def test_the_row_records_where_the_read_came_from(client, funded_workspace, instance_admin):
    workspace, _operator = funded_workspace
    client.force_login(instance_admin)

    client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/")

    assert BillingAccessLog.objects.get().user_agent != ""


def test_a_workspace_admin_reading_their_own_ledger_writes_no_row(client, workspace_factory):
    """The log is an operator accountability record. A tenant's own read is not an operator event."""
    from plane.db.models import User, WorkspaceMember

    workspace = workspace_factory(name="تیم خودش")
    admin = User.objects.create(username="own-admin", email="own-admin@example.com")
    WorkspaceMember.objects.create(workspace=workspace, member=admin, role=20)
    client.force_login(admin)

    response = client.get(f"/api/billing/workspaces/{workspace.slug}/billing/ledger/")

    assert response.status_code == 200
    assert BillingAccessLog.objects.count() == 0


def test_a_plain_user_is_refused_and_writes_no_row(client, funded_workspace):
    """The canary has to hold on the log too, not only on the response."""
    from plane.db.models import User

    workspace, _operator = funded_workspace
    plain = User.objects.create(username="plain", email="plain@example.com")
    client.force_login(plain)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/")

    assert response.status_code in (401, 403)
    assert BillingAccessLog.objects.count() == 0


def test_an_anonymous_read_writes_no_row(client, funded_workspace):
    workspace, _operator = funded_workspace

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/wallet/")

    assert response.status_code in (401, 403)
    assert BillingAccessLog.objects.count() == 0


def test_the_service_never_raises_when_the_request_has_no_user(db, workspace_factory):
    """An audit failure must not break a read the operator is entitled to."""
    workspace = workspace_factory(name="تیم بی‌درخواست")

    class FakeRequest:
        user = None
        META: dict = {}

    assert ledger.record_admin_read(workspace=workspace, view=BillingAccessLog.VIEW_WALLET, request=FakeRequest()) is None
    assert BillingAccessLog.objects.count() == 0


def test_the_service_survives_a_request_object_with_no_meta(db, workspace_factory, instance_admin):
    """Not every caller is a Django request. A missing META must not be an AttributeError."""
    workspace = workspace_factory(name="تیم حداقلی")

    class MinimalRequest:
        user = instance_admin

    MinimalRequest.user.is_authenticated = True
    ledger.record_admin_read(workspace=workspace, view=BillingAccessLog.VIEW_LEDGER, request=MinimalRequest())

    assert BillingAccessLog.objects.get().viewer_id == instance_admin.pk
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_access_log.py -v
```

Expected: `AttributeError: module 'plane.billing.services.ledger' has no attribute 'record_admin_read'`, and the view tests fail because no rows are written.

- [ ] **Step 3: Write the service**

Append to `apps/api/plane/billing/services/ledger.py`. Import `BillingAccessLog` from `plane.billing.models` alongside the other model imports at the top of the module:

```python
# An instance administrator may read any workspace's money. That is necessary
# -- an operator cannot answer a customer's billing question without seeing the
# numbers -- but it means a customer's financial data is one leaked screenshot
# away from being public. The exposure is managed by traceability: every read
# names who looked, at which workspace and from where.
#
# This lives in a service rather than in the views so that a future report, CSV
# export or new endpoint cannot forget it. A view-level call is a convention
# that erodes; a service-level one is a capability the view has to know exists.
def record_admin_read(*, workspace, view: str, request) -> Optional["BillingAccessLog"]:
    """Write one audit row for an admin read of a tenant's money.

    Returns the row, or ``None`` when there is no authenticated user to name --
    an anonymous request, which the permission has already refused, must not
    leave a row attributing a read to nobody.

    Never raises. A failure to record an audit must not deny the operator a
    read they are authorised for; the alternative is that a broken log becomes
    a way to make billing disappear, which is a worse failure than a missing
    row.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None

    # META is absent on a hand-built request object, so it is read defensively.
    meta = getattr(request, "META", None) or {}
    return BillingAccessLog.objects.create(
        viewer=user,
        workspace=workspace,
        view=view,
        ip_address=(meta.get("REMOTE_ADDR") or "")[:45],
        # Truncated because the column is 512 and an over-long agent would raise
        # DataError, a 500, in the middle of an otherwise successful read.
        user_agent=(meta.get("HTTP_USER_AGENT") or "")[:512],
    )
```

Use `Optional["BillingAccessLog"]` as written only if `BillingAccessLog` is imported at module level. If the import is circular, drop the quotes on the return annotation — it is a return type only, never evaluated at runtime.

- [ ] **Step 4: Call it from the two admin views**

In `apps/api/plane/billing/api/views/wallet_views.py`, in `AdminWorkspaceWalletView.get`, after the `workspace is None` guard and before building the response:

```python
        ledger_service.record_admin_read(
            workspace=workspace, view=BillingAccessLog.VIEW_WALLET, request=request
        )
```

Same in `AdminWorkspaceLedgerView.get`, with `BillingAccessLog.VIEW_LEDGER`. Add `BillingAccessLog` to the `from plane.billing.models import (...)` block in that file.

**Do not add a call to `WorkspaceLedgerView` or `WorkspaceWalletView`.** Those are a workspace admin reading their own money, which is not an operator event — `test_a_workspace_admin_reading_their_own_ledger_writes_no_row` pins this.

**Do not add a call to `AdminWorkspaceGrantView` or `AdminWorkspaceRevokeView`.** Those are writes, not reads, and they are already attributed by `LedgerEntry.created_by`. Logging them as `VIEW_LEDGER` would mislabel them in the trail.

- [ ] **Step 5: Run the tests**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_access_log.py -v
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing -q
```

Expected: all pass, no regression.

- [ ] **Step 6: Prove the tests are not vacuous**

Mutate the view to skip the log call, confirm the failures, then restore:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_access_log.py -q -k "writes_one_row"
```

Expected: FAIL with `BillingAccessLog.DoesNotExist`. Restore the file afterwards and re-run to confirm green.

- [ ] **Step 7: Lint and commit**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff check plane/billing/
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff format --check plane/billing/
git add apps/api/plane/billing/services/ledger.py apps/api/plane/billing/api/views/wallet_views.py apps/api/plane/billing/tests/test_access_log.py
git commit -m "feat(billing): audit every admin read of a tenant ledger"
```

---

## Task 4: `feature_limit()` — the reader the storage was missing

**Files:**

- Modify: `apps/api/plane/billing/services/entitlements.py`
- Modify: `apps/api/plane/billing/tests/test_phase2_limits.py`

**Interfaces:**

- Consumes: `FeatureFlag.limit_type`, `PlanFeatureFlag.limit_value`, and the existing `has_feature(workspace, code)` / `resolve_workspace_plan(workspace)`.
- Produces: `feature_limit(workspace, code: str) -> Optional[int]` — the effective numeric limit, or `None` when the flag is not a `number` flag, is not granted, or the workspace has not switched it on. Never raises.

**Why this is in Phase 2 and not Phase 3.** `PlanFeatureFlag` already stores data that nothing reads: `has_feature()` reads `is_enabled` only and has zero production callers. Storing `limit_value` without a reader would repeat that exactly. Phase 2 writes the reader and tests it, so Phase 3 builds on proven behaviour.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/plane/billing/tests/test_phase2_limits.py`:

```python
# --- feature_limit: the reader that makes limit_value reachable --------------


@pytest.fixture
def limited_workspace(workspace_factory):
    """A workspace on a plan that grants a number flag with a limit of 7."""
    from plane.db.models import WorkspaceFeatureFlag

    workspace = workspace_factory(name="تیم محدود")
    plan = Plan.objects.create(code="limited", name="پلن محدود")
    flag = FeatureFlag.objects.create(code="projects", name="پروژه", limit_type="number", unit_label="پروژه")
    grant = PlanFeatureFlag.objects.create(plan=plan, feature_flag=flag, is_enabled=True, limit_value=7)
    Subscription.objects.create(
        workspace=workspace, plan=plan, status=SubscriptionStatus.ACTIVE, seats=1, cycle=BillingCycle.MONTHLY
    )
    WorkspaceFeatureFlag.objects.create(workspace=workspace, feature_flag=flag, is_enabled=True)
    return workspace, flag, grant


def test_the_effective_limit_is_returned(limited_workspace):
    from plane.billing.services.entitlements import feature_limit

    workspace, _flag, _grant = limited_workspace
    assert feature_limit(workspace, "projects") == 7


def test_a_boolean_flag_has_no_numeric_limit(limited_workspace, workspace_factory):
    from plane.billing.services.entitlements import feature_limit
    from plane.db.models import WorkspaceFeatureFlag

    workspace, _flag, _grant = limited_workspace
    other = workspace_factory(name="تیم دیگر")
    bool_flag = FeatureFlag.objects.create(code="charts", name="نمودار", limit_type="boolean")
    plan = Plan.objects.create(code="boolplan", name="پلن")
    PlanFeatureFlag.objects.create(plan=plan, feature_flag=bool_flag, is_enabled=True)
    Subscription.objects.create(
        workspace=other, plan=plan, status=SubscriptionStatus.ACTIVE, seats=1, cycle=BillingCycle.MONTHLY
    )
    WorkspaceFeatureFlag.objects.create(workspace=other, feature_flag=bool_flag, is_enabled=True)

    assert feature_limit(other, "charts") is None


def test_a_flag_the_workspace_has_not_switched_on_has_no_limit(limited_workspace):
    from plane.billing.services.entitlements import feature_limit
    from plane.db.models import WorkspaceFeatureFlag

    workspace, flag, _grant = limited_workspace
    WorkspaceFeatureFlag.objects.filter(workspace=workspace, feature_flag=flag).update(is_enabled=False)

    assert feature_limit(workspace, "projects") is None


def test_a_flag_the_plan_does_not_grant_has_no_limit(limited_workspace):
    from plane.billing.services.entitlements import feature_limit

    workspace, flag, _grant = limited_workspace
    grant = PlanFeatureFlag.objects.get(feature_flag=flag)
    grant.is_enabled = False
    grant.save()

    assert feature_limit(workspace, "projects") is None


def test_an_unknown_code_has_no_limit(limited_workspace):
    from plane.billing.services.entitlements import feature_limit

    workspace, _flag, _grant = limited_workspace
    assert feature_limit(workspace, "no-such-flag") is None


def test_a_missing_workspace_has_no_limit():
    from plane.billing.services.entitlements import feature_limit

    assert feature_limit(None, "projects") is None


def test_a_granted_number_flag_with_no_stored_limit_reports_none(limited_workspace):
    """The serializer forbids this, but a row can predate the serializer. It must not crash."""
    from plane.billing.services.entitlements import feature_limit

    workspace, flag, _grant = limited_workspace
    PlanFeatureFlag.objects.filter(feature_flag=flag).update(limit_value=None)

    assert feature_limit(workspace, "projects") is None


def test_an_inactive_flag_has_no_limit(limited_workspace):
    from plane.billing.services.entitlements import feature_limit

    workspace, flag, _grant = limited_workspace
    FeatureFlag.objects.filter(code=flag.code).update(is_active=False)

    assert feature_limit(workspace, "projects") is None


def test_feature_limit_agrees_with_has_feature(limited_workspace):
    """Two answers to two questions about the same switch. If they disagree, one is a lie."""
    from plane.billing.services.entitlements import feature_limit, has_feature

    workspace, flag, _grant = limited_workspace
    assert has_feature(workspace, flag.code) is True
    assert feature_limit(workspace, flag.code) == 7

    WorkspaceFeatureFlagFactory = __import__("plane.db.models", fromlist=["WorkspaceFeatureFlag"]).WorkspaceFeatureFlag
    WorkspaceFeatureFlagFactory.objects.filter(workspace=workspace, feature_flag=flag).update(is_enabled=False)

    assert has_feature(workspace, flag.code) is False
    assert feature_limit(workspace, flag.code) is None
```

Add the imports the fixture needs at the top of the test file, alongside the existing `from plane.billing.models import (...)`:

```python
from plane.billing.models import BillingCycle, Subscription, SubscriptionStatus
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_phase2_limits.py -v -k "feature_limit or limit_is"
```

Expected: `ImportError: cannot import name 'feature_limit'`.

- [ ] **Step 3: Write the reader**

Append to `apps/api/plane/billing/services/entitlements.py`, after `has_feature`:

```python
def feature_limit(workspace, code: str) -> Optional[int]:
    """The effective numeric limit of a ``number`` feature flag, or None.

    None means "this question does not apply", and it covers every case that is
    not a countable bound: the flag is not a number flag, the plan does not
    grant it, the workspace has not switched it on, the catalogue row is
    inactive, or there is no such flag at all.

    It deliberately reuses the same three layers ``has_feature`` checks -- the
    same filters in the same order -- because a feature that ``has_feature``
    says is off but that still reports a limit is a feature the caller will
    start trusting. Two functions answering two questions about one switch must
    not disagree; ``test_feature_limit_agrees_with_has_feature`` pins that.

    Phase 2 has no production caller for this yet. It is written and tested now
    so that Phase 3 gates its first real capability on proven behaviour rather
    than on a function nobody has run.
    """
    if workspace is None or not code:
        return None

    feature_flag = FeatureFlag.objects.filter(code=code, is_active=True).first()
    if feature_flag is None or feature_flag.limit_type != "number":
        return None

    plan = resolve_workspace_plan(workspace)
    if plan is None:
        return None

    if not PlanFeatureFlag.objects.filter(plan=plan, feature_flag=feature_flag, is_enabled=True).exists():
        return None

    if not WorkspaceFeatureFlag.objects.filter(
        workspace=workspace, feature_flag=feature_flag, is_enabled=True
    ).exists():
        return None

    limit = PlanFeatureFlag.objects.filter(plan=plan, feature_flag=feature_flag, is_enabled=True).values_list(
        "limit_value", flat=True
    ).first()

    # A granted number flag with no stored limit cannot be gated on, so it grants
    # nothing rather than granting an unbounded amount by accident. The serializer
    # forbids creating that row; this handles one that predates it.
    return limit
```

The `LIMIT_TYPE_NUMBER` constant is defined in `plane.billing.models` as a module-level name. Prefer importing it over the bare string `"number"`:

```python
from plane.billing.models import LIMIT_TYPE_NUMBER
```

and compare `feature_flag.limit_type != LIMIT_TYPE_NUMBER`.

- [ ] **Step 4: Run the tests**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_phase2_limits.py -v --create-db
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing -q
```

Expected: all pass, no regression.

- [ ] **Step 5: Lint and commit**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff check plane/billing/
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff format --check plane/billing/
git add apps/api/plane/billing/services/entitlements.py apps/api/plane/billing/tests/test_phase2_limits.py
git commit -m "feat(billing): read a feature flag's effective limit"
```

---

## Task 5: The three admin endpoints

**Files:**

- Modify: `apps/api/plane/billing/api/views/admin_views.py`
- Modify: `apps/api/plane/billing/api/serializers.py`
- Modify: `apps/api/plane/billing/api/urls.py`
- Modify: `apps/api/plane/billing/tests/test_api_views.py` (`ADMIN_URLS`)
- Modify: `apps/api/plane/billing/tests/test_phase2_limits.py`

**Interfaces:**

- Consumes: everything from Tasks 1–4, plus `WorkspaceContextMixin` (Phase 1), `BillingAdminAPIView.paginated` (`apps/api/plane/billing/api/views/admin_views.py:39`), `money.wallet_balance`, `money.wallet_hold_balance`, `ledger.workspace_entries`, `ledger.record_admin_read`, `entitlements.resolve_workspace_plan`.
- Produces:
  - `GET /api/billing/admin/workspaces/` → paginated list of `TAdminWorkspaceSummary`
  - `GET /api/billing/admin/workspaces/<slug>/billing/` → `AdminWorkspaceBillingSerializer`
  - `GET /api/billing/admin/feature-flags/` → paginated list of `FeatureFlagSerializer`
  - `AdminWorkspaceBillingSerializer` — the detail-page projection

**Note on the wallet-balance cost.** `money.wallet_balance(workspace)` aggregates ledger entries. Calling it per workspace in the list view is N queries. If the list has more than a few pages of workspaces, annotate instead; measure before optimising, and if you annotate, do not reuse `money.wallet_balance` — the balance expression is deliberately in one place for a reason.

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/plane/billing/tests/test_phase2_limits.py`:

```python
# --- wallet_balances: the batch reader behind the list page -----------------
# The dangerous failure is reporting HELD money as spendable, so the held
# account is pinned separately from the spendable one.


def test_the_batch_balance_matches_the_single_read(workspace_factory):
    from plane.billing.services import money, wallet

    first = workspace_factory(name="تیم یک")
    second = workspace_factory(name="تیم دو")
    wallet.grant_from_admin(
        workspace=first, amount_toman=400_000, description="اعتبار اول", created_by=None, idempotency_key="wb-1"
    )
    wallet.grant_from_admin(
        workspace=second, amount_toman=900_000, description="اعتبار دوم", created_by=None, idempotency_key="wb-2"
    )

    totals = money.wallet_balances([first.pk, second.pk])

    assert totals[first.pk] == money.wallet_balance(first) == 400_000
    assert totals[second.pk] == money.wallet_balance(second) == 900_000


def test_held_money_is_not_reported_as_spendable(workspace_factory):
    """A hold moves money to the held account. If both accounts are summed the
    balance looks untouched and every grant appears to have been ignored."""
    from plane.billing.services import money, wallet

    workspace = workspace_factory(name="تیم نگه‌داری")
    wallet.grant_from_admin(
        workspace=workspace, amount_toman=500_000, description="اعتبار اولیه", created_by=None, idempotency_key="wb-hold-grant"
    )
    wallet.hold_funds(
        workspace=workspace,
        amount_toman=300_000,
        description="نگه‌داری بابت فاکتور",
        idempotency_key="wb-hold-1",
    )

    totals = money.wallet_balances([workspace.pk])

    assert totals[workspace.pk] == 200_000
    assert money.wallet_hold_balance(workspace) == 300_000
    # The single read must agree, or the two APIs disagree about the same wallet.
    assert totals[workspace.pk] == money.wallet_balance(workspace)


def test_a_workspace_with_no_wallet_is_absent_rather_than_zero(workspace_factory):
    """The list page reads a missing account as zero. The helper must not CREATE
    a wallet row on a read-only page."""
    from plane.billing.models import Wallet
    from plane.billing.services import money

    workspace = workspace_factory(name="تیم خالی")

    totals = money.wallet_balances([workspace.pk])

    assert workspace.pk not in totals
    assert Wallet.objects.filter(workspace=workspace).count() == 0


def test_the_batch_reader_agrees_with_the_single_read_after_a_refund(workspace_factory):
    from plane.billing.services import money, wallet

    workspace = workspace_factory(name="تیم بازپرداخت")
    wallet.grant_from_admin(
        workspace=workspace, amount_toman=1_000_000, description="اعتبار اولیه", created_by=None, idempotency_key="wb-r-grant"
    )
    wallet.refund_to_spendable(
        workspace=workspace, amount_toman=400_000, reason="انصراف از خرید", reference="pay-7788", idempotency_key="wb-r-1"
    )

    assert money.wallet_balances([workspace.pk])[workspace.pk] == money.wallet_balance(workspace) == 1_000_000


# --- the admin workspace endpoints -----------------------------------------


def test_the_workspace_list_needs_an_instance_admin(client, funded_workspace):
    from plane.db.models import User

    plain = User.objects.create(username="lister", email="lister@example.com")
    client.force_login(plain)

    response = client.get("/api/billing/admin/workspaces/")

    assert response.status_code in (401, 403)


def test_the_workspace_list_returns_each_workspace_with_its_plan_and_balance(client, workspace_factory, instance_admin):
    client.force_login(instance_admin)
    first = workspace_factory(name="تیم الف")
    second = workspace_factory(name="تیم ب")

    response = client.get("/api/billing/admin/workspaces/")

    assert response.status_code == 200, response.content
    slugs = {row["slug"] for row in response.json()["results"]}
    assert {first.slug, second.slug} <= slugs


def test_the_workspace_list_reports_the_plan_code(client, workspace_factory, instance_admin):
    from plane.billing.models import Subscription

    workspace = workspace_factory(name="تیم پلن")
    plan = Plan.objects.create(code="listed", name="پلن فهرست")
    Subscription.objects.create(
        workspace=workspace, plan=plan, status=SubscriptionStatus.ACTIVE, seats=3, cycle=BillingCycle.MONTHLY
    )
    client.force_login(instance_admin)

    rows = {row["slug"]: row for row in client.get("/api/billing/admin/workspaces/").json()["results"]}

    assert rows[workspace.slug]["plan_code"] == "listed"
    assert rows[workspace.slug]["seats"] == 3


def test_the_workspace_list_reports_the_wallet_balance(client, workspace_factory, instance_admin):
    from plane.billing.services import wallet

    workspace = workspace_factory(name="تیم موجودی")
    wallet.grant_from_admin(
        workspace=workspace, amount_toman=250_000, description="اعتبار اولیه برای فهرست", created_by=None, idempotency_key="list-1"
    )
    client.force_login(instance_admin)

    rows = {row["slug"]: row for row in client.get("/api/billing/admin/workspaces/").json()["results"]}

    assert rows[workspace.slug]["balance_toman"] == 250_000


def test_the_detail_page_returns_plan_seats_and_money(client, workspace_factory, instance_admin):
    from plane.billing.models import Subscription
    from plane.billing.services import wallet

    workspace = workspace_factory(name="تیم جزئیات")
    plan = Plan.objects.create(code="detail", name="پلن جزئیات")
    Subscription.objects.create(
        workspace=workspace, plan=plan, status=SubscriptionStatus.ACTIVE, seats=5, cycle=BillingCycle.YEARLY
    )
    wallet.grant_from_admin(
        workspace=workspace, amount_toman=1_000_000, description="اعتبار برای صفحهٔ جزئیات", created_by=None, idempotency_key="det-1"
    )
    client.force_login(instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/")

    assert response.status_code == 200, response.content
    body = response.json()
    assert body["slug"] == workspace.slug
    assert body["name"] == "تیم جزئیات"
    assert body["plan_code"] == "detail"
    assert body["seats"] == 5
    assert body["balance_toman"] == 1_000_000


def test_the_detail_page_of_an_unknown_workspace_is_404(client, instance_admin):
    client.force_login(instance_admin)

    assert client.get("/api/billing/admin/workspaces/no-such-workspace/billing/").status_code == 404


def test_the_detail_page_is_refused_to_a_plain_user(client, funded_workspace):
    from plane.db.models import User

    workspace, _operator = funded_workspace
    plain = User.objects.create(username="detail-plain", email="detail-plain@example.com")
    client.force_login(plain)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/")

    assert response.status_code in (401, 403)


def test_the_detail_page_writes_an_access_log_row(client, funded_workspace, instance_admin):
    """It returns the balance, so it is a money read and must be audited like one."""
    workspace, _operator = funded_workspace
    client.force_login(instance_admin)

    client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/")

    assert BillingAccessLog.objects.filter(view=BillingAccessLog.VIEW_WALLET).count() == 1


def test_the_detail_page_ignores_a_forged_workspace_query_parameter(client, workspace_factory, instance_admin):
    """The URL decides which workspace; ?slug= must not widen it."""
    mine = workspace_factory(name="تیم خودم")
    other = workspace_factory(name="تیم بیگانه")
    client.force_login(instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{mine.slug}/billing/?slug={other.slug}")

    assert response.status_code == 200
    assert response.json()["slug"] == mine.slug


def test_the_feature_flag_catalogue_is_instance_admin_only(client):
    from plane.db.models import User

    plain = User.objects.create(username="flag-plain", email="flag-plain@example.com")
    client.force_login(plain)

    assert client.get("/api/billing/admin/feature-flags/").status_code in (401, 403)


def test_the_feature_flag_catalogue_returns_the_typed_limit(client, instance_admin):
    FeatureFlag.objects.create(code="typed", name="پرچم نوع‌دار", limit_type="number", unit_label="پروژه")
    client.force_login(instance_admin)

    body = client.get("/api/billing/admin/feature-flags/").json()

    assert body["results"][0]["limit_type"] == "number"
    assert body["results"][0]["unit_label"] == "پروژه"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_phase2_limits.py -v -k "workspace_list or detail_page or catalogue"
```

Expected: 404s — none of the three routes exist.

- [ ] **Step 3: Add the serializers**

Add to `apps/api/plane/billing/api/serializers.py`:

```python
class AdminWorkspaceSummarySerializer(serializers.Serializer):
    """One row of the admin workspace list: enough to spot a problem, nothing more.

    Read-only by construction -- a ``Serializer`` with no writable field rejects
    a POST body -- because this projection is a listing, not a write surface.
    """

    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.SlugField()
    plan_code = serializers.CharField(allow_null=True)
    seats = serializers.IntegerField()
    balance_toman = serializers.IntegerField()


class AdminWorkspaceBillingSerializer(serializers.Serializer):
    """The whole billing picture of one workspace for the admin detail page.

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
```

`id`, `name` and `slug` are `SerializerMethodField`-free so the view builds the dict and passes it through; construct the payload with plain keys.

- [ ] **Step 4: Add the views**

Add to `apps/api/plane/billing/api/views/admin_views.py`. Imports to add: `BillingAccessLog`, `Subscription`, `SubscriptionStatus`, `WalletMember`-free seat counting via `WorkspaceMember`, `AdminWorkspaceBillingSerializer`, `AdminWorkspaceSummarySerializer`, `ledger as ledger_service`, `money as money_service`, `entitlements`, and `WorkspaceContextMixin` from `plane.billing.api.views.wallet_views`.

```python
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
    """

    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        queryset = Workspace.objects.order_by("name")

        def build(page):
            workspaces = list(page)
            ids = [workspace.pk for workspace in workspaces]
            if not ids:
                return []

            plan_by_workspace = {
                row["workspace_id"]: row
                for row in Subscription.objects.filter(workspace_id__in=ids, status=SubscriptionStatus.ACTIVE)
                .values("workspace_id", "plan__code", "seats")
            }
            balances = money_service.wallet_balances(ids)

            return [
                {
                    "id": workspace.pk,
                    "name": workspace.name,
                    "slug": workspace.slug,
                    "plan_code": (plan_by_workspace.get(workspace.pk) or {}).get("plan__code"),
                    "seats": (plan_by_workspace.get(workspace.pk) or {}).get("seats", 0),
                    "balance_toman": balances.get(workspace.pk, 0),
                }
                for workspace in workspaces
            ]

        return self.paginate(request, queryset=queryset, on_results=build)
```

This needs one new helper in `services/money.py`. Append it after `wallet_hold_balance` (line 358):

```python
def wallet_balances(workspace_ids: Iterable[UUID]) -> Dict[UUID, int]:
    """Spendable balance for many workspaces in two queries.

    The admin workspace list needs a balance per row. Calling
    ``wallet_balance`` per workspace is two aggregate queries each, which turns
    a 50-row page into 100 round trips.

    A workspace whose wallet has no ledger account yet is simply absent from the
    result, and the caller reads that as zero. It is NOT created here:
    ``get_or_create_wallet_accounts`` would write a row per workspace on a
    read-only list page, so a GET would create hundreds of rows. The detail page
    already creates them on demand.

    The two aggregates are over one account set, never one pass over a kind. A
    single ``Case``/``When`` over ``debit_account__kind`` is first-match-wins, so
    it silently drops the credit leg of an entry whose debit side is
    debit-normal -- the exact defect ``_signed_total``'s docstring warns about.
    """
    account_ids = list(
        LedgerAccount.objects.filter(
            workspace_id__in=list(workspace_ids),
            # NOT a kind filter. BOTH wallet legs are ASSET -- see the note in
            # get_or_create_wallet_accounts (money.py:100) -- so filtering on
            # kind=ASSET would return the HELD account as well and a page row
            # would report a wallet as fully funded when its money is in hold.
            # The spendable leg is identified by its account code, which is the
            # only thing that distinguishes the two accounts.
            code__in=[WalletAccountCode.wallet_default(workspace_id) for workspace_id in workspace_ids],
        ).values_list("id", "workspace_id")
    )
    if not account_ids:
        return {}

    ids = [account_id for account_id, _workspace_id in account_ids]
    workspace_by_account = dict(account_ids)

    debits: Dict[UUID, int] = {}
    for row in (
        LedgerEntry.objects.filter(debit_account_id__in=ids)
        .values("debit_account_id")
        .annotate(total=Sum("amount_toman"))
    ):
        debits[row["debit_account_id"]] = row["total"] or 0

    credits: Dict[UUID, int] = {}
    for row in (
        LedgerEntry.objects.filter(credit_account_id__in=ids)
        .values("credit_account_id")
        .annotate(total=Sum("amount_toman"))
    ):
        credits[row["credit_account_id"]] = row["total"] or 0

    # Every wallet account is ASSET (debit-normal), so the sign is fixed here.
    # Read ``is_debit_normal`` from the account instead if a wallet account ever
    # stops being debit-normal; the assumption is local to this return.
    return {
        workspace_by_account[account_id]: debits.get(account_id, 0) - credits.get(account_id, 0)
        for account_id in ids
    }
```

Two constraints this helper must honour, both inherited from `_signed_total` (`money.py:290`):

- **Filter by the spendable account CODE, never by `kind`.** Both wallet legs are `ASSET` — `get_or_create_wallet_accounts` (line 100) makes spendable and held both `LedgerAccountKind.ASSET`, deliberately, because a hold restricts money the workspace still owns. A `kind=ASSET` filter therefore matches both and a page row would report a held wallet as fully funded. `test_held_money_is_not_reported_as_spendable` is the test that catches this.
- **No `LedgerEntry.workspace` filter.** A workspace-owned account is filtered by account alone, because `post_entry` accepts `workspace=None` and an entry posted against the account without a workspace would otherwise be invisible, under-counting the balance.

Import `WalletAccountCode` — read its real location and member names first; `get_or_create_wallet_accounts` calls `WalletAccountCode.wallet_default(workspace.pk)` and `WalletAccountCode.wallet_hold(workspace.pk)`. Add `Iterable` and `UUID` to the typing import at the top of `money.py` if they are not already there.

Next, the detail endpoint:

```python
class AdminWorkspaceBillingEndpoint(WorkspaceContextMixin, BillingAdminAPIView):
    """The billing picture of one workspace: plan, subscription, seats and money.

    Returns the wallet balance, so it writes an access-log row exactly as the
    wallet endpoint does. The audit trail has to follow the money, not a
    particular URL.
    """

    permission_classes = [InstanceAdminPermission]

    def get(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        ledger_service.record_admin_read(
            workspace=workspace, view=BillingAccessLog.VIEW_WALLET, request=request
        )

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
```

And the flag catalogue:

```python
class AdminFeatureFlagListEndpoint(BillingAdminAPIView):
    """The flag catalogue, grouped by category in the UI.

    Ordered by ``(category, code)`` which is already ``FeatureFlag.Meta.ordering``,
    so the UI can group without sorting client-side.
    """

    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        return self.paginated(request, FeatureFlag.objects.all(), FeatureFlagSerializer)
```

- [ ] **Step 5: Register the routes**

In `apps/api/plane/billing/api/urls.py`, inside the admin block:

```python
    path("admin/workspaces/", AdminWorkspaceListEndpoint.as_view(), name="billing-admin-workspaces"),
    path(
        "admin/workspaces/<slug>/billing/",
        AdminWorkspaceBillingEndpoint.as_view(),
        name="billing-admin-workspace-billing",
    ),
    path("admin/feature-flags/", AdminFeatureFlagListEndpoint.as_view(), name="billing-admin-feature-flags"),
```

Add the three view classes to the imports from `admin_views`.

**Route-order warning.** `admin/workspaces/` must not be shadowed by any `admin/plans/<…>` style route, and it must be registered **before** any future `admin/workspaces/<slug>/…` catch-all. `path()` matches in order, so a later exact path can be shadowed by an earlier greedy converter. Register the collection path first.

- [ ] **Step 6: Extend the `ADMIN_URLS` canary**

In `apps/api/plane/billing/tests/test_api_views.py`, add the new routes to the `ADMIN_URLS` list, including a real slug. Since the canary walks the list and asserts a non-admin is refused, use a workspace fixture slug:

```python
ADMIN_URLS = [
    # ... existing entries ...
    "/api/billing/admin/workspaces/",
    "/api/billing/admin/feature-flags/",
]
```

And add a dedicated test for the slug-parameterised one:

```python
def test_the_workspace_detail_route_rejects_a_plain_user(client, funded_workspace):
    workspace, _operator = funded_workspace
    plain = User.objects.create(username="canary", email="canary@example.com")
    client.force_login(plain)

    response = client.get(f"/api/billing/admin/workspaces/{workspace.slug}/billing/")

    assert response.status_code in (401, 403)
```

- [ ] **Step 7: Run the tests**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing -q --create-db
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest -m unit -q --create-db
```

Expected: the billing suite passes and the full unit suite is `432 passed` (or higher — Phase 2 only adds tests).

- [ ] **Step 8: Lint and commit**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff check plane/billing/
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff format --check plane/billing/
git add apps/api/plane/billing/
git commit -m "feat(billing): admin workspace list, detail and flag catalogue"
```

---

## Task 6: The types and the service client

**Files:**

- Modify: `packages/types/src/billing/index.ts`
- Modify: `packages/services/src/billing/billing.service.ts`
- Modify: `packages/services/src/billing/index.ts`

**Interfaces:**

- Consumes: the three endpoints from Task 5.
- Produces: `TFeatureFlag`, `TPlanFeatureFlag`, `TAdminWorkspaceSummary`, `TAdminWorkspaceBilling`, the three new `TBillingPlan` fields; `BillingService.adminWorkspaces`, `.adminWorkspaceBilling`, `.featureFlags`; cache keys `BILLING_ADMIN_WORKSPACES`, `BILLING_ADMIN_WORKSPACE_BILLING`, `BILLING_FEATURE_FLAGS`.

- [ ] **Step 1: Add the types**

In `packages/types/src/billing/index.ts`, add the three new fields to `TBillingPlan` (line ~104), keeping the existing alphabetical-ish ordering of the type literal:

```typescript
proration_mode: TBillingProrationMode;
renew_lock_days: number;
sms_prices: Record<string, number>;
```

and add above it:

```typescript
/** How an upgrade in the middle of a paid cycle treats the unused remainder. */
export type TBillingProrationMode = "credit_remaining" | "no_extension";
```

Then append:

```typescript
/* feature flag catalogue */

/**
 * A flag's shape decides what the plan form renders for it: a switch, a number
 * with a unit, or "unlimited" with no control at all. One global limit number
 * across all flags does not work, because "5 charts" and "10 projects" are not
 * the same constraint.
 */
export type TBillingLimitType = "boolean" | "number" | "unlimited";

export type TFeatureFlag = {
  category: string;
  code: string;
  created_at: string;
  description: string;
  id: string;
  is_active: boolean;
  is_public: boolean;
  limit_type: TBillingLimitType;
  name: string;
  unit_label: string;
  updated_at: string;
};

export type TPlanFeatureFlag = {
  config: Record<string, unknown>;
  created_at: string;
  feature_flag: string;
  feature_flag_code: string;
  feature_flag_name: string;
  id: string;
  is_enabled: boolean;
  /** Present only for a flag whose limit_type is "number". */
  limit_value: number | null;
  limit_type: TBillingLimitType;
  unit_label: string;
  updated_at: string;
};

/* admin workspace billing */

/**
 * One row of the admin workspace list. Read-only: the list is a triage view,
 * not a write surface.
 */
export type TAdminWorkspaceSummary = {
  balance_toman: number;
  id: string;
  name: string;
  plan_code: string | null;
  seats: number;
  slug: string;
};

/**
 * The admin detail page. Carries the wallet balance, so the backend writes an
 * access-log row for every read of this payload.
 */
export type TAdminWorkspaceBilling = {
  active_members: number;
  balance_toman: number;
  ends_at: string | null;
  hold_balance_toman: number;
  id: string;
  name: string;
  plan_code: string | null;
  plan_name: string | null;
  proration_mode: TBillingProrationMode | null;
  renew_lock_days: number | null;
  seats: number;
  slug: string;
  starts_at: string | null;
  subscription_status: string | null;
};

/** The paginated envelope the admin list endpoints return. */
export type TAdminWorkspaceListResponse = {
  group_by?: string;
  next_page_results: string | null;
  prev_page_results: string | null;
  total_pages: number;
  total_records: number;
  results: TAdminWorkspaceSummary[];
};
```

Check the existing paginated response shape (e.g. `TBillingPlanListResponse`) and match its real field names rather than the ones guessed above.

- [ ] **Step 2: Add the service methods**

In `packages/services/src/billing/billing.service.ts`, follow the existing method style (`APIService`, `this.get`/`this.post`, a `Promise<T>` return). Add:

```typescript
  /**
   * Every workspace with the plan, seat count and wallet balance an operator
   * triages by. Not audited row by row on the backend -- the detail read is.
   */
  async adminWorkspaces(params: TBillingListParams): Promise<TAdminWorkspaceListResponse> {
    return this.get("/billing/admin/workspaces/", { params });
  }

  /**
   * The billing picture of one workspace. The backend writes an access-log row
   * on every call, so this is the audited read.
   */
  async adminWorkspaceBilling(workspaceSlug: string): Promise<TAdminWorkspaceBilling> {
    return this.get(`/billing/admin/workspaces/${workspaceSlug}/billing/`);
  }

  /** The flag catalogue, already ordered by (category, code) so the UI can group directly. */
  async featureFlags(params: TBillingListParams): Promise<{ results: TFeatureFlag[] }> {
    return this.get("/billing/admin/feature-flags/", { params });
  }
```

Verify the base URL prefix against an existing method (`async plans` at line ~139) — if that one posts to `/billing/plans/`, these are right; if it includes an extra segment, match it exactly.

- [ ] **Step 3: Add the cache keys**

In `packages/services/src/billing/index.ts`:

```typescript
/* admin workspace billing */

/**
 * One key per workspace, because two tenants must never share a cache entry
 * for their money. The slug is the whole key: a detail page is read for one
 * workspace at a time.
 */
export const BILLING_ADMIN_WORKSPACE_BILLING = (workspaceSlug: string) =>
  buildBillingListKey("billing-admin-workspace-billing", { workspaceSlug });

/** The workspace list and the flag catalogue are unfiltered reads of the whole instance. */
export const BILLING_ADMIN_WORKSPACES = "billing-admin-workspaces";
export const BILLING_FEATURE_FLAGS = "billing-feature-flags";
```

- [ ] **Step 4: Verify the types compile**

```bash
pnpm turbo run check:types --filter=@plane/types --filter=@plane/services
```

Expected: both pass with no errors.

- [ ] **Step 5: Commit**

```bash
git add packages/types/src/billing/index.ts packages/services/src/billing/
git commit -m "feat(billing): types and service client for the admin workspace views"
```

---

## Task 7: The three admin pages and the typed plan form

**Files:**

- Create: `apps/admin/app/(all)/(dashboard)/billing/workspaces/page.tsx`
- Create: `apps/admin/app/(all)/(dashboard)/billing/workspaces/[slug]/page.tsx`
- Create: `apps/admin/app/(all)/(dashboard)/billing/feature-flags/page.tsx`
- Create: `apps/admin/app/(all)/(dashboard)/billing/components/workspace-billing-tabs.tsx`
- Modify: `apps/admin/app/(all)/(dashboard)/billing/components/billing-layout.tsx` (`BILLING_TABS`, line 13)
- Modify: `apps/admin/app/(all)/(dashboard)/billing/plans/page.tsx`

**Interfaces:**

- Consumes: everything from Task 6.
- Produces: three routes under `/billing/`.

- [ ] **Step 1: Extend `BILLING_TABS`**

In `apps/admin/app/(all)/(dashboard)/billing/components/billing-layout.tsx`, add three entries to the `BILLING_TABS` array, keeping the existing Persian labels and placing them before the records tab:

```typescript
  { href: "/billing/workspaces/", label: "ورک‌اسپیس‌ها" },
  { href: "/billing/feature-flags/", label: "پرچم‌های قابلیت" },
```

`normalizePath` already strips the trailing slash, and the detail page at `/billing/workspaces/<slug>/` will not match either tab exactly — so the list tab should also highlight when a detail page is open. Change the comparison to:

```typescript
const isActive =
  currentPath === normalizePath(tab.href) ||
  (tab.href === "/billing/workspaces/" && currentPath.startsWith("/billing/workspaces/"));
```

- [ ] **Step 2: Build the workspace list page**

Create `apps/admin/app/(all)/(dashboard)/billing/workspaces/page.tsx`. Follow the existing page structure in `billing/transactions/page.tsx` — `BillingRTLFrame`, `useSWR` against `BILLING_ADMIN_WORKSPACES`, `BillingSection` for grouping. Columns, in this order:

| ستون           | منبع                                                                    |
| -------------- | ----------------------------------------------------------------------- |
| نام            | `name`                                                                  |
| شناسه          | `slug`                                                                  |
| پلن            | `plan_code`, or «—» when null                                           |
| صندلی          | `seats`                                                                 |
| موجودی کیف پول | `balance_toman` formatted with the shared `formatNumber` from `./utils` |

Each row links to `/billing/workspaces/<slug>/`. Use `Link` from `react-router`, as `billing-layout.tsx` does.

Handle `plan_code === null` explicitly with a Persian placeholder — a null plan means "this workspace is on no plan", which is exactly the thing an operator is scanning for, so it must be visible rather than rendered as an empty cell.

- [ ] **Step 3: Build the detail page and its tabs**

Create `apps/admin/app/(all)/(dashboard)/billing/components/workspace-billing-tabs.tsx`. Render four tabs: **پلن فعال**, **اشتراک و انقضا**, **صندلی و اعضا**, **کیف پول و دفتر کل**. Take `activeTab` and `onChange` as props; keep the tab state in the page component, not in the component, so a route change can reset it.

Create `apps/admin/app/(all)/(dashboard)/billing/workspaces/[slug]/page.tsx`. Read `slug` with `useParams()`. `useSWR` against `BILLING_ADMIN_WORKSPACE_BILLING(slug)` for the plan, subscription and money tabs. For the ledger tab, `useSWR` against `BillingService`'s existing admin ledger path `/billing/admin/workspaces/<slug>/wallet/ledger/` — this endpoint already exists from Phase 1; do not add a new one.

The wallet tab must render, above everything and always visible:

```tsx
<div className="rounded-custom border border-warning-subtle bg-warning-subtle px-4 py-3 text-13 text-warning">
  این اطلاعات قابلیت مشاهدهٔ مشتری دارد و هر بار مشاهدهٔ آن ثبت می‌شود.
</div>
```

Confirm the exact `text-warning` / `bg-warning-subtle` token names against the existing Tailwind config before using them; if they do not exist, use the token names that do. The message is required by M13 — an operator who does not know they are being recorded cannot be held to the trail.

Use `BillingRTLFrame` with `title={workspace.name}` and a `description` of the slug.

- [ ] **Step 4: Build the flag catalogue page**

Create `apps/admin/app/(all)/(dashboard)/billing/feature-flags/page.tsx`. `useSWR` against `BILLING_FEATURE_FLAGS`, then group `results` by `category` — the backend order is already `(category, code)`, so a `Map` built by iterating preserves it without a sort.

Render one `BillingSection` per category. Each row shows the flag's Persian `name`, its `code`, and a badge naming its shape: «روشن یا خاموش» / «محدودیت عددی» / «نامحدود». A flag with `is_active === false` renders greyed and without controls. `unit_label` is shown next to a number flag.

- [ ] **Step 5: Add the typed controls to the plan form**

In `apps/admin/app/(all)/(dashboard)/billing/plans/page.tsx`, add a section **after the price fields**. Fetch the catalogue with `useSWR(BILLING_FEATURE_FLAGS)` and the current plan's grants with `useSWR` against `/billing/admin/plans/<planId>/feature-flags/`.

Group the catalogue by `category` and render per flag, driven by `limit_type` — never by a hardcoded list of codes:

```tsx
{
  flag.limit_type === "boolean" && (
    <Switch checked={Boolean(grant?.is_enabled)} onChange={(checked) => updateGrant(flag, { is_enabled: checked })} />
  );
}

{
  flag.limit_type === "number" && (
    <div className="flex items-center gap-2">
      <Input
        type="number"
        min={0}
        value={grant?.limit_value ?? ""}
        onChange={(event) => updateGrant(flag, { limit_value: Number(event.target.value) })}
      />
      {flag.unit_label && <span className="text-13 text-tertiary">{flag.unit_label}</span>}
    </div>
  );
}

{
  flag.limit_type === "unlimited" && <span className="text-13 text-tertiary">نامحدود</span>;
}
```

Above the section, the permanent warning:

```tsx
<div className="rounded-custom border border-warning-subtle bg-warning-subtle px-4 py-3 text-13 text-warning">
  تغییر پرچم‌ها روی اشتراک‌های فعال بلافاصله اعمال می‌شود.
</div>
```

Two rules the implementation must respect:

- **A `number` flag with an empty input must not be submitted as `null`.** The backend refuses an explicit `null` on a number flag, which would surface as an opaque 400. Validate in the form and show the Persian message «برای پرچم عددی، مقدار محدودیت الزامی است.» on the field.
- **Never send `limit_value` for a boolean or unlimited flag.** The backend refuses it by design, and sending it would turn every toggle into a 400.

- [ ] **Step 6: Verify the frontend builds**

```bash
pnpm turbo run check:types --filter=admin
pnpm turbo run check:lint --filter=admin
```

Expected: both pass. If `oxfmt` reformats anything, run `pnpm fix:format` and re-verify.

- [ ] **Step 7: Look at the pages**

Run `pnpm dev` and open `/billing/workspaces/`, then one workspace's detail page, then `/billing/feature-flags/` and the plan form. Check the pages render in RTL, the Persian strings read correctly, the warning on the wallet tab is visible, and a `number` flag renders a number input with its unit suffix. If the dev server cannot run in this environment, say so plainly in the report rather than claiming the pages were verified.

- [ ] **Step 8: Commit**

```bash
git add apps/admin/app
git commit -m "feat(admin): workspace billing pages and the typed plan form"
```

---

## Task 8: The AGENTS.md feature flag rule

**Files:**

- Modify: `AGENTS.md`

**Interfaces:**

- Consumes: nothing.
- Produces: the mandatory registration rule, so every future capability joins the flag catalogue automatically.

- [ ] **Step 1: Add the section**

In `AGENTS.md`, add a new `## Feature flags` section directly after `## Code Style`. The `### Components` bullet already restricts primitives to `@makeplane/propel` and composite components to `@plane/blocks`; this section belongs beside it.

The section must state all four rules, because each exists because its absence caused a specific failure:

```markdown
## Feature flags

- **Registration**: Every new user-facing capability MUST have a `FeatureFlag` row in
  `apps/api/plane/billing` before or in the same change that introduces it. A capability with no
  flag cannot be gated per plan and cannot be priced per seat later. `has_feature()` had zero
  production callers until Phase 3 of the billing work — that is what "registered but unread"
  looks like.
- **limit_type**: Each flag declares `boolean`, `number` or `unlimited`. Choose `number` with a
  `unit_label` whenever the capability has a countable limit — a single global limit across flags
  does not work, because "5 charts" and "10 projects" are not the same constraint. A
  `limit_value` on a non-number flag is rejected by the serializer rather than silently dropped.
- **Gating**: Gate the capability with `has_feature(workspace, code)` from
  `plane.billing.services.entitlements`, and read a countable limit with
  `feature_limit(workspace, code)`. Do not read `PlanFeatureFlag` directly, and do not branch on
  `plan.code` — that couples the code to the plan catalogue.
- **Testing**: Gating needs a test that covers the off case, otherwise the flag silently does
  nothing. A flag whose limit is stored but never read is the same failure with a smaller blast
  radius.

See `docs/superpowers/specs/2026-10-07-billing-wallet-upgrade-design.md` for the design.
```

- [ ] **Step 2: Verify it did not break existing docs**

```bash
pnpm exec oxfmt --check AGENTS.md
```

Expected: formatted, no change.

- [ ] **Step 3: Commit**

```bash
git add AGENTS.md
git commit -m "docs: require every new capability to register a feature flag"
```

---

## Task 9: Whole-feature verification

**Files:** none. This task reads and reports; it commits only if it makes a small fix.

**Interfaces:**

- Consumes: the whole feature.
- Produces: an honest report.

- [ ] **Step 1: Run the full backend suite from a rebuilt schema**

```bash
docker compose -f docker-compose-test.yml up -d test-db test-redis
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest -m unit -q --create-db
```

Expected: `432 passed` or higher, zero failures. Phase 2 only adds tests, so a **failure anywhere is a regression** — most likely in the 312 billing tests. Report any failure before fixing it.

- [ ] **Step 2: Verify the migrations**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests python manage.py makemigrations --check --dry-run
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff check plane/billing/
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests ruff format --check plane/billing/
```

Expected: `No changes detected`, `All checks passed!`, all files formatted.

**Then state the unverified thing plainly in the report:** `pytest.ini` sets `--nomigrations`, so the migrations have still never been applied by a real `migrate`. Read `0006_feature_flag_limits.py` line by line and confirm it contains only `AddField` and `CreateModel` operations — no `RemoveField`, and no `AlterField` that rewrites `PlanFeatureFlag.config`.

- [ ] **Step 3: Verify the frontend**

```bash
pnpm turbo run check:types --filter=admin --filter=@plane/types --filter=@plane/services
pnpm turbo run check:lint --filter=admin
```

- [ ] **Step 4: Mutation-test four of the new guarantees**

Apply each mutation, run the named tests, confirm they fail, then restore. A mutation that leaves the suite green is a vacuous test and is the single most valuable finding this task can produce.

| #   | Mutation                                                                                                 | Test that must fail                                                                           |
| --- | -------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| 1   | Remove `BillingAccessLog.VIEW_LEDGER` from the call in `AdminWorkspaceLedgerView.get`                    | `pytest plane/billing/tests/test_access_log.py -k "writes_one_row"`                           |
| 2   | Make `AdminWorkspaceBillingEndpoint` read `request.query_params.get("slug")` instead of `self.workspace` | `pytest plane/billing/tests/test_phase2_limits.py -k "forged_workspace"`                      |
| 3   | Delete the `limit_value` check from `PlanFeatureFlagSerializer.validate`                                 | `pytest plane/billing/tests/test_phase2_limits.py -k "limit_on_a_boolean or without_a_limit"` |
| 4   | Make `feature_limit` skip the `WorkspaceFeatureFlag` check                                               | `pytest plane/billing/tests/test_phase2_limits.py -k "has_not_switched_on or agrees_with"`    |

```bash
# per mutation, then:
cp apps/api/plane/billing/<file> /tmp/opencode-<name>.bak   # back up first
# apply the change, run the test, expect FAIL
cp /tmp/opencode-<name>.bak apps/api/plane/billing/<file>    # restore
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing -q
```

Report each mutation's outcome. If any leaves the suite green, say so and treat it as a Critical finding.

- [ ] **Step 5: Verify the invariants**

State each with the evidence that proves it:

- `PlanFeatureFlag.config` is still a free `JSONField`, and no migration operation rewrote it.
- `limit_type`, `unit_label` and `limit_value` are all present in the `FeatureFlagSerializer` and `PlanFeatureFlagSerializer` field lists.
- `BillingAccessLog` has a row written by each of the three money-returning admin endpoints (`/wallet/`, `/wallet/ledger/`, `/billing/`).
- No endpoint under `/admin/` accepts a workspace or slug from the query string.
- `feature_limit` and `has_feature` never disagree — the test that pins this passed.
- Every new Persian string is Persian; grep the diff for any English user-facing string.
- `grep -rn 'TODO\|FIXME\|print(' apps/api/plane/billing/ apps/admin/app/\(all\)/\(dashboard\)/billing/` returns nothing.

- [ ] **Step 6: Write the report**

Report: the exact test counts; each invariant with its evidence; the four mutation outcomes; anything unverified; and the endpoint map the frontend depends on.

**Do not claim anything you did not observe.** If the dev server could not run, say the pages were not visually verified. If a real `migrate` was not run, say the migrations are unproven against a live database. The honest gaps are the value of this task.

---

## What Phase 2 deliberately does not build

Stated so a later reader does not mistake absence for oversight:

- **No production caller for `feature_limit()`.** It is written and tested so Phase 3 builds on proven behaviour. Phase 3 adds the first gated capability.
- **No proration, no renew-lock enforcement, no SMS pricing behaviour.** The three `Plan` fields exist and are editable; the code that reads them is Phase 3 and Phase 4.
- **No workspace-level feature-flag toggle page in the admin.** `WorkspaceFeatureFlag` is only reachable through the web app today.
- **No access-log viewer page.** `BillingAccessLog` is written but not yet surfaced; a `/billing/access-log/` page is the natural next task.
- **No CSV export** of any of the three new views.
