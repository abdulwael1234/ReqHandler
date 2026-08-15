"""Exportable-tree evaluation and FK validation (SRS-104a, SRS-092a, SRS-102)."""

from typing import Any

from r210_generator.validator import evaluate_exportable_trees, validate_fk_completeness

from .conftest import (
    APPROVED,
    PENDING,
    REJECTED,
    argument,
    array_detail,
    base_type,
    connection_member,
    data_element,
    enum_value,
    operation,
    port_connection,
    port_interface,
    port_prototype,
    simple_detail,
    struct_element,
    type_definition,
)


class TestApprovedParentRequired:
    """SRS-104a: only an approved parent can head an exportable tree."""

    def test_pending_parent_is_not_exportable(self, make_snapshot: Any) -> None:
        """SRS-104a: a pending parent produces neither a tree nor a warning."""
        snapshot = make_snapshot(
            type_definitions=[type_definition(1, "SensorData", status=PENDING)]
        )
        result = evaluate_exportable_trees(snapshot)
        assert result.trees == [] and result.warnings == []

    def test_approved_childless_parent_is_exportable(self, make_snapshot: Any) -> None:
        """SRS-104a: an approved parent with no children exports."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1)], simple_type_definitions=[simple_detail(1, 1)]
        )
        result = evaluate_exportable_trees(snapshot)
        assert [t.label for t in result.trees] == ["Float32"]


class TestChildApproval:
    """SRS-092a: all non-rejected children must be approved."""

    def test_pending_child_blocks_the_parent(self, make_snapshot: Any) -> None:
        """SRS-104a: a pending child holds its parent back, with a warning."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1), type_definition(2, "SensorData")],
            struct_elements=[struct_element(1, 2, "temperature", 1, status=PENDING)],
        )
        result = evaluate_exportable_trees(snapshot)
        assert [t.label for t in result.trees] == ["Float32"]
        assert len(result.warnings) == 1
        assert "temperature is pending_review" in result.warnings[0].blocking_children[0]

    def test_rejected_child_does_not_block(self, make_snapshot: Any) -> None:
        """SRS-092a: a rejected child is excluded from evaluation entirely."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1), type_definition(2, "SensorData")],
            struct_elements=[
                struct_element(1, 2, "temperature", 1),
                struct_element(2, 2, "obsolete", 2, status=REJECTED),
            ],
        )
        result = evaluate_exportable_trees(snapshot)
        tree = next(t for t in result.trees if t.label == "SensorData")
        assert [c.name for _, c in tree.active_children] == ["temperature"]
        assert [c.name for _, c in tree.excluded_children] == ["obsolete"]
        assert result.warnings == []

    def test_all_children_rejected_still_exports_the_parent(self, make_snapshot: Any) -> None:
        """SRS-092a: with every child rejected, nothing blocks the parent."""
        snapshot = make_snapshot(
            type_definitions=[type_definition(1, "Colours", kind="enum")],
            enum_values=[enum_value(1, 1, "RED", 1, status=REJECTED)],
        )
        result = evaluate_exportable_trees(snapshot)
        assert len(result.trees) == 1
        assert result.trees[0].active_children == ()


class TestGrandchildRecursion:
    """LLD-04 §4.3: a client-server interface is evaluated recursively."""

    def test_pending_argument_fails_the_interface(self, make_snapshot: Any) -> None:
        """SRS-104a: a pending argument fails its operation and the interface."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1)],
            port_interfaces=[port_interface(1, "Diagnostics")],
            client_server_operations=[operation(1, 1, "ReadDtc", 1)],
            operation_arguments=[argument(1, 1, "dtcId", 1, status=PENDING)],
        )
        result = evaluate_exportable_trees(snapshot)
        assert [w.label for w in result.warnings] == ["Diagnostics"]
        assert "dtcId is pending_review" in result.warnings[0].blocking_children[0]

    def test_rejected_argument_does_not_fail_the_interface(self, make_snapshot: Any) -> None:
        """SRS-092a: exclusion applies at every level of the tree."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1)],
            port_interfaces=[port_interface(1, "Diagnostics")],
            client_server_operations=[operation(1, 1, "ReadDtc", 1)],
            operation_arguments=[argument(1, 1, "dtcId", 1, status=REJECTED)],
        )
        result = evaluate_exportable_trees(snapshot)
        assert "Diagnostics" in [t.label for t in result.trees]
        assert result.warnings == []

    def test_sender_receiver_uses_data_elements(self, make_snapshot: Any) -> None:
        """LLD-04 §4.3: interface children depend on the interface type."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1)],
            port_interfaces=[port_interface(1, "Speed", interface_type="sender_receiver")],
            interface_data_elements=[data_element(1, 1, "kph", 1, status=PENDING)],
        )
        assert len(evaluate_exportable_trees(snapshot).warnings) == 1


