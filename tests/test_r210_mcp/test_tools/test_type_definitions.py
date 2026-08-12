"""Development tests for the type-definition tools (LLD-02 §7.2)."""

import pytest

from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.type_definitions import (
    handle_create_enum_value,
    handle_create_struct_element,
    handle_create_type_definition,
    handle_query_type_definitions,
    handle_update_type_definition,
)


class TestCreateTypeDefinition:
    def test_creates_a_simple_typedef_with_its_detail_row(self, initialized_db: str) -> None:
        """SRS-038a — exactly one subtype detail row per parent."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_type_definition(
            ctx, {"name": "Speed", "kind": "simple_typedef", "subtype": {"base_type": "uint8"}}
        )
        key = response["result"]["unique_key"]
        with ctx.db.read_only() as conn:
            parent = ctx.dal.get_type_definition_by_key(conn, key)
            detail = ctx.dal.get_simple_type_definition_by_parent(conn, parent.id)
        assert detail.base_type == "uint8"

    def test_creates_an_enum_with_its_values(self, initialized_db: str) -> None:
        """SRS-037 — children are stored with their declaration positions."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_type_definition(
            ctx,
            {
                "name": "Mode",
                "kind": "enum",
                "subtype": {
                    "values": [
                        {"name": "RED", "value": "0", "position": 1},
                        {"name": "GREEN", "value": "1", "position": 2},
                    ]
                },
            },
        )
        with ctx.db.read_only() as conn:
            parent = ctx.dal.get_type_definition_by_key(conn, response["result"]["unique_key"])
            children = ctx.dal.get_children(conn, "EnumValues", "enum_type_id", parent.id)
        assert [child.name for child in children] == ["RED", "GREEN"]

    def test_creates_a_struct_with_its_elements(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        response = handle_create_type_definition(
            ctx,
            {
                "name": "Point",
                "kind": "struct",
                "subtype": {"elements": [{"name": "x", "position": 1}]},
            },
        )
        with ctx.db.read_only() as conn:
            parent = ctx.dal.get_type_definition_by_key(conn, response["result"]["unique_key"])
            children = ctx.dal.get_children(conn, "StructElements", "struct_type_id", parent.id)
        assert [child.name for child in children] == ["x"]

    def test_missing_subtype_is_rejected(self, initialized_db: str) -> None:
        """SRS-038a — the subtype detail is required."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_type_definition(ctx, {"name": "Speed", "kind": "array"})
        assert caught.value.error.field == "subtype"

    def test_rejects_an_unknown_kind(self, initialized_db: str) -> None:
        """SRS-043 — kind is one of four values."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_type_definition(ctx, {"name": "X", "kind": "record", "subtype": {}})
        assert caught.value.error.field == "kind"

    def test_unresolved_array_reference_targets_the_parent(self, initialized_db: str) -> None:
        """SRS-036a, SRS-074 — subtype rows are not reviewable artifact types."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_type_definition(
            ctx, {"name": "Buffer", "kind": "array", "subtype": {"array_size": 8}}
        )
        key = response["result"]["unique_key"]
        with ctx.db.read_only() as conn:
            issues = ctx.dal.query_review_issues(conn, {"artifact_unique_key": key})
        assert issues[0].issue_type == "unresolved_reference"
        assert issues[0].artifact_type == "type_definition"

    def test_rejects_an_array_size_below_one(self, initialized_db: str) -> None:
        """SRS-038b — array_size is an integer >= 1."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_type_definition(
                ctx, {"name": "Buffer", "kind": "array", "subtype": {"array_size": 0}}
            )
        assert caught.value.error.field == "subtype.array_size"

    def test_duplicate_name_and_kind_warns(self, initialized_db: str) -> None:
        """SRS-034, SRS-121 — the warning rides on the create response."""
        ctx = build_context(initialized_db, "review")
        payload = {"name": "Speed", "kind": "struct", "subtype": {"elements": []}}
        handle_create_type_definition(ctx, payload)
        response = handle_create_type_definition(ctx, dict(payload, name=" speed "))
        assert response["result"]["warnings"]
        with ctx.db.read_only() as conn:
            assert len(ctx.dal.query_review_issues(conn, {"issue_type": "ambiguous"})) == 1

    def test_a_failed_child_rolls_back_the_parent(self, initialized_db: str) -> None:
        """SRS-084, SRS-038c — the parent, subtype and children are one transaction."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(Exception):
            handle_create_type_definition(
                ctx,
                {
                    "name": "Mode",
                    "kind": "enum",
                    "subtype": {
                        "values": [
                            {"name": "RED", "position": 1},
                            {"name": "RED", "position": 2},
                        ]
                    },
                },
            )
        with ctx.db.read_only() as conn:
            assert ctx.dal.query_type_definitions(conn, {"name": "Mode"}) == []


class TestUpdateTypeDefinition:
    def test_rejects_a_kind_change(self, initialized_db: str) -> None:
        """SRS-120 — kind is immutable."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_type_definition(
            ctx, {"name": "Speed", "kind": "struct", "subtype": {"elements": []}}
        )["result"]["unique_key"]
        with pytest.raises(McpValidationError) as caught:
            handle_update_type_definition(ctx, {"unique_key": key, "kind": "enum"})
        assert caught.value.error.field == "kind"


class TestChildTools:
    def test_struct_element_requires_a_struct_parent(self, initialized_db: str) -> None:
        """SRS-044 — the parent kind must match the child type."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_type_definition(
            ctx, {"name": "Mode", "kind": "enum", "subtype": {"values": []}}
        )["result"]["unique_key"]
        with pytest.raises(McpValidationError) as caught:
            handle_create_struct_element(
                ctx, {"struct_type_key": key, "name": "value", "position": 1}
            )
        assert caught.value.error.field == "struct_type_key"

    def test_enum_value_requires_an_enum_parent(self, initialized_db: str) -> None:
        """SRS-044."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_type_definition(
            ctx, {"name": "Speed", "kind": "struct", "subtype": {"elements": []}}
        )["result"]["unique_key"]
        with pytest.raises(McpValidationError) as caught:
            handle_create_enum_value(ctx, {"enum_type_key": key, "name": "RED", "position": 1})
        assert caught.value.error.field == "enum_type_key"

    def test_enum_value_is_created_on_an_enum_parent(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = handle_create_type_definition(
            ctx, {"name": "Mode", "kind": "enum", "subtype": {"values": []}}
        )["result"]["unique_key"]
        response = handle_create_enum_value(
            ctx, {"enum_type_key": key, "name": "RED", "position": 1}
        )
        assert response["result"]["name"] == "RED"


class TestQuery:
    def test_filters_by_kind(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        handle_create_type_definition(
            ctx, {"name": "Mode", "kind": "enum", "subtype": {"values": []}}
        )
        handle_create_type_definition(
            ctx, {"name": "Speed", "kind": "struct", "subtype": {"elements": []}}
        )
        response = handle_query_type_definitions(ctx, {"kind": "enum"})
        assert [record["name"] for record in response["result"]["records"]] == ["Mode"]
