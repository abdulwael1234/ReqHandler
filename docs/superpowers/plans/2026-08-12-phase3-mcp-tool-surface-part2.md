# Phase 3 Implementation Plan — Part 2: The Descriptor Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Read Part 1 first:** `docs/superpowers/plans/2026-08-12-phase3-mcp-tool-surface.md` — it carries the Goal, Architecture, Global Constraints and File Structure that apply to every task here, and Tasks 1–6 which these tasks consume.

**Covers:** Tasks 7–10 — the tool context and the three generic engines that execute the create, update and query descriptors.

---

## Task 7: `ToolContext` and engine descriptors

**Files:**
- Create: `src/r210_mcp/tools/context.py`
- Create: `src/r210_mcp/tools/_engine.py`
- Test: `tests/test_r210_mcp/test_tools/test_engine_parts.py`
- Create: `tests/test_r210_mcp/test_tools/__init__.py` (empty)

**Interfaces:**
- Consumes: `DatabaseConnection`, `DataAccessLayer`, `McpValidationError` (Task 1), `validate_*` and `normalize_name` (Task 3), `INITIAL_STATUSES` and `auto_demote_parent_chain` (Task 4).
- Produces:
  - `context.VALID_ADAPTER_MODES: frozenset[str]`
  - `context.ToolContext(db, dal, adapter_mode)` — frozen dataclass
  - `context.build_context(db_path: str, adapter_mode: str = "extraction") -> ToolContext`
  - `_engine.FieldValidator` protocol, `_engine.choice_of(permitted) -> FieldValidator`
  - `_engine.FieldSpec`, `_engine.RefSpec`, `_engine.CreateSpec`, `_engine.UpdateSpec`, `_engine.QuerySpec`
  - `_engine.ARTIFACT_TYPE_FOR_TABLE: dict[str, str]`
  - `_engine.record_to_dict(record) -> dict[str, Any]`
  - `_engine.reject_status_argument(tool, arguments) -> None`
  - `_engine.reject_unknown_arguments(tool, arguments, permitted) -> None`
  - `_engine.collect_fields(tool, fields, arguments, *, require) -> dict[str, Any]`
  - `_engine.initial_status(tool, arguments) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_engine_parts.py`:

