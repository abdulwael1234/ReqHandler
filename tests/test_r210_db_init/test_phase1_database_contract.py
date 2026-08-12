"""Exhaustive Phase 1 database contract tests.

These tests treat the initialized SQLite database as the public interface. They
exercise the physical schema and realistic record graphs without reaching into
the initializer's private methods.
"""

import sqlite3

import pytest

from r210_db_init.initializer import DatabaseInitializer
from r210_db_init.migrations.v001_initial_schema import INDEX_DDL
from r210_mcp.db.models import TABLE_RECORD_MAP

EXPECTED_FOREIGN_KEYS = {
    ("TypeDefinitions", "source_requirement_id", "SourceRequirements", "id"),
    ("SimpleTypeDefinitions", "type_definition_id", "TypeDefinitions", "id"),
    ("ArrayTypeDefinitions", "type_definition_id", "TypeDefinitions", "id"),
    ("ArrayTypeDefinitions", "element_type_id", "TypeDefinitions", "id"),
    ("StructElements", "struct_type_id", "TypeDefinitions", "id"),
    ("StructElements", "element_type_id", "TypeDefinitions", "id"),
    ("EnumValues", "enum_type_id", "TypeDefinitions", "id"),
    ("PortInterfaces", "source_requirement_id", "SourceRequirements", "id"),
    ("InterfaceDataElements", "port_interface_id", "PortInterfaces", "id"),
    ("InterfaceDataElements", "type_definition_id", "TypeDefinitions", "id"),
    ("ClientServerOperations", "port_interface_id", "PortInterfaces", "id"),
    ("OperationArguments", "operation_id", "ClientServerOperations", "id"),
    ("OperationArguments", "type_definition_id", "TypeDefinitions", "id"),
    ("PortPrototypes", "source_requirement_id", "SourceRequirements", "id"),
    ("PortPrototypes", "port_interface_id", "PortInterfaces", "id"),
    ("PortPrototypeFunctions", "port_prototype_id", "PortPrototypes", "id"),
    ("PortConnections", "source_requirement_id", "SourceRequirements", "id"),
    ("PortConnectionMembers", "port_connection_id", "PortConnections", "id"),
    ("PortConnectionMembers", "port_prototype_id", "PortPrototypes", "id"),
    ("ReviewIssues", "source_requirement_id", "SourceRequirements", "id"),
}

NULLABLE_CROSS_ARTIFACT_REFERENCES = {
    ("ArrayTypeDefinitions", "element_type_id"),
    ("StructElements", "element_type_id"),
    ("InterfaceDataElements", "type_definition_id"),
    ("OperationArguments", "type_definition_id"),
    ("PortPrototypes", "port_interface_id"),
}

ARTIFACT_STATUS_TABLES = {
    "SourceRequirements",
    "TypeDefinitions",
    "StructElements",
    "EnumValues",
    "PortInterfaces",
    "InterfaceDataElements",
    "ClientServerOperations",
    "OperationArguments",
    "PortPrototypes",
    "PortPrototypeFunctions",
    "PortConnections",
    "PortConnectionMembers",
}


def _foreign_keys(conn: sqlite3.Connection) -> set[tuple[str, str, str, str]]:
    relationships = set()
    for table in TABLE_RECORD_MAP:
        for row in conn.execute(f'PRAGMA foreign_key_list("{table}")'):
            relationships.add((table, row[3], row[2], row[4]))
    return relationships


