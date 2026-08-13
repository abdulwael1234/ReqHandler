"""Port-prototype tools: the prototype and its function references.

`port_interface_key` is optional: SRS-036 stores a missing relationship as
NULL rather than 0. It is not one of the four SRS-036a columns, so leaving it
unresolved does not create a ReviewIssue.

See: LLD-02 §7.4 (Port Prototype Tools — SRS-061, SRS-063, SRS-086)
"""

from typing import Any

from ..db.models import ARTIFACT_STATUSES
from ..validation.common import validate_not_empty
from ..validation.port_interfaces import PORT_DIRECTIONS, RELATIONSHIP_TYPES
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
_INTERFACE_REF = RefSpec("port_interface_key", "port_interface_id", "PortInterfaces")

_CREATE = CreateSpec(
    tool="create_port_prototype",
    table="PortPrototypes",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("description", "description"),
        FieldSpec("direction", "direction", True, choice_of(PORT_DIRECTIONS)),
        FieldSpec("component_reference", "component_reference", True, validate_not_empty),
    ),
    refs=(_SOURCE_REF, _INTERFACE_REF),
    duplicate_name_arg="name",
)

_UPDATE = UpdateSpec(
    tool="update_port_prototype",
    table="PortPrototypes",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("description", "description"),
        FieldSpec("direction", "direction", validator=choice_of(PORT_DIRECTIONS)),
        FieldSpec("component_reference", "component_reference", validator=validate_not_empty),
    ),
    refs=(_SOURCE_REF, _INTERFACE_REF),
)

_QUERY = QuerySpec(
    tool="query_port_prototypes",
    table="PortPrototypes",
    filters=(
        FieldSpec("name", "name"),
        FieldSpec("direction", "direction", validator=choice_of(PORT_DIRECTIONS)),
        FieldSpec("component_reference", "component_reference"),
        FieldSpec("status", "status", validator=choice_of(ARTIFACT_STATUSES)),
    ),
)

_CREATE_FUNCTION = CreateSpec(
    tool="create_port_prototype_function",
    table="PortPrototypeFunctions",
    fields=(
        FieldSpec("function_name", "function_name", True, validate_not_empty),
        FieldSpec("relationship_type", "relationship_type", True, choice_of(RELATIONSHIP_TYPES)),
    ),
    refs=(
        RefSpec(
            "port_prototype_key",
            "port_prototype_id",
            "PortPrototypes",
            required=True,
            parent=True,
        ),
    ),
)

_UPDATE_FUNCTION = UpdateSpec(
    tool="update_port_prototype_function",
    table="PortPrototypeFunctions",
    fields=(
        FieldSpec("function_name", "function_name", validator=validate_not_empty),
        FieldSpec(
            "relationship_type", "relationship_type", validator=choice_of(RELATIONSHIP_TYPES)
        ),
    ),
)


def handle_create_port_prototype(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a port prototype (SRS-061, SRS-086)."""
    return run_create(ctx, _CREATE, arguments)


def handle_update_port_prototype(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a port prototype."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_port_prototypes(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query port prototypes (SRS-086)."""
    return run_query(ctx, _QUERY, arguments)


def handle_create_port_prototype_function(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Create a function reference on a prototype (SRS-063)."""
    return run_create(ctx, _CREATE_FUNCTION, arguments)


def handle_update_port_prototype_function(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update a prototype function reference."""
    return run_update(ctx, _UPDATE_FUNCTION, arguments)
