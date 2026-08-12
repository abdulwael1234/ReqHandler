"""Port-interface vocabularies and child-type matching.

The value sets repeat the CHECK constraints in V001 so that a bad value is
rejected with a structured SRS-083 error naming the field, rather than
surfacing as a raw `sqlite3.IntegrityError`.

See: LLD-02 §6.4 (Port Interface Validators — SRS-052, SRS-055, SRS-059)
"""

import sqlite3

from ..db.dal import DataAccessLayer
from ..errors import McpValidationError

INTERFACE_TYPES = frozenset({"sender_receiver", "client_server"})  # SRS-052
ARGUMENT_DIRECTIONS = frozenset({"input", "output", "input_output"})  # SRS-059
PORT_DIRECTIONS = frozenset({"provider", "requester"})  # SRS-061
RELATIONSHIP_TYPES = frozenset({"access_point", "trigger"})  # SRS-063

# Child table → the parent interface_type it requires (SRS-055).
CHILD_REQUIRED_INTERFACE_TYPE: dict[str, str] = {
    "InterfaceDataElements": "sender_receiver",
    "ClientServerOperations": "client_server",
}


def validate_child_interface_type(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    port_interface_id: int,
    child_table: str,
    *,
    operation: str,
    field: str,
) -> None:
    """Reject a child whose parent interface is of the wrong type (SRS-055)."""
    expected = CHILD_REQUIRED_INTERFACE_TYPE[child_table]
    parent = dal.get_port_interface_by_id(conn, port_interface_id)
    if parent is None:
        raise McpValidationError.of(
            operation, f"{field} does not resolve to a PortInterfaces record", field=field
        )
    if parent.interface_type != expected:
        raise McpValidationError.of(
            operation,
            f"{child_table} requires a {expected!r} interface; "
            f"parent is {parent.interface_type!r}",
            field=field,
            affected_key=str(parent.unique_key),
        )
