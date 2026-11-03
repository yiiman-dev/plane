# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Which requests read the instance admin cookie and which read the user cookie.

The god-mode billing API is instance-admin only, so it has to read the admin
cookie. A workspace route is a user route and must keep the user cookie, or a
member's session would be read as an admin's.
"""

# Module imports
from plane.authentication.middleware.session import is_admin_path


def test_billing_admin_paths_read_the_admin_session():
    assert is_admin_path("/api/billing/admin/transactions/queued/")
    assert is_admin_path("/api/billing/admin/gateways/")


def test_instance_admin_paths_keep_reading_the_admin_session():
    assert is_admin_path("/api/instances/admins/me/")


def test_workspace_and_public_billing_paths_keep_the_user_session():
    assert not is_admin_path("/api/billing/workspaces/acme/billing/wallet/")
    assert not is_admin_path("/api/billing/orders/")
    assert not is_admin_path("/api/billing/plans/")
