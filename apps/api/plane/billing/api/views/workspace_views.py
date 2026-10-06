# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third part imports
from rest_framework import status
from rest_framework.response import Response

# Module imports
from plane.app.permissions.workspace import (
    WorkspaceMemberPermission,
    WorkSpaceAdminPermission,
)
from plane.billing.models import FeatureFlag, WorkspaceFeatureFlag
from plane.billing.services.entitlements import (
    FEATURE_NOT_IN_PLAN_CODE,
    FEATURE_NOT_IN_PLAN_MESSAGE,
    FEATURE_UNAVAILABLE_MESSAGE,
    FEATURE_UNKNOWN_MESSAGE,
    get_feature_flag_rows,
    get_workspace_entitlement,
    grantable_feature_codes,
)
from plane.db.models import Workspace
from plane.license.api.views.base import BaseAPIView

WORKSPACE_NOT_FOUND = {"error": "ورک‌اسپیس یافت نشد."}


class WorkspaceEntitlementBaseView(BaseAPIView):
    """Shared workspace lookup for the workspace scoped billing endpoints."""

    @property
    def workspace_slug(self):
        # WorkSpaceAdminPermission resolves the workspace from this property
        return self.kwargs.get("slug")

    @property
    def workspace(self):
        return Workspace.objects.filter(slug=self.workspace_slug).first()


class WorkspaceEntitlementEndpoint(WorkspaceEntitlementBaseView):
    """Current plan, seat budget and feature access of one workspace.

    Reading is open to every active member, no admin role needed.
    """

    permission_classes = [WorkspaceMemberPermission]

    def get(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        entitlement = get_workspace_entitlement(workspace)
        entitlement["workspace"] = {
            "id": str(workspace.id),
            "name": workspace.name,
            "slug": workspace.slug,
        }
        return Response(entitlement, status=status.HTTP_200_OK)


class WorkspaceFeatureFlagListEndpoint(WorkspaceEntitlementBaseView):
    """Feature flags with this workspace's access and activation state."""

    permission_classes = [WorkspaceMemberPermission]

    def get(self, request, slug):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)
        return Response({"results": get_feature_flag_rows(workspace)}, status=status.HTTP_200_OK)


class WorkspaceFeatureFlagEnableEndpoint(WorkspaceEntitlementBaseView):
    """Switch a capability on, which only the plan can allow."""

    permission_classes = [WorkSpaceAdminPermission]

    def post(self, request, slug, code):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        feature_flag = FeatureFlag.objects.filter(code=code).first()
        if feature_flag is None:
            return Response(
                {"error": FEATURE_UNKNOWN_MESSAGE, "code": "feature_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not feature_flag.is_active:
            return Response(
                {"error": FEATURE_UNAVAILABLE_MESSAGE, "code": "feature_unavailable"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # the plan has to grant it first, an admin cannot hand out what was not bought
        if feature_flag.code not in grantable_feature_codes(workspace):
            return Response(
                {"error": FEATURE_NOT_IN_PLAN_MESSAGE, "code": FEATURE_NOT_IN_PLAN_CODE},
                status=status.HTTP_403_FORBIDDEN,
            )

        WorkspaceFeatureFlag.objects.update_or_create(
            workspace=workspace,
            feature_flag=feature_flag,
            defaults={"is_enabled": True},
        )
        return Response(
            {"code": feature_flag.code, "is_enabled": True, "has_access": True},
            status=status.HTTP_200_OK,
        )


class WorkspaceFeatureFlagDisableEndpoint(WorkspaceEntitlementBaseView):
    """Switch a capability off for this workspace.

    The grant and the flag row survive, only this workspace stops using it.
    """

    permission_classes = [WorkSpaceAdminPermission]

    def post(self, request, slug, code):
        workspace = self.workspace
        if workspace is None:
            return Response(WORKSPACE_NOT_FOUND, status=status.HTTP_404_NOT_FOUND)

        feature_flag = FeatureFlag.objects.filter(code=code).first()
        if feature_flag is None:
            return Response(
                {"error": FEATURE_UNKNOWN_MESSAGE, "code": "feature_not_found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        WorkspaceFeatureFlag.objects.filter(workspace=workspace, feature_flag=feature_flag).update(is_enabled=False)
        return Response({"code": feature_flag.code, "is_enabled": False}, status=status.HTTP_200_OK)
