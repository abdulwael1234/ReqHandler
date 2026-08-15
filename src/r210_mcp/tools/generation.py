"""Generation trigger.

Delegates to the deterministic generator (LLD-04). `report_only` is fully
operative. `r210_only` and `both` run the whole pipeline too, but rendering
needs the work-computer templates: without them the generator reports the
unmet Phase 5 entry criteria and this tool returns them as a structured error,
naming what is missing rather than claiming the feature does not exist. That
supersedes DEV-31's blanket "not yet implemented"; DEV-31 closes when the
templates are installed.

The import is deferred to call time so that `r210_mcp` does not import
`r210_generator` at module load: the tool surface must stay usable — and its
tests runnable — independently of the generator package.

See: LLD-02 §7.9 (Generation Trigger Tool — SRS-090)
"""

from typing import Any

from ..errors import McpError, McpResult
from ..validation.common import validate_choice, validate_not_empty
from ._engine import reject_unknown_arguments
from .context import ToolContext

_TOOL = "trigger_generation"

GENERATION_MODES = frozenset({"r210_only", "report_only", "both"})


def handle_trigger_generation(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate the mode and destination, then run the generator (SRS-090, SRS-104).

    `output_dir` is required and has no default. Output paths are work
    configuration (SRS-019d) and this copy has none, so any default would be a
    guess — and a *relative* one would write wherever the server happened to be
    started, which is how a report first landed in the repository root (DEV-48).
    """
    reject_unknown_arguments(_TOOL, arguments, frozenset({"mode", "output_dir"}))
    mode = arguments.get("mode")
    validate_choice(mode, GENERATION_MODES, "mode", operation=_TOOL)
    output_dir = arguments.get("output_dir")
    validate_not_empty(output_dir, "output_dir", operation=_TOOL)

    from r210_generator.generator import Generator
    from r210_generator.models import GeneratorConfig

    config = GeneratorConfig(output_dir=str(output_dir))
    result = Generator(ctx.db.db_path, config).generate(str(mode))

    if result.unconfigured:
        from r210_generator.r210.templates import ENTRY_CRITERIA

        detail = "; ".join(f"{key}: {ENTRY_CRITERIA[key]}" for key in result.unconfigured)
        return McpError(
            operation=_TOOL,
            field="mode",
            reason=(
                f"R210 rendering is not configured for mode {mode!r}. "
                f"Unmet entry criteria - {detail}. "
                "See docs/WORK_MACHINE_CONFIGURATION.md and docs/PHASE5_SCOPE.md §2."
            ),
            affected_key=None,
        ).to_dict()

    # Not `**result.summary()`: LLD-04 §10 names two of its keys `warnings` and
    # `errors`, and `warnings` already means something else in an MCP response
    # envelope — a list of duplicate-detection strings (SRS-034). Splicing the
    # generator's integer counts in under those names collides with the
    # envelope, so they are renamed at this boundary (DEV-49).
    summary = result.summary()
    return McpResult(
        unique_key="",
        data={
            "mode": mode,
            "r210_files_generated": summary["r210_files_generated"],
            "report_generated": summary["report_generated"],
            "report_file": summary["report_file"],
            "exported_artifacts": summary["exported_artifacts"],
            "excluded_pending_children": summary["warnings"],
            "excluded_unresolved_references": summary["errors"],
        },
    ).to_dict()
