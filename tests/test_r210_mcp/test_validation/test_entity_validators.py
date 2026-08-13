"""Development tests for the entity validators (LLD-02 §6.3-6.5)."""

import sqlite3

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.validation.port_connections import (
    create_compatibility_review_issue,
    validate_connection_complete,
)
from r210_mcp.validation.port_interfaces import (
    ARGUMENT_DIRECTIONS,
    CHILD_REQUIRED_INTERFACE_TYPE,
    INTERFACE_TYPES,
    PORT_DIRECTIONS,
    RELATIONSHIP_TYPES,
    validate_child_interface_type,
)
from r210_mcp.validation.type_definitions import (
    KIND_SUBTYPE_MAP,
    KINDS,
    validate_kind_value,
    validate_parent_kind,
    validate_subtype_matches_kind,
)


def _prototype(dal: DataAccessLayer, conn: sqlite3.Connection, key: str, direction: str) -> int:
    return dal.insert_port_prototype(conn, key, f"Port{key}", direction, "ECU")


class TestKinds:
    def test_the_four_permitted_kinds(self) -> None:
        """SRS-043 — kind is one of four values."""
        assert KINDS == frozenset({"simple_typedef", "array", "struct", "enum"})
        assert set(KIND_SUBTYPE_MAP) == KINDS

    def test_rejects_an_unknown_kind(self) -> None:
        with pytest.raises(McpValidationError) as caught:
            validate_kind_value("record", operation="create_type_definition")
        assert caught.value.error.field == "kind"


class TestSubtypeMatchesKind:
    def test_accepts_the_matching_shape(self) -> None:
        """SRS-038a, SRS-044 — the subtype detail must match the kind."""
        validate_subtype_matches_kind(
            "simple_typedef", {"base_type": "uint8"}, operation="create_type_definition"
        )
        validate_subtype_matches_kind("array", {"array_size": 4}, operation="t")
        validate_subtype_matches_kind("struct", {"elements": []}, operation="t")
        validate_subtype_matches_kind("enum", {"values": []}, operation="t")

    def test_missing_subtype_is_rejected(self) -> None:
        """SRS-038a — the subtype detail is required."""
        with pytest.raises(McpValidationError) as caught:
            validate_subtype_matches_kind("array", None, operation="create_type_definition")
        assert caught.value.error.field == "subtype"

    def test_wrong_shape_is_rejected(self) -> None:
        """SRS-044 — an array subtype on a struct kind is a mismatch."""
        with pytest.raises(McpValidationError):
            validate_subtype_matches_kind("struct", {"array_size": 4}, operation="t")


