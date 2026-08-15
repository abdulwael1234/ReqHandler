"""Generation trigger commands: report, generate.

Both delegate to the `trigger_generation` tool rather than importing the
generator, so the CLI and the MCP surface trigger generation through one path.

See: LLD-06 §6.4 (Generate Commands)
"""

import argparse

from ..bridge import ReviewToolBridge
from ..display import DisplayFormatter


def cmd_report(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Generate the review report only (SRS-104).

    SRS-104 requires the report to be producible independently of R210
    generation, so this is a distinct command rather than a mode flag.
    """
    response = bridge.generate("report_only", getattr(args, "output", None))
    return fmt.format_result(response), (1 if "error" in response else 0)


def cmd_generate(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Trigger generation in the requested mode (SRS-090)."""
    response = bridge.generate(args.mode, getattr(args, "output", None))
    return fmt.format_result(response), (1 if "error" in response else 0)
