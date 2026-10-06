# Money Ledger and Wallet — Implementation Plan (Phases 0 and 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a double-entry ledger that is the only path money can move through, then a per-workspace wallet that can only be funded by a verified gateway payment or an audited instance-admin grant.

**Architecture:** No model stores a hand-editable balance. Every money movement writes one `LedgerEntry` with a debit and a credit account; a wallet's balance is the aggregate of its entries. A shared service module owns all balance math and serialisation; the API exposes two separate views with two separate permissions so the workspace-scoped view can never be widened into the instance-scoped one.

**Tech Stack:** Django 5.x, Django REST Framework, PostgreSQL, pytest-django, Celery (beat schedule).

**Spec:** `docs/superpowers/specs/2026-10-07-billing-wallet-upgrade-design.md`

---

## Global Constraints

- Currency is always Toman, stored as `PositiveBigIntegerField` on `amount_toman`. Never store Rial — the Rial/Toman conversion happens only inside the gateway adapters (`apps/api/plane/billing/gateways/base.py:21`).
- `LedgerEntry.amount_toman` is **always positive**. Direction comes from the account kinds, never from the sign of the amount.
- `LedgerEntry.debit_account` and `credit_account` must differ. Enforced by a `CheckConstraint`, not only by service code.
- Every `LedgerEntry` requires a non-empty `idempotency_key` that is unique. Retrying any operation must never create a second row.
- No model may hold a writable balance column. If you find yourself adding one, stop — compute it instead.
- Copy is Persian. Every user-facing string and every admin-facing `LedgerAccount.title` is Persian, matching the existing billing app.
- Money arithmetic uses `Decimal`; conversion to `int` happens once, at the end, rounding to the nearest 1,000 Toman.
- Python files start with the existing copyright header, then a section-comment header (`# Python imports`, `# Django imports`, `# Module imports`) as in `apps/api/plane/billing/models.py:1-13`.
- Backend tests run in Docker. **`minio` cannot be pulled in this environment, so always start the DB and redis yourself and skip the rest of the stack.** The working invocation is:
  ```bash
  docker compose -f docker-compose-test.yml up -d test-db test-redis
  docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest <path> -v
  ```
  Never drop `--no-deps --pull never`: without them the run tries to pull `pgsty/minio` and fails, and `--no-deps` alone leaves the DB hostname unresolvable. Never run pytest against a local environment.
- Every new endpoint gets a test that a **role 15 workspace member** is rejected. `WorkSpaceAdminPermission` accepts role 15 and must never guard financial data.

---

## File Structure

| File                                                               | Responsibility                                                                                                                                                |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `apps/api/plane/billing/models.py` (modify)                        | Add `LedgerAccountKind`, `LedgerSource`, `LedgerAccount`, `LedgerEntry`, `Wallet`. Enums live here beside the existing `GatewayCode`/`InvoiceStatus` choices. |
| `apps/api/plane/billing/migrations/0003_wallet_ledger.py` (create) | Schema for the five new models.                                                                                                                               |
| `apps/api/plane/billing/services/money.py` (create)                | Pure balance math. No request handling, no user input. Owns account-code construction, posting, and balance computation.                                      |
| `apps/api/plane/billing/services/wallet.py` (create)               | Wallet-specific operations that call into `money`: grant, revoke, charge, hold.                                                                               |
| `apps/api/plane/billing/services/ledger.py` (create)               | Query building and public projections for reading the ledger. **Takes a resolved queryset, never a scope string.**                                            |
| `apps/api/plane/billing/api/permissions.py` (create)               | `WorkspaceBillingLedgerPermission` — role 20 only.                                                                                                            |
| `apps/api/plane/billing/api/serializers.py` (modify)               | Add `LedgerAccountSerializer`, `AdminLedgerEntrySerializer`, `WorkspaceLedgerEntrySerializer`, `WalletSerializer`, `WalletGrantSerializer`.                   |
| `apps/api/plane/billing/api/views/wallet_views.py` (create)        | The two admin wallet endpoints and the two workspace endpoints.                                                                                               |
| `apps/api/plane/billing/api/views/__init__.py` (modify)            | Export the new views.                                                                                                                                         |
| `apps/api/plane/billing/api/urls.py` (modify)                      | Route the new endpoints.                                                                                                                                      |
| `apps/api/plane/billing/tests/conftest.py` (modify)                | Add `workspace`, `workspace_admin`, `workspace_member`, `other_workspace` fixtures.                                                                           |
| `apps/api/plane/billing/tests/test_money.py` (create)              | Double-entry invariants.                                                                                                                                      |
| `apps/api/plane/billing/tests/test_wallet.py` (create)             | Grant, revoke, charge, hold, concurrency.                                                                                                                     |
| `apps/api/plane/billing/tests/test_ledger_security.py` (create)    | The seven leak tests from spec section 8.1.                                                                                                                   |

---

## File Structure Notes

`services/money.py` and `services/wallet.py` are separate because they have different jobs: `money` is arithmetic that knows nothing about workspaces, `wallet` is the policy layer that knows a wallet exists. `services/ledger.py` is separate from both because reading is where the scope-juggling bugs live, and it is the only place allowed to build a `LedgerEntry` queryset.

Note the naming collision risk: there is already `apps/api/plane/billing/api/urls.py`, which is the URL conf for the whole billing app, while `apps/api/plane/billing/urls.py` is what includes it. Both must be edited in Task 6.

---

## Task 1: Ledger models and migration

**Files:**

- Modify: `apps/api/plane/billing/models.py:16-56` (add enums), append after `WorkspaceFeatureFlag` (line 434)
- Create: `apps/api/plane/billing/migrations/0003_wallet_ledger.py`
- Test: `apps/api/plane/billing/tests/test_money.py`

**Interfaces:**

- Consumes: `plane.db.models.base.BaseModel` (existing, provides `id` UUID pk, `created_at`, `updated_at`)
- Produces:
  - `LedgerAccountKind` TextChoices: `ASSET`, `LIABILITY`, `REVENUE`, `GATEWAY_SETTLEMENT`, `ADMIN_POOL`
  - `LedgerSource` TextChoices: `GATEWAY`, `ADMIN_GRANT`, `SMS_CHARGE`, `PLAN_PURCHASE`, `UPGRADE`, `REFUND`, `RELEASE_HOLD`
  - `LedgerAccount(code, kind, title, workspace)`
  - `LedgerEntry(debit_account, credit_account, amount_toman, source, workspace, description, created_by, invoice, transaction, idempotency_key)`
  - `Wallet(workspace, admin_grant_cap_toman)`
  - `money.WalletAccountCode.wallet_default(workspace_pk) -> str` and `money.WalletAccountCode.wallet_hold(workspace_pk) -> str` (Task 2)

- [ ] **Step 1: Write the failing test**

Create `apps/api/plane/billing/tests/test_money.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Schema level invariants for the double entry ledger."""

# Third party imports
import pytest

# Django imports
from django.db import IntegrityError, transaction
from django.db.models import Sum

# Module imports
from plane.billing.models import LedgerAccount, LedgerAccountKind, LedgerEntry, LedgerSource, Wallet
from plane.db.models import Workspace

pytestmark = pytest.mark.django_db


def test_account_code_is_unique():
    LedgerAccount.objects.create(code="wallet:default:1", kind=LedgerAccountKind.ASSET, title="کیف پول")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerAccount.objects.create(code="wallet:default:1", kind=LedgerAccountKind.ASSET, title="تکراری")


def test_entry_rejects_identical_debit_and_credit():
    account = LedgerAccount.objects.create(code="a", kind=LedgerAccountKind.ASSET, title="الف")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                debit_account=account,
                credit_account=account,
                amount_toman=1000,
                source=LedgerSource.ADMIN_GRANT,
                idempotency_key="k1",
            )


def test_entry_rejects_zero_amount():
    debit = LedgerAccount.objects.create(code="d", kind=LedgerAccountKind.ASSET, title="بدهکار")
    credit = LedgerAccount.objects.create(code="c", kind=LedgerAccountKind.LIABILITY, title="بستانه")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                debit_account=debit,
                credit_account=credit,
                amount_toman=0,
                source=LedgerSource.ADMIN_GRANT,
                idempotency_key="k2",
            )


def test_idempotency_key_is_unique():
    debit = LedgerAccount.objects.create(code="d2", kind=LedgerAccountKind.ASSET, title="بدهکار")
    credit = LedgerAccount.objects.create(code="c2", kind=LedgerAccountKind.REVENUE, title="درآمد")
    LedgerEntry.objects.create(
        debit_account=debit, credit_account=credit, amount_toman=500, source=LedgerSource.ADMIN_GRANT, idempotency_key="dup"
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                debit_account=debit, credit_account=credit, amount_toman=500, source=LedgerSource.ADMIN_GRANT, idempotency_key="dup"
            )


def test_wallet_is_one_per_workspace():
    workspace = Workspace.objects.create(name="تیم", slug="team-wallet-test")
    Wallet.objects.create(workspace=workspace)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Wallet.objects.create(workspace=workspace)


def test_balance_is_the_sum_of_entries_not_a_column():
    """A wallet has no balance column; the sum of debits minus credits is the balance."""
    workspace = Workspace.objects.create(name="تیم ۲", slug="team-sum-test")
    wallet = Wallet.objects.create(workspace=workspace)
    assert not hasattr(wallet, "balance_toman")

    default = LedgerAccount.objects.create(
        code=f"wallet:default:{workspace.pk}", kind=LedgerAccountKind.ASSET, title="کیف پول", workspace=workspace
    )
    pool = LedgerAccount.objects.create(code="admin_grant_pool", kind=LedgerAccountKind.ADMIN_POOL, title="اعتبار ادمین")
    LedgerEntry.objects.create(
        debit_account=default,
        credit_account=pool,
        amount_toman=120_000,
        source=LedgerSource.ADMIN_GRANT,
        workspace=workspace,
        idempotency_key="sum-1",
    )
    balance = LedgerEntry.objects.filter(workspace=workspace).aggregate(total=Sum("amount_toman"))["total"]
    assert balance == 120_000
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_money.py -v
```

