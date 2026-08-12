"""Generation trigger.

The deterministic generator is LLD-04, delivered in a later phase. The tool is
registered and validates its input so the contract is real, but reports that
generation is unavailable rather than pretending to succeed (DEV-31).

See: LLD-02 §7.9 (Generation Trigger Tool — SRS-090)
"""

from typing import Any

from ..errors import McpError
from ..validation.common import validate_choice
from ._engine import reject_unknown_arguments
from .context import ToolContext

_TOOL = "trigger_generation"

GENERATION_MODES = frozenset({"r210_only", "report_only", "both"})


def handle_trigger_generation(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate the mode, then report that the generator is not available."""
    reject_unknown_arguments(_TOOL, arguments, frozenset({"mode"}))
    validate_choice(arguments.get("mode"), GENERATION_MODES, "mode", operation=_TOOL)
    return McpError(
        operation=_TOOL,
        field=None,
        reason=(
            "Deterministic generation is not yet implemented; the generator "
            "component (LLD-04) is delivered in a later phase."
        ),
        affected_key=None,
    ).to_dict()
