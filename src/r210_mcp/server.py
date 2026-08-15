"""MCP server entry point.

The SDK import lives inside `build_server()` so that importing this module — which the
Local Review CLI and every test does — does not require `mcp` to be installed.
All behaviour is in `tools/registry.py`; this class only binds a database path
and an authority mode to it (DEV-26).

See: LLD-02 §9 (MCP Server Entry Point)
"""

import json
from typing import Any

from .tools.context import build_context
from .tools.registry import TOOL_HANDLERS, dispatch


class SdkNotInstalled(RuntimeError):
    """The `mcp` SDK is needed for the stdio transport and is not importable.

    Only `run()` and `build_server()` need it. Everything else — the 35 tool
    handlers, the review CLI (SRS-123), the generator — works without it, and
    the message says so, because the alternative is an operator concluding the
    whole prototype is unusable on a machine that cannot reach a package index.
    """

    def __init__(self, cause: ImportError) -> None:
        super().__init__(
            f"the MCP stdio server needs the 'mcp' SDK, which is not installed ({cause}).\n"
            "  Install it with:  python -m pip install 'mcp>=2.0'\n"
            "  Version 2.x is required: the 1.x registration API is not what this code calls.\n"
            "  Everything else works without it - the review CLI (r210-review), the\n"
            "  generator, and the tool handlers themselves are all SDK-free by design."
        )
        self.cause = cause


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

    def build_server(self) -> Any:
        """Construct the SDK server object, without serving it.

        Split out from `run` so the wiring is testable: a test can list and
        call tools through this object without opening a stdio transport.

        The SDK import is local to this method. `mcp` is a runtime dependency
        of the stdio adapter alone, and both the review CLI (SRS-123) and the
        handler tests import this module without it.
        """
        import mcp.types as types
        from mcp.server.lowlevel.server import Server

        tools = [
            types.Tool(
                name=name,
                description=(TOOL_HANDLERS[name].__doc__ or name).strip().splitlines()[0],
                # Permissive by design: argument validation is the handlers'
                # job, and they reject unknown arguments with a structured
                # McpError that carries the tool name and reason (SRS-109).
                # Publishing per-tool JSON Schema is recorded as open work.
                input_schema={"type": "object", "additionalProperties": True},
            )
            for name in TOOL_HANDLERS
        ]

        async def on_list_tools(_ctx: Any, _params: Any) -> Any:
            return types.ListToolsResult(tools=tools)

        async def on_call_tool(_ctx: Any, params: Any) -> Any:
            payload = self.handle_tool(params.name, dict(params.arguments or {}))
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(payload))],
                structured_content=payload,
                # An McpError is a *result*, not a protocol failure: SRS-109
                # requires the caller receive operation, field, reason and key.
                is_error="error" in payload,
            )

        return Server(
            "r210-automation",
            on_list_tools=on_list_tools,
            on_call_tool=on_call_tool,
        )

    def run(self) -> None:  # pragma: no cover - opens a stdio transport
        """Serve the tool surface over stdio (LLD-02 §9).

        Raises `SdkNotInstalled` rather than letting `ModuleNotFoundError`
        escape: on a machine where `mcp` cannot be installed — which the work
        computer may well be — a bare traceback naming `anyio` tells the
        operator nothing about what to do, or that the review CLI and the
        generator work regardless (DEV-51).
        """
        try:
            import anyio
            from mcp.server.stdio import stdio_server
        except ImportError as exc:
            raise SdkNotInstalled(exc) from exc

        server = self.build_server()

        async def _serve() -> None:
            async with stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        anyio.run(_serve)
