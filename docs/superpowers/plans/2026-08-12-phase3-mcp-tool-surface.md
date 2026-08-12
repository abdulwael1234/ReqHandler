# Phase 3 — MCP Tool Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the validation layer, all 35 MCP tool handlers, and the MCP server adapter on top of the Phase 2 data access layer.

**Architecture:** Tool handlers are module-level functions taking a frozen `ToolContext` (connection factory, DAL, adapter mode) and a plain `dict` of arguments, returning a plain `dict`. The 13 create / 13 update / 6 query tools are driven by frozen descriptors executed by three generic engines in `tools/_engine.py`; four irregular tools are written out explicitly. `tools/registry.py` dispatches by name and is the single boundary where exceptions become error responses and where SRS-015a projection is applied. `server.py` is a thin adapter and the only module importing `mcp`.

**Tech Stack:** Python 3.11+, stdlib `sqlite3`, `uuid`, `dataclasses`, `re`; pytest; ruff; mypy strict. The `mcp` SDK is used only in `server.py` and is not installed in the development environment.

**Spec:** `docs/superpowers/specs/2026-08-12-phase3-mcp-tool-surface-design.md`

## Global Constraints

- Python `>=3.11`. Use PEP 604 unions (`str | None`), never `Optional[...]`.
- `ruff check src tests` must pass. Line length 100. Rules `E`, `F`, `I`, `W`, `UP`.
- `mypy src` under `strict = true` must pass with zero errors.
- `python -m pytest tests/ -q -p no:cacheprovider` must pass. The `-p no:cacheprovider` flag is required on this machine, which denies `.pytest_cache` creation.
- Tests import from `src/` via `pythonpath = ["src"]` in `pyproject.toml`. No install step needed.
- Every source module docstring ends with a `See: LLD-02 §<n>` line. Every test docstring cites the `SRS-<nnn>` it verifies. This is the repository's traceability convention.
- No `DELETE` statement anywhere (SRS-091). No import of `r210_db_init` from `r210_mcp` (SRS-093).
- `import mcp` appears in exactly one file: `src/r210_mcp/server.py`.
- Never edit `migrations/v001_initial_schema.py`. The schema is fixed for this phase.
- Records returned by the DAL are frozen dataclasses. Use attribute access (`record.status`), never subscripting.
- Tests use the existing `initialized_db` fixture from `tests/conftest.py`.

---

## File Structure

**New source files**

| File | Responsibility |
|---|---|
| `src/r210_mcp/validation/common.py` | Field-level validators and name normalization |
| `src/r210_mcp/validation/status.py` | Transition matrices, parent approval, demotion chain, reference resolution |
| `src/r210_mcp/validation/type_definitions.py` | Kind values, subtype/kind matching, kind immutability |
| `src/r210_mcp/validation/port_interfaces.py` | Interface type, child-type matching, direction |
| `src/r210_mcp/validation/port_connections.py` | Member existence, duplicates, cardinality, SRS-125 fallback |
| `src/r210_mcp/duplicate_detection.py` | Normalized duplicate comparison |
| `src/r210_mcp/projection.py` | `GEMINI_PROJECTION` allowlist and `project()` |
| `src/r210_mcp/tools/context.py` | `ToolContext` frozen dataclass |
| `src/r210_mcp/tools/_engine.py` | Descriptors and the create/update/query engines |
| `src/r210_mcp/tools/registry.py` | Name→handler dispatch, error boundary, projection boundary |

**Modified source files**

| File | Change |
|---|---|
| `src/r210_mcp/errors.py` | Add `McpValidationError` |
| `src/r210_mcp/db/dal.py` | Add six methods (§Task 2) |
| `src/r210_mcp/tools/{source_requirements,type_definitions,port_interfaces,port_prototypes,port_connections,review_issues,review_status,reference,generation}.py` | Replace docstring stubs with handlers |
| `src/r210_mcp/server.py` | Replace docstring stub with the MCP adapter |

**Test files** mirror the source under `tests/test_r210_mcp/test_validation/` and `tests/test_r210_mcp/test_tools/`, plus `tests/test_r210_mcp/test_cross_cutting.py` for the parametrized rule suites.

---

## Task 1: `McpValidationError`

**Files:**
- Modify: `src/r210_mcp/errors.py`
- Test: `tests/test_r210_mcp/test_errors.py`

**Interfaces:**
- Consumes: `McpError` from Phase 2.
- Produces: `McpValidationError(error: McpError)` with attribute `.error`, and classmethod `McpValidationError.of(operation, reason, *, field=None, affected_key=None) -> McpValidationError`. Every later task raises this.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_r210_mcp/test_errors.py`:

```python
class TestMcpValidationError:
    def test_carries_the_structured_payload(self) -> None:
        """SRS-109 — the exception must expose operation, field, reason, key."""
        exc = McpValidationError.of(
            "create_type_definition",
            "name must not be empty",
            field="name",
            affected_key="abc",
        )
        assert exc.error.operation == "create_type_definition"
        assert exc.error.field == "name"
        assert exc.error.reason == "name must not be empty"
        assert exc.error.affected_key == "abc"
        assert exc.error.to_dict()["error"]["reason"] == "name must not be empty"

    def test_str_is_the_reason(self) -> None:
        exc = McpValidationError.of("update_enum_value", "position must be >= 1")
        assert str(exc) == "position must be >= 1"

    def test_is_an_exception(self) -> None:
        with pytest.raises(McpValidationError):
            raise McpValidationError.of("resolve_reference", "not found")
