"""Structured error types for MCP tool responses.

All MCP tools return errors using the McpError dataclass, which provides:
- operation: the tool name that failed
- field: the invalid field name (optional)
- reason: human-readable explanation
- affected_key: unique_key of affected record (optional)

See: LLD-02 §3.1 (Error Response — SRS-083, SRS-109)
"""
