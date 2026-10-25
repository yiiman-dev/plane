# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from datetime import date

# Django imports
from django.db.models import Sum
from django.db.models.functions import Coalesce, TruncDate

# Third party imports
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

# Module imports
from plane.api.views.base import BaseAPIView
from plane.app.permissions import ProjectEntityPermission
from plane.app.serializers import IssueWorklogSerializer
from plane.app.views.time_tracking import (
    IssueTimerCancelEndpoint,
    IssueTimerPauseEndpoint,
    IssueTimerStartEndpoint,
    IssueTimerStopEndpoint,
    IssueWorklogDetailEndpoint,
    IssueWorklogEndpoint,
    WorkspaceActiveTimerEndpoint,
)
from plane.db.models import IssueWorklog, Project

# The public endpoints reuse the handlers of the internal time-tracking views. The
# business rules (feature gate, logging permission, overlap policy, pause/resume
# math, owner-or-admin checks) live only in plane.app.views.time_tracking.
# Authentication (API key) and throttling come from the public BaseAPIView.


class IssueTimeLogAPIEndpoint(BaseAPIView):
    """List an issue's time logs with totals, or add a manual time log."""

    permission_classes = [ProjectEntityPermission]
    get = IssueWorklogEndpoint.get
    post = IssueWorklogEndpoint.post


class IssueTimeLogDetailAPIEndpoint(BaseAPIView):
    """Update the duration or description of a time log, or delete it."""

    permission_classes = [ProjectEntityPermission]
    patch = IssueWorklogDetailEndpoint.patch
    delete = IssueWorklogDetailEndpoint.delete


class IssueTimerStartAPIEndpoint(BaseAPIView):
    """Start a timer on an issue, or resume its paused timer."""

    permission_classes = [ProjectEntityPermission]
    post = IssueTimerStartEndpoint.post


class IssueTimerPauseAPIEndpoint(BaseAPIView):
    """Pause the caller's running timer on an issue."""

    permission_classes = [ProjectEntityPermission]
    post = IssueTimerPauseEndpoint.post


class IssueTimerStopAPIEndpoint(BaseAPIView):
    """Stop the caller's running or paused timer on an issue and save it as a time log."""

    permission_classes = [ProjectEntityPermission]
    post = IssueTimerStopEndpoint.post


class IssueTimerCancelAPIEndpoint(BaseAPIView):
    """Discard the caller's running or paused timer on an issue without saving it."""

    permission_classes = [ProjectEntityPermission]
    post = IssueTimerCancelEndpoint.post


class WorkspaceActiveTimerAPIEndpoint(BaseAPIView):
    """List the caller's running or paused timers across the workspace."""

    permission_classes = [IsAuthenticated]
    get = WorkspaceActiveTimerEndpoint.get


class ProjectTimeLogReportAPIEndpoint(BaseAPIView):
    """Project time-log report with optional date range and user filters.

    Query parameters (all optional):
      - start_date, end_date: YYYY-MM-DD, inclusive. Matched against start_time,
        falling back to created_at for logs without a start_time.
      - user_id: only logs of this user.

    Totals sum the stored duration_seconds. A running timer's live elapsed time is
    included per log but is not added to the totals until the timer is stopped.
    """

    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id):
        project = Project.objects.filter(pk=project_id, workspace__slug=slug).first()
        if not project:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            start_date = date.fromisoformat(request.query_params["start_date"]) if request.query_params.get("start_date") else None
            end_date = date.fromisoformat(request.query_params["end_date"]) if request.query_params.get("end_date") else None
        except ValueError:
            return Response(
                {"error": "start_date and end_date must be in YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logs = (
            IssueWorklog.objects.filter(project=project, workspace__slug=slug, deleted_at__isnull=True)
            .annotate(log_at=Coalesce("start_time", "created_at"))
            .select_related("user", "issue")
            .order_by("-log_at")
        )
        if start_date:
            logs = logs.filter(log_at__date__gte=start_date)
        if end_date:
            logs = logs.filter(log_at__date__lte=end_date)
        if request.query_params.get("user_id"):
            logs = logs.filter(user_id=request.query_params["user_id"])

        totals = logs.aggregate(total=Sum("duration_seconds"))
        # order_by() clears the default ordering so GROUP BY only uses the grouped fields.
        by_user = (
            logs.order_by()
            .values("user_id", "user__display_name", "user__email")
            .annotate(total=Sum("duration_seconds"))
            .order_by("-total")
        )
        by_date = (
            logs.order_by()
            .annotate(day=TruncDate("log_at"))
            .values("day")
            .annotate(total=Sum("duration_seconds"))
            .order_by("-day")
        )

        def serialize(page_logs):
            return IssueWorklogSerializer(page_logs, many=True).data

        response = self.paginate(
            request=request,
            queryset=logs,
            on_results=serialize,
        )
        response.data["summary"] = {
            "total_duration_seconds": totals["total"] or 0,
            "by_user": [
                {
                    "user_id": str(row["user_id"]),
                    "display_name": row["user__display_name"] or row["user__email"],
                    "total_duration_seconds": row["total"] or 0,
                }
                for row in by_user
            ],
            "by_date": [
                {"date": row["day"].isoformat(), "total_duration_seconds": row["total"] or 0}
                for row in by_date
                if row["day"] is not None
            ],
        }
        return response
