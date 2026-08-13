"""Run the R210 MCP server: `python -m r210_mcp <db_path> [--mode MODE]`.

See: LLD-02 §9 (MCP Server Entry Point)
"""

import argparse

from .server import R210McpServer


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
    R210McpServer(args.db_path, args.mode).run()


if __name__ == "__main__":
    main()
