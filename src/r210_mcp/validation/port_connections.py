"""Port-connection completeness validation.

SRS-071 leaves interface compatibility undefined (TBD). SRS-125 therefore
requires the server to accept the connection but record an `incomplete`
ReviewIssue, so that an unverified connection is never silently treated as
validated.

See: LLD-02 §6.5 (Port Connection Validators — SRS-069–072, SRS-122, SRS-125)
"""

import sqlite3
from uuid import uuid4

from ..db.dal import DataAccessLayer
from ..errors import McpValidationError


def validate_connection_complete(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    connection_id: int,
    *,
    operation: str,
    field: str = "port_prototype_key",
) -> None:
    """Re-check every rule over a whole connection (SRS-122).

    Raises on the first failure so that the caller's transaction rolls back.
    LLD-02 §6.5 returns a list of errors, but a partially-valid connection must
    not be committed, and `transaction()` rolls back on the exception
    (LLD-02 §10.3).

    `field` names the argument the caller actually supplied: `create_port_connection`
    takes a `members` array, while the member tools take `port_prototype_key`.
    SRS-109 requires the error to name the field the caller can act on.
    """
    connection = dal.get_record_by_id(conn, "PortConnections", connection_id)
    affected_key = None if connection is None else str(connection.unique_key)

    members = dal.get_children(conn, "PortConnectionMembers", "port_connection_id", connection_id)
    if not members:
        raise McpValidationError.of(
            operation,
            "connection has no members; at least one provider and one requester "
            "are required (SRS-072)",
            field=field,
            affected_key=affected_key,
        )

    prototype_ids = [member.port_prototype_id for member in members]
    if len(set(prototype_ids)) != len(prototype_ids):
        raise McpValidationError.of(
            operation,
            "connection contains a duplicate port_prototype reference (SRS-070)",
            field=field,
            affected_key=affected_key,
        )

    directions: list[str] = []
    for prototype_id in prototype_ids:
        prototype = dal.get_record_by_id(conn, "PortPrototypes", prototype_id)
        if prototype is None:
            raise McpValidationError.of(
                operation,
                f"member references PortPrototypes id {prototype_id}, which does not exist "
                "(SRS-069)",
                field=field,
                affected_key=affected_key,
            )
        directions.append(str(prototype.direction))

    for required in ("provider", "requester"):
        if required not in directions:
            raise McpValidationError.of(
                operation,
                f"connection requires at least one {required} member (SRS-072)",
                field=field,
                affected_key=affected_key,
            )


def create_compatibility_review_issue(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    connection_key: str,
    source_requirement_id: int | None,
) -> str:
    """Record that compatibility could not be verified (SRS-125)."""
    issue_key = str(uuid4())
    dal.insert_review_issue(
        conn,
        unique_key=issue_key,
        issue_type="incomplete",
        message=(
            "Interface compatibility was not verified: the SRS-071 compatibility "
            "rules are not yet defined (SRS-125)."
        ),
        source_requirement_id=source_requirement_id,
        artifact_type="port_connection",
        artifact_unique_key=connection_key,
    )
    return issue_key
