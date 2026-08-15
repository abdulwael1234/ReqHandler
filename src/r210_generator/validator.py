"""Pre-generation validation: exportable trees, then foreign-key completeness.

Both entry points are pure functions over a `DatabaseSnapshot` — no database,
no I/O. That is deliberate: every rule here is exhaustively testable against a
constructed snapshot, and Phase 5's rendering reuses them unchanged.

See: LLD-04 §4 (Parent-Child Tree Evaluation), §5 (Foreign Key Validation)
"""

from typing import Any

from .models import (
    ArtifactTree,
    DatabaseSnapshot,
    ExportableSet,
    ValidatedSet,
    ValidationError,
    ValidationWarning,
)

APPROVED = "approved"
REJECTED = "rejected"


def _label(record: Any) -> str:
    """`name` for most tables; `description` for PortConnections (LLD-01 §4.13)."""
    return str(getattr(record, "name", None) or getattr(record, "description", None) or "")


def _children_of(
    snapshot: DatabaseSnapshot, table: str, record: Any
) -> list[tuple[str, Any]]:
    """The reviewable children of one parent, as (child_table, record) pairs.

    `SimpleTypeDefinitions` and `ArrayTypeDefinitions` are structural subtypes
    with no `status` column (SRS-035a), so they are not children for the
    purposes of tree evaluation — a simple or array type has none.
    """
    if table == "TypeDefinitions":
        if record.kind == "struct":
            return [("StructElements", c) for c in snapshot.struct_elements
                    if c.struct_type_id == record.id]
        if record.kind == "enum":
            return [("EnumValues", c) for c in snapshot.enum_values
                    if c.enum_type_id == record.id]
        return []
    if table == "PortInterfaces":
        if record.interface_type == "sender_receiver":
            return [("InterfaceDataElements", c) for c in snapshot.interface_data_elements
                    if c.port_interface_id == record.id]
        return [("ClientServerOperations", c) for c in snapshot.client_server_operations
                if c.port_interface_id == record.id]
    if table == "ClientServerOperations":
        return [("OperationArguments", c) for c in snapshot.operation_arguments
                if c.operation_id == record.id]
    if table == "PortPrototypes":
        return [("PortPrototypeFunctions", c) for c in snapshot.port_prototype_functions
                if c.port_prototype_id == record.id]
    if table == "PortConnections":
        return [("PortConnectionMembers", c) for c in snapshot.port_connection_members
                if c.port_connection_id == record.id]
    return []


def _blocking(snapshot: DatabaseSnapshot, table: str, record: Any) -> list[str]:
    """Children that stop this record being exportable, described for the report.

    Recursive: LLD-04 §4.3 requires a client-server interface to fail when an
    argument of one of its operations is not approved, not merely when an
    operation is. A rejected child is excluded from evaluation entirely
    (SRS-092a) and so blocks nothing.
    """
    blocking: list[str] = []
    for child_table, child in _children_of(snapshot, table, record):
        if child.status == REJECTED:
            continue
        if child.status != APPROVED:
            blocking.append(f"{child_table} {_label(child)} is {child.status}")
            continue
        blocking.extend(_blocking(snapshot, child_table, child))
    return blocking


def evaluate_exportable_trees(snapshot: DatabaseSnapshot) -> ExportableSet:
    """Partition approved parents into exportable trees and warnings.

    A tree is exportable when the parent is approved and every non-rejected
    descendant is approved (SRS-104a, SRS-092a).
    """
    exportable = ExportableSet()

    parents: list[tuple[str, Any]] = []
    parents.extend(("TypeDefinitions", r) for r in snapshot.type_definitions)
    parents.extend(("PortInterfaces", r) for r in snapshot.port_interfaces)
    parents.extend(("PortPrototypes", r) for r in snapshot.port_prototypes)
    parents.extend(("PortConnections", r) for r in snapshot.port_connections)

    for table, record in parents:
        if record.status != APPROVED:
            continue
        children = _children_of(snapshot, table, record)
        rejected = tuple((t, c) for t, c in children if c.status == REJECTED)
        active = tuple((t, c) for t, c in children if c.status != REJECTED)

        blocking = _blocking(snapshot, table, record)
        if blocking:
            exportable.warnings.append(
                ValidationWarning(
                    table=table,
                    unique_key=str(record.unique_key),
                    label=_label(record),
                    reason="Not all non-rejected children are approved",
                    blocking_children=tuple(blocking),
                )
            )
            continue

        exportable.trees.append(
            ArtifactTree(
                table=table,
                record=record,
                active_children=active,
                excluded_children=rejected,
            )
        )
    return exportable


def _fk_problems(snapshot: DatabaseSnapshot, tree: ArtifactTree) -> list[str]:
    """Unresolved or dangling mandatory references in one tree (LLD-04 §5.1).

    The four SRS-036a references are nullable during extraction and mandatory
    here; `PortPrototypes.port_interface_id` and
    `PortConnectionMembers.port_prototype_id` are structurally required.
    """
    problems: list[str] = []
    types = snapshot.type_definitions_by_id()
    prototypes = snapshot.port_prototypes_by_id()
    interfaces = snapshot.port_interfaces_by_id()

    def check(value: int | None, targets: dict[int, Any], what: str) -> None:
        if value is None:
            problems.append(f"{what} is unresolved")
        elif value not in targets:
            problems.append(f"{what} references a record that does not exist")

    if tree.table == "TypeDefinitions":
        if tree.record.kind == "array":
            for detail in snapshot.array_type_definitions:
                if detail.type_definition_id == tree.record.id:
                    check(detail.element_type_id, types, "ArrayTypeDefinitions.element_type_id")
    if tree.table == "PortPrototypes":
        check(tree.record.port_interface_id, interfaces, "PortPrototypes.port_interface_id")

    for child_table, child in tree.active_children:
        if child_table == "StructElements":
            check(child.element_type_id, types, f"StructElements[{_label(child)}].element_type_id")
        elif child_table == "InterfaceDataElements":
            check(
                child.type_definition_id,
                types,
                f"InterfaceDataElements[{_label(child)}].type_definition_id",
            )
        elif child_table == "PortConnectionMembers":
            check(
                child.port_prototype_id,
                prototypes,
                f"PortConnectionMembers[position {child.position}].port_prototype_id",
            )
        elif child_table == "ClientServerOperations":
            for argument in snapshot.operation_arguments:
                if argument.operation_id == child.id and argument.status != REJECTED:
                    check(
                        argument.type_definition_id,
                        types,
                        f"OperationArguments[{_label(argument)}].type_definition_id",
                    )
    return problems


def validate_fk_completeness(
    snapshot: DatabaseSnapshot, exportable: ExportableSet
) -> ValidatedSet:
    """Exclude and report trees whose mandatory references are not resolved."""
    validated = ValidatedSet()
    for tree in exportable.trees:
        problems = _fk_problems(snapshot, tree)
        if problems:
            validated.errors.append(
                ValidationError(
                    table=tree.table,
                    unique_key=tree.unique_key,
                    label=tree.label,
                    reason="; ".join(problems),
                )
            )
        else:
            validated.trees.append(tree)
    return validated
