"""Fixtures for the generator tests.

Two styles, deliberately:

* `make_snapshot` builds a `DatabaseSnapshot` directly from record dataclasses.
  Tree evaluation and FK validation are pure functions over a snapshot, so
  their tests need no database and can construct states — a dangling foreign
  key, a rejected grandchild — that the MCP tools would refuse to create.
* `populated_db` drives the real tool surface, so the loader is tested against
  a real migrated database, as the repository's testing conventions require.
"""

from typing import Any

import pytest

from r210_generator.models import DatabaseSnapshot
from r210_mcp.db.models import (
    ArrayTypeDefinitionRecord,
    ClientServerOperationRecord,
    EnumValueRecord,
    InterfaceDataElementRecord,
    OperationArgumentRecord,
    PortConnectionMemberRecord,
    PortConnectionRecord,
    PortInterfaceRecord,
    PortPrototypeFunctionRecord,
    PortPrototypeRecord,
    ReviewIssueRecord,
    SimpleTypeDefinitionRecord,
    SourceRequirementRecord,
    StructElementRecord,
    TypeDefinitionRecord,
)
from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import dispatch

APPROVED = "approved"
PENDING = "pending_review"
REJECTED = "rejected"


def type_definition(
    record_id: int, name: str, kind: str = "struct", status: str = APPROVED
) -> TypeDefinitionRecord:
    """A TypeDefinitions row with a key derived from its id."""
    return TypeDefinitionRecord(
        id=record_id,
        unique_key=f"td-{record_id}",
        name=name,
        kind=kind,
        description=None,
        source_requirement_id=None,
        status=status,
        review_note=None,
    )


def struct_element(
    record_id: int,
    struct_type_id: int,
    name: str,
    position: int,
    element_type_id: int | None = 1,
    status: str = APPROVED,
) -> StructElementRecord:
    """A StructElements row, resolved to type 1 unless told otherwise."""
    return StructElementRecord(
        id=record_id,
        unique_key=f"se-{record_id}",
        struct_type_id=struct_type_id,
        name=name,
        element_type_id=element_type_id,
        position=position,
        description=None,
        status=status,
    )


def enum_value(
    record_id: int, enum_type_id: int, name: str, position: int, status: str = APPROVED
) -> EnumValueRecord:
    """An EnumValues row."""
    return EnumValueRecord(
        id=record_id,
        unique_key=f"ev-{record_id}",
        enum_type_id=enum_type_id,
        name=name,
        value=None,
        position=position,
        description=None,
        status=status,
    )


def port_interface(
    record_id: int,
    name: str,
    interface_type: str = "client_server",
    status: str = APPROVED,
) -> PortInterfaceRecord:
    """A PortInterfaces row."""
    return PortInterfaceRecord(
        id=record_id,
        unique_key=f"pi-{record_id}",
        name=name,
        description=None,
        source_requirement_id=None,
        interface_type=interface_type,
        status=status,
        review_note=None,
    )


def data_element(
    record_id: int,
    port_interface_id: int,
    name: str,
    position: int,
    type_definition_id: int | None = 1,
    status: str = APPROVED,
) -> InterfaceDataElementRecord:
    """An InterfaceDataElements row."""
    return InterfaceDataElementRecord(
        id=record_id,
        unique_key=f"ide-{record_id}",
        port_interface_id=port_interface_id,
        name=name,
        type_definition_id=type_definition_id,
        position=position,
        description=None,
        status=status,
    )


def operation(
    record_id: int, port_interface_id: int, name: str, position: int, status: str = APPROVED
) -> ClientServerOperationRecord:
    """A ClientServerOperations row."""
    return ClientServerOperationRecord(
        id=record_id,
        unique_key=f"cso-{record_id}",
        port_interface_id=port_interface_id,
        name=name,
        position=position,
        description=None,
        status=status,
    )


def argument(
    record_id: int,
    operation_id: int,
    name: str,
    position: int,
    type_definition_id: int | None = 1,
    status: str = APPROVED,
) -> OperationArgumentRecord:
    """An OperationArguments row."""
    return OperationArgumentRecord(
        id=record_id,
        unique_key=f"oa-{record_id}",
        operation_id=operation_id,
        name=name,
        type_definition_id=type_definition_id,
        direction="input",
        position=position,
        status=status,
    )


def port_prototype(
    record_id: int,
    name: str,
    port_interface_id: int | None = 1,
    status: str = APPROVED,
) -> PortPrototypeRecord:
    """A PortPrototypes row."""
    return PortPrototypeRecord(
        id=record_id,
        unique_key=f"pp-{record_id}",
        name=name,
        description=None,
        source_requirement_id=None,
        port_interface_id=port_interface_id,
        direction="provider",
        component_reference="Comp",
        status=status,
        review_note=None,
    )


