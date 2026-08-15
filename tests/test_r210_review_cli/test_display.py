"""Terminal formatting for the review CLI (SRS-118)."""

from typing import Any

from r210_review_cli.display import DisplayFormatter


def _listing(records: list[dict[str, Any]]) -> dict[str, Any]:
    """A query response envelope around the given records."""
    return {"result": {"table": "TypeDefinitions", "count": len(records), "records": records}}


class TestFormatList:
    """SRS-118: the reviewer sees artifacts in a scannable table."""

    def test_header_and_one_row_per_record(self) -> None:
        """SRS-118: a header line plus one row per record."""
        out = DisplayFormatter().format_list(
            _listing(
                [
                    {"unique_key": "aaaa", "name": "SensorData", "status": "approved"},
                    {"unique_key": "bbbb", "name": "MotorState", "status": "rejected"},
                ]
            ),
            "TypeDefinitions",
        )
        assert "TypeDefinitions (2 records)" in out.splitlines()[0]
        assert "SensorData" in out and "MotorState" in out

    def test_empty_list_says_so(self) -> None:
        """SRS-118: an empty result is stated, not printed as a blank table."""
        assert "0 records" in DisplayFormatter().format_list(_listing([]), "TypeDefinitions")

    def test_port_connection_falls_back_to_description(self) -> None:
        """LLD-01 §4.13: PortConnections has no name column."""
        out = DisplayFormatter().format_list(
            _listing([{"unique_key": "cccc", "description": "brake bus", "status": "approved"}]),
            "PortConnections",
        )
        assert "brake bus" in out

    def test_error_response_renders_as_error(self) -> None:
        """SRS-109: a rejected filter is reported, not shown as an empty table."""
        out = DisplayFormatter().format_list(
            {"error": {"operation": "query_type_definitions", "field": "kind",
                       "reason": "bad kind", "affected_key": None}},
            "TypeDefinitions",
        )
        assert "bad kind" in out


class TestColorGating:
    """SRS-118: redirected output must stay plain text (DEV-44)."""

    def test_no_ansi_when_color_disabled(self) -> None:
        """SRS-118: escape sequences never reach a pipe or file."""
        out = DisplayFormatter(color=False).format_list(
            _listing([{"unique_key": "k", "name": "N", "status": "approved"}]), "TypeDefinitions"
        )
        assert "\x1b[" not in out

    def test_ansi_present_when_color_enabled(self) -> None:
        """SRS-118: a terminal gets colour."""
        out = DisplayFormatter(color=True).format_list(
            _listing([{"unique_key": "k", "name": "N", "status": "approved"}]), "TypeDefinitions"
        )
        assert "\x1b[32m" in out and "\x1b[0m" in out

    def test_text_is_identical_apart_from_escapes(self) -> None:
        """SRS-118: colour adds nothing to the information content."""
        records = _listing([{"unique_key": "k", "name": "N", "status": "approved"}])
        plain = DisplayFormatter(color=False).format_list(records, "TypeDefinitions")
        colored = DisplayFormatter(color=True).format_list(records, "TypeDefinitions")
        assert colored.replace("\x1b[32m", "").replace("\x1b[0m", "") == plain


class TestFormatDetail:
    """SRS-087: a record is shown with its children."""

    def test_fields_and_children_appear(self) -> None:
        """SRS-087: the record's fields and each child are listed."""
        out = DisplayFormatter().format_detail(
            {
                "result": {
                    "unique_key": "aaaa",
                    "table": "TypeDefinitions",
                    "record": {"name": "SensorData", "kind": "struct", "status": "approved"},
                    "children": [
                        {
                            "table": "StructElements",
                            "record": {"name": "temperature", "status": "approved"},
                        }
                    ],
                }
            }
        )
        assert "SensorData" in out and "temperature" in out and "Children: 1" in out

    def test_internal_id_is_hidden(self) -> None:
        """SRS-027: the reviewer works in unique_keys, not primary keys."""
        out = DisplayFormatter().format_detail(
            {"result": {"unique_key": "a", "table": "T", "record": {"id": 7, "name": "N"}}}
        )
        assert "id:" not in out


class TestFormatResult:
    """SRS-109/SRS-035c: errors and demotions are surfaced, never swallowed."""

    def test_error_response_is_marked(self) -> None:
        """SRS-109: an error response prints its operation and reason."""
        out = DisplayFormatter().format_result(
            {"error": {"operation": "set_review_status", "field": "new_status",
                       "reason": "bad transition", "affected_key": "k"}}
        )
        assert "set_review_status" in out and "bad transition" in out and "✗" in out

    def test_demoted_parents_are_reported(self) -> None:
        """SRS-035c: auto-demoted parents must be visible to the reviewer."""
        out = DisplayFormatter().format_result(
            {"result": {"unique_key": "k", "status": "rejected", "demoted": ["p1", "p2"]}}
        )
        assert "p1" in out and "p2" in out and "auto-demoted" in out

    def test_warnings_are_reported(self) -> None:
        """SRS-034: duplicate warnings reach the reviewer."""
        out = DisplayFormatter().format_result(
            {"result": {"unique_key": "k", "warnings": ["possible duplicate of X"]}}
        )
        assert "possible duplicate of X" in out


class TestFormatStats:
    """SRS-118: database statistics summarise review progress."""

    def test_stats_lists_tables_with_totals(self) -> None:
        """SRS-118: each table's total and status breakdown appear."""
        out = DisplayFormatter().format_stats(
            {"TypeDefinitions": {"total": 3, "by_status": {"approved": 1, "pending_review": 2}}}
        )
        assert "TypeDefinitions" in out and "3" in out and "approved" in out

    def test_tables_are_sorted(self) -> None:
        """SRS-108: output ordering is deterministic."""
        out = DisplayFormatter().format_stats(
            {
                "ZTable": {"total": 0, "by_status": {}},
                "ATable": {"total": 0, "by_status": {}},
            }
        )
        assert out.index("ATable") < out.index("ZTable")
