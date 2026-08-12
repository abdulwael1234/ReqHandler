"""Development tests for set_review_status, the cross-cutting tools, the
registry and the server adapter.

See: LLD-02 §7.7-7.9, §9, §11
"""

from typing import Any

import pytest

from r210_mcp.server import R210McpServer
from r210_mcp.tools.context import ToolContext, build_context
from r210_mcp.tools.generation import handle_trigger_generation
from r210_mcp.tools.reference import handle_resolve_reference
from r210_mcp.tools.registry import (
    TOOL_HANDLERS,
    dispatch,
    get_children_for_display,
    get_stats,
    query_by_table,
)
from r210_mcp.tools.review_status import handle_set_review_status
from r210_mcp.tools.source_requirements import handle_create_source_requirement
from r210_mcp.tools.type_definitions import handle_create_type_definition

MISSING_KEY = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


def _key(response: dict[str, Any]) -> str:
    return str(response["result"]["unique_key"])


def _type_definition(ctx: ToolContext, name: str = "Mode") -> str:
    return _key(
        handle_create_type_definition(
            ctx, {"name": name, "kind": "enum", "subtype": {"values": []}}
        )
    )


class TestCallerAuthority:
    def test_rejects_a_caller_that_does_not_match_the_mode(self, initialized_db: str) -> None:
        """SRS-082a — a forged caller parameter is rejected."""
        ctx = build_context(initialized_db, "extraction")
        key = _type_definition(ctx)
        with pytest.raises(Exception) as caught:
            handle_set_review_status(
                ctx, {"unique_key": key, "new_status": "ambiguous", "caller": "review"}
            )
        assert caught.value.error.field == "caller"  # type: ignore[attr-defined]

    def test_extraction_cannot_approve(self, initialized_db: str) -> None:
        """SRS-082a — approval is reserved for manual review."""
        ctx = build_context(initialized_db, "extraction")
        key = _type_definition(ctx)
        with pytest.raises(Exception) as caught:
            handle_set_review_status(
                ctx, {"unique_key": key, "new_status": "approved", "caller": "extraction"}
            )
        assert "SRS-082a" in caught.value.error.reason  # type: ignore[attr-defined]

    def test_review_may_approve(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = _type_definition(ctx)
        response = handle_set_review_status(
            ctx, {"unique_key": key, "new_status": "approved", "caller": "review"}
        )
        assert response["result"]["status"] == "approved"


class TestStatusTargets:
    def test_rejects_a_review_issue(self, initialized_db: str) -> None:
        """SRS-091a — issue status changes through update_review_issue."""
        ctx = build_context(initialized_db, "review")
        with ctx.db.transaction() as conn:
            ctx.dal.insert_review_issue(
                conn, unique_key=MISSING_KEY, issue_type="ambiguous", message="m"
            )
        response = dispatch(
            ctx,
            "set_review_status",
            {"unique_key": MISSING_KEY, "new_status": "approved", "caller": "review"},
        )
        assert "update_review_issue" in response["error"]["reason"]

    def test_rejects_a_structural_subtype(self, initialized_db: str) -> None:
        """SRS-091a — subtype tables have no status column."""
        ctx = build_context(initialized_db, "review")
        with ctx.db.transaction() as conn:
            parent_id = ctx.dal.insert_type_definition(conn, "td", "Speed", "simple_typedef")
            ctx.dal.insert_simple_type_definition(conn, MISSING_KEY, parent_id, "uint8", None)
        response = dispatch(
            ctx,
            "set_review_status",
            {"unique_key": MISSING_KEY, "new_status": "approved", "caller": "review"},
        )
        assert "structural subtype" in response["error"]["reason"]


class TestTransitionAndBlocking:
    def test_rejects_a_forbidden_transition(self, initialized_db: str) -> None:
        """SRS-035b — approved may not go straight to ambiguous."""
        ctx = build_context(initialized_db, "review")
        key = _type_definition(ctx)
        handle_set_review_status(
            ctx, {"unique_key": key, "new_status": "approved", "caller": "review"}
        )
        response = dispatch(
            ctx,
            "set_review_status",
            {"unique_key": key, "new_status": "ambiguous", "caller": "review"},
        )
        assert response["error"]["field"] == "new_status"

    def test_pending_child_blocks_approval(self, initialized_db: str) -> None:
        """SRS-046, SRS-053 — a parent cannot be approved over a pending child."""
        ctx = build_context(initialized_db, "review")
        key = _type_definition(ctx)
        with ctx.db.transaction() as conn:
            parent = ctx.dal.get_type_definition_by_key(conn, key)
            ctx.dal.insert_enum_value(conn, "ev", parent.id, "RED", None, 1)
        response = dispatch(
            ctx,
            "set_review_status",
            {"unique_key": key, "new_status": "approved", "caller": "review"},
        )
        assert "EnumValues" in response["error"]["reason"]

    def test_rejected_child_does_not_block(self, initialized_db: str) -> None:
        """SRS-092a — a rejected child is excluded from the evaluation."""
        ctx = build_context(initialized_db, "review")
        key = _type_definition(ctx)
        with ctx.db.transaction() as conn:
            parent = ctx.dal.get_type_definition_by_key(conn, key)
            child_id = ctx.dal.insert_enum_value(conn, "ev", parent.id, "RED", None, 1)
            ctx.dal.update_status(conn, "EnumValues", child_id, "rejected")
        response = handle_set_review_status(
            ctx, {"unique_key": key, "new_status": "approved", "caller": "review"}
        )
        assert response["result"]["status"] == "approved"

    def test_unresolved_reference_blocks_approval(self, initialized_db: str) -> None:
        """SRS-036a — a record with an unresolved reference is not approvable."""
        ctx = build_context(initialized_db, "review")
        with ctx.db.transaction() as conn:
            parent_id = ctx.dal.insert_type_definition(conn, "td", "Speed", "struct")
            ctx.dal.insert_struct_element(conn, MISSING_KEY, parent_id, "value", None, 1)
        response = dispatch(
            ctx,
            "set_review_status",
            {"unique_key": MISSING_KEY, "new_status": "approved", "caller": "review"},
        )
        assert "element_type_id" in response["error"]["reason"]


class TestNotesAndDemotion:
    def test_stores_a_review_note(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = _key(handle_create_source_requirement(ctx, {"source_reference": "REQ-1"}))
        response = handle_set_review_status(
            ctx,
            {
                "unique_key": key,
                "new_status": "rejected",
                "review_note": "Out of date",
                "caller": "review",
            },
        )
        assert response["result"]["review_note"] == "Out of date"

    def test_ignores_a_note_on_a_table_without_the_column(self, initialized_db: str) -> None:
        """SRS-091a — the note is silently ignored, not an error."""
        ctx = build_context(initialized_db, "review")
        with ctx.db.transaction() as conn:
            parent_id = ctx.dal.insert_type_definition(conn, "td", "Mode", "enum")
            ctx.dal.insert_enum_value(conn, MISSING_KEY, parent_id, "RED", None, 1)
        response = handle_set_review_status(
            ctx,
            {
                "unique_key": MISSING_KEY,
                "new_status": "rejected",
                "review_note": "x",
                "caller": "review",
            },
        )
        assert response["result"]["status"] == "rejected"

    def test_child_leaving_approved_demotes_the_parent(self, initialized_db: str) -> None:
        """SRS-035c — both changes happen in one transaction."""
        ctx = build_context(initialized_db, "review")
        with ctx.db.transaction() as conn:
            parent_id = ctx.dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = ctx.dal.insert_enum_value(conn, MISSING_KEY, parent_id, "RED", None, 1)
            ctx.dal.update_status(conn, "EnumValues", child_id, "approved")
            ctx.dal.update_status(conn, "TypeDefinitions", parent_id, "approved")
        response = handle_set_review_status(
            ctx, {"unique_key": MISSING_KEY, "new_status": "pending_review", "caller": "review"}
        )
        assert response["result"]["demoted"] == ["td"]


class TestResolveReference:
    def test_finds_the_owning_table(self, initialized_db: str) -> None:
        """SRS-087 — references resolve by UUID across every table."""
        ctx = build_context(initialized_db, "review")
        key = _key(handle_create_source_requirement(ctx, {"source_reference": "REQ-1"}))
        response = handle_resolve_reference(ctx, {"unique_key": key})
        assert response["result"]["table"] == "SourceRequirements"
        assert response["result"]["record"]["source_reference"] == "REQ-1"

    def test_unknown_key_is_an_error(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        response = dispatch(ctx, "resolve_reference", {"unique_key": MISSING_KEY})
        assert response["error"]["field"] == "unique_key"


class TestTriggerGeneration:
    @pytest.mark.parametrize("mode", ["r210_only", "report_only", "both"])
    def test_validates_the_mode_then_reports_unavailable(
        self, initialized_db: str, mode: str
    ) -> None:
        """SRS-090 — the tool exists; the generator arrives in a later phase."""
        ctx = build_context(initialized_db, "review")
        response = handle_trigger_generation(ctx, {"mode": mode})
        assert "not yet implemented" in response["error"]["reason"]

    def test_rejects_an_unknown_mode(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        response = dispatch(ctx, "trigger_generation", {"mode": "everything"})
        assert response["error"]["field"] == "mode"


class TestRegistry:
    def test_registers_thirty_five_tools(self) -> None:
        """LLD-02 §9 — 13 create + 13 update + 6 query + 3 cross-cutting."""
        assert len(TOOL_HANDLERS) == 35
        assert sum(1 for name in TOOL_HANDLERS if name.startswith("create_")) == 13
        assert sum(1 for name in TOOL_HANDLERS if name.startswith("update_")) == 13
        assert sum(1 for name in TOOL_HANDLERS if name.startswith("query_")) == 6

    def test_dispatches_by_name(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        response = dispatch(ctx, "create_source_requirement", {"source_reference": "REQ-1"})
        assert response["result"]["source_reference"] == "REQ-1"

    def test_unknown_tool_is_a_structured_error(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        assert dispatch(ctx, "delete_everything", {})["error"]["operation"] == "delete_everything"

    def test_validation_error_becomes_a_response(self, initialized_db: str) -> None:
        """SRS-083, SRS-109 — the boundary serializes, it does not raise."""
        ctx = build_context(initialized_db, "review")
        response = dispatch(ctx, "create_source_requirement", {"source_reference": ""})
        assert response["error"]["field"] == "source_reference"

    def test_constraint_violation_becomes_a_response(self, initialized_db: str) -> None:
        """SRS-109 — the boundary knows the tool name and the affected key."""
        ctx = build_context(initialized_db, "review")
        parent = _type_definition(ctx)
        dispatch(ctx, "create_enum_value", {"enum_type_key": parent, "name": "R", "position": 1})
        response = dispatch(
            ctx, "create_enum_value", {"enum_type_key": parent, "name": "R", "position": 2}
        )
        assert response["error"]["operation"] == "create_enum_value"
        assert "constraint" in response["error"]["reason"]

    def test_extraction_mode_projects_the_response(self, initialized_db: str) -> None:
        """SRS-015a — source_text never leaves in extraction mode."""
        ctx = build_context(initialized_db, "extraction")
        response = dispatch(
            ctx,
            "create_source_requirement",
            {"source_reference": "REQ-1", "source_text": "confidential"},
        )
        assert "source_text" not in response["result"]
        assert response["result"]["source_reference"] == "REQ-1"

    def test_review_mode_returns_full_records(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        response = dispatch(
            ctx,
            "create_source_requirement",
            {"source_reference": "REQ-1", "source_text": "full text"},
        )
        assert response["result"]["source_text"] == "full text"


class TestNonMcpHelpers:
    def test_query_by_table_reaches_a_child_table(self, initialized_db: str) -> None:
        """LLD-06 — the review CLI needs child tables that have no query tool."""
        ctx = build_context(initialized_db, "review")
        handle_create_type_definition(
            ctx,
            {
                "name": "Mode",
                "kind": "enum",
                "subtype": {"values": [{"name": "RED", "position": 1}]},
            },
        )
        assert [row["name"] for row in query_by_table(ctx, "EnumValues", {})] == ["RED"]

    def test_children_for_display(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = _type_definition(ctx)
        with ctx.db.transaction() as conn:
            parent = ctx.dal.get_type_definition_by_key(conn, key)
            ctx.dal.insert_enum_value(conn, "ev", parent.id, "RED", None, 1)
            parent_id = parent.id
        children = get_children_for_display(ctx, "TypeDefinitions", parent_id)
        assert children[0]["table"] == "EnumValues"
        assert children[0]["record"]["name"] == "RED"

    def test_stats_count_by_status(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        dispatch(ctx, "create_source_requirement", {"source_reference": "REQ-1"})
        stats = get_stats(ctx)
        assert stats["SourceRequirements"]["total"] == 1
        assert stats["SourceRequirements"]["by_status"]["pending_review"] == 1
        assert stats["SimpleTypeDefinitions"]["by_status"] == {}


class TestServerAdapter:
    def test_rejects_an_unknown_adapter_mode(self, initialized_db: str) -> None:
        """SRS-082a — authority is bound at construction."""
        with pytest.raises(ValueError):
            R210McpServer(initialized_db, "superuser")

    def test_defaults_to_extraction(self, initialized_db: str) -> None:
        assert R210McpServer(initialized_db).adapter_mode == "extraction"

    def test_lists_thirty_five_tools(self, initialized_db: str) -> None:
        assert len(R210McpServer(initialized_db).tool_names()) == 35

    def test_handle_tool_dispatches_without_the_sdk(self, initialized_db: str) -> None:
        """LLD-06 — the review CLI invokes tools without the MCP protocol."""
        server = R210McpServer(initialized_db, "review")
        response = server.handle_tool("create_source_requirement", {"source_reference": "REQ-1"})
        assert response["result"]["source_reference"] == "REQ-1"

    def test_unknown_tool_returns_an_error(self, initialized_db: str) -> None:
        assert "error" in R210McpServer(initialized_db, "review").handle_tool("nope", {})

    def test_importing_the_module_does_not_require_mcp(self) -> None:
        """The SDK is absent here; only run() may need it."""
        import r210_mcp.server as module

        assert not hasattr(module, "mcp")