```python
"""Development tests for the engine's shared parts (LLD-02 §7, §10)."""

import pytest

from r210_mcp.db.models import SourceRequirementRecord
from r210_mcp.errors import McpValidationError
from r210_mcp.tools._engine import (
    ARTIFACT_TYPE_FOR_TABLE,
    FieldSpec,
    choice_of,
    collect_fields,
    initial_status,
    record_to_dict,
    reject_status_argument,
    reject_unknown_arguments,
)
from r210_mcp.tools.context import VALID_ADAPTER_MODES, ToolContext, build_context
from r210_mcp.validation.common import validate_not_empty


class TestToolContext:
    def test_build_context_defaults_to_extraction(self, initialized_db: str) -> None:
        """SRS-082a — the safe mode is the default."""
        ctx = build_context(initialized_db)
        assert ctx.adapter_mode == "extraction"

    def test_build_context_rejects_an_unknown_mode(self, initialized_db: str) -> None:
        with pytest.raises(ValueError):
            build_context(initialized_db, "administrator")

    def test_both_modes_are_valid(self, initialized_db: str) -> None:
        for mode in VALID_ADAPTER_MODES:
            assert isinstance(build_context(initialized_db, mode), ToolContext)


class TestRejectStatusArgument:
    def test_rejects_status_in_an_update(self) -> None:
        """SRS-091a — status changes only through set_review_status."""
        with pytest.raises(McpValidationError) as caught:
            reject_status_argument("update_type_definition", {"unique_key": "k", "status": "approved"})
        assert caught.value.error.field == "status"
        assert "set_review_status" in caught.value.error.reason
        assert caught.value.error.affected_key == "k"

    def test_allows_arguments_without_status(self) -> None:
        reject_status_argument("update_type_definition", {"unique_key": "k", "name": "X"})


class TestRejectUnknownArguments:
    def test_rejects_an_unrecognised_argument(self) -> None:
        """SRS-083 — an unknown argument is a caller error, not silently dropped."""
        with pytest.raises(McpValidationError) as caught:
            reject_unknown_arguments("create_source_requirement", {"bogus": 1}, frozenset({"name"}))
        assert caught.value.error.field == "bogus"


class TestCollectFields:
    def test_collects_and_validates(self) -> None:
        fields = (FieldSpec(arg="name", column="name", required=True, validator=validate_not_empty),)
        assert collect_fields("t", fields, {"name": "Speed"}, require=True) == {"name": "Speed"}

    def test_missing_required_field_is_rejected(self) -> None:
        """SRS-083 — a required argument that is absent names itself."""
        fields = (FieldSpec(arg="name", column="name", required=True, validator=validate_not_empty),)
        with pytest.raises(McpValidationError) as caught:
            collect_fields("t", fields, {}, require=True)
        assert caught.value.error.field == "name"

    def test_absent_required_field_is_skipped_when_not_requiring(self) -> None:
        """The update path validates only what the caller supplied."""
        fields = (FieldSpec(arg="name", column="name", required=True, validator=validate_not_empty),)
        assert collect_fields("t", fields, {}, require=False) == {}

    def test_maps_the_argument_name_to_the_column_name(self) -> None:
        fields = (FieldSpec(arg="function", column="function_name"),)
        assert collect_fields("t", fields, {"function": "Run"}, require=False) == {
            "function_name": "Run"
        }


class TestChoiceOf:
    def test_accepts_and_rejects(self) -> None:
        validator = choice_of(frozenset({"input", "output"}))
        validator("input", "direction", operation="t")
        with pytest.raises(McpValidationError):
            validator("sideways", "direction", operation="t")


class TestInitialStatus:
    def test_defaults_to_pending_review(self) -> None:
        """SRS-035a — every new record starts in pending_review."""
        assert initial_status("create_type_definition", {}) == "pending_review"

    @pytest.mark.parametrize("value", ["pending_review", "ambiguous", "out_of_scope"])
    def test_accepts_the_three_non_terminal_states(self, value: str) -> None:
        assert initial_status("create_type_definition", {"initial_status": value}) == value

    @pytest.mark.parametrize("value", ["approved", "rejected", "bogus"])
    def test_rejects_a_review_outcome(self, value: str) -> None:
        """SRS-082a — a create tool cannot claim a review outcome."""
        with pytest.raises(McpValidationError) as caught:
            initial_status("create_type_definition", {"initial_status": value})
        assert caught.value.error.field == "initial_status"


class TestRecordToDict:
    def test_expands_a_record(self) -> None:
        record = SourceRequirementRecord(1, "k", "REQ-1", None, "pending_review", None)
        assert record_to_dict(record) == {
            "id": 1,
            "unique_key": "k",
            "source_reference": "REQ-1",
            "source_text": None,
            "status": "pending_review",
            "review_note": None,
        }


class TestArtifactTypeMap:
    def test_inverts_the_model_registry(self) -> None:
        """SRS-074 — every artifact table has one artifact_type name."""
        assert ARTIFACT_TYPE_FOR_TABLE["TypeDefinitions"] == "type_definition"
        assert ARTIFACT_TYPE_FOR_TABLE["PortConnectionMembers"] == "port_connection_member"
        assert "SourceRequirements" not in ARTIFACT_TYPE_FOR_TABLE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_engine_parts.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'r210_mcp.tools.context'`

- [ ] **Step 3: Write minimal implementation**

Create `src/r210_mcp/tools/context.py`:

```python
"""The context every tool handler receives.

LLD-02 §9 makes handlers bound methods of `R210McpServer`. They are functions
over this context instead, so that a handler can be called without the MCP SDK
present — which LLD-06 requires for the Local Review CLI (DEV-26).

See: LLD-02 §9 (MCP Server Entry Point)
"""

from dataclasses import dataclass

from ..db.connection import DatabaseConnection
from ..db.dal import DataAccessLayer

# The adapter's authority, bound at construction time (SRS-082a).
VALID_ADAPTER_MODES = frozenset({"extraction", "review"})


@dataclass(frozen=True)
class ToolContext:
    """Everything a handler needs: a connection factory, the DAL, authority."""

    db: DatabaseConnection
    dal: DataAccessLayer
    adapter_mode: str


def build_context(db_path: str, adapter_mode: str = "extraction") -> ToolContext:
    """Construct a context, defaulting to the mode that cannot approve.

    `ValueError`, not `McpValidationError`: an invalid mode is a wiring error
    at construction time, never caller-supplied tool input.
    """
    if adapter_mode not in VALID_ADAPTER_MODES:
        raise ValueError(f"adapter_mode must be one of {sorted(VALID_ADAPTER_MODES)}")
    return ToolContext(
        db=DatabaseConnection(db_path), dal=DataAccessLayer(), adapter_mode=adapter_mode
    )
```

Create `src/r210_mcp/tools/_engine.py`:

