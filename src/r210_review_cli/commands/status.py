"""Status change commands: approve, reject, mark.

All three delegate to `set_review_status` with `caller="review"`, so the
transition matrix (SRS-035b), the parent-approval check (SRS-046, SRS-053,
SRS-092a), reference resolution (SRS-036a) and parent auto-demotion (SRS-035c)
are enforced by exactly the code the extraction adapter runs. That identity is
the point of SRS-123, so none of it is re-implemented here.

See: LLD-06 §6.2 (Status Commands)
"""

import argparse

from ..bridge import ReviewToolBridge
from ..display import DisplayFormatter


def _set(
    bridge: ReviewToolBridge,
    fmt: DisplayFormatter,
    unique_key: str,
    new_status: str,
    note: str | None,
) -> tuple[str, int]:
    """Apply one status change and render its outcome."""
    response = bridge.set_review_status(unique_key, new_status, review_note=note)
    return fmt.format_result(response), (1 if "error" in response else 0)


def cmd_approve(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Set status to approved (SRS-089)."""
    return _set(bridge, fmt, args.unique_key, "approved", args.note)


def cmd_reject(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Set status to rejected (SRS-089)."""
    return _set(bridge, fmt, args.unique_key, "rejected", args.note)


def cmd_mark(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Set any permitted status (SRS-089)."""
    return _set(bridge, fmt, args.unique_key, args.status, args.note)
