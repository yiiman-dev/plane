# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Server side enforcement for work item (``Issue``) title editing.

Only workspace / project admins are allowed to rename an existing work item.
Every other field keeps its existing permission rules, and creating a work
item with a title stays open to all members, so the restriction only ever
applies to ``name`` on an update request.

The helpers live outside the views so every endpoint that can write
``Issue.name`` shares one role check and one error contract.
"""

from plane.db.models import ProjectMember, WorkspaceMember
from plane.utils.error_codes import ERROR_CODES
from plane.utils.permissions.base import ROLE


def is_project_admin(user, slug, project_id) -> bool:
    """Return whether ``user`` administers ``project_id`` in ``slug``.

    Mirrors the role resolution of ``allow_permission``: a project admin, or a
    workspace admin who is a member of the project, is treated as an admin.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return False

    if not slug or not project_id:
        return False

    is_project_admin_member = ProjectMember.objects.filter(
        member=user,
        workspace__slug=slug,
        project_id=project_id,
        role=ROLE.ADMIN.value,
        is_active=True,
    ).exists()
    if is_project_admin_member:
        return True

    is_workspace_admin_member = WorkspaceMember.objects.filter(
        member=user,
        workspace__slug=slug,
        role=ROLE.ADMIN.value,
        is_active=True,
    ).exists()

    return is_workspace_admin_member


def can_edit_issue_name(user, slug, project_id) -> bool:
    """Return whether ``user`` may change the title of an existing work item."""
    return is_project_admin(user, slug, project_id)


def get_issue_name_edit_error(user, slug, project_id, request_data, current_name=None):
    """Return an error payload when the request tries to rename a work item.

    Returns ``None`` when the request is allowed: it either does not touch
    ``name`` at all, or the sender is an admin, or the title is sent unchanged
    (a no-op round trip of the current value).
    """
    if request_data is None or "name" not in request_data:
        return None

    requested_name = request_data.get("name")
    if requested_name is None:
        return None

    if current_name is not None and requested_name == current_name:
        return None

    if can_edit_issue_name(user, slug, project_id):
        return None

    return {
        "error_code": ERROR_CODES["ISSUE_NAME_EDIT_NOT_ALLOWED"],
        "error_message": "ISSUE_NAME_EDIT_NOT_ALLOWED",
        "error_detail": "Only workspace or project admins can change the title of a work item.",
    }