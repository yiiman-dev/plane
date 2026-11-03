# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Operational commands for users who linked their Bale chat to Plane.

The Bale webhook hands every plain text message of a linked user to
:func:`handle_bale_message`. Every query below is scoped to the workspaces and
projects the user is really a member of, so knowing a task number is never
enough to reach a project the user has no access to.
"""

# Python imports
import logging
from typing import Optional

# Django imports
from django.db import IntegrityError
from django.db.models import QuerySet
from django.utils import timezone
from django.utils.html import escape


logger = logging.getLogger("plane")

# The Bale API rejects messages longer than this, keep replies comfortably below it.
MAX_MESSAGE_LENGTH = 3900

# ``in_app:issue_activities:mentioned`` is the only sender value the mention
# pipeline assigns, the other in-app senders are created / assigned / subscribed.
MENTION_SENDER = "in_app:issue_activities:mentioned"

OPEN_STATE_GROUPS = ["backlog", "unstarted", "started"]

MAX_TASKS = 15
MAX_CYCLES = 10
MAX_MENTIONS = 10
MAX_TASK_MATCHES = 5

PRIORITY_LABELS = {
    "urgent": "فوری",
    "high": "بالا",
    "medium": "متوسط",
    "low": "کم",
    "none": "بدون اولویت",
}

HELP_TEXT = "\n".join(
    [
        "فرمان‌های ربات پلان:",
        "/help — نمایش همین راهنما",
        "/tasks — فهرست تسک‌های بازِ تخصیص‌یافته به شما",
        "/task 123 — جزئیات یک تسک با شماره یا شناسهٔ ABC-123",
        "/comment 123 متن — ثبت کامنت روی تسک",
        "/cycle — سیکل‌های فعال جاری با درصد پیشرفت",
        "/mentions — منشن‌های اخیر شما",
        "",
        "مثال: comment 123 لطفاً این تسک را بررسی کنید",
    ]
)

GENERIC_ERROR = "در انجام این درخواست خطایی رخ داد. لطفاً کمی بعد دوباره تلاش کنید."

_MODELS = None


def _load_models():
    """Import the ORM lazily so the module can be imported before the app registry is ready."""
    global _MODELS
    if _MODELS is None:
        from plane.db import models

        _MODELS = models
    return _MODELS


def _truncate(text: str) -> str:
    """Keep a reply below the maximum message length accepted by the channel."""
    if len(text) <= MAX_MESSAGE_LENGTH:
        return text
    return text[: MAX_MESSAGE_LENGTH - 1].rstrip() + "…"


def _format_date(value) -> str:
    """Render a date or datetime in the instance timezone."""
    if value is None:
        return "تعیین نشده"
    try:
        if hasattr(value, "hour"):
            return timezone.localtime(value).strftime("%Y-%m-%d %H:%M")
        return value.strftime("%Y-%m-%d")
    except (ValueError, TypeError, OSError):
        return "تعیین نشده"


def _priority_label(priority: Optional[str]) -> str:
    return PRIORITY_LABELS.get(priority, "تعیین نشده")


def _state_label(issue) -> str:
    return issue.state.name if issue.state_id and issue.state else "تعیین نشده"


def _accessible_projects(user) -> QuerySet:
    """Projects the user is really an active member of, through workspace and project membership."""
    models = _load_models()
    return models.Project.objects.filter(
        workspace__workspace_member__member=user,
        workspace__workspace_member__is_active=True,
        project_projectmember__member=user,
        project_projectmember__is_active=True,
        archived_at__isnull=True,
    )


def _user_issues(user) -> QuerySet:
    """Every visible issue of the user's projects, except drafts and archived ones."""
    models = _load_models()
    return (
        models.Issue.objects.filter(
            project__in=_accessible_projects(user),
            archived_at__isnull=True,
            is_draft=False,
        )
        .select_related("project", "state")
        .order_by("-updated_at")
    )


def _open_issues(user) -> QuerySet:
    """Open issues, meaning every state group except completed and cancelled."""
    return _user_issues(user).filter(state__group__in=OPEN_STATE_GROUPS)


def _identifier(issue) -> str:
    return f"{issue.project.identifier}-{issue.sequence_id}"


