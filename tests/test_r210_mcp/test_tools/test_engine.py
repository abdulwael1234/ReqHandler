"""Development tests for the descriptor engine (LLD-02 §7, §10).

The specs here are stand-ins for the real tool descriptors, so the engine is
exercised independently of any particular tool module.
"""

from typing import Any
from uuid import UUID

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.db.models import SourceRequirementRecord
from r210_mcp.errors import McpValidationError
from r210_mcp.tools._engine import (
    ARTIFACT_TYPE_FOR_TABLE,
    CreateSpec,
    FieldSpec,
    QuerySpec,
    RefSpec,
    UpdateSpec,
    choice_of,
    collect_fields,
    initial_status,
    record_to_dict,
    reject_status_argument,
    reject_unknown_arguments,
    run_create,
    run_query,
    run_update,
)
from r210_mcp.tools.context import VALID_ADAPTER_MODES, ToolContext, build_context
from r210_mcp.validation.common import validate_not_empty, validate_position

MISSING_KEY = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
STATUSES = frozenset({"pending_review", "approved", "rejected", "ambiguous", "out_of_scope"})

SOURCE_REQUIREMENT = CreateSpec(
    tool="create_source_requirement",
    table="SourceRequirements",
    fields=(
        FieldSpec("source_reference", "source_reference", True, validate_not_empty),
        FieldSpec("source_text", "source_text"),
    ),
)

TYPE_DEFINITION = CreateSpec(
    tool="create_type_definition",
    table="TypeDefinitions",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("kind", "kind", True),
    ),
    duplicate_name_arg="name",
    duplicate_kind_arg="kind",
)

ENUM_VALUE = CreateSpec(
    tool="create_enum_value",
    table="EnumValues",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("position", "position", True, validate_position),
    ),
    refs=(RefSpec("enum_type_key", "enum_type_id", "TypeDefinitions", required=True, parent=True),),
)

STRUCT_ELEMENT = CreateSpec(
    tool="create_struct_element",
    table="StructElements",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("position", "position", True, validate_position),
    ),
    refs=(
        RefSpec("struct_type_key", "struct_type_id", "TypeDefinitions", required=True, parent=True),
        RefSpec("element_type_key", "element_type_id", "TypeDefinitions", may_be_unresolved=True),
    ),
)

UPDATE_TYPE_DEFINITION = UpdateSpec(
    tool="update_type_definition",
    table="TypeDefinitions",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("description", "description"),
    ),
    immutable_args=("kind",),
)

UPDATE_STRUCT_ELEMENT = UpdateSpec(
    tool="update_struct_element",
    table="StructElements",
    fields=(FieldSpec("name", "name", validator=validate_not_empty),),
    refs=(RefSpec("element_type_key", "element_type_id", "TypeDefinitions",
                  may_be_unresolved=True),),
)

QUERY_SOURCE_REQUIREMENTS = QuerySpec(
    tool="query_source_requirements",
    table="SourceRequirements",
    filters=(
        FieldSpec("status", "status", validator=choice_of(STATUSES)),
        FieldSpec("source_reference", "source_reference"),
    ),
)


def _key(response: dict[str, Any]) -> str:
    return str(response["result"]["unique_key"])


# ── Task 7: context and shared parts ────────────────────────────────────────


class TestToolContext:
    def test_build_context_defaults_to_extraction(self, initialized_db: str) -> None:
        """SRS-082a — the safe mode is the default."""
        assert build_context(initialized_db).adapter_mode == "extraction"

    def test_build_context_rejects_an_unknown_mode(self, initialized_db: str) -> None:
        with pytest.raises(ValueError):
            build_context(initialized_db, "administrator")

    def test_both_modes_are_valid(self, initialized_db: str) -> None:
        for mode in VALID_ADAPTER_MODES:
            assert isinstance(build_context(initialized_db, mode), ToolContext)


