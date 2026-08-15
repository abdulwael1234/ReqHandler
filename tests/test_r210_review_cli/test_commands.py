"""Query, status and issue commands (SRS-089, SRS-118, SRS-119)."""

import argparse

from r210_review_cli.bridge import ReviewToolBridge
from r210_review_cli.commands import issues, query, status
from r210_review_cli.display import DisplayFormatter

from .conftest import Seeded

UNKNOWN_KEY = "99999999-9999-4999-8999-999999999999"


def _args(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _tools(seeded: Seeded) -> tuple[ReviewToolBridge, DisplayFormatter]:
    return ReviewToolBridge(seeded.db_path), DisplayFormatter()


class TestEntityAliases:
    """LLD-06 §4.2: six entity types, each with a short alias."""

    def test_long_and_short_forms_agree(self) -> None:
        """SRS-118: both spellings address the same table."""
        assert query.resolve_entity("types") == query.resolve_entity("td") == "TypeDefinitions"
        assert query.resolve_entity("issues") == query.resolve_entity("ri") == "ReviewIssues"

    def test_six_entities_twelve_spellings(self) -> None:
        """LLD-06 §4.2: exactly six tables reachable, under twelve names."""
        assert len(set(query.ENTITY_TABLES.values())) == 6
        assert len(query.ENTITY_TABLES) == 12

    def test_unknown_alias_raises(self) -> None:
        """SRS-118: an unrecognised entity type is a programming error."""
        try:
            query.resolve_entity("widgets")
        except KeyError as exc:
            assert "widgets" in str(exc)
        else:
            raise AssertionError("expected KeyError")


class TestListCommand:
    """SRS-118: the reviewer lists artifacts by type."""

    def test_list_returns_records(self, seeded: Seeded) -> None:
        """SRS-118: listing a populated table succeeds."""
        bridge, fmt = _tools(seeded)
        text, code = query.cmd_list(
            bridge, fmt, _args(entity_type="td", status=None, kind=None, issue_type=None)
        )
        assert code == 0
        assert "SensorData" in text

    def test_list_filters_by_status(self, seeded: Seeded) -> None:
        """SRS-118: --status narrows the result set."""
        bridge, fmt = _tools(seeded)
        text, code = query.cmd_list(
            bridge, fmt, _args(entity_type="td", status="approved", kind=None, issue_type=None)
        )
        assert code == 0
        assert "0 records" in text

    def test_rejected_filter_exits_one(self, seeded: Seeded) -> None:
        """SRS-109: an unacceptable filter is reported, not silently dropped."""
        bridge, fmt = _tools(seeded)
        text, code = query.cmd_list(
            bridge, fmt, _args(entity_type="td", status=None, kind="nonsense", issue_type=None)
        )
        assert code == 1
        assert "kind" in text


class TestShowCommand:
    """SRS-087: show resolves a key to its record."""

    def test_show_known_key(self, seeded: Seeded) -> None:
        """SRS-087: a known key prints its table, fields and children."""
        bridge, fmt = _tools(seeded)
        text, code = query.cmd_show(bridge, fmt, _args(unique_key=seeded.type_key))
        assert code == 0
        assert "TypeDefinitions" in text and "temperature" in text

    def test_show_unknown_key_exits_one(self, seeded: Seeded) -> None:
        """SRS-109: an unresolvable key is an error, exit code 1."""
        bridge, fmt = _tools(seeded)
        text, code = query.cmd_show(bridge, fmt, _args(unique_key=UNKNOWN_KEY))
        assert code == 1
        assert "resolve_reference" in text


class TestSearchAndStats:
    """SRS-118: name search and database statistics."""

    def test_search_finds_by_pattern(self, seeded: Seeded) -> None:
        """SRS-118: a lowercase prefix matches a mixed-case name."""
        bridge, fmt = _tools(seeded)
        text, code = query.cmd_search(bridge, fmt, _args(entity_type="td", name="sensor%"))
        assert code == 0
        assert "SensorData" in text and "Float32" not in text

    def test_stats_reports_totals(self, seeded: Seeded) -> None:
        """SRS-118: stats includes every table."""
        bridge, fmt = _tools(seeded)
        text, code = query.cmd_stats(bridge, fmt, _args())
        assert code == 0
        assert "TypeDefinitions" in text and "ReviewIssues" in text


class TestStatusCommands:
    """SRS-089: the reviewer sets artifact review state."""

    def test_approve_succeeds(self, seeded: Seeded) -> None:
        """SRS-082a: review authority permits approval."""
        bridge, fmt = _tools(seeded)
        text, code = status.cmd_approve(
            bridge, fmt, _args(unique_key=seeded.base_type_key, note=None)
        )
        assert code == 0
        assert "✓" in text

    def test_reject_carries_the_note(self, seeded: Seeded) -> None:
        """SRS-089: --note is passed through as review_note."""
        bridge, fmt = _tools(seeded)
        _, code = status.cmd_reject(
            bridge, fmt, _args(unique_key=seeded.type_key, note="wrong units")
        )
        assert code == 0
        record = bridge.show(seeded.type_key)["result"]["record"]
        assert record["review_note"] == "wrong units"

    def test_mark_rejects_an_invalid_transition(self, seeded: Seeded) -> None:
        """SRS-035b: an impermissible transition fails with exit code 1."""
        bridge, fmt = _tools(seeded)
        status.cmd_mark(
            bridge, fmt, _args(unique_key=seeded.base_type_key, status="out_of_scope", note=None)
        )
        text, code = status.cmd_mark(
            bridge, fmt, _args(unique_key=seeded.base_type_key, status="approved", note=None)
        )
        assert code == 1
        assert "set_review_status" in text

    def test_parent_approval_blocked_by_pending_child(self, seeded: Seeded) -> None:
        """SRS-046: a parent cannot be approved while a child is pending."""
        bridge, fmt = _tools(seeded)
        text, code = status.cmd_approve(bridge, fmt, _args(unique_key=seeded.type_key, note=None))
        assert code == 1
        assert "children" in text

    def test_unknown_key_exits_one(self, seeded: Seeded) -> None:
        """SRS-109: an unresolvable key is a structured error."""
        bridge, fmt = _tools(seeded)
        _, code = status.cmd_approve(bridge, fmt, _args(unique_key=UNKNOWN_KEY, note=None))
        assert code == 1

    def test_issues_are_refused_by_set_review_status(self, seeded: Seeded) -> None:
        """SRS-119: issue status goes through update_review_issue only."""
        bridge, fmt = _tools(seeded)
        text, code = status.cmd_approve(bridge, fmt, _args(unique_key=seeded.issue_key, note=None))
        assert code == 1
        assert "update_review_issue" in text


class TestIssueCommands:
    """SRS-119: issues move pending → resolved / rejected → pending."""

    def test_resolve_sets_resolved_and_text(self, seeded: Seeded) -> None:
        """SRS-119: resolve records the resolution text."""
        bridge, fmt = _tools(seeded)
        _, code = issues.cmd_resolve(
            bridge, fmt, _args(unique_key=seeded.issue_key, resolution="units are mV")
        )
        assert code == 0
        record = bridge.show(seeded.issue_key)["result"]["record"]
        assert (record["status"], record["resolution"]) == ("resolved", "units are mV")

    def test_dismiss_then_reopen(self, seeded: Seeded) -> None:
        """SRS-119: a dismissed issue can be reopened."""
        bridge, fmt = _tools(seeded)
        _, dismiss_code = issues.cmd_dismiss(bridge, fmt, _args(unique_key=seeded.issue_key))
        _, reopen_code = issues.cmd_reopen(bridge, fmt, _args(unique_key=seeded.issue_key))
        assert (dismiss_code, reopen_code) == (0, 0)
        assert bridge.show(seeded.issue_key)["result"]["record"]["status"] == "pending"

    def test_unknown_issue_exits_one(self, seeded: Seeded) -> None:
        """SRS-109: an unknown issue key is a structured error."""
        bridge, fmt = _tools(seeded)
        _, code = issues.cmd_dismiss(bridge, fmt, _args(unique_key=UNKNOWN_KEY))
        assert code == 1
