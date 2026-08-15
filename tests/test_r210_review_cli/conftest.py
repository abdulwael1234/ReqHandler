"""Fixtures shared by the review CLI tests.

Records are created through the extraction adapter, exactly as the Gemini skill
would, so the tests meet the same records a reviewer would. Creates generate
their own UUIDs (SRS-027), so the fixture returns every key it made.

The struct element references a real base type: SRS-036a blocks approval of any
record whose references are still unresolved, so a tree with a dangling
`element_type_id` can never be approved and would make approval tests useless.
"""

from dataclasses import dataclass

import pytest

from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import dispatch


@dataclass(frozen=True)
class Seeded:
    """Keys of the records a seeded database contains."""

    db_path: str
    base_type_key: str
    type_key: str
    struct_element_key: str
    issue_key: str


@pytest.fixture
def seeded(initialized_db: str) -> Seeded:
    """A base type, a struct referencing it, and one pending review issue."""
    ctx = build_context(initialized_db, adapter_mode="extraction")

    base_key = str(
        dispatch(
            ctx,
            "create_type_definition",
            {"name": "Float32", "kind": "simple_typedef", "subtype": {"base_type": "float"}},
        )["result"]["unique_key"]
    )
    type_key = str(
        dispatch(
            ctx,
            "create_type_definition",
            {"name": "SensorData", "kind": "struct", "subtype": {"elements": []}},
        )["result"]["unique_key"]
    )
    element_key = str(
        dispatch(
            ctx,
            "create_struct_element",
            {
                "struct_type_key": type_key,
                "name": "temperature",
                "position": 1,
                "element_type_key": base_key,
            },
        )["result"]["unique_key"]
    )
    issue_key = str(
        dispatch(
            ctx,
            "create_review_issue",
            {"issue_type": "incomplete", "message": "units not stated"},
        )["result"]["unique_key"]
    )

    return Seeded(
        db_path=initialized_db,
        base_type_key=base_key,
        type_key=type_key,
        struct_element_key=element_key,
        issue_key=issue_key,
    )