class TestSharedParts:
    def test_reject_status_argument(self) -> None:
        """SRS-091a — status changes only through set_review_status."""
        with pytest.raises(McpValidationError) as caught:
            reject_status_argument("update_type_definition", {"unique_key": "k", "status": "x"})
        assert caught.value.error.field == "status"
        assert "set_review_status" in caught.value.error.reason
        assert caught.value.error.affected_key == "k"
        reject_status_argument("update_type_definition", {"unique_key": "k", "name": "X"})

    def test_reject_unknown_arguments(self) -> None:
        """SRS-083 — an unknown argument is a caller error, not silently dropped."""
        with pytest.raises(McpValidationError) as caught:
            reject_unknown_arguments("create_source_requirement", {"bogus": 1}, frozenset({"name"}))
        assert caught.value.error.field == "bogus"

    def test_collect_fields_maps_argument_to_column(self) -> None:
        fields = (FieldSpec(arg="function", column="function_name"),)
        assert collect_fields("t", fields, {"function": "Run"}, require=False) == {
            "function_name": "Run"
        }

    def test_collect_fields_enforces_required_only_on_create(self) -> None:
        fields = (FieldSpec("name", "name", True, validate_not_empty),)
        with pytest.raises(McpValidationError) as caught:
            collect_fields("t", fields, {}, require=True)
        assert caught.value.error.field == "name"
        assert collect_fields("t", fields, {}, require=False) == {}

    def test_choice_of(self) -> None:
        validator = choice_of(frozenset({"input", "output"}))
        validator("input", "direction", operation="t")
        with pytest.raises(McpValidationError):
            validator("sideways", "direction", operation="t")

    def test_initial_status_defaults_and_restricts(self) -> None:
        """SRS-035a, SRS-082a — a create tool cannot claim a review outcome."""
        assert initial_status("t", {}) == "pending_review"
        for value in ("pending_review", "ambiguous", "out_of_scope"):
            assert initial_status("t", {"initial_status": value}) == value
        for value in ("approved", "rejected", "bogus"):
            with pytest.raises(McpValidationError) as caught:
                initial_status("t", {"initial_status": value})
            assert caught.value.error.field == "initial_status"

    def test_record_to_dict(self) -> None:
        record = SourceRequirementRecord(1, "k", "REQ-1", None, "pending_review", None)
        assert record_to_dict(record)["source_reference"] == "REQ-1"

    def test_artifact_type_map_inverts_the_model_registry(self) -> None:
        """SRS-074 — every artifact table has one artifact_type name."""
        assert ARTIFACT_TYPE_FOR_TABLE["TypeDefinitions"] == "type_definition"
        assert ARTIFACT_TYPE_FOR_TABLE["PortConnectionMembers"] == "port_connection_member"
        assert "SourceRequirements" not in ARTIFACT_TYPE_FOR_TABLE


# ── Task 8: the create engine ───────────────────────────────────────────────


