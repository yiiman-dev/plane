# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Charging a workspace wallet for outbound SMS.

Per event, because that is how SMS is actually bought: a verification code, a
mention and a comment all cost the operator money and none of them cost the same.
``Plan.sms_prices`` holds the price per channel event in Toman.

The charge is taken **before** delivery is attempted, and the order is the whole
design:

* Charge then send: if the process dies in between, the money is gone and the
  message was not delivered. That shows up as a ``failed`` log row next to a
  ledger entry -- a loss the operator can see and refund by hand.
* Send then charge: the same crash gives away a free message every time, and
  nothing in the data says it happened. Free messages are invisible, which is the
  worse failure of the two.

``wallet.charge_sms`` owns the ledger mechanics: the per-log idempotency key that
makes a redelivered log free, and the row lock that keeps two concurrent
deliveries from spending the same balance twice. This module is the decision in
front of it.
"""  # Python imports

from dataclasses import dataclass
from typing import Dict, List, Optional

# Django imports
from django.db.models import Count, Sum

# Module imports
from plane.billing.models import LedgerAccount, LedgerEntry, LedgerSource, Subscription, SubscriptionStatus
from plane.billing.services import wallet
from plane.billing.services.entitlements import resolve_workspace_plan
from plane.billing.services.money import WalletAccountCode
from plane.billing.services.wallet import InsufficientBalance
from plane.db.models import (
    NOTIFICATION_CHANNEL_SMS,
    NOTIFICATION_CHANNEL_STATUS_FAILED,
    NOTIFICATION_CHANNEL_STATUS_PENDING,
    NOTIFICATION_CHANNEL_STATUS_SENT,
    NOTIFICATION_CHANNEL_STATUS_SKIPPED,
    NotificationChannelLog,
)

# Read by the delivery task to decide what to tell the operator. A machine
# readable reason, not a sentence: this one is written into the log row.
INSUFFICIENT_BALANCE_REASON = "insufficient_wallet_balance"


@dataclass(frozen=True)
class SMSCharge:
    """What one queued message costs and what was taken for it.

    ``price_toman`` is recorded even when the message is skipped, so the delivery
    row still answers "what would this have cost" after the plan's price changes.
    """

    price_toman: int = 0
    skipped_reason: Optional[str] = None
    entry: Optional[LedgerEntry] = None

    @property
    def may_send(self) -> bool:
        return self.skipped_reason is None


def normalize_price(raw_price) -> int:
    """A stored price as a usable number of Toman, or 0 when it is not one.

    Two stored values collapse into zero, and both are deliberate: something
    that is not a number at all -- a price typed into the plan form as a string
    of digits is fine, a stray word left in the JSON blob is not -- and a
    negative number, which would move money the wrong way. ``sms_prices`` is a
    free-form JSON column, so anything can be in it, and none of it is a reason
    to refuse a delivery or to bill a wallet backwards.

    The delivery path and the operator's report both ask what a price means, so
    they ask this function rather than each carrying their own copy of the rule:
    a report that disagreed with the charge about what "free" means would be
    wrong about the money it exists to explain.
    """
    try:
        price = int(raw_price)
    except (TypeError, ValueError):
        return 0

    return price if price > 0 else 0


def price_for_event(workspace, event: str) -> int:
    """The plan's price in Toman for one channel event, or 0 when it is free.

    Four answers collapse into zero, and each is deliberate: no workspace row on
    the log, no plan, a plan with no entry for this event, or an entry that is not
    a usable number (see :func:`normalize_price`). An installation that has not
    priced anything delivers exactly as it did before this existed -- the only
    safe default for a change that puts a charge on a delivery path.
    """
    if workspace is None or not event:
        return 0

    plan = resolve_workspace_plan(workspace)
    if plan is None:
        return 0

    return normalize_price((plan.sms_prices or {}).get(event))


def charge_for_log(log) -> SMSCharge:
    """Take the price of one queued message from its workspace wallet.

    Refusal is returned rather than raised: the caller is a delivery task whose
    job is to record the outcome on the log row, and an exception here would make
    an empty wallet look like a provider failure.
    """
    price = price_for_event(getattr(log, "workspace", None), getattr(log, "event", ""))
    if price <= 0:
        return SMSCharge()

    try:
        entry = wallet.charge_sms(
            workspace=log.workspace,
            amount_toman=price,
            log_id=log.id,
            created_by=getattr(log, "triggered_by", None),
        )
    except InsufficientBalance:
        return SMSCharge(price_toman=price, skipped_reason=INSUFFICIENT_BALANCE_REASON)

    return SMSCharge(price_toman=price, entry=entry)


def workspace_cost_rows(workspaces) -> List[Dict]:
    """What each workspace was charged for SMS, next to what it was delivered.

    Three tables answer one question and none of them answers it alone. The
    ledger says what left the wallet, the delivery log says what arrived and at
    which rate it was priced at the time, and the plan says what the rate is
    *now*. A charge the report cannot explain is the one number an operator
    works from, so it is computed here rather than left to the screen.

    Four queries for the whole page whatever its size: one grouped by workspace,
    event and status for the messages, one for the wallets, one for the charges
    and one for the plans.

    The charged figure is read the way a balance is -- from the ledger side of
    the workspace's spendable account -- rather than by summing the delivery
    rows, which are the thing being audited. An account owns every entry that
    touches it, so a charge posted without a workspace on its entry still lands
    on the right wallet, and money RETURNING to the wallet is not counted as a
    charge however it was posted.
    """
    workspaces = list(workspaces)
    ids = [workspace.pk for workspace in workspaces]
    if not ids:
        return []

    # One pass over the log answers the counts, the snapshotted money and the
    # per event split: they are all the same grouping, and three queries over one
    # table would be three ways to disagree with each other.
    activity = {
        workspace_id: {
            "counts": {},
            "events": {},
            "delivered_toman": 0,
            "lost_toman": 0,
            "refused_toman": 0,
        }
        for workspace_id in ids
    }
    messages = (
        NotificationChannelLog.objects.filter(workspace_id__in=ids, channel=NOTIFICATION_CHANNEL_SMS)
        .values("workspace_id", "event", "status")
        .annotate(messages=Count("id"), snapshotted_toman=Sum("sms_price_toman"))
    )
    for row in messages:
        bucket = activity[row["workspace_id"]]
        status = row["status"]
        bucket["counts"][status] = bucket["counts"].get(status, 0) + row["messages"]

        event = bucket["events"].setdefault(row["event"], {"count": 0, "snapshotted_toman": 0})
        event["count"] += row["messages"]
        snapshotted = row["snapshotted_toman"] or 0
        event["snapshotted_toman"] += snapshotted

        # A skipped message was priced and never charged, so it is counted on
        # its own: folding it into the cost would report money that never left.
        if status == NOTIFICATION_CHANNEL_STATUS_SENT:
            bucket["delivered_toman"] += snapshotted
        elif status == NOTIFICATION_CHANNEL_STATUS_FAILED:
            bucket["lost_toman"] += snapshotted
        elif status == NOTIFICATION_CHANNEL_STATUS_SKIPPED:
            bucket["refused_toman"] += snapshotted

    # Read-only by construction: the account is looked up by code rather than
    # through ``get_or_create_wallet_accounts``, so opening the report never
    # creates a wallet for a workspace that has none. Those workspaces simply
    # have nothing charged, which is what an absent account means.
    workspace_by_account = dict(
        LedgerAccount.objects.filter(
            workspace_id__in=ids,
            code__in=[WalletAccountCode.wallet_default(workspace_id) for workspace_id in ids],
        ).values_list("id", "workspace_id")
    )
    charged_by_workspace: Dict = {}
    if workspace_by_account:
        charged_by_workspace = {
            workspace_by_account[row["credit_account_id"]]: row["total"] or 0
            for row in LedgerEntry.objects.filter(
                credit_account_id__in=list(workspace_by_account), source=LedgerSource.SMS_CHARGE
            )
            .values("credit_account_id")
            .annotate(total=Sum("amount_toman"))
        }

    plan_by_workspace = {
        row["workspace_id"]: row
        for row in Subscription.objects.filter(workspace_id__in=ids, status=SubscriptionStatus.ACTIVE).values(
            "workspace_id", "plan__code", "plan__sms_prices"
        )
    }

    rows = []
    for workspace in workspaces:
        bucket = activity[workspace.pk]
        plan_row = plan_by_workspace.get(workspace.pk) or {}
        current_prices = plan_row.get("plan__sms_prices") or {}
        charged_toman = charged_by_workspace.get(workspace.pk, 0)

        rows.append(
            {
                "workspace_id": str(workspace.pk),
                "workspace_name": workspace.name,
                "workspace_slug": workspace.slug,
                "plan_code": plan_row.get("plan__code"),
                "sent_count": bucket["counts"].get(NOTIFICATION_CHANNEL_STATUS_SENT, 0),
                "failed_count": bucket["counts"].get(NOTIFICATION_CHANNEL_STATUS_FAILED, 0),
                "skipped_count": bucket["counts"].get(NOTIFICATION_CHANNEL_STATUS_SKIPPED, 0),
                "pending_count": bucket["counts"].get(NOTIFICATION_CHANNEL_STATUS_PENDING, 0),
                "charged_toman": charged_toman,
                "delivered_toman": bucket["delivered_toman"],
                "lost_toman": bucket["lost_toman"],
                "refused_toman": bucket["refused_toman"],
                # The column the operator works from. Anything other than zero
                # is a discrepancy: positive means the wallet paid for a
                # message with no delivery row to show for it, which is exactly
                # what the charge-before-send order can leave behind.
                "unexplained_toman": charged_toman - bucket["delivered_toman"] - bucket["lost_toman"],
                # Busiest event first, ties broken by code, so the order is
                # stable across two requests for the same data.
                "events": [
                    {
                        "event": event,
                        "count": entry["count"],
                        "snapshotted_toman": entry["snapshotted_toman"],
                        # What the plan charges for this event TODAY. Shown
                        # beside the snapshot precisely because the two differ
                        # after any price change, and the snapshot is the one
                        # that describes the money already spent.
                        "current_rate_toman": normalize_price(current_prices.get(event)),
                    }
                    for event, entry in sorted(bucket["events"].items(), key=lambda item: (-item[1]["count"], item[0]))
                ],
            }
        )

    return rows
