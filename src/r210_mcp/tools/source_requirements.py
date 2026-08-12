"""Source-requirement tools: create, update, query.

See: LLD-02 §7.1 (Source Requirement Tools — SRS-085)
"""

from typing import Any

from ..db.models import ARTIFACT_STATUSES
from ..validation.common import validate_not_empty
from ._engine import (
    CreateSpec,
    FieldSpec,
    QuerySpec,
    UpdateSpec,
    choice_of,
    run_create,
    run_query,
    run_update,
)
from .context import ToolContext

_CREATE = CreateSpec(
    tool="create_source_requirement",
    table="SourceRequirements",
    fields=(
        FieldSpec("source_reference", "source_reference", True, validate_not_empty),
        FieldSpec("source_text", "source_text"),
        FieldSpec("review_note", "review_note"),
    ),
)

_UPDATE = UpdateSpec(
    tool="update_source_requirement",
    table="SourceRequirements",
    fields=(
        FieldSpec("source_reference", "source_reference", validator=validate_not_empty),
        FieldSpec("source_text", "source_text"),
        FieldSpec("review_note", "review_note"),
    ),
)

_QUERY = QuerySpec(
    tool="query_source_requirements",
    table="SourceRequirements",
    filters=(
        FieldSpec("status", "status", validator=choice_of(ARTIFACT_STATUSES)),
        FieldSpec("source_reference", "source_reference"),
    ),
)


def handle_create_source_requirement(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a source requirement (SRS-085)."""
    return run_create(ctx, _CREATE, arguments)


def handle_update_source_requirement(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a source requirement; `status` is rejected (SRS-091a)."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_source_requirements(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Query source requirements (SRS-085)."""
    return run_query(ctx, _QUERY, arguments)
