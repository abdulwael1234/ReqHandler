"""Independent verification of the Phase 2 Data Access Layer (LLD-02 §5).

Supplements the development tests with broad public-wrapper coverage and the
focused risks listed in ``PHASE2_IMPLEMENTED_REQUIREMENTS.md`` §9.
"""

import sqlite3
from collections.abc import Generator
from typing import Any

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.db.models import TypeDefinitionRecord


@pytest.fixture
def phase2_conn(initialized_db: str) -> Generator[sqlite3.Connection, None, None]:
    connection = DatabaseConnection(initialized_db).connect()
    try:
        yield connection
    finally:
        connection.close()


@pytest.fixture
def dal() -> DataAccessLayer:
    return DataAccessLayer()


@pytest.fixture
def phase2_records(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> dict[str, tuple[int, str]]:
    """Create one valid record in every Phase 2 DAL table."""
    records: dict[str, tuple[int, str]] = {}

    def remember(table: str, record_id: int, unique_key: str) -> int:
        records[table] = (record_id, unique_key)
        return record_id

    source = remember(
        "SourceRequirements",
        dal.insert_source_requirement(phase2_conn, "verify-source", "REQ-VERIFY"),
        "verify-source",
    )
    struct = remember(
        "TypeDefinitions",
        dal.insert_type_definition(
            phase2_conn, "verify-struct", "VerifyStruct", "struct", source_requirement_id=source
        ),
        "verify-struct",
    )
    simple_parent = dal.insert_type_definition(
        phase2_conn, "verify-simple-parent", "VerifySimple", "simple_typedef"
    )
    array_parent = dal.insert_type_definition(
        phase2_conn, "verify-array-parent", "VerifyArray", "array"
    )
    remember(
        "SimpleTypeDefinitions",
        dal.insert_simple_type_definition(phase2_conn, "verify-simple", simple_parent, "uint8"),
        "verify-simple",
    )
    remember(
        "ArrayTypeDefinitions",
        dal.insert_array_type_definition(phase2_conn, "verify-array", array_parent, None, 4),
        "verify-array",
    )
    remember(
        "StructElements",
        dal.insert_struct_element(phase2_conn, "verify-element", struct, "member", None, 1),
        "verify-element",
    )
    enum_parent = dal.insert_type_definition(
        phase2_conn, "verify-enum-parent", "VerifyEnum", "enum"
    )
    remember(
        "EnumValues",
        dal.insert_enum_value(phase2_conn, "verify-enum", enum_parent, "ON", "1", 1),
        "verify-enum",
    )
    interface = remember(
        "PortInterfaces",
        dal.insert_port_interface(
            phase2_conn, "verify-interface", "VerifyInterface", "client_server"
        ),
        "verify-interface",
    )
    remember(
        "InterfaceDataElements",
        dal.insert_interface_data_element(phase2_conn, "verify-data", interface, "value", None, 1),
        "verify-data",
    )
    operation = remember(
        "ClientServerOperations",
        dal.insert_client_server_operation(phase2_conn, "verify-operation", interface, "Read", 1),
        "verify-operation",
    )
    remember(
        "OperationArguments",
        dal.insert_operation_argument(
            phase2_conn, "verify-argument", operation, "result", None, "output", 1
        ),
        "verify-argument",
    )
    prototype = remember(
        "PortPrototypes",
        dal.insert_port_prototype(
            phase2_conn, "verify-prototype", "VerifyPort", "provider", "VerifySwc"
        ),
        "verify-prototype",
    )
    remember(
        "PortPrototypeFunctions",
        dal.insert_port_prototype_function(
            phase2_conn, "verify-function", prototype, "Rte_Verify", "access_point"
        ),
        "verify-function",
    )
    connection = remember(
        "PortConnections",
        dal.insert_port_connection(phase2_conn, "verify-connection"),
        "verify-connection",
    )
    remember(
        "PortConnectionMembers",
        dal.insert_port_connection_member(phase2_conn, "verify-member", connection, prototype, 1),
        "verify-member",
    )
    remember(
        "ReviewIssues",
        dal.insert_review_issue(phase2_conn, "verify-issue", "ambiguous", "Needs review"),
        "verify-issue",
    )
    return records


PUBLIC_METHODS = {
    "SourceRequirements": (
        "get_source_requirement_by_key",
        "query_source_requirements",
        "update_source_requirement",
    ),
    "TypeDefinitions": (
        "get_type_definition_by_key",
        "query_type_definitions",
        "update_type_definition",
    ),
    "SimpleTypeDefinitions": (
        "get_simple_type_definition_by_key",
        None,
        "update_simple_type_definition",
    ),
    "ArrayTypeDefinitions": (
        "get_array_type_definition_by_key",
        None,
        "update_array_type_definition",
    ),
    "StructElements": (
        "get_struct_element_by_key",
        "query_struct_elements",
        "update_struct_element",
    ),
    "EnumValues": ("get_enum_value_by_key", "query_enum_values", "update_enum_value"),
    "PortInterfaces": (
        "get_port_interface_by_key",
        "query_port_interfaces",
        "update_port_interface",
    ),
    "InterfaceDataElements": (
        "get_interface_data_element_by_key",
        "query_interface_data_elements",
        "update_interface_data_element",
    ),
    "ClientServerOperations": (
        "get_client_server_operation_by_key",
        "query_client_server_operations",
        "update_client_server_operation",
    ),
    "OperationArguments": (
        "get_operation_argument_by_key",
        "query_operation_arguments",
        "update_operation_argument",
    ),
    "PortPrototypes": (
        "get_port_prototype_by_key",
        "query_port_prototypes",
        "update_port_prototype",
    ),
    "PortPrototypeFunctions": (
        "get_port_prototype_function_by_key",
        "query_port_prototype_functions",
        "update_port_prototype_function",
    ),
    "PortConnections": (
        "get_port_connection_by_key",
        "query_port_connections",
        "update_port_connection",
    ),
    "PortConnectionMembers": (
        "get_port_connection_member_by_key",
        "query_port_connection_members",
        "update_port_connection_member",
    ),
    "ReviewIssues": ("get_review_issue_by_key", "query_review_issues", "update_review_issue"),
}

# Independent expected matrix: deliberately not derived from the production
# table registries, so a registry omission cannot make verification pass.
STATUS_COLUMNS = {
    "SourceRequirements": True,
    "TypeDefinitions": True,
    "SimpleTypeDefinitions": None,
    "ArrayTypeDefinitions": None,
    "StructElements": False,
    "EnumValues": False,
    "PortInterfaces": True,
    "InterfaceDataElements": False,
    "ClientServerOperations": False,
    "OperationArguments": False,
    "PortPrototypes": True,
    "PortPrototypeFunctions": False,
    "PortConnections": True,
    "PortConnectionMembers": False,
    "ReviewIssues": False,
}

# A non-identity field suitable for proving each public update wrapper is wired
# to the correct record type. Expected values are checked through its getter.
UPDATE_CASES: dict[str, tuple[str, Any]] = {
    "SourceRequirements": ("source_reference", "REQ-UPDATED"),
    "TypeDefinitions": ("description", "updated description"),
    "SimpleTypeDefinitions": ("size", "32"),
    "ArrayTypeDefinitions": ("array_size", 9),
    "StructElements": ("description", "updated description"),
    "EnumValues": ("value", "2"),
    "PortInterfaces": ("description", "updated description"),
    "InterfaceDataElements": ("description", "updated description"),
    "ClientServerOperations": ("description", "updated description"),
    "OperationArguments": ("direction", "input_output"),
    "PortPrototypes": ("description", "updated description"),
    "PortPrototypeFunctions": ("function_name", "Rte_Updated"),
    "PortConnections": ("description", "updated description"),
    "PortConnectionMembers": ("position", 2),
    "ReviewIssues": ("resolution", "resolved by verification"),
}


@pytest.mark.parametrize("table", PUBLIC_METHODS)
def test_each_public_getter_returns_its_record(
    table: str,
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    getter_name = PUBLIC_METHODS[table][0]
    record = getattr(dal, getter_name)(phase2_conn, phase2_records[table][1])
    assert record is not None
    assert record.id == phase2_records[table][0]
    assert record.unique_key == phase2_records[table][1]


@pytest.mark.parametrize(
    "table", [table for table, (_, query, _) in PUBLIC_METHODS.items() if query is not None]
)
def test_each_public_query_can_filter_by_unique_key(
    table: str,
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    query_name = PUBLIC_METHODS[table][1]
    assert query_name is not None
    records = getattr(dal, query_name)(phase2_conn, {"unique_key": phase2_records[table][1]})
    assert [record.id for record in records] == [phase2_records[table][0]]


@pytest.mark.parametrize("table", PUBLIC_METHODS)
def test_each_public_update_changes_a_mutable_field_without_changing_identity(
    table: str,
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    getter_name, _, update_name = PUBLIC_METHODS[table]
    record_id, unique_key = phase2_records[table]
    field, expected = UPDATE_CASES[table]

    getattr(dal, update_name)(phase2_conn, record_id, **{field: expected})

    updated = getattr(dal, getter_name)(phase2_conn, unique_key)
    assert updated is not None
    assert updated.id == record_id
    assert updated.unique_key == unique_key
    assert getattr(updated, field) == expected


@pytest.mark.parametrize(
    ("table", "has_review_note"),
    [(table, has_note) for table, has_note in STATUS_COLUMNS.items() if has_note is not None],
)
def test_status_updates_cover_every_status_bearing_table(
    table: str,
    has_review_note: bool,
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    record_id, unique_key = phase2_records[table]
    new_status = "resolved" if table == "ReviewIssues" else "approved"

    dal.update_status(phase2_conn, table, record_id, new_status, "matrix note")

    record = dal.get_record_by_unique_key(phase2_conn, table, unique_key)
    assert record.status == new_status
    if has_review_note:
        assert record.review_note == "matrix note"


@pytest.mark.parametrize(
    "table", [table for table, has_note in STATUS_COLUMNS.items() if has_note is None]
)
def test_status_updates_reject_every_structural_subtype(
    table: str,
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    with pytest.raises(ValueError, match=f"{table} has no status column"):
        dal.update_status(phase2_conn, table, phase2_records[table][0], "approved")


def test_a_status_update_without_note_preserves_the_existing_note(
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    record_id, unique_key = phase2_records["TypeDefinitions"]
    dal.update_status(phase2_conn, "TypeDefinitions", record_id, "ambiguous", "keep me")

    dal.update_status(phase2_conn, "TypeDefinitions", record_id, "approved")

    record = dal.get_type_definition_by_key(phase2_conn, unique_key)
    assert record is not None
    assert record.review_note == "keep me"


def test_none_and_non_none_filters_can_be_combined(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    dal.insert_type_definition(phase2_conn, "null-struct", "NullRef", "struct")
    dal.insert_type_definition(phase2_conn, "null-enum", "NullRef", "enum")

    matches = dal.query_type_definitions(
        phase2_conn, {"source_requirement_id": None, "kind": "struct"}
    )

    assert [record.unique_key for record in matches] == ["null-struct"]


def test_all_nullable_cross_artifact_references_round_trip_as_null(
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    nullable_fields = {
        "ArrayTypeDefinitions": "element_type_id",
        "StructElements": "element_type_id",
        "InterfaceDataElements": "type_definition_id",
        "OperationArguments": "type_definition_id",
        "PortPrototypes": "port_interface_id",
    }

    for table, field in nullable_fields.items():
        record = dal.get_record_by_unique_key(phase2_conn, table, phase2_records[table][1])
        assert getattr(record, field) is None, table


def test_omitted_and_explicit_none_optionals_both_store_null(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    omitted_id = dal.insert_type_definition(phase2_conn, "omitted-optionals", "Omitted", "struct")
    explicit_id = dal.insert_type_definition(
        phase2_conn,
        "explicit-none-optionals",
        "ExplicitNone",
        "struct",
        description=None,
        source_requirement_id=None,
        review_note=None,
    )

    omitted = dal.get_type_definition_by_id(phase2_conn, omitted_id)
    explicit = dal.get_type_definition_by_id(phase2_conn, explicit_id)
    assert omitted is not None and explicit is not None
    assert omitted.description is None and explicit.description is None
    assert omitted.source_requirement_id is None and explicit.source_requirement_id is None
    assert omitted.review_note is None and explicit.review_note is None
    assert omitted.status == explicit.status == "pending_review"


def test_generic_insert_uses_the_schema_default_only_when_status_is_omitted(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    record_id = dal._insert(
        phase2_conn,
        TypeDefinitionRecord,
        {"unique_key": "schema-default", "name": "SchemaDefault", "kind": "struct"},
    )

    record = dal.get_type_definition_by_id(phase2_conn, record_id)
    assert record is not None
    assert record.status == "pending_review"

    with pytest.raises(sqlite3.IntegrityError):
        dal._insert(
            phase2_conn,
            TypeDefinitionRecord,
            {
                "unique_key": "explicit-null-status",
                "name": "ExplicitNullStatus",
                "kind": "struct",
                "status": None,
            },
        )


def test_port_prototype_functions_without_position_are_ordered_by_id(
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    first_id = phase2_records["PortPrototypeFunctions"][0]
    prototype_id = phase2_records["PortPrototypes"][0]
    second_id = dal.insert_port_prototype_function(
        phase2_conn, "verify-function-2", prototype_id, "Rte_Verify2", "access_point"
    )

    records = dal.query_port_prototype_functions(phase2_conn)

    assert [record.id for record in records] == [first_id, second_id]


def test_unique_key_collision_resolution_is_deterministic(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    dal.insert_source_requirement(phase2_conn, "shared-key", "REQ-SHARED")
    dal.insert_type_definition(phase2_conn, "shared-key", "Shared", "struct")

    resolved = dal.resolve_unique_key(phase2_conn, "shared-key")

    assert resolved is not None
    assert resolved[0] == "SourceRequirements"


@pytest.mark.parametrize(
    ("table", "expected_key", "insert"),
    [
        (
            "PortInterfaces",
            "duplicate-interface",
            lambda dal, conn: dal.insert_port_interface(
                conn, "duplicate-interface", "MixedCase", "client_server"
            ),
        ),
        (
            "PortPrototypes",
            "duplicate-prototype",
            lambda dal, conn: dal.insert_port_prototype(
                conn, "duplicate-prototype", "MixedCase", "provider", "Swc"
            ),
        ),
    ],
)
def test_duplicate_queries_cover_all_named_artifact_families(
    table: str,
    expected_key: str,
    insert: Any,
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
) -> None:
    insert(dal, phase2_conn)

    matches = dal.find_duplicates_by_name(phase2_conn, table, "mixedcase")

    assert [record.unique_key for record in matches] == [expected_key]


def test_kind_filter_is_rejected_for_a_named_table_without_kind(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    with pytest.raises(ValueError, match="PortInterfaces has no kind column"):
        dal.find_duplicates_by_name(phase2_conn, "PortInterfaces", "anything", kind="client_server")


def test_duplicate_search_rejects_a_table_without_name(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    with pytest.raises(ValueError, match="SourceRequirements has no name column"):
        dal.find_duplicates_by_name(phase2_conn, "SourceRequirements", "anything")


def test_bound_values_are_not_interpreted_as_sql(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    hostile_name = 'name"; DROP TABLE "TypeDefinitions"; --'
    dal.insert_type_definition(phase2_conn, "hostile-key", hostile_name, "struct")

    record = dal.find_duplicates_by_name(phase2_conn, "TypeDefinitions", hostile_name)[0]

    assert record.name == hostile_name
    assert dal.get_type_definition_by_key(phase2_conn, "hostile-key") is not None


def test_children_statuses_rejects_a_non_foreign_key_column_name(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    with pytest.raises(ValueError, match="unknown column"):
        dal.get_children_statuses(phase2_conn, "StructElements", "struct_type_id OR 1=1", 1)


def test_children_statuses_rejects_a_table_without_status(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    with pytest.raises(ValueError, match="has no status column"):
        dal.get_children_statuses(phase2_conn, "SimpleTypeDefinitions", "type_definition_id", 1)


def test_missing_parent_subtype_lookup_returns_none(
    phase2_conn: sqlite3.Connection, dal: DataAccessLayer
) -> None:
    parent_id = dal.insert_type_definition(
        phase2_conn, "parent-without-detail", "NoDetail", "simple_typedef"
    )

    assert dal.get_simple_type_definition_by_parent(phase2_conn, parent_id) is None
    assert dal.get_array_type_definition_by_parent(phase2_conn, parent_id) is None


def test_parent_subtype_getters_return_the_existing_detail_rows(
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    simple = dal.get_simple_type_definition_by_key(phase2_conn, "verify-simple")
    array = dal.get_array_type_definition_by_key(phase2_conn, "verify-array")
    assert simple is not None and array is not None
    assert (
        dal.get_simple_type_definition_by_parent(phase2_conn, simple.type_definition_id) == simple
    )
    assert dal.get_array_type_definition_by_parent(phase2_conn, array.type_definition_id) == array


def test_children_statuses_returns_only_the_requested_parents_children(
    phase2_conn: sqlite3.Connection,
    dal: DataAccessLayer,
    phase2_records: dict[str, tuple[int, str]],
) -> None:
    parent_id = phase2_records["TypeDefinitions"][0]
    other_parent = dal.insert_type_definition(phase2_conn, "other-struct", "OtherStruct", "struct")
    dal.insert_struct_element(phase2_conn, "other-child", other_parent, "other", None, 1)
    dal.update_status(
        phase2_conn, "StructElements", phase2_records["StructElements"][0], "approved"
    )

    assert dal.get_children_statuses(
        phase2_conn, "StructElements", "struct_type_id", parent_id
    ) == ["approved"]