Expected: collection error — `ImportError: cannot import name 'LedgerAccount'`

- [ ] **Step 3: Add the enums to models.py**

Insert after `TransactionStatus` (ends line 51), before `SubscriptionStatus`:

```python
class LedgerAccountKind(models.TextChoices):
    ASSET = "asset", "Asset"
    LIABILITY = "liability", "Liability"
    REVENUE = "revenue", "Revenue"
    GATEWAY_SETTLEMENT = "gateway_settlement", "Gateway settlement"
    ADMIN_POOL = "admin_pool", "Admin grant pool"


class LedgerSource(models.TextChoices):
    GATEWAY = "gateway", "Gateway"
    ADMIN_GRANT = "admin_grant", "Admin grant"
    SMS_CHARGE = "sms_charge", "SMS charge"
    PLAN_PURCHASE = "plan_purchase", "Plan purchase"
    UPGRADE = "upgrade", "Upgrade"
    REFUND = "refund", "Refund"
    RELEASE_HOLD = "release_hold", "Release hold"
```

- [ ] **Step 4: Append the three models**

Append after `WorkspaceFeatureFlag` (ends line 434). Do not nest them — each is a top level class:

```python
class LedgerAccount(BaseModel):
    """One side of every money movement. Codes are stable and referenced in code."""

    code = models.CharField(max_length=255, unique=True, db_index=True)
    kind = models.CharField(max_length=32, choices=LedgerAccountKind.choices, default=LedgerAccountKind.ASSET)
    title = models.CharField(max_length=255, blank=True)
    workspace = models.ForeignKey(
        "db.Workspace", on_delete=models.CASCADE, related_name="ledger_accounts", null=True, blank=True
    )

    class Meta:
        ordering = ("code",)

    def __str__(self) -> str:
        return self.code

    @property
    def is_debit_normal(self) -> bool:
        """Assets and pools grow on the debit side, everything else on the credit side."""
        return self.kind in (LedgerAccountKind.ASSET, LedgerAccountKind.ADMIN_POOL)


class LedgerEntry(BaseModel):
    """One balanced movement of money. ``amount_toman`` is always positive."""

    debit_account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="debit_entries")
    credit_account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name="credit_entries")
    amount_toman = models.PositiveBigIntegerField()
    source = models.CharField(max_length=32, choices=LedgerSource.choices)
    workspace = models.ForeignKey(
        "db.Workspace", on_delete=models.CASCADE, related_name="ledger_entries", null=True, blank=True
    )
    description = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "db.User", on_delete=models.SET_NULL, related_name="ledger_entries", null=True, blank=True
    )
    invoice = models.ForeignKey(
        "billing.Invoice", on_delete=models.SET_NULL, related_name="ledger_entries", null=True, blank=True
    )
    transaction = models.ForeignKey(
        "billing.PaymentTransaction", on_delete=models.SET_NULL, related_name="ledger_entries", null=True, blank=True
    )
    idempotency_key = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(debit_account=models.F("credit_account")),
                name="ledger_entry_distinct_accounts",
            ),
            models.CheckConstraint(condition=models.Q(amount_toman__gt=0), name="ledger_entry_positive_amount"),
        ]

    def __str__(self) -> str:
        return f"{self.source} {self.amount_toman}"


class Wallet(BaseModel):
    """A workspace wallet. The balance lives in LedgerEntry rows, never in a column."""

    workspace = models.OneToOneField("db.Workspace", on_delete=models.CASCADE, related_name="billing_wallet")
    # Zero means no cap. Guards against a mistyped admin grant.
    admin_grant_cap_toman = models.PositiveBigIntegerField(default=0)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"wallet:{self.workspace.slug}"
```

- [ ] **Step 5: Generate and inspect the migration**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm api-tests python manage.py makemigrations billing
```

Expected: a file named `0003_*.py`. Rename it to `0003_wallet_ledger.py`, then read it and confirm it contains `distinct_accounts` and `positive_amount` checks and the `wallet` OneToOne.

- [ ] **Step 6: Run test to verify it passes**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_money.py -v
```

Expected: 6 passed

- [ ] **Step 7: Commit**

```bash
git add apps/api/plane/billing/models.py apps/api/plane/billing/migrations/0003_wallet_ledger.py apps/api/plane/billing/tests/test_money.py
git commit -m "feat(billing): add double-entry ledger models

LedgerAccount, LedgerEntry and Wallet. No model stores a balance, so
every movement of money is forced through a balanced entry. The
database rejects an entry that debits and credits the same account or
carries a zero amount, so those invariants hold even if a future
service layer forgets them."
```

---

## Task 2: The money service — account codes, posting, balance

**Files:**

- Create: `apps/api/plane/billing/services/money.py`
- Test: `apps/api/plane/billing/tests/test_money.py` (append)

**Interfaces:**

- Consumes: `LedgerAccount`, `LedgerEntry`, `Wallet`, `LedgerAccountKind`, `LedgerSource` from Task 1
- Produces:
  - `class WalletAccountCode` with static methods `wallet_default(workspace_pk) -> str`, `wallet_hold(workspace_pk) -> str`
  - `class LedgerAccountCode` with static method `gateway_receivable(gateway_code: str) -> str`
  - `get_or_create_account(code: str, kind: str, title: str, workspace=None) -> LedgerAccount`
  - `post_entry(*, debit, credit, amount_toman: int, source: str, workspace=None, description: str = "", created_by=None, invoice=None, transaction=None, idempotency_key: str) -> LedgerEntry`
  - `account_balance(account: LedgerAccount) -> int`
  - `wallet_balance(workspace) -> int`
  - `round_to_toman(value: Decimal) -> int`

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/plane/billing/tests/test_money.py`:

```python
# Local imports
from plane.billing.services import money


def test_wallet_account_codes_are_stable():
    assert money.WalletAccountCode.wallet_default("abc-123") == "wallet:default:abc-123"
    assert money.WalletAccountCode.wallet_hold("abc-123") == "wallet:hold:abc-123"
    assert money.WalletAccountCode.gateway_receivable("zarinpal") == "gateway:zarinpal:receivable"


def test_post_entry_creates_one_balanced_row():
    workspace = Workspace.objects.create(name="تیم ۳", slug="team-post-test")
    debit = money.get_or_create_account("d3", LedgerAccountKind.ASSET, "بدهکار")
    credit = money.get_or_create_account("c3", LedgerAccountKind.ADMIN_POOL, "بستانه")

    entry = money.post_entry(
        debit=debit,
        credit=credit,
        amount_toman=7_500,
        source=LedgerSource.ADMIN_GRANT,
        workspace=workspace,
        idempotency_key="post-1",
    )

    assert entry.amount_toman == 7_500
    assert entry.debit_account_id == debit.pk
    assert entry.credit_account_id == credit.pk


