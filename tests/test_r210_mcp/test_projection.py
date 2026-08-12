"""Development tests for the SRS-015a response projection (LLD-02 §11)."""

from r210_mcp.projection import GEMINI_ALLOWED_FIELDS, project_record, project_response

FORBIDDEN = [
    "source_text",
    "description",
    "review_note",
    "resolution",
    "component_reference",
    "function_name",
]


class TestAllowlist:
    def test_forbidden_fields_are_absent_from_the_allowlist(self) -> None:
        """SRS-015a — the exclusion list is explicit in the requirement."""
        for field in FORBIDDEN:
            assert field not in GEMINI_ALLOWED_FIELDS

    def test_permitted_fields_are_present(self) -> None:
        for field in [
            "unique_key",
            "name",
            "kind",
            "interface_type",
            "status",
            "direction",
            "source_reference",
            "issue_type",
        ]:
            assert field in GEMINI_ALLOWED_FIELDS


class TestProjectRecord:
    def test_drops_a_forbidden_field(self) -> None:
        """SRS-015a — description never reaches the Gemini context."""
        projected = project_record(
            {"unique_key": "k", "name": "Speed", "kind": "struct", "description": "secret"}
        )
        assert projected == {"unique_key": "k", "name": "Speed", "kind": "struct"}

    def test_keeps_source_reference_for_source_requirements(self) -> None:
        """SRS-015a — SourceRequirements has no name; source_reference stands in."""
        projected = project_record(
            {"unique_key": "k", "source_reference": "REQ-1", "source_text": "secret"}
        )
        assert projected == {"unique_key": "k", "source_reference": "REQ-1"}


class TestProjectResponse:
    def test_drops_a_forbidden_top_level_field(self) -> None:
        """SRS-015a — a create response carries record fields inline."""
        payload = {
            "result": {"unique_key": "k", "source_reference": "REQ-1", "source_text": "secret"}
        }
        assert project_response(payload) == {
            "result": {"unique_key": "k", "source_reference": "REQ-1"}
        }

    def test_projects_nested_record_lists(self) -> None:
        payload = {
            "result": {
                "unique_key": "k",
                "records": [
                    {"unique_key": "a", "name": "A", "description": "secret"},
                    {"unique_key": "b", "name": "B", "review_note": "secret"},
                ],
            }
        }
        projected = project_response(payload)
        for record in projected["result"]["records"]:
            assert "description" not in record
            assert "review_note" not in record

    def test_preserves_warnings_and_metadata(self) -> None:
        """SRS-015a — warning text and returned keys are permitted metadata."""
        payload = {
            "result": {"unique_key": "k", "warnings": ["Possible duplicate: ..."], "count": 2}
        }
        projected = project_response(payload)
        assert projected["result"]["warnings"] == ["Possible duplicate: ..."]
        assert projected["result"]["count"] == 2

    def test_passes_an_error_response_through(self) -> None:
        payload = {"error": {"operation": "t", "field": None, "reason": "r", "affected_key": None}}
        assert project_response(payload) == payload
