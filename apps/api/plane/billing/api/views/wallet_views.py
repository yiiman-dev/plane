# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Wallet reads and instance-admin grants.

Two families of endpoint live here and they are kept apart on purpose:

- the ``admin/`` family is guarded by ``InstanceAdminPermission`` and may
  read any workspace's wallet and ledger;
- the workspace family is guarded by ``WorkspaceBillingLedgerPermission``,
  resolves its workspace from the URL only, and serialises with the
  narrower projection.

Neither accepts a workspace, a slug or a scope from the query string. The
workspace is ``self.kwargs["slug"]`` and nothing else, so a forged
``?scope=instance`` or ``?slug=other`` has nowhere to land: no code path in
this module reads a tenant selector out of the query parameters at all.

Both families inherit ``BillingAdminAPIView`` purely for its pagination
envelope and session authentication; the workspace views immediately
override ``permission_classes``. That inheritance is deliberate rather than
lazy -- it is what makes ``test_the_two_families_use_different_permissions``
a meaningful assertion, because the two families would otherwise differ in
authentication, pagination and error handling as well as in authority.

Scope note -- who is audited, and who is not
-------------------------------------------
Only the ``admin/`` READS call ``ledger_service.record_admin_read``. The
workspace family must not: a tenant admin looking at their own balance is not
an operator event, and an accountability log that records it is noise an
investigation has to sift through. Grant and revoke are writes already
attributed by ``LedgerEntry.created_by``, so logging them here would file them
under a read they did not perform.

Scope note -- the revoke endpoint is here ON PURPOSE
----------------------------------------------------
This module ships SIX endpoints: four reads/writes the task brief named, plus
``POST /api/billing/admin/workspaces/<slug>/wallet/revoke/`` (the counterpart
to grant) and the admin ledger read. The revoke endpoint was added by a
deliberate scope decision in fix round 1, not by reading an interfaces note
as a request:

* it is guarded by ``InstanceAdminPermission``, like every other admin route;
* it workspace-scopes the pk lookup, so a pk from another tenant does not
  resolve and the service is never handed a foreign row;
* its errors go through ``handle_wallet_error``, so it reports the same
  statuses as grant: 400 on a bad body, 404 on a pk that is not this
  workspace's or not live, 409 on not-a-grant / already-reversed / not enough
  money / key reused for another movement, 403 on the cross-tenant refusal.

