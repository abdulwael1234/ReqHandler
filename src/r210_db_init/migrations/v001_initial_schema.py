"""V001: Initial schema — creates all 16 tables defined in LLD-01 §3.

Tables created:
- SourceRequirements, TypeDefinitions, SimpleTypeDefinitions,
  ArrayTypeDefinitions, StructElements, EnumValues, PortInterfaces,
  InterfaceDataElements, ClientServerOperations, OperationArguments,
  PortPrototypes, PortPrototypeFunctions, PortConnections,
  PortConnectionMembers, ReviewIssues
- (schema_version is created by the initializer itself)

See: LLD-05 §5.2 (Initial Schema Migration)
"""

import sqlite3

from .base import Migration

# The five review states shared by every artifact and reviewable child record
# (SRS-035). Repeated inline in each CHECK constraint below because SQLite
# stores the DDL text verbatim.
_STATUS_CHECK = (
    "CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope'))"
)

# Table name → CREATE TABLE statement, in dependency order so that foreign-key
# targets always exist before their referencing tables. This mapping is the
# single source of truth for which tables the migration creates; the
# initializer derives its verification set from it (LLD-05 §4.3).
TABLE_DDL: dict[str, str] = {
    # ── SourceRequirements (LLD-01 §3.1 — SRS-039, SRS-040, SRS-041) ──
    "SourceRequirements": f"""
        CREATE TABLE IF NOT EXISTS SourceRequirements (
            id               INTEGER PRIMARY KEY,
            unique_key       TEXT    NOT NULL UNIQUE,
            source_reference TEXT    NOT NULL,
            source_text      TEXT,
            status           TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            review_note      TEXT
        )
    """,
    # ── TypeDefinitions (LLD-01 §3.2 — SRS-042, SRS-043) ──
    "TypeDefinitions": f"""
        CREATE TABLE IF NOT EXISTS TypeDefinitions (
            id                      INTEGER PRIMARY KEY,
            unique_key              TEXT    NOT NULL UNIQUE,
            name                    TEXT    NOT NULL,
            kind                    TEXT    NOT NULL
                                    CHECK (kind IN ('simple_typedef','array','struct','enum')),
            description             TEXT,
            source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
            status                  TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            review_note             TEXT
        )
    """,
    # ── SimpleTypeDefinitions (LLD-01 §3.3 — SRS-047, SRS-038a) ──
    "SimpleTypeDefinitions": """
        CREATE TABLE IF NOT EXISTS SimpleTypeDefinitions (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            type_definition_id  INTEGER NOT NULL UNIQUE REFERENCES TypeDefinitions(id),
            base_type           TEXT    NOT NULL,
            size                TEXT
        )
    """,
    # ── ArrayTypeDefinitions (LLD-01 §3.4 — SRS-048, SRS-038a, SRS-038b) ──
    "ArrayTypeDefinitions": """
        CREATE TABLE IF NOT EXISTS ArrayTypeDefinitions (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            type_definition_id  INTEGER NOT NULL UNIQUE REFERENCES TypeDefinitions(id),
            element_type_id     INTEGER NOT NULL REFERENCES TypeDefinitions(id),
            array_size          INTEGER NOT NULL CHECK (array_size >= 1)
        )
    """,
    # ── StructElements (LLD-01 §3.5 — SRS-049, SRS-037, SRS-038b, SRS-038c) ──
    "StructElements": f"""
        CREATE TABLE IF NOT EXISTS StructElements (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            struct_type_id      INTEGER NOT NULL REFERENCES TypeDefinitions(id),
            name                TEXT    NOT NULL,
            element_type_id     INTEGER NOT NULL REFERENCES TypeDefinitions(id),
            position            INTEGER NOT NULL CHECK (position >= 1),
            description         TEXT,
            status              TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            UNIQUE (struct_type_id, position),
            UNIQUE (struct_type_id, name)
        )
    """,
    # ── EnumValues (LLD-01 §3.6 — SRS-050, SRS-037, SRS-038b, SRS-038c) ──
    "EnumValues": f"""
        CREATE TABLE IF NOT EXISTS EnumValues (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            enum_type_id        INTEGER NOT NULL REFERENCES TypeDefinitions(id),
            name                TEXT    NOT NULL,
            value               TEXT,
            position            INTEGER NOT NULL CHECK (position >= 1),
            description         TEXT,
            status              TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            UNIQUE (enum_type_id, position),
            UNIQUE (enum_type_id, name)
        )
    """,
    # ── PortInterfaces (LLD-01 §3.7 — SRS-051, SRS-052) ──
    "PortInterfaces": f"""
        CREATE TABLE IF NOT EXISTS PortInterfaces (
            id                      INTEGER PRIMARY KEY,
            unique_key              TEXT    NOT NULL UNIQUE,
            name                    TEXT    NOT NULL,
            description             TEXT,
            source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
            interface_type          TEXT    NOT NULL
                                    CHECK (interface_type IN ('sender_receiver','client_server')),
            status                  TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            review_note             TEXT
        )
    """,
    # ── InterfaceDataElements (LLD-01 §3.8 — SRS-056, SRS-037) ──
    "InterfaceDataElements": f"""
        CREATE TABLE IF NOT EXISTS InterfaceDataElements (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            port_interface_id   INTEGER NOT NULL REFERENCES PortInterfaces(id),
            name                TEXT    NOT NULL,
            type_definition_id  INTEGER NOT NULL REFERENCES TypeDefinitions(id),
            position            INTEGER NOT NULL CHECK (position >= 1),
            description         TEXT,
            status              TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            UNIQUE (port_interface_id, position)
        )
    """,
    # ── ClientServerOperations (LLD-01 §3.9 — SRS-057, SRS-037) ──
    "ClientServerOperations": f"""
        CREATE TABLE IF NOT EXISTS ClientServerOperations (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            port_interface_id   INTEGER NOT NULL REFERENCES PortInterfaces(id),
            name                TEXT    NOT NULL,
            position            INTEGER NOT NULL CHECK (position >= 1),
            description         TEXT,
            status              TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            UNIQUE (port_interface_id, position)
        )
    """,
    # ── OperationArguments (LLD-01 §3.10 — SRS-058, SRS-059, SRS-037) ──
    "OperationArguments": f"""
        CREATE TABLE IF NOT EXISTS OperationArguments (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            operation_id        INTEGER NOT NULL REFERENCES ClientServerOperations(id),
            name                TEXT    NOT NULL,
            type_definition_id  INTEGER NOT NULL REFERENCES TypeDefinitions(id),
            direction           TEXT    NOT NULL
                                CHECK (direction IN ('input','output','input_output')),
            position            INTEGER NOT NULL CHECK (position >= 1),
            status              TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            UNIQUE (operation_id, position)
        )
    """,
    # ── PortPrototypes (LLD-01 §3.11 — SRS-060, SRS-061, SRS-036) ──
    "PortPrototypes": f"""
        CREATE TABLE IF NOT EXISTS PortPrototypes (
            id                      INTEGER PRIMARY KEY,
            unique_key              TEXT    NOT NULL UNIQUE,
            name                    TEXT    NOT NULL,
            description             TEXT,
            source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
            port_interface_id       INTEGER REFERENCES PortInterfaces(id),
            direction               TEXT    NOT NULL
                                    CHECK (direction IN ('provider','requester')),
            component_reference     TEXT    NOT NULL,
            status                  TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            review_note             TEXT
        )
    """,
    # ── PortPrototypeFunctions (LLD-01 §3.12 — SRS-062, SRS-063) ──
    "PortPrototypeFunctions": f"""
        CREATE TABLE IF NOT EXISTS PortPrototypeFunctions (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            port_prototype_id   INTEGER NOT NULL REFERENCES PortPrototypes(id),
            function_name       TEXT    NOT NULL,
            relationship_type   TEXT    NOT NULL
                                CHECK (relationship_type IN ('access_point','trigger')),
            status              TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK}
        )
    """,
    # ── PortConnections (LLD-01 §3.13 — SRS-065, SRS-068) ──
    "PortConnections": f"""
        CREATE TABLE IF NOT EXISTS PortConnections (
            id                      INTEGER PRIMARY KEY,
            unique_key              TEXT    NOT NULL UNIQUE,
            description             TEXT,
            source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
            status                  TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            review_note             TEXT
        )
    """,
    # ── PortConnectionMembers (LLD-01 §3.14 — SRS-066, SRS-070, SRS-037) ──
    "PortConnectionMembers": f"""
        CREATE TABLE IF NOT EXISTS PortConnectionMembers (
            id                  INTEGER PRIMARY KEY,
            unique_key          TEXT    NOT NULL UNIQUE,
            port_connection_id  INTEGER NOT NULL REFERENCES PortConnections(id),
            port_prototype_id   INTEGER NOT NULL REFERENCES PortPrototypes(id),
            position            INTEGER NOT NULL CHECK (position >= 1),
            status              TEXT    NOT NULL DEFAULT 'pending_review' {_STATUS_CHECK},
            UNIQUE (port_connection_id, position),
            UNIQUE (port_connection_id, port_prototype_id)
        )
    """,
    # ── ReviewIssues (LLD-01 §3.15 — SRS-074, SRS-075, SRS-076) ──
    "ReviewIssues": """
        CREATE TABLE IF NOT EXISTS ReviewIssues (
            id                      INTEGER PRIMARY KEY,
            unique_key              TEXT    NOT NULL UNIQUE,
            source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
            artifact_type           TEXT
                                    CHECK (artifact_type IN (
                                        'type_definition','struct_element','enum_value',
                                        'port_interface','interface_data_element',
                                        'client_server_operation','operation_argument',
                                        'port_prototype','port_prototype_function',
                                        'port_connection','port_connection_member'
                                    ) OR artifact_type IS NULL),
            artifact_unique_key     TEXT,
            issue_type              TEXT    NOT NULL
                                    CHECK (issue_type IN ('ambiguous','incomplete',
                                                          'unresolved_reference','unsupported',
                                                          'out_of_scope')),
            message                 TEXT    NOT NULL,
            status                  TEXT    NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','resolved','rejected')),
            resolution              TEXT,
            CHECK (artifact_unique_key IS NULL OR artifact_type IS NOT NULL)
        )
    """,
}

