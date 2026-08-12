"""Tests for structured MCP response types."""

import pytest

from r210_mcp.errors import McpError


def test_mcp_error_requires_a_reason() -> None:
    """SRS-109 requires every error to report its reason for failure."""
    with pytest.raises(TypeError):
        McpError(operation="create_type_definition")  # type: ignore[call-arg]
