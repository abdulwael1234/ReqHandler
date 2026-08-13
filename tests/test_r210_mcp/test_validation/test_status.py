"""Development tests for the status rules (LLD-02 §6.2)."""

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.validation.status import (
    auto_demote_parent_chain,
    check_parent_can_be_approved,
    check_references_resolved,
    validate_artifact_transition,
    validate_issue_transition,
)


class TestTransitions:
    @pytest.mark.parametrize(
        ("current", "requested"),
        [
            ("pending_review", "approved"),
            ("pending_review", "out_of_scope"),
            ("approved", "pending_review"),
            ("approved", "rejected"),
            ("rejected", "pending_review"),
            ("ambiguous", "approved"),
            ("out_of_scope", "pending_review"),
        ],
    )
    def test_permitted_transitions_are_accepted(self, current: str, requested: str) -> None:
        """SRS-035b — the permitted artifact transition matrix."""
        validate_artifact_transition(current, requested, operation="set_review_status")

    @pytest.mark.parametrize(
        ("current", "requested"),
        [
            ("approved", "ambiguous"),
            ("approved", "out_of_scope"),
            ("rejected", "approved"),
            ("out_of_scope", "approved"),
            ("pending_review", "pending_review"),
        ],
    )
    def test_forbidden_transitions_are_rejected(self, current: str, requested: str) -> None:
        """SRS-035b — no transition outside the matrix is permitted."""
        with pytest.raises(McpValidationError) as caught:
            validate_artifact_transition(current, requested, operation="set_review_status")
        assert caught.value.error.field == "new_status"

    def test_issue_transitions_follow_their_own_matrix(self) -> None:
        """SRS-035b — issues use pending/resolved/rejected."""
        validate_issue_transition("pending", "resolved", operation="update_review_issue")
        with pytest.raises(McpValidationError):
            validate_issue_transition("resolved", "rejected", operation="update_review_issue")

    def test_the_reported_field_is_caller_chosen(self) -> None:
        """update_review_issue names its argument `status`, not `new_status`."""
        with pytest.raises(McpValidationError) as caught:
            validate_issue_transition(
                "resolved", "rejected", operation="update_review_issue", field="status"
            )
        assert caught.value.error.field == "status"


class TestParentApproval:
    def test_pending_child_blocks_the_parent(self, initialized_db: str) -> None:
        """SRS-046, SRS-053 — a parent cannot be approved over a pending child."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
        with db.read_only() as conn:
            blockers = check_parent_can_be_approved(conn, dal, "TypeDefinitions", parent_id)
        assert len(blockers) == 1
        assert blockers[0]["child_table"] == "EnumValues"
        assert blockers[0]["status"] == "pending_review"

    def test_rejected_child_does_not_block(self, initialized_db: str) -> None:
        """SRS-092a — rejected children are excluded from the evaluation."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
            dal.update_status(conn, "EnumValues", child_id, "rejected")
        with db.read_only() as conn:
            assert check_parent_can_be_approved(conn, dal, "TypeDefinitions", parent_id) == []

    def test_all_children_approved_is_clear(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
            dal.update_status(conn, "EnumValues", child_id, "approved")
        with db.read_only() as conn:
            assert check_parent_can_be_approved(conn, dal, "TypeDefinitions", parent_id) == []

    def test_a_childless_parent_is_clear(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_port_connection(conn, "pc")
        with db.read_only() as conn:
            assert check_parent_can_be_approved(conn, dal, "PortConnections", parent_id) == []


class TestDemotionChain:
    def test_demotes_an_approved_parent(self, initialized_db: str) -> None:
        """SRS-035c — an approved parent is demoted when a child changes."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
            dal.update_status(conn, "TypeDefinitions", parent_id, "approved")
        with db.transaction() as conn:
            demoted = auto_demote_parent_chain(conn, dal, "EnumValues", child_id)
        assert demoted == ["td"]
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "TypeDefinitions", parent_id)
        assert record.status == "pending_review"

    def test_walks_the_grandparent_chain(self, initialized_db: str) -> None:
        """SRS-035c — OperationArguments -> Operation -> PortInterface."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            iface_id = dal.insert_port_interface(conn, "pi", "Iface", "client_server")
            op_id = dal.insert_client_server_operation(conn, "op", iface_id, "Get", 1)
            arg_id = dal.insert_operation_argument(conn, "arg", op_id, "a", None, "input", 1)
            dal.update_status(conn, "ClientServerOperations", op_id, "approved")
            dal.update_status(conn, "PortInterfaces", iface_id, "approved")
        with db.transaction() as conn:
            demoted = auto_demote_parent_chain(conn, dal, "OperationArguments", arg_id)
        assert demoted == ["op", "pi"]

    def test_leaves_a_non_approved_parent_alone(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
        with db.transaction() as conn:
            assert auto_demote_parent_chain(conn, dal, "EnumValues", child_id) == []


class TestReferencesResolved:
    def test_unresolved_struct_element_reference_is_reported(self, initialized_db: str) -> None:
        """SRS-036a — a record with an unresolved reference cannot be approved."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
            child_id = dal.insert_struct_element(conn, "se", parent_id, "value", None, 1)
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "StructElements", child_id)
            unresolved = check_references_resolved(conn, dal, "StructElements", record)
        assert unresolved == ["element_type_id"]

    def test_resolved_reference_is_clear(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            target_id = dal.insert_type_definition(conn, "t", "U8", "simple_typedef")
            parent_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
            child_id = dal.insert_struct_element(conn, "se", parent_id, "value", target_id, 1)
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "StructElements", child_id)
            assert check_references_resolved(conn, dal, "StructElements", record) == []

    def test_array_parent_inherits_its_subtype_reference(self, initialized_db: str) -> None:
        """SRS-036a — approving an array TypeDefinition checks its detail row."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Buffer", "array")
            dal.insert_array_type_definition(conn, "at", parent_id, None, 8)
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "TypeDefinitions", parent_id)
            unresolved = check_references_resolved(conn, dal, "TypeDefinitions", record)
        assert unresolved == ["element_type_id"]

    def test_a_table_without_references_is_clear(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            record_id = dal.insert_source_requirement(conn, "sr", "REQ-1")
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "SourceRequirements", record_id)
            assert check_references_resolved(conn, dal, "SourceRequirements", record) == []