# Index name → (table, indexed columns). Single source of truth for the index
# set, mirrored by the initializer's verification step (LLD-05 §4.3).
INDEX_DDL: dict[str, tuple[str, str]] = {
    # SourceRequirements
    "idx_source_requirements_status": ("SourceRequirements", "status"),
    "idx_source_requirements_source_reference": ("SourceRequirements", "source_reference"),
    # TypeDefinitions
    "idx_type_definitions_kind": ("TypeDefinitions", "kind"),
    "idx_type_definitions_status": ("TypeDefinitions", "status"),
    "idx_type_definitions_source_req": ("TypeDefinitions", "source_requirement_id"),
    # Supports the duplicate-detection query (SRS-034)
    "idx_type_definitions_name_kind": ("TypeDefinitions", "name COLLATE NOCASE, kind"),
    # StructElements / EnumValues
    "idx_struct_elements_parent": ("StructElements", "struct_type_id"),
    "idx_enum_values_parent": ("EnumValues", "enum_type_id"),
    # PortInterfaces
    "idx_port_interfaces_type": ("PortInterfaces", "interface_type"),
    "idx_port_interfaces_status": ("PortInterfaces", "status"),
    "idx_port_interfaces_source_req": ("PortInterfaces", "source_requirement_id"),
    "idx_port_interfaces_name_type": ("PortInterfaces", "name COLLATE NOCASE, interface_type"),
    # Interface children
    "idx_interface_data_elements_parent": ("InterfaceDataElements", "port_interface_id"),
    "idx_client_server_operations_parent": ("ClientServerOperations", "port_interface_id"),
    "idx_operation_arguments_parent": ("OperationArguments", "operation_id"),
    # PortPrototypes
    "idx_port_prototypes_interface": ("PortPrototypes", "port_interface_id"),
    "idx_port_prototypes_direction": ("PortPrototypes", "direction"),
    "idx_port_prototypes_status": ("PortPrototypes", "status"),
    "idx_port_prototypes_source_req": ("PortPrototypes", "source_requirement_id"),
    "idx_port_prototypes_name": ("PortPrototypes", "name COLLATE NOCASE"),
    "idx_port_prototype_functions_parent": ("PortPrototypeFunctions", "port_prototype_id"),
    # PortConnections
    "idx_port_connections_status": ("PortConnections", "status"),
    "idx_port_connections_source_req": ("PortConnections", "source_requirement_id"),
    "idx_port_connection_members_parent": ("PortConnectionMembers", "port_connection_id"),
    "idx_port_connection_members_prototype": ("PortConnectionMembers", "port_prototype_id"),
    # ReviewIssues
    "idx_review_issues_status": ("ReviewIssues", "status"),
    "idx_review_issues_issue_type": ("ReviewIssues", "issue_type"),
    "idx_review_issues_source_req": ("ReviewIssues", "source_requirement_id"),
    "idx_review_issues_artifact": ("ReviewIssues", "artifact_type, artifact_unique_key"),
}


class V001InitialSchema(Migration):
    """Migration: version 0 → 1. Creates all tables from LLD-01."""

    @property
    def description(self) -> str:
        return "Initial schema — all 16 tables per LLD-01 v1.0"

    def up(self, conn: sqlite3.Connection) -> None:
        for ddl in TABLE_DDL.values():
            conn.execute(ddl)
        self._create_indexes(conn)

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """Create all indexes using IF NOT EXISTS for idempotency (SRS-098)."""
        for name, (table, columns) in INDEX_DDL.items():
            conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table}({columns})")