class TestCreateEngine:
    def test_inserts_and_returns_a_uuid_key(self, initialized_db: str) -> None:
        """SRS-027 — every referable record carries a generated UUID."""
        ctx = build_context(initialized_db, "review")
        key = _key(run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": "REQ-1"}))
        UUID(key)
        with ctx.db.read_only() as conn:
            record = ctx.dal.get_record_by_unique_key(conn, "SourceRequirements", key)
        assert record.source_reference == "REQ-1"

    def test_defaults_status_to_pending_review(self, initialized_db: str) -> None:
        """SRS-035a — new records start pending_review."""
        ctx = build_context(initialized_db, "review")
        response = run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": "REQ-2"})
        assert response["result"]["status"] == "pending_review"

    def test_missing_required_argument_is_rejected(self, initialized_db: str) -> None:
        """SRS-083 — the error names the missing field."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            run_create(ctx, SOURCE_REQUIREMENT, {})
        assert caught.value.error.field == "source_reference"

    def test_unknown_argument_is_rejected(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError):
            run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": "R", "colour": "red"})

    def test_resolves_a_parent_key_to_an_id(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        parent = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Mode", "kind": "enum"}))
        response = run_create(
            ctx, ENUM_VALUE, {"enum_type_key": parent, "name": "RED", "position": 1}
        )
        assert response["result"]["name"] == "RED"

    def test_unknown_parent_key_is_rejected(self, initialized_db: str) -> None:
        """SRS-083 — a key that resolves to nothing is a caller error."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            run_create(ctx, ENUM_VALUE, {"enum_type_key": MISSING_KEY, "name": "R", "position": 1})
        assert caught.value.error.field == "enum_type_key"

    def test_unresolved_reference_creates_an_issue(self, initialized_db: str) -> None:
        """SRS-036a — an unresolved type reference is recorded for review."""
        ctx = build_context(initialized_db, "review")
        parent = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"}))
        child = _key(
            run_create(
                ctx, STRUCT_ELEMENT, {"struct_type_key": parent, "name": "value", "position": 1}
            )
        )
        with ctx.db.read_only() as conn:
            issues = ctx.dal.query_review_issues(conn, {"artifact_unique_key": child})
        assert len(issues) == 1
        assert issues[0].issue_type == "unresolved_reference"
        assert issues[0].artifact_type == "struct_element"

    def test_child_creation_demotes_an_approved_parent(self, initialized_db: str) -> None:
        """SRS-035c, LLD-02 §10.4 — a new pending child invalidates approval."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        parent = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Mode", "kind": "enum"}))
        with ctx.db.transaction() as conn:
            record = dal.get_type_definition_by_key(conn, parent)
            dal.update_status(conn, "TypeDefinitions", record.id, "approved")
        response = run_create(
            ctx, ENUM_VALUE, {"enum_type_key": parent, "name": "RED", "position": 1}
        )
        assert response["result"]["demoted"] == [parent]

    def test_duplicate_produces_a_warning_and_an_issue(self, initialized_db: str) -> None:
        """SRS-034, SRS-121 — the warning is returned and an issue is created."""
        ctx = build_context(initialized_db, "review")
        run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"})
        response = run_create(ctx, TYPE_DEFINITION, {"name": "  speed ", "kind": "struct"})
        assert response["result"]["warnings"]
        with ctx.db.read_only() as conn:
            assert len(ctx.dal.query_review_issues(conn, {"issue_type": "ambiguous"})) == 1

    def test_a_failed_insert_leaves_nothing_behind(self, initialized_db: str) -> None:
        """SRS-084 — the whole create is one transaction."""
        ctx = build_context(initialized_db, "review")
        parent = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Mode", "kind": "enum"}))
        run_create(ctx, ENUM_VALUE, {"enum_type_key": parent, "name": "RED", "position": 1})
        with pytest.raises(Exception):
            run_create(ctx, ENUM_VALUE, {"enum_type_key": parent, "name": "RED", "position": 2})
        with ctx.db.read_only() as conn:
            assert len(ctx.dal.query_enum_values(conn, {"name": "RED"})) == 1


# ── Task 9: the update engine ───────────────────────────────────────────────


class TestUpdateEngine:
    def test_updates_a_permitted_field(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"}))
        run_update(ctx, UPDATE_TYPE_DEFINITION, {"unique_key": key, "name": "Velocity"})
        with ctx.db.read_only() as conn:
            assert ctx.dal.get_type_definition_by_key(conn, key).name == "Velocity"

    def test_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a — status is not an updatable field."""
        ctx = build_context(initialized_db, "review")
        key = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"}))
        with pytest.raises(McpValidationError) as caught:
            run_update(ctx, UPDATE_TYPE_DEFINITION, {"unique_key": key, "status": "approved"})
        assert caught.value.error.field == "status"

    def test_rejects_an_immutable_field(self, initialized_db: str) -> None:
        """SRS-120 — kind cannot change after creation."""
        ctx = build_context(initialized_db, "review")
        key = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"}))
        with pytest.raises(McpValidationError) as caught:
            run_update(ctx, UPDATE_TYPE_DEFINITION, {"unique_key": key, "kind": "enum"})
        assert caught.value.error.field == "kind"

    def test_rejects_an_unknown_key(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            run_update(ctx, UPDATE_TYPE_DEFINITION, {"unique_key": MISSING_KEY, "name": "X"})
        assert caught.value.error.field == "unique_key"

    def test_rejects_a_malformed_key(self, initialized_db: str) -> None:
        """SRS-027, SRS-083 — the key must be a UUID."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError):
            run_update(ctx, UPDATE_TYPE_DEFINITION, {"unique_key": "nope", "name": "X"})

    def test_demotes_an_approved_record(self, initialized_db: str) -> None:
        """SRS-082b — changing approved content forces re-review."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        key = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"}))
        with ctx.db.transaction() as conn:
            record = dal.get_type_definition_by_key(conn, key)
            dal.update_status(conn, "TypeDefinitions", record.id, "approved")
        response = run_update(ctx, UPDATE_TYPE_DEFINITION, {"unique_key": key, "name": "Velocity"})
        assert response["result"]["demoted"] == [key]
        with ctx.db.read_only() as conn:
            assert ctx.dal.get_type_definition_by_key(conn, key).status == "pending_review"

    def test_does_not_demote_when_nothing_changed(self, initialized_db: str) -> None:
        """SRS-082b applies to a content change, not to an empty update."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        key = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"}))
        with ctx.db.transaction() as conn:
            record = dal.get_type_definition_by_key(conn, key)
            dal.update_status(conn, "TypeDefinitions", record.id, "approved")
        run_update(ctx, UPDATE_TYPE_DEFINITION, {"unique_key": key})
        with ctx.db.read_only() as conn:
            assert ctx.dal.get_type_definition_by_key(conn, key).status == "approved"

    def test_an_absent_reference_argument_does_not_clear_the_column(
        self, initialized_db: str
    ) -> None:
        """An omitted key means "unchanged", never "set to NULL"."""
        ctx = build_context(initialized_db, "review")
        target = _key(run_create(ctx, TYPE_DEFINITION, {"name": "U8", "kind": "simple_typedef"}))
        parent = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"}))
        child = _key(
            run_create(
                ctx,
                STRUCT_ELEMENT,
                {
                    "struct_type_key": parent,
                    "name": "value",
                    "position": 1,
                    "element_type_key": target,
                },
            )
        )
        run_update(ctx, UPDATE_STRUCT_ELEMENT, {"unique_key": child, "name": "renamed"})
        with ctx.db.read_only() as conn:
            assert ctx.dal.get_struct_element_by_key(conn, child).element_type_id is not None

    def test_resolving_a_reference_resolves_its_issue(self, initialized_db: str) -> None:
        """SRS-036a, LLD-02 §7.2 — the issue follows the reference."""
        ctx = build_context(initialized_db, "review")
        target = _key(run_create(ctx, TYPE_DEFINITION, {"name": "U8", "kind": "simple_typedef"}))
        parent = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"}))
        child = _key(
            run_create(
                ctx, STRUCT_ELEMENT, {"struct_type_key": parent, "name": "value", "position": 1}
            )
        )
        run_update(ctx, UPDATE_STRUCT_ELEMENT, {"unique_key": child, "element_type_key": target})
        with ctx.db.read_only() as conn:
            issues = ctx.dal.query_review_issues(conn, {"artifact_unique_key": child})
        assert [issue.status for issue in issues] == ["resolved"]

    def test_child_update_demotes_the_parent_chain(self, initialized_db: str) -> None:
        """SRS-082b + SRS-035c — the demotion propagates upward."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        parent = _key(run_create(ctx, TYPE_DEFINITION, {"name": "Speed", "kind": "struct"}))
        child = _key(
            run_create(
                ctx, STRUCT_ELEMENT, {"struct_type_key": parent, "name": "value", "position": 1}
            )
        )
        with ctx.db.transaction() as conn:
            dal.update_status(
                conn, "StructElements", dal.get_struct_element_by_key(conn, child).id, "approved"
            )
            dal.update_status(
                conn, "TypeDefinitions", dal.get_type_definition_by_key(conn, parent).id, "approved"
            )
        response = run_update(ctx, UPDATE_STRUCT_ELEMENT, {"unique_key": child, "name": "renamed"})
        assert set(response["result"]["demoted"]) == {child, parent}