def port_connection(
    record_id: int, description: str, status: str = APPROVED
) -> PortConnectionRecord:
    """A PortConnections row. Labelled by description: it has no name column."""
    return PortConnectionRecord(
        id=record_id,
        unique_key=f"pc-{record_id}",
        description=description,
        source_requirement_id=None,
        status=status,
        review_note=None,
    )


def connection_member(
    record_id: int,
    port_connection_id: int,
    port_prototype_id: int,
    position: int,
    status: str = APPROVED,
) -> PortConnectionMemberRecord:
    """A PortConnectionMembers row."""
    return PortConnectionMemberRecord(
        id=record_id,
        unique_key=f"pcm-{record_id}",
        port_connection_id=port_connection_id,
        port_prototype_id=port_prototype_id,
        position=position,
        status=status,
    )


def review_issue(
    record_id: int,
    issue_type: str = "incomplete",
    status: str = "pending",
    message: str = "information missing",
    resolution: str | None = None,
) -> ReviewIssueRecord:
    """A ReviewIssues row."""
    return ReviewIssueRecord(
        id=record_id,
        unique_key=f"ri-{record_id}",
        source_requirement_id=None,
        artifact_type=None,
        artifact_unique_key=None,
        issue_type=issue_type,
        message=message,
        status=status,
        resolution=resolution,
    )


def base_type(record_id: int = 1, name: str = "Float32") -> TypeDefinitionRecord:
    """The simple type every resolved reference in these fixtures points at."""
    return type_definition(record_id, name, kind="simple_typedef")


def simple_detail(record_id: int, type_definition_id: int) -> SimpleTypeDefinitionRecord:
    """A SimpleTypeDefinitions structural row."""
    return SimpleTypeDefinitionRecord(
        id=record_id,
        unique_key=f"std-{record_id}",
        type_definition_id=type_definition_id,
        base_type="float",
        size=None,
    )


def array_detail(
    record_id: int, type_definition_id: int, element_type_id: int | None = 1
) -> ArrayTypeDefinitionRecord:
    """An ArrayTypeDefinitions structural row."""
    return ArrayTypeDefinitionRecord(
        id=record_id,
        unique_key=f"atd-{record_id}",
        type_definition_id=type_definition_id,
        element_type_id=element_type_id,
        array_size=4,
    )


def function(
    record_id: int,
    port_prototype_id: int,
    name: str = "ReadTemp",
    relationship_type: str = "access_point",
    status: str = APPROVED,
) -> PortPrototypeFunctionRecord:
    """A PortPrototypeFunctions row."""
    return PortPrototypeFunctionRecord(
        id=record_id,
        unique_key=f"ppf-{record_id}",
        port_prototype_id=port_prototype_id,
        function_name=name,
        relationship_type=relationship_type,
        status=status,
    )


def source_requirement(record_id: int, reference: str = "REQ-001") -> SourceRequirementRecord:
    """A SourceRequirements row."""
    return SourceRequirementRecord(
        id=record_id,
        unique_key=f"sr-{record_id}",
        source_reference=reference,
        source_text="synthetic requirement text",
        status=APPROVED,
        review_note=None,
    )


@pytest.fixture
def make_snapshot() -> Any:
    """Build a DatabaseSnapshot from whichever record lists a test needs."""

    def _make(**kwargs: Any) -> DatabaseSnapshot:
        return DatabaseSnapshot(**{key: tuple(value) for key, value in kwargs.items()})

    return _make


@pytest.fixture
def approved_struct_snapshot(make_snapshot: Any) -> DatabaseSnapshot:
    """A fully approved struct tree: base type, struct, two elements."""
    return make_snapshot(
        type_definitions=[base_type(1), type_definition(2, "SensorData")],
        simple_type_definitions=[simple_detail(1, 1)],
        struct_elements=[
            struct_element(1, 2, "temperature", 1),
            struct_element(2, 2, "humidity", 2),
        ],
    )


@pytest.fixture
def populated_db(initialized_db: str) -> str:
    """A real database with an approved struct tree and one pending issue."""
    ctx = build_context(initialized_db, adapter_mode="extraction")
    review = build_context(initialized_db, adapter_mode="review")

    base = str(
        dispatch(
            ctx,
            "create_type_definition",
            {"name": "Float32", "kind": "simple_typedef", "subtype": {"base_type": "float"}},
        )["result"]["unique_key"]
    )
    struct = str(
        dispatch(
            ctx,
            "create_type_definition",
            {"name": "SensorData", "kind": "struct", "subtype": {"elements": []}},
        )["result"]["unique_key"]
    )
    element = str(
        dispatch(
            ctx,
            "create_struct_element",
            {
                "struct_type_key": struct,
                "name": "temperature",
                "position": 1,
                "element_type_key": base,
            },
        )["result"]["unique_key"]
    )
    dispatch(ctx, "create_review_issue", {"issue_type": "incomplete", "message": "units missing"})

    for key in (base, element, struct):
        dispatch(
            review,
            "set_review_status",
            {"unique_key": key, "new_status": APPROVED, "caller": "review"},
        )
    return initialized_db
