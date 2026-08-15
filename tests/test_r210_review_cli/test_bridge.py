"""ReviewToolBridge — direct tool invocation without MCP transport (SRS-123)."""

from typing import Any

from r210_review_cli.bridge import ReviewToolBridge

from .conftest import Seeded

UNKNOWN_KEY = "99999999-9999-4999-8999-999999999999"


class TestBridgeAuthority:
    """SRS-082a: the review adapter may approve; extraction may not."""

    def test_bridge_can_approve(self, seeded: Seeded) -> None:
        """SRS-082a: adapter_mode='review' structurally permits approval."""
        bridge = ReviewToolBridge(seeded.db_path)
        bridge.set_review_status(seeded.base_type_key, "approved")
        bridge.set_review_status(seeded.struct_element_key, "approved")
        result = bridge.set_review_status(seeded.type_key, "approved")
        assert "error" not in result, result

    def test_bridge_supplies_caller_review(self, seeded: Seeded) -> None:
        """SRS-082a: the bridge passes caller='review' so the tool accepts it."""
        bridge = ReviewToolBridge(seeded.db_path)
        result = bridge.set_review_status(seeded.type_key, "ambiguous")
        assert result["result"]["unique_key"] == seeded.type_key

    def test_parent_approval_still_enforced(self, seeded: Seeded) -> None:
        """SRS-046: a parent cannot be approved while a child is pending."""
        bridge = ReviewToolBridge(seeded.db_path)
        result = bridge.set_review_status(seeded.type_key, "approved")
        assert result["error"]["operation"] == "set_review_status"


class TestBridgeProjection:
    """SRS-015a: review mode returns full records, not Gemini projections."""

    def test_query_returns_full_records(self, seeded: Seeded) -> None:
        """SRS-015a: projection applies to extraction only, so name is present."""
        bridge = ReviewToolBridge(seeded.db_path)
        records = bridge.query("TypeDefinitions")["result"]["records"]
        assert [r["name"] for r in records] == ["Float32", "SensorData"]

    def test_query_preserves_tool_errors(self, seeded: Seeded) -> None:
        """SRS-109: a rejected filter surfaces as an error, not an empty list."""
        bridge = ReviewToolBridge(seeded.db_path)
        assert "error" in bridge.query("TypeDefinitions", {"kind": "not_a_kind"})

    def test_child_table_without_query_tool(self, seeded: Seeded) -> None:
        """LLD-06 §5.2: child tables fall back to query_by_table."""
        bridge = ReviewToolBridge(seeded.db_path)
        result = bridge.query("StructElements")["result"]
        assert result["count"] == 1


class TestBridgeShow:
    """SRS-087: resolve a key to its table, record and children."""

    def test_show_returns_table_and_children(self, seeded: Seeded) -> None:
        """SRS-087: show resolves the owning table and attaches children."""
        bridge = ReviewToolBridge(seeded.db_path)
        result = bridge.show(seeded.type_key)["result"]
        assert result["table"] == "TypeDefinitions"
        assert [child["table"] for child in result["children"]] == ["StructElements"]

    def test_show_unknown_key_returns_error(self, seeded: Seeded) -> None:
        """SRS-109: an unresolvable key yields a structured error, not a raise."""
        bridge = ReviewToolBridge(seeded.db_path)
        assert bridge.show(UNKNOWN_KEY)["error"]["operation"] == "resolve_reference"


class TestBridgeSearchAndStats:
    """SRS-118: the reviewer inspects the database without writing SQL."""

    def test_search_matches_case_insensitively(self, seeded: Seeded) -> None:
        """SRS-118: search finds a record by a lowercase prefix pattern."""
        bridge = ReviewToolBridge(seeded.db_path)
        records = bridge.search("TypeDefinitions", "sensor%")["result"]["records"]
        assert [r["name"] for r in records] == ["SensorData"]

    def test_stats_counts_every_table(self, seeded: Seeded) -> None:
        """SRS-118: stats reports totals and status breakdowns per table."""
        bridge = ReviewToolBridge(seeded.db_path)
        stats: dict[str, Any] = bridge.stats()
        assert stats["TypeDefinitions"]["total"] == 2
        assert stats["TypeDefinitions"]["by_status"] == {"pending_review": 2}
        assert stats["SimpleTypeDefinitions"]["by_status"] == {}, "structural: no status column"


class TestBridgeIssues:
    """SRS-119: issues move pending → resolved / rejected → pending."""

    def test_resolve_records_resolution(self, seeded: Seeded) -> None:
        """SRS-119: resolve sets the status and stores the resolution text."""
        bridge = ReviewToolBridge(seeded.db_path)
        result = bridge.update_review_issue(
            seeded.issue_key, status="resolved", resolution="units are mV"
        )
        assert result["result"]["status"] == "resolved"


class TestBridgeHasNoCreateOrDelete:
    """SRS-091/SRS-093: the review surface exposes no creation, no deletion."""

    def test_bridge_exposes_no_create_or_delete(self) -> None:
        """SRS-091/SRS-093: neither verb appears in the bridge's public API."""
        public = {n for n in dir(ReviewToolBridge) if not n.startswith("_")}
        assert not {n for n in public if "create" in n or "delete" in n}