# ── Task 10: the query engine ───────────────────────────────────────────────


class TestQueryEngine:
    def test_returns_every_record_without_filters(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": "REQ-A"})
        run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": "REQ-B"})
        response = run_query(ctx, QUERY_SOURCE_REQUIREMENTS, {})
        assert response["result"]["count"] == 2
        assert response["result"]["table"] == "SourceRequirements"

    def test_applies_a_filter(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": "REQ-A"})
        run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": "REQ-B"})
        response = run_query(ctx, QUERY_SOURCE_REQUIREMENTS, {"source_reference": "REQ-B"})
        assert [r["source_reference"] for r in response["result"]["records"]] == ["REQ-B"]

    def test_rejects_an_invalid_filter_value(self, initialized_db: str) -> None:
        """SRS-083 — filter values are validated like any other input."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            run_query(ctx, QUERY_SOURCE_REQUIREMENTS, {"status": "bogus"})
        assert caught.value.error.field == "status"

    def test_rejects_an_unknown_filter(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError):
            run_query(ctx, QUERY_SOURCE_REQUIREMENTS, {"colour": "red"})

    def test_records_are_deterministically_ordered(self, initialized_db: str) -> None:
        """SRS-108 — query output order is stable."""
        ctx = build_context(initialized_db, "review")
        for index in range(5):
            run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": f"REQ-{index}"})
        first = run_query(ctx, QUERY_SOURCE_REQUIREMENTS, {})["result"]["records"]
        second = run_query(ctx, QUERY_SOURCE_REQUIREMENTS, {})["result"]["records"]
        references = [row["source_reference"] for row in first]
        assert references == [row["source_reference"] for row in second]
        assert references == [f"REQ-{index}" for index in range(5)]

    def test_records_omit_the_internal_id(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": "REQ-A"})
        assert "id" not in run_query(ctx, QUERY_SOURCE_REQUIREMENTS, {})["result"]["records"][0]
