# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""Guard that keeps a blocked work item from being started.

Plane stores a "blocked by" relation as an ``IssueRelation`` row where ``issue``
is the blocker and ``related_issue`` is the blocked work item, with
``relation_type`` set to ``blocked_by``. A blocked work item may not enter the
``started`` state group until every one of its blockers has reached the
``completed`` group.

The lookup and the validation live here so every entry point - the app API
single item update (used by the state pickers, the board and list drag & drop
and the spreadsheet), the external API, and any bulk path that resolves a state
per work item - shares one rule and one error payload.
"""

# Django imports
from django.db.models import Q

# Third Party imports
from rest_framework import serializers

# Module imports
from plane.db.models import IssueRelation, StateGroup
from plane.utils.error_codes import ERROR_CODES

# Relation type Plane uses for "this work item is blocked by that one".
BLOCKED_BY_RELATION_TYPE = "blocked_by"


def get_unresolved_blockers(issue_ids):
    """Map each work item id to the blockers that are not completed yet.

    Soft deleted relations are ignored. A blocker counts as resolved only once
    its own state sits in the ``completed`` group, so an open or cancelled
    blocker keeps the transition blocked.
    """
    issue_ids = [str(issue_id) for issue_id in issue_ids if issue_id]
    if not issue_ids:
        return {}

    relations = (
        IssueRelation.objects.filter(
            relation_type=BLOCKED_BY_RELATION_TYPE,
            deleted_at__isnull=True,
            related_issue_id__in=issue_ids,
        )
        .exclude(Q(issue__state__isnull=True) | Q(issue__state__group=StateGroup.COMPLETED))
        .select_related("issue", "issue__state")
        .order_by("issue__sequence_id")
    )

    blockers = {}
    for relation in relations:
        blockers.setdefault(str(relation.related_issue_id), []).append(relation.issue)
    return blockers


def get_unresolved_blocker_names(issue_ids):
    """Map each work item id to the names of its unresolved blockers."""
    return {
        issue_id: [blocker.name for blocker in blockers]
        for issue_id, blockers in get_unresolved_blockers(issue_ids).items()
    }


def validate_state_transition_allowed(issue, target_state):
    """Reject a move into the ``started`` group while blockers are unresolved.

    Every other destination group stays unrestricted, so backlog, unstarted,
    cancelled, completed and a request without a state keep behaving exactly as
    before.
    """
    # A work item that is not persisted yet cannot be blocked by anything.
    if issue is None or issue.id is None:
        return
    if target_state is None or target_state.group != StateGroup.STARTED:
        return

    blockers = get_unresolved_blockers([issue.id]).get(str(issue.id))
    if not blockers:
        return

    raise serializers.ValidationError(
        {
            "error_code": [ERROR_CODES["ISSUE_BLOCKED_BY_UNRESOLVED"]],
            "state_id": [
                "This work item cannot be moved into a started state because it is blocked by unresolved work items: "
                + ", ".join(blocker.name for blocker in blockers)
            ],
            "blocked_by": [
                {"id": str(blocker.id), "name": blocker.name, "sequence_id": str(blocker.sequence_id)}
                for blocker in blockers
            ],
        }
    )