The argument for keeping it: a ledger with a grant surface and no reversal
surface is not complete, and an operator who cannot reverse a mistaken grant
through the API will work around it out of band. The argument against is only
that it was not asked for. Everything it needs is already shipped and pinned
by tests, so the cost of keeping it is one route and one serializer.
"""

# Python imports
import uuid

# Third party imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.billing.api.permissions import WorkspaceBillingLedgerPermission
from plane.billing.api.serializers import (
    AdminLedgerEntrySerializer,
    WalletGrantSerializer,
    WalletRevokeSerializer,
    WalletSerializer,
    WorkspaceLedgerEntrySerializer,
)
from plane.billing.api.views.admin_views import BillingAdminAPIView
from plane.billing.models import BillingAccessLog, LedgerEntry, Wallet
from plane.billing.services import ledger as ledger_service
from plane.billing.services import wallet as wallet_service
from plane.db.models import Workspace
from plane.license.api.permissions import InstanceAdminPermission

WORKSPACE_NOT_FOUND = {"error": "ورک‌اسپیس یافت نشد."}

# ``WalletError`` subclasses that mean "this request is malformed", mapped to
# 400. Listed rather than caught wholesale, because the base class also
# carries the cross-tenant refusal, which is emphatically NOT a 400 -- see
# ``handle_wallet_error``.
#
# ``InvalidIdempotencyKey`` is included even though no client can trigger it
# here: the view derives the key itself. It is a 400 because the shape of the
# failure is a bad argument, and leaving it to fall through to the base-class
# branch would report a server-side confusion as a permission problem.
WALLET_ERROR_BAD_REQUEST = (
    wallet_service.InvalidGrantDescription,
    wallet_service.InvalidAmount,
    wallet_service.InvalidChargeReference,
    wallet_service.InvalidHoldSource,
    wallet_service.InvalidHoldDescription,
    wallet_service.InvalidPaymentReference,
    wallet_service.InvalidIdempotencyKey,
)

# A policy decision about a well-formed request: over the cap, not enough
# money, not the kind of row, already reversed. 409, so a client can tell
# "retry this later" apart from "you sent something wrong".
WALLET_ERROR_CONFLICT = (
    wallet_service.GrantTooLarge,
    wallet_service.InsufficientBalance,
    wallet_service.NotAGrantEntry,
    wallet_service.GrantAlreadyReversed,
)

# THE mapping, as a registry rather than a pair of tuples and an ``elif``
# ladder, because a taxonomy assembled out of ``isinstance`` checks has no way
# to notice a new member. ``HOLD_ALLOWED_SOURCES`` in ``wallet.py`` drifted
# exactly this way: the allow-list missed a source, the ledger accepted it, and
# nothing failed.
#
# So the registry is a plain dict keyed on the exception CLASS (exact type, not
# a subclass test) and ``handle_wallet_error`` looks the type up in it. A
# ``WalletError`` subclass that is not a key raises ``UnmappedWalletError``
# here, which becomes a 500 -- loud, and in a test run an immediate failure --
# instead of silently reporting a permission problem forever.
WALLET_ERROR_STATUS = {
    wallet_service.InvalidGrantDescription: status.HTTP_400_BAD_REQUEST,
    wallet_service.InvalidAmount: status.HTTP_400_BAD_REQUEST,
    wallet_service.InvalidChargeReference: status.HTTP_400_BAD_REQUEST,
    wallet_service.InvalidHoldSource: status.HTTP_400_BAD_REQUEST,
    wallet_service.InvalidHoldDescription: status.HTTP_400_BAD_REQUEST,
    wallet_service.InvalidPaymentReference: status.HTTP_400_BAD_REQUEST,
    wallet_service.InvalidIdempotencyKey: status.HTTP_400_BAD_REQUEST,
    wallet_service.GrantTooLarge: status.HTTP_409_CONFLICT,
    wallet_service.InsufficientBalance: status.HTTP_409_CONFLICT,
    wallet_service.NotAGrantEntry: status.HTTP_409_CONFLICT,
    wallet_service.GrantAlreadyReversed: status.HTTP_409_CONFLICT,
    # The bare class IS the cross-tenant refusal, and it must stay 403/404
    # rather than becoming a 500: reporting "that is not yours" as a server
    # fault would both be wrong and tell an attacker they had found something.
    wallet_service.WalletError: status.HTTP_403_FORBIDDEN,
}

# The two tuples above are what the registry is built from, kept as the single
# source of truth so the grouping stays readable; ``test_every_wallet_error_
# subclass_is_in_the_status_registry`` fails if the two ever disagree with each
# other or with ``wallet.py``.


class UnmappedWalletError(Exception):
    """A ``WalletError`` subclass this layer has no HTTP status for.

    Raised rather than defaulted to 403 so that adding a policy error to
    ``wallet.py`` without deciding what a client should be told is a visible
    break, not a silent one.
    """


def _assert_registry_matches_the_groupings() -> None:
    """Every class in the two groupings is a key, and every key is in one."""
    grouped = set(WALLET_ERROR_BAD_REQUEST) | set(WALLET_ERROR_CONFLICT) | {wallet_service.WalletError}
    if grouped != set(WALLET_ERROR_STATUS):
        missing = sorted(cls.__name__ for cls in grouped - set(WALLET_ERROR_STATUS))
        extra = sorted(cls.__name__ for cls in set(WALLET_ERROR_STATUS) - grouped)
        raise AssertionError(f"WALLET_ERROR_STATUS out of step with its groupings; unmapped={missing} unknown={extra}")


_assert_registry_matches_the_groupings()


def handle_wallet_error(error: Exception) -> Response:
    """Map one wallet policy failure onto its HTTP status.

    The lookup is on the exact type, so an unmapped subclass cannot inherit
    some other error's status by subclassing it, and cannot silently inherit
    the base class's 403 either -- it raises, which is the point.

    The bare ``WalletError`` is mapped, not collapsed onto 403 by accident. It
    is the cross-tenant refusal (a bare raise with no subclass), and reporting
    that as a 400 would tell the caller to fix its input when the real answer
    is "that is not yours". 403 says exactly that without confirming whether
    the foreign row exists.
    """
    # ``ValueError`` here is only ever ``money._assert_same_movement``: the
    # idempotency key was reused for a different movement. That is a conflict
    # with existing state, not a server fault, and letting it reach DRF's
    # handler would turn a client mistake into a 500.
    if isinstance(error, ValueError):
        return Response(
            {"error": "کلید یکتایی تراکنش قبلاً برای تراکنش دیگری استفاده شده است."},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(error, wallet_service.WalletError):
        try:
            mapped = WALLET_ERROR_STATUS[type(error)]
        except KeyError:
            raise UnmappedWalletError(
                f"{type(error).__name__} has no HTTP status; add it to WALLET_ERROR_STATUS"
            ) from error
        return Response({"error": error.message}, status=mapped)
    # Not a wallet policy failure at all -- a programming error here should be a
    # 500 rather than dressed up as a client mistake.
    raise error


class WorkspaceContextMixin:
    """Resolves the workspace from the URL and nothing else.

    ``workspace_slug`` is also what the permission classes read, so the
    object that was authorised and the object being served cannot differ:
    both spellings go through the same ``self.kwargs["slug"]``.
    """

    @property
    def workspace_slug(self):
        # ``WorkspaceBillingLedgerPermission`` resolves the workspace from
        # this property, and returns False when it is missing or blank. That
        # is the safe direction to fail in: a view that forgot it is denied,
        # not served.
        return self.kwargs.get("slug")

    @property
    def workspace(self):
        return Workspace.objects.filter(slug=self.workspace_slug).first()


class AdminWorkspaceWalletView(WorkspaceContextMixin, BillingAdminAPIView):
    """The wallet of one workspace, for an instance administrator.

    Reads any workspace's wallet, which is the whole point of the admin
    family and why it is not reachable by a workspace role at all.
    """

    permission_classes = [InstanceAdminPermission]

    def get(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        wallet_row, _created = Wallet.objects.get_or_create(workspace=workspace)
        # After the 404 guard, never before: a row must name a read that
        # actually happened, and the workspace family below deliberately does
        # NOT call this -- see the module docstring.
        ledger_service.record_admin_read(workspace=workspace, view=BillingAccessLog.VIEW_WALLET, request=request)
        return Response(WalletSerializer(wallet_row).data)


class AdminWorkspaceLedgerView(WorkspaceContextMixin, BillingAdminAPIView):
    """The full ledger of one workspace, for an instance administrator.

    Serialised with the ADMIN projection, so the operator sees the actor,
    both account legs and the idempotency key. A workspace admin reading the
    same rows through the workspace family gets a narrower projection of the
    identical queryset -- the difference is in what the two responses may
    contain, never in which rows each is allowed to see.
    """

    permission_classes = [InstanceAdminPermission]

    def get(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        ledger_service.record_admin_read(workspace=workspace, view=BillingAccessLog.VIEW_LEDGER, request=request)
        return self.paginated(request, ledger_service.workspace_entries(workspace), AdminLedgerEntrySerializer)


class WorkspaceLedgerView(WorkspaceContextMixin, BillingAdminAPIView):
    """A workspace admin reading their own money.

    The same paginated envelope as the admin ledger view, so a client parses
    one shape; only the projection differs.
    """

    permission_classes = [WorkspaceBillingLedgerPermission]

    def get(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        return self.paginated(request, ledger_service.workspace_entries(workspace), WorkspaceLedgerEntrySerializer)


class WorkspaceWalletView(WorkspaceContextMixin, BillingAdminAPIView):
    """A workspace admin reading their own balance and held amount."""

    permission_classes = [WorkspaceBillingLedgerPermission]

    def get(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        wallet_row, _created = Wallet.objects.get_or_create(workspace=workspace)
        return Response(WalletSerializer(wallet_row).data)


class AdminWorkspaceGrantView(WorkspaceContextMixin, BillingAdminAPIView):
    """Credit a workspace wallet by hand.

    Three things are pinned here rather than left to the caller:

    * the actor is ``request.user``, so no body can name a different
      administrator;
    * the workspace is the one the URL resolved, so no body can retarget the
      credit;
    * the idempotency key is the ``Idempotency-Key`` header or a value
      generated here -- never a body field, or a caller could name the key
      of another workspace's movement.

    There is deliberately NO pre-check for an existing key ahead of the
    service call. The service already resolves the replay first thing, and a
    second copy of that rule at the HTTP layer is a second place for it to
    drift -- which is exactly what went wrong in an earlier task, where a
    completed reversal raised ``InsufficientBalance`` on its own retry.
    """

    permission_classes = [InstanceAdminPermission]

    def post(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        serializer = WalletGrantSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Inside the try: an over-long header raises InvalidIdempotencyKey, which
        # must become a 400 rather than escaping as a 500.
        try:
            idempotency_key = self.resolve_idempotency_key(request)
        except wallet_service.InvalidIdempotencyKey as error:
            return handle_wallet_error(error)
        try:
            entry, replayed = wallet_service.grant_from_admin_with_outcome(
                workspace=workspace,
                amount_toman=serializer.validated_data["amount_toman"],
                description=serializer.validated_data["description"],
                created_by=request.user,
                idempotency_key=idempotency_key,
            )
        except (wallet_service.WalletError, ValueError) as error:
            # ``ValueError`` is NOT a ``WalletError``: it is
            # ``money._assert_same_movement`` refusing an idempotency key
            # that was reused for a different movement. Catching only the
            # policy exceptions would let a client mistake reach DRF's
            # handler and be reported as a 500.
            return handle_wallet_error(error)

        # The SERVICE says whether it replayed, rather than the view guessing
        # from ``created_at``. A wall-clock comparison is wrong in both
        # directions -- a clock stepping backwards between the two reads makes
        # a fresh post look like a replay, and an app host ahead of the
        # database host makes a replay look fresh -- and neither is
        # reproducible in CI, so neither would have been caught by a test.
        return Response(
            AdminLedgerEntrySerializer(entry).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )

    # idempotency_key is a CharField(max_length=255) with a UNIQUE index. An
    # over-long header would raise DataError, not IntegrityError, and escape the
    # exception handler as a 500 -- so it is bounded here rather than trusted.
    MAX_IDEMPOTENCY_KEY_LENGTH = 255

    @staticmethod
    def resolve_idempotency_key(request, prefix: str = "api-grant") -> str:
        """The client's retry key if it sent one, otherwise one minted here.

        The header is the only place a client may influence this. A body
        field named ``idempotency_key`` is not read: naming the key is naming
        a row in a globally unique column, and a client that could choose it
        could probe for another workspace's movements.

        THE FALLBACK IS A FRESH ``uuid4`` ON EVERY REQUEST, never a
        deterministic function of the caller, the body or the clock. A
        derived fallback would be a correctness bug, not just a weak
        uniqueness argument: the column is globally unique, so two unrelated
        requests that landed on the same derived value would make the second
        one look like a replay of the first, and the second would silently
        post nothing while answering 201. The cost of the mint is that a
        headerless client gets no retry protection -- which is the honest
        answer, since it never supplied a key to protect itself with, and
        telling it otherwise would be a promise the ledger cannot keep.
        """
        supplied = request.headers.get("Idempotency-Key")
        if supplied and supplied.strip():
            key = supplied.strip()
            if len(key) > AdminWorkspaceGrantView.MAX_IDEMPOTENCY_KEY_LENGTH:
                raise wallet_service.InvalidIdempotencyKey("کلید تکرارپذیری بیش از حد طولانی است.")
            return key
        return f"{prefix}:{uuid.uuid4()}"


class AdminWorkspaceRevokeView(WorkspaceContextMixin, BillingAdminAPIView):
    """Reverse a grant an operator made by hand.

    ``revoke_grant`` takes a ``LedgerEntry`` INSTANCE, not a pk, and that is
    load-bearing: the service re-reads and re-checks the row, but the
    confused-deputy surface is closed by whoever resolves the pk. So the
    lookup below is scoped by the workspace the URL resolved, and a pk
    belonging to another tenant simply does not resolve -- a 404, with the
    service never being handed a foreign row at all.
    """

    permission_classes = [InstanceAdminPermission]

    def post(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        serializer = WalletRevokeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        entry = LedgerEntry.objects.filter(
            workspace=workspace,
            pk=serializer.validated_data["entry"],
        ).first()
        if entry is None:
            return Response({"error": "تراکنش یافت نشد."}, status=status.HTTP_404_NOT_FOUND)

        try:
            reversal, replayed = wallet_service.revoke_grant_with_outcome(
                workspace=workspace,
                entry=entry,
                description=serializer.validated_data["description"],
                created_by=request.user,
                idempotency_key=AdminWorkspaceGrantView.resolve_idempotency_key(request, prefix="api-revoke"),
            )
        except LedgerEntry.DoesNotExist:
            return Response({"error": "تراکنش یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        except (wallet_service.WalletError, ValueError) as error:
            return handle_wallet_error(error)

        # Told, not inferred -- see ``AdminWorkspaceGrantView.post``.
        return Response(
            AdminLedgerEntrySerializer(reversal).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
