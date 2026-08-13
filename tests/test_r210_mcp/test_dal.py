"""Development tests for DataAccessLayer (LLD-02 §5).

Scope: enough to establish that every table round-trips, that the cross-cutting
methods work, and that the identifier allowlist holds. Exhaustive verification
is a separate activity.
"""

import sqlite3
from collections.abc import Generator

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DAL_TABLES, TABLE_COLUMNS, DataAccessLayer
from r210_mcp.db.models import TABLE_RECORD_MAP


@pytest.fixture
def conn(initialized_db: str) -> Generator[sqlite3.Connection, None, None]:
    """An autocommit connection carrying the pragmas the DAL expects."""
    connection = DatabaseConnection(initialized_db).connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def dal() -> DataAccessLayer:
    return DataAccessLayer()


@pytest.fixture
def seeded(conn: sqlite3.Connection, dal: DataAccessLayer) -> dict[str, int]:
    """One valid row in every table, inserted in dependency order.

    Returns table name → row id. Subtype rows need their own parent because
    `type_definition_id` is UNIQUE (SRS-038a).
    """
    ids: dict[str, int] = {}

    ids["SourceRequirements"] = dal.insert_source_requirement(
        conn, "sr-1", "REQ-001", source_text="The system shall do the thing."
    )
    source_id = ids["SourceRequirements"]

    struct_parent = dal.insert_type_definition(
        conn, "td-struct", "Coordinates", "struct", source_requirement_id=source_id
    )
    enum_parent = dal.insert_type_definition(conn, "td-enum", "Mode", "enum")
    simple_parent = dal.insert_type_definition(conn, "td-simple", "Counter", "simple_typedef")
    array_parent = dal.insert_type_definition(conn, "td-array", "Buffer", "array")
    ids["TypeDefinitions"] = struct_parent

    ids["SimpleTypeDefinitions"] = dal.insert_simple_type_definition(
        conn, "std-1", simple_parent, "uint16", size="16"
    )
    ids["ArrayTypeDefinitions"] = dal.insert_array_type_definition(
        conn, "atd-1", array_parent, simple_parent, 8
    )
    ids["StructElements"] = dal.insert_struct_element(
        conn, "se-1", struct_parent, "x", simple_parent, 1
    )
    ids["EnumValues"] = dal.insert_enum_value(conn, "ev-1", enum_parent, "IDLE", "0", 1)

    interface_id = dal.insert_port_interface(
        conn, "pi-1", "SensorData", "client_server", source_requirement_id=source_id
    )
    ids["PortInterfaces"] = interface_id
    ids["InterfaceDataElements"] = dal.insert_interface_data_element(
        conn, "ide-1", interface_id, "reading", simple_parent, 1
    )
    operation_id = dal.insert_client_server_operation(conn, "cso-1", interface_id, "Read", 1)
    ids["ClientServerOperations"] = operation_id
    ids["OperationArguments"] = dal.insert_operation_argument(
        conn, "oa-1", operation_id, "value", simple_parent, "output", 1
    )

    prototype_id = dal.insert_port_prototype(
        conn, "pp-1", "SensorPort", "provider", "SensorSwc", port_interface_id=interface_id
    )
    ids["PortPrototypes"] = prototype_id
    ids["PortPrototypeFunctions"] = dal.insert_port_prototype_function(
        conn, "ppf-1", prototype_id, "Rte_Read", "access_point"
    )

    connection_id = dal.insert_port_connection(conn, "pc-1", description="Sensor to app")
    ids["PortConnections"] = connection_id
    ids["PortConnectionMembers"] = dal.insert_port_connection_member(
        conn, "pcm-1", connection_id, prototype_id, 1
    )

    ids["ReviewIssues"] = dal.insert_review_issue(
        conn,
        "ri-1",
        "unresolved_reference",
        "Type reference could not be resolved.",
        source_requirement_id=source_id,
        artifact_type="type_definition",
        artifact_unique_key="td-struct",
    )
    return ids


