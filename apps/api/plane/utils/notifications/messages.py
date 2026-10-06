# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Build channel agnostic notification messages from issue activity payloads."""

# Python imports
from typing import Any, Dict, Optional

# Django imports
from django.conf import settings

# Module imports
from plane.db.models.notification import (
    NOTIFICATION_EVENT_COMMENT,
    NOTIFICATION_EVENT_ISSUE_COMPLETED,
    NOTIFICATION_EVENT_MENTION,
    NOTIFICATION_EVENT_PROPERTY_CHANGE,
    NOTIFICATION_EVENT_STATE_CHANGE,
)
from .base import ChannelMessage


def get_app_base_url() -> str:
    """Return the web app base url without a trailing slash"""
    base_url = getattr(settings, "APP_BASE_URL", None) or getattr(settings, "WEB_URL", None) or ""
    return str(base_url).rstrip("/")


def build_issue_url(issue_data: Dict[str, Any]) -> Optional[str]:
    """Build the deep link of the issue that triggered the notification"""
    base_url = get_app_base_url()
    workspace_slug = issue_data.get("workspace_slug")
    project_id = issue_data.get("project_id")
    issue_id = issue_data.get("id")
    if not (base_url and workspace_slug and project_id and issue_id):
        return None
    return f"{base_url}/{workspace_slug}/projects/{project_id}/issues/{issue_id}"


def get_issue_identifier(issue_data: Dict[str, Any]) -> str:
    """Return the human readable identifier of the issue, ie PROJ-12"""
    project_identifier = issue_data.get("project_identifier")
    sequence_id = issue_data.get("sequence_id")
    if project_identifier and sequence_id:
        return f"{project_identifier}-{sequence_id}"
    return str(issue_data.get("name") or "")


def build_activity_sentence(event: str, data: Dict[str, Any]) -> str:
    """Return the human readable sentence describing the activity"""
    activity = data.get("issue_activity") or {}
    comment = activity.get("issue_comment") or {}
    actor = activity.get("actor_detail", {}).get("display_name") or activity.get("actor") or "Someone"
    comment_stripped = (comment.get("comment_stripped") or "").strip()

    if event == NOTIFICATION_EVENT_MENTION:
        if comment_stripped:
            return f"{actor} mentioned you: {comment_stripped}"
        return f"{actor} mentioned you in a comment"
    if event == NOTIFICATION_EVENT_COMMENT:
        if comment_stripped:
            return f"{actor} commented: {comment_stripped}"
        return f"{actor} added a comment"
    if event == NOTIFICATION_EVENT_STATE_CHANGE:
        state_name = data.get("issue", {}).get("state_name") or activity.get("new_value") or "a new state"
        return f"{actor} moved this issue to {state_name}"
    if event == NOTIFICATION_EVENT_ISSUE_COMPLETED:
        return f"{actor} completed this issue"
    if event == NOTIFICATION_EVENT_PROPERTY_CHANGE:
        field_name = (activity.get("field_name") or activity.get("field") or "a field").replace("_", " ")
        new_value = activity.get("new_value")
        if new_value:
            return f"{actor} updated {field_name} to {new_value}"
        return f"{actor} updated {field_name}"
    return f"{actor} updated this issue"


def build_channel_message(event: str, data: Dict[str, Any]) -> ChannelMessage:
    """Build the message delivered on the external channels

    :param event: notification event key
    :param data: activity payload, shaped like the email notification payload
    :returns: channel agnostic message with the deep link to the issue
    """
    issue_data = data.get("issue") or {}
    identifier = get_issue_identifier(issue_data)
    name = issue_data.get("name") or identifier or "An issue"
    title = f"{identifier}: {name}" if identifier and identifier != name else name
    sentence = build_activity_sentence(event, data)
    text = f"{title}\n{sentence}"
    return ChannelMessage(text=text, url=build_issue_url(issue_data), title=title, metadata={"event": event})