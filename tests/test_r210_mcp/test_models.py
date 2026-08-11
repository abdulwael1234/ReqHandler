"""Tests for the database record models and registries (LLD-02 §3.3–§3.5).

Requirement coverage: SRS-035, SRS-035a, SRS-035b, SRS-074, SRS-076.

These tests validate the in-memory model layer against the schema that the
initializer actually creates, so the two cannot drift apart silently.
"""

import dataclasses
import sqlite3

import pytest

from r210_mcp.db.models import (
    ARTIFACT_STATUSES,
    ARTIFACT_TABLES,
    ARTIFACT_TRANSITIONS,
    ARTIFACT_TYPE_TABLE_MAP,
    CHILD_PARENT_MAP,
    ISSUE_STATUSES,
    ISSUE_TRANSITIONS,
    PARENT_CHILD_MAP,
    REVIEWABLE_CHILD_TABLES,
    STRUCTURAL_SUBTYPE_TABLES,
    TABLE_RECORD_MAP,
)


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }


class TestStatusConstants:
    def test_artifact_statuses_are_the_five_review_states(self) -> None:
        """SRS-035."""
        assert ARTIFACT_STATUSES == frozenset(
            {"pending_review", "approved", "rejected", "ambiguous", "out_of_scope"}
        )

    def test_issue_statuses_are_the_three_issue_states(self) -> None:
        """SRS-076."""
        assert ISSUE_STATUSES == frozenset({"pending", "resolved", "rejected"})


class TestStatusTransitions:
    """SRS-035b: the permitted state transitions, exactly as specified."""

    def test_artifact_transitions_match_the_specified_matrix(self) -> None:
        assert ARTIFACT_TRANSITIONS == {
            "pending_review": frozenset({"approved", "rejected", "ambiguous", "out_of_scope"}),
            "approved": frozenset({"pending_review", "rejected"}),
            "rejected": frozenset({"pending_review"}),
            "ambiguous": frozenset({"pending_review", "approved", "rejected", "out_of_scope"}),
            "out_of_scope": frozenset({"pending_review"}),
        }

    def test_issue_transitions_match_the_specified_matrix(self) -> None:
        assert ISSUE_TRANSITIONS == {
            "pending": frozenset({"resolved", "rejected"}),
            "resolved": frozenset({"pending"}),
            "rejected": frozenset({"pending"}),
        }

    def test_every_artifact_status_has_a_transition_entry(self) -> None:
        assert set(ARTIFACT_TRANSITIONS) == set(ARTIFACT_STATUSES)

    def test_every_issue_status_has_a_transition_entry(self) -> None:
        assert set(ISSUE_TRANSITIONS) == set(ISSUE_STATUSES)

    def test_transition_targets_are_all_known_statuses(self) -> None:
        for targets in ARTIFACT_TRANSITIONS.values():
            assert targets <= ARTIFACT_STATUSES
        for targets in ISSUE_TRANSITIONS.values():
            assert targets <= ISSUE_STATUSES

    def test_no_status_transitions_to_itself(self) -> None:
        for source, targets in ARTIFACT_TRANSITIONS.items():
            assert source not in targets
        for source, targets in ISSUE_TRANSITIONS.items():
            assert source not in targets

    def test_approved_is_not_reachable_from_rejected_or_out_of_scope(self) -> None:
        """SRS-035b: those states must pass back through pending_review first."""
        assert "approved" not in ARTIFACT_TRANSITIONS["rejected"]
        assert "approved" not in ARTIFACT_TRANSITIONS["out_of_scope"]


class TestRecordDataclasses:
    """LLD-02 §3.3: a frozen dataclass per table, matching the real schema."""

    def test_every_table_in_the_schema_has_a_record_dataclass(
        self, conn: sqlite3.Connection
    ) -> None:
        schema_tables = _table_names(conn) - {"sqlite_sequence"}

        assert schema_tables == set(TABLE_RECORD_MAP)

    @pytest.mark.parametrize("table", sorted(TABLE_RECORD_MAP))
    def test_dataclass_fields_match_table_columns_in_order(
        self, conn: sqlite3.Connection, table: str
    ) -> None:
        record_type = TABLE_RECORD_MAP[table]
        field_names = [f.name for f in dataclasses.fields(record_type)]

        assert field_names == _columns(conn, table)

    @pytest.mark.parametrize("table", sorted(TABLE_RECORD_MAP))
    def test_record_dataclasses_are_frozen(self, table: str) -> None:
        record_type = TABLE_RECORD_MAP[table]

        assert dataclasses.is_dataclass(record_type)
        assert record_type.__dataclass_params__.frozen


