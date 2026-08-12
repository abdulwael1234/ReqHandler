"""Reference resolution by UUID.

See: LLD-02 §7.8 (Reference Resolution Tool — SRS-087)
"""

from typing import Any

from ..errors import McpResult, McpValidationError
from ..validation.common import validate_uuid_format
from ._engine import record_to_dict, reject_unknown_arguments
from .context import ToolContext

_TOOL = "resolve_reference"


def handle_resolve_reference(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Find the table and record owning a unique_key (SRS-087)."""
    reject_unknown_arguments(_TOOL, arguments, frozenset({"unique_key"}))
    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=_TOOL)

    with ctx.db.read_only() as conn:
        found = ctx.dal.resolve_unique_key(conn, str(key))

    if found is None:
        raise McpValidationError.of(
            _TOOL,
            f"no record with unique_key {key!r}",
            field="unique_key",
            affected_key=str(key),
        )
    table, record = found
    payload = record_to_dict(record)
    payload.pop("id", None)
    return McpResult(unique_key=str(key), data={"table": table, "record": payload}).to_dict()
