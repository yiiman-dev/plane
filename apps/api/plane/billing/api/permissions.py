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