```python
"""Descriptors and shared steps for the regular create/update/query tools.

The 13 creates, 13 updates and 6 queries are one algorithm each, parameterized
by table. Holding that algorithm once means the cross-cutting rules — SRS-091a
status rejection, SRS-082b content demotion, SRS-035c parent demotion — have
exactly one implementation rather than one per tool (DEV-32). This mirrors the
generic core the DAL already uses behind its typed surface (DEV-18).

See: LLD-02 §7 (Tool Handler Implementations), §10 (Update Rules)
"""

from dataclasses import dataclass, fields as dataclass_fields
from typing import Any, Protocol

from ..db.models import ARTIFACT_TYPE_TABLE_MAP
from ..errors import McpValidationError
from ..validation.common import validate_choice
from ..validation.status import INITIAL_STATUSES

# Table → the artifact_type name a ReviewIssue uses to point at it (SRS-074).
ARTIFACT_TYPE_FOR_TABLE: dict[str, str] = {
    table: artifact_type for artifact_type, table in ARTIFACT_TYPE_TABLE_MAP.items()
}


class FieldValidator(Protocol):
    """A common validator, bound to the tool name at call time."""

    def __call__(self, value: Any, field: str, *, operation: str) -> None: ...


def choice_of(permitted: frozenset[str]) -> FieldValidator:
    """Adapt `validate_choice` to the single-value validator shape."""

    def _validate(value: Any, field: str, *, operation: str) -> None:
        validate_choice(value, permitted, field, operation=operation)

    return _validate


@dataclass(frozen=True)
class FieldSpec:
    """One plain column, written from one argument."""

    arg: str
    column: str
    required: bool = False
    validator: FieldValidator | None = None


@dataclass(frozen=True)
class RefSpec:
    """A `*_key` argument resolved to an integer foreign key."""

    arg: str
    column: str
    table: str
    required: bool = False
    parent: bool = False
    may_be_unresolved: bool = False


@dataclass(frozen=True)
class CreateSpec:
    tool: str
    table: str
    fields: tuple[FieldSpec, ...] = ()
    refs: tuple[RefSpec, ...] = ()
    duplicate_name_arg: str | None = None
    duplicate_kind_arg: str | None = None
    has_status: bool = True


@dataclass(frozen=True)
class UpdateSpec:
    tool: str
    table: str
    fields: tuple[FieldSpec, ...] = ()
    refs: tuple[RefSpec, ...] = ()
    immutable_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuerySpec:
    tool: str
    table: str
    filters: tuple[FieldSpec, ...] = ()


def record_to_dict(record: Any) -> dict[str, Any]:
    """Expand a record dataclass into a response payload."""
    return {field.name: getattr(record, field.name) for field in dataclass_fields(record)}


def reject_status_argument(tool: str, arguments: dict[str, Any]) -> None:
    """Reject `status` in an update tool (SRS-091a, LLD-02 §10)."""
    if "status" in arguments:
        raise McpValidationError.of(
            tool,
            "Status cannot be changed through update tools. "
            "Use 'set_review_status' instead (SRS-091a).",
            field="status",
            affected_key=arguments.get("unique_key"),
        )


def reject_unknown_arguments(
    tool: str, arguments: dict[str, Any], permitted: frozenset[str]
) -> None:
    """Reject any argument the tool does not define (SRS-083)."""
    for name in sorted(set(arguments) - permitted):
        raise McpValidationError.of(
            tool,
            f"unknown argument for {tool}: {name}",
            field=name,
            affected_key=arguments.get("unique_key"),
        )


def collect_fields(
    tool: str,
    fields: tuple[FieldSpec, ...],
    arguments: dict[str, Any],
    *,
    require: bool,
) -> dict[str, Any]:
    """Validate the supplied arguments and map them to column names.

    `require=True` on the create path enforces presence; `require=False` on the
    update path validates only what the caller actually supplied.
    """
    values: dict[str, Any] = {}
    for spec in fields:
        if spec.arg not in arguments:
            if require and spec.required:
                raise McpValidationError.of(
                    tool,
                    f"{spec.arg} is required",
                    field=spec.arg,
                    affected_key=arguments.get("unique_key"),
                )
            continue
        value = arguments[spec.arg]
        if spec.validator is not None and not (value is None and not spec.required):
            spec.validator(value, spec.arg, operation=tool)
        values[spec.column] = value
    return values


def initial_status(tool: str, arguments: dict[str, Any]) -> str:
    """The status a create tool assigns (SRS-035a, LLD-02 §7.1).

    Only the three non-terminal states are accepted; `approved` and `rejected`
    are review outcomes that no create tool may claim (SRS-082a).
    """
    value = arguments.get("initial_status")
    if value is None:
        return "pending_review"
    if value not in INITIAL_STATUSES:
        permitted = ", ".join(sorted(INITIAL_STATUSES))
        raise McpValidationError.of(
            tool,
            f"initial_status must be one of: {permitted}",
            field="initial_status",
        )
    return str(value)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_engine_parts.py -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/context.py src/r210_mcp/tools/_engine.py tests/test_r210_mcp/test_tools/
git commit -m "feat(tools): add ToolContext and engine descriptors"
```