def test_post_entry_is_idempotent_and_returns_the_first_row():
    debit = money.get_or_create_account("d4", LedgerAccountKind.ASSET, "بدهکار")
    credit = money.get_or_create_account("c4", LedgerAccountKind.ADMIN_POOL, "بستانه")

    first = money.post_entry(debit=debit, credit=credit, amount_toman=1000, source=LedgerSource.ADMIN_GRANT, idempotency_key="same")
    second = money.post_entry(debit=debit, credit=credit, amount_toman=1000, source=LedgerSource.ADMIN_GRANT, idempotency_key="same")

    assert first.pk == second.pk
    assert LedgerEntry.objects.filter(idempotency_key="same").count() == 1
    # the replay must not double the balance
    assert money.account_balance(debit) == 1000


def test_wallet_balance_counts_debits_minus_credits():
    workspace = Workspace.objects.create(name="تیم ۴", slug="team-balance-test")
    default = money.get_or_create_account(
        money.WalletAccountCode.wallet_default(workspace.pk), LedgerAccountKind.ASSET, "کیف پول قابل خرج", workspace
    )
    hold = money.get_or_create_account(
        money.WalletAccountCode.wallet_hold(workspace.pk), LedgerAccountKind.LIABILITY, "کیف پول قفل", workspace
    )
    pool = money.get_or_create_account("pool-1", LedgerAccountKind.ADMIN_POOL, "استخر اعتبار")

    money.post_entry(debit=default, credit=pool, amount_toman=50_000, source=LedgerSource.ADMIN_GRANT, workspace=workspace, idempotency_key="b1")
    # holding money moves it out of the spendable account
    money.post_entry(debit=default, credit=hold, amount_toman=20_000, source=LedgerSource.REFUND, workspace=workspace, idempotency_key="b2")

    assert money.wallet_balance(workspace) == 30_000
    # the hold is tracked separately and is not spendable
    assert money.wallet_hold_balance(workspace) == 20_000


def test_round_to_toman_rounds_to_the_nearest_thousand():
    assert money.round_to_toman(Decimal("1234.4")) == 1000
    assert money.round_to_toman(Decimal("1234.5")) == 2000
    assert money.round_to_toman(Decimal("999")) == 1000
```

Add `from decimal import Decimal` to the imports at the top of the file.

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_money.py -v
```

Expected: collection error — `ModuleNotFoundError: No module named 'plane.billing.services.money'`

- [ ] **Step 3: Create the module**

Create `apps/api/plane/billing/services/money.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Pure balance arithmetic for the double entry ledger.

This module owns every money movement in the product. It deliberately
knows nothing about requests, users or permissions so that it can be
tested without a database and reused by every subsystem that spends or
receives money.

No balance is ever stored. ``account_balance`` derives it from entries.
"""

# Python imports
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

# Django imports
from django.db import IntegrityError, transaction

# Module imports
from plane.billing.models import LedgerAccount, LedgerAccountKind, LedgerEntry, LedgerSource, Wallet

# All Toman amounts are rounded to the nearest 1,000 so an invoice reads cleanly.
ROUNDING_UNIT = Decimal("1000")


class WalletAccountCode:
    """Account codes for the two sides of a workspace wallet."""

    @staticmethod
    def wallet_default(workspace_pk) -> str:
        """Spendable balance."""
        return f"wallet:default:{workspace_pk}"

    @staticmethod
    def wallet_hold(workspace_pk) -> str:
        """Balance withheld pending an admin decision. Never spendable."""
        return f"wallet:hold:{workspace_pk}"

    @staticmethod
    def gateway_receivable(gateway_code: str) -> str:
        return f"gateway:{gateway_code}:receivable"


ADMIN_GRANT_POOL = "admin_grant_pool"


def round_to_toman(value: Decimal) -> int:
    """Round to the nearest 1,000 Toman, halves going up."""
    return int(Decimal(value).quantize(ROUNDING_UNIT, rounding=ROUND_HALF_UP))


def get_or_create_account(code: str, kind: str, title: str, workspace=None) -> LedgerAccount:
    """Fetch an account by its stable code, creating it the first time.

    Creating an account is idempotent so that a caller never has to seed
    accounts ahead of time.
    """
    account, _ = LedgerAccount.objects.get_or_create(
        code=code,
        defaults={"kind": kind, "title": title, "workspace": workspace},
    )
    return account


def get_or_create_wallet_accounts(workspace) -> tuple[LedgerAccount, LedgerAccount]:
    """The spendable and held accounts of a workspace, created on demand."""
    spendable = get_or_create_account(
        WalletAccountCode.wallet_default(workspace.pk), LedgerAccountKind.ASSET, "موجودی قابل خرج", workspace
    )
    held = get_or_create_account(
        WalletAccountCode.wallet_hold(workspace.pk), LedgerAccountKind.LIABILITY, "موجودی قفل‌شده", workspace
    )
    return spendable, held


def post_entry(
    *,
    debit: LedgerAccount,
    credit: LedgerAccount,
    amount_toman: int,
    source: str,
    workspace=None,
    description: str = "",
    created_by=None,
    invoice=None,
    transaction=None,
    idempotency_key: str,
) -> LedgerEntry:
    """Write one balanced movement of money.

    Replaying the same ``idempotency_key`` returns the original row and
    posts nothing, so a gateway callback that arrives twice cannot double
    a balance.
    """
    if debit.pk == credit.pk:
        raise ValueError("debit and credit accounts must differ")
    if amount_toman <= 0:
        raise ValueError("amount_toman must be positive")

    existing = LedgerEntry.objects.filter(idempotency_key=idempotency_key).first()
    if existing is not None:
        return existing

    try:
        with transaction.atomic():
            return LedgerEntry.objects.create(
                debit_account=debit,
                credit_account=credit,
                amount_toman=amount_toman,
                source=source,
                workspace=workspace,
                description=description,
                created_by=created_by,
                invoice=invoice,
                transaction=transaction,
                idempotency_key=idempotency_key,
            )
    except IntegrityError:
        # Lost a race against a concurrent replay of the same key.
        return LedgerEntry.objects.get(idempotency_key=idempotency_key)


def _signed_total(account: LedgerAccount, workspace=None) -> int:
    """Debits minus credits for one account, respecting its normal side."""
    entries = LedgerEntry.objects.filter(workspace=workspace) if workspace is not None else LedgerEntry.objects.all()
    debit_total = entries.filter(debit_account=account).aggregate(total=Sum("amount_toman"))["total"] or 0
    credit_total = entries.filter(credit_account=account).aggregate(total=Sum("amount_toman"))["total"] or 0

    if account.is_debit_normal:
        return debit_total - credit_total
    return credit_total - debit_total


def account_balance(account: LedgerAccount, workspace=None) -> int:
    """Balance of a single account. Positive means the account holds money."""
    return _signed_total(account, workspace=workspace)


def wallet_balance(workspace) -> int:
    """Spendable wallet balance for a workspace. Never returns a negative value silently."""
    spendable, _held = get_or_create_wallet_accounts(workspace)
    return max(0, _signed_total(spendable, workspace=workspace))


def wallet_hold_balance(workspace) -> int:
    """How much of the workspace's money is currently withheld."""
    _spendable, held = get_or_create_wallet_accounts(workspace)
    return max(0, _signed_total(held, workspace=workspace))
```

Add the missing import at the top:

```python
# Django imports
from django.db.models import Sum
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_money.py -v
```

Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/billing/services/money.py apps/api/plane/billing/tests/test_money.py
git commit -m "feat(billing): add the money service for ledger arithmetic

post_entry is keyed on idempotency_key so a replayed callback returns
the original row instead of moving money twice. wallet_balance derives
from entries rather than a column, which is what keeps the reported
balance and the ledger impossible to disagree."
```

---

## Task 3: The billing ledger permission

**Files:**

- Create: `apps/api/plane/billing/api/permissions.py`
- Test: `apps/api/plane/billing/tests/test_ledger_security.py` (created here, minimal)

**Interfaces:**

- Consumes: `plane.db.models.workspace.WorkspaceMember`
- Produces: `WorkspaceBillingLedgerPermission(BasePermission)` reading `view.workspace_slug`

- [ ] **Step 1: Write the failing test**

Create `apps/api/plane/billing/tests/test_ledger_security.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Leak tests for the financial endpoints.

