"""Direct invocation of the MCP tool handlers, without MCP transport.

LLD-06 §5.1 imports `R210McpServer`. That module imports the `mcp` SDK, which
would both fail in an environment without the SDK and violate LLD-06 §7's own
network-isolation rule — the document contradicts itself, and §7 carries the
requirement (SRS-123). Phase 3 made the handlers plain functions over a
`ToolContext` (DEV-26) precisely so this layer could exist, so the bridge
targets `tools/registry` instead (DEV-40). Every guarantee §5.2 asks for is
preserved: identical validation, identical transactions, identical errors,
approval permitted by `adapter_mode` (SRS-082a), full unprojected records.

See: LLD-06 §5 (Tool Invocation Layer)
"""

from typing import Any

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.tools._engine import record_to_dict
from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import (
    dispatch,
    get_children_for_display,
    get_stats,
    query_by_table,
)

# Tables reachable through a dedicated query tool (LLD-06 §5.2). Anything else
# goes through `query_by_table`, which is why child tables need no entry here.
QUERY_TOOLS: dict[str, str] = {
    "SourceRequirements": "query_source_requirements",
    "TypeDefinitions": "query_type_definitions",
    "PortInterfaces": "query_port_interfaces",
    "PortPrototypes": "query_port_prototypes",
    "PortConnections": "query_port_connections",
    "ReviewIssues": "query_review_issues",
}


class ReviewToolBridge:
    """Invoke tool handlers directly, with review authority (SRS-082a, SRS-123).

    Provides no create operations — extraction's job, not the reviewer's — and
    no delete operations, which are never exposed (SRS-091, SRS-093).
    """

    def __init__(self, db_path: str) -> None:
        self._ctx = build_context(db_path, adapter_mode="review")
        self._db = DatabaseConnection(db_path)
        self._dal = DataAccessLayer()

    def set_review_status(
        self,
        unique_key: str,
        new_status: str,
        table_hint: str | None = None,
        review_note: str | None = None,
    ) -> dict[str, Any]:
        """Set an artifact's review state (SRS-089).

        `table_hint` is optional: `resolve_unique_key` already finds the owning
        table, and requiring the caller to name it invites a mismatch (DEV-35).
        """
        args: dict[str, Any] = {
            "unique_key": unique_key,
            "new_status": new_status,
            "caller": "review",
        }
        if table_hint is not None:
            args["table_hint"] = table_hint
        if review_note is not None:
            args["review_note"] = review_note
        return dispatch(self._ctx, "set_review_status", args)

    def update_review_issue(
        self,
        unique_key: str,
        status: str | None = None,
        resolution: str | None = None,
    ) -> dict[str, Any]:
        """Change an issue's lifecycle state (SRS-119)."""
        args: dict[str, Any] = {"unique_key": unique_key}
        if status is not None:
            args["status"] = status
        if resolution is not None:
            args["resolution"] = resolution
        return dispatch(self._ctx, "update_review_issue", args)

    def query(self, table: str, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        """List records, preferring the dedicated query tool when one exists.

        Returns the full response envelope rather than a bare list, so that a
        rejected filter surfaces as an error instead of an empty result.
        """
        tool = QUERY_TOOLS.get(table)
        if tool is None:
            records = query_by_table(self._ctx, table, filters)
            return {"result": {"table": table, "count": len(records), "records": records}}
        return dispatch(self._ctx, tool, filters or {})

    def search(self, table: str, pattern: str) -> dict[str, Any]:
        """Case-insensitive name search (SRS-118, DEV-43)."""
        with self._db.read_only() as conn:
            records = self._dal.search_by_name_pattern(conn, table, pattern)
        payload = [record_to_dict(record) for record in records]
        for row in payload:
            row.pop("id", None)
        return {"result": {"table": table, "count": len(payload), "records": payload}}

    def show(self, unique_key: str) -> dict[str, Any]:
        """Resolve a key to its table and record, with children attached.

        `resolve_reference` strips `id` from its payload, so the primary key is
        re-resolved through the DAL to load children.
        """
        response = dispatch(self._ctx, "resolve_reference", {"unique_key": unique_key})
        if "error" in response:
            return response

        with self._db.read_only() as conn:
            found = self._dal.resolve_unique_key(conn, unique_key)
        response["result"]["children"] = (
            get_children_for_display(self._ctx, found[0], int(found[1].id))
            if found is not None
            else []
        )
        return response

    def stats(self) -> dict[str, Any]:
        """Row and status counts per table (SRS-118)."""
        return get_stats(self._ctx)

    def generate(self, mode: str, output_dir: str | None = None) -> dict[str, Any]:
        """Trigger generation (SRS-090)."""
        args: dict[str, Any] = {"mode": mode}
        if output_dir is not None:
            args["output_dir"] = output_dir
        return dispatch(self._ctx, "trigger_generation", args)