```

Add `import pytest` and extend the existing import to `from r210_mcp.errors import McpError, McpResult, McpValidationError`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_errors.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'McpValidationError'`

- [ ] **Step 3: Write minimal implementation**

Append to `src/r210_mcp/errors.py`:

```python
class McpValidationError(Exception):
    """Raised by the validation layer and tool handlers (LLD-02 §6).

    Carries a fully-formed `McpError` so the dispatch boundary can serialize it
    without reconstructing context it does not have. LLD-02 §6 raises this type
    throughout but never defines it (DEV-25).
    """

    def __init__(self, error: McpError) -> None:
        super().__init__(error.reason)
        self.error = error

    @classmethod
    def of(
        cls,
        operation: str,
        reason: str,
        *,
        field: str | None = None,
        affected_key: str | None = None,
    ) -> "McpValidationError":
        return cls(
            McpError(operation=operation, field=field, reason=reason, affected_key=affected_key)
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_r210_mcp/test_errors.py -q -p no:cacheprovider`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/errors.py tests/test_r210_mcp/test_errors.py
git commit -m "feat: add McpValidationError for the validation layer"
```

---

## Task 2: DAL graph and generic methods

**Files:**
- Modify: `src/r210_mcp/db/dal.py`
- Test: `tests/test_r210_mcp/test_dal.py`

**Interfaces:**
- Consumes: `_get_by`, `_query`, `_insert`, `_update`, `_check_table`, `_select_list`, `_order_by`, `_reject_unknown`, `TABLE_COLUMNS`, `TABLE_RECORD_MAP`, `CHILD_PARENT_MAP` — all existing.
- Produces, on `DataAccessLayer`:
  - `get_record_by_id(conn, table: str, record_id: int) -> Any`
  - `get_parent_record(conn, child_table: str, child_id: int) -> tuple[str, Any] | None`
  - `get_children(conn, child_table: str, fk_column: str, parent_id: int) -> list[Any]`
  - `query_table(conn, table: str, filters: dict[str, Any] | None = None) -> list[Any]`
  - `insert_record(conn, table: str, values: dict[str, Any]) -> int`
  - `update_record(conn, table: str, record_id: int, values: dict[str, Any]) -> None`

The last two are not named by the LLD; the generic engine needs them, so DEV-28 covers six methods rather than the four the LLD calls.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_r210_mcp/test_dal.py`:

```python
class TestGraphAndGenericMethods:
    def test_get_record_by_id_round_trips(self, initialized_db: str) -> None:
        """SRS-026 — records are addressable by their integer primary key."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            record_id = dal.insert_source_requirement(conn, "k1", "REQ-1")
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "SourceRequirements", record_id)
        assert record.unique_key == "k1"

    def test_get_record_by_id_returns_none_when_absent(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.read_only() as conn:
            assert dal.get_record_by_id(conn, "SourceRequirements", 9999) is None

    def test_get_parent_record_resolves_the_relation(self, initialized_db: str) -> None:
        """SRS-035c — the demotion chain needs child → parent navigation."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Colour", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
        with db.read_only() as conn:
            found = dal.get_parent_record(conn, "EnumValues", child_id)
        assert found is not None
        table, parent = found
        assert table == "TypeDefinitions"
        assert parent.unique_key == "td"

    def test_get_parent_record_returns_none_for_a_root_table(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            record_id = dal.insert_type_definition(conn, "td2", "Speed", "struct")
        with db.read_only() as conn:
            assert dal.get_parent_record(conn, "TypeDefinitions", record_id) is None

    def test_get_children_is_position_ordered(self, initialized_db: str) -> None:
        """SRS-037, SRS-108 — children come back in declaration order."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td3", "Mode", "enum")
            dal.insert_enum_value(conn, "b", parent_id, "B", None, 2)
            dal.insert_enum_value(conn, "a", parent_id, "A", None, 1)
        with db.read_only() as conn:
            children = dal.get_children(conn, "EnumValues", "enum_type_id", parent_id)
        assert [c.unique_key for c in children] == ["a", "b"]

    def test_query_table_applies_filters(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            dal.insert_source_requirement(conn, "q1", "REQ-A")
            dal.insert_source_requirement(conn, "q2", "REQ-B")
        with db.read_only() as conn:
            rows = dal.query_table(conn, "SourceRequirements", {"source_reference": "REQ-B"})
        assert [r.unique_key for r in rows] == ["q2"]

    def test_insert_and_update_record_are_generic(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            record_id = dal.insert_record(
                conn, "SourceRequirements", {"unique_key": "g1", "source_reference": "REQ-G"}
            )
            dal.update_record(conn, "SourceRequirements", record_id, {"source_text": "body"})
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "SourceRequirements", record_id)
        assert record.source_text == "body"

    def test_generic_methods_reject_an_unknown_table(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.read_only() as conn:
            with pytest.raises(ValueError):
                dal.query_table(conn, "Nonexistent", None)
            with pytest.raises(ValueError):
                dal.insert_record(conn, "schema_version", {"version": 9})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_dal.py::TestGraphAndGenericMethods -q -p no:cacheprovider`
Expected: FAIL with `AttributeError: 'DataAccessLayer' object has no attribute 'get_record_by_id'`