The permission used here must reject role 15. WorkSpaceAdminPermission
does not — it accepts role__in=[Admin, Member] — so financial data may
never be guarded by it.
"""

# Third party imports
import pytest

# Django imports

# Module imports
from plane.billing.api.permissions import WorkspaceBillingLedgerPermission

pytestmark = pytest.mark.django_db


class _FakeView:
    def __init__(self, slug):
        self.workspace_slug = slug


class _FakeRequest:
    def __init__(self, user):
        self.user = user


def test_existing_workspace_admin_permission_accepts_role_15():
    """The reason this permission exists: guard against reusing the loose one."""
    from plane.app.permissions.workspace import WorkSpaceAdminPermission

    import inspect

    source = inspect.getsource(WorkSpaceAdminPermission.has_permission)
    assert "role=Admin" not in source, "if this now filters to role 20 only, revisit whether this permission is needed"
    assert "role__in=[Admin, Member]" in source
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_ledger_security.py -v
```

Expected: `ModuleNotFoundError: No module named 'plane.billing.api.permissions'`

- [ ] **Step 3: Create the permission**

Create `apps/api/plane/billing/api/permissions.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Permissions for financial data."""

# Python imports

# Third party imports
from rest_framework.permissions import BasePermission

# Django imports

# Module imports
from plane.db.models.workspace import WorkspaceMember

# Plane role numbers. Admin is 20, a plain Member is 15.
ADMIN_ROLE = 20


class WorkspaceBillingLedgerPermission(BasePermission):
    """Read access to a workspace's own money for workspace admins only.

    ``WorkSpaceAdminPermission`` is not reused on purpose: it accepts
    ``role__in=[Admin, Member]``, so it also lets ordinary members
    through. A ledger shows how much a company spends and how much an
    instance administrator granted it, which no ordinary member may see.
    """

    message = "این بخش تنها برای مدیران ورک‌اسپیس در دسترس است."

    def has_permission(self, request, view) -> bool:
        if request.user is None or request.user.is_anonymous:
            return False
        return WorkspaceMember.objects.filter(
            member=request.user,
            workspace__slug=view.workspace_slug,
            role=ADMIN_ROLE,
            is_active=True,
        ).exists()
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_ledger_security.py -v
```

Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/billing/api/permissions.py apps/api/plane/billing/tests/test_ledger_security.py
git commit -m "feat(billing): add a role 20 permission for financial reads

WorkSpaceAdminPermission accepts role 15 as well as 20, so guarding a
ledger with it would expose spending and admin grants to every member.
The test pins that behaviour down so the loose permission is never
reused here by accident."
```

---

## Task 4: Wallet operations — grant, revoke, charge, hold

**Files:**

- Create: `apps/api/plane/billing/services/wallet.py`
- Test: `apps/api/plane/billing/tests/test_wallet.py` (create)

**Interfaces:**

- Consumes: everything from Task 2's `money` module
- Produces:
  - `class WalletError(Exception)`
  - `class GrantTooLarge(WalletError)`, `class InsufficientBalance(WalletError)`, `class InvalidGrantDescription(WalletError)`
  - `MIN_GRANT_DESCRIPTION_LENGTH = 10`
  - `grant_from_admin(*, workspace, amount_toman: int, description: str, created_by, idempotency_key: str) -> LedgerEntry`
  - `revoke_grant(*, workspace, entry: LedgerEntry, description: str, created_by, idempotency_key: str) -> LedgerEntry`
  - `charge_sms(*, workspace, amount_toman: int, log_id, idempotency_key: str = None) -> LedgerEntry`
  - `hold_funds(*, workspace, amount_toman: int, source: str, idempotency_key: str) -> LedgerEntry`
  - `release_hold(*, workspace, amount_toman: int, idempotency_key: str) -> LedgerEntry`
  - `refund_to_spendable(*, workspace, amount_toman: int, reason: str, idempotency_key: str) -> LedgerEntry`

- [ ] **Step 1: Write the failing tests**

Create `apps/api/plane/billing/tests/test_wallet.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Wallet policy: grants, revocations, charges and holds."""

# Third party imports
import pytest
from django.db import transaction as db_transaction

# Django imports

# Module imports
from plane.billing.models import LedgerEntry, LedgerSource, Wallet
from plane.billing.services import money, wallet
from plane.db.models import Workspace

pytestmark = pytest.mark.django_db


@pytest.fixture
def workspace(db):
    return Workspace.objects.create(name="تیم کیف پول", slug="wallet-ops-team")


@pytest.fixture
def admin_user(db):
    from plane.db.models import User

    return User.objects.create(email="granter@example.com", first_name="Grant", last_name="Admin")


def test_grant_requires_a_meaningful_description(workspace, admin_user):
    with pytest.raises(wallet.InvalidGrantDescription):
        wallet.grant_from_admin(
            workspace=workspace, amount_toman=10_000, description="کوتاه", created_by=admin_user, idempotency_key="g-bad"
        )


def test_grant_moves_money_into_the_workspace(workspace, admin_user):
    entry = wallet.grant_from_admin(
        workspace=workspace, amount_toman=250_000, description="هدیهٔ قرارداد سالانهٔ مشتری نمونه", created_by=admin_user, idempotency_key="g-1"
    )

    assert entry.source == LedgerSource.ADMIN_GRANT
    assert entry.created_by_id == admin_user.pk
    assert entry.workspace_id == workspace.pk
    assert money.wallet_balance(workspace) == 250_000


def test_grant_respects_the_cap(workspace, admin_user):
    Wallet.objects.create(workspace=workspace, admin_grant_cap_toman=100_000)

    with pytest.raises(wallet.GrantTooLarge):
        wallet.grant_from_admin(
            workspace=workspace, amount_toman=500_000, description="بیش از سقف مجاز", created_by=admin_user, idempotency_key="g-cap"
        )

    assert money.wallet_balance(workspace) == 0


def test_grant_is_idempotent(workspace, admin_user):
    first = wallet.grant_from_admin(
        workspace=workspace, amount_toman=10_000, description="شارژ آزمایشی اول", created_by=admin_user, idempotency_key="g-same"
    )
    second = wallet.grant_from_admin(
        workspace=workspace, amount_toman=10_000, description="شارژ آزمایشی اول", created_by=admin_user, idempotency_key="g-same"
    )

    assert first.pk == second.pk
    assert money.wallet_balance(workspace) == 10_000


def test_revoke_writes_a_reversing_entry_and_keeps_the_original(workspace, admin_user):
    original = wallet.grant_from_admin(
        workspace=workspace, amount_toman=80_000, description="شارژ اولیه برای آزمایش", created_by=admin_user, idempotency_key="r-1"
    )

    reversal = wallet.revoke_grant(
        workspace=workspace, entry=original, description="ابطال اشتباه ادمین", created_by=admin_user, idempotency_key="r-1-rev"
    )

    assert reversal.amount_toman == 80_000
    # the original row is untouched — history is never rewritten
    assert LedgerEntry.objects.filter(pk=original.pk).exists()
    assert money.wallet_balance(workspace) == 0


def test_charge_sms_reduces_the_spendable_balance(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace, amount_toman=100_000, description="شارژ برای تست پیامک", created_by=admin_user, idempotency_key="c-setup"
    )

    entry = wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=77)

    assert entry.source == LedgerSource.SMS_CHARGE
    assert money.wallet_balance(workspace) == 98_800


def test_charge_sms_is_idempotent_per_log(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace, amount_toman=100_000, description="شارژ برای تست تکرار پیامک", created_by=admin_user, idempotency_key="c-setup-2"
    )

    first = wallet.charge_sms(workspace=workspace, amount_toman=900, log_id=88)
    second = wallet.charge_sms(workspace=workspace, amount_toman=900, log_id=88)

    assert first.pk == second.pk
    assert money.wallet_balance(workspace) == 99_100


def test_charge_sms_refuses_an_empty_wallet(workspace):
    with pytest.raises(wallet.InsufficientBalance):
        wallet.charge_sms(workspace=workspace, amount_toman=1_200, log_id=99)

    assert money.wallet_balance(workspace) == 0


def test_charge_sms_refuses_a_short_balance(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace, amount_toman=5_000, description="شارژ ناکافی برای تست", created_by=admin_user, idempotency_key="c-setup-3"
    )

    with pytest.raises(wallet.InsufficientBalance):
        wallet.charge_sms(workspace=workspace, amount_toman=6_000, log_id=100)


def test_hold_moves_money_out_of_reach_and_release_returns_it(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace, amount_toman=200_000, description="شارژ برای تست قفل", created_by=admin_user, idempotency_key="h-setup"
    )

    wallet.hold_funds(workspace=workspace, amount_toman=120_000, source=LedgerSource.REFUND, idempotency_key="h-1")

    assert money.wallet_balance(workspace) == 80_000
    assert money.wallet_hold_balance(workspace) == 120_000

    wallet.release_hold(workspace=workspace, amount_toman=120_000, idempotency_key="h-1-rel")

    assert money.wallet_balance(workspace) == 200_000
    assert money.wallet_hold_balance(workspace) == 0


def test_release_hold_cannot_exceed_what_is_held(workspace, admin_user):
    wallet.grant_from_admin(
        workspace=workspace, amount_toman=50_000, description="شارژ برای تست آزادسازی", created_by=admin_user, idempotency_key="rh-setup"
    )
    wallet.hold_funds(workspace=workspace, amount_toman=20_000, source=LedgerSource.REFUND, idempotency_key="rh-1")

    with pytest.raises(wallet.InsufficientBalance):
        wallet.release_hold(workspace=workspace, amount_toman=40_000, idempotency_key="rh-1-bad")


@pytest.fixture
def race_workspace(db):
    return Workspace.objects.create(name="تیم هم‌زمانی", slug="wallet-race-team")


def test_concurrent_charges_do_not_overdraw(race_workspace):
    """Two charges racing on the same balance must not both succeed past the limit.

    ``charge_sms`` takes a row lock on the wallet account, so the second
    charge sees the balance the first one already spent. Sequential calls
    with the lock held model that interleaving without needing threads.
    """
    workspace = race_workspace
    admin_user = None

    wallet.grant_from_admin(
        workspace=workspace, amount_toman=10_000, description="شارژ برای تست هم‌زمانی", created_by=admin_user, idempotency_key="race-setup"
    )

    # Simulate the interleaving by charging twice inside one transaction and
    # confirming the second is refused once the balance is gone.
    wallet.charge_sms(workspace=workspace, amount_toman=6_000, log_id=201)
    with pytest.raises(wallet.InsufficientBalance):
        wallet.charge_sms(workspace=workspace, amount_toman=6_000, log_id=202)

    assert money.wallet_balance(workspace) == 4_000
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_wallet.py -v
```

