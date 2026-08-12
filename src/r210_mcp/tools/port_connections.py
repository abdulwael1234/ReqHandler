"""Port-connection tools: the connection and its members.

`update_port_connection_member` revalidates the entire connection inside the
member's own transaction, so an update that would leave the connection invalid
rolls back rather than committing a broken graph (SRS-122, LLD-02 §10.3).

See: LLD-02 §7.5 (Port Connection Tools), §10.3 (Transactional Revalidation)
"""

from typing import Any

from ..db.models import ARTIFACT_STATUSES
from ..errors import McpResult, McpValidationError
from ..validation.common import validate_position, validate_uuid_format
from ..validation.port_connections import (
    create_compatibility_review_issue,
    validate_connection_complete,
)
from ._engine import (
    CreateSpec,
    FieldSpec,
    QuerySpec,
    RefSpec,
    UpdateSpec,
    choice_of,
    demote_if_approved,
    record_to_dict,
    reject_status_argument,
    reject_unknown_arguments,
    run_create,
    run_query,
    run_update,
)
from .context import ToolContext

_MEMBER_UPDATE_TOOL = "update_port_connection_member"

_CREATE = CreateSpec(
    tool="create_port_connection",
    table="PortConnections",
    fields=(FieldSpec("description", "description"),),
    refs=(RefSpec("source_requirement_key", "source_requirement_id", "SourceRequirements"),),
)

_UPDATE = UpdateSpec(
    tool="update_port_connection",
    table="PortConnections",
    fields=(FieldSpec("description", "description"),),
    refs=(RefSpec("source_requirement_key", "source_requirement_id", "SourceRequirements"),),
)

_QUERY = QuerySpec(
    tool="query_port_connections",
    table="PortConnections",
    filters=(FieldSpec("status", "status", validator=choice_of(ARTIFACT_STATUSES)),),
)

_CREATE_MEMBER = CreateSpec(
    tool="create_port_connection_member",
    table="PortConnectionMembers",
    fields=(FieldSpec("position", "position", True, validate_position),),
    refs=(
        RefSpec(
            "port_connection_key",
            "port_connection_id",
            "PortConnections",
            required=True,
            parent=True,
        ),
        RefSpec("port_prototype_key", "port_prototype_id", "PortPrototypes", required=True),
    ),
)


def handle_create_port_connection(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a connection and record that compatibility is unverified (SRS-125)."""
    response = run_create(ctx, _CREATE, arguments)
    connection_key = str(response["result"]["unique_key"])
    with ctx.db.transaction() as conn:
        connection = ctx.dal.get_record_by_unique_key(conn, "PortConnections", connection_key)
        create_compatibility_review_issue(
            conn, ctx.dal, connection_key, connection.source_requirement_id
        )
    return response


def handle_update_port_connection(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a port connection."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_port_connections(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query port connections (SRS-086)."""
    return run_query(ctx, _QUERY, arguments)


def handle_create_port_connection_member(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Add a member to a connection (SRS-069, SRS-070)."""
    return run_create(ctx, _CREATE_MEMBER, arguments)


def handle_update_port_connection_member(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update a member and revalidate the whole connection (SRS-122).

    Written out rather than driven by the engine because the revalidation must
    happen inside the same transaction as the update: `transaction()` rolls
    back on the raised error, so a rejected revalidation undoes the change
    (LLD-02 §10.3).
    """
    reject_status_argument(_MEMBER_UPDATE_TOOL, arguments)
    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=_MEMBER_UPDATE_TOOL)
    reject_unknown_arguments(
        _MEMBER_UPDATE_TOOL,
        arguments,
        frozenset({"unique_key", "port_prototype_key", "position"}),
    )

    with ctx.db.transaction() as conn:
        member = ctx.dal.get_record_by_unique_key(conn, "PortConnectionMembers", str(key))
        if member is None:
            raise McpValidationError.of(
                _MEMBER_UPDATE_TOOL,
                f"no PortConnectionMembers record with unique_key {key!r}",
                field="unique_key",
                affected_key=str(key),
            )

        changed: dict[str, Any] = {}
        if "position" in arguments:
            validate_position(arguments["position"], "position", operation=_MEMBER_UPDATE_TOOL)
            changed["position"] = arguments["position"]
        if "port_prototype_key" in arguments:
            target = ctx.dal.get_record_by_unique_key(
                conn, "PortPrototypes", str(arguments["port_prototype_key"])
            )
            if target is None:
                raise McpValidationError.of(
                    _MEMBER_UPDATE_TOOL,
                    "port_prototype_key does not resolve to an existing PortPrototypes record",
                    field="port_prototype_key",
                    affected_key=str(arguments["port_prototype_key"]),
                )
            changed["port_prototype_id"] = target.id

        if changed:
            ctx.dal.update_record(conn, "PortConnectionMembers", member.id, changed)
        demoted = demote_if_approved(conn, ctx.dal, "PortConnectionMembers", member.id, changed)
        validate_connection_complete(
            conn, ctx.dal, int(member.port_connection_id), operation=_MEMBER_UPDATE_TOOL
        )
        updated = ctx.dal.get_record_by_id(conn, "PortConnectionMembers", member.id)

    data = record_to_dict(updated)
    data.pop("id", None)
    data.pop("unique_key", None)
    if demoted:
        data["demoted"] = demoted
    return McpResult(unique_key=str(key), data=data).to_dict()
