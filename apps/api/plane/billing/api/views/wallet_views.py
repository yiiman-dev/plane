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
"""

# Python imports
import uuid

# Django imports
from django.utils import timezone

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
from plane.billing.models import LedgerEntry, Wallet
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


def handle_wallet_error(error: Exception) -> Response:
    """Map one wallet policy failure onto its HTTP status.

    Deliberately mapped, not collapsed onto the base class. ``WalletError``
    itself is the cross-tenant refusal (a bare raise with no subclass), and
    reporting that as a 400 would tell the caller to fix its input when the
    real answer is "that is not yours". 403 says exactly that without
    confirming whether the foreign row exists.
    """
    if isinstance(error, WALLET_ERROR_BAD_REQUEST):
        return Response({"error": error.message}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(error, WALLET_ERROR_CONFLICT):
        return Response({"error": error.message}, status=status.HTTP_409_CONFLICT)
    # ``ValueError`` here is only ever ``money._assert_same_movement``: the
    # idempotency key was reused for a different movement. That is a conflict
    # with existing state, not a server fault, and letting it reach DRF's
    # handler would turn a client mistake into a 500.
    if isinstance(error, ValueError):
        return Response(
            {"error": "کلید یکتایی تراکنش قبلاً برای تراکنش دیگری استفاده شده است."},
            status=status.HTTP_409_CONFLICT,
        )
    # Anything left is a bare ``WalletError`` or a subclass added later.
    # Unknown policy errors are treated as the refusal they most likely are.
    return Response({"error": str(error)}, status=status.HTTP_403_FORBIDDEN)


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

        idempotency_key = self.resolve_idempotency_key(request)
        # Taken BEFORE the call, not queried after: the service returns the
        # entry either way, and whether it is the row this request created is
        # answered by comparing timestamps. A lookup here would be a second
        # opinion on the same question.
        started_at = timezone.now()
        try:
            entry = wallet_service.grant_from_admin(
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

        # A replay returned the entry that was already on file, so 200. The
        # test is on ``created_at`` rather than on a flag, because that is
        # the only difference between the two outcomes the service leaves
        # behind.
        replayed = entry.created_at is not None and entry.created_at < started_at
        return Response(
            AdminLedgerEntrySerializer(entry).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )

    @staticmethod
    def resolve_idempotency_key(request) -> str:
        """The client's retry key if it sent one, otherwise one minted here.

        The header is the only place a client may influence this. A body
        field named ``idempotency_key`` is not read: naming the key is naming
        a row in a globally unique column, and a client that could choose it
        could probe for another workspace's movements.
        """
        supplied = request.headers.get("Idempotency-Key")
        if supplied and supplied.strip():
            return supplied.strip()
        return f"api-grant:{uuid.uuid4()}"


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

        started_at = timezone.now()
        try:
            reversal = wallet_service.revoke_grant(
                workspace=workspace,
                entry=entry,
                description=serializer.validated_data["description"],
                created_by=request.user,
                idempotency_key=AdminWorkspaceGrantView.resolve_idempotency_key(request),
            )
        except LedgerEntry.DoesNotExist:
            return Response({"error": "تراکنش یافت نشد."}, status=status.HTTP_404_NOT_FOUND)
        except (wallet_service.WalletError, ValueError) as error:
            return handle_wallet_error(error)

        replayed = reversal.created_at is not None and reversal.created_at < started_at
        return Response(
            AdminLedgerEntrySerializer(reversal).data,
            status=status.HTTP_200_OK if replayed else status.HTTP_201_CREATED,
        )