Expected: `ModuleNotFoundError: No module named 'plane.billing.services.wallet'`

- [ ] **Step 3: Create the module**

Create `apps/api/plane/billing/services/wallet.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Wallet policy: how money enters a workspace wallet and how it leaves.

Every function here delegates the arithmetic to ``services.money``. This
layer owns the rules — what a valid grant looks like, when a charge is
refused, what a hold means — so those rules can be read in one place.
"""

# Python imports
from typing import Optional

# Django imports
from django.db import transaction

# Module imports
from plane.billing.models import LedgerEntry, LedgerSource, Wallet
from plane.billing.services import money

# An admin grant is an internal note. Anything shorter than this is a typo,
# not an explanation.
MIN_GRANT_DESCRIPTION_LENGTH = 10


class WalletError(Exception):
    """Base class for wallet policy violations."""

    message = "عملیات کیف پول نامعتبر است."

    def __init__(self, message: str = None):
        self.message = message or self.__class__.message
        super().__init__(self.message)


class InvalidGrantDescription(WalletError):
    message = "توضیح اعتبار دستی الزامی و باید حداقل ۱۰ کاراکتر باشد."


class GrantTooLarge(WalletError):
    message = "مبلغ اعتبار از سقف مجاز هر بار بیشتر است."


class InsufficientBalance(WalletError):
    message = "موجودی کیف پول کافی نیست."


def _assert_amount(amount_toman: int) -> None:
    if not isinstance(amount_toman, int) or amount_toman <= 0:
        raise WalletError("مبلغ باید عدد صحیح مثبت باشد.")


def _pool_account():
    return money.get_or_create_account(money.ADMIN_GRANT_POOL, "admin_pool", "اعتبار اعطایی مدیر")


def grant_from_admin(
    *, workspace, amount_toman: int, description: str, created_by, idempotency_key: str
) -> LedgerEntry:
    """Credit a workspace wallet from the instance admin grant pool.

    ``created_by`` comes from the authenticated request, never from the
    request body, so an admin cannot be forged onto a grant.
    """
    _assert_amount(amount_toman)
    if not description or len(description.strip()) < MIN_GRANT_DESCRIPTION_LENGTH:
        raise InvalidGrantDescription()

    spendable, _held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        wallet_row, _created = Wallet.objects.get_or_create(workspace=workspace)
        cap = wallet_row.admin_grant_cap_toman
        if cap and amount_toman > cap:
            raise GrantTooLarge()

        return money.post_entry(
            debit=_pool_account(),
            credit=spendable,
            amount_toman=amount_toman,
            source=LedgerSource.ADMIN_GRANT,
            workspace=workspace,
            description=description.strip(),
            created_by=created_by,
            idempotency_key=idempotency_key,
        )


def revoke_grant(*, workspace, entry: LedgerEntry, description: str, created_by, idempotency_key: str) -> LedgerEntry:
    """Reverse a grant with a new entry. The original row is never edited or deleted."""
    _assert_amount(entry.amount_toman)
    if not description or len(description.strip()) < MIN_GRANT_DESCRIPTION_LENGTH:
        raise InvalidGrantDescription()

    spendable, _held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        locked = LedgerEntry.objects.select_for_update().get(pk=entry.pk)
        spendable_row = type(spendable).objects.select_for_update().get(pk=spendable.pk)
        if money.account_balance(spendable_row, workspace=workspace) < locked.amount_toman:
            raise InsufficientBalance("موجودی برای ابطال کل مبلغ کافی نیست.")

        return money.post_entry(
            debit=spendable_row,
            credit=locked.debit_account,
            amount_toman=locked.amount_toman,
            source=LedgerSource.REFUND,
            workspace=workspace,
            description=description.strip(),
            created_by=created_by,
            idempotency_key=idempotency_key,
        )


def charge_sms(*, workspace, amount_toman: int, log_id, idempotency_key: Optional[str] = None) -> LedgerEntry:
    """Spend from the wallet for one outbound SMS.

    Keyed on the notification log id so a retried delivery never charges
    the workspace twice for the same message.
    """
    _assert_amount(amount_toman)
    key = idempotency_key or f"sms:{log_id}:charge"

    spendable, _held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        locked_spendable = type(spendable).objects.select_for_update().get(pk=spendable.pk)
        if money.account_balance(locked_spendable, workspace=workspace) < amount_toman:
            raise InsufficientBalance()

        return money.post_entry(
            debit=locked_spendable,
            credit=money.get_or_create_account("expense:sms", "revenue", "هزینهٔ پیامک"),
            amount_toman=amount_toman,
            source=LedgerSource.SMS_CHARGE,
            workspace=workspace,
            idempotency_key=key,
        )


def hold_funds(*, workspace, amount_toman: int, source: str, idempotency_key: str) -> LedgerEntry:
    """Move money out of the spendable balance into the hold.

    Used when a payment was taken but could not be applied. The workspace
    owner cannot spend or see this money until an admin decides.
    """
    _assert_amount(amount_toman)
    spendable, held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        locked_spendable = type(spendable).objects.select_for_update().get(pk=spendable.pk)
        if money.account_balance(locked_spendable, workspace=workspace) < amount_toman:
            raise InsufficientBalance("موجودی برای قفل کردن کافی نیست.")

        return money.post_entry(
            debit=locked_spendable,
            credit=held,
            amount_toman=amount_toman,
            source=source,
            workspace=workspace,
            idempotency_key=idempotency_key,
        )


def release_hold(*, workspace, amount_toman: int, idempotency_key: str) -> LedgerEntry:
    """Return held money to the spendable balance."""
    _assert_amount(amount_toman)
    spendable, held = money.get_or_create_wallet_accounts(workspace)

    with transaction.atomic():
        locked_held = type(held).objects.select_for_update().get(pk=held.pk)
        if money.account_balance(locked_held, workspace=workspace) < amount_toman:
            raise InsufficientBalance("مبلغ قفل‌شده کافی نیست.")

        return money.post_entry(
            debit=locked_held,
            credit=spendable,
            amount_toman=amount_toman,
            source=LedgerSource.RELEASE_HOLD,
            workspace=workspace,
            idempotency_key=idempotency_key,
        )


def refund_to_spendable(*, workspace, amount_toman: int, reason: str, idempotency_key: str) -> LedgerEntry:
    """Return money directly to the spendable balance without passing through a hold.

    Only for a payment the gateway explicitly rejected, where we know no
    money was ever taken.
    """
    _assert_amount(amount_toman)
    spendable, _held = money.get_or_create_wallet_accounts(workspace)
    return money.post_entry(
        debit=money.get_or_create_account(f"gateway:reversal:{idempotency_key}", "gateway_settlement", "برگشت درگاه"),
        credit=spendable,
        amount_toman=amount_toman,
        source=LedgerSource.REFUND,
        workspace=workspace,
        description=reason,
        idempotency_key=idempotency_key,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_wallet.py -v
```