---

## Task 8: The create engine

**Files:**
- Modify: `src/r210_mcp/tools/_engine.py`
- Test: `tests/test_r210_mcp/test_tools/test_engine_create.py`

**Interfaces:**
- Consumes: everything from Task 7; `check_for_duplicates` and `duplicate_warning` (Task 5); `auto_demote_parent_chain` (Task 4); `McpResult` from Phase 2; `DataAccessLayer.insert_record`, `.get_record_by_id`, `.get_record_by_unique_key`, `.update_status` (Task 2).
- Produces:
  - `_engine.resolve_refs(conn, dal, tool, refs, arguments) -> tuple[dict[str, Any], list[str], int | None]` — returns (column→id, unresolved column names, parent record id)
  - `_engine.create_unresolved_issue(conn, dal, table, artifact_key, column, source_requirement_id) -> str`
  - `_engine.demote_parent_on_child_creation(conn, dal, child_table, parent_id) -> list[str]`
  - `_engine.run_create(ctx, spec, arguments) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_engine_create.py`:

```python
"""Development tests for the create engine (LLD-02 §7, §10.4)."""

from uuid import UUID

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.tools._engine import CreateSpec, FieldSpec, RefSpec, run_create
from r210_mcp.tools.context import build_context
from r210_mcp.validation.common import validate_not_empty, validate_position

SOURCE_REQUIREMENT = CreateSpec(
    tool="create_source_requirement",
    table="SourceRequirements",
    fields=(
        FieldSpec("source_reference", "source_reference", True, validate_not_empty),
        FieldSpec("source_text", "source_text"),
        FieldSpec("review_note", "review_note"),
    ),
)

ENUM_VALUE = CreateSpec(
    tool="create_enum_value",
    table="EnumValues",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("value", "value"),
        FieldSpec("position", "position", True, validate_position),
        FieldSpec("description", "description"),
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
        RefSpec(
            "element_type_key",
            "element_type_id",
            "TypeDefinitions",
            may_be_unresolved=True,
        ),
    ),
)


class TestCreateEngine:
    def test_inserts_and_returns_a_uuid_key(self, initialized_db: str) -> None:
        """SRS-027 — every referable record carries a generated UUID."""
        ctx = build_context(initialized_db, "review")
        response = run_create(ctx, SOURCE_REQUIREMENT, {"source_reference": "REQ-1"})
        key = response["result"]["unique_key"]
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

    def test_resolves_a_parent_key_to_an_id(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        parent = run_create(
            ctx,
            CreateSpec(tool="t", table="TypeDefinitions", fields=(
                FieldSpec("name", "name", True, validate_not_empty),
                FieldSpec("kind", "kind", True),
            )),
            {"name": "Mode", "kind": "enum"},
        )["result"]["unique_key"]
        response = run_create(
            ctx, ENUM_VALUE, {"enum_type_key": parent, "name": "RED", "position": 1}
        )
        assert response["result"]["name"] == "RED"

    def test_unknown_parent_key_is_rejected(self, initialized_db: str) -> None:
        """SRS-083 — a key that resolves to nothing is a caller error."""
        ctx = build_context(initialized_db, "review")
        missing = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
        with pytest.raises(McpValidationError) as caught:
            run_create(ctx, ENUM_VALUE, {"enum_type_key": missing, "name": "RED", "position": 1})
        assert caught.value.error.field == "enum_type_key"

    def test_unresolved_reference_creates_an_issue(self, initialized_db: str) -> None:
        """SRS-036a — an unresolved type reference is recorded for review."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
            parent_key = "td"
        response = run_create(
            ctx, STRUCT_ELEMENT, {"struct_type_key": parent_key, "name": "value", "position": 1}
        )
        child_key = response["result"]["unique_key"]
        with ctx.db.read_only() as conn:
            issues = dal.query_review_issues(conn, {"artifact_unique_key": child_key})
        assert len(issues) == 1
        assert issues[0].issue_type == "unresolved_reference"
        assert issues[0].artifact_type == "struct_element"
        assert dal.get_record_by_id(conn, "StructElements", parent_id) is not None

    def test_child_creation_demotes_an_approved_parent(self, initialized_db: str) -> None:
        """SRS-035c, LLD-02 §10.4 — a new pending child invalidates approval."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            dal.update_status(conn, "TypeDefinitions", parent_id, "approved")
        response = run_create(
            ctx, ENUM_VALUE, {"enum_type_key": "td", "name": "RED", "position": 1}
        )
        assert response["result"]["demoted"] == ["td"]
        with ctx.db.read_only() as conn:
            assert dal.get_record_by_id(conn, "TypeDefinitions", parent_id).status == (
                "pending_review"
            )

    def test_duplicate_produces_a_warning_and_an_issue(self, initialized_db: str) -> None:
        """SRS-034, SRS-121 — the warning is returned and an issue is created."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        spec = CreateSpec(
            tool="create_type_definition",
            table="TypeDefinitions",
            fields=(
                FieldSpec("name", "name", True, validate_not_empty),
                FieldSpec("kind", "kind", True),
            ),
            duplicate_name_arg="name",
            duplicate_kind_arg="kind",
        )
        run_create(ctx, spec, {"name": "Speed", "kind": "struct"})
        response = run_create(ctx, spec, {"name": "  speed ", "kind": "struct"})
        assert response["result"]["warnings"]
        with ctx.db.read_only() as conn:
            issues = dal.query_review_issues(conn, {"issue_type": "ambiguous"})
        assert len(issues) == 1

    def test_a_failed_insert_leaves_nothing_behind(self, initialized_db: str) -> None:
        """SRS-084 — the whole create is one transaction."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Mode", "enum")
            dal.insert_enum_value(conn, "ev", 1, "RED", None, 1)
        with pytest.raises(Exception):
            run_create(ctx, ENUM_VALUE, {"enum_type_key": "td", "name": "RED", "position": 1})
        with ctx.db.read_only() as conn:
            assert len(dal.query_enum_values(conn, {"name": "RED"})) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_engine_create.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'run_create'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/r210_mcp/tools/_engine.py`, and extend its imports with