def _insert_complete_graph(conn: sqlite3.Connection) -> dict[str, int]:
    """Insert a valid graph containing at least one row in every app table."""
    ids: dict[str, int] = {}
    ids["source"] = conn.execute(
        "INSERT INTO SourceRequirements "
        "(unique_key, source_reference, source_text, status, review_note) "
        "VALUES ('src-1', 'SRS-001', 'source', 'approved', 'reviewed')"
    ).lastrowid

    for key, name, kind in (
        ("simple", "Speed", "simple_typedef"),
        ("array", "SpeedArray", "array"),
        ("struct", "VehicleData", "struct"),
        ("enum", "VehicleState", "enum"),
    ):
        ids[key] = conn.execute(
            "INSERT INTO TypeDefinitions "
            "(unique_key, name, kind, source_requirement_id, status) "
            "VALUES (?, ?, ?, ?, 'approved')",
            (f"type-{key}", name, kind, ids["source"]),
        ).lastrowid

    conn.execute(
        "INSERT INTO SimpleTypeDefinitions "
        "(unique_key, type_definition_id, base_type, size) "
        "VALUES ('simple-detail', ?, 'uint16', '16')",
        (ids["simple"],),
    )
    conn.execute(
        "INSERT INTO ArrayTypeDefinitions "
        "(unique_key, type_definition_id, element_type_id, array_size) "
        "VALUES ('array-detail', ?, ?, 8)",
        (ids["array"], ids["simple"]),
    )
    conn.execute(
        "INSERT INTO StructElements "
        "(unique_key, struct_type_id, name, element_type_id, position, status) "
        "VALUES ('struct-field', ?, 'speed', ?, 1, 'approved')",
        (ids["struct"], ids["simple"]),
    )
    conn.execute(
        "INSERT INTO EnumValues (unique_key, enum_type_id, name, value, position, status) "
        "VALUES ('enum-value', ?, 'RUNNING', '1', 1, 'approved')",
        (ids["enum"],),
    )

    ids["sr_interface"] = conn.execute(
        "INSERT INTO PortInterfaces "
        "(unique_key, name, source_requirement_id, interface_type, status) "
        "VALUES ('if-sr', 'VehicleDataIf', ?, 'sender_receiver', 'approved')",
        (ids["source"],),
    ).lastrowid
    ids["cs_interface"] = conn.execute(
        "INSERT INTO PortInterfaces "
        "(unique_key, name, source_requirement_id, interface_type, status) "
        "VALUES ('if-cs', 'VehicleControlIf', ?, 'client_server', 'approved')",
        (ids["source"],),
    ).lastrowid
    conn.execute(
        "INSERT INTO InterfaceDataElements "
        "(unique_key, port_interface_id, name, type_definition_id, position, status) "
        "VALUES ('data-element', ?, 'VehicleData', ?, 1, 'approved')",
        (ids["sr_interface"], ids["struct"]),
    )
    ids["operation"] = conn.execute(
        "INSERT INTO ClientServerOperations "
        "(unique_key, port_interface_id, name, position, status) "
        "VALUES ('operation', ?, 'SetSpeed', 1, 'approved')",
        (ids["cs_interface"],),
    ).lastrowid
    conn.execute(
        "INSERT INTO OperationArguments "
        "(unique_key, operation_id, name, type_definition_id, direction, position, status) "
        "VALUES ('argument', ?, 'requestedSpeed', ?, 'input', 1, 'approved')",
        (ids["operation"], ids["simple"]),
    )

    for key, direction, component in (
        ("provider", "provider", "/Components/Provider"),
        ("requester", "requester", "/Components/Requester"),
    ):
        ids[key] = conn.execute(
            "INSERT INTO PortPrototypes "
            "(unique_key, name, source_requirement_id, port_interface_id, direction, "
            "component_reference, status) VALUES (?, ?, ?, ?, ?, ?, 'approved')",
            (f"port-{key}", key.title(), ids["source"], ids["cs_interface"], direction, component),
        ).lastrowid
    conn.execute(
        "INSERT INTO PortPrototypeFunctions "
        "(unique_key, port_prototype_id, function_name, relationship_type, status) "
        "VALUES ('port-function', ?, 'SetSpeed', 'access_point', 'approved')",
        (ids["requester"],),
    )
    ids["connection"] = conn.execute(
        "INSERT INTO PortConnections (unique_key, source_requirement_id, status) "
        "VALUES ('connection', ?, 'approved')",
        (ids["source"],),
    ).lastrowid
    for position, prototype in enumerate((ids["provider"], ids["requester"]), start=1):
        conn.execute(
            "INSERT INTO PortConnectionMembers "
            "(unique_key, port_connection_id, port_prototype_id, position, status) "
            "VALUES (?, ?, ?, ?, 'approved')",
            (f"member-{position}", ids["connection"], prototype, position),
        )
    conn.execute(
        "INSERT INTO ReviewIssues "
        "(unique_key, source_requirement_id, artifact_type, artifact_unique_key, "
        "issue_type, message, status, resolution) "
        "VALUES ('issue', ?, 'port_connection', 'connection', 'incomplete', "
        "'checked', 'resolved', 'complete')",
        (ids["source"],),
    )
    return ids


