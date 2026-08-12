"""Structured error and success types for MCP tool responses.

All MCP tools return errors using the McpError dataclass, which provides:
- operation: the tool name that failed
- field: the invalid field name (optional)
- reason: human-readable explanation
- affected_key: unique_key of affected record (optional)

See: LLD-02 §3.1 (Error Response — SRS-083, SRS-109), §3.2 (Success Response)
"""

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any


@dataclass(frozen=True)
class McpError:
    """Structured error returned to MCP callers (LLD-02 §3.1)."""

    operation: str
    field: str | None = None
    reason: str = dataclass_field(kw_only=True)
    affected_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "operation": self.operation,
                "field": self.field,
                "reason": self.reason,
                "affected_key": self.affected_key,
            }
        }


@dataclass(frozen=True)
class McpResult:
    """Structured success response returned to MCP callers (LLD-02 §3.2)."""

    unique_key: str
    # Additional fields relevant to the operation.
    data: dict[str, Any] = dataclass_field(default_factory=dict)
    # Duplicate-detection warnings (SRS-034, SRS-121).
    warnings: list[str] = dataclass_field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"unique_key": self.unique_key, **self.data}
        if self.warnings:
            result["warnings"] = self.warnings
        return {"result": result}