`from uuid import uuid4`, `import sqlite3`, `from ..duplicate_detection import check_for_duplicates, duplicate_warning`, `from ..errors import McpResult`, `from ..db.dal import DataAccessLayer`, `from ..db.models import CHILD_PARENT_MAP`, `from ..validation.status import auto_demote_parent_chain`, `from .context import ToolContext`:

```python
def resolve_refs(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    tool: str,
    refs: tuple[RefSpec, ...],
    arguments: dict[str, Any],
) -> tuple[dict[str, Any], list[str], int | None]:
    """Resolve every `*_key` argument to an integer id.

    Returns the column values, the columns left unresolved (SRS-036a), and the
    parent record's id when one of the refs is marked `parent`. A required key
    that is absent or resolves to nothing is a caller error (SRS-083); one of
    the four SRS-036a columns may resolve to NULL and stay unresolved.
    """
    values: dict[str, Any] = {}
    unresolved: list[str] = []
    parent_id: int | None = None

    for spec in refs:
        key = arguments.get(spec.arg)
        if key is None:
            if spec.required:
                raise McpValidationError.of(
                    tool, f"{spec.arg} is required", field=spec.arg
                )
            if spec.may_be_unresolved and spec.arg in arguments:
                values[spec.column] = None
                unresolved.append(spec.column)
            elif spec.arg in arguments:
                values[spec.column] = None
            continue

        record = dal.get_record_by_unique_key(conn, spec.table, key)
        if record is None:
            raise McpValidationError.of(
                tool,
                f"{spec.arg} does not resolve to an existing {spec.table} record",
                field=spec.arg,
                affected_key=str(key),
            )
        values[spec.column] = record.id
        if spec.parent:
            parent_id = int(record.id)

    return values, unresolved, parent_id


def create_unresolved_issue(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    table: str,
    artifact_key: str,
    column: str,
    source_requirement_id: int | None,
) -> str:
    """Record an unresolved type reference for review (SRS-036a).

    A structural subtype row is not an independently reviewable artifact type
    (SRS-035a, SRS-074), so an unresolved `ArrayTypeDefinitions` reference is
    reported against the parent `TypeDefinitions` record (LLD-02 §7.2 step 8).
    """
    issue_key = str(uuid4())
    dal.insert_review_issue(
        conn,
        issue_key,
        source_requirement_id,
        ARTIFACT_TYPE_FOR_TABLE[table],
        artifact_key,
        "unresolved_reference",
        f"{table}.{column} is unresolved; resolve it before approval (SRS-036a).",
    )
    return issue_key


def demote_parent_on_child_creation(
    conn: sqlite3.Connection, dal: DataAccessLayer, child_table: str, parent_id: int
) -> list[str]:
    """Demote an approved parent when a pending child is added (LLD-02 §10.4)."""
    relation = CHILD_PARENT_MAP.get(child_table)
    if relation is None:
        return []
    parent = dal.get_record_by_id(conn, relation.parent_table, parent_id)
    if parent is None:
        return []
    demoted: list[str] = []
    if parent.status == "approved":
        dal.update_status(conn, relation.parent_table, parent_id, "pending_review", None)
        demoted.append(str(parent.unique_key))
    demoted.extend(auto_demote_parent_chain(conn, dal, relation.parent_table, parent_id))
    return demoted


def _permitted_create_arguments(spec: CreateSpec) -> frozenset[str]:
    names = {field.arg for field in spec.fields} | {ref.arg for ref in spec.refs}
    if spec.has_status:
        names.add("initial_status")
    return frozenset(names)


def run_create(ctx: ToolContext, spec: CreateSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a create descriptor (LLD-02 §7).

    Everything runs inside one transaction, reads included: resolving a key and
    then inserting against it in a separate transaction would leave a window in
    which the target disappears (SRS-084).
    """
    reject_unknown_arguments(spec.tool, arguments, _permitted_create_arguments(spec))
    values = collect_fields(spec.tool, spec.fields, arguments, require=True)
    status = initial_status(spec.tool, arguments) if spec.has_status else None
    unique_key = str(uuid4())

    with ctx.db.transaction() as conn:
        ref_values, unresolved, parent_id = resolve_refs(
            conn, ctx.dal, spec.tool, spec.refs, arguments
        )
        row = {"unique_key": unique_key, **values, **ref_values}
        if status is not None:
            row["status"] = status

        warnings: list[str] = []
        duplicates: list[dict[str, str]] = []
        if spec.duplicate_name_arg is not None:
            name = arguments.get(spec.duplicate_name_arg)
            kind = (
                arguments.get(spec.duplicate_kind_arg)
                if spec.duplicate_kind_arg is not None
                else None
            )
            if isinstance(name, str):
                duplicates = check_for_duplicates(conn, ctx.dal, spec.table, name, kind)
                if duplicates:
                    warnings.append(duplicate_warning(spec.table, name, duplicates))

        record_id = ctx.dal.insert_record(conn, spec.table, row)
        source_requirement_id = ref_values.get("source_requirement_id")

        for column in unresolved:
            create_unresolved_issue(
                conn, ctx.dal, spec.table, unique_key, column, source_requirement_id
            )

        if duplicates:
            ctx.dal.insert_review_issue(
                conn,
                str(uuid4()),
                source_requirement_id,
                ARTIFACT_TYPE_FOR_TABLE.get(spec.table),
                unique_key,
                "ambiguous",
                warnings[0],
            )

        demoted: list[str] = []
        if parent_id is not None:
            demoted = demote_parent_on_child_creation(conn, ctx.dal, spec.table, parent_id)

        created = ctx.dal.get_record_by_id(conn, spec.table, record_id)

    data = record_to_dict(created)
    data.pop("id", None)
    data.pop("unique_key", None)
    if demoted:
        data["demoted"] = demoted
    return McpResult(unique_key=unique_key, data=data, warnings=warnings).to_dict()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_tools/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/_engine.py tests/test_r210_mcp/test_tools/test_engine_create.py
git commit -m "feat(tools): add the descriptor-driven create engine"
```