class TestPhysicalSchemaContract:
    def test_foreign_key_topology_matches_the_phase_contract_exactly(
        self, conn: sqlite3.Connection
    ) -> None:
        assert _foreign_keys(conn) == EXPECTED_FOREIGN_KEYS

    def test_all_foreign_keys_use_restrictive_default_actions(
        self, conn: sqlite3.Connection
    ) -> None:
        for table in TABLE_RECORD_MAP:
            for row in conn.execute(f'PRAGMA foreign_key_list("{table}")'):
                assert row[5:7] == ("NO ACTION", "NO ACTION")

    def test_every_record_table_has_integer_primary_key_named_id(
        self, conn: sqlite3.Connection
    ) -> None:
        for table in set(TABLE_RECORD_MAP) - {"schema_version"}:
            primary_keys = [row for row in conn.execute(f'PRAGMA table_info("{table}")') if row[5]]
            assert [(row[1], row[2], row[5]) for row in primary_keys] == [("id", "INTEGER", 1)]

    def test_every_application_record_has_required_unique_key(
        self, conn: sqlite3.Connection
    ) -> None:
        for table in set(TABLE_RECORD_MAP) - {"schema_version"}:
            columns = {row[1]: row for row in conn.execute(f'PRAGMA table_info("{table}")')}
            assert columns["unique_key"][3] == 1

    def test_only_approved_cross_artifact_references_are_nullable(
        self, conn: sqlite3.Connection
    ) -> None:
        fk_nullability = {}
        for table, column, _parent, _target in EXPECTED_FOREIGN_KEYS:
            columns = {row[1]: row for row in conn.execute(f'PRAGMA table_info("{table}")')}
            fk_nullability[(table, column)] = columns[column][3] == 0

        expected_nullable = NULLABLE_CROSS_ARTIFACT_REFERENCES | {
            ("TypeDefinitions", "source_requirement_id"),
            ("PortInterfaces", "source_requirement_id"),
            ("PortPrototypes", "source_requirement_id"),
            ("PortConnections", "source_requirement_id"),
            ("ReviewIssues", "source_requirement_id"),
        }
        assert {key for key, nullable in fk_nullability.items() if nullable} == expected_nullable

    def test_status_defaults_match_record_category(self, conn: sqlite3.Connection) -> None:
        for table in ARTIFACT_STATUS_TABLES:
            columns = {row[1]: row for row in conn.execute(f'PRAGMA table_info("{table}")')}
            assert columns["status"][4] == "'pending_review'"
        issue_columns = {
            row[1]: row for row in conn.execute('PRAGMA table_info("ReviewIssues")')
        }
        assert issue_columns["status"][4] == "'pending'"

    def test_declared_indexes_have_the_expected_table_and_column_order(
        self, conn: sqlite3.Connection
    ) -> None:
        for name, (expected_table, expected_columns) in INDEX_DDL.items():
            index_row = conn.execute(
                "SELECT tbl_name FROM sqlite_master WHERE type = 'index' AND name = ?", (name,)
            ).fetchone()
            assert index_row == (expected_table,)
            actual_columns = [
                row[2] for row in conn.execute(f'PRAGMA index_info("{name}")')
            ]
            expected_names = [part.strip().split()[0] for part in expected_columns.split(",")]
            assert actual_columns == expected_names

    @pytest.mark.parametrize(
        "index_name, expected_collations",
        [
            ("idx_type_definitions_name_kind", ["NOCASE", "BINARY"]),
            ("idx_port_interfaces_name_type", ["NOCASE", "BINARY"]),
            ("idx_port_prototypes_name", ["NOCASE"]),
        ],
    )
    def test_duplicate_detection_indexes_preserve_nocase_collation(
        self, conn: sqlite3.Connection, index_name: str, expected_collations: list[str]
    ) -> None:
        collations = [
            row[4]
            for row in conn.execute(f'PRAGMA index_xinfo("{index_name}")')
            if row[5] == 1
        ]
        assert collations == expected_collations


class TestCompleteRecordGraph:
    def test_every_application_table_accepts_a_coherent_record_graph(
        self, conn: sqlite3.Connection
    ) -> None:
        _insert_complete_graph(conn)

        populated = {
            table
            for table in set(TABLE_RECORD_MAP) - {"schema_version"}
            if conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] > 0
        }
        assert populated == set(TABLE_RECORD_MAP) - {"schema_version"}

    def test_complete_graph_survives_reinitialization(self, initialized_db: str) -> None:
        connection = sqlite3.connect(initialized_db)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            _insert_complete_graph(connection)
            connection.commit()
        finally:
            connection.close()

        result = DatabaseInitializer(initialized_db).init_db()

        assert result.status == "up_to_date"
        connection = sqlite3.connect(initialized_db)
        try:
            counts = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in set(TABLE_RECORD_MAP) - {"schema_version"}
            }
        finally:
            connection.close()
        assert all(count > 0 for count in counts.values())

    def test_parent_rows_cannot_be_deleted_while_children_reference_them(
        self, conn: sqlite3.Connection
    ) -> None:
        ids = _insert_complete_graph(conn)

        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM SourceRequirements WHERE id = ?", (ids["source"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM PortInterfaces WHERE id = ?", (ids["cs_interface"],))
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM TypeDefinitions WHERE id = ?", (ids["simple"],))
