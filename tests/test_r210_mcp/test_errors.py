"""Tests for structured MCP response types."""

import pytest

from r210_mcp.errors import McpError, McpResult, McpValidationError


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


class TestMcpValidationError:
    def test_carries_the_structured_payload(self) -> None:
        """SRS-109 — the exception must expose operation, field, reason, key."""
        exc = McpValidationError.of(
            "create_type_definition",
            "name must not be empty",
            field="name",
            affected_key="abc",
        )
        assert exc.error.operation == "create_type_definition"
        assert exc.error.field == "name"
        assert exc.error.reason == "name must not be empty"
        assert exc.error.affected_key == "abc"
        assert exc.error.to_dict()["error"]["reason"] == "name must not be empty"

    def test_str_is_the_reason(self) -> None:
        exc = McpValidationError.of("update_enum_value", "position must be >= 1")
        assert str(exc) == "position must be >= 1"

    def test_is_an_exception(self) -> None:
        with pytest.raises(McpValidationError):
            raise McpValidationError.of("resolve_reference", "not found")
