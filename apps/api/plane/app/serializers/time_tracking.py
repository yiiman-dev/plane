# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Third party imports
from rest_framework import serializers

# Module imports
from .base import BaseSerializer
from .user import UserLiteSerializer
from plane.db.models import ProjectTimeTrackingSetting, IssueWorklog


class ProjectTimeTrackingSettingSerializer(BaseSerializer):
    overlap_allowed_member_details = UserLiteSerializer(source="overlap_allowed_members", many=True, read_only=True)
    custom_allowed_member_details = UserLiteSerializer(source="custom_allowed_members", many=True, read_only=True)

    class Meta:
        model = ProjectTimeTrackingSetting
        fields = [
            "id",
            "project",
            "workspace",
            "is_enabled",
            "allow_overlap",
            "overlap_allowed_members",
            "overlap_allowed_member_details",
            "breaks_enabled",
            "focus_duration_minutes",
            "break_duration_minutes",
            "logging_permission",
            "custom_allowed_members",
            "custom_allowed_member_details",
            "default_view",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "project",
            "workspace",
            "created_at",
            "updated_at",
        ]


class IssueWorklogSerializer(BaseSerializer):
    user_detail = UserLiteSerializer(source="user", read_only=True)

    class Meta:
        model = IssueWorklog
        fields = [
            "id",
            "issue",
            "project",
            "workspace",
            "user",
            "user_detail",
            "start_time",
            "end_time",
            "duration_seconds",
            "is_running",
            "is_paused",
            "started_at",
            "description",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "project",
            "workspace",
            "user",
            "user_detail",
            "is_running",
            "is_paused",
            "started_at",
            "created_at",
            "updated_at",
        ]
