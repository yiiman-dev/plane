# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.conf import settings
from django.db import models

# Module imports
from .project import Project, ProjectBaseModel
from .issue import Issue


class ProjectTimeTrackingSetting(ProjectBaseModel):
    """Configuration for time tracking per project, managed by project/workspace admins."""

    LOGGING_PERMISSION_CHOICES = (
        ("all_members", "همه اعضای تیم"),
        ("assignee_only", "فقط اساینی"),
        ("custom_members", "افراد خاص"),
    )

    DEFAULT_VIEW_CHOICES = (
        ("grouped_by_date", "بر اساس تاریخ"),
        ("grouped_by_user", "بر اساس افراد"),
        ("timeline_intervals", "مقاطع زمانی"),
    )

    project = models.OneToOneField(
        Project,
        on_delete=models.CASCADE,
        related_name="time_tracking_setting",
    )
    is_enabled = models.BooleanField(default=True)
    allow_overlap = models.BooleanField(default=True)
    overlap_allowed_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="overlap_exempt_projects",
    )
    breaks_enabled = models.BooleanField(default=True)
    focus_duration_minutes = models.PositiveIntegerField(default=15)
    break_duration_minutes = models.PositiveIntegerField(default=5)
    logging_permission = models.CharField(
        max_length=32,
        default="all_members",
        choices=LOGGING_PERMISSION_CHOICES,
    )
    custom_allowed_members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        blank=True,
        related_name="custom_time_log_projects",
    )
    default_view = models.CharField(
        max_length=32,
        default="grouped_by_date",
        choices=DEFAULT_VIEW_CHOICES,
    )

    class Meta:
        verbose_name = "Project Time Tracking Setting"
        verbose_name_plural = "Project Time Tracking Settings"
        db_table = "project_time_tracking_settings"

    def __str__(self):
        return f"TimeTrackingSettings: {self.project.name}"


class IssueWorklog(ProjectBaseModel):
    """Recorded time spent or live running timer on a specific issue."""

    issue = models.ForeignKey(
        Issue,
        on_delete=models.CASCADE,
        related_name="worklogs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="issue_worklogs",
    )
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    is_running = models.BooleanField(default=False, db_index=True)
    is_paused = models.BooleanField(default=False, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Issue Worklog"
        verbose_name_plural = "Issue Worklogs"
        db_table = "issue_worklogs"
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.issue.name} - {self.user.email}: {self.duration_seconds}s"
