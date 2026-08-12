"""Allow unresolved cross-artifact type references to be stored as NULL.

SQLite cannot remove a NOT NULL constraint in place, so this migration
rebuilds the four affected child/detail tables while preserving their rows,
constraints, foreign keys, and indexes (SRS-036a, SRS-099).
"""

import sqlite3

from .base import Migration

_TABLE_REBUILDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ArrayTypeDefinitions": (
        """
        CREATE TABLE _v002_ArrayTypeDefinitions (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            type_definition_id  INTEGER NOT NULL UNIQUE REFERENCES TypeDefinitions(id),
            element_type_id     INTEGER REFERENCES TypeDefinitions(id),
            array_size          INTEGER NOT NULL CHECK (array_size >= 1)
        )
        """,
        ("id", "unique_key", "type_definition_id", "element_type_id", "array_size"),
    ),
    "StructElements": (
        """
        CREATE TABLE _v002_StructElements (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            struct_type_id      INTEGER NOT NULL REFERENCES TypeDefinitions(id),
            name                TEXT    NOT NULL,
            element_type_id     INTEGER REFERENCES TypeDefinitions(id),
            position            INTEGER NOT NULL CHECK (position >= 1),
            description         TEXT,
            status              TEXT    NOT NULL DEFAULT 'pending_review'
                                CHECK (status IN (
                                    'pending_review', 'approved', 'rejected',
                                    'ambiguous', 'out_of_scope'
                                )),
            UNIQUE (struct_type_id, position),
            UNIQUE (struct_type_id, name)
        )
        """,
        (
            "id",
            "unique_key",
            "struct_type_id",
            "name",
            "element_type_id",
            "position",
            "description",
            "status",
        ),
    ),
    "InterfaceDataElements": (
        """
        CREATE TABLE _v002_InterfaceDataElements (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            port_interface_id   INTEGER NOT NULL REFERENCES PortInterfaces(id),
            name                TEXT    NOT NULL,
            type_definition_id  INTEGER REFERENCES TypeDefinitions(id),
            position            INTEGER NOT NULL CHECK (position >= 1),
            description         TEXT,
            status              TEXT    NOT NULL DEFAULT 'pending_review'
                                CHECK (status IN (
                                    'pending_review', 'approved', 'rejected',
                                    'ambiguous', 'out_of_scope'
                                )),
            UNIQUE (port_interface_id, position)
        )
        """,
        (
            "id",
            "unique_key",
            "port_interface_id",
            "name",
            "type_definition_id",
            "position",
            "description",
            "status",
        ),
    ),
    "OperationArguments": (
        """
        CREATE TABLE _v002_OperationArguments (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            operation_id        INTEGER NOT NULL REFERENCES ClientServerOperations(id),
            name                TEXT    NOT NULL,
            type_definition_id  INTEGER REFERENCES TypeDefinitions(id),
            direction           TEXT    NOT NULL
                                CHECK (direction IN ('input','output','input_output')),
            position            INTEGER NOT NULL CHECK (position >= 1),
            status              TEXT    NOT NULL DEFAULT 'pending_review'
                                CHECK (status IN (
                                    'pending_review', 'approved', 'rejected',
                                    'ambiguous', 'out_of_scope'
                                )),
            UNIQUE (operation_id, position)
        )
        """,
        (
            "id",
            "unique_key",
            "operation_id",
            "name",
            "type_definition_id",
            "direction",
            "position",
            "status",
        ),
    ),
}

_REBUILT_INDEXES: dict[str, tuple[str, str]] = {
    "idx_struct_elements_parent": ("StructElements", "struct_type_id"),
    "idx_interface_data_elements_parent": ("InterfaceDataElements", "port_interface_id"),
    "idx_operation_arguments_parent": ("OperationArguments", "operation_id"),
}


class V002NullableTypeReferences(Migration):
    """Make the four SRS-036a type-reference columns nullable."""

    @property
    def description(self) -> str:
        return "Allow unresolved cross-artifact type references"

    def up(self, conn: sqlite3.Connection) -> None:
        for table, (create_sql, columns) in _TABLE_REBUILDS.items():
            temporary_table = f"_v002_{table}"
            column_list = ", ".join(columns)
            conn.execute(create_sql)
            conn.execute(
                f'INSERT INTO "{temporary_table}" ({column_list}) '
                f'SELECT {column_list} FROM "{table}"'
            )
            conn.execute(f'DROP TABLE "{table}"')
            conn.execute(f'ALTER TABLE "{temporary_table}" RENAME TO "{table}"')

        for name, (table, indexed_columns) in _REBUILT_INDEXES.items():
            conn.execute(f"CREATE INDEX {name} ON {table}({indexed_columns})")