class TestRegistries:
    def test_every_table_except_schema_version_is_covered(self) -> None:
        assert DAL_TABLES == set(TABLE_RECORD_MAP) - {"schema_version"}

    def test_columns_match_the_live_schema(self, conn: sqlite3.Connection) -> None:
        """The derived registry must equal what the database actually declares."""
        for table, columns in TABLE_COLUMNS.items():
            actual = tuple(
                row[1] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            )
            assert columns == actual, f"{table} column mismatch"


class TestRoundTrip:
    def test_every_table_round_trips(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        """Insert → fetch → record, for all 15 application tables."""
        assert set(seeded) == DAL_TABLES

        for table, record_id in seeded.items():
            record = dal._get_by(conn, TABLE_RECORD_MAP[table], "id", record_id)
            assert record is not None, f"{table} row {record_id} not found"
            assert type(record) is TABLE_RECORD_MAP[table]
            assert record.id == record_id

    def test_typed_getter_returns_the_inserted_values(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        record = dal.get_type_definition_by_key(conn, "td-struct")
        assert record is not None
        assert record.name == "Coordinates"
        assert record.kind == "struct"
        assert record.status == "pending_review"
        assert record.source_requirement_id == seeded["SourceRequirements"]

    def test_missing_key_returns_none(
        self, conn: sqlite3.Connection, dal: DataAccessLayer
    ) -> None:
        assert dal.get_type_definition_by_key(conn, "absent") is None

    def test_update_writes_only_the_named_fields(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        dal.update_type_definition(conn, seeded["TypeDefinitions"], description="Updated")
        record = dal.get_type_definition_by_key(conn, "td-struct")
        assert record is not None
        assert record.description == "Updated"
        assert record.name == "Coordinates"

    def test_update_with_no_fields_is_a_no_op(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        dal.update_type_definition(conn, seeded["TypeDefinitions"])
        assert dal.get_type_definition_by_key(conn, "td-struct") is not None


class TestQuery:
    def test_filters_by_equality(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        results = dal.query_type_definitions(conn, {"kind": "struct"})
        assert [r.unique_key for r in results] == ["td-struct"]

    def test_none_filter_matches_null_not_nothing(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        """SRS-036a — querying unresolved references is a real use case."""
        results = dal.query_type_definitions(conn, {"source_requirement_id": None})
        assert {r.unique_key for r in results} == {"td-enum", "td-simple", "td-array"}

    def test_unfiltered_query_returns_every_row(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        assert len(dal.query_type_definitions(conn)) == 4

    def test_children_are_ordered_by_parent_then_position(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        """SRS-108 — deterministic ordering, regardless of insertion order."""
        parent = seeded["TypeDefinitions"]
        dal.insert_struct_element(conn, "se-3", parent, "z", None, 3)
        dal.insert_struct_element(conn, "se-2", parent, "y", None, 2)

        elements = dal.query_struct_elements(conn, {"struct_type_id": parent})
        assert [e.position for e in elements] == [1, 2, 3]
        assert [e.name for e in elements] == ["x", "y", "z"]


class TestCrossCutting:
    def test_update_status_sets_state_and_note(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        dal.update_status(
            conn, "TypeDefinitions", seeded["TypeDefinitions"], "approved", "Verified"
        )
        record = dal.get_type_definition_by_key(conn, "td-struct")
        assert record is not None
        assert record.status == "approved"
        assert record.review_note == "Verified"

    def test_update_status_on_a_child_without_a_note(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        dal.update_status(conn, "StructElements", seeded["StructElements"], "approved")
        record = dal.get_struct_element_by_key(conn, "se-1")
        assert record is not None
        assert record.status == "approved"

    def test_update_status_ignores_a_note_on_a_table_without_the_column(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        """SRS-091a silently ignores notes for tables without a note column."""
        dal.update_status(
            conn, "StructElements", seeded["StructElements"], "approved", "ignored note"
        )

        record = dal.get_struct_element_by_key(conn, "se-1")
        assert record is not None
        assert record.status == "approved"

    def test_update_status_rejects_a_table_without_status(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        with pytest.raises(ValueError, match="status"):
            dal.update_status(
                conn, "SimpleTypeDefinitions", seeded["SimpleTypeDefinitions"], "approved"
            )

    def test_get_record_by_unique_key_resolves_a_runtime_table(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        record = dal.get_record_by_unique_key(conn, "PortInterfaces", "pi-1")
        assert record is not None
        assert record.name == "SensorData"

    def test_get_children_statuses(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        parent = seeded["TypeDefinitions"]
        dal.insert_struct_element(conn, "se-2", parent, "y", None, 2)
        dal.update_status(conn, "StructElements", seeded["StructElements"], "approved")

        statuses = dal.get_children_statuses(conn, "StructElements", "struct_type_id", parent)
        assert statuses == ["approved", "pending_review"]

    def test_find_duplicates_by_name_is_case_insensitive(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        """SRS-034 — the query finds candidates; warning policy is Phase 6."""
        matches = dal.find_duplicates_by_name(conn, "TypeDefinitions", "COORDINATES")
        assert [m.unique_key for m in matches] == ["td-struct"]

    def test_find_duplicates_by_name_narrows_by_kind(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        assert dal.find_duplicates_by_name(conn, "TypeDefinitions", "Coordinates", "enum") == []

    def test_resolve_unique_key_finds_the_owning_table(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        resolved = dal.resolve_unique_key(conn, "pcm-1")
        assert resolved is not None
        table, record = resolved
        assert table == "PortConnectionMembers"
        assert record.id == seeded["PortConnectionMembers"]

    def test_resolve_unique_key_returns_none_when_absent(
        self, conn: sqlite3.Connection, dal: DataAccessLayer
    ) -> None:
        assert dal.resolve_unique_key(conn, "no-such-key") is None

    def test_get_connection_members_are_position_ordered(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        connection_id = seeded["PortConnections"]
        other = dal.insert_port_prototype(conn, "pp-2", "AppPort", "requester", "AppSwc")
        dal.insert_port_connection_member(conn, "pcm-2", connection_id, other, 2)

        members = dal.get_connection_members(conn, connection_id)
        assert [m.position for m in members] == [1, 2]


class TestIdentifierAllowlist:
    def test_unknown_table_is_rejected(
        self, conn: sqlite3.Connection, dal: DataAccessLayer
    ) -> None:
        with pytest.raises(ValueError, match="unknown table"):
            dal.get_record_by_unique_key(conn, "TypeDefinitions; DROP TABLE EnumValues", "k")

    def test_schema_version_is_outside_the_dal_surface(
        self, conn: sqlite3.Connection, dal: DataAccessLayer
    ) -> None:
        with pytest.raises(ValueError, match="unknown table"):
            dal.get_record_by_unique_key(conn, "schema_version", "k")

    def test_unknown_insert_column_is_rejected(
        self, conn: sqlite3.Connection, dal: DataAccessLayer
    ) -> None:
        with pytest.raises(ValueError, match="unknown column"):
            dal._insert(conn, TABLE_RECORD_MAP["TypeDefinitions"], {"nope": 1})

    def test_unknown_update_column_is_rejected(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        with pytest.raises(ValueError, match="unknown column"):
            dal.update_type_definition(conn, seeded["TypeDefinitions"], nope=1)

    def test_unknown_filter_column_is_rejected(
        self, conn: sqlite3.Connection, dal: DataAccessLayer
    ) -> None:
        with pytest.raises(ValueError, match="unknown column"):
            dal.query_type_definitions(conn, {"nope": 1})

    def test_id_cannot_be_written(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        with pytest.raises(ValueError, match="unknown column"):
            dal.update_type_definition(conn, seeded["TypeDefinitions"], id=99)


class TestConstraintsPropagate:
    def test_unique_violation_reaches_the_caller(
        self, conn: sqlite3.Connection, dal: DataAccessLayer, seeded: dict[str, int]
    ) -> None:
        """The DAL does not translate constraint failures — Phase 3 does."""
        with pytest.raises(sqlite3.IntegrityError):
            dal.insert_type_definition(conn, "td-struct", "Other", "struct")

    def test_check_violation_reaches_the_caller(
        self, conn: sqlite3.Connection, dal: DataAccessLayer
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            dal.insert_type_definition(conn, "td-bad", "Bad", "not_a_kind")

    def test_foreign_key_violation_reaches_the_caller(
        self, conn: sqlite3.Connection, dal: DataAccessLayer
    ) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            dal.insert_struct_element(conn, "se-bad", 9999, "x", None, 1)


class TestGraphAndGenericMethods:
    """The methods LLD-02 §6.2, §10 and §9 call that Phase 2 did not build."""

    def test_get_record_by_id_round_trips(self, initialized_db: str) -> None:
        """SRS-026 — records are addressable by their integer primary key."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as connection:
            record_id = dal.insert_source_requirement(connection, "k1", "REQ-1")
        with db.read_only() as connection:
            record = dal.get_record_by_id(connection, "SourceRequirements", record_id)
        assert record.unique_key == "k1"

    def test_get_record_by_id_returns_none_when_absent(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.read_only() as connection:
            assert dal.get_record_by_id(connection, "SourceRequirements", 9999) is None

    def test_get_parent_record_resolves_the_relation(self, initialized_db: str) -> None:
        """SRS-035c — the demotion chain needs child to parent navigation."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as connection:
            parent_id = dal.insert_type_definition(connection, "td", "Colour", "enum")
            child_id = dal.insert_enum_value(connection, "ev", parent_id, "RED", None, 1)
        with db.read_only() as connection:
            found = dal.get_parent_record(connection, "EnumValues", child_id)
        assert found is not None
        table, parent = found
        assert table == "TypeDefinitions"
        assert parent.unique_key == "td"

    def test_get_parent_record_returns_none_for_a_root_table(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as connection:
            record_id = dal.insert_type_definition(connection, "td2", "Speed", "struct")
        with db.read_only() as connection:
            assert dal.get_parent_record(connection, "TypeDefinitions", record_id) is None

    def test_get_children_is_position_ordered(self, initialized_db: str) -> None:
        """SRS-037, SRS-108 — children come back in declaration order."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as connection:
            parent_id = dal.insert_type_definition(connection, "td3", "Mode", "enum")
            dal.insert_enum_value(connection, "b", parent_id, "B", None, 2)
            dal.insert_enum_value(connection, "a", parent_id, "A", None, 1)
        with db.read_only() as connection:
            children = dal.get_children(connection, "EnumValues", "enum_type_id", parent_id)
        assert [child.unique_key for child in children] == ["a", "b"]

    def test_query_table_applies_filters(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as connection:
            dal.insert_source_requirement(connection, "q1", "REQ-A")
            dal.insert_source_requirement(connection, "q2", "REQ-B")
        with db.read_only() as connection:
            rows = dal.query_table(connection, "SourceRequirements", {"source_reference": "REQ-B"})
        assert [row.unique_key for row in rows] == ["q2"]

    def test_insert_and_update_record_are_generic(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as connection:
            record_id = dal.insert_record(
                connection,
                "SourceRequirements",
                {"unique_key": "g1", "source_reference": "REQ-G"},
            )
            dal.update_record(connection, "SourceRequirements", record_id, {"source_text": "body"})
        with db.read_only() as connection:
            record = dal.get_record_by_id(connection, "SourceRequirements", record_id)
        assert record.source_text == "body"

    def test_generic_methods_reject_an_unknown_table(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.read_only() as connection:
            with pytest.raises(ValueError):
                dal.query_table(connection, "Nonexistent", None)
            with pytest.raises(ValueError):
                dal.insert_record(connection, "schema_version", {"version": 9})