class TestTableGroupings:
    """SRS-035a: which tables are reviewable, and which are structural extensions."""

    def test_reviewable_child_tables_are_the_seven_specified(self) -> None:
        assert REVIEWABLE_CHILD_TABLES == frozenset(
            {
                "StructElements",
                "EnumValues",
                "InterfaceDataElements",
                "ClientServerOperations",
                "OperationArguments",
                "PortConnectionMembers",
                "PortPrototypeFunctions",
            }
        )

    def test_structural_subtype_tables_are_the_two_specified(self) -> None:
        assert STRUCTURAL_SUBTYPE_TABLES == frozenset(
            {"SimpleTypeDefinitions", "ArrayTypeDefinitions"}
        )

    @pytest.mark.parametrize("table", sorted(REVIEWABLE_CHILD_TABLES))
    def test_reviewable_child_tables_have_a_status_column(
        self, conn: sqlite3.Connection, table: str
    ) -> None:
        assert "status" in _columns(conn, table)

    @pytest.mark.parametrize("table", sorted(STRUCTURAL_SUBTYPE_TABLES))
    def test_structural_subtype_tables_have_no_status_column(
        self, conn: sqlite3.Connection, table: str
    ) -> None:
        assert "status" not in _columns(conn, table)

    @pytest.mark.parametrize("table", sorted(ARTIFACT_TABLES))
    def test_artifact_tables_carry_status_and_review_note(
        self, conn: sqlite3.Connection, table: str
    ) -> None:
        """SRS-091a: review_note lives on artifact tables, not on children."""
        columns = _columns(conn, table)

        assert "status" in columns
        assert "review_note" in columns

    def test_artifact_and_child_table_groups_do_not_overlap(self) -> None:
        assert not ARTIFACT_TABLES & REVIEWABLE_CHILD_TABLES
        assert not ARTIFACT_TABLES & STRUCTURAL_SUBTYPE_TABLES
        assert not REVIEWABLE_CHILD_TABLES & STRUCTURAL_SUBTYPE_TABLES


class TestParentChildRegistry:
    """LLD-02 §3.5: the registry used for parent-approval blocking and demotion."""

    def test_registry_covers_every_reviewable_child_table(self) -> None:
        registered = {
            relation.child_table
            for relations in PARENT_CHILD_MAP.values()
            for relation in relations
        }

        assert registered == REVIEWABLE_CHILD_TABLES

    def test_parent_tables_exist_in_the_schema(self, conn: sqlite3.Connection) -> None:
        assert set(PARENT_CHILD_MAP) <= _table_names(conn)

    def test_declared_foreign_key_columns_exist_on_the_child_tables(
        self, conn: sqlite3.Connection
    ) -> None:
        for relations in PARENT_CHILD_MAP.values():
            for relation in relations:
                assert relation.fk_column in _columns(conn, relation.child_table)

    def test_declared_relations_match_the_real_foreign_keys(
        self, conn: sqlite3.Connection
    ) -> None:
        """The registry must describe FKs the database actually declares."""
        for parent_table, relations in PARENT_CHILD_MAP.items():
            for relation in relations:
                actual = {
                    (row[3], row[2])  # (from-column, referenced table)
                    for row in conn.execute(f"PRAGMA foreign_key_list({relation.child_table})")
                }
                assert (relation.fk_column, parent_table) in actual

    def test_child_parent_map_is_the_inverse_of_parent_child_map(self) -> None:
        derived = {
            relation.child_table: (parent_table, relation.fk_column)
            for parent_table, relations in PARENT_CHILD_MAP.items()
            for relation in relations
        }
        actual = {
            child: (relation.parent_table, relation.fk_column)
            for child, relation in CHILD_PARENT_MAP.items()
        }

        assert actual == derived

    def test_operation_arguments_reach_port_interfaces_through_a_grandparent_chain(self) -> None:
        """LLD-01 §5: OperationArguments → ClientServerOperations → PortInterfaces."""
        parent = CHILD_PARENT_MAP["OperationArguments"].parent_table
        grandparent = CHILD_PARENT_MAP[parent].parent_table

        assert parent == "ClientServerOperations"
        assert grandparent == "PortInterfaces"


class TestArtifactTypeMap:
    """SRS-074: the typed polymorphic reference resolves to a real table."""

    def test_covers_exactly_the_eleven_specified_artifact_types(self) -> None:
        assert set(ARTIFACT_TYPE_TABLE_MAP) == {
            "type_definition",
            "struct_element",
            "enum_value",
            "port_interface",
            "interface_data_element",
            "client_server_operation",
            "operation_argument",
            "port_prototype",
            "port_prototype_function",
            "port_connection",
            "port_connection_member",
        }

    def test_every_artifact_type_maps_to_an_existing_table(
        self, conn: sqlite3.Connection
    ) -> None:
        assert set(ARTIFACT_TYPE_TABLE_MAP.values()) <= _table_names(conn)

    def test_mapping_is_one_to_one(self) -> None:
        values = list(ARTIFACT_TYPE_TABLE_MAP.values())

        assert len(set(values)) == len(values)

    def test_schema_check_constraint_accepts_every_mapped_artifact_type(
        self, conn: sqlite3.Connection
    ) -> None:
        """The model list and the CHECK constraint in LLD-01 §3.15 must agree."""
        for index, artifact_type in enumerate(ARTIFACT_TYPE_TABLE_MAP):
            conn.execute(
                "INSERT INTO ReviewIssues (unique_key, artifact_type, issue_type, message) "
                "VALUES (?, ?, 'ambiguous', 'check')",
                (f"issue-{index}", artifact_type),
            )
