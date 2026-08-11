"""Allow running as: python -m r210_mcp"""

import sys


def main() -> None:
    """Start the MCP server on stdio transport.

    TODO: Parse db_path from arguments/environment and start R210McpServer.
    """
    print("r210-mcp: not yet implemented", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
