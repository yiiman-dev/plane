# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from collections import defaultdict
from datetime import datetime

# Django imports
from django.utils import timezone
from django.db.models import Q

# Third party imports
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

# Module imports
from .base import BaseAPIView
from plane.app.permissions import ProjectBasePermission, ProjectEntityPermission
from plane.app.serializers import (
    ProjectTimeTrackingSettingSerializer,
    IssueWorklogSerializer,
    UserLiteSerializer,
)
from plane.db.models import (
    Project,
    Issue,
    ProjectMember,
    WorkspaceMember,
    ProjectTimeTrackingSetting,
    IssueWorklog,
)
from plane.db.models.project import ROLE
from plane.billing.services.entitlements import time_tracking_rejection


def _check_can_log_time(user, issue, setting, is_admin=False):
    """Check if the given user is allowed to log time on this issue."""
    if is_admin:
        return True

    perm = setting.logging_permission
    if perm == "all_members":
        return True

    is_assignee = issue.assignees.filter(id=user.id).exists()
    if perm == "assignee_only":
        return is_assignee

    if perm == "custom_members":
        return is_assignee or setting.custom_allowed_members.filter(id=user.id).exists()

    return True


class ProjectTimeTrackingSettingEndpoint(BaseAPIView):
    """Retrieve and update project time tracking settings."""

    permission_classes = [ProjectBasePermission]

    def get(self, request, slug, project_id):
        project = Project.objects.filter(pk=project_id, workspace__slug=slug).first()
        if not project:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        rejection = time_tracking_rejection(project.workspace)
        if rejection is not None:
            return Response(rejection, status=status.HTTP_403_FORBIDDEN)

        setting, _ = ProjectTimeTrackingSetting.objects.get_or_create(
            project=project,
            defaults={"workspace": project.workspace, "is_enabled": True, "allow_overlap": True},
        )
        serializer = ProjectTimeTrackingSettingSerializer(setting)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, slug, project_id):
        project = Project.objects.filter(pk=project_id, workspace__slug=slug).first()
        if not project:
            return Response({"error": "Project not found"}, status=status.HTTP_404_NOT_FOUND)

        rejection = time_tracking_rejection(project.workspace)
        if rejection is not None:
            return Response(rejection, status=status.HTTP_403_FORBIDDEN)

        # Ensure user has project admin or workspace admin role
        is_project_admin = ProjectMember.objects.filter(
            project=project,
            member=request.user,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()
        is_ws_admin = WorkspaceMember.objects.filter(
            workspace__slug=slug,
            member=request.user,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()

        if not (is_project_admin or is_ws_admin):
            return Response(
                {"error": "تنها مدیران پروژه یا ورک‌اسپیس می‌توانند تنظیمات را تغییر دهند."},
                status=status.HTTP_403_FORBIDDEN,
            )

        setting, _ = ProjectTimeTrackingSetting.objects.get_or_create(
            project=project,
            defaults={"workspace": project.workspace},
        )

        serializer = ProjectTimeTrackingSettingSerializer(setting, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            # Sync is_time_tracking_enabled with project
            if "is_enabled" in request.data:
                project.is_time_tracking_enabled = serializer.validated_data["is_enabled"]
                project.save(update_fields=["is_time_tracking_enabled"])
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class IssueWorklogEndpoint(BaseAPIView):
    """Retrieve worklog statistics & history for an issue, and add manual time logs."""

    permission_classes = [ProjectEntityPermission]

    def get(self, request, slug, project_id, issue_id):
        issue = Issue.objects.filter(pk=issue_id, project_id=project_id, workspace__slug=slug).first()
        if not issue:
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)

        rejection = time_tracking_rejection(issue.workspace)
        if rejection is not None:
            return Response(rejection, status=status.HTTP_403_FORBIDDEN)

        setting, _ = ProjectTimeTrackingSetting.objects.get_or_create(
            project=issue.project,
            defaults={"workspace": issue.workspace},
        )

        is_admin = ProjectMember.objects.filter(
            project=issue.project,
            member=request.user,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()
        can_log_time = _check_can_log_time(request.user, issue, setting, is_admin=is_admin)

        logs = (
            IssueWorklog.objects.filter(issue=issue, deleted_at__isnull=True)
            .select_related("user")
            .order_by("-created_at")
        )

        completed_duration_seconds = 0
        total_duration_seconds = 0
        now = timezone.now()

        grouped_by_date = defaultdict(lambda: {"date": "", "total_seconds": 0, "logs": []})
        grouped_by_user = defaultdict(lambda: {"user": None, "total_seconds": 0, "logs": []})
        intervals = []

        serialized_logs = []
        for log in logs:
            is_paused = getattr(log, "is_paused", False)
            elapsed = log.duration_seconds
            if log.is_running and log.started_at:
                elapsed += max(0, int((now - log.started_at).total_seconds()))

            if not log.is_running and not is_paused:
                completed_duration_seconds += log.duration_seconds

            total_duration_seconds += elapsed

            log_date = ""
            if log.start_time:
                log_date = log.start_time.strftime("%Y-%m-%d")
            elif log.created_at:
                log_date = log.created_at.strftime("%Y-%m-%d")

            log_dict = {
                "id": str(log.id),
                "user": UserLiteSerializer(log.user).data,
                "duration_seconds": elapsed,
                "is_running": log.is_running,
                "is_paused": is_paused,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "start_time": log.start_time.isoformat() if log.start_time else None,
                "end_time": log.end_time.isoformat() if log.end_time else None,
                "description": log.description,
                "created_at": log.created_at.isoformat(),
            }
            serialized_logs.append(log_dict)

            # Grouping
            if log_date:
                grouped_by_date[log_date]["date"] = log_date
                grouped_by_date[log_date]["total_seconds"] += elapsed
                grouped_by_date[log_date]["logs"].append(log_dict)

            user_id = str(log.user.id)
            grouped_by_user[user_id]["user"] = UserLiteSerializer(log.user).data
            grouped_by_user[user_id]["total_seconds"] += elapsed
            grouped_by_user[user_id]["logs"].append(log_dict)

            intervals.append(log_dict)

        # Check if current user has an active timer on this issue
        active_timer_for_user = (
            logs.filter(user=request.user, deleted_at__isnull=True)
            .filter(Q(is_running=True) | Q(is_paused=True))
            .first()
        )

        active_elapsed = 0
        if active_timer_for_user:
            active_elapsed = active_timer_for_user.duration_seconds
            if active_timer_for_user.is_running and active_timer_for_user.started_at:
                active_elapsed += max(0, int((now - active_timer_for_user.started_at).total_seconds()))

        return Response(
            {
                "completed_duration_seconds": completed_duration_seconds,
                "total_duration_seconds": total_duration_seconds,
                "can_log_time": can_log_time,
                "default_view": setting.default_view,
                "is_time_tracking_enabled": setting.is_enabled,
                "active_timer": {
                    "id": str(active_timer_for_user.id),
                    "started_at": active_timer_for_user.started_at.isoformat() if active_timer_for_user.started_at else None,
                    "duration_seconds": active_timer_for_user.duration_seconds,
                    "elapsed_seconds": active_elapsed,
                    "is_running": active_timer_for_user.is_running,
                    "is_paused": getattr(active_timer_for_user, "is_paused", False),
                } if active_timer_for_user else None,
                "logs": serialized_logs,
                "grouped_by_date": list(grouped_by_date.values()),
                "grouped_by_user": list(grouped_by_user.values()),
                "intervals": intervals,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request, slug, project_id, issue_id):
        """Manually log time."""
        issue = Issue.objects.filter(pk=issue_id, project_id=project_id, workspace__slug=slug).first()
        if not issue:
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)

        rejection = time_tracking_rejection(issue.workspace)
        if rejection is not None:
            return Response(rejection, status=status.HTTP_403_FORBIDDEN)

        setting, _ = ProjectTimeTrackingSetting.objects.get_or_create(
            project=issue.project,
            defaults={"workspace": issue.workspace},
        )
        if not setting.is_enabled:
            return Response({"error": "ثبت زمان برای این پروژه غیرفعال است."}, status=status.HTTP_400_BAD_REQUEST)

        is_admin = ProjectMember.objects.filter(
            project=issue.project,
            member=request.user,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()
        if not _check_can_log_time(request.user, issue, setting, is_admin=is_admin):
            return Response({"error": "شما مجاز به ثبت زمان روی این تسک نیستید."}, status=status.HTTP_403_FORBIDDEN)

        duration_seconds = request.data.get("duration_seconds")
        if duration_seconds is None:
            hours = int(request.data.get("hours", 0) or 0)
            minutes = int(request.data.get("minutes", 0) or 0)
            seconds = int(request.data.get("seconds", 0) or 0)
            duration_seconds = (hours * 3600) + (minutes * 60) + seconds

        duration_seconds = max(1, int(duration_seconds))
        description = request.data.get("description", "")
        start_time = request.data.get("start_time")
        end_time = request.data.get("end_time")

        now = timezone.now()
        parsed_start = None
        if start_time:
            try:
                parsed_start = datetime.fromisoformat(str(start_time).replace("Z", "+00:00"))
            except Exception:
                parsed_start = now
        else:
            parsed_start = now

        worklog = IssueWorklog.objects.create(
            issue=issue,
            project=issue.project,
            workspace=issue.workspace,
            user=request.user,
            duration_seconds=duration_seconds,
            start_time=parsed_start,
            end_time=end_time or now,
            description=description,
            is_running=False,
        )

        serializer = IssueWorklogSerializer(worklog)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class IssueWorklogDetailEndpoint(BaseAPIView):
    """Update or delete a worklog item."""

    permission_classes = [ProjectEntityPermission]

    def patch(self, request, slug, project_id, issue_id, pk):
        worklog = IssueWorklog.objects.filter(
            pk=pk,
            issue_id=issue_id,
            project_id=project_id,
            workspace__slug=slug,
            deleted_at__isnull=True,
        ).first()
        if not worklog:
            return Response({"error": "Worklog not found"}, status=status.HTTP_404_NOT_FOUND)

        is_owner = worklog.user_id == request.user.id
        is_admin = ProjectMember.objects.filter(
            project_id=project_id,
            member=request.user,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()

        if not (is_owner or is_admin):
            return Response({"error": "اجازه ویرایش این لاگ را ندارید."}, status=status.HTTP_403_FORBIDDEN)

        if "duration_seconds" in request.data:
            worklog.duration_seconds = max(0, int(request.data["duration_seconds"]))
        if "description" in request.data:
            worklog.description = str(request.data["description"])
        worklog.save()

        serializer = IssueWorklogSerializer(worklog)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, slug, project_id, issue_id, pk):
        worklog = IssueWorklog.objects.filter(
            pk=pk,
            issue_id=issue_id,
            project_id=project_id,
            workspace__slug=slug,
            deleted_at__isnull=True,
        ).first()
        if not worklog:
            return Response({"error": "Worklog not found"}, status=status.HTTP_404_NOT_FOUND)

        is_owner = worklog.user_id == request.user.id
        is_admin = ProjectMember.objects.filter(
            project_id=project_id,
            member=request.user,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()

        if not (is_owner or is_admin):
            return Response({"error": "اجازه حذف این لاگ را ندارید."}, status=status.HTTP_403_FORBIDDEN)

        worklog.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class IssueTimerStartEndpoint(BaseAPIView):
    """Start or resume a live timer on an issue."""

    permission_classes = [ProjectEntityPermission]

    def post(self, request, slug, project_id, issue_id):
        issue = Issue.objects.filter(pk=issue_id, project_id=project_id, workspace__slug=slug).first()
        if not issue:
            return Response({"error": "Issue not found"}, status=status.HTTP_404_NOT_FOUND)

        rejection = time_tracking_rejection(issue.workspace)
        if rejection is not None:
            return Response(rejection, status=status.HTTP_403_FORBIDDEN)

        setting, _ = ProjectTimeTrackingSetting.objects.get_or_create(
            project=issue.project,
            defaults={"workspace": issue.workspace},
        )
        if not setting.is_enabled:
            return Response({"error": "ثبت زمان برای این پروژه غیرفعال است."}, status=status.HTTP_400_BAD_REQUEST)

        is_admin = ProjectMember.objects.filter(
            project=issue.project,
            member=request.user,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()

        if not _check_can_log_time(request.user, issue, setting, is_admin=is_admin):
            return Response({"error": "شما مجاز به ثبت زمان روی این تسک نیستید."}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()

        # Check existing active (running or paused) timer on THIS issue
        existing_on_issue = (
            IssueWorklog.objects.filter(
                issue=issue,
                user=request.user,
                deleted_at__isnull=True,
            )
            .filter(Q(is_running=True) | Q(is_paused=True))
            .first()
        )
        if existing_on_issue:
            if existing_on_issue.is_running:
                elapsed = existing_on_issue.duration_seconds
                if existing_on_issue.started_at:
                    elapsed += max(0, int((now - existing_on_issue.started_at).total_seconds()))
                return Response(
                    {
                        "message": "تایمر هم‌اکنون برای این تسک فعال است.",
                        "worklog_id": str(existing_on_issue.id),
                        "elapsed_seconds": elapsed,
                        "started_at": existing_on_issue.started_at.isoformat() if existing_on_issue.started_at else now.isoformat(),
                        "is_running": True,
                        "is_paused": False,
                    },
                    status=status.HTTP_200_OK,
                )
            else:
                # Resume paused timer
                existing_on_issue.is_running = True
                existing_on_issue.is_paused = False
                existing_on_issue.started_at = now
                existing_on_issue.save(update_fields=["is_running", "is_paused", "started_at"])
                return Response(
                    {
                        "message": "تایمر با موفقیت ادامه یافت.",
                        "worklog_id": str(existing_on_issue.id),
                        "elapsed_seconds": existing_on_issue.duration_seconds,
                        "started_at": now.isoformat(),
                        "is_running": True,
                        "is_paused": False,
                    },
                    status=status.HTTP_200_OK,
                )

        # Check overlap policy across other issues
        other_running_timers = IssueWorklog.objects.filter(
            user=request.user,
            is_running=True,
            deleted_at__isnull=True,
        ).exclude(issue=issue)

        if other_running_timers.exists():
            # Check if overlap is allowed by setting or user exemption
            is_overlap_allowed = setting.allow_overlap or setting.overlap_allowed_members.filter(id=request.user.id).exists()
            if not is_overlap_allowed:
                active_timer = other_running_timers.first()
                return Response(
                    {
                        "error": "تایمر فعال دیگری در حال اجراست و طبق تنظیمات پروژه، هم‌پوشانی تایمر مجاز نیست.",
                        "code": "timer_overlap_not_allowed",
                        "active_issue_id": str(active_timer.issue_id),
                        "active_issue_name": active_timer.issue.name,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Create new running worklog
        worklog = IssueWorklog.objects.create(
            issue=issue,
            project=issue.project,
            workspace=issue.workspace,
            user=request.user,
            is_running=True,
            is_paused=False,
            started_at=now,
            start_time=now,
            duration_seconds=0,
            description=request.data.get("description", ""),
        )

        return Response(
            {
                "worklog_id": str(worklog.id),
                "issue_id": str(issue.id),
                "started_at": now.isoformat(),
                "duration_seconds": 0,
                "elapsed_seconds": 0,
                "is_running": True,
                "is_paused": False,
            },
            status=status.HTTP_201_CREATED,
        )


class IssueTimerPauseEndpoint(BaseAPIView):
    """Pause an active running timer on an issue."""

    permission_classes = [ProjectEntityPermission]

    def post(self, request, slug, project_id, issue_id):
        worklog = (
            IssueWorklog.objects.filter(
                issue_id=issue_id,
                user=request.user,
                deleted_at__isnull=True,
            )
            .filter(Q(is_running=True) | Q(is_paused=True))
            .first()
        )

        if not worklog:
            return Response({"error": "تایمر فعالی برای این تسک یافت نشد."}, status=status.HTTP_404_NOT_FOUND)

        if worklog.is_paused:
            return Response(
                {
                    "worklog_id": str(worklog.id),
                    "duration_seconds": worklog.duration_seconds,
                    "elapsed_seconds": worklog.duration_seconds,
                    "is_running": False,
                    "is_paused": True,
                },
                status=status.HTTP_200_OK,
            )

        now = timezone.now()
        elapsed = 0
        if worklog.started_at:
            elapsed = max(0, int((now - worklog.started_at).total_seconds()))

        worklog.duration_seconds += elapsed
        worklog.is_running = False
        worklog.is_paused = True
        worklog.started_at = None
        worklog.save(update_fields=["duration_seconds", "is_running", "is_paused", "started_at"])

        return Response(
            {
                "worklog_id": str(worklog.id),
                "duration_seconds": worklog.duration_seconds,
                "elapsed_seconds": worklog.duration_seconds,
                "is_running": False,
                "is_paused": True,
            },
            status=status.HTTP_200_OK,
        )


class IssueTimerStopEndpoint(BaseAPIView):
    """Stop/finish an active (running or paused) timer on an issue."""

    permission_classes = [ProjectEntityPermission]

    def post(self, request, slug, project_id, issue_id):
        worklog = (
            IssueWorklog.objects.filter(
                issue_id=issue_id,
                user=request.user,
                deleted_at__isnull=True,
            )
            .filter(Q(is_running=True) | Q(is_paused=True))
            .first()
        )

        if not worklog:
            return Response({"error": "تایمر فعالی برای این تسک یافت نشد."}, status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        elapsed = 0
        if worklog.is_running and worklog.started_at:
            elapsed = max(0, int((now - worklog.started_at).total_seconds()))

        worklog.duration_seconds += elapsed
        worklog.end_time = now
        worklog.is_running = False
        worklog.is_paused = False
        worklog.started_at = None

        description = request.data.get("description")
        if description is not None:
            worklog.description = str(description)

        worklog.save()

        serializer = IssueWorklogSerializer(worklog)
        return Response(serializer.data, status=status.HTTP_200_OK)


class IssueTimerCancelEndpoint(BaseAPIView):
    """Discard an active running or paused timer without saving."""

    permission_classes = [ProjectEntityPermission]

    def post(self, request, slug, project_id, issue_id):
        worklog = (
            IssueWorklog.objects.filter(
                issue_id=issue_id,
                user=request.user,
                deleted_at__isnull=True,
            )
            .filter(Q(is_running=True) | Q(is_paused=True))
            .first()
        )

        if not worklog:
            return Response({"error": "تایمر فعالی یافت نشد."}, status=status.HTTP_404_NOT_FOUND)

        worklog.delete()
        return Response({"message": "تایمر با موفقیت لغو و حذف شد."}, status=status.HTTP_200_OK)


class WorkspaceActiveTimerEndpoint(BaseAPIView):
    """Get all currently active (running or paused) timers for the authenticated user in the workspace."""

    permission_classes = [IsAuthenticated]

    def get(self, request, slug):
        worklogs = (
            IssueWorklog.objects.filter(
                user=request.user,
                workspace__slug=slug,
                deleted_at__isnull=True,
            )
            .filter(Q(is_running=True) | Q(is_paused=True))
            .select_related("issue", "project", "project__time_tracking_setting")
            .order_by("-updated_at")
        )

        now = timezone.now()
        active_timers = []
        for worklog in worklogs:
            is_paused = getattr(worklog, "is_paused", False)
            elapsed = worklog.duration_seconds
            if worklog.is_running and worklog.started_at:
                elapsed += max(0, int((now - worklog.started_at).total_seconds()))

            setting = getattr(worklog.project, "time_tracking_setting", None)
            focus_mins = setting.focus_duration_minutes if setting else 15
            break_mins = setting.break_duration_minutes if setting else 5
            breaks_enabled = setting.breaks_enabled if setting else True

            active_timers.append({
                "id": str(worklog.id),
                "issue_id": str(worklog.issue.id),
                "issue_name": worklog.issue.name,
                "issue_sequence_id": worklog.issue.sequence_id,
                "project_id": str(worklog.project.id),
                "project_name": worklog.project.name,
                "project_identifier": worklog.project.identifier,
                "started_at": worklog.started_at.isoformat() if worklog.started_at else None,
                "base_duration_seconds": worklog.duration_seconds,
                "elapsed_seconds": elapsed,
                "server_time": now.isoformat(),
                "is_running": worklog.is_running,
                "is_paused": is_paused,
                "breaks_enabled": breaks_enabled,
                "focus_duration_minutes": focus_mins,
                "break_duration_minutes": break_mins,
            })

        first_timer = active_timers[0] if active_timers else None

        return Response(
            {
                "active_timer": first_timer,
                "active_timers": active_timers,
            },
            status=status.HTTP_200_OK,
        )