class TestParentKind:
    def test_accepts_the_expected_kind(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
        with db.read_only() as conn:
            validate_parent_kind(
                conn, dal, parent_id, "enum", operation="create_enum_value", field="enum_type_key"
            )

    def test_rejects_the_wrong_parent_kind(self, initialized_db: str) -> None:
        """SRS-044 — an EnumValue may only hang off an enum."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
        with db.read_only() as conn:
            with pytest.raises(McpValidationError) as caught:
                validate_parent_kind(
                    conn,
                    dal,
                    parent_id,
                    "enum",
                    operation="create_enum_value",
                    field="enum_type_key",
                )
        assert caught.value.error.field == "enum_type_key"


class TestInterfaceVocabularies:
    def test_match_the_schema_check_constraints(self) -> None:
        """SRS-052, SRS-059, SRS-061, SRS-063 — the permitted value sets."""
        assert INTERFACE_TYPES == frozenset({"sender_receiver", "client_server"})
        assert ARGUMENT_DIRECTIONS == frozenset({"input", "output", "input_output"})
        assert PORT_DIRECTIONS == frozenset({"provider", "requester"})
        assert RELATIONSHIP_TYPES == frozenset({"access_point", "trigger"})

    def test_children_require_the_right_interface_type(self) -> None:
        """SRS-055 — data elements need sender_receiver, operations client_server."""
        assert CHILD_REQUIRED_INTERFACE_TYPE["InterfaceDataElements"] == "sender_receiver"
        assert CHILD_REQUIRED_INTERFACE_TYPE["ClientServerOperations"] == "client_server"


class TestChildInterfaceType:
    def test_accepts_a_matching_parent(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            iface_id = dal.insert_port_interface(conn, "pi", "Iface", "sender_receiver")
        with db.read_only() as conn:
            validate_child_interface_type(
                conn,
                dal,
                iface_id,
                "InterfaceDataElements",
                operation="create_interface_data_element",
                field="port_interface_key",
            )

    def test_rejects_a_mismatched_parent(self, initialized_db: str) -> None:
        """SRS-055 — a data element cannot hang off a client_server interface."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            iface_id = dal.insert_port_interface(conn, "pi", "Iface", "client_server")
        with db.read_only() as conn:
            with pytest.raises(McpValidationError) as caught:
                validate_child_interface_type(
                    conn,
                    dal,
                    iface_id,
                    "InterfaceDataElements",
                    operation="create_interface_data_element",
                    field="port_interface_key",
                )
        assert caught.value.error.field == "port_interface_key"
        assert "sender_receiver" in caught.value.error.reason


class TestValidateConnectionComplete:
    def test_accepts_one_provider_and_one_requester(self, initialized_db: str) -> None:
        """SRS-072 — a valid connection has at least one of each."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            provider = _prototype(dal, conn, "p", "provider")
            requester = _prototype(dal, conn, "r", "requester")
            connection_id = dal.insert_port_connection(conn, "pc")
            dal.insert_port_connection_member(conn, "m1", connection_id, provider, 1)
            dal.insert_port_connection_member(conn, "m2", connection_id, requester, 2)
        with db.read_only() as conn:
            validate_connection_complete(conn, dal, connection_id, operation="t")

    def test_rejects_a_missing_requester(self, initialized_db: str) -> None:
        """SRS-072 — direction cardinality requires >=1 provider and >=1 requester."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            provider = _prototype(dal, conn, "p", "provider")
            connection_id = dal.insert_port_connection(conn, "pc")
            dal.insert_port_connection_member(conn, "m1", connection_id, provider, 1)
        with db.read_only() as conn:
            with pytest.raises(McpValidationError) as caught:
                validate_connection_complete(conn, dal, connection_id, operation="t")
        assert "requester" in caught.value.error.reason

    def test_a_duplicate_prototype_cannot_be_stored(self, initialized_db: str) -> None:
        """SRS-070 — enforced by the schema, not reachable through the DAL.

        V001 puts a UNIQUE constraint on (port_connection_id, port_prototype_id),
        so the duplicate branch inside `validate_connection_complete` is defence
        in depth for rows that arrive some other way. This test pins the real
        enforcement point.
        """
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction() as conn:
                provider = _prototype(dal, conn, "p", "provider")
                connection_id = dal.insert_port_connection(conn, "pc")
                dal.insert_port_connection_member(conn, "m1", connection_id, provider, 1)
                dal.insert_port_connection_member(conn, "m3", connection_id, provider, 2)

    def test_rejects_an_empty_connection(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            connection_id = dal.insert_port_connection(conn, "pc")
        with db.read_only() as conn:
            with pytest.raises(McpValidationError):
                validate_connection_complete(conn, dal, connection_id, operation="t")


class TestCompatibilityIssue:
    def test_creates_an_incomplete_issue(self, initialized_db: str) -> None:
        """SRS-125 — compatibility is TBD, so record it rather than assume it."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            dal.insert_port_connection(conn, "pc")
            create_compatibility_review_issue(conn, dal, "pc", None)
        with db.read_only() as conn:
            issues = dal.query_review_issues(conn, {"artifact_unique_key": "pc"})
        assert len(issues) == 1
        assert issues[0].issue_type == "incomplete"
        assert issues[0].artifact_type == "port_connection"
