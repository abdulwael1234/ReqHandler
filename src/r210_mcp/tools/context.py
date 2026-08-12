"""The context every tool handler receives.

LLD-02 §9 makes handlers bound methods of `R210McpServer`. They are functions
over this context instead, so that a handler can be called without the MCP SDK
present — which LLD-06 requires for the Local Review CLI (DEV-26).

See: LLD-02 §9 (MCP Server Entry Point)
"""

from dataclasses import dataclass

from ..db.connection import DatabaseConnection
from ..db.dal import DataAccessLayer

# The adapter's authority, bound at construction time (SRS-082a).
VALID_ADAPTER_MODES = frozenset({"extraction", "review"})


@dataclass(frozen=True)
class ToolContext:
    """Everything a handler needs: a connection factory, the DAL, authority."""

    db: DatabaseConnection
    dal: DataAccessLayer
    adapter_mode: str


def build_context(db_path: str, adapter_mode: str = "extraction") -> ToolContext:
    """Construct a context, defaulting to the mode that cannot approve.

    `ValueError`, not `McpValidationError`: an invalid mode is a wiring error
    at construction time, never caller-supplied tool input.
    """
    if adapter_mode not in VALID_ADAPTER_MODES:
        raise ValueError(f"adapter_mode must be one of {sorted(VALID_ADAPTER_MODES)}")
    return ToolContext(
        db=DatabaseConnection(db_path), dal=DataAccessLayer(), adapter_mode=adapter_mode
    )
