"""Data Access Layer — all SQL queries for CRUD operations.

Provides DataAccessLayer class with methods for:
- Record insertion (all 15 application tables)
- Record update (permitted fields only)
- Record query with filters
- Unique-key resolution across tables
- Status updates

The layer performs no validation: status transitions, duplicate-warning policy,
parent demotion, and connection rules belong to the validation layer and the
tool handlers (LLD-02 §5.1, §6). Constraint violations raised by SQLite
propagate to the caller, which is the layer that knows the operation name and
affected key needed to build an McpError.

See: LLD-02 §5 (Data Access Layer), §7 (Tool Handlers reference DAL for all DB
operations)
"""

import sqlite3
from dataclasses import fields
from typing import Any, TypeVar

from .models import (
    CHILD_PARENT_MAP,
    TABLE_RECORD_MAP,
    ArrayTypeDefinitionRecord,
    ClientServerOperationRecord,
    EnumValueRecord,
    InterfaceDataElementRecord,
    OperationArgumentRecord,
    PortConnectionMemberRecord,
    PortConnectionRecord,
    PortInterfaceRecord,
    PortPrototypeFunctionRecord,
    PortPrototypeRecord,
    ReviewIssueRecord,
    SimpleTypeDefinitionRecord,
    SourceRequirementRecord,
    StructElementRecord,
    TypeDefinitionRecord,
)

_R = TypeVar("_R")

# The default review state every new record carries (SRS-035a). Repeated here
# so callers may omit the argument; the column default in the schema is the
# authoritative one.
PENDING_REVIEW = "pending_review"

# Tables the DAL reads and writes. `schema_version` is owned by the initializer
# (LLD-05 §4.3) and carries no unique_key, so it is outside the DAL surface.
DAL_TABLES = frozenset(TABLE_RECORD_MAP) - {"schema_version"}

# Column names per table, derived from the record dataclasses rather than
# written out a second time. models.py guarantees that record field order
# matches database column order, and Phase 1's
# `test_dataclass_fields_match_table_columns_in_order` enforces it, so these
# tuples cannot drift from the schema (DEV-11).
TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    table: tuple(f.name for f in fields(record))
    for table, record in TABLE_RECORD_MAP.items()
    if table in DAL_TABLES
}

# Record dataclass → table name. Keying the generic core on the record class
# instead of a table string makes a table/record mismatch unrepresentable.
RECORD_TABLE_MAP: dict[type[Any], str] = {
    TABLE_RECORD_MAP[table]: table for table in DAL_TABLES
}


