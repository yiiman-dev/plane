# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Permissions for financial data."""

# Python imports

# Third party imports
from rest_framework.permissions import BasePermission

# Django imports

# Module imports
from plane.app.permissions.base import ROLE
from plane.db.models.workspace import WorkspaceMember


class WorkspaceBillingLedgerPermission(BasePermission):
    """Access to a workspace's own money, for workspace admins only.

    "Workspace admin" here means exactly one thing: an **active
    ``WorkspaceMember`` row with ``role=ROLE.ADMIN`` (20)** on the workspace
    in question. It does **not** mean ``Workspace.owner``. Ownership is a
    separate foreign key, and it is not consulted here — a user who owns the
    workspace but has no active role-20 membership row is **denied**, the same
    as ``WorkspaceOwnerPermission`` does.

    ``WorkSpaceAdminPermission`` is not reused on purpose: it accepts
    ``role__in=[Admin, Member]``, so it also lets ordinary members
    through. A ledger shows how much a company spends and how much an
    instance administrator granted it, which no ordinary member may see.

    This class gates on role only, not on ``request.method``. The read-only
    intent of the ledger endpoints is enforced by the views (GET-only
    routes), not here, so do not rely on this permission to block writes.
    """

    message = "این بخش تنها برای مدیران ورک‌اسپیس در دسترس است."

    def has_permission(self, request, view) -> bool:
        if request.user is None or request.user.is_anonymous:
            return False

        workspace_slug = getattr(view, "workspace_slug", None)
        if not workspace_slug:
            return False

        return WorkspaceMember.objects.filter(
            member=request.user,
            workspace__slug=workspace_slug,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()
