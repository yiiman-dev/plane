# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Reading the ledger.

Scope is decided by which function a caller picks, never by a parameter.
There is deliberately no ``get_entries(scope=...)`` -- a scope that arrives
from a request can be forged, whereas a function that takes a resolved
workspace cannot. The permission class (``WorkspaceBillingLedgerPermission``)
decides WHO may ask; the two projections decide WHAT comes back, because a
permission class cannot tell an instance administrator's view apart from a
workspace administrator's.

Nothing in this module writes. A caller that can reach ``LedgerEntry.objects``
can already reach the unfiltered manager, so the value here is that the safe
read is the one that is easiest to spell correctly at a call site.
"""

# Python imports

# Django imports
from django.db.models import QuerySet

# Module imports
from plane.billing.models import LedgerEntry, LedgerSource

# Admin grants are written for internal eyes. Workspace owners see that
# credit happened, not who authorised it or why.
#
# These are the tenant facing labels, and they are keyed by the raw value
# rather than derived from ``get_source_display()``: ``LedgerSource`` labels
# are English internal vocabulary ("Admin grant"), and a statement shown to a
# Persian speaking workspace admin should read as one. The trade is that a
# source added to ``LedgerSource`` later needs a line here, which is why
# ``test_public_source_label_covers_every_source`` fails until it gets one --
# an unmapped source is a bug that is caught, not a raw enum member that
# silently ships.
PUBLIC_SOURCE_LABELS = {
    LedgerSource.ADMIN_GRANT: "اعتبار ارائه‌شده توسط مدیریت سامانه",
    LedgerSource.SMS_CHARGE: "هزینهٔ ارسال پیامک",
    LedgerSource.GATEWAY: "شارژ آنلاین",
    LedgerSource.PLAN_PURCHASE: "خرید پلن",
    LedgerSource.UPGRADE: "ارتقای پلن",
    LedgerSource.REFUND: "بازگشت وجه",
    LedgerSource.RELEASE_HOLD: "آزادسازی وجه",
    LedgerSource.HOLD: "وجه قفل‌شده",
    LedgerSource.GRANT_REVERSAL: "ابطال اعتبار توسط مدیریت سامانه",
}

# Sources whose ``description`` is written by an operator for another operator.
# ``grant_from_admin`` requires free text ("why did you hand this company
# money?") and that text is not the workspace's business; naming it can leak
# another customer's situation, an internal margin discussion, or the fact that
# a grant was compensation for a failure nobody outside should hear about.
#
# ``GRANT_REVERSAL`` is here for the same reason and it is the reason this is a
# separate ``LedgerSource`` at all rather than a redaction rule on ``REFUND``.
# ``revoke_grant`` also takes operator free text ("why are you taking this
# back?"), and while it was booked under ``REFUND`` that note went straight to
# the workspace admin's statement -- the leak this whole module exists to
# prevent. Adding ``REFUND`` here instead would have fixed it by breaking
# ``refund_to_spendable``, whose description carries the payment reference the
# PAYER is entitled to. Two sources, two audiences.
#
# Deliberately a list, and deliberately short. Every OTHER source describes a
# movement the workspace itself caused or is owed an answer about: an SMS
# charge names its own notification log, and a hold description is the
# explanation the owner is entitled to. Redacting those as well would trade a
# real disclosure problem for a real transparency one.
INTERNAL_SOURCES = frozenset({LedgerSource.ADMIN_GRANT, LedgerSource.GRANT_REVERSAL})


def workspace_entries(workspace, *, source: str | None = None) -> QuerySet[LedgerEntry]:
    """Every entry belonging to one workspace. The only tenant filter is the workspace itself.

    ``workspace`` is a resolved model instance, not a slug or a pk from a
    request body, so a caller cannot point this at a tenant it was not
    authorised for -- by the time it is called the question has already been
    answered by the permission class.

    ``source`` narrows to one kind of movement for the tenant's own
    statement. It takes a raw ``LedgerSource`` member because the tenant
    projection deliberately does not expose the member itself (see
    ``WorkspaceLedgerEntrySerializer``); a tenant that wants to filter by
    "پیامک" sends the label it was shown, which
    ``resolve_public_source`` maps back. It can never widen the result set,
    only narrow it, because the workspace filter is applied regardless.

    ``select_related`` on both legs because every projection of an entry
    reads them; without it a statement of N entries costs 3N queries.
    """
    queryset = LedgerEntry.objects.filter(workspace=workspace)
    resolved = resolve_public_source(source)
    if resolved is not None:
        queryset = queryset.filter(source=resolved)
    return queryset.select_related("debit_account", "credit_account").order_by("-created_at", "-id")


def resolve_public_source(label_or_member: str | None) -> str | None:
    """Map a Persian label a tenant was shown back to its LedgerSource member.

    Returns ``None`` for an unrecognised value rather than guessing: the
    caller treats that as "no filter", which shows more of the tenant's own
    statement rather than someone else's.
    """
    if not label_or_member:
        return None
    if label_or_member in PUBLIC_SOURCE_LABELS:
        return label_or_member
    for member, label in PUBLIC_SOURCE_LABELS.items():
        if label == label_or_member:
            return member
    if label_or_member in dict(LedgerSource.choices):
        return label_or_member
    return None


def all_entries() -> QuerySet[LedgerEntry]:
    """Every entry in the instance. Instance administrators only.

    Separate from ``workspace_entries`` on purpose, so that the cross tenant
    read is visible at every call site as a differently named function rather
    than as a flag someone can pass.
    """
    return (
        LedgerEntry.objects.all()
        .select_related("debit_account", "credit_account", "created_by", "workspace")
        .order_by("-created_at", "-id")
    )


def public_description(entry: LedgerEntry) -> str:
    """A description safe to show a workspace admin."""
    if entry.source in INTERNAL_SOURCES:
        return PUBLIC_SOURCE_LABELS.get(entry.source, "")
    # An entry with no description still gets its label, so the projection
    # never renders a blank row where a statement should say what happened.
    return entry.description or PUBLIC_SOURCE_LABELS.get(entry.source, "")


def public_source_label(entry: LedgerEntry) -> str:
    """The tenant facing name of an entry's source.

    Falls back to ``get_source_display()`` for a source this module has no
    Persian label for. That fallback is English rather than a raw enum member,
    which keeps the "no machine values" property true even in the case the
    label map has not caught up with.
    """
    return PUBLIC_SOURCE_LABELS.get(entry.source) or entry.get_source_display()
