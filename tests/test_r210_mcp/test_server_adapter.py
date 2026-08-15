"""The stdio MCP adapter (LLD-02 §9).

`run()` opens a transport and is exercised by the out-of-band stdio check
recorded in docs/PHASE4_IMPLEMENTED_REQUIREMENTS.md. `build_server()` is the
wiring underneath it, and is tested here directly.

Skipped when the `mcp` SDK is absent: the repository's other 800-odd tests must
keep running without it (DEV-26), which is the whole reason handlers are
functions over a ToolContext rather than server methods.
"""

import json
from typing import Any

import pytest

from r210_mcp.server import R210McpServer
from r210_mcp.tools.registry import TOOL_HANDLERS

mcp = pytest.importorskip("mcp", reason="the mcp SDK is an optional runtime dependency")

anyio = pytest.importorskip("anyio")


def _run(coroutine: Any) -> Any:
    return anyio.run(lambda: coroutine)


class TestBuildServer:
    """LLD-02 §9: all 35 tools are advertised over the protocol."""

    def test_lists_every_tool(self, initialized_db: str) -> None:
        """SRS-086: a client can discover the whole tool surface."""
        server = R210McpServer(initialized_db).build_server()
        handler = server.get_request_handler("tools/list")
        result = _run(handler.handler(None, None))
        assert {tool.name for tool in result.tools} == set(TOOL_HANDLERS)

    def test_every_tool_has_a_description(self, initialized_db: str) -> None:
        """SRS-086: an advertised tool without a description is unusable."""
        server = R210McpServer(initialized_db).build_server()
        handler = server.get_request_handler("tools/list")
        result = _run(handler.handler(None, None))
        assert all(tool.description for tool in result.tools)


class TestCallTool:
    """LLD-02 §9: a protocol call reaches the same handler as a direct call."""

    @staticmethod
    def _call(db_path: str, name: str, arguments: dict[str, Any], mode: str = "extraction") -> Any:
        import mcp.types as types

        server = R210McpServer(db_path, mode).build_server()
        handler = server.get_request_handler("tools/call")
        params = types.CallToolRequestParams(name=name, arguments=arguments)
        return _run(handler.handler(None, params))

    def test_create_returns_the_new_key(self, initialized_db: str) -> None:
        """SRS-086: a create over the protocol produces a record."""
        result = self._call(
            initialized_db,
            "create_type_definition",
            {"name": "Probe", "kind": "simple_typedef", "subtype": {"base_type": "float"}},
        )
        payload = json.loads(result.content[0].text)
        assert payload["result"]["unique_key"]
        assert result.is_error is False

    def test_extraction_create_reflects_no_content(self, initialized_db: str) -> None:
        """SRS-015a / DEV-38: a create returns only the key, over the wire too."""
        result = self._call(
            initialized_db,
            "create_type_definition",
            {"name": "Probe", "kind": "simple_typedef", "subtype": {"base_type": "float"}},
        )
        payload = json.loads(result.content[0].text)
        assert set(payload["result"]) == {"unique_key"}

    def test_query_results_are_projected(self, initialized_db: str) -> None:
        """SRS-015a: only allowlisted fields cross the protocol boundary."""
        self._call(
            initialized_db,
            "create_type_definition",
            {
                "name": "Probe",
                "kind": "simple_typedef",
                "description": "must not be returned",
                "subtype": {"base_type": "float"},
            },
        )
        result = self._call(initialized_db, "query_type_definitions", {"name": "Probe"})
        record = json.loads(result.content[0].text)["result"]["records"][0]
        assert set(record) <= {"unique_key", "name", "kind", "status"}
        assert "description" not in record

    def test_authority_is_enforced_over_the_protocol(self, initialized_db: str) -> None:
        """SRS-082a: the extraction adapter cannot approve, even remotely."""
        created = self._call(
            initialized_db,
            "create_type_definition",
            {"name": "Probe", "kind": "simple_typedef", "subtype": {"base_type": "float"}},
        )
        key = json.loads(created.content[0].text)["result"]["unique_key"]
        result = self._call(
            initialized_db,
            "set_review_status",
            {"unique_key": key, "new_status": "approved", "caller": "review"},
        )
        assert result.is_error is True
        assert "SRS-082a" in json.loads(result.content[0].text)["error"]["reason"]

    def test_unknown_tool_is_a_structured_error(self, initialized_db: str) -> None:
        """SRS-109: an unknown tool is a result, not a protocol crash."""
        result = self._call(initialized_db, "no_such_tool", {})
        payload = json.loads(result.content[0].text)
        assert payload["error"]["reason"] == "unknown tool: no_such_tool"
        assert result.is_error is True

    def test_validation_error_is_reported_not_raised(self, initialized_db: str) -> None:
        """SRS-109: a rejected argument comes back as an error result."""
        result = self._call(initialized_db, "create_type_definition", {"name": "X"})
        assert result.is_error is True
        assert json.loads(result.content[0].text)["error"]["field"] == "kind"

