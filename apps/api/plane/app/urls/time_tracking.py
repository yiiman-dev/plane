# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Django imports
from django.urls import path

# Module imports
from plane.app.views import (
    ProjectTimeTrackingSettingEndpoint,
    IssueWorklogEndpoint,
    IssueWorklogDetailEndpoint,
    IssueTimerStartEndpoint,
    IssueTimerPauseEndpoint,
    IssueTimerStopEndpoint,
    IssueTimerCancelEndpoint,
    WorkspaceActiveTimerEndpoint,
)

urlpatterns = [
    # Project Time Tracking Settings
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/time-tracking-settings/",
        ProjectTimeTrackingSettingEndpoint.as_view(),
        name="project-time-tracking-settings",
    ),
    # Issue Time Logs (List, Aggregate Stats, Manual Log)
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/",
        IssueWorklogEndpoint.as_view(),
        name="issue-time-logs",
    ),
    # Issue Worklog Detail (Update, Delete)
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/<uuid:pk>/",
        IssueWorklogDetailEndpoint.as_view(),
        name="issue-time-log-detail",
    ),
    # Issue Timer Controls
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/timer/start/",
        IssueTimerStartEndpoint.as_view(),
        name="issue-timer-start",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/timer/pause/",
        IssueTimerPauseEndpoint.as_view(),
        name="issue-timer-pause",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/timer/stop/",
        IssueTimerStopEndpoint.as_view(),
        name="issue-timer-stop",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/timer/cancel/",
        IssueTimerCancelEndpoint.as_view(),
        name="issue-timer-cancel",
    ),
    # Workspace Active Timer (for global floating widget sync)
    path(
        "workspaces/<str:slug>/time-logs/active-timer/",
        WorkspaceActiveTimerEndpoint.as_view(),
        name="workspace-active-timer",
    ),
]
