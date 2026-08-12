"""Review-issue tools: create, update, query.

`update_review_issue` is the one update tool that accepts `status`: SRS-091a
routes artifact status through `set_review_status` but leaves issue status
here (SRS-119), validated against the issue transition matrix.

See: LLD-02 §7.6 (Review Issue Tools — SRS-088, SRS-119)
"""

from typing import Any
from uuid import uuid4

from ..db.models import ISSUE_STATUSES
from ..errors import McpResult, McpValidationError
from ..validation.common import (
    validate_artifact_type,
    validate_choice,
    validate_not_empty,
    validate_uuid_format,
)
from ..validation.status import validate_issue_transition
from ._engine import (
    FieldSpec,
    QuerySpec,
    choice_of,
    record_to_dict,
    reject_unknown_arguments,
    run_query,
)
from .context import ToolContext

_CREATE_TOOL = "create_review_issue"
_UPDATE_TOOL = "update_review_issue"

# The five values the ReviewIssues.issue_type CHECK constraint permits.
ISSUE_TYPES = frozenset(
    {"ambiguous", "incomplete", "unresolved_reference", "unsupported", "out_of_scope"}
)

_QUERY = QuerySpec(
    tool="query_review_issues",
    table="ReviewIssues",
    filters=(
        FieldSpec("issue_type", "issue_type", validator=choice_of(ISSUE_TYPES)),
        FieldSpec("status", "status", validator=choice_of(ISSUE_STATUSES)),
        FieldSpec("artifact_type", "artifact_type"),
        FieldSpec("artifact_unique_key", "artifact_unique_key"),
    ),
)


def handle_create_review_issue(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a review issue (SRS-088)."""
    reject_unknown_arguments(
        _CREATE_TOOL,
        arguments,
        frozenset(
            {
                "issue_type",
                "message",
                "artifact_type",
                "artifact_unique_key",
                "source_requirement_key",
            }
        ),
    )
    validate_choice(arguments.get("issue_type"), ISSUE_TYPES, "issue_type", operation=_CREATE_TOOL)
    validate_not_empty(arguments.get("message"), "message", operation=_CREATE_TOOL)
    artifact_type = arguments.get("artifact_type")
    validate_artifact_type(artifact_type, "artifact_type", operation=_CREATE_TOOL)
    artifact_key = arguments.get("artifact_unique_key")
    if artifact_key is not None and artifact_type is None:
        raise McpValidationError.of(
            _CREATE_TOOL,
            "artifact_type is required when artifact_unique_key is given (SRS-074)",
            field="artifact_type",
            affected_key=str(artifact_key),
        )

    unique_key = str(uuid4())
    with ctx.db.transaction() as conn:
        source_requirement_id: int | None = None
        source_key = arguments.get("source_requirement_key")
        if source_key is not None:
            source = ctx.dal.get_source_requirement_by_key(conn, str(source_key))
            if source is None:
                raise McpValidationError.of(
                    _CREATE_TOOL,
                    "source_requirement_key does not resolve to an existing record",
                    field="source_requirement_key",
                    affected_key=str(source_key),
                )
            source_requirement_id = source.id
        record_id = ctx.dal.insert_review_issue(
            conn,
            unique_key=unique_key,
            issue_type=str(arguments["issue_type"]),
            message=str(arguments["message"]),
            source_requirement_id=source_requirement_id,
            artifact_type=artifact_type,
            artifact_unique_key=None if artifact_key is None else str(artifact_key),
        )
        created = ctx.dal.get_record_by_id(conn, "ReviewIssues", record_id)

    data = record_to_dict(created)
    data.pop("id", None)
    data.pop("unique_key", None)
    return McpResult(unique_key=unique_key, data=data).to_dict()


def handle_update_review_issue(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update an issue's status, message or resolution (SRS-119)."""
    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=_UPDATE_TOOL)
    reject_unknown_arguments(
        _UPDATE_TOOL, arguments, frozenset({"unique_key", "status", "message", "resolution"})
    )

    with ctx.db.transaction() as conn:
        issue = ctx.dal.get_record_by_unique_key(conn, "ReviewIssues", str(key))
        if issue is None:
            raise McpValidationError.of(
                _UPDATE_TOOL,
                f"no ReviewIssues record with unique_key {key!r}",
                field="unique_key",
                affected_key=str(key),
            )
        changed: dict[str, Any] = {}
        if "status" in arguments:
            validate_choice(arguments["status"], ISSUE_STATUSES, "status", operation=_UPDATE_TOOL)
            validate_issue_transition(
                str(issue.status),
                str(arguments["status"]),
                operation=_UPDATE_TOOL,
                affected_key=str(key),
                field="status",
            )
            changed["status"] = arguments["status"]
        if "message" in arguments:
            validate_not_empty(arguments["message"], "message", operation=_UPDATE_TOOL)
            changed["message"] = arguments["message"]
        if "resolution" in arguments:
            changed["resolution"] = arguments["resolution"]
        if changed:
            ctx.dal.update_record(conn, "ReviewIssues", issue.id, changed)
        updated = ctx.dal.get_record_by_id(conn, "ReviewIssues", issue.id)

    data = record_to_dict(updated)
    data.pop("id", None)
    data.pop("unique_key", None)
    return McpResult(unique_key=str(key), data=data).to_dict()


def handle_query_review_issues(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query review issues (SRS-088)."""
    return run_query(ctx, _QUERY, arguments)
