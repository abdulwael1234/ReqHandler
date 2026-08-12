"""Development tests for the source-requirement tools (LLD-02 §7.1)."""

import pytest

from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.source_requirements import (
    handle_create_source_requirement,
    handle_query_source_requirements,
    handle_update_source_requirement,
)


class TestCreate:
    def test_creates_with_a_generated_key(self, initialized_db: str) -> None:
        """SRS-085 — the server creates source requirements."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_source_requirement(
            ctx, {"source_reference": "REQ-1", "source_text": "The ECU shall..."}
        )
        assert response["result"]["source_reference"] == "REQ-1"
        assert response["result"]["status"] == "pending_review"

    def test_rejects_an_empty_reference(self, initialized_db: str) -> None:
        """SRS-083 — invalid input names the field."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_source_requirement(ctx, {"source_reference": "  "})
        assert caught.value.error.field == "source_reference"

    def test_accepts_an_initial_status(self, initialized_db: str) -> None:
        """SRS-035a — the skill may tag an uncertain record at creation."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_source_requirement(
            ctx, {"source_reference": "REQ-2", "initial_status": "ambiguous"}
        )
        assert response["result"]["status"] == "ambiguous"

    def test_rejects_approved_as_an_initial_status(self, initialized_db: str) -> None:
        """SRS-082a — a create tool cannot claim approval."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError):
            handle_create_source_requirement(
                ctx, {"source_reference": "REQ-3", "initial_status": "approved"}
            )


class TestUpdate:
    def test_updates_the_text(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = handle_create_source_requirement(ctx, {"source_reference": "REQ-1"})["result"][
            "unique_key"
        ]
        response = handle_update_source_requirement(
            ctx, {"unique_key": key, "source_text": "revised"}
        )
        assert response["result"]["source_text"] == "revised"

    def test_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a — status only through set_review_status."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_source_requirement(ctx, {"source_reference": "REQ-1"})["result"][
            "unique_key"
        ]
        with pytest.raises(McpValidationError) as caught:
            handle_update_source_requirement(ctx, {"unique_key": key, "status": "approved"})
        assert caught.value.error.field == "status"


class TestQuery:
    def test_filters_by_status(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        handle_create_source_requirement(ctx, {"source_reference": "REQ-1"})
        handle_create_source_requirement(
            ctx, {"source_reference": "REQ-2", "initial_status": "out_of_scope"}
        )
        response = handle_query_source_requirements(ctx, {"status": "out_of_scope"})
        assert response["result"]["count"] == 1
        assert response["result"]["records"][0]["source_reference"] == "REQ-2"

    def test_rejects_an_invalid_status_filter(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError):
            handle_query_source_requirements(ctx, {"status": "bogus"})
