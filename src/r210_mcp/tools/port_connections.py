"""Port-connection tools: the connection and its members.

`update_port_connection_member` revalidates the entire connection inside the
member's own transaction, so an update that would leave the connection invalid
rolls back rather than committing a broken graph (SRS-122, LLD-02 §10.3).

See: LLD-02 §7.5 (Port Connection Tools), §10.3 (Transactional Revalidation)
"""

import sqlite3
from typing import Any
from uuid import uuid4

from ..db.dal import DataAccessLayer
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
    initial_status,
    record_to_dict,
    reject_status_argument,
    reject_unknown_arguments,
    run_create,
    run_query,
    run_update,
)
from .context import ToolContext

_MEMBER_UPDATE_TOOL = "update_port_connection_member"

_CREATE_TOOL = "create_port_connection"
_MEMBER_CREATE_TOOL = "create_port_connection_member"

_CREATE_ARGUMENTS = frozenset(
    {"description", "source_requirement_key", "members", "initial_status"}
)


def _revalidate_connection(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    unique_key: str,
    source_requirement_id: int | None,
) -> None:
    """Re-check the whole connection after a member is added (SRS-122).

    Runs inside the member's create transaction, so a member that would leave
    the connection invalid is rolled back rather than committed (LLD-02 §7.5).
    """
    member = dal.get_record_by_unique_key(conn, "PortConnectionMembers", unique_key)
    if member is None:  # pragma: no cover - the insert above guarantees it
        return
    validate_connection_complete(
        conn, dal, int(member.port_connection_id), operation=_MEMBER_CREATE_TOOL
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
    tool=_MEMBER_CREATE_TOOL,
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
    post_create=_revalidate_connection,
)


def _validate_members(arguments: dict[str, Any]) -> list[dict[str, Any]]:
    """Check the members array before any row is written (LLD-02 §7.5 steps 1-2).

    A connection is meaningless without members — SRS-072 requires at least one
    provider and one requester — so `members` is required rather than something
    added afterwards. Catching duplicates and bad positions here means the
    error names `members`, which is the argument the caller supplied.
    """
    members = arguments.get("members")
    if not isinstance(members, list) or not members:
        raise McpValidationError.of(
            _CREATE_TOOL,
            "members must not be empty; a connection requires at least one provider "
            "and one requester (SRS-072)",
            field="members",
        )

    keys: list[str] = []
    positions: list[int] = []
    for index, member in enumerate(members):
        if not isinstance(member, dict):
            raise McpValidationError.of(
                _CREATE_TOOL,
                f"members[{index}] must be an object with port_prototype_key and position",
                field="members",
            )
        key = member.get("port_prototype_key")
        if not isinstance(key, str):
            raise McpValidationError.of(
                _CREATE_TOOL,
                f"members[{index}].port_prototype_key is required",
                field="members",
            )
        validate_position(member.get("position"), f"members[{index}].position",
                          operation=_CREATE_TOOL)
        keys.append(key)
        positions.append(int(member["position"]))

    if len(set(positions)) != len(positions):
        raise McpValidationError.of(
            _CREATE_TOOL,
            "member position values must be unique within a connection (SRS-037)",
            field="members",
        )
    if len(set(keys)) != len(keys):
        raise McpValidationError.of(
            _CREATE_TOOL,
            "members contains a duplicate port_prototype_key; a prototype may appear "
            "at most once per connection (SRS-070)",
            field="members",
        )
    return members


def handle_create_port_connection(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a connection with all its members, atomically (LLD-02 §7.5).

    The parent, every member, the completeness check and the SRS-125
    compatibility issue all share one transaction. An invalid connection is
    never persisted, not even briefly: `transaction()` rolls the whole thing
    back on the raised error (SRS-084, SRS-122).
    """
    reject_unknown_arguments(_CREATE_TOOL, arguments, _CREATE_ARGUMENTS)
    members = _validate_members(arguments)
    status = initial_status(_CREATE_TOOL, arguments)
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

        connection_id = ctx.dal.insert_port_connection(
            conn, unique_key, arguments.get("description"), source_requirement_id, status
        )

        for member in members:
            key = str(member["port_prototype_key"])
            prototype = ctx.dal.get_port_prototype_by_key(conn, key)
            if prototype is None:
                raise McpValidationError.of(
                    _CREATE_TOOL,
                    f"members[].port_prototype_key {key!r} does not resolve to an "
                    "existing PortPrototypes record (SRS-069)",
                    field="members",
                    affected_key=key,
                )
            ctx.dal.insert_port_connection_member(
                conn, str(uuid4()), connection_id, prototype.id, int(member["position"])
            )

        validate_connection_complete(
            conn, ctx.dal, connection_id, operation=_CREATE_TOOL, field="members"
        )
        create_compatibility_review_issue(conn, ctx.dal, unique_key, source_requirement_id)
        created = ctx.dal.get_record_by_id(conn, "PortConnections", connection_id)

    data = record_to_dict(created)
    data.pop("id", None)
    data.pop("unique_key", None)
    return McpResult(unique_key=unique_key, data=data).to_dict()


def handle_update_port_connection(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a port connection."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_port_connections(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query port connections (SRS-086)."""
    return run_query(ctx, _QUERY, arguments)


def handle_create_port_connection_member(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Add a member and revalidate the whole connection (SRS-069, SRS-070, SRS-122).

    Revalidation runs through `post_create`, inside the insert's own
    transaction, so a member that would invalidate the connection is rolled
    back (LLD-02 §7.5).
    """
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