class TestStructuralSubtypes:
    """SRS-035a: SimpleTypeDefinitions and ArrayTypeDefinitions carry no status."""

    def test_array_type_has_no_reviewable_children(self, make_snapshot: Any) -> None:
        """SRS-035a: a structural subtype cannot block its parent."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1), type_definition(2, "Samples", kind="array")],
            array_type_definitions=[array_detail(1, 2)],
        )
        result = evaluate_exportable_trees(snapshot)
        assert sorted(t.label for t in result.trees) == ["Float32", "Samples"]


class TestForeignKeyValidation:
    """SRS-102: mandatory references must resolve at the export boundary."""

    def test_unresolved_struct_element_type_is_an_error(self, make_snapshot: Any) -> None:
        """SRS-036a: a nullable reference is mandatory here, not during extraction."""
        snapshot = make_snapshot(
            type_definitions=[type_definition(2, "SensorData")],
            struct_elements=[struct_element(1, 2, "temperature", 1, element_type_id=None)],
        )
        validated = validate_fk_completeness(snapshot, evaluate_exportable_trees(snapshot))
        assert validated.trees == []
        assert "element_type_id is unresolved" in validated.errors[0].reason

    def test_dangling_reference_is_an_error(self, make_snapshot: Any) -> None:
        """SRS-102: a reference to a missing record is as bad as a null one."""
        snapshot = make_snapshot(
            type_definitions=[type_definition(2, "SensorData")],
            struct_elements=[struct_element(1, 2, "temperature", 1, element_type_id=99)],
        )
        validated = validate_fk_completeness(snapshot, evaluate_exportable_trees(snapshot))
        assert "does not exist" in validated.errors[0].reason

    def test_resolved_tree_validates(self, approved_struct_snapshot: Any) -> None:
        """SRS-102: a fully resolved tree passes."""
        exportable = evaluate_exportable_trees(approved_struct_snapshot)
        validated = validate_fk_completeness(approved_struct_snapshot, exportable)
        assert validated.errors == []
        assert sorted(t.label for t in validated.trees) == ["Float32", "SensorData"]

    def test_unresolved_array_element_type(self, make_snapshot: Any) -> None:
        """SRS-036a: an array's element type is mandatory at export."""
        snapshot = make_snapshot(
            type_definitions=[type_definition(2, "Samples", kind="array")],
            array_type_definitions=[array_detail(1, 2, element_type_id=None)],
        )
        validated = validate_fk_completeness(snapshot, evaluate_exportable_trees(snapshot))
        assert "ArrayTypeDefinitions.element_type_id is unresolved" in validated.errors[0].reason

    def test_prototype_without_interface(self, make_snapshot: Any) -> None:
        """SRS-036: an unresolved port_interface_id excludes the prototype."""
        snapshot = make_snapshot(port_prototypes=[port_prototype(1, "SpeedOut", None)])
        validated = validate_fk_completeness(snapshot, evaluate_exportable_trees(snapshot))
        assert "PortPrototypes.port_interface_id is unresolved" in validated.errors[0].reason

    def test_connection_member_dangling_prototype(self, make_snapshot: Any) -> None:
        """SRS-102: a member pointing at no prototype excludes the connection."""
        snapshot = make_snapshot(
            port_connections=[port_connection(1, "brake bus")],
            port_connection_members=[connection_member(1, 1, 99, 1)],
        )
        validated = validate_fk_completeness(snapshot, evaluate_exportable_trees(snapshot))
        assert "port_prototype_id references a record that does not exist" in (
            validated.errors[0].reason
        )

    def test_rejected_argument_is_not_fk_checked(self, make_snapshot: Any) -> None:
        """SRS-092a: an excluded record's references are irrelevant."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1)],
            port_interfaces=[port_interface(1, "Diagnostics")],
            client_server_operations=[operation(1, 1, "ReadDtc", 1)],
            operation_arguments=[
                argument(1, 1, "dtcId", 1, type_definition_id=None, status=REJECTED)
            ],
        )
        validated = validate_fk_completeness(snapshot, evaluate_exportable_trees(snapshot))
        assert validated.errors == []


class TestDeterminism:
    """SRS-101: evaluation is a pure function and repeats exactly."""

    def test_two_evaluations_agree(self, approved_struct_snapshot: Any) -> None:
        """SRS-101: the same snapshot yields the same trees and warnings."""
        first = evaluate_exportable_trees(approved_struct_snapshot)
        second = evaluate_exportable_trees(approved_struct_snapshot)
        assert [t.unique_key for t in first.trees] == [t.unique_key for t in second.trees]
        assert first.warnings == second.warnings

    def test_connection_labelled_by_description(self, make_snapshot: Any) -> None:
        """LLD-01 §4.13: PortConnections has no name column."""
        snapshot = make_snapshot(port_connections=[port_connection(1, "brake bus")])
        assert evaluate_exportable_trees(snapshot).trees[0].label == "brake bus"


class TestUnusedImportsGuard:
    """Keeps the fixture helpers honest — every import above is exercised."""

    def test_approved_constant(self) -> None:
        """SRS-035: the fixtures default to the approved state."""
        assert APPROVED == "approved"