def _display_name(assignee) -> str:
    return getattr(assignee, "display_name", None) or "کاربر حذف‌شده"


def _split_issue_token(token: str):
    """Split ``ABC-123`` or ``123`` into ``(project identifier, sequence id)``."""
    token = token.strip()
    if not token:
        return None, None

    identifier, separator, sequence = token.partition("-")
    if separator:
        return identifier.upper(), int(sequence) if sequence.isdigit() else None

    if token.isdigit():
        return None, int(token)

    return token.upper(), None


def _find_issues(user, token: str):
    """Resolve a task token inside the user's accessible projects only."""
    identifier, sequence_id = _split_issue_token(token)
    if identifier is None and sequence_id is None:
        return []

    queryset = _user_issues(user)
    if sequence_id is not None:
        queryset = queryset.filter(sequence_id=sequence_id)
    if identifier is not None:
        queryset = queryset.filter(project__identifier__iexact=identifier)

    return list(queryset[: MAX_TASK_MATCHES + 1])


def _handle_help() -> str:
    return HELP_TEXT


def _handle_tasks(user) -> str:
    queryset = _open_issues(user).filter(issue_assignee__assignee=user).distinct()
    total = queryset.count()
    issues = list(queryset[:MAX_TASKS])

    if not issues:
        return "هیچ تسک بازی به شما تخصیص نیافته است."

    lines = [f"تسک‌های باز شما ({len(issues)} از {total} مورد):"]
    for issue in issues:
        lines.append(
            f"• {_identifier(issue)} — {issue.name}\n"
            f"  پروژه: {issue.project.name} | وضعیت: {_state_label(issue)} | اولویت: {_priority_label(issue.priority)}"
        )

    if total > MAX_TASKS:
        lines.append(f"و {total - MAX_TASKS} تسک دیگر هم باز دارید.")

    return "\n".join(lines)


def _handle_task(user, args) -> str:
    if not args:
        return "شمارهٔ تسک را بنویسید. مثال: task 123 یا task ABC-123"

    issues = _find_issues(user, args[0])
    if not issues:
        return "تسکی با این شماره در پروژه‌های شما پیدا نشد یا به آن دسترسی ندارید."

    if len(issues) > 1:
        lines = ["این شماره در چند پروژه وجود دارد. لطفاً شناسهٔ کامل را بفرستید:"]
        for issue in issues[:MAX_TASK_MATCHES]:
            lines.append(f"• {_identifier(issue)} — {issue.name} ({issue.project.name})")
        lines.append("مثال: task ABC-123")
        return "\n".join(lines)

    issue = issues[0]
    assignees = [_display_name(assignee) for assignee in issue.issue_assignee.all()]

    return "\n".join(
        [
            f"{_identifier(issue)} — {issue.name}",
            f"پروژه: {issue.project.name}",
            f"وضعیت: {_state_label(issue)}",
            f"اولویت: {_priority_label(issue.priority)}",
            f"تاریخ پایان: {_format_date(issue.target_date)}",
            f"مسئول: {'، '.join(assignees) if assignees else 'تعیین نشده'}",
        ]
    )


def _handle_comment(user, args) -> str:
    if not args:
        return "شمارهٔ تسک و متن کامنت را بنویسید. مثال: comment 123 متن دلخواه"

    body = " ".join(args[1:]).strip()
    if not body:
        return "متن کامنت ناقص است. مثال: comment 123 متن دلخواه"

    models = _load_models()
    issues = _find_issues(user, args[0])
    if not issues:
        return "تسکی با این شماره در پروژه‌های شما پیدا نشد یا به آن دسترسی ندارید."

    if len(issues) > 1:
        return "این شماره در چند پروژه وجود دارد. لطفاً شناسهٔ کامل را بفرستید. مثال: comment ABC-123 متن دلخواه"

    issue = issues[0]
    models.IssueComment.objects.create(
        issue=issue,
        project=issue.project,
        workspace=issue.workspace,
        actor=user,
        comment_html=f"<p>{escape(body)}</p>",
        comment_stripped=body,
    )
    return f"کامنت شما روی {_identifier(issue)} ثبت شد."