- [ ] **Step 3: Write minimal implementation**

Add to the cross-cutting section of `src/r210_mcp/db/dal.py`, after `resolve_unique_key`:

```python
    def get_record_by_id(self, conn: sqlite3.Connection, table: str, record_id: int) -> Any:
        """Fetch by primary key from a table named at runtime (LLD-02 §10.1)."""
        self._check_table(table)
        return self._get_by(conn, TABLE_RECORD_MAP[table], "id", record_id)

    def get_parent_record(
        self, conn: sqlite3.Connection, child_table: str, child_id: int
    ) -> tuple[str, Any] | None:
        """Resolve a child's parent as (table, record), or None at the root.

        Drives the SRS-035c demotion chain. Returns None when the table has no
        parent, when the child is missing, or when the FK is NULL.
        """
        relation = CHILD_PARENT_MAP.get(child_table)
        if relation is None:
            return None
        child = self.get_record_by_id(conn, child_table, child_id)
        if child is None:
            return None
        parent_id = getattr(child, relation.fk_column)
        if parent_id is None:
            return None
        parent = self.get_record_by_id(conn, relation.parent_table, parent_id)
        if parent is None:
            return None
        return relation.parent_table, parent

    def get_children(
        self, conn: sqlite3.Connection, child_table: str, fk_column: str, parent_id: int
    ) -> list[Any]:
        """All children of one parent, in deterministic order (SRS-108)."""
        self._check_table(child_table)
        self._reject_unknown(child_table, {fk_column}, TABLE_COLUMNS[child_table])
        rows = conn.execute(
            f'SELECT {self._select_list(child_table)} FROM "{child_table}"'
            f' WHERE "{fk_column}" = ? ORDER BY {self._order_by(child_table)}',
            (parent_id,),
        ).fetchall()
        record_type = TABLE_RECORD_MAP[child_table]
        return [self._to_record(record_type, row) for row in rows]

    def query_table(
        self, conn: sqlite3.Connection, table: str, filters: dict[str, Any] | None = None
    ) -> list[Any]:
        """Query a table named at runtime (LLD-02 §9)."""
        self._check_table(table)
        return self._query(conn, TABLE_RECORD_MAP[table], filters)

    def insert_record(
        self, conn: sqlite3.Connection, table: str, values: dict[str, Any]
    ) -> int:
        """Insert into a table named at runtime, for the descriptor engine."""
        self._check_table(table)
        return self._insert(conn, TABLE_RECORD_MAP[table], values)

    def update_record(
        self, conn: sqlite3.Connection, table: str, record_id: int, values: dict[str, Any]
    ) -> None:
        """Update a table named at runtime, for the descriptor engine."""
        self._check_table(table)
        self._update(conn, TABLE_RECORD_MAP[table], record_id, values)
```

