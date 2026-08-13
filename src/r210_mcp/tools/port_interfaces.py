"""Port-interface tools: the interface, its children, and operation arguments.

The two child creates pre-check the parent's `interface_type` before the
engine inserts, because SRS-055 is an application-level rule the schema cannot
express.

See: LLD-02 §7.3 (Port Interface Tools — SRS-052, SRS-055, SRS-059, SRS-086)
"""

from typing import Any

from ..db.models import ARTIFACT_STATUSES
from ..validation.common import validate_not_empty, validate_position
from ..validation.port_interfaces import (
    ARGUMENT_DIRECTIONS,
    INTERFACE_TYPES,
    validate_child_interface_type,
)
from ._engine import (
    CreateSpec,
    FieldSpec,
    QuerySpec,
    RefSpec,
    UpdateSpec,
    choice_of,
    run_create,
    run_query,
    run_update,
)
from .context import ToolContext

_SOURCE_REF = RefSpec("source_requirement_key", "source_requirement_id", "SourceRequirements")

_CREATE = CreateSpec(
    tool="create_port_interface",
    table="PortInterfaces",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("description", "description"),
        FieldSpec("interface_type", "interface_type", True, choice_of(INTERFACE_TYPES)),
    ),
    refs=(_SOURCE_REF,),
    duplicate_name_arg="name",
)

_UPDATE = UpdateSpec(
    tool="update_port_interface",
    table="PortInterfaces",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("description", "description"),
        FieldSpec("interface_type", "interface_type", validator=choice_of(INTERFACE_TYPES)),
    ),
    refs=(_SOURCE_REF,),
)

_QUERY = QuerySpec(
    tool="query_port_interfaces",
    table="PortInterfaces",
    filters=(
        FieldSpec("name", "name"),
        FieldSpec("interface_type", "interface_type", validator=choice_of(INTERFACE_TYPES)),
        FieldSpec("status", "status", validator=choice_of(ARTIFACT_STATUSES)),
    ),
)

_CREATE_DATA_ELEMENT = CreateSpec(
    tool="create_interface_data_element",
    table="InterfaceDataElements",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("position", "position", True, validate_position),
        FieldSpec("description", "description"),
    ),
    refs=(
        RefSpec(
            "port_interface_key", "port_interface_id", "PortInterfaces", required=True, parent=True
        ),
        RefSpec(
            "type_definition_key", "type_definition_id", "TypeDefinitions", may_be_unresolved=True
        ),
    ),
)

_UPDATE_DATA_ELEMENT = UpdateSpec(
    tool="update_interface_data_element",
    table="InterfaceDataElements",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("position", "position", validator=validate_position),
        FieldSpec("description", "description"),
    ),
    refs=(
        RefSpec(
            "type_definition_key", "type_definition_id", "TypeDefinitions", may_be_unresolved=True
        ),
    ),
)

_CREATE_OPERATION = CreateSpec(
    tool="create_client_server_operation",
    table="ClientServerOperations",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("position", "position", True, validate_position),
        FieldSpec("description", "description"),
    ),
    refs=(
        RefSpec(
            "port_interface_key", "port_interface_id", "PortInterfaces", required=True, parent=True
        ),
    ),
)

_UPDATE_OPERATION = UpdateSpec(
    tool="update_client_server_operation",
    table="ClientServerOperations",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("position", "position", validator=validate_position),
        FieldSpec("description", "description"),
    ),
)

_CREATE_ARGUMENT = CreateSpec(
    tool="create_operation_argument",
    table="OperationArguments",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("direction", "direction", True, choice_of(ARGUMENT_DIRECTIONS)),
        FieldSpec("position", "position", True, validate_position),
    ),
    refs=(
        RefSpec(
            "operation_key", "operation_id", "ClientServerOperations", required=True, parent=True
        ),
        RefSpec(
            "type_definition_key", "type_definition_id", "TypeDefinitions", may_be_unresolved=True
        ),
    ),
)

_UPDATE_ARGUMENT = UpdateSpec(
    tool="update_operation_argument",
    table="OperationArguments",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("direction", "direction", validator=choice_of(ARGUMENT_DIRECTIONS)),
        FieldSpec("position", "position", validator=validate_position),
    ),
    refs=(
        RefSpec(
            "type_definition_key", "type_definition_id", "TypeDefinitions", may_be_unresolved=True
        ),
    ),
)


def _check_interface_type(
    ctx: ToolContext, arguments: dict[str, Any], child_table: str, tool: str
) -> None:
    """Pre-check the parent interface_type before inserting (SRS-055)."""
    key = arguments.get("port_interface_key")
    if not isinstance(key, str):
        return
    with ctx.db.read_only() as conn:
        parent = ctx.dal.get_port_interface_by_key(conn, key)
        if parent is None:
            return
        validate_child_interface_type(
            conn, ctx.dal, parent.id, child_table, operation=tool, field="port_interface_key"
        )


def handle_create_port_interface(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a port interface (SRS-052, SRS-086)."""
    return run_create(ctx, _CREATE, arguments)


def handle_update_port_interface(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a port interface."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_port_interfaces(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query port interfaces (SRS-086)."""
    return run_query(ctx, _QUERY, arguments)


def handle_create_interface_data_element(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Create a data element on a sender_receiver interface (SRS-055)."""
    _check_interface_type(
        ctx, arguments, "InterfaceDataElements", "create_interface_data_element"
    )
    return run_create(ctx, _CREATE_DATA_ELEMENT, arguments)


def handle_update_interface_data_element(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update an interface data element."""
    return run_update(ctx, _UPDATE_DATA_ELEMENT, arguments)


def handle_create_client_server_operation(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Create an operation on a client_server interface (SRS-055)."""
    _check_interface_type(
        ctx, arguments, "ClientServerOperations", "create_client_server_operation"
    )
    return run_create(ctx, _CREATE_OPERATION, arguments)


def handle_update_client_server_operation(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update a client-server operation."""
    return run_update(ctx, _UPDATE_OPERATION, arguments)


def handle_create_operation_argument(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Create an operation argument (SRS-059)."""
    return run_create(ctx, _CREATE_ARGUMENT, arguments)


def handle_update_operation_argument(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update an operation argument."""
    return run_update(ctx, _UPDATE_ARGUMENT, arguments)
