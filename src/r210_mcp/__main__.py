"""Run the R210 MCP server: `python -m r210_mcp <db_path> [--mode MODE]`.

See: LLD-02 §9 (MCP Server Entry Point)
"""

import argparse
import sys

from .server import R210McpServer, SdkNotInstalled


def main() -> None:
    """Entry point for the stdio MCP server."""
    parser = argparse.ArgumentParser(description="R210 MCP Server")
    parser.add_argument("db_path", help="Path to the SQLite database file")
    parser.add_argument(
        "--mode",
        default="extraction",
        choices=["extraction", "review"],
        help="Adapter authority mode (SRS-082a)",
    )
    args = parser.parse_args()
    try:
        R210McpServer(args.db_path, args.mode).run()
    except SdkNotInstalled as exc:
        # A missing optional dependency is a configuration problem, not a
        # crash: report it and exit 1 rather than printing a traceback whose
        # top line names `anyio` (DEV-51).
        print(f"r210-mcp: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