---

## Task 9: The update engine

**Files:**
- Modify: `src/r210_mcp/tools/_engine.py`
- Test: `tests/test_r210_mcp/test_tools/test_engine_update.py`

**Interfaces:**
- Consumes: Task 7 and Task 8 output; `STRUCTURAL_SUBTYPE_TABLES` and `CHILD_PARENT_MAP` from `db.models`.
- Produces:
  - `_engine.demote_if_approved(conn, dal, table, record_id, changed) -> list[str]`
  - `_engine.run_update(ctx, spec, arguments) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_engine_update.py`:

```python
"""Development tests for the update engine (LLD-02 §10)."""

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.tools._engine import FieldSpec, UpdateSpec, run_update
from r210_mcp.tools.context import build_context
from r210_mcp.validation.common import validate_not_empty

TYPE_DEFINITION = UpdateSpec(
    tool="update_type_definition",
    table="TypeDefinitions",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("description", "description"),
    ),
    immutable_args=("kind",),
)

ENUM_VALUE = UpdateSpec(
    tool="update_enum_value",
    table="EnumValues",
    fields=(FieldSpec("name", "name", validator=validate_not_empty),),
)


class TestUpdateEngine:
    def test_updates_a_permitted_field(self, initialized_db: str) -> None:
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Speed", "struct")
        run_update(ctx, TYPE_DEFINITION, {"unique_key": "td", "name": "Velocity"})
        with ctx.db.read_only() as conn:
            assert dal.get_type_definition_by_key(conn, "td").name == "Velocity"

    def test_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a — status is not an updatable field."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Speed", "struct")
        with pytest.raises(McpValidationError) as caught:
            run_update(ctx, TYPE_DEFINITION, {"unique_key": "td", "status": "approved"})
        assert caught.value.error.field == "status"

    def test_rejects_an_immutable_field(self, initialized_db: str) -> None:
        """SRS-120 — kind cannot change after creation."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Speed", "struct")
        with pytest.raises(McpValidationError) as caught:
            run_update(ctx, TYPE_DEFINITION, {"unique_key": "td", "kind": "enum"})
        assert caught.value.error.field == "kind"

    def test_rejects_an_unknown_key(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            run_update(
                ctx,
                TYPE_DEFINITION,
                {"unique_key": "3f2504e0-4f89-41d3-9a0c-0305e82c3301", "name": "X"},
            )
        assert caught.value.error.field == "unique_key"

    def test_demotes_an_approved_record(self, initialized_db: str) -> None:
        """SRS-082b — changing approved content forces re-review."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            record_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
            dal.update_status(conn, "TypeDefinitions", record_id, "approved")
        response = run_update(ctx, TYPE_DEFINITION, {"unique_key": "td", "name": "Velocity"})
        assert "td" in response["result"]["demoted"]
        with ctx.db.read_only() as conn:
            assert dal.get_type_definition_by_key(conn, "td").status == "pending_review"

    def test_does_not_demote_when_nothing_changed(self, initialized_db: str) -> None:
        """SRS-082b applies to a content change, not to an empty update."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            record_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
            dal.update_status(conn, "TypeDefinitions", record_id, "approved")
        run_update(ctx, TYPE_DEFINITION, {"unique_key": "td"})
        with ctx.db.read_only() as conn:
            assert dal.get_type_definition_by_key(conn, "td").status == "approved"

    def test_child_update_demotes_the_parent_chain(self, initialized_db: str) -> None:
        """SRS-082b + SRS-035c — the demotion propagates upward."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
            dal.update_status(conn, "EnumValues", child_id, "approved")
            dal.update_status(conn, "TypeDefinitions", parent_id, "approved")
        response = run_update(ctx, ENUM_VALUE, {"unique_key": "ev", "name": "CRIMSON"})
        assert set(response["result"]["demoted"]) == {"ev", "td"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_engine_update.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'run_update'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/r210_mcp/tools/_engine.py`, extending its model imports with `STRUCTURAL_SUBTYPE_TABLES`:

```python
def demote_if_approved(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    table: str,
    record_id: int,
    changed: dict[str, Any],
) -> list[str]:
    """Demote an approved record whose content changed (SRS-082b, §10.1).

    A structural subtype row has no status of its own (SRS-035a), so its
    change demotes the parent `TypeDefinitions` record instead.
    """
    if not changed:
        return []

    if table in STRUCTURAL_SUBTYPE_TABLES:
        record = dal.get_record_by_id(conn, table, record_id)
        if record is None:
            return []
        parent = dal.get_record_by_id(conn, "TypeDefinitions", record.type_definition_id)
        if parent is None or parent.status != "approved":
            return []
        dal.update_status(conn, "TypeDefinitions", parent.id, "pending_review", None)
        return [str(parent.unique_key)]

    record = dal.get_record_by_id(conn, table, record_id)
    if record is None:
        return []

    demoted: list[str] = []
    if record.status == "approved":
        dal.update_status(conn, table, record_id, "pending_review", None)
        demoted.append(str(record.unique_key))
    if table in CHILD_PARENT_MAP:
        demoted.extend(auto_demote_parent_chain(conn, dal, table, record_id))
    return demoted


def _permitted_update_arguments(spec: UpdateSpec) -> frozenset[str]:
    names = {field.arg for field in spec.fields} | {ref.arg for ref in spec.refs}
    names.add("unique_key")
    return frozenset(names)


def run_update(ctx: ToolContext, spec: UpdateSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute an update descriptor (LLD-02 §10.2)."""
    reject_status_argument(spec.tool, arguments)
    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=spec.tool)

    for name in spec.immutable_args:
        if name in arguments:
            raise McpValidationError.of(
                spec.tool,
                f"{name} cannot be changed after creation (SRS-120)",
                field=name,
                affected_key=str(key),
            )

    reject_unknown_arguments(spec.tool, arguments, _permitted_update_arguments(spec))
    values = collect_fields(spec.tool, spec.fields, arguments, require=False)

    with ctx.db.transaction() as conn:
        record = ctx.dal.get_record_by_unique_key(conn, spec.table, str(key))
        if record is None:
            raise McpValidationError.of(
                spec.tool,
                f"no {spec.table} record with unique_key {key!r}",
                field="unique_key",
                affected_key=str(key),
            )
        ref_values, _unresolved, _parent_id = resolve_refs(
            conn, ctx.dal, spec.tool, spec.refs, arguments
        )
        changed = {**values, **ref_values}
        if changed:
            ctx.dal.update_record(conn, spec.table, record.id, changed)
        demoted = demote_if_approved(conn, ctx.dal, spec.table, record.id, changed)
        updated = ctx.dal.get_record_by_id(conn, spec.table, record.id)

    data = record_to_dict(updated)
    data.pop("id", None)
    data.pop("unique_key", None)
    if demoted:
        data["demoted"] = demoted
    return McpResult(unique_key=str(key), data=data).to_dict()
```

