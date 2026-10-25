# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.api.views.time_tracking import (
    IssueTimeLogAPIEndpoint,
    IssueTimeLogDetailAPIEndpoint,
    IssueTimerStartAPIEndpoint,
    IssueTimerPauseAPIEndpoint,
    IssueTimerStopAPIEndpoint,
    IssueTimerCancelAPIEndpoint,
    ProjectTimeLogReportAPIEndpoint,
    WorkspaceActiveTimerAPIEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/",
        IssueTimeLogAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="time-logs",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/<uuid:pk>/",
        IssueTimeLogDetailAPIEndpoint.as_view(http_method_names=["patch", "delete"]),
        name="time-log-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/timer/start/",
        IssueTimerStartAPIEndpoint.as_view(http_method_names=["post"]),
        name="time-log-timer-start",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/timer/pause/",
        IssueTimerPauseAPIEndpoint.as_view(http_method_names=["post"]),
        name="time-log-timer-pause",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/timer/stop/",
        IssueTimerStopAPIEndpoint.as_view(http_method_names=["post"]),
        name="time-log-timer-stop",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/issues/<uuid:issue_id>/time-logs/timer/cancel/",
        IssueTimerCancelAPIEndpoint.as_view(http_method_names=["post"]),
        name="time-log-timer-cancel",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/time-logs/",
        ProjectTimeLogReportAPIEndpoint.as_view(http_method_names=["get"]),
        name="project-time-logs",
    ),
    path(
        "workspaces/<str:slug>/time-logs/active-timers/",
        WorkspaceActiveTimerAPIEndpoint.as_view(http_method_names=["get"]),
        name="workspace-active-timers",
    ),
]
