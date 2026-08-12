"""The sole tool that writes a review status.

`table_hint` from LLD-02 §7.7 is accepted but optional: `resolve_unique_key`
already finds the owning table, and requiring the caller to name it invites a
mismatch between the hint and reality (DEV-35).

See: LLD-02 §7.7 (Review Status Tool — SRS-035b, SRS-082a, SRS-089, SRS-091a)
"""

from typing import Any

from ..db.models import (
    ARTIFACT_STATUSES,
    ARTIFACT_TABLES,
    PARENT_CHILD_MAP,
    REVIEWABLE_CHILD_TABLES,
    STRUCTURAL_SUBTYPE_TABLES,
)
from ..errors import McpResult, McpValidationError
from ..validation.common import validate_choice, validate_uuid_format
from ..validation.status import (
    auto_demote_parent_chain,
    check_parent_can_be_approved,
    check_references_resolved,
    validate_artifact_transition,
)
from ._engine import record_to_dict, reject_unknown_arguments
from .context import ToolContext

_TOOL = "set_review_status"

# The tables this tool may target (SRS-091a): artifacts, SourceRequirements,
# and the seven reviewable children. ReviewIssues and the structural subtypes
# are excluded.
STATUS_TARGET_TABLES = ARTIFACT_TABLES | REVIEWABLE_CHILD_TABLES


def handle_set_review_status(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Set a review state (SRS-089), enforcing authority and the invariants."""
    reject_unknown_arguments(
        _TOOL,
        arguments,
        frozenset({"unique_key", "table_hint", "new_status", "review_note", "caller"}),
    )
    caller = arguments.get("caller")
    if caller != ctx.adapter_mode:
        raise McpValidationError.of(
            _TOOL,
            f"caller {caller!r} does not match the server adapter_mode "
            f"{ctx.adapter_mode!r} (SRS-082a)",
            field="caller",
            affected_key=arguments.get("unique_key"),
        )

    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=_TOOL)
    new_status = arguments.get("new_status")
    validate_choice(new_status, ARTIFACT_STATUSES, "new_status", operation=_TOOL)

    with ctx.db.transaction() as conn:
        found = ctx.dal.resolve_unique_key(conn, str(key))
        if found is None:
            raise McpValidationError.of(
                _TOOL,
                f"no record with unique_key {key!r}",
                field="unique_key",
                affected_key=str(key),
            )
        table, record = found

        if table == "ReviewIssues":
            raise McpValidationError.of(
                _TOOL,
                "Use update_review_issue for review-issue status changes (SRS-119).",
                field="unique_key",
                affected_key=str(key),
            )
        if table in STRUCTURAL_SUBTYPE_TABLES:
            raise McpValidationError.of(
                _TOOL,
                f"{table} is a structural subtype and has no status field (SRS-091a).",
                field="unique_key",
                affected_key=str(key),
            )
        if table not in STATUS_TARGET_TABLES:
            raise McpValidationError.of(
                _TOOL,
                f"{table} is not a reviewable table (SRS-091a).",
                field="unique_key",
                affected_key=str(key),
            )

        validate_artifact_transition(
            str(record.status), str(new_status), operation=_TOOL, affected_key=str(key)
        )

        if new_status == "approved":
            if ctx.adapter_mode == "extraction":
                raise McpValidationError.of(
                    _TOOL,
                    "Approval is reserved for manual review (SRS-082a).",
                    field="new_status",
                    affected_key=str(key),
                )
            unresolved = check_references_resolved(conn, ctx.dal, table, record)
            if unresolved:
                raise McpValidationError.of(
                    _TOOL,
                    "cannot approve while these references are unresolved: "
                    f"{', '.join(unresolved)} (SRS-036a)",
                    field="new_status",
                    affected_key=str(key),
                )
            if table in PARENT_CHILD_MAP:
                blockers = check_parent_can_be_approved(conn, ctx.dal, table, int(record.id))
                if blockers:
                    detail = "; ".join(
                        f"{blocker['child_table']} is {blocker['status']}" for blocker in blockers
                    )
                    raise McpValidationError.of(
                        _TOOL,
                        f"cannot approve while children are not approved: {detail} "
                        "(SRS-046, SRS-053)",
                        field="new_status",
                        affected_key=str(key),
                    )

        ctx.dal.update_status(
            conn, table, int(record.id), str(new_status), arguments.get("review_note")
        )

        demoted: list[str] = []
        if new_status != "approved":
            demoted = auto_demote_parent_chain(conn, ctx.dal, table, int(record.id))

        updated = ctx.dal.get_record_by_id(conn, table, int(record.id))

    data = record_to_dict(updated)
    data.pop("id", None)
    data.pop("unique_key", None)
    data["table"] = table
    if demoted:
        data["demoted"] = demoted
    return McpResult(unique_key=str(key), data=data).to_dict()