Extend the existing `from .models import (...)` block with `CHILD_PARENT_MAP` if it is not already imported (it is — it backs `_order_by`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_dal.py -q -p no:cacheprovider && python -m mypy src`
Expected: PASS, and mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/db/dal.py tests/test_r210_mcp/test_dal.py
git commit -m "feat(dal): add graph navigation and generic table methods"
```

---

## Task 3: `validation/common.py`

**Files:**
- Create: `src/r210_mcp/validation/common.py` (replaces the stub docstring file)
- Test: `tests/test_r210_mcp/test_validation/test_common.py`
- Create: `tests/test_r210_mcp/test_validation/__init__.py` (empty)

**Interfaces:**
- Consumes: `McpValidationError` (Task 1), `ARTIFACT_TYPE_TABLE_MAP` from `db.models`.
- Produces — every validator takes `operation` because `McpError` requires it; the LLD's signatures omit it and therefore cannot build a complete SRS-109 error:
  - `validate_not_empty(value: Any, field: str, *, operation: str, affected_key: str | None = None) -> None`
  - `validate_uuid_format(value: Any, field: str, *, operation: str, affected_key: str | None = None) -> None`
  - `validate_choice(value: Any, permitted: frozenset[str], field: str, *, operation: str, affected_key: str | None = None) -> None`
  - `validate_position(value: Any, field: str, *, operation: str, affected_key: str | None = None) -> None`
  - `validate_positive_int(value: Any, field: str, *, operation: str, affected_key: str | None = None) -> None`
  - `validate_artifact_type(value: str | None, field: str, *, operation: str, affected_key: str | None = None) -> None`
  - `normalize_name(name: str) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_validation/test_common.py`:

```python
"""Development tests for the common validators (LLD-02 §6.1)."""

import pytest

from r210_mcp.errors import McpValidationError
from r210_mcp.validation.common import (
    normalize_name,
    validate_artifact_type,
    validate_choice,
    validate_not_empty,
    validate_position,
    validate_positive_int,
    validate_uuid_format,
)

VALID_UUID = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"


class TestValidateNotEmpty:
    def test_accepts_a_non_empty_string(self) -> None:
        validate_not_empty("x", "name", operation="create_type_definition")

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_rejects_empty_values(self, value: object) -> None:
        """SRS-083 — invalid input names the field and the reason."""
        with pytest.raises(McpValidationError) as caught:
            validate_not_empty(value, "name", operation="create_type_definition")
        assert caught.value.error.field == "name"
        assert caught.value.error.operation == "create_type_definition"


class TestValidateUuidFormat:
    def test_accepts_a_uuid(self) -> None:
        validate_uuid_format(VALID_UUID, "unique_key", operation="update_source_requirement")

    @pytest.mark.parametrize("value", ["not-a-uuid", "", None, 42])
    def test_rejects_a_non_uuid(self, value: object) -> None:
        """SRS-027, SRS-083 — keys are UUIDs and malformed keys are rejected."""
        with pytest.raises(McpValidationError):
            validate_uuid_format(value, "unique_key", operation="update_source_requirement")


class TestValidateChoice:
    def test_accepts_a_permitted_value(self) -> None:
        validate_choice("struct", frozenset({"struct", "enum"}), "kind", operation="t")

    def test_rejects_and_lists_the_permitted_values(self) -> None:
        """SRS-083 — the reason tells the caller what was permitted."""
        with pytest.raises(McpValidationError) as caught:
            validate_choice("bogus", frozenset({"struct", "enum"}), "kind", operation="t")
        assert "enum" in caught.value.error.reason
        assert "struct" in caught.value.error.reason


class TestValidatePosition:
    @pytest.mark.parametrize("value", [1, 2, 100])
    def test_accepts_a_positive_integer(self, value: int) -> None:
        validate_position(value, "position", operation="create_enum_value")

    @pytest.mark.parametrize("value", [0, -1, "1", 1.5, None, True])
    def test_rejects_anything_else(self, value: object) -> None:
        """SRS-038b — position is an integer >= 1. bool is not an int here."""
        with pytest.raises(McpValidationError):
            validate_position(value, "position", operation="create_enum_value")


class TestValidatePositiveInt:
    def test_accepts_one(self) -> None:
        validate_positive_int(1, "array_size", operation="create_type_definition")

    @pytest.mark.parametrize("value", [0, -3, None, "2"])
    def test_rejects_anything_else(self, value: object) -> None:
        """SRS-038b — array_size is an integer >= 1."""
        with pytest.raises(McpValidationError):
            validate_positive_int(value, "array_size", operation="create_type_definition")


class TestValidateArtifactType:
    def test_accepts_none(self) -> None:
        validate_artifact_type(None, "artifact_type", operation="create_review_issue")

    def test_accepts_each_permitted_type(self) -> None:
        """SRS-074 — the eleven typed artifact references."""
        for value in ["type_definition", "enum_value", "port_connection_member"]:
            validate_artifact_type(value, "artifact_type", operation="create_review_issue")

    def test_rejects_an_unknown_type(self) -> None:
        with pytest.raises(McpValidationError):
            validate_artifact_type("widget", "artifact_type", operation="create_review_issue")


class TestNormalizeName:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("  Speed  ", "speed"),
            ("Vehicle   Speed", "vehicle speed"),
            ("VEHICLE\tSPEED", "vehicle speed"),
            ("Vehicle\n Speed", "vehicle speed"),
            ("speed", "speed"),
        ],
    )
    def test_trims_collapses_and_lowercases(self, raw: str, expected: str) -> None:
        """SRS-034 — trim, collapse internal whitespace, compare case-insensitively."""
        assert normalize_name(raw) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_validation/test_common.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'normalize_name'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/validation/common.py`:

```python
"""Shared field validators and name normalization.

Every validator takes the `operation` (tool) name because `McpError` requires
it — SRS-109 mandates that an error identify the failing operation, and a
validator that does not receive the tool name cannot build one. LLD-02 §6.1
omits the parameter (DEV-34).

See: LLD-02 §6.1 (Common Validators — SRS-083)
"""

import re
from typing import Any
from uuid import UUID

from ..db.models import ARTIFACT_TYPE_TABLE_MAP
from ..errors import McpValidationError

_WHITESPACE = re.compile(r"\s+")


def _fail(operation: str, field: str, reason: str, affected_key: str | None) -> None:
    raise McpValidationError.of(operation, reason, field=field, affected_key=affected_key)


def validate_not_empty(
    value: Any, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject None, a non-string, or a string that is empty after stripping."""
    if not isinstance(value, str) or not value.strip():
        _fail(operation, field, f"{field} must be a non-empty string", affected_key)


def validate_uuid_format(
    value: Any, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject anything that is not a UUID string (SRS-027)."""
    if not isinstance(value, str):
        _fail(operation, field, f"{field} must be a UUID string", affected_key)
        return
    try:
        UUID(value)
    except ValueError:
        _fail(operation, field, f"{field} is not a valid UUID: {value!r}", affected_key)


def validate_choice(
    value: Any,
    permitted: frozenset[str],
    field: str,
    *,
    operation: str,
    affected_key: str | None = None,
) -> None:
    """Reject a value outside the permitted set, naming the permitted values."""
    if value not in permitted:
        allowed = ", ".join(sorted(permitted))
        _fail(operation, field, f"{field} must be one of: {allowed}", affected_key)


def _is_int(value: Any) -> bool:
    # bool is a subclass of int; True is not a position.
    return isinstance(value, int) and not isinstance(value, bool)


def validate_position(
    value: Any, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject a position that is not an integer >= 1 (SRS-038b)."""
    if not _is_int(value) or value < 1:
        _fail(operation, field, f"{field} must be an integer >= 1", affected_key)


def validate_positive_int(
    value: Any, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject a size that is not an integer >= 1 (SRS-038b)."""
    if not _is_int(value) or value < 1:
        _fail(operation, field, f"{field} must be an integer >= 1", affected_key)


def validate_artifact_type(
    value: str | None, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject an artifact_type outside the eleven permitted values (SRS-074)."""
    if value is None:
        return
    if value not in ARTIFACT_TYPE_TABLE_MAP:
        allowed = ", ".join(sorted(ARTIFACT_TYPE_TABLE_MAP))
        _fail(operation, field, f"{field} must be one of: {allowed}", affected_key)


def normalize_name(name: str) -> str:
    """Trim, collapse internal whitespace, lowercase (SRS-034)."""
    return _WHITESPACE.sub(" ", name.strip()).lower()
```

Create `tests/test_r210_mcp/test_validation/__init__.py` as an empty file.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_validation/test_common.py -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff `All checks passed!`, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/validation/common.py tests/test_r210_mcp/test_validation/
git commit -m "feat(validation): add common field validators and name normalization"
```

---

## Task 4: `validation/status.py`

**Files:**
- Create: `src/r210_mcp/validation/status.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_validation/test_status.py`

**Interfaces:**
- Consumes: `ARTIFACT_TRANSITIONS`, `ISSUE_TRANSITIONS`, `PARENT_CHILD_MAP`, `CHILD_PARENT_MAP` from `db.models`; `DataAccessLayer.get_children_statuses`, `.get_parent_record`, `.update_status`, `.get_record_by_id`, `.get_children` (Task 2); `McpValidationError` (Task 1).
- Produces:
  - `INITIAL_STATUSES: frozenset[str]` — `{"pending_review", "ambiguous", "out_of_scope"}`
  - `UNRESOLVED_REFERENCE_COLUMNS: dict[str, str]` — the four SRS-036a columns
  - `validate_artifact_transition(current, requested, *, operation, affected_key=None) -> None`
  - `validate_issue_transition(current, requested, *, operation, affected_key=None) -> None`
  - `check_parent_can_be_approved(conn, dal, parent_table, parent_id) -> list[dict[str, str]]`
  - `auto_demote_parent_chain(conn, dal, child_table, child_id) -> list[str]`
  - `check_references_resolved(conn, dal, table, record) -> list[str]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_validation/test_status.py`:

```python
"""Development tests for the status rules (LLD-02 §6.2)."""

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.validation.status import (
    auto_demote_parent_chain,
    check_parent_can_be_approved,
    check_references_resolved,
    validate_artifact_transition,
    validate_issue_transition,
)


class TestTransitions:
    @pytest.mark.parametrize(
        ("current", "requested"),
        [
            ("pending_review", "approved"),
            ("pending_review", "out_of_scope"),
            ("approved", "pending_review"),
            ("approved", "rejected"),
            ("rejected", "pending_review"),
            ("ambiguous", "approved"),
            ("out_of_scope", "pending_review"),
        ],
    )
    def test_permitted_transitions_are_accepted(self, current: str, requested: str) -> None:
        """SRS-035b — the permitted artifact transition matrix."""
        validate_artifact_transition(current, requested, operation="set_review_status")

    @pytest.mark.parametrize(
        ("current", "requested"),
        [
            ("approved", "ambiguous"),
            ("approved", "out_of_scope"),
            ("rejected", "approved"),
            ("out_of_scope", "approved"),
            ("pending_review", "pending_review"),
        ],
    )
    def test_forbidden_transitions_are_rejected(self, current: str, requested: str) -> None:
        """SRS-035b — no transition outside the matrix is permitted."""
        with pytest.raises(McpValidationError) as caught:
            validate_artifact_transition(current, requested, operation="set_review_status")
        assert caught.value.error.field == "new_status"

    def test_issue_transitions_follow_their_own_matrix(self) -> None:
        """SRS-035b — issues use pending/resolved/rejected."""
        validate_issue_transition("pending", "resolved", operation="update_review_issue")
        with pytest.raises(McpValidationError):
            validate_issue_transition("resolved", "rejected", operation="update_review_issue")


class TestParentApproval:
    def test_pending_child_blocks_the_parent(self, initialized_db: str) -> None:
        """SRS-046, SRS-053 — a parent cannot be approved over a pending child."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
        with db.read_only() as conn:
            blockers = check_parent_can_be_approved(conn, dal, "TypeDefinitions", parent_id)
        assert len(blockers) == 1
        assert blockers[0]["child_table"] == "EnumValues"
        assert blockers[0]["status"] == "pending_review"

    def test_rejected_child_does_not_block(self, initialized_db: str) -> None:
        """SRS-092a — rejected children are excluded from the evaluation."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
            dal.update_status(conn, "EnumValues", child_id, "rejected")
        with db.read_only() as conn:
            assert check_parent_can_be_approved(conn, dal, "TypeDefinitions", parent_id) == []

    def test_all_children_approved_is_clear(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
            dal.update_status(conn, "EnumValues", child_id, "approved")
        with db.read_only() as conn:
            assert check_parent_can_be_approved(conn, dal, "TypeDefinitions", parent_id) == []

    def test_a_childless_parent_is_clear(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_port_connection(conn, "pc")
        with db.read_only() as conn:
            assert check_parent_can_be_approved(conn, dal, "PortConnections", parent_id) == []


class TestDemotionChain:
    def test_demotes_an_approved_parent(self, initialized_db: str) -> None:
        """SRS-035c — an approved parent is demoted when a child changes."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
            dal.update_status(conn, "TypeDefinitions", parent_id, "approved")
        with db.transaction() as conn:
            demoted = auto_demote_parent_chain(conn, dal, "EnumValues", child_id)
        assert demoted == ["td"]
        with db.read_only() as conn:
            assert dal.get_record_by_id(conn, "TypeDefinitions", parent_id).status == (
                "pending_review"
            )

    def test_walks_the_grandparent_chain(self, initialized_db: str) -> None:
        """SRS-035c — OperationArguments -> Operation -> PortInterface."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            iface_id = dal.insert_port_interface(conn, "pi", "Iface", "client_server")
            op_id = dal.insert_client_server_operation(conn, "op", iface_id, "Get", 1)
            arg_id = dal.insert_operation_argument(conn, "arg", op_id, "a", None, "input", 1)
            dal.update_status(conn, "ClientServerOperations", op_id, "approved")
            dal.update_status(conn, "PortInterfaces", iface_id, "approved")
        with db.transaction() as conn:
            demoted = auto_demote_parent_chain(conn, dal, "OperationArguments", arg_id)
        assert demoted == ["op", "pi"]

    def test_leaves_a_non_approved_parent_alone(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
        with db.transaction() as conn:
            assert auto_demote_parent_chain(conn, dal, "EnumValues", child_id) == []


class TestReferencesResolved:
    def test_unresolved_struct_element_reference_is_reported(self, initialized_db: str) -> None:
        """SRS-036a — a record with an unresolved reference cannot be approved."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
            child_id = dal.insert_struct_element(conn, "se", parent_id, "value", None, 1)
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "StructElements", child_id)
            unresolved = check_references_resolved(conn, dal, "StructElements", record)
        assert unresolved == ["element_type_id"]

    def test_resolved_reference_is_clear(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            target_id = dal.insert_type_definition(conn, "t", "U8", "simple_typedef")
            parent_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
            child_id = dal.insert_struct_element(conn, "se", parent_id, "value", target_id, 1)
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "StructElements", child_id)
            assert check_references_resolved(conn, dal, "StructElements", record) == []

    def test_array_parent_inherits_its_subtype_reference(self, initialized_db: str) -> None:
        """SRS-036a — approving an array TypeDefinition checks its detail row."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Buffer", "array")
            dal.insert_array_type_definition(conn, "at", parent_id, None, 8)
        with db.read_only() as conn:
            record = dal.get_record_by_id(conn, "TypeDefinitions", parent_id)
            unresolved = check_references_resolved(conn, dal, "TypeDefinitions", record)
        assert unresolved == ["element_type_id"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_validation/test_status.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'auto_demote_parent_chain'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/validation/status.py`:

```python
"""Status transition rules, parent-approval blocking, and demotion.

See: LLD-02 §6.2 (Status Validators), §3.5 (Parent-Child Registry)
"""

import sqlite3
from typing import Any

from ..db.dal import DataAccessLayer
from ..db.models import (
    ARTIFACT_TRANSITIONS,
    CHILD_PARENT_MAP,
    ISSUE_TRANSITIONS,
    PARENT_CHILD_MAP,
)
from ..errors import McpValidationError

# Statuses a create tool may assign. Approval and rejection are review
# outcomes, not creation-time claims (SRS-035a, LLD-02 §7.1).
INITIAL_STATUSES = frozenset({"pending_review", "ambiguous", "out_of_scope"})

# The four cross-artifact type references SRS-036a allows to stay NULL. A
# record holding one of these unresolved may not be approved or exported.
UNRESOLVED_REFERENCE_COLUMNS: dict[str, str] = {
    "ArrayTypeDefinitions": "element_type_id",
    "StructElements": "element_type_id",
    "InterfaceDataElements": "type_definition_id",
    "OperationArguments": "type_definition_id",
}


def _validate_transition(
    matrix: dict[str, frozenset[str]],
    current: str,
    requested: str,
    operation: str,
    affected_key: str | None,
) -> None:
    if requested not in matrix.get(current, frozenset()):
        permitted = ", ".join(sorted(matrix.get(current, frozenset()))) or "(none)"
        raise McpValidationError.of(
            operation,
            f"transition {current!r} -> {requested!r} is not permitted; "
            f"permitted from {current!r}: {permitted}",
            field="new_status",
            affected_key=affected_key,
        )


def validate_artifact_transition(
    current: str, requested: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject a transition outside the artifact matrix (SRS-035b)."""
    _validate_transition(ARTIFACT_TRANSITIONS, current, requested, operation, affected_key)


def validate_issue_transition(
    current: str, requested: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject a transition outside the review-issue matrix (SRS-035b)."""
    _validate_transition(ISSUE_TRANSITIONS, current, requested, operation, affected_key)


def check_parent_can_be_approved(
    conn: sqlite3.Connection, dal: DataAccessLayer, parent_table: str, parent_id: int
) -> list[dict[str, str]]:
    """Children blocking approval of this parent (SRS-046, SRS-053).

    Rejected children are excluded — an incorrectly extracted child must not
    permanently block its parent (SRS-092a).
    """
    blockers: list[dict[str, str]] = []
    for relation in PARENT_CHILD_MAP.get(parent_table, []):
        statuses = dal.get_children_statuses(
            conn, relation.child_table, relation.fk_column, parent_id
        )
        for status in statuses:
            if status not in ("approved", "rejected"):
                blockers.append({"child_table": relation.child_table, "status": status})
    return blockers


def auto_demote_parent_chain(
    conn: sqlite3.Connection, dal: DataAccessLayer, child_table: str, child_id: int
) -> list[str]:
    """Demote every approved ancestor to pending_review (SRS-035c).

    Walks the whole chain rather than stopping at the first non-approved
    ancestor: a grandparent may be approved while the parent is not.
    Returns the demoted unique_keys, for reporting in the tool response.
    """
    demoted: list[str] = []
    current_table, current_id = child_table, child_id
    while current_table in CHILD_PARENT_MAP:
        found = dal.get_parent_record(conn, current_table, current_id)
        if found is None:
            break
        parent_table, parent = found
        if parent.status == "approved":
            dal.update_status(conn, parent_table, parent.id, "pending_review", None)
            demoted.append(parent.unique_key)
        current_table, current_id = parent_table, parent.id
    return demoted


def check_references_resolved(
    conn: sqlite3.Connection, dal: DataAccessLayer, table: str, record: Any
) -> list[str]:
    """Columns still NULL that SRS-036a requires resolved before approval.

    A `TypeDefinitions` record of kind `array` carries its reference on the
    `ArrayTypeDefinitions` detail row, which is not independently reviewable
    (SRS-035a), so approving the parent checks the child's column.
    """
    column = UNRESOLVED_REFERENCE_COLUMNS.get(table)
    if column is not None:
        return [column] if getattr(record, column) is None else []

    if table == "TypeDefinitions" and record.kind == "array":
        detail = dal.get_array_type_definition_by_parent(conn, record.id)
        if detail is not None and detail.element_type_id is None:
            return ["element_type_id"]
    return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_validation/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/validation/status.py tests/test_r210_mcp/test_validation/test_status.py
git commit -m "feat(validation): add transitions, parent approval, and demotion chain"
```

---

## Task 5: `duplicate_detection.py`

**Files:**
- Create: `src/r210_mcp/duplicate_detection.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_duplicate_detection.py`

**Interfaces:**
- Consumes: `normalize_name` (Task 3), `DataAccessLayer.find_duplicates_by_name`.
- Produces:
  - `check_for_duplicates(conn, dal, table: str, name: str, kind: str | None = None) -> list[dict[str, str]]` — each entry `{"unique_key": ..., "name": ...}`
  - `duplicate_warning(table: str, name: str, matches: list[dict[str, str]]) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_duplicate_detection.py`:

```python
"""Development tests for duplicate detection (LLD-02 §8)."""

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.duplicate_detection import check_for_duplicates, duplicate_warning


class TestCheckForDuplicates:
    def test_matches_ignoring_case(self, initialized_db: str) -> None:
        """SRS-034 — comparison is case-insensitive."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Speed", "struct")
        with db.read_only() as conn:
            matches = check_for_duplicates(conn, dal, "TypeDefinitions", "speed", "struct")
        assert [m["unique_key"] for m in matches] == ["td"]

    def test_matches_after_whitespace_normalization(self, initialized_db: str) -> None:
        """SRS-034 — trim and collapse internal whitespace before comparing."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Vehicle Speed", "struct")
        with db.read_only() as conn:
            matches = check_for_duplicates(
                conn, dal, "TypeDefinitions", "  Vehicle   Speed  ", "struct"
            )
        assert [m["unique_key"] for m in matches] == ["td"]

    def test_a_different_kind_is_not_a_duplicate(self, initialized_db: str) -> None:
        """SRS-034 — duplicates share the same kind and the same name."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Speed", "struct")
        with db.read_only() as conn:
            assert check_for_duplicates(conn, dal, "TypeDefinitions", "Speed", "enum") == []

    def test_no_match_returns_empty(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.read_only() as conn:
            assert check_for_duplicates(conn, dal, "TypeDefinitions", "Absent", "struct") == []


class TestDuplicateWarning:
    def test_names_the_table_and_the_matches(self) -> None:
        """SRS-121 — the warning is returned in the create response."""
        text = duplicate_warning("TypeDefinitions", "Speed", [{"unique_key": "k", "name": "Speed"}])
        assert "Speed" in text
        assert "k" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_duplicate_detection.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'check_for_duplicates'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/duplicate_detection.py`:

```python
"""Name-normalized duplicate detection.

The DAL's `find_duplicates_by_name` performs the indexed, case-insensitive
half of SRS-034 (`COLLATE NOCASE`). The whitespace normalization the
requirement also specifies is applied here, on both sides of the comparison,
because normalizing inside the DAL would diverge from the index (DEV-24).

See: LLD-02 §8 (Duplicate Detection — SRS-034, SRS-121)
"""

import sqlite3

from .db.dal import DataAccessLayer
from .validation.common import normalize_name


def check_for_duplicates(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    table: str,
    name: str,
    kind: str | None = None,
) -> list[dict[str, str]]:
    """Existing records whose normalized name equals this one (SRS-034)."""
    target = normalize_name(name)
    candidates = dal.find_duplicates_by_name(conn, table, name, kind)
    matches = [
        {"unique_key": str(record.unique_key), "name": str(record.name)}
        for record in candidates
        if normalize_name(str(record.name)) == target
    ]
    return matches


def duplicate_warning(table: str, name: str, matches: list[dict[str, str]]) -> str:
    """Human-readable warning returned in the create response (SRS-121)."""
    keys = ", ".join(match["unique_key"] for match in matches)
    return (
        f"Possible duplicate: {table} already contains {len(matches)} record(s) "
        f"named {name!r} (unique_key: {keys}). Review before approving."
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_duplicate_detection.py -q -p no:cacheprovider && python -m mypy src`
Expected: PASS, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/duplicate_detection.py tests/test_r210_mcp/test_duplicate_detection.py
git commit -m "feat: add normalized duplicate detection"
```

---

## Task 6: `projection.py`

**Files:**
- Create: `src/r210_mcp/projection.py`
- Test: `tests/test_r210_mcp/test_projection.py`

**Interfaces:**
- Consumes: `TABLE_RECORD_MAP` from `db.models`.
- Produces:
  - `GEMINI_ALLOWED_FIELDS: frozenset[str]` — the SRS-015a allowlist
  - `project_record(table: str, record: dict[str, Any]) -> dict[str, Any]`
  - `project_response(payload: dict[str, Any]) -> dict[str, Any]` — recursive; used by the registry

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_projection.py`:

```python
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
            "TypeDefinitions",
            {"unique_key": "k", "name": "Speed", "kind": "struct", "description": "secret"},
        )
        assert projected == {"unique_key": "k", "name": "Speed", "kind": "struct"}

    def test_keeps_source_reference_for_source_requirements(self) -> None:
        """SRS-015a — SourceRequirements has no name; source_reference stands in."""
        projected = project_record(
            "SourceRequirements",
            {"unique_key": "k", "source_reference": "REQ-1", "source_text": "secret"},
        )
        assert projected == {"unique_key": "k", "source_reference": "REQ-1"}


class TestProjectResponse:
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

    def test_preserves_warnings_and_errors(self) -> None:
        """SRS-015a — warning text and returned keys are permitted metadata."""
        payload = {"result": {"unique_key": "k", "warnings": ["Possible duplicate: ..."]}}
        assert project_response(payload)["result"]["warnings"] == ["Possible duplicate: ..."]

    def test_passes_an_error_response_through(self) -> None:
        payload = {"error": {"operation": "t", "field": None, "reason": "r", "affected_key": None}}
        assert project_response(payload) == payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_projection.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'r210_mcp.projection'`

- [ ] **Step 3: Write minimal implementation**

Create `src/r210_mcp/projection.py`:

```python
"""Response projection for Gemini-facing tool calls.

SRS-015a limits what may enter the Gemini model context. The projection is
applied once, at the dispatch boundary in `tools/registry.py`, rather than
inside each query handler as LLD-02 §11.2 sketches: a handler cannot omit a
step it does not perform (DEV-30).

See: LLD-02 §11 (Response Projection — SRS-015a)
"""

from typing import Any

# The permitted response fields, verbatim from SRS-015a. `source_reference`
# stands in for `name` on SourceRequirements; `issue_type` supports
# issue-awareness during extraction.
GEMINI_ALLOWED_FIELDS = frozenset(
    {
        "unique_key",
        "name",
        "kind",
        "interface_type",
        "status",
        "direction",
        "source_reference",
        "issue_type",
    }
)

# Response keys that are tool metadata rather than record fields. SRS-015a
# permits returned unique_keys and duplicate-warning text.
_METADATA_KEYS = frozenset({"unique_key", "warnings", "demoted", "table", "count"})


def project_record(table: str, record: dict[str, Any]) -> dict[str, Any]:
    """Drop every field outside the SRS-015a allowlist."""
    return {key: value for key, value in record.items() if key in GEMINI_ALLOWED_FIELDS}


def _project_value(value: Any) -> Any:
    if isinstance(value, dict):
        return project_record("", value)
    if isinstance(value, list):
        return [_project_value(item) for item in value]
    return value


def project_response(payload: dict[str, Any]) -> dict[str, Any]:
    """Project a whole tool response (LLD-02 §11.2).

    An error response passes through unchanged: it carries no record fields,
    and SRS-109 requires the operation, field, reason and affected key.
    """
    if "error" in payload:
        return payload
    result = payload.get("result")
    if not isinstance(result, dict):
        return payload

    projected: dict[str, Any] = {}
    for key, value in result.items():
        if key in _METADATA_KEYS:
            projected[key] = value
        else:
            projected[key] = _project_value(value)
    return {"result": projected}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_projection.py -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/projection.py tests/test_r210_mcp/test_projection.py
git commit -m "feat: add SRS-015a response projection"
```

---

## Plan Index

The plan is 25 tasks across five files. Execute them in order.

| Part | Tasks | Contents |
|---|---|---|
| This file | 1–6 | `McpValidationError`, DAL additions, common validators, status rules, duplicate detection, projection |
| `...-part2.md` | 7–10 | `ToolContext`, descriptors, and the create/update/query engines |
| `...-part3.md` | 11–15 | Entity validators; source-requirement and type-definition handlers |
| `...-part4.md` | 16–19 | Port-interface, port-prototype, port-connection and review-issue handlers |
| `...-part5.md` | 20–25 | `set_review_status`, `resolve_reference`/`trigger_generation`, registry, server, cross-cutting tests, docs |
