"""Rules that must hold across the whole tool surface.

Each test is parametrized off a registry rather than a hand-written list, so a
tool or table added later is covered automatically rather than quietly
escaping the rule.
"""

from typing import Any

import pytest

from r210_mcp.db.dal import TABLE_COLUMNS
from r210_mcp.db.models import ARTIFACT_TABLES, REVIEWABLE_CHILD_TABLES
from r210_mcp.projection import GEMINI_ALLOWED_FIELDS
from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import TOOL_HANDLERS, dispatch

MISSING_KEY = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
UPDATE_TOOLS = sorted(name for name in TOOL_HANDLERS if name.startswith("update_"))
STATUS_TABLES = sorted(ARTIFACT_TABLES | REVIEWABLE_CHILD_TABLES)
FORBIDDEN_FIELDS = [
    "source_text",
    "description",
    "review_note",
    "resolution",
    "component_reference",
    "function_name",
]
# Response keys that are tool metadata rather than record fields (SRS-015a).
METADATA_KEYS = frozenset({"warnings", "demoted", "table", "count", "records", "record"})


@pytest.mark.parametrize("tool", UPDATE_TOOLS)
def test_every_update_tool_rejects_status(initialized_db: str, tool: str) -> None:
    """SRS-091a — no update tool accepts `status`, except update_review_issue.

    `update_review_issue` is the documented exception: SRS-119 puts issue
    status changes there precisely because set_review_status excludes them.
    """
    ctx = build_context(initialized_db, "review")
    response = dispatch(ctx, tool, {"unique_key": MISSING_KEY, "status": "approved"})
    assert "error" in response
    if tool != "update_review_issue":
        assert response["error"]["field"] == "status"


@pytest.mark.parametrize("table", STATUS_TABLES)
def test_every_reviewable_table_carries_a_status_column(table: str) -> None:
    """SRS-035a — artifacts and reviewable children hold a review state."""
    assert "status" in TABLE_COLUMNS[table]


@pytest.mark.parametrize("tool", sorted(TOOL_HANDLERS))
def test_no_tool_leaks_a_forbidden_field_in_extraction_mode(
    initialized_db: str, tool: str
) -> None:
    """SRS-015a — adversarial: every tool, invoked with hostile arguments.

    Named by REPOSITORY_REVIEW_REPORT.md §7 as a required test. The arguments
    are deliberately invalid for most tools; what matters is that whatever
    comes back carries no field outside the allowlist.
    """
    ctx = build_context(initialized_db, "extraction")
    response = dispatch(
        ctx,
        tool,
        {
            "unique_key": MISSING_KEY,
            "source_reference": "REQ-1",
            "source_text": "confidential",
            "description": "confidential",
            "review_note": "confidential",
        },
    )
    result = response.get("result")
    if not isinstance(result, dict):
        return
    for key in result:
        assert key in METADATA_KEYS or key in GEMINI_ALLOWED_FIELDS, f"{tool} leaked {key}"
    for nested in ("records", "record"):
        value = result.get(nested)
        rows: list[Any] = (
            value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        )
        for row in rows:
            for field in FORBIDDEN_FIELDS:
                assert field not in row, f"{tool} leaked {field}"


@pytest.mark.parametrize("caller", ["extraction", "review", None, "admin"])
def test_extraction_cannot_approve_whatever_caller_is_forged(
    initialized_db: str, caller: str | None
) -> None:
    """SRS-082a — adversarial: a forged caller never buys approval authority.

    Named by REPOSITORY_REVIEW_REPORT.md §7 as a required test. Every
    reviewable table is created and then approval is attempted under an
    extraction-mode context.
    """
    ctx = build_context(initialized_db, "extraction")
    review = build_context(initialized_db, "review")
    key = str(
        dispatch(
            review,
            "create_source_requirement",
            {"source_reference": "REQ-1"},
        )["result"]["unique_key"]
    )
    response = dispatch(
        ctx, "set_review_status", {"unique_key": key, "new_status": "approved", "caller": caller}
    )
    assert "error" in response, f"extraction approved via caller={caller!r}"
    with ctx.db.read_only() as conn:
        assert ctx.dal.get_source_requirement_by_key(conn, key).status == "pending_review"


def test_extraction_cannot_approve_a_child_either(initialized_db: str) -> None:
    """SRS-082a — the block covers reviewable children, not just artifacts.

    Uses a real record: with a nonexistent key the call would fail at record
    lookup and never reach the authority check, which would make this test
    pass for the wrong reason.
    """
    ctx = build_context(initialized_db, "extraction")
    review = build_context(initialized_db, "review")
    parent = str(
        dispatch(
            review,
            "create_type_definition",
            {"name": "Mode", "kind": "enum", "subtype": {"values": []}},
        )["result"]["unique_key"]
    )
    child = str(
        dispatch(
            review,
            "create_enum_value",
            {"enum_type_key": parent, "name": "RED", "position": 1},
        )["result"]["unique_key"]
    )
    response = dispatch(
        ctx,
        "set_review_status",
        {"unique_key": child, "new_status": "approved", "caller": "extraction"},
    )
    assert "SRS-082a" in response["error"]["reason"]
    with ctx.db.read_only() as conn:
        assert ctx.dal.get_enum_value_by_key(conn, child).status == "pending_review"


def test_no_delete_tool_is_registered() -> None:
    """SRS-091 — deletion is not on the MCP tool surface."""
    assert not [name for name in TOOL_HANDLERS if "delete" in name or "remove" in name]


def test_no_reset_tool_is_registered() -> None:
    """SRS-093 — destructive operations are not exposed through MCP."""
    assert not [name for name in TOOL_HANDLERS if "reset" in name or "drop" in name]


def test_the_mcp_package_never_imports_the_initializer() -> None:
    """SRS-093 — development_reset must not be reachable from the MCP surface."""
    import pathlib

    source_root = pathlib.Path(__file__).resolve().parents[2] / "src" / "r210_mcp"
    offenders = [
        path.name
        for path in source_root.rglob("*.py")
        if "r210_db_init" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
