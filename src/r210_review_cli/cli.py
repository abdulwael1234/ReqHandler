"""CLI entry point and argument parsing.

Twelve commands, per LLD-06 §4.1. The previous stub docstring listed nine; it
predated LLD-06 v1.2 and was stale, so it is corrected here rather than treated
as the specification.

Usage:
    r210-review [--db <path>] <command> [arguments] [options]

Commands:
    list    <entity_type>                     List artifacts/issues by type
    show    <unique_key>                      Show detailed record
    search  <entity_type> --name <pattern>    Search by name
    approve <unique_key> [--note <text>]      Set status to approved
    reject  <unique_key> [--note <text>]      Set status to rejected
    mark    <unique_key> <status> [--note]    Set any valid status
    resolve <issue_key> --resolution <text>   Resolve a review issue
    dismiss <issue_key>                       Reject a review issue
    reopen  <issue_key>                       Reopen a resolved/rejected issue
    report  [--output <path>]                 Generate review report
    generate [--mode <mode>] [--output <dir>] Trigger R210 generation
    stats                                     Show database statistics

Exit codes: 0 success, 1 tool error, 2 usage error (DEV-42).

See: LLD-06 §4 (CLI Entry Point)
"""

import argparse
import sys
from collections.abc import Callable

from .bridge import ReviewToolBridge
from .commands import generate, issues, query, status
from .display import DisplayFormatter

ENTITY_CHOICES = [
    "sources",
    "src",
    "types",
    "td",
    "interfaces",
    "pi",
    "prototypes",
    "pp",
    "connections",
    "pc",
    "issues",
    "ri",
]

ARTIFACT_STATUS_CHOICES = [
    "pending_review",
    "approved",
    "rejected",
    "ambiguous",
    "out_of_scope",
]

GENERATION_MODES = ["r210_only", "report_only", "both"]

Command = Callable[[ReviewToolBridge, DisplayFormatter, argparse.Namespace], tuple[str, int]]

COMMANDS: dict[str, Command] = {
    "list": query.cmd_list,
    "show": query.cmd_show,
    "search": query.cmd_search,
    "stats": query.cmd_stats,
    "approve": status.cmd_approve,
    "reject": status.cmd_reject,
    "mark": status.cmd_mark,
    "resolve": issues.cmd_resolve,
    "dismiss": issues.cmd_dismiss,
    "reopen": issues.cmd_reopen,
    "report": generate.cmd_report,
    "generate": generate.cmd_generate,
}


def build_parser() -> argparse.ArgumentParser:
    """Construct the full twelve-command parser (LLD-06 §4.3)."""
    parser = argparse.ArgumentParser(
        prog="r210-review",
        description="R210 Local Review CLI - review artifacts without Gemini API",
    )
    parser.add_argument("--db", default="r210.db", help="Path to SQLite database file")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List artifacts by type")
    list_parser.add_argument("entity_type", choices=ENTITY_CHOICES)
    list_parser.add_argument("--status", help="Filter by status")
    list_parser.add_argument("--kind", help="Filter by kind (types only)")
    list_parser.add_argument("--issue-type", dest="issue_type", help="Filter by issue_type")

    show_parser = sub.add_parser("show", help="Show record details")
    show_parser.add_argument("unique_key", help="UUID of the record")

    search_parser = sub.add_parser("search", help="Search by name")
    search_parser.add_argument("entity_type", choices=ENTITY_CHOICES)
    search_parser.add_argument("--name", required=True, help="Name pattern to search")

    for name, helptext in (("approve", "Approve an artifact"), ("reject", "Reject an artifact")):
        parser_for = sub.add_parser(name, help=helptext)
        parser_for.add_argument("unique_key")
        parser_for.add_argument("--note", help="Review note")

    mark_parser = sub.add_parser("mark", help="Set artifact status")
    mark_parser.add_argument("unique_key")
    mark_parser.add_argument("status", choices=ARTIFACT_STATUS_CHOICES)
    mark_parser.add_argument("--note", help="Review note")

    resolve_parser = sub.add_parser("resolve", help="Resolve a review issue")
    resolve_parser.add_argument("unique_key")
    resolve_parser.add_argument("--resolution", required=True, help="Resolution text")

    for name, helptext in (("dismiss", "Reject a review issue"), ("reopen", "Reopen an issue")):
        parser_for = sub.add_parser(name, help=helptext)
        parser_for.add_argument("unique_key")

    report_parser = sub.add_parser("report", help="Generate review report")
    report_parser.add_argument("--output", help="Output directory")

    gen_parser = sub.add_parser("generate", help="Trigger R210 generation")
    gen_parser.add_argument("--mode", choices=GENERATION_MODES, default="both")
    gen_parser.add_argument("--output", help="Output directory")

    sub.add_parser("stats", help="Show database statistics")
    return parser


def _make_stdout_printable() -> None:
    """Ensure the box-drawing and status glyphs of LLD-06 §6.2 can be written.

    On Windows `sys.stdout` defaults to cp1252, which cannot encode `─`, `■`,
    `✓`, `✗` or `⚠`, so printing a formatted table raises UnicodeEncodeError.
    Reconfiguring to UTF-8 with `errors="replace"` keeps the specified output
    where the console supports it and degrades to `?` where it does not —
    either way the CLI never dies on an encoding.
    """
    stream = sys.stdout
    if hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):  # pragma: no cover - stream already closed
            pass


def run(argv: list[str] | None = None) -> int:
    """Parse, dispatch, print, and return the exit code.

    Returning an int rather than exiting is what makes the whole CLI testable
    in-process; `main` is the only place that calls `sys.exit`.
    """
    args = build_parser().parse_args(argv)
    _make_stdout_printable()
    bridge = ReviewToolBridge(args.db)
    formatter = DisplayFormatter(color=sys.stdout.isatty())
    text, code = COMMANDS[args.command](bridge, formatter, args)
    print(text)
    return code


def main() -> None:
    """Entry point for the r210-review console script."""
    sys.exit(run())