Extend the module's validation import to
`from ..validation.common import validate_choice, validate_uuid_format`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_tools/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/_engine.py tests/test_r210_mcp/test_tools/test_engine_update.py
git commit -m "feat(tools): add the descriptor-driven update engine"
```

---

## Task 10: The query engine

**Files:**
- Modify: `src/r210_mcp/tools/_engine.py`
- Test: `tests/test_r210_mcp/test_tools/test_engine_query.py`

**Interfaces:**
- Consumes: Tasks 7–9.
- Produces: `_engine.run_query(ctx, spec, arguments) -> dict[str, Any]` returning `{"result": {"table": ..., "count": n, "records": [...]}}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_engine_query.py`:

```python
"""Development tests for the query engine (LLD-02 §7.1)."""

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.tools._engine import FieldSpec, QuerySpec, choice_of, run_query
from r210_mcp.tools.context import build_context

STATUSES = frozenset({"pending_review", "approved", "rejected", "ambiguous", "out_of_scope"})

SOURCE_REQUIREMENTS = QuerySpec(
    tool="query_source_requirements",
    table="SourceRequirements",
    filters=(
        FieldSpec("status", "status", validator=choice_of(STATUSES)),
        FieldSpec("source_reference", "source_reference"),
    ),
)


class TestQueryEngine:
    def test_returns_every_record_without_filters(self, initialized_db: str) -> None:
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            dal.insert_source_requirement(conn, "a", "REQ-A")
            dal.insert_source_requirement(conn, "b", "REQ-B")
        response = run_query(ctx, SOURCE_REQUIREMENTS, {})
        assert response["result"]["count"] == 2
        assert [r["unique_key"] for r in response["result"]["records"]] == ["a", "b"]

    def test_applies_a_filter(self, initialized_db: str) -> None:
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            dal.insert_source_requirement(conn, "a", "REQ-A")
            record_id = dal.insert_source_requirement(conn, "b", "REQ-B")
            dal.update_status(conn, "SourceRequirements", record_id, "approved")
        response = run_query(ctx, SOURCE_REQUIREMENTS, {"status": "approved"})
        assert [r["unique_key"] for r in response["result"]["records"]] == ["b"]

    def test_rejects_an_invalid_filter_value(self, initialized_db: str) -> None:
        """SRS-083 — filter values are validated like any other input."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            run_query(ctx, SOURCE_REQUIREMENTS, {"status": "bogus"})
        assert caught.value.error.field == "status"

    def test_rejects_an_unknown_filter(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError):
            run_query(ctx, SOURCE_REQUIREMENTS, {"colour": "red"})

    def test_records_are_deterministically_ordered(self, initialized_db: str) -> None:
        """SRS-108 — query output order is stable."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            for index in range(5):
                dal.insert_source_requirement(conn, f"k{index}", f"REQ-{index}")
        first = [r["unique_key"] for r in run_query(ctx, SOURCE_REQUIREMENTS, {})["result"]["records"]]
        second = [r["unique_key"] for r in run_query(ctx, SOURCE_REQUIREMENTS, {})["result"]["records"]]
        assert first == second == ["k0", "k1", "k2", "k3", "k4"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_engine_query.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'run_query'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/r210_mcp/tools/_engine.py`:

```python
def run_query(ctx: ToolContext, spec: QuerySpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a query descriptor (LLD-02 §7.1).

    Read-only: no transaction is opened. Projection is not applied here — the
    dispatch boundary owns it, so a handler cannot omit it (DEV-30).
    """
    permitted = frozenset({field.arg for field in spec.filters})
    reject_unknown_arguments(spec.tool, arguments, permitted)
    filters = collect_fields(spec.tool, spec.filters, arguments, require=False)

    with ctx.db.read_only() as conn:
        records = ctx.dal.query_table(conn, spec.table, filters or None)

    payload = [record_to_dict(record) for record in records]
    for row in payload:
        row.pop("id", None)
    return {"result": {"table": spec.table, "count": len(payload), "records": payload}}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_tools/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/_engine.py tests/test_r210_mcp/test_tools/test_engine_query.py
git commit -m "feat(tools): add the descriptor-driven query engine"
```

---

**Tasks 11–15 continue in `docs/superpowers/plans/2026-08-12-phase3-mcp-tool-surface-part3.md`.**