class DataAccessLayer:
    """Low-level SQL operations. All methods accept a connection parameter.

    Every table and column name is resolved through the registries above before
    it reaches a statement, and every value is bound with a ``?`` placeholder.
    SQLite cannot parameterize identifiers, so that lookup is what keeps a
    table-driven layer free of string-interpolated caller input.
    """

    # ── Generic core ─────────────────────────────────────────────────────

    def _table_of(self, record_type: type[Any]) -> str:
        table = RECORD_TABLE_MAP.get(record_type)
        if table is None:
            raise ValueError(f"{record_type.__name__} is not a DAL record type")
        return table

    def _check_table(self, table: str) -> str:
        if table not in DAL_TABLES:
            raise ValueError(f"unknown table: {table!r}")
        return table

    def _writable_columns(self, table: str) -> tuple[str, ...]:
        """Columns a caller may write. `id` is assigned by SQLite."""
        return tuple(name for name in TABLE_COLUMNS[table] if name != "id")

    def _reject_unknown(self, table: str, names: Any, permitted: tuple[str, ...]) -> None:
        unknown = sorted(set(names) - set(permitted))
        if unknown:
            raise ValueError(f"unknown column(s) for {table}: {', '.join(unknown)}")

    def _select_list(self, table: str) -> str:
        return ", ".join(f'"{name}"' for name in TABLE_COLUMNS[table])

    def _order_by(self, table: str) -> str:
        """Deterministic ordering (SRS-108).

        Ordered child tables sort by parent then position so that a query
        spanning several parents still returns each parent's children in
        declaration order; everything else sorts by insertion order.
        """
        relation = CHILD_PARENT_MAP.get(table)
        if relation is not None and "position" in TABLE_COLUMNS[table]:
            return f'"{relation.fk_column}", "position"'
        return '"id"'

    def _where(self, table: str, filters: dict[str, Any] | None) -> tuple[str, tuple[Any, ...]]:
        if not filters:
            return "", ()
        self._reject_unknown(table, filters, TABLE_COLUMNS[table])
        clauses: list[str] = []
        params: list[Any] = []
        for name, value in filters.items():
            # `= NULL` matches nothing in SQL; an explicit None filter means
            # "unresolved", which is a case SRS-036a expects callers to query.
            if value is None:
                clauses.append(f'"{name}" IS NULL')
            else:
                clauses.append(f'"{name}" = ?')
                params.append(value)
        return " WHERE " + " AND ".join(clauses), tuple(params)

    def _insert(
        self, conn: sqlite3.Connection, record_type: type[Any], values: dict[str, Any]
    ) -> int:
        table = self._table_of(record_type)
        permitted = self._writable_columns(table)
        self._reject_unknown(table, values, permitted)
        # Iterate the schema order, not the caller's dict order.
        names = [name for name in permitted if name in values]
        columns = ", ".join(f'"{name}"' for name in names)
        placeholders = ", ".join("?" for _ in names)
        cursor = conn.execute(
            f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',
            tuple(values[name] for name in names),
        )
        record_id = cursor.lastrowid
        if record_id is None:
            raise RuntimeError(f"INSERT into {table} returned no row id")
        return record_id

    def _update(
        self,
        conn: sqlite3.Connection,
        record_type: type[Any],
        record_id: int,
        values: dict[str, Any],
    ) -> None:
        table = self._table_of(record_type)
        self._reject_unknown(table, values, self._writable_columns(table))
        if not values:
            return
        assignments = ", ".join(f'"{name}" = ?' for name in values)
        conn.execute(
            f'UPDATE "{table}" SET {assignments} WHERE "id" = ?',
            (*values.values(), record_id),
        )

    def _to_record(self, record_type: type[_R], row: sqlite3.Row) -> _R:
        """Expand a row positionally into its record dataclass (LLD-02 §3.3)."""
        return record_type(*row)

    def _get_by(
        self,
        conn: sqlite3.Connection,
        record_type: type[_R],
        column: str,
        value: Any,
    ) -> _R | None:
        table = self._table_of(record_type)
        self._reject_unknown(table, {column}, TABLE_COLUMNS[table])
        row = conn.execute(
            f'SELECT {self._select_list(table)} FROM "{table}" WHERE "{column}" = ?',
            (value,),
        ).fetchone()
        return None if row is None else self._to_record(record_type, row)

    def _query(
        self,
        conn: sqlite3.Connection,
        record_type: type[_R],
        filters: dict[str, Any] | None = None,
    ) -> list[_R]:
        table = self._table_of(record_type)
        where, params = self._where(table, filters)
        rows = conn.execute(
            f'SELECT {self._select_list(table)} FROM "{table}"{where}'
            f" ORDER BY {self._order_by(table)}",
            params,
        ).fetchall()
        return [self._to_record(record_type, row) for row in rows]

    # ── Source Requirements (LLD-01 §3.1) ────────────────────────────────

    def insert_source_requirement(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        source_reference: str,
        source_text: str | None = None,
        status: str = PENDING_REVIEW,
        review_note: str | None = None,
    ) -> int:
        return self._insert(
            conn,
            SourceRequirementRecord,
            {
                "unique_key": unique_key,
                "source_reference": source_reference,
                "source_text": source_text,
                "status": status,
                "review_note": review_note,
            },
        )

    def update_source_requirement(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, SourceRequirementRecord, record_id, fields)

    def get_source_requirement_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> SourceRequirementRecord | None:
        return self._get_by(conn, SourceRequirementRecord, "unique_key", unique_key)

    def query_source_requirements(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[SourceRequirementRecord]:
        return self._query(conn, SourceRequirementRecord, filters)

    # ── Type Definitions (LLD-01 §3.2–§3.6) ──────────────────────────────

    def insert_type_definition(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        name: str,
        kind: str,
        description: str | None = None,
        source_requirement_id: int | None = None,
        status: str = PENDING_REVIEW,
        review_note: str | None = None,
    ) -> int:
        return self._insert(
            conn,
            TypeDefinitionRecord,
            {
                "unique_key": unique_key,
                "name": name,
                "kind": kind,
                "description": description,
                "source_requirement_id": source_requirement_id,
                "status": status,
                "review_note": review_note,
            },
        )

    def update_type_definition(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, TypeDefinitionRecord, record_id, fields)

    def get_type_definition_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> TypeDefinitionRecord | None:
        return self._get_by(conn, TypeDefinitionRecord, "unique_key", unique_key)

    def get_type_definition_by_id(
        self, conn: sqlite3.Connection, record_id: int
    ) -> TypeDefinitionRecord | None:
        return self._get_by(conn, TypeDefinitionRecord, "id", record_id)

    def query_type_definitions(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[TypeDefinitionRecord]:
        return self._query(conn, TypeDefinitionRecord, filters)

    def insert_simple_type_definition(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        type_definition_id: int,
        base_type: str,
        size: str | None = None,
    ) -> int:
        return self._insert(
            conn,
            SimpleTypeDefinitionRecord,
            {
                "unique_key": unique_key,
                "type_definition_id": type_definition_id,
                "base_type": base_type,
                "size": size,
            },
        )

    def update_simple_type_definition(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, SimpleTypeDefinitionRecord, record_id, fields)

    def get_simple_type_definition_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> SimpleTypeDefinitionRecord | None:
        return self._get_by(conn, SimpleTypeDefinitionRecord, "unique_key", unique_key)

    def get_simple_type_definition_by_parent(
        self, conn: sqlite3.Connection, type_definition_id: int
    ) -> SimpleTypeDefinitionRecord | None:
        """The one detail row for a `simple_typedef` parent (SRS-038a)."""
        return self._get_by(
            conn, SimpleTypeDefinitionRecord, "type_definition_id", type_definition_id
        )

    def insert_array_type_definition(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        type_definition_id: int,
        element_type_id: int | None,
        array_size: int,
    ) -> int:
        return self._insert(
            conn,
            ArrayTypeDefinitionRecord,
            {
                "unique_key": unique_key,
                "type_definition_id": type_definition_id,
                "element_type_id": element_type_id,
                "array_size": array_size,
            },
        )

    def update_array_type_definition(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, ArrayTypeDefinitionRecord, record_id, fields)

    def get_array_type_definition_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> ArrayTypeDefinitionRecord | None:
        return self._get_by(conn, ArrayTypeDefinitionRecord, "unique_key", unique_key)

    def get_array_type_definition_by_parent(
        self, conn: sqlite3.Connection, type_definition_id: int
    ) -> ArrayTypeDefinitionRecord | None:
        """The one detail row for an `array` parent (SRS-038a)."""
        return self._get_by(
            conn, ArrayTypeDefinitionRecord, "type_definition_id", type_definition_id
        )

    def insert_struct_element(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        struct_type_id: int,
        name: str,
        element_type_id: int | None,
        position: int,
        description: str | None = None,
        status: str = PENDING_REVIEW,
    ) -> int:
        return self._insert(
            conn,
            StructElementRecord,
            {
                "unique_key": unique_key,
                "struct_type_id": struct_type_id,
                "name": name,
                "element_type_id": element_type_id,
                "position": position,
                "description": description,
                "status": status,
            },
        )

    def update_struct_element(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, StructElementRecord, record_id, fields)

    def get_struct_element_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> StructElementRecord | None:
        return self._get_by(conn, StructElementRecord, "unique_key", unique_key)

    def query_struct_elements(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[StructElementRecord]:
        return self._query(conn, StructElementRecord, filters)

    def insert_enum_value(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        enum_type_id: int,
        name: str,
        value: str | None,
        position: int,
        description: str | None = None,
        status: str = PENDING_REVIEW,
    ) -> int:
        return self._insert(
            conn,
            EnumValueRecord,
            {
                "unique_key": unique_key,
                "enum_type_id": enum_type_id,
                "name": name,
                "value": value,
                "position": position,
                "description": description,
                "status": status,
            },
        )

    def update_enum_value(self, conn: sqlite3.Connection, record_id: int, **fields: Any) -> None:
        self._update(conn, EnumValueRecord, record_id, fields)

    def get_enum_value_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> EnumValueRecord | None:
        return self._get_by(conn, EnumValueRecord, "unique_key", unique_key)

    def query_enum_values(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[EnumValueRecord]:
        return self._query(conn, EnumValueRecord, filters)

    # ── Port Interfaces (LLD-01 §3.7–§3.10) ──────────────────────────────

    def insert_port_interface(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        name: str,
        interface_type: str,
        description: str | None = None,
        source_requirement_id: int | None = None,
        status: str = PENDING_REVIEW,
        review_note: str | None = None,
    ) -> int:
        return self._insert(
            conn,
            PortInterfaceRecord,
            {
                "unique_key": unique_key,
                "name": name,
                "description": description,
                "source_requirement_id": source_requirement_id,
                "interface_type": interface_type,
                "status": status,
                "review_note": review_note,
            },
        )

    def update_port_interface(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, PortInterfaceRecord, record_id, fields)

    def get_port_interface_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> PortInterfaceRecord | None:
        return self._get_by(conn, PortInterfaceRecord, "unique_key", unique_key)

    def get_port_interface_by_id(
        self, conn: sqlite3.Connection, record_id: int
    ) -> PortInterfaceRecord | None:
        return self._get_by(conn, PortInterfaceRecord, "id", record_id)

    def query_port_interfaces(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[PortInterfaceRecord]:
        return self._query(conn, PortInterfaceRecord, filters)

    def insert_interface_data_element(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        port_interface_id: int,
        name: str,
        type_definition_id: int | None,
        position: int,
        description: str | None = None,
        status: str = PENDING_REVIEW,
    ) -> int:
        return self._insert(
            conn,
            InterfaceDataElementRecord,
            {
                "unique_key": unique_key,
                "port_interface_id": port_interface_id,
                "name": name,
                "type_definition_id": type_definition_id,
                "position": position,
                "description": description,
                "status": status,
            },
        )

    def update_interface_data_element(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, InterfaceDataElementRecord, record_id, fields)

    def get_interface_data_element_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> InterfaceDataElementRecord | None:
        return self._get_by(conn, InterfaceDataElementRecord, "unique_key", unique_key)

    def query_interface_data_elements(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[InterfaceDataElementRecord]:
        return self._query(conn, InterfaceDataElementRecord, filters)

    def insert_client_server_operation(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        port_interface_id: int,
        name: str,
        position: int,
        description: str | None = None,
        status: str = PENDING_REVIEW,
    ) -> int:
        return self._insert(
            conn,
            ClientServerOperationRecord,
            {
                "unique_key": unique_key,
                "port_interface_id": port_interface_id,
                "name": name,
                "position": position,
                "description": description,
                "status": status,
            },
        )

    def update_client_server_operation(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, ClientServerOperationRecord, record_id, fields)

    def get_client_server_operation_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> ClientServerOperationRecord | None:
        return self._get_by(conn, ClientServerOperationRecord, "unique_key", unique_key)

    def query_client_server_operations(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[ClientServerOperationRecord]:
        return self._query(conn, ClientServerOperationRecord, filters)

    def insert_operation_argument(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        operation_id: int,
        name: str,
        type_definition_id: int | None,
        direction: str,
        position: int,
        status: str = PENDING_REVIEW,
    ) -> int:
        return self._insert(
            conn,
            OperationArgumentRecord,
            {
                "unique_key": unique_key,
                "operation_id": operation_id,
                "name": name,
                "type_definition_id": type_definition_id,
                "direction": direction,
                "position": position,
                "status": status,
            },
        )

    def update_operation_argument(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, OperationArgumentRecord, record_id, fields)

    def get_operation_argument_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> OperationArgumentRecord | None:
        return self._get_by(conn, OperationArgumentRecord, "unique_key", unique_key)

    def query_operation_arguments(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[OperationArgumentRecord]:
        return self._query(conn, OperationArgumentRecord, filters)

    # ── Port Prototypes (LLD-01 §3.11–§3.12) ─────────────────────────────

    def insert_port_prototype(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        name: str,
        direction: str,
        component_reference: str,
        description: str | None = None,
        source_requirement_id: int | None = None,
        port_interface_id: int | None = None,
        status: str = PENDING_REVIEW,
        review_note: str | None = None,
    ) -> int:
        return self._insert(
            conn,
            PortPrototypeRecord,
            {
                "unique_key": unique_key,
                "name": name,
                "description": description,
                "source_requirement_id": source_requirement_id,
                "port_interface_id": port_interface_id,
                "direction": direction,
                "component_reference": component_reference,
                "status": status,
                "review_note": review_note,
            },
        )

    def update_port_prototype(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, PortPrototypeRecord, record_id, fields)

    def get_port_prototype_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> PortPrototypeRecord | None:
        return self._get_by(conn, PortPrototypeRecord, "unique_key", unique_key)

    def get_port_prototype_by_id(
        self, conn: sqlite3.Connection, prototype_id: int
    ) -> PortPrototypeRecord | None:
        return self._get_by(conn, PortPrototypeRecord, "id", prototype_id)

    def query_port_prototypes(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[PortPrototypeRecord]:
        return self._query(conn, PortPrototypeRecord, filters)

    def insert_port_prototype_function(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        port_prototype_id: int,
        function_name: str,
        relationship_type: str,
        status: str = PENDING_REVIEW,
    ) -> int:
        return self._insert(
            conn,
            PortPrototypeFunctionRecord,
            {
                "unique_key": unique_key,
                "port_prototype_id": port_prototype_id,
                "function_name": function_name,
                "relationship_type": relationship_type,
                "status": status,
            },
        )

    def update_port_prototype_function(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, PortPrototypeFunctionRecord, record_id, fields)

    def get_port_prototype_function_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> PortPrototypeFunctionRecord | None:
        return self._get_by(conn, PortPrototypeFunctionRecord, "unique_key", unique_key)

    def query_port_prototype_functions(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[PortPrototypeFunctionRecord]:
        return self._query(conn, PortPrototypeFunctionRecord, filters)

    # ── Port Connections (LLD-01 §3.13–§3.14) ────────────────────────────

    def insert_port_connection(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        description: str | None = None,
        source_requirement_id: int | None = None,
        status: str = PENDING_REVIEW,
        review_note: str | None = None,
    ) -> int:
        return self._insert(
            conn,
            PortConnectionRecord,
            {
                "unique_key": unique_key,
                "description": description,
                "source_requirement_id": source_requirement_id,
                "status": status,
                "review_note": review_note,
            },
        )

    def update_port_connection(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, PortConnectionRecord, record_id, fields)

    def get_port_connection_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> PortConnectionRecord | None:
        return self._get_by(conn, PortConnectionRecord, "unique_key", unique_key)

    def query_port_connections(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[PortConnectionRecord]:
        return self._query(conn, PortConnectionRecord, filters)

    def insert_port_connection_member(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        port_connection_id: int,
        port_prototype_id: int,
        position: int,
        status: str = PENDING_REVIEW,
    ) -> int:
        return self._insert(
            conn,
            PortConnectionMemberRecord,
            {
                "unique_key": unique_key,
                "port_connection_id": port_connection_id,
                "port_prototype_id": port_prototype_id,
                "position": position,
                "status": status,
            },
        )

    def update_port_connection_member(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, PortConnectionMemberRecord, record_id, fields)

    def get_port_connection_member_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> PortConnectionMemberRecord | None:
        return self._get_by(conn, PortConnectionMemberRecord, "unique_key", unique_key)

    def get_connection_members(
        self, conn: sqlite3.Connection, connection_id: int
    ) -> list[PortConnectionMemberRecord]:
        """Members of one connection, in position order (LLD-02 §5.1)."""
        return self._query(
            conn, PortConnectionMemberRecord, {"port_connection_id": connection_id}
        )

    def query_port_connection_members(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[PortConnectionMemberRecord]:
        return self._query(conn, PortConnectionMemberRecord, filters)

    # ── Review Issues (LLD-01 §3.15) ─────────────────────────────────────

    def insert_review_issue(
        self,
        conn: sqlite3.Connection,
        unique_key: str,
        issue_type: str,
        message: str,
        source_requirement_id: int | None = None,
        artifact_type: str | None = None,
        artifact_unique_key: str | None = None,
        status: str = "pending",
        resolution: str | None = None,
    ) -> int:
        return self._insert(
            conn,
            ReviewIssueRecord,
            {
                "unique_key": unique_key,
                "source_requirement_id": source_requirement_id,
                "artifact_type": artifact_type,
                "artifact_unique_key": artifact_unique_key,
                "issue_type": issue_type,
                "message": message,
                "status": status,
                "resolution": resolution,
            },
        )

    def update_review_issue(
        self, conn: sqlite3.Connection, record_id: int, **fields: Any
    ) -> None:
        self._update(conn, ReviewIssueRecord, record_id, fields)

    def get_review_issue_by_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> ReviewIssueRecord | None:
        return self._get_by(conn, ReviewIssueRecord, "unique_key", unique_key)

    def query_review_issues(
        self, conn: sqlite3.Connection, filters: dict[str, Any] | None = None
    ) -> list[ReviewIssueRecord]:
        return self._query(conn, ReviewIssueRecord, filters)

    # ── Cross-cutting ────────────────────────────────────────────────────

    def update_status(
        self,
        conn: sqlite3.Connection,
        table: str,
        record_id: int,
        new_status: str,
        review_note: str | None = None,
    ) -> None:
        """Write a review state.

        Whether the transition is permitted is not decided here — that is the
        validation layer's job (SRS-035b). A `review_note` is silently ignored
        when the table has no such column, as required by SRS-091a.
        """
        self._check_table(table)
        columns = TABLE_COLUMNS[table]
        if "status" not in columns:
            raise ValueError(f"{table} has no status column")
        if "review_note" not in columns:
            review_note = None

        if review_note is None:
            conn.execute(
                f'UPDATE "{table}" SET "status" = ? WHERE "id" = ?', (new_status, record_id)
            )
        else:
            conn.execute(
                f'UPDATE "{table}" SET "status" = ?, "review_note" = ? WHERE "id" = ?',
                (new_status, review_note, record_id),
            )

    def get_record_by_unique_key(
        self, conn: sqlite3.Connection, table: str, unique_key: str
    ) -> Any:
        """Fetch from a table named at runtime.

        Returns an instance of `TABLE_RECORD_MAP[table]`, or None. The concrete
        type is not statically known because the table is caller-supplied; use
        the per-table getters where the table is fixed.
        """
        self._check_table(table)
        return self._get_by(conn, TABLE_RECORD_MAP[table], "unique_key", unique_key)

    def get_children_statuses(
        self, conn: sqlite3.Connection, child_table: str, fk_column: str, parent_id: int
    ) -> list[str]:
        """Review states of one parent's children, for approval rules (SRS-046, SRS-053)."""
        self._check_table(child_table)
        columns = TABLE_COLUMNS[child_table]
        self._reject_unknown(child_table, {fk_column}, columns)
        if "status" not in columns:
            raise ValueError(f"{child_table} has no status column")
        rows = conn.execute(
            f'SELECT "status" FROM "{child_table}" WHERE "{fk_column}" = ?'
            f" ORDER BY {self._order_by(child_table)}",
            (parent_id,),
        ).fetchall()
        return [str(row[0]) for row in rows]

    def find_duplicates_by_name(
        self, conn: sqlite3.Connection, table: str, name: str, kind: str | None = None
    ) -> list[Any]:
        """Case-insensitive name matches, for duplicate warnings (SRS-034, SRS-121).

        Returns candidates; deciding whether to warn is the tool handler's call.
        `COLLATE NOCASE` matches the indexes V001 created for exactly this query.

        This implements only the case-insensitive half of SRS-034. The
        whitespace normalization the requirement also specifies — trim, then
        collapse internal runs to a single space — is applied by the caller in
        Phase 6, because normalizing here would silently diverge from the
        `COLLATE NOCASE` index and turn an indexed lookup into a scan.
        """
        self._check_table(table)
        columns = TABLE_COLUMNS[table]
        if "name" not in columns:
            raise ValueError(f"{table} has no name column")

        sql = f'SELECT {self._select_list(table)} FROM "{table}" WHERE "name" = ? COLLATE NOCASE'
        params: list[Any] = [name]
        if kind is not None:
            if "kind" not in columns:
                raise ValueError(f"{table} has no kind column")
            sql += ' AND "kind" = ?'
            params.append(kind)
        sql += f" ORDER BY {self._order_by(table)}"

        record_type = TABLE_RECORD_MAP[table]
        return [self._to_record(record_type, row) for row in conn.execute(sql, params).fetchall()]

    def search_by_name_pattern(
        self, conn: sqlite3.Connection, table: str, pattern: str
    ) -> list[Any]:
        """Case-insensitive `LIKE` search on `name`, for the review CLI (SRS-118).

        Mirrors `find_duplicates_by_name`: the table is resolved through the
        allowlist, `name` presence is checked against `TABLE_COLUMNS`, and the
        pattern is bound rather than interpolated. `COLLATE NOCASE` matches the
        indexes V001 created for name lookups.

        LLD-06 §4.2 specifies pattern search but the DAL only did equality;
        adding it here rather than filtering client-side keeps one notion of
        matching, inside the layer that owns the identifier allowlist (DEV-43).
        """
        self._check_table(table)
        if "name" not in TABLE_COLUMNS[table]:
            raise ValueError(f"{table} has no name column")

        sql = (
            f'SELECT {self._select_list(table)} FROM "{table}" '
            f'WHERE "name" LIKE ? COLLATE NOCASE ORDER BY {self._order_by(table)}'
        )
        record_type = TABLE_RECORD_MAP[table]
        return [
            self._to_record(record_type, row) for row in conn.execute(sql, [pattern]).fetchall()
        ]

    def resolve_unique_key(
        self, conn: sqlite3.Connection, unique_key: str
    ) -> tuple[str, Any] | None:
        """Search all tables for a record with the given unique_key.

        Returns (table_name, record) or None. Keys are UUIDs unique across the
        database (SRS-027), so the first match is the only match.
        """
        for table in sorted(DAL_TABLES):
            record = self._get_by(conn, TABLE_RECORD_MAP[table], "unique_key", unique_key)
            if record is not None:
                return table, record
        return None

    def get_record_by_id(self, conn: sqlite3.Connection, table: str, record_id: int) -> Any:
        """Fetch by primary key from a table named at runtime (LLD-02 §10.1)."""
        self._check_table(table)
        return self._get_by(conn, TABLE_RECORD_MAP[table], "id", record_id)

    def get_parent_record(
        self, conn: sqlite3.Connection, child_table: str, child_id: int
    ) -> tuple[str, Any] | None:
        """Resolve a child's parent as (table, record), or None at the root.

        Drives the SRS-035c demotion chain. Returns None when the table has no
        parent, when the child is missing, or when the foreign key is NULL.
        """
        relation = CHILD_PARENT_MAP.get(child_table)
        if relation is None:
            return None
        child = self.get_record_by_id(conn, child_table, child_id)
        if child is None:
            return None
        parent_id = getattr(child, relation.fk_column)
        if parent_id is None:
            return None
        parent = self.get_record_by_id(conn, relation.parent_table, parent_id)
        if parent is None:
            return None
        return relation.parent_table, parent

    def get_children(
        self, conn: sqlite3.Connection, child_table: str, fk_column: str, parent_id: int
    ) -> list[Any]:
        """All children of one parent, in deterministic order (SRS-108)."""
        self._check_table(child_table)
        self._reject_unknown(child_table, {fk_column}, TABLE_COLUMNS[child_table])
        rows = conn.execute(
            f'SELECT {self._select_list(child_table)} FROM "{child_table}"'
            f' WHERE "{fk_column}" = ? ORDER BY {self._order_by(child_table)}',
            (parent_id,),
        ).fetchall()
        record_type = TABLE_RECORD_MAP[child_table]
        return [self._to_record(record_type, row) for row in rows]

    def query_table(
        self, conn: sqlite3.Connection, table: str, filters: dict[str, Any] | None = None
    ) -> list[Any]:
        """Query a table named at runtime (LLD-02 §9)."""
        self._check_table(table)
        return self._query(conn, TABLE_RECORD_MAP[table], filters)

    def insert_record(self, conn: sqlite3.Connection, table: str, values: dict[str, Any]) -> int:
        """Insert into a table named at runtime, for the descriptor engine."""
        self._check_table(table)
        return self._insert(conn, TABLE_RECORD_MAP[table], values)

    def update_record(
        self, conn: sqlite3.Connection, table: str, record_id: int, values: dict[str, Any]
    ) -> None:
        """Update a table named at runtime, for the descriptor engine."""
        self._check_table(table)
        self._update(conn, TABLE_RECORD_MAP[table], record_id, values)

    def count_rows(self, conn: sqlite3.Connection, table: str) -> int:
        """Total rows in one table (LLD-02 §9.3 statistics)."""
        self._check_table(table)
        row = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()
        return int(row[0])

    def count_by_status(self, conn: sqlite3.Connection, table: str) -> dict[str, int]:
        """Row counts grouped by review state (LLD-02 §9.3 statistics).

        Returns an empty mapping for a table with no `status` column rather
        than raising: a caller tallying every table should not have to know
        which ones are structural subtypes (SRS-035a).
        """
        self._check_table(table)
        if "status" not in TABLE_COLUMNS[table]:
            return {}
        rows = conn.execute(
            f'SELECT "status", COUNT(*) FROM "{table}" GROUP BY "status"'
        ).fetchall()
        return {str(row[0]): int(row[1]) for row in rows}