Expected: 13 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/billing/services/wallet.py apps/api/plane/billing/tests/test_wallet.py
git commit -m "feat(billing): add wallet grant, charge and hold operations

Grants require a ten character description and honour a per-wallet cap
so a mistyped amount cannot wreck the instance's whole balance. Charges
are keyed on the notification log id, so a retried SMS delivery is never
billed twice. Holds take money out of reach instead of returning it,
which is what makes a failed payment auditable rather than lost."
```

---

## Task 5: Ledger queries and the two projections

**Files:**

- Create: `apps/api/plane/billing/services/ledger.py`
- Modify: `apps/api/plane/billing/api/serializers.py` (append)
- Test: `apps/api/plane/billing/tests/test_ledger_security.py` (append)

**Interfaces:**

- Consumes: `LedgerEntry`, `LedgerAccount` from Task 1; `money` from Task 2
- Produces:
  - `ledger.workspace_entries(workspace) -> QuerySet[LedgerEntry]` — already scoped, takes no scope argument
  - `ledger.all_entries() -> QuerySet[LedgerEntry]`
  - `ledger.public_description(entry) -> str` — strips admin internal text
  - `AdminLedgerEntrySerializer`
  - `WorkspaceLedgerEntrySerializer` — no `created_by`, no `invoice`, no `transaction`, no account codes
  - `WalletSerializer` — balance, hold, cap
  - `WalletGrantSerializer` — validates `amount_toman` and `description`

- [ ] **Step 1: Write the failing tests**

Append to `apps/api/plane/billing/tests/test_ledger_security.py`:

```python
# Module imports
from plane.billing.models import LedgerEntry, LedgerSource
from plane.billing.services import money, wallet
from plane.db.models import Workspace

from plane.billing.api.serializers import WorkspaceLedgerEntrySerializer


@pytest.fixture
def funded_workspace(db):
    ws = Workspace.objects.create(name="تیم نشت", slug="leak-team")
    admin_user = None
    from plane.db.models import User

    admin_user = User.objects.create(email="leak-admin@example.com", first_name="Leak", last_name="Admin")
    wallet.grant_from_admin(
        workspace=ws, amount_toman=400_000, description="اعتبار داخلی محرمانه برای شرکت نمونه", created_by=admin_user, idempotency_key="leak-1"
    )
    return ws, admin_user


def test_workspace_projection_hides_the_actor_and_internal_accounts(funded_workspace):
    ws, _admin = funded_workspace

    entry = LedgerEntry.objects.get(idempotency_key="leak-1")
    data = WorkspaceLedgerEntrySerializer(entry).data

    assert "created_by" not in data
    assert "invoice" not in data
    assert "transaction" not in data
    assert "debit_account" not in data
    assert "credit_account" not in data
    # the amount is the workspace's own business and stays visible
    assert data["amount_toman"] == 400_000


def test_workspace_projection_does_not_repeat_the_internal_description(funded_workspace):
    ws, _admin = funded_workspace
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")

    data = WorkspaceLedgerEntrySerializer(entry).data

    assert "محرمانه" not in data["description"]


def test_admin_projection_keeps_the_internal_detail(funded_workspace):
    ws, admin = funded_workspace
    entry = LedgerEntry.objects.get(idempotency_key="leak-1")

    from plane.billing.api.serializers import AdminLedgerEntrySerializer

    data = AdminLedgerEntrySerializer(entry).data

    assert "محرمانه" in data["description"]
    assert data["created_by"]["id"] == str(admin.pk)


def test_workspace_entries_queryset_never_spans_workspaces(funded_workspace):
    ws, _admin = funded_workspace
    other = Workspace.objects.create(name="تیم دیگر", slug="other-team")
    admin_user = None
    from plane.db.models import User

    admin_user = User.objects.create(email="other-admin@example.com", first_name="Other", last_name="Admin")
    wallet.grant_from_admin(
        workspace=other, amount_toman=999_000, description="اعتبار تیم دیگر که نباید دیده شود", created_by=admin_user, idempotency_key="leak-2"
    )

    codes = set(ledger.workspace_entries(ws).values_list("idempotency_key", flat=True))
    assert codes == {"leak-1"}


def test_ledger_module_has_no_scope_parameter():
    """The scope must come from the queryset the caller built, never from a parameter."""
    import inspect

    from plane.billing.services import ledger

    signature = inspect.signature(ledger.workspace_entries)
    assert list(signature.parameters) == ["workspace"]
```

Add the missing import at the top of the test file:

```python
# Module imports
from plane.billing.services import ledger
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_ledger_security.py -v
```

Expected: `ModuleNotFoundError: No module named 'plane.billing.services.ledger'`

- [ ] **Step 3: Create the ledger service**

Create `apps/api/plane/billing/services/ledger.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Reading the ledger.

Scope is decided by which function a caller picks, never by a parameter.
There is deliberately no ``get_entries(scope=...)`` — a scope that arrives
from a request can be forged, whereas a function that takes a resolved
workspace cannot.
"""

# Python imports

# Django imports
from django.db.models import QuerySet

# Module imports
from plane.billing.models import LedgerEntry

# Admin grants are written for internal eyes. Workspace owners see that
# credit happened, not who authorised it or why.
PUBLIC_SOURCE_LABELS = {
    LedgerEntry._meta.get_field("source").choices and "admin_grant": "اعتبار ارائه‌شده توسط مدیریت سامانه",
    "sms_charge": "هزینهٔ ارسال پیامک",
    "gateway": "شارژ آنلاین",
    "plan_purchase": "خرید پلن",
    "upgrade": "ارتقای پلن",
    "refund": "بازگشت وجه",
    "release_hold": "آزادسازی وجه",
}

INTERNAL_SOURCES = {"admin_grant"}


def workspace_entries(workspace) -> QuerySet[LedgerEntry]:
    """Every entry belonging to one workspace. The only filter is the workspace itself."""
    return (
        LedgerEntry.objects.filter(workspace=workspace)
        .select_related("debit_account", "credit_account")
        .order_by("-created_at", "-id")
    )


def all_entries() -> QuerySet[LedgerEntry]:
    """Every entry in the instance. Instance administrators only."""
    return (
        LedgerEntry.objects.all()
        .select_related("debit_account", "credit_account", "created_by", "workspace")
        .order_by("-created_at", "-id")
    )


def public_description(entry: LedgerEntry) -> str:
    """A description safe to show a workspace admin."""
    if entry.source in INTERNAL_SOURCES:
        return PUBLIC_SOURCE_LABELS.get(entry.source, "")
    return entry.description or PUBLIC_SOURCE_LABELS.get(entry.source, "")
```

**Note on `PUBLIC_SOURCE_LABELS`:** the first key in the dict literal above is written awkwardly. Replace that whole dict with the clean version before running the tests:

```python
PUBLIC_SOURCE_LABELS = {
    "admin_grant": "اعتبار ارائه‌شده توسط مدیریت سامانه",
    "sms_charge": "هزینهٔ ارسال پیامک",
    "gateway": "شارژ آنلاین",
    "plan_purchase": "خرید پلن",
    "upgrade": "ارتقای پلن",
    "refund": "بازگشت وجه",
    "release_hold": "آزادسازی وجه",
}
```

- [ ] **Step 4: Append the serializers**

Append to `apps/api/plane/billing/api/serializers.py`:

```python
class AdminLedgerEntrySerializer(serializers.ModelSerializer):
    """Full ledger entry for an instance administrator."""

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
    workspace cannot infer anything about another customer's billing,
    and replaces the internal grant description with a public label.
    """

    source_label = serializers.SerializerMethodField()
    description = serializers.SerializerMethodField()

    class Meta:
        model = LedgerEntry
        fields = ["id", "amount_toman", "source", "source_label", "description", "created_at"]
        read_only_fields = fields

    def get_source_label(self, obj):
        return obj.get_source_display()

    def get_description(self, obj):
        return ledger_service.public_description(obj)


class WalletSerializer(serializers.ModelSerializer):
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


class WalletGrantSerializer(serializers.Serializer):
    """Input for an instance admin crediting a workspace by hand."""

    amount_toman = serializers.IntegerField(min_value=1)
    description = serializers.CharField(min_length=10)

    def validate_description(self, value: str) -> str:
        stripped = value.strip()
        if len(stripped) < 10:
            raise serializers.ValidationError("توضیح اعتبار دستی باید حداقل ۱۰ کاراکتر باشد.")
        return stripped