def _cycle_progress(cycle) -> Optional[int]:
    """Completed percentage, read from the stored snapshot first and recalculated second."""
    snapshot = cycle.progress_snapshot or {}
    snapshot_total = snapshot.get("total_issues") or 0
    if snapshot_total:
        return int(round((snapshot.get("completed_issues") or 0) * 100 / snapshot_total))

    issues = cycle.issue_cycle.filter(
        deleted_at__isnull=True,
        issue__deleted_at__isnull=True,
        issue__archived_at__isnull=True,
        issue__is_draft=False,
    )
    total = issues.count()
    if total:
        return int(round(issues.filter(issue__state__group="completed").count() * 100 / total))

    return None


def _handle_cycle(user) -> str:
    models = _load_models()
    now = timezone.now()
    cycles = list(
        models.Cycle.objects.filter(
            project__in=_accessible_projects(user),
            archived_at__isnull=True,
            start_date__isnull=False,
            end_date__isnull=False,
            start_date__lte=now,
            end_date__gte=now,
        )
        .select_related("project", "workspace")
        .order_by("end_date")[:MAX_CYCLES]
    )

    if not cycles:
        return "در حال حاضر سیکل فعالی در پروژه‌های شما وجود ندارد."

    lines = ["سیکل‌های فعال جاری:"]
    for cycle in cycles:
        progress = _cycle_progress(cycle)
        progress_label = f"{progress}٪" if progress is not None else "نامشخص"
        lines.append(
            f"• {cycle.name}\n"
            f"  پروژه: {cycle.project.name}\n"
            f"  شروع: {_format_date(cycle.start_date)} | پایان: {_format_date(cycle.end_date)}\n"
            f"  پیشرفت: {progress_label}"
        )

    return "\n".join(lines)


def _mention_line(notification) -> str:
    data = notification.get("data") or {}
    issue_data = data.get("issue") or {}
    project_identifier = issue_data.get("identifier") or notification.get("project__identifier")
    sequence_id = issue_data.get("sequence_id")
    name = issue_data.get("name") or notification.get("title") or "تسک بدون عنوان"

    prefix = f"{project_identifier}-{sequence_id}" if project_identifier and sequence_id else "تسک"
    actor = notification.get("triggered_by__display_name") or "یکی از همکاران"
    state_name = issue_data.get("state_name")

    line = f"• {prefix} — {name} | از طرف: {actor}"
    if state_name:
        line += f" | وضعیت: {state_name}"
    return f"{line} | {_format_date(notification.get('created_at'))}"


def _handle_mentions(user) -> str:
    models = _load_models()
    projects = _accessible_projects(user)

    notifications = list(
        models.Notification.objects.filter(
            sender=MENTION_SENDER,
            receiver=user,
            archived_at__isnull=True,
            project__in=projects,
        )
        .values(
            "created_at",
            "title",
            "data",
            "project__identifier",
            "triggered_by__display_name",
        )
        .order_by("-created_at")[:MAX_MENTIONS]
    )

    if not notifications:
        return "منشن جدیدی برای شما وجود ندارد."

    lines = ["منشن‌های اخیر شما:"]
    lines.extend(_mention_line(notification) for notification in notifications)
    return "\n".join(lines)


def handle_bale_message(*, user, text: str, chat_id: str) -> Optional[str]:
    """Turn a message of a linked Bale chat into a reply.

    :param user: the Plane user the Bale chat is linked to
    :param text: the plain text message sent by the user
    :param chat_id: the Bale chat identifier the message came from
    :return: the reply text, or None when nothing should be sent
    """
    if user is None or not text:
        return None

    parts = text.strip().split()
    if not parts:
        return None

    command = parts[0].lower()
    args = parts[1:]

    try:
        if command == "/help":
            reply = _handle_help()
        elif command == "/tasks":
            reply = _handle_tasks(user)
        elif command == "/task":
            reply = _handle_task(user, args)
        elif command == "/comment":
            reply = _handle_comment(user, args)
        elif command == "/cycle":
            reply = _handle_cycle(user)
        elif command == "/mentions":
            reply = _handle_mentions(user)
        else:
            return None
    except IntegrityError:
        logger.warning("Bale command %s failed while saving data", command)
        return GENERIC_ERROR
    except Exception:
        logger.exception("Bale command %s failed", command)
        return GENERIC_ERROR

    return _truncate(reply) if reply else None