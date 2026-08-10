"""MCP server entry point and tool registration.

This module implements the R210McpServer class, which:
- Registers all 35 MCP tool handlers
- Dispatches incoming tool calls to the appropriate handler
- Manages the database connection lifecycle
- Runs as a stdio-based MCP server process

See: LLD-02 §9 (Tool Registration)
"""
