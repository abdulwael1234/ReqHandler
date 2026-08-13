"""Tool dispatch, the error boundary, and the projection boundary.

This module is where an exception becomes a response and where SRS-015a
projection is applied — once, to every tool, rather than inside each query
handler (DEV-30). Translating `sqlite3.IntegrityError` here is what Phase 2
deferred to: only this layer knows the tool name and the affected key that
SRS-109 requires.

See: LLD-02 §9 (Tool Registration), §11 (Response Projection)
"""

import sqlite3
from collections.abc import Callable
from typing import Any

from ..db.models import PARENT_CHILD_MAP, TABLE_RECORD_MAP
from ..errors import McpError, McpValidationError
from ..projection import project_response
from ._engine import record_to_dict
from .context import ToolContext
from .generation import handle_trigger_generation
from .port_connections import (
    handle_create_port_connection,
    handle_create_port_connection_member,
    handle_query_port_connections,
    handle_update_port_connection,
    handle_update_port_connection_member,
)
from .port_interfaces import (
    handle_create_client_server_operation,
    handle_create_interface_data_element,
    handle_create_operation_argument,
    handle_create_port_interface,
    handle_query_port_interfaces,
    handle_update_client_server_operation,
    handle_update_interface_data_element,
    handle_update_operation_argument,
    handle_update_port_interface,
)
from .port_prototypes import (
    handle_create_port_prototype,
    handle_create_port_prototype_function,
    handle_query_port_prototypes,
    handle_update_port_prototype,
    handle_update_port_prototype_function,
)
from .reference import handle_resolve_reference
from .review_issues import (
    handle_create_review_issue,
    handle_query_review_issues,
    handle_update_review_issue,
)
from .review_status import handle_set_review_status
from .source_requirements import (
    handle_create_source_requirement,
    handle_query_source_requirements,
    handle_update_source_requirement,
)
from .type_definitions import (
    handle_create_enum_value,
    handle_create_struct_element,
    handle_create_type_definition,
    handle_query_type_definitions,
    handle_update_enum_value,
    handle_update_struct_element,
    handle_update_type_definition,
)

ToolHandler = Callable[[ToolContext, dict[str, Any]], dict[str, Any]]

# The 35 tools of LLD-02 §9: 13 create, 13 update, 6 query, 3 cross-cutting.
TOOL_HANDLERS: dict[str, ToolHandler] = {
    "create_source_requirement": handle_create_source_requirement,
    "update_source_requirement": handle_update_source_requirement,
    "query_source_requirements": handle_query_source_requirements,
    "create_type_definition": handle_create_type_definition,
    "update_type_definition": handle_update_type_definition,
    "query_type_definitions": handle_query_type_definitions,
    "create_struct_element": handle_create_struct_element,
    "update_struct_element": handle_update_struct_element,
    "create_enum_value": handle_create_enum_value,
    "update_enum_value": handle_update_enum_value,
    "create_port_interface": handle_create_port_interface,
    "update_port_interface": handle_update_port_interface,
    "query_port_interfaces": handle_query_port_interfaces,
    "create_interface_data_element": handle_create_interface_data_element,
    "update_interface_data_element": handle_update_interface_data_element,
    "create_client_server_operation": handle_create_client_server_operation,
    "update_client_server_operation": handle_update_client_server_operation,
    "create_operation_argument": handle_create_operation_argument,
    "update_operation_argument": handle_update_operation_argument,
    "create_port_prototype": handle_create_port_prototype,
    "update_port_prototype": handle_update_port_prototype,
    "query_port_prototypes": handle_query_port_prototypes,
    "create_port_prototype_function": handle_create_port_prototype_function,
    "update_port_prototype_function": handle_update_port_prototype_function,
    "create_port_connection": handle_create_port_connection,
    "update_port_connection": handle_update_port_connection,
    "query_port_connections": handle_query_port_connections,
    "create_port_connection_member": handle_create_port_connection_member,
    "update_port_connection_member": handle_update_port_connection_member,
    "create_review_issue": handle_create_review_issue,
    "update_review_issue": handle_update_review_issue,
    "query_review_issues": handle_query_review_issues,
    "set_review_status": handle_set_review_status,
    "resolve_reference": handle_resolve_reference,
    "trigger_generation": handle_trigger_generation,
}


def _returns_records_to_extraction(tool_name: str) -> bool:
    """Whether SRS-015a(b) lets this tool return record fields to extraction.

    Clause (b) permits *query results* — the skill needs them for duplicate
    checking and reference resolution. Clause (c) limits every other response
    to returned `unique_key` values and duplicate-warning text, so a create or
    update reflects no content back (LLD-02 §11.2).
    """
    return tool_name.startswith("query_") or tool_name == "resolve_reference"


def dispatch(ctx: ToolContext, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run a tool by name, returning a response rather than raising.

    Projection is applied here so that no handler can omit it (SRS-015a).
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return McpError(
            operation=tool_name, field=None, reason=f"unknown tool: {tool_name}", affected_key=None
        ).to_dict()

    try:
        response = handler(ctx, arguments)
    except McpValidationError as exc:
        response = exc.error.to_dict()
    except sqlite3.IntegrityError as exc:
        response = McpError(
            operation=tool_name,
            field=None,
            reason=f"database constraint violated: {exc}",
            affected_key=arguments.get("unique_key"),
        ).to_dict()

    if ctx.adapter_mode == "extraction":
        return project_response(
            response, records_permitted=_returns_records_to_extraction(tool_name)
        )
    return response


def query_by_table(
    ctx: ToolContext, table: str, filters: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Query a table that has no dedicated query tool (LLD-02 §9, LLD-06)."""
    with ctx.db.read_only() as conn:
        records = ctx.dal.query_table(conn, table, filters or None)
    return [record_to_dict(record) for record in records]


def get_children_for_display(ctx: ToolContext, table: str, record_id: int) -> list[dict[str, Any]]:
    """Load a parent's children for display (LLD-02 §9)."""
    children: list[dict[str, Any]] = []
    with ctx.db.read_only() as conn:
        for relation in PARENT_CHILD_MAP.get(table, []):
            for record in ctx.dal.get_children(
                conn, relation.child_table, relation.fk_column, record_id
            ):
                children.append({"table": relation.child_table, "record": record_to_dict(record)})
    return children


def get_stats(ctx: ToolContext) -> dict[str, Any]:
    """Row and status counts per table (LLD-02 §9).

    Table names come from the model registry, so a table added by a future
    migration is counted without editing a second list.
    """
    tables = sorted(set(TABLE_RECORD_MAP) - {"schema_version"})
    stats: dict[str, Any] = {}
    with ctx.db.read_only() as conn:
        for table in tables:
            stats[table] = {
                "total": ctx.dal.count_rows(conn, table),
                "by_status": ctx.dal.count_by_status(conn, table),
            }
    return stats
