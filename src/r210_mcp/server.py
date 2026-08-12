"""MCP server entry point.

The SDK import lives inside `run()` so that importing this module — which the
Local Review CLI and every test does — does not require `mcp` to be installed.
All behaviour is in `tools/registry.py`; this class only binds a database path
and an authority mode to it (DEV-26).

See: LLD-02 §9 (MCP Server Entry Point)
"""

from typing import Any

from .tools.context import build_context
from .tools.registry import TOOL_HANDLERS, dispatch


class R210McpServer:
    """Binds a database and an authority mode to the tool surface (SRS-082a)."""

    def __init__(self, db_path: str, adapter_mode: str = "extraction") -> None:
        self._ctx = build_context(db_path, adapter_mode)

    @property
    def adapter_mode(self) -> str:
        return self._ctx.adapter_mode

    def tool_names(self) -> list[str]:
        """The registered tool names, in registration order."""
        return list(TOOL_HANDLERS)

    def handle_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call directly, without the MCP protocol (LLD-06)."""
        return dispatch(self._ctx, tool_name, arguments)

    def run(self) -> None:  # pragma: no cover - requires the mcp SDK
        """Serve the tool surface over stdio.

        Imported lazily: `mcp` is a runtime dependency of this method only, and
        is not installed in the development environment. Unverified here.
        """
        import anyio
        from mcp.server import Server
        from mcp.server.stdio import stdio_server

        server: Any = Server("r210-automation")

        def _make(tool_name: str) -> Any:
            async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
                return self.handle_tool(tool_name, arguments)

            return _handler

        for name in TOOL_HANDLERS:
            server.call_tool(name)(_make(name))

        async def _serve() -> None:
            async with stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        anyio.run(_serve)