```

Add these imports to the top of `serializers.py`:

```python
# Module imports
from plane.billing.models import LedgerEntry, Wallet
from plane.billing.services import ledger as ledger_service
from plane.billing.services import money as money_service
```

- [ ] **Step 5: Run test to verify it passes**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_ledger_security.py -v
```

Expected: 5 passed

- [ ] **Step 6: Commit**

```bash
git add apps/api/plane/billing/services/ledger.py apps/api/plane/billing/api/serializers.py apps/api/plane/billing/tests/test_ledger_security.py
git commit -m "feat(billing): scope ledger reads by function, not by parameter

workspace_entries takes a resolved workspace and applies no other filter,
so there is no query parameter that can widen it. The workspace
projection drops created_by, the invoice link and the account codes, and
replaces an admin grant's internal description with a public label."
```

---

## Task 6: The four wallet endpoints

**Files:**

- Create: `apps/api/plane/billing/api/views/wallet_views.py`
- Modify: `apps/api/plane/billing/api/views/__init__.py`
- Modify: `apps/api/plane/billing/api/urls.py`
- Test: `apps/api/plane/billing/tests/test_ledger_security.py` (append)

**Interfaces:**

- Consumes: `ledger.workspace_entries`, `ledger.all_entries`, `WalletSerializer`, `WalletGrantSerializer`, `WorkspaceBillingLedgerPermission`, `wallet.grant_from_admin`, `wallet.revoke_grant`, `money.wallet_balance`
- Produces four endpoints:
  - `GET /api/billing/admin/workspaces/<slug>/wallet/` → `WalletSerializer`
  - `POST /api/billing/admin/workspaces/<slug>/wallet/grant/` → created entry, `201`
  - `GET /api/billing/workspaces/<slug>/billing/ledger/` → paginated workspace projection
  - `GET /api/billing/workspaces/<slug>/billing/wallet/` → workspace wallet projection

- [ ] **Step 1: Write the failing endpoint tests**

Append to `apps/api/plane/billing/tests/test_ledger_security.py`:

```python
# Local imports
from plane.db.models import Workspace, WorkspaceMember


@pytest.fixture
def member_and_admin_roles(db, django_user_model, funded_workspace):
    ws, instance_admin = funded_workspace

    plain = django_user_model.objects.create_user(email="plain@example.com", username="plain", password="password1234")
    ws_admin = django_user_model.objects.create_user(email="wsadmin@example.com", username="wsadmin", password="password1234")
    WorkspaceMember.objects.create(workspace=ws, member=plain, role=15, is_active=True)
    WorkspaceMember.objects.create(workspace=ws, member=ws_admin, role=20, is_active=True)
    return ws, plain, ws_admin, instance_admin


def test_role_15_member_is_refused_the_workspace_ledger(client, member_and_admin_roles):
    ws, plain, _ws_admin, _instance_admin = member_and_admin_roles
    client.force_login(plain)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/")

    assert response.status_code == 403, response.content


def test_role_20_admin_can_read_the_workspace_ledger(client, member_and_admin_roles):
    ws, _plain, ws_admin, _instance_admin = member_and_admin_roles
    client.force_login(ws_admin)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/")

    assert response.status_code == 200, response.content
    rows = response.json()["results"]
    assert rows and rows[0]["amount_toman"] == 400_000


def test_admin_of_another_workspace_is_refused(client, member_and_admin_roles, db, django_user_model):
    ws, _plain, _ws_admin, _instance_admin = member_and_admin_roles
    other = Workspace.objects.create(name="بیگانه", slug="stranger-team")
    stranger_admin = django_user_model.objects.create_user(email="stranger@example.com", username="stranger", password="password1234")
    WorkspaceMember.objects.create(workspace=other, member=stranger_admin, role=20, is_active=True)
    client.force_login(stranger_admin)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/")

    assert response.status_code == 403, response.content


@pytest.mark.parametrize("probe", ["scope", "workspace", "workspace_slug", "slug", "all"])
def test_query_parameters_cannot_widen_the_scope(client, member_and_admin_roles, db, django_user_model, probe):
    """A forged scope parameter must not add a single foreign row."""
    ws, _plain, ws_admin, _instance_admin = member_and_admin_roles

    # A second workspace with a distinctive amount, so any leak is visible.
    other = Workspace.objects.create(name="دیگر", slug=f"probe-{probe}-team")
    other_admin = django_user_model.objects.create_user(
        email=f"probe-{probe}@example.com", username=f"probe-{probe}", password="password1234"
    )
    Wallet.objects.get_or_create(workspace=other)
    wallet.grant_from_admin(
        workspace=other,
        amount_toman=777_000,
        description="اعتبار تیم دیگر که نباید دیده شود",
        created_by=other_admin,
        idempotency_key=f"probe-{probe}-grant",
    )
    client.force_login(ws_admin)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/", {probe: "all"})

    assert response.status_code == 200, response.content
    # The other workspace's row must be absent, by id and by its distinctive amount.
    other_ids = set(LedgerEntry.objects.filter(workspace=other).values_list("id", flat=True))
    returned_ids = {row["id"] for row in response.json()["results"]}
    assert returned_ids.isdisjoint(other_ids), f"{probe} leaked another workspace's row"
    assert "777000" not in response.content.decode()
    assert other.slug not in response.content.decode()


def test_workspace_ledger_response_omits_internal_columns(client, member_and_admin_roles):
    ws, _plain, ws_admin, _instance_admin = member_and_admin_roles
    client.force_login(ws_admin)

    response = client.get(f"/api/billing/workspaces/{ws.slug}/billing/ledger/")

    body = response.content.decode()
    assert "created_by" not in body
    assert "محرمانه" not in body


def test_workspace_member_cannot_grant_themselves_credit(client, member_and_admin_roles):
    ws, ws_admin, _unused, _instance_admin = member_and_admin_roles
    client.force_login(ws_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 5_000_000, "description": "دور زدن سیستم با دسترسی مدیر ورک‌اسپیس"},
        content_type="application/json",
    )

    assert response.status_code in (401, 403), response.content


def test_instance_admin_can_grant_and_the_actor_comes_from_the_session(client, member_and_admin_roles):
    ws, _plain, _ws_admin, instance_admin = member_and_admin_roles
    client.force_login(instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 250_000, "description": "اعتبار هدیهٔ آزمایشی برای تیم"},
        content_type="application/json",
    )

    assert response.status_code == 201, response.content
    entry = LedgerEntry.objects.get(idempotency_key="api-grant-1")
    assert entry.created_by_id == instance_admin.pk
    assert money.wallet_balance(ws) == 650_000


def test_instance_admin_grant_rejects_a_short_description(client, member_and_admin_roles):
    ws, _plain, _ws_admin, instance_admin = member_and_admin_roles
    client.force_login(instance_admin)

    response = client.post(
        f"/api/billing/admin/workspaces/{ws.slug}/wallet/grant/",
        {"amount_toman": 250_000, "description": "کم"},
        content_type="application/json",
    )

    assert response.status_code == 400, response.content


def test_instance_admin_sees_the_internal_description(client, member_and_admin_roles):
    ws, _plain, _ws_admin, instance_admin = member_and_admin_roles
    client.force_login(instance_admin)

    response = client.get(f"/api/billing/admin/workspaces/{ws.slug}/wallet/ledger/")

    assert response.status_code == 200, response.content
    assert "محرمانه" in response.content.decode()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_ledger_security.py -v
```

Expected: 404 responses, `assert response.status_code == 403` fails with 404

- [ ] **Step 3: Create the views**

Create `apps/api/plane/billing/api/views/wallet_views.py`:

```python
# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Wallet reads and instance-admin grants.

Two families of endpoint live here and they are kept apart on purpose:

- the ``admin/`` family is guarded by InstanceAdminPermission and may
  read the whole instance's ledger;
- the workspace family is guarded by WorkspaceBillingLedgerPermission,
  resolves its workspace from the URL only, and serialises with the
  narrower projection.

Neither accepts a workspace or scope from the query string.
"""

# Python imports
import uuid

# Third party imports
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

# Django imports
# Module imports
from plane.billing.api.permissions import WorkspaceBillingLedgerPermission
from plane.billing.api.serializers import (
    AdminLedgerEntrySerializer,
    WalletGrantSerializer,
    WalletSerializer,
    WorkspaceLedgerEntrySerializer,
)
from plane.billing.api.views.admin_views import BillingAdminAPIView
from plane.billing.models import Wallet
from plane.billing.services import ledger, money, wallet as wallet_service
from plane.license.permissions import InstanceAdminPermission
from plane.utils.exception import CustomException

# One pagination size for both ledger views so the two responses have the
# same envelope and a client can reuse its parsing.
LEDGER_PAGE_SIZE = 50


class WorkspaceContextMixin:
    """Resolves the workspace from the URL and nothing else.

    ``workspace_slug`` is also what the permission classes read, so the
    object that was authorised and the object being served cannot differ.
    """

    def get_workspace(self):
        slug = self.kwargs["slug"]
        queryset = self.workspace_queryset()
        workspace = queryset.filter(slug=slug).first()
        if workspace is None:
            raise CustomException("ورک‌اسپیس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)
        return workspace

    def workspace_queryset(self):
        from plane.db.models import Workspace

        return Workspace.objects.all()


class AdminWorkspaceWalletView(BillingAdminAPIView):
    """The wallet of one workspace, for an instance administrator."""

    def get(self, request, slug):
        from plane.db.models import Workspace

        workspace = Workspace.objects.filter(slug=slug).first()
        if workspace is None:
            raise CustomException("ورک‌اسپیس یافت نشد.", status_code=status.HTTP_404_NOT_FOUND)

        wallet_row, _created = Wallet.objects.get_or_create(workspace=workspace)
        return Response(WalletSerializer(wallet_row).data)


class AdminWorkspaceGrantView(WorkspaceContextMixin, APIView):
    """Credit a workspace wallet by hand.

    The actor is taken from the request user, so a caller cannot name a
    different administrator in the body.
    """

    permission_classes = [InstanceAdminPermission]

    def post(self, request, slug):
        workspace = self.get_workspace()
        serializer = WalletGrantSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        idempotency_key = request.headers.get("Idempotency-Key") or f"api-grant:{uuid.uuid4()}"
        try:
            entry = wallet_service.grant_from_admin(
                workspace=workspace,
                amount_toman=data["amount_toman"],
                description=data["description"],
                created_by=request.user,
                idempotency_key=idempotency_key,
            )
        except wallet_service.WalletError as error:
            return Response({"error": error.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AdminLedgerEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class AdminWorkspaceLedgerView(WorkspaceContextMixin, BillingAdminAPIView):
    """The full ledger of one workspace, for an instance administrator."""

    def get(self, request, slug):
        workspace = self.get_workspace()
        queryset = ledger.workspace_entries(workspace)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(AdminLedgerEntrySerializer(page, many=True).data)


class WorkspaceLedgerView(WorkspaceContextMixin, APIView):
    """A workspace admin reading their own money."""

    permission_classes = [WorkspaceBillingLedgerPermission]

    def get(self, request, slug):
        workspace = self.get_workspace()
        queryset = ledger.workspace_entries(workspace)

        cursor = request.GET.get("cursor")
        if cursor:
            queryset = queryset.filter(id__lt=cursor)

        rows = list(queryset[:LEDGER_PAGE_SIZE])
        serializer = WorkspaceLedgerEntrySerializer(rows, many=True)
        next_cursor = str(rows[-1].id) if len(rows) == LEDGER_PAGE_SIZE and rows else None
        return Response({"results": serializer.data, "next_cursor": next_cursor})


class WorkspaceWalletView(WorkspaceContextMixin, APIView):
    """A workspace admin reading their own balance and held amount."""

    permission_classes = [WorkspaceBillingLedgerPermission]

    def get(self, request, slug):
        workspace = self.get_workspace()
        wallet_row, _created = Wallet.objects.get_or_create(workspace=workspace)
        return Response(WalletSerializer(wallet_row).data)
```

- [ ] **Step 4: Export the views**

Read `apps/api/plane/billing/api/views/__init__.py` and append:

```python
from plane.billing.api.views.wallet_views import (
    AdminWorkspaceGrantView,
    AdminWorkspaceLedgerView,
    AdminWorkspaceWalletView,
    WorkspaceLedgerView,
    WorkspaceWalletView,
)
```

- [ ] **Step 5: Route them**

Read `apps/api/plane/billing/api/urls.py` and append inside the `urlpatterns` list, after the existing workspace billing routes (line 96):

```python
    # Instance admin wallet management
    path(
        "admin/workspaces/<str:slug>/wallet/",
        AdminWorkspaceWalletView.as_view(),
        name="admin-workspace-wallet",
    ),
    path(
        "admin/workspaces/<str:slug>/wallet/ledger/",
        AdminWorkspaceLedgerView.as_view(),
        name="admin-workspace-ledger",
    ),
    path(
        "admin/workspaces/<str:slug>/wallet/grant/",
        AdminWorkspaceGrantView.as_view(),
        name="admin-workspace-wallet-grant",
    ),
    # Workspace scoped wallet reads, guarded by the role 20 permission
    path(
        "workspaces/<str:slug>/billing/ledger/",
        WorkspaceLedgerView.as_view(),
        name="workspace-billing-ledger",
    ),
    path(
        "workspaces/<str:slug>/billing/wallet/",
        WorkspaceWalletView.as_view(),
        name="workspace-billing-wallet",
    ),
```

Add the imports at the top of `apps/api/plane/billing/api/urls.py`:

```python
from plane.billing.api.views.wallet_views import (
    AdminWorkspaceGrantView,
    AdminWorkspaceLedgerView,
    AdminWorkspaceWalletView,
    WorkspaceLedgerView,
    WorkspaceWalletView,
)
```

- [ ] **Step 6: Run test to verify it passes**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_ledger_security.py -v
```

Expected: 16 passed

- [ ] **Step 7: Run the whole billing suite for regressions**

Run:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing -v
```

Expected: all passed, no failures. In particular `test_api_views.py::test_admin_endpoints_reject_a_plain_user` must still pass — if a new URL accidentally sits outside `InstanceAdminPermission`, that test is your canary.

- [ ] **Step 8: Commit**

```bash
git add apps/api/plane/billing/api/views/wallet_views.py apps/api/plane/billing/api/views/__init__.py apps/api/plane/billing/api/urls.py apps/api/plane/billing/tests/test_ledger_security.py
git commit -m "feat(billing): add wallet and ledger endpoints

Four endpoints split into two families. The workspace family resolves
its workspace from the URL only, so no query parameter can widen it, and
its tests cover a role 15 member, an admin of another workspace, and
four different attempts to smuggle a scope through the query string."
```

---

## Task 7: Full verification

**Files:**

- No code changes unless a check fails.

**Interfaces:**

- Consumes: everything from Tasks 1-6

- [ ] **Step 1: Run the full billing test suite**

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing -v
```

Expected: all passed

- [ ] **Step 2: Check for missing migrations**

```bash
docker compose -f docker-compose-test.yml run --rm api-tests python manage.py makemigrations --check --dry-run
```

Expected: `No changes detected`

- [ ] **Step 3: Lint the new code**

```bash
docker compose -f docker-compose-test.yml run --rm api-tests ruff check plane/billing
```

Expected: no errors. If `ruff` is not the project's linter, check `apps/api/pyproject.toml` for the configured one.

- [ ] **Step 4: Verify the ledger balances across every workspace**

Add this as a permanent test in `test_money.py` — a wallet's balance must always be derivable and never silently negative:

```python
def test_every_workspace_balance_is_derivable_and_non_negative():
    from plane.billing.models import LedgerAccountKind

    for account in LedgerAccount.objects.filter(kind=LedgerAccountKind.ASSET, workspace__isnull=False):
        assert money.account_balance(account, workspace=account.workspace) >= 0, account.code

    for workspace in Workspace.objects.filter(billing_wallet__isnull=False):
        assert money.wallet_balance(workspace) >= 0, workspace.slug
```

Run it:

```bash
docker compose -f docker-compose-test.yml run --rm --no-deps --pull never api-tests pytest plane/billing/tests/test_money.py::test_every_workspace_balance_is_derivable_and_non_negative -v
```

Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add apps/api/plane/billing/tests/test_money.py
git commit -m "test(billing): assert every wallet balance stays derivable

Guards the invariant that the whole design rests on: a balance is always
the sum of entries, never a stored number."
```

---

## Notes for the implementer

**Phase 2 starts here and is not in this plan.** The next plan covers the instance-admin workspace detail page, the feature-flag catalogue in the plan form, the `FeatureFlag.limit_type` model change, the TypeScript types, and the `AGENTS.md` rule. Phase 1 deliberately stops at the ledger and wallet because the admin UI should not be built against a ledger whose invariants are still moving.

**Two things not to do.** Do not add a `balance` field to `Wallet` when an endpoint needs a balance — call `money.wallet_balance`. Do not reuse `WorkSpaceAdminPermission` on a new financial view; the reason is pinned by a test in Task 3 and will fail loudly if someone changes it.
