"""Tests for structured MCP response types."""

import pytest

from r210_mcp.errors import McpError, McpResult


def test_mcp_error_requires_a_reason() -> None:
    """SRS-109 requires every error to report its reason for failure."""
    with pytest.raises(TypeError):
        McpError(operation="create_type_definition")  # type: ignore[call-arg]


def test_mcp_error_serializes_every_required_field() -> None:
    """SRS-109 — errors expose operation, field, reason, and affected identity."""
    error = McpError(
        operation="create_type_definition",
        field="kind",
        reason="unsupported kind",
        affected_key="type-1",
    )

    assert error.to_dict() == {
        "error": {
            "operation": "create_type_definition",
            "field": "kind",
            "reason": "unsupported kind",
            "affected_key": "type-1",
        }
    }


def test_mcp_result_flattens_data_and_includes_non_empty_warnings() -> None:
    result = McpResult(
        unique_key="type-1",
        data={"id": 7, "status": "pending_review"},
        warnings=["possible duplicate"],
    )

    assert result.to_dict() == {
        "result": {
            "unique_key": "type-1",
            "id": 7,
            "status": "pending_review",
            "warnings": ["possible duplicate"],
        }
    }


def test_mcp_result_omits_empty_warnings_and_uses_fresh_defaults() -> None:
    first = McpResult(unique_key="first")
    second = McpResult(unique_key="second")
    first.data["id"] = 1
    first.warnings.append("warning")

    assert second.to_dict() == {"result": {"unique_key": "second"}}
