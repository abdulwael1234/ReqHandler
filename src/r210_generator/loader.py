"""Database snapshot loading.

LLD-04 §9.2 sketches this with a raw `sqlite3.connect`, its own pragmas and its
own `BEGIN`. Following that literally would put a second SQL site and a fourth
copy of the connection setup into the repository, against the architecture the
project holds elsewhere. The loader therefore goes through the existing layers
— `DatabaseConnection.read_snapshot()` for the consistent read transaction and
`DataAccessLayer.query_table()` for every table — and contains no SQL (DEV-45).

See: LLD-04 §9 (Data Loading)
"""

from typing import Any

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer

from .models import DatabaseSnapshot

# Snapshot field ← table. Ordering within each table is the DAL's deterministic
# order: `(parent_fk, position)` for ordered children, `id` otherwise (SRS-108).
SNAPSHOT_TABLES: tuple[tuple[str, str], ...] = (
    ("source_requirements", "SourceRequirements"),
    ("type_definitions", "TypeDefinitions"),
    ("simple_type_definitions", "SimpleTypeDefinitions"),
    ("array_type_definitions", "ArrayTypeDefinitions"),
    ("struct_elements", "StructElements"),
    ("enum_values", "EnumValues"),
    ("port_interfaces", "PortInterfaces"),
    ("interface_data_elements", "InterfaceDataElements"),
    ("client_server_operations", "ClientServerOperations"),
    ("operation_arguments", "OperationArguments"),
    ("port_prototypes", "PortPrototypes"),
    ("port_prototype_functions", "PortPrototypeFunctions"),
    ("port_connections", "PortConnections"),
    ("port_connection_members", "PortConnectionMembers"),
    ("review_issues", "ReviewIssues"),
)


class Loader:
    """Load complete database state for generation (LLD-04 §9)."""

    def __init__(self, dal: DataAccessLayer | None = None) -> None:
        self._dal = dal or DataAccessLayer()

    def load_all(self, db_path: str) -> DatabaseSnapshot:
        """Read every table inside one transaction, so all views agree.

        Without the surrounding transaction a concurrent commit could land
        between two SELECTs and produce a snapshot that never existed.
        """
        db = DatabaseConnection(db_path)
        loaded: dict[str, Any] = {}
        with db.read_snapshot() as conn:
            for attribute, table in SNAPSHOT_TABLES:
                loaded[attribute] = tuple(self._dal.query_table(conn, table))

        # LLD-04 §9.2 orders TypeDefinitions by `kind, name COLLATE NOCASE, id`
        # rather than by id. Applying it here rather than adding a second
        # ordering path to the finished DAL: the rows are already in memory,
        # and a Python sort is exactly as deterministic (DEV-45).
        loaded["type_definitions"] = tuple(
            sorted(loaded["type_definitions"], key=lambda r: (r.kind, r.name.lower(), r.id))
        )
        return DatabaseSnapshot(**loaded)
