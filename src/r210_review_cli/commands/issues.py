"""Review issue lifecycle commands: resolve, dismiss, reopen.

`ISSUE_STATUSES` is {"pending", "resolved", "rejected"} (LLD-01), so the three
commands are three target states of one tool. Which transitions are legal is
`update_review_issue`'s decision, not this module's (SRS-119).

See: LLD-06 §6.3 (Issue Commands)
"""

import argparse

from ..bridge import ReviewToolBridge
from ..display import DisplayFormatter


def cmd_resolve(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Resolve an issue, recording its resolution text (SRS-119)."""
    response = bridge.update_review_issue(
        args.unique_key, status="resolved", resolution=args.resolution
    )
    return fmt.format_result(response), (1 if "error" in response else 0)


def cmd_dismiss(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Reject an issue without resolving it (SRS-119)."""
    response = bridge.update_review_issue(args.unique_key, status="rejected")
    return fmt.format_result(response), (1 if "error" in response else 0)


def cmd_reopen(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Return a resolved or rejected issue to pending (SRS-119)."""
    response = bridge.update_review_issue(args.unique_key, status="pending")
    return fmt.format_result(response), (1 if "error" in response else 0)
