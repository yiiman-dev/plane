# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Shared, dependency-free building blocks for the billing view modules.

Lives in its own module rather than in ``wallet_views`` for an import reason,
not an aesthetic one: ``wallet_views`` imports ``BillingAdminAPIView`` from
``admin_views``, so an ``admin_views`` that imported ``WorkspaceContextMixin``
back out of ``wallet_views`` would close a cycle. Whichever of the two modules
Django happened to import first would then fail with a partially-initialised
module error. A mixin that both admin and workspace views need has to sit
below both of them.

Nothing here imports another view module, so this module is safe to import from
either side of that boundary.
"""

# Module imports
from plane.db.models import Workspace

WORKSPACE_NOT_FOUND = {"error": "ورک‌اسپیس یافت نشد."}


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
