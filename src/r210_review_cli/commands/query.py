"""Query commands: list, show, search, stats.

Each command returns `(text, exit_code)` rather than printing, so the whole
command surface is testable without capturing stdout.

See: LLD-06 §6.1 (Query Commands)
"""

import argparse
from typing import Any

from ..bridge import ReviewToolBridge
from ..display import DisplayFormatter

# LLD-06 §4.2. Long form and alias resolve to the same table.
ENTITY_TABLES: dict[str, str] = {
    "sources": "SourceRequirements",
    "src": "SourceRequirements",
    "types": "TypeDefinitions",
    "td": "TypeDefinitions",
    "interfaces": "PortInterfaces",
    "pi": "PortInterfaces",
    "prototypes": "PortPrototypes",
    "pp": "PortPrototypes",
    "connections": "PortConnections",
    "pc": "PortConnections",
    "issues": "ReviewIssues",
    "ri": "ReviewIssues",
}


def resolve_entity(alias: str) -> str:
    """Map an entity type or alias to its table name (LLD-06 §4.2)."""
    table = ENTITY_TABLES.get(alias)
    if table is None:
        raise KeyError(f"unknown entity type: {alias}")
    return table


def _filters(args: argparse.Namespace) -> dict[str, Any]:
    """Collect whichever of --status/--kind/--issue-type were supplied.

    A filter the target table does not accept is passed through rather than
    dropped: the tool rejects it with a structured error, which is more useful
    to the reviewer than silently ignoring what they asked for.
    """
    filters: dict[str, Any] = {}
    for attribute in ("status", "kind", "issue_type"):
        value = getattr(args, attribute, None)
        if value is not None:
            filters[attribute] = value
    return filters


def cmd_list(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """List artifacts or issues by type (SRS-118)."""
    table = resolve_entity(args.entity_type)
    response = bridge.query(table, _filters(args))
    return fmt.format_list(response, table), (1 if "error" in response else 0)


def cmd_show(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Show one record with its children (SRS-087)."""
    response = bridge.show(args.unique_key)
    return fmt.format_detail(response), (1 if "error" in response else 0)


def cmd_search(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Search a table by name pattern (SRS-118, DEV-43)."""
    table = resolve_entity(args.entity_type)
    response = bridge.search(table, args.name)
    return fmt.format_list(response, table), (1 if "error" in response else 0)


def cmd_stats(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Report row and status counts per table (SRS-118)."""
    return fmt.format_stats(bridge.stats()), 0
