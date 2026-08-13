# Phase 3 Implementation Plan — Part 5: Status Tool, Registry, Server, Verification

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Read Part 1 first:** `docs/superpowers/plans/2026-08-12-phase3-mcp-tool-surface.md` for Goal, Architecture and Global Constraints. Parts 2–4 build the engine, validators and handlers these tasks consume.

**Covers:** Tasks 20–25 — `set_review_status`, the two cross-cutting tools, the registry, the MCP adapter, the parametrized rule suites, and the phase documentation.

---

## Task 20: `set_review_status`

The only tool that writes status directly, and the only one that consults
`adapter_mode` for authority.

**Files:**
- Create: `src/r210_mcp/tools/review_status.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_tools/test_review_status.py`

**Interfaces:**
- Consumes: `validate_artifact_transition`, `check_parent_can_be_approved`, `auto_demote_parent_chain`, `check_references_resolved` (Task 4); `ARTIFACT_STATUSES`, `ARTIFACT_TABLES`, `REVIEWABLE_CHILD_TABLES`, `STRUCTURAL_SUBTYPE_TABLES`, `PARENT_CHILD_MAP` from `db.models`.
- Produces: `handle_set_review_status(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]`, and `STATUS_TARGET_TABLES: frozenset[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_review_status.py`:

```python
"""Development tests for set_review_status (LLD-02 §7.7)."""

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.review_status import handle_set_review_status
from r210_mcp.tools.source_requirements import handle_create_source_requirement
from r210_mcp.tools.type_definitions import handle_create_type_definition


def _type_definition(ctx: object, name: str = "Mode") -> str:
    response = handle_create_type_definition(
        ctx, {"name": name, "kind": "enum", "subtype": {"values": []}}
    )
    return str(response["result"]["unique_key"])


class TestCallerAuthority:
    def test_rejects_a_caller_that_does_not_match_the_mode(self, initialized_db: str) -> None:
        """SRS-082a — a forged caller parameter is rejected."""
        ctx = build_context(initialized_db, "extraction")
        key = _type_definition(ctx)
        with pytest.raises(McpValidationError) as caught:
            handle_set_review_status(
                ctx, {"unique_key": key, "new_status": "ambiguous", "caller": "review"}
            )
        assert caught.value.error.field == "caller"

    def test_extraction_cannot_approve(self, initialized_db: str) -> None:
        """SRS-082a — approval is reserved for manual review."""
        ctx = build_context(initialized_db, "extraction")
        key = _type_definition(ctx)
        with pytest.raises(McpValidationError) as caught:
            handle_set_review_status(
                ctx, {"unique_key": key, "new_status": "approved", "caller": "extraction"}
            )
        assert "SRS-082a" in caught.value.error.reason

    def test_review_may_approve(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = _type_definition(ctx)
        response = handle_set_review_status(
            ctx, {"unique_key": key, "new_status": "approved", "caller": "review"}
        )
        assert response["result"]["status"] == "approved"


class TestTargetTables:
    def test_rejects_a_review_issue(self, initialized_db: str) -> None:
        """SRS-091a — issue status changes through update_review_issue."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            dal.insert_review_issue(conn, "ri", None, None, None, "ambiguous", "m")
        with pytest.raises(McpValidationError) as caught:
            handle_set_review_status(
                ctx, {"unique_key": "ri", "new_status": "approved", "caller": "review"}
            )
        assert "update_review_issue" in caught.value.error.reason

    def test_rejects_a_structural_subtype(self, initialized_db: str) -> None:
        """SRS-091a — subtype tables have no status column."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Speed", "simple_typedef")
            dal.insert_simple_type_definition(conn, "st", parent_id, "uint8", None)
        with pytest.raises(McpValidationError) as caught:
            handle_set_review_status(
                ctx, {"unique_key": "st", "new_status": "approved", "caller": "review"}
            )
        assert "status" in caught.value.error.reason


class TestTransitionAndBlocking:
    def test_rejects_a_forbidden_transition(self, initialized_db: str) -> None:
        """SRS-035b — approved may not go straight to ambiguous."""
        ctx = build_context(initialized_db, "review")
        key = _type_definition(ctx)
        handle_set_review_status(
            ctx, {"unique_key": key, "new_status": "approved", "caller": "review"}
        )
        with pytest.raises(McpValidationError):
            handle_set_review_status(
                ctx, {"unique_key": key, "new_status": "ambiguous", "caller": "review"}
            )

    def test_pending_child_blocks_approval(self, initialized_db: str) -> None:
        """SRS-046, SRS-053 — a parent cannot be approved over a pending child."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        key = _type_definition(ctx)
        with ctx.db.transaction() as conn:
            parent = dal.get_type_definition_by_key(conn, key)
            dal.insert_enum_value(conn, "ev", parent.id, "RED", None, 1)
        with pytest.raises(McpValidationError) as caught:
            handle_set_review_status(
                ctx, {"unique_key": key, "new_status": "approved", "caller": "review"}
            )
        assert "EnumValues" in caught.value.error.reason

    def test_unresolved_reference_blocks_approval(self, initialized_db: str) -> None:
        """SRS-036a — a record with an unresolved reference is not approvable."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
            dal.insert_struct_element(conn, "se", parent_id, "value", None, 1)
        with pytest.raises(McpValidationError) as caught:
            handle_set_review_status(
                ctx, {"unique_key": "se", "new_status": "approved", "caller": "review"}
            )
        assert "element_type_id" in caught.value.error.reason


class TestNotesAndDemotion:
    def test_stores_a_review_note(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = handle_create_source_requirement(ctx, {"source_reference": "REQ-1"})["result"][
            "unique_key"
        ]
        response = handle_set_review_status(
            ctx,
            {
                "unique_key": key,
                "new_status": "rejected",
                "review_note": "Out of date",
                "caller": "review",
            },
        )
        assert response["result"]["review_note"] == "Out of date"

    def test_ignores_a_note_on_a_table_without_the_column(self, initialized_db: str) -> None:
        """SRS-091a — the note is silently ignored, not an error."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
        response = handle_set_review_status(
            ctx,
            {"unique_key": "ev", "new_status": "rejected", "review_note": "x", "caller": "review"},
        )
        assert response["result"]["status"] == "rejected"

    def test_child_leaving_approved_demotes_the_parent(self, initialized_db: str) -> None:
        """SRS-035c — both changes happen in one transaction."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with ctx.db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
            child_id = dal.insert_enum_value(conn, "ev", parent_id, "RED", None, 1)
            dal.update_status(conn, "EnumValues", child_id, "approved")
            dal.update_status(conn, "TypeDefinitions", parent_id, "approved")
        response = handle_set_review_status(
            ctx, {"unique_key": "ev", "new_status": "pending_review", "caller": "review"}
        )
        assert response["result"]["demoted"] == ["td"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_review_status.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'handle_set_review_status'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/tools/review_status.py`:

```python
"""The sole tool that writes a review status.

`table_hint` from LLD-02 §7.7 is accepted but optional: `resolve_unique_key`
already finds the owning table, and requiring the caller to name it invites a
mismatch between hint and reality (DEV-35).

See: LLD-02 §7.7 (Review Status Tool — SRS-035b, SRS-082a, SRS-089, SRS-091a)
"""

from typing import Any

from ..db.models import (
    ARTIFACT_STATUSES,
    ARTIFACT_TABLES,
    PARENT_CHILD_MAP,
    REVIEWABLE_CHILD_TABLES,
    STRUCTURAL_SUBTYPE_TABLES,
)
from ..errors import McpResult, McpValidationError
from ..validation.common import validate_choice, validate_uuid_format
from ..validation.status import (
    auto_demote_parent_chain,
    check_parent_can_be_approved,
    check_references_resolved,
    validate_artifact_transition,
)
from ._engine import record_to_dict, reject_unknown_arguments
from .context import ToolContext

_TOOL = "set_review_status"

# The tables this tool may target (SRS-091a): artifacts, SourceRequirements,
# and the seven reviewable children. ReviewIssues and the structural subtypes
# are excluded.
STATUS_TARGET_TABLES = ARTIFACT_TABLES | REVIEWABLE_CHILD_TABLES


def handle_set_review_status(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Set a review state (SRS-089), enforcing authority and the invariants."""
    reject_unknown_arguments(
        _TOOL,
        arguments,
        frozenset({"unique_key", "table_hint", "new_status", "review_note", "caller"}),
    )
    caller = arguments.get("caller")
    if caller != ctx.adapter_mode:
        raise McpValidationError.of(
            _TOOL,
            f"caller {caller!r} does not match the server adapter_mode "
            f"{ctx.adapter_mode!r} (SRS-082a)",
            field="caller",
            affected_key=arguments.get("unique_key"),
        )

    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=_TOOL)
    new_status = arguments.get("new_status")
    validate_choice(new_status, ARTIFACT_STATUSES, "new_status", operation=_TOOL)

    with ctx.db.transaction() as conn:
        found = ctx.dal.resolve_unique_key(conn, str(key))
        if found is None:
            raise McpValidationError.of(
                _TOOL,
                f"no record with unique_key {key!r}",
                field="unique_key",
                affected_key=str(key),
            )
        table, record = found

        if table == "ReviewIssues":
            raise McpValidationError.of(
                _TOOL,
                "Use update_review_issue for review-issue status changes (SRS-119).",
                field="unique_key",
                affected_key=str(key),
            )
        if table in STRUCTURAL_SUBTYPE_TABLES:
            raise McpValidationError.of(
                _TOOL,
                f"{table} is a structural subtype and has no status field (SRS-091a).",
                field="unique_key",
                affected_key=str(key),
            )
        if table not in STATUS_TARGET_TABLES:
            raise McpValidationError.of(
                _TOOL,
                f"{table} is not a reviewable table (SRS-091a).",
                field="unique_key",
                affected_key=str(key),
            )

        validate_artifact_transition(
            str(record.status), str(new_status), operation=_TOOL, affected_key=str(key)
        )

        if new_status == "approved":
            if ctx.adapter_mode == "extraction":
                raise McpValidationError.of(
                    _TOOL,
                    "Approval is reserved for manual review (SRS-082a).",
                    field="new_status",
                    affected_key=str(key),
                )
            unresolved = check_references_resolved(conn, ctx.dal, table, record)
            if unresolved:
                raise McpValidationError.of(
                    _TOOL,
                    f"cannot approve while these references are unresolved: "
                    f"{', '.join(unresolved)} (SRS-036a)",
                    field="new_status",
                    affected_key=str(key),
                )
            if table in PARENT_CHILD_MAP:
                blockers = check_parent_can_be_approved(conn, ctx.dal, table, int(record.id))
                if blockers:
                    detail = "; ".join(
                        f"{blocker['child_table']} is {blocker['status']}" for blocker in blockers
                    )
                    raise McpValidationError.of(
                        _TOOL,
                        f"cannot approve while children are not approved: {detail} "
                        "(SRS-046, SRS-053)",
                        field="new_status",
                        affected_key=str(key),
                    )

        ctx.dal.update_status(
            conn, table, int(record.id), str(new_status), arguments.get("review_note")
        )

        demoted: list[str] = []
        if new_status != "approved":
            demoted = auto_demote_parent_chain(conn, ctx.dal, table, int(record.id))

        updated = ctx.dal.get_record_by_id(conn, table, int(record.id))

    data = record_to_dict(updated)
    data.pop("id", None)
    data.pop("unique_key", None)
    data["table"] = table
    if demoted:
        data["demoted"] = demoted
    return McpResult(unique_key=str(key), data=data).to_dict()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/review_status.py tests/test_r210_mcp/test_tools/test_review_status.py
git commit -m "feat(tools): add set_review_status with approval authority and blocking"
```

---

## Task 21: `resolve_reference` and `trigger_generation`

**Files:**
- Create: `src/r210_mcp/tools/reference.py`, `src/r210_mcp/tools/generation.py` (replace the stubs)
- Test: `tests/test_r210_mcp/test_tools/test_reference_and_generation.py`

**Interfaces:**
- Produces: `handle_resolve_reference(ctx, arguments) -> dict[str, Any]`; `handle_trigger_generation(ctx, arguments) -> dict[str, Any]`; `generation.GENERATION_MODES: frozenset[str]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_reference_and_generation.py`:

```python
"""Development tests for resolve_reference and trigger_generation (LLD-02 §7.8-7.9)."""

import pytest

from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.generation import handle_trigger_generation
from r210_mcp.tools.reference import handle_resolve_reference
from r210_mcp.tools.source_requirements import handle_create_source_requirement


class TestResolveReference:
    def test_finds_the_owning_table(self, initialized_db: str) -> None:
        """SRS-087 — references resolve by UUID across every table."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_source_requirement(ctx, {"source_reference": "REQ-1"})["result"][
            "unique_key"
        ]
        response = handle_resolve_reference(ctx, {"unique_key": key})
        assert response["result"]["table"] == "SourceRequirements"
        assert response["result"]["record"]["source_reference"] == "REQ-1"

    def test_unknown_key_is_an_error(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_resolve_reference(
                ctx, {"unique_key": "3f2504e0-4f89-41d3-9a0c-0305e82c3301"}
            )
        assert caught.value.error.field == "unique_key"


class TestTriggerGeneration:
    @pytest.mark.parametrize("mode", ["r210_only", "report_only", "both"])
    def test_validates_the_mode_then_reports_unavailable(
        self, initialized_db: str, mode: str
    ) -> None:
        """SRS-090 — the tool exists; the generator arrives in Phase 7."""
        ctx = build_context(initialized_db, "review")
        response = handle_trigger_generation(ctx, {"mode": mode})
        assert "error" in response
        assert "not yet implemented" in response["error"]["reason"]

    def test_rejects_an_unknown_mode(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_trigger_generation(ctx, {"mode": "everything"})
        assert caught.value.error.field == "mode"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_reference_and_generation.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'handle_resolve_reference'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/tools/reference.py`:

```python
"""Reference resolution by UUID.

See: LLD-02 §7.8 (Reference Resolution Tool — SRS-087)
"""

from typing import Any

from ..errors import McpResult, McpValidationError
from ..validation.common import validate_uuid_format
from ._engine import record_to_dict, reject_unknown_arguments
from .context import ToolContext

_TOOL = "resolve_reference"


def handle_resolve_reference(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Find the table and record owning a unique_key (SRS-087)."""
    reject_unknown_arguments(_TOOL, arguments, frozenset({"unique_key"}))
    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=_TOOL)

    with ctx.db.read_only() as conn:
        found = ctx.dal.resolve_unique_key(conn, str(key))

    if found is None:
        raise McpValidationError.of(
            _TOOL,
            f"no record with unique_key {key!r}",
            field="unique_key",
            affected_key=str(key),
        )
    table, record = found
    payload = record_to_dict(record)
    payload.pop("id", None)
    return McpResult(unique_key=str(key), data={"table": table, "record": payload}).to_dict()
```

Replace the contents of `src/r210_mcp/tools/generation.py`:

```python
"""Generation trigger.

The deterministic generator is LLD-04, delivered in Phase 7. The tool is
registered and validates its input so the contract is real, but reports that
generation is unavailable rather than pretending to succeed (DEV-31).

See: LLD-02 §7.9 (Generation Trigger Tool — SRS-090)
"""

from typing import Any

from ..errors import McpError
from ..validation.common import validate_choice
from ._engine import reject_unknown_arguments
from .context import ToolContext

_TOOL = "trigger_generation"

GENERATION_MODES = frozenset({"r210_only", "report_only", "both"})


def handle_trigger_generation(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate the mode, then report that the generator is not available."""
    reject_unknown_arguments(_TOOL, arguments, frozenset({"mode"}))
    validate_choice(arguments.get("mode"), GENERATION_MODES, "mode", operation=_TOOL)
    return McpError(
        operation=_TOOL,
        field=None,
        reason=(
            "Deterministic generation is not yet implemented; the generator "
            "component (LLD-04) is delivered in a later phase."
        ),
        affected_key=None,
    ).to_dict()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/reference.py src/r210_mcp/tools/generation.py tests/test_r210_mcp/test_tools/test_reference_and_generation.py
git commit -m "feat(tools): add resolve_reference and trigger_generation"
```

---

## Task 22: The tool registry

**Files:**
- Create: `src/r210_mcp/tools/registry.py`
- Test: `tests/test_r210_mcp/test_tools/test_registry.py`

**Interfaces:**
- Consumes: every handler from Tasks 14–21; `project_response` (Task 6).
- Produces:
  - `TOOL_HANDLERS: dict[str, Callable[[ToolContext, dict[str, Any]], dict[str, Any]]]` — all 35
  - `dispatch(ctx, tool_name, arguments) -> dict[str, Any]` — the error and projection boundary
  - `query_by_table(ctx, table, filters) -> list[dict[str, Any]]`
  - `get_children_for_display(ctx, table, record_id) -> list[dict[str, Any]]`
  - `get_stats(ctx) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_registry.py`:

```python
"""Development tests for the dispatch boundary (LLD-02 §9, §11)."""

import pytest

from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import TOOL_HANDLERS, dispatch, get_stats, query_by_table


class TestRegistry:
    def test_registers_thirty_five_tools(self) -> None:
        """LLD-02 §9 — 13 create + 13 update + 6 query + 3 cross-cutting."""
        assert len(TOOL_HANDLERS) == 35
        assert sum(1 for name in TOOL_HANDLERS if name.startswith("create_")) == 13
        assert sum(1 for name in TOOL_HANDLERS if name.startswith("update_")) == 13
        assert sum(1 for name in TOOL_HANDLERS if name.startswith("query_")) == 6


class TestDispatch:
    def test_dispatches_by_name(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        response = dispatch(ctx, "create_source_requirement", {"source_reference": "REQ-1"})
        assert response["result"]["source_reference"] == "REQ-1"

    def test_unknown_tool_is_a_structured_error(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        response = dispatch(ctx, "delete_everything", {})
        assert response["error"]["operation"] == "delete_everything"

    def test_validation_error_becomes_a_response(self, initialized_db: str) -> None:
        """SRS-083, SRS-109 — the boundary serializes, it does not raise."""
        ctx = build_context(initialized_db, "review")
        response = dispatch(ctx, "create_source_requirement", {"source_reference": ""})
        assert response["error"]["field"] == "source_reference"

    def test_constraint_violation_becomes_a_response(self, initialized_db: str) -> None:
        """SRS-109 — the boundary knows the tool name and the affected key."""
        ctx = build_context(initialized_db, "review")
        parent = dispatch(
            ctx,
            "create_type_definition",
            {"name": "Mode", "kind": "enum", "subtype": {"values": []}},
        )["result"]["unique_key"]
        dispatch(
            ctx,
            "create_enum_value",
            {"enum_type_key": parent, "name": "RED", "position": 1},
        )
        response = dispatch(
            ctx,
            "create_enum_value",
            {"enum_type_key": parent, "name": "RED", "position": 2},
        )
        assert response["error"]["operation"] == "create_enum_value"
        assert response["error"]["reason"]

    def test_extraction_mode_projects_the_response(self, initialized_db: str) -> None:
        """SRS-015a — source_text never leaves in extraction mode."""
        ctx = build_context(initialized_db, "extraction")
        response = dispatch(
            ctx,
            "create_source_requirement",
            {"source_reference": "REQ-1", "source_text": "confidential"},
        )
        assert "source_text" not in response["result"]
        assert response["result"]["source_reference"] == "REQ-1"

    def test_review_mode_returns_full_records(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        response = dispatch(
            ctx,
            "create_source_requirement",
            {"source_reference": "REQ-1", "source_text": "full text"},
        )
        assert response["result"]["source_text"] == "full text"


class TestNonMcpHelpers:
    def test_query_by_table_reaches_a_child_table(self, initialized_db: str) -> None:
        """LLD-06 — the review CLI needs child tables that have no query tool."""
        ctx = build_context(initialized_db, "review")
        parent = dispatch(
            ctx,
            "create_type_definition",
            {"name": "Mode", "kind": "enum", "subtype": {"values": [{"name": "RED", "position": 1}]}},
        )["result"]["unique_key"]
        assert parent
        rows = query_by_table(ctx, "EnumValues", {})
        assert [row["name"] for row in rows] == ["RED"]

    def test_stats_count_by_status(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        dispatch(ctx, "create_source_requirement", {"source_reference": "REQ-1"})
        stats = get_stats(ctx)
        assert stats["SourceRequirements"]["total"] == 1
        assert stats["SourceRequirements"]["by_status"]["pending_review"] == 1
        assert stats["SimpleTypeDefinitions"]["by_status"] == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_registry.py -q -p no:cacheprovider`
Expected: FAIL with `ModuleNotFoundError: No module named 'r210_mcp.tools.registry'`

- [ ] **Step 3: Write minimal implementation**

Create `src/r210_mcp/tools/registry.py`:

```python
"""Tool dispatch, the error boundary, and the projection boundary.

This module is where an exception becomes a response and where SRS-015a
projection is applied — once, to every tool, rather than inside each query
handler (DEV-30). Translating `sqlite3.IntegrityError` here is what Phase 2
deferred to: only this layer knows the tool name and the affected key that
SRS-109 requires.

See: LLD-02 §9 (Tool Registration), §11 (Response Projection)
"""

import sqlite3
from collections.abc import Callable
from typing import Any

from ..db.models import STRUCTURAL_SUBTYPE_TABLES, TABLE_RECORD_MAP
from ..errors import McpError, McpValidationError
from ..projection import project_response
from ._engine import record_to_dict
from .context import ToolContext
from .generation import handle_trigger_generation
from .port_connections import (
    handle_create_port_connection,
    handle_create_port_connection_member,
    handle_query_port_connections,
    handle_update_port_connection,
    handle_update_port_connection_member,
)
from .port_interfaces import (
    handle_create_client_server_operation,
    handle_create_interface_data_element,
    handle_create_operation_argument,
    handle_create_port_interface,
    handle_query_port_interfaces,
    handle_update_client_server_operation,
    handle_update_interface_data_element,
    handle_update_operation_argument,
    handle_update_port_interface,
)
from .port_prototypes import (
    handle_create_port_prototype,
    handle_create_port_prototype_function,
    handle_query_port_prototypes,
    handle_update_port_prototype,
    handle_update_port_prototype_function,
)
from .reference import handle_resolve_reference
from .review_issues import (
    handle_create_review_issue,
    handle_query_review_issues,
    handle_update_review_issue,
)
from .review_status import handle_set_review_status
from .source_requirements import (
    handle_create_source_requirement,
    handle_query_source_requirements,
    handle_update_source_requirement,
)
from .type_definitions import (
    handle_create_enum_value,
    handle_create_struct_element,
    handle_create_type_definition,
    handle_query_type_definitions,
    handle_update_enum_value,
    handle_update_struct_element,
    handle_update_type_definition,
)

ToolHandler = Callable[[ToolContext, dict[str, Any]], dict[str, Any]]

# The 35 tools of LLD-02 §9: 13 create, 13 update, 6 query, 3 cross-cutting.
TOOL_HANDLERS: dict[str, ToolHandler] = {
    "create_source_requirement": handle_create_source_requirement,
    "update_source_requirement": handle_update_source_requirement,
    "query_source_requirements": handle_query_source_requirements,
    "create_type_definition": handle_create_type_definition,
    "update_type_definition": handle_update_type_definition,
    "query_type_definitions": handle_query_type_definitions,
    "create_struct_element": handle_create_struct_element,
    "update_struct_element": handle_update_struct_element,
    "create_enum_value": handle_create_enum_value,
    "update_enum_value": handle_update_enum_value,
    "create_port_interface": handle_create_port_interface,
    "update_port_interface": handle_update_port_interface,
    "query_port_interfaces": handle_query_port_interfaces,
    "create_interface_data_element": handle_create_interface_data_element,
    "update_interface_data_element": handle_update_interface_data_element,
    "create_client_server_operation": handle_create_client_server_operation,
    "update_client_server_operation": handle_update_client_server_operation,
    "create_operation_argument": handle_create_operation_argument,
    "update_operation_argument": handle_update_operation_argument,
    "create_port_prototype": handle_create_port_prototype,
    "update_port_prototype": handle_update_port_prototype,
    "query_port_prototypes": handle_query_port_prototypes,
    "create_port_prototype_function": handle_create_port_prototype_function,
    "update_port_prototype_function": handle_update_port_prototype_function,
    "create_port_connection": handle_create_port_connection,
    "update_port_connection": handle_update_port_connection,
    "query_port_connections": handle_query_port_connections,
    "create_port_connection_member": handle_create_port_connection_member,
    "update_port_connection_member": handle_update_port_connection_member,
    "create_review_issue": handle_create_review_issue,
    "update_review_issue": handle_update_review_issue,
    "query_review_issues": handle_query_review_issues,
    "set_review_status": handle_set_review_status,
    "resolve_reference": handle_resolve_reference,
    "trigger_generation": handle_trigger_generation,
}


def dispatch(ctx: ToolContext, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Run a tool by name, returning a response rather than raising.

    Projection is applied here so that no handler can omit it (SRS-015a).
    """
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return McpError(
            operation=tool_name, field=None, reason=f"unknown tool: {tool_name}", affected_key=None
        ).to_dict()

    try:
        response = handler(ctx, arguments)
    except McpValidationError as exc:
        response = exc.error.to_dict()
    except sqlite3.IntegrityError as exc:
        response = McpError(
            operation=tool_name,
            field=None,
            reason=f"database constraint violated: {exc}",
            affected_key=arguments.get("unique_key"),
        ).to_dict()

    if ctx.adapter_mode == "extraction":
        return project_response(response)
    return response


def query_by_table(
    ctx: ToolContext, table: str, filters: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Query a table that has no dedicated query tool (LLD-02 §9, LLD-06)."""
    with ctx.db.read_only() as conn:
        records = ctx.dal.query_table(conn, table, filters or None)
    return [record_to_dict(record) for record in records]


def get_children_for_display(
    ctx: ToolContext, table: str, record_id: int
) -> list[dict[str, Any]]:
    """Load a parent's children for display (LLD-02 §9)."""
    from ..db.models import PARENT_CHILD_MAP

    children: list[dict[str, Any]] = []
    with ctx.db.read_only() as conn:
        for relation in PARENT_CHILD_MAP.get(table, []):
            for record in ctx.dal.get_children(
                conn, relation.child_table, relation.fk_column, record_id
            ):
                children.append(
                    {"table": relation.child_table, "record": record_to_dict(record)}
                )
    return children


def get_stats(ctx: ToolContext) -> dict[str, Any]:
    """Row and status counts per table (LLD-02 §9).

    Table names come from the model registry, so a table added by a future
    migration is counted without editing a second list.
    """
    tables = sorted(set(TABLE_RECORD_MAP) - {"schema_version"})
    stats: dict[str, Any] = {}
    with ctx.db.read_only() as conn:
        for table in tables:
            total = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            by_status: dict[str, int] = {}
            if table not in STRUCTURAL_SUBTYPE_TABLES:
                rows = conn.execute(
                    f'SELECT "status", COUNT(*) FROM "{table}" GROUP BY "status"'
                ).fetchall()
                by_status = {str(row[0]): int(row[1]) for row in rows}
            stats[table] = {"total": int(total), "by_status": by_status}
    return stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/registry.py tests/test_r210_mcp/test_tools/test_registry.py
git commit -m "feat(tools): add dispatch registry with error and projection boundaries"
```

---

## Task 23: The MCP server adapter

The only module that imports `mcp`. The SDK is not installed here, so the
adapter is verified by an import-guard test rather than by running a server.

**Files:**
- Modify: `src/r210_mcp/server.py`
- Modify: `src/r210_mcp/__main__.py`
- Test: `tests/test_r210_mcp/test_server.py`

**Interfaces:**
- Consumes: `TOOL_HANDLERS`, `dispatch` (Task 22); `build_context` (Task 7).
- Produces: `R210McpServer(db_path, adapter_mode="extraction")` with `.handle_tool(name, arguments)`, `.tool_names()`, `.run()`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_server.py`:

```python
"""Development tests for the MCP adapter (LLD-02 §9).

The `mcp` SDK is not installed in this environment, so these tests exercise
the non-MCP surface: construction, tool listing, and direct dispatch. `run()`
is the only method that touches the SDK, and it imports it lazily.
"""

import pytest

from r210_mcp.server import R210McpServer


class TestConstruction:
    def test_rejects_an_unknown_adapter_mode(self, initialized_db: str) -> None:
        """SRS-082a — authority is bound at construction."""
        with pytest.raises(ValueError):
            R210McpServer(initialized_db, "superuser")

    def test_defaults_to_extraction(self, initialized_db: str) -> None:
        assert R210McpServer(initialized_db).adapter_mode == "extraction"


class TestToolSurface:
    def test_lists_thirty_five_tools(self, initialized_db: str) -> None:
        assert len(R210McpServer(initialized_db).tool_names()) == 35

    def test_handle_tool_dispatches_without_the_sdk(self, initialized_db: str) -> None:
        """LLD-06 — the review CLI invokes tools without the MCP protocol."""
        server = R210McpServer(initialized_db, "review")
        response = server.handle_tool("create_source_requirement", {"source_reference": "REQ-1"})
        assert response["result"]["source_reference"] == "REQ-1"

    def test_unknown_tool_returns_an_error(self, initialized_db: str) -> None:
        server = R210McpServer(initialized_db, "review")
        assert "error" in server.handle_tool("nope", {})


class TestSdkIsolation:
    def test_importing_the_package_does_not_require_mcp(self) -> None:
        """The SDK is absent here; only run() may need it."""
        import r210_mcp.server as module

        assert "mcp" not in dir(module)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_server.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'R210McpServer'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/server.py`:

```python
"""MCP server entry point.

The SDK import lives inside `run()` so that importing this module — which the
Local Review CLI and every test does — does not require `mcp` to be installed.
All behaviour is in `tools/registry.py`; this class only binds a database path
and an authority mode to it.

See: LLD-02 §9 (MCP Server Entry Point)
"""

from typing import Any

from .tools.context import build_context
from .tools.registry import TOOL_HANDLERS, dispatch


class R210McpServer:
    """Binds a database and an authority mode to the tool surface (SRS-082a)."""

    def __init__(self, db_path: str, adapter_mode: str = "extraction") -> None:
        self._ctx = build_context(db_path, adapter_mode)

    @property
    def adapter_mode(self) -> str:
        return self._ctx.adapter_mode

    def tool_names(self) -> list[str]:
        """The registered tool names, in registration order."""
        return list(TOOL_HANDLERS)

    def handle_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call directly, without the MCP protocol (LLD-06)."""
        return dispatch(self._ctx, tool_name, arguments)

    def run(self) -> None:  # pragma: no cover - requires the mcp SDK
        """Serve the tool surface over stdio.

        Imported lazily: `mcp` is a runtime dependency of this method only.
        """
        from mcp.server import Server
        from mcp.server.stdio import stdio_server

        server: Any = Server("r210-automation")

        for name in TOOL_HANDLERS:

            def _make(tool_name: str) -> Any:
                async def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
                    return self.handle_tool(tool_name, arguments)

                return _handler

            server.call_tool(name)(_make(name))

        import anyio

        async def _serve() -> None:
            async with stdio_server() as (read, write):
                await server.run(read, write, server.create_initialization_options())

        anyio.run(_serve)
```

Replace the contents of `src/r210_mcp/__main__.py`:

```python
"""Run the R210 MCP server: `python -m r210_mcp <db_path> [--mode MODE]`."""

import argparse

from .server import R210McpServer


def main() -> None:
    parser = argparse.ArgumentParser(description="R210 MCP Server")
    parser.add_argument("db_path", help="Path to the SQLite database file")
    parser.add_argument(
        "--mode",
        default="extraction",
        choices=["extraction", "review"],
        help="Adapter authority mode (SRS-082a)",
    )
    args = parser.parse_args()
    R210McpServer(args.db_path, args.mode).run()


if __name__ == "__main__":
    main()
```

If the SDK's actual API differs from the sketch above, adjust `run()` only —
no test depends on its internals, and `# pragma: no cover` marks it as
unverified in this environment. Record the final shape in the phase document.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/server.py src/r210_mcp/__main__.py tests/test_r210_mcp/test_server.py
git commit -m "feat: add the MCP server adapter with a lazy SDK import"
```

---

## Task 24: Cross-cutting rule suites and the two adversarial tests

The rules that must hold for *every* tool get one parametrized test each,
driven off the registries, so a tool added later without the rule fails.

**Files:**
- Create: `tests/test_r210_mcp/test_cross_cutting.py`

**Interfaces:**
- Consumes: `TOOL_HANDLERS`, `dispatch` (Task 22); `GEMINI_ALLOWED_FIELDS` (Task 6); model registries.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_cross_cutting.py`:

```python
"""Rules that must hold across the whole tool surface.

Each test is parametrized off a registry rather than a hand-written list, so a
tool or table added later is covered automatically.
"""

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.db.models import ARTIFACT_TABLES, REVIEWABLE_CHILD_TABLES
from r210_mcp.projection import GEMINI_ALLOWED_FIELDS
from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import TOOL_HANDLERS, dispatch

UPDATE_TOOLS = sorted(name for name in TOOL_HANDLERS if name.startswith("update_"))
STATUS_TABLES = sorted(ARTIFACT_TABLES | REVIEWABLE_CHILD_TABLES)
FORBIDDEN_FIELDS = [
    "source_text",
    "description",
    "review_note",
    "resolution",
    "component_reference",
    "function_name",
]


@pytest.mark.parametrize("tool", UPDATE_TOOLS)
def test_every_update_tool_rejects_status(initialized_db: str, tool: str) -> None:
    """SRS-091a — no update tool accepts `status`, except update_review_issue."""
    ctx = build_context(initialized_db, "review")
    response = dispatch(
        ctx, tool, {"unique_key": "3f2504e0-4f89-41d3-9a0c-0305e82c3301", "status": "approved"}
    )
    assert "error" in response
    if tool != "update_review_issue":
        assert response["error"]["field"] == "status"


@pytest.mark.parametrize("table", STATUS_TABLES)
def test_every_reviewable_table_can_hold_each_status(initialized_db: str, table: str) -> None:
    """SRS-035 — all five review states are storable on every reviewable table."""
    dal = DataAccessLayer()
    ctx = build_context(initialized_db, "review")
    with ctx.db.transaction() as conn:
        columns = conn.execute(f'SELECT * FROM "{table}" LIMIT 0').description
    assert any(column[0] == "status" for column in columns)


@pytest.mark.parametrize("tool", sorted(TOOL_HANDLERS))
def test_no_tool_leaks_a_forbidden_field_in_extraction_mode(
    initialized_db: str, tool: str
) -> None:
    """SRS-015a — adversarial: every tool, invoked with hostile arguments.

    Named by REPOSITORY_REVIEW_REPORT.md §7 as a required test. Arguments are
    deliberately invalid for most tools; what matters is that whatever comes
    back carries no field outside the allowlist.
    """
    ctx = build_context(initialized_db, "extraction")
    response = dispatch(
        ctx,
        tool,
        {
            "unique_key": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
            "source_reference": "REQ-1",
            "source_text": "confidential",
            "description": "confidential",
            "review_note": "confidential",
        },
    )
    result = response.get("result")
    if not isinstance(result, dict):
        return
    for key in result:
        if key in ("warnings", "demoted", "table", "count", "records", "record"):
            continue
        assert key in GEMINI_ALLOWED_FIELDS, f"{tool} leaked {key}"
    for nested in ("records", "record"):
        value = result.get(nested)
        rows = value if isinstance(value, list) else [value] if isinstance(value, dict) else []
        for row in rows:
            for field in FORBIDDEN_FIELDS:
                assert field not in row, f"{tool} leaked {field}"


@pytest.mark.parametrize("table", STATUS_TABLES)
def test_extraction_cannot_approve_anything(initialized_db: str, table: str) -> None:
    """SRS-082a — adversarial: forged caller, every reviewable table.

    Named by REPOSITORY_REVIEW_REPORT.md §7 as a required test.
    """
    ctx = build_context(initialized_db, "extraction")
    for caller in ("extraction", "review", None):
        response = dispatch(
            ctx,
            "set_review_status",
            {
                "unique_key": "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
                "new_status": "approved",
                "caller": caller,
            },
        )
        assert "error" in response, f"extraction approved via caller={caller!r}"


def test_no_delete_tool_is_registered() -> None:
    """SRS-091 — deletion is not on the MCP tool surface."""
    assert not [name for name in TOOL_HANDLERS if "delete" in name or "remove" in name]


def test_no_reset_tool_is_registered() -> None:
    """SRS-093 — destructive operations are not exposed through MCP."""
    assert not [name for name in TOOL_HANDLERS if "reset" in name or "drop" in name]
```

- [ ] **Step 2: Run the suite and read every failure**

Run: `python -m pytest tests/test_r210_mcp/test_cross_cutting.py -q -p no:cacheprovider`
Expected: Any failure here is a real gap in Tasks 14–22, not a test bug. Fix the handler, not the assertion.

- [ ] **Step 3: Fix whatever the suite catches**

Work through failures one at a time. The likely ones:
- A tool whose response includes a forbidden field because a handler returned a record without popping it.
- A create tool that accepts `status` directly instead of `initial_status`.

- [ ] **Step 4: Run the whole suite**

Run: `python -m pytest tests/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add tests/test_r210_mcp/test_cross_cutting.py
git commit -m "test: add cross-cutting rule suites and adversarial authority tests"
```

---

## Task 25: Phase documentation

**Files:**
- Create: `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md`
- Modify: `docs/DEVIATIONS_FROM_REQUIREMENTS.md`
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Write `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md`**

Follow the structure of `docs/PHASE2_IMPLEMENTED_REQUIREMENTS.md`: metadata
table, scope, status legend (Full / Mechanism), one requirements table per
area, design properties, verification summary with the real test counts, and a
"deliberately does not do" table naming Phase 7 (generator) and Phase 8
(review CLI) as the only remaining phases.

Requirements to trace, at minimum: SRS-027, SRS-034, SRS-035, SRS-035a,
SRS-035b, SRS-035c, SRS-036a, SRS-037, SRS-038a, SRS-038b, SRS-038c, SRS-043,
SRS-044, SRS-046, SRS-052, SRS-053, SRS-055, SRS-059, SRS-061, SRS-063,
SRS-069, SRS-070, SRS-072, SRS-074, SRS-082a, SRS-082b, SRS-083, SRS-084,
SRS-085 through SRS-093, SRS-091a, SRS-092a, SRS-108, SRS-109, SRS-119,
SRS-120, SRS-121, SRS-122, SRS-125, and SRS-015a.

- [ ] **Step 2: Append section 4B to `docs/DEVIATIONS_FROM_REQUIREMENTS.md`**

Write DEV-25 through DEV-35 in the existing format — what the documents say,
what the implementation does, why, and the effect on behaviour:

| ID | Type | Summary |
|---|---|---|
| DEV-25 | Gap-fill | `McpValidationError` defined; LLD-02 §6 raises it but never defines it |
| DEV-26 | Refinement | Handlers are functions over `ToolContext`, not bound methods |
| DEV-27 | Gap-fill | SRS-036a's approval block implemented as `check_references_resolved` |
| DEV-28 | Addition | Six DAL methods added; LLD names four, the engine needs `insert_record` and `update_record` |
| DEV-29 | Correction | Records are dataclasses, not dict-subscriptable rows |
| DEV-30 | Refinement | Projection applied once at the dispatch boundary |
| DEV-31 | Boundary | `trigger_generation` registered but reports generation unavailable |
| DEV-32 | Refinement | Descriptor-driven engine behind the named handler surface |
| DEV-33 | Correction | Phase 3 absorbs Phases 4–6; the documented split is not implementable |
| DEV-34 | Refinement | Validators take `operation`, without which they cannot build an SRS-109 error |
| DEV-35 | Refinement | `table_hint` is optional; `resolve_unique_key` finds the owning table |

Update the deviation index in §5 and add a revision-history row.

- [ ] **Step 3: Update `README.md` and `CLAUDE.md`**

In `README.md`, change the Status section: the MCP server is implemented; the
remaining components are the generator (LLD-04) and the review CLI (LLD-06).

In `CLAUDE.md`, update the "Implementation state" section: Phase 3 delivered
the validation layer, the 35 tools and the server adapter; the stubs remaining
are `r210_generator/` and `r210_review_cli/`. Add the new architecture facts —
handlers are functions over `ToolContext`, the registry is the error and
projection boundary, `mcp` is imported only inside `server.run()`.

- [ ] **Step 4: Verify the whole suite one last time**

Run:
```bash
python -m pytest tests/ -q -p no:cacheprovider
python -m ruff check src tests
python -m mypy src
```
Expected: all three clean. Record the real test count in the phase document —
do not carry forward an estimate.

- [ ] **Step 5: Commit**

```bash
git add docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md docs/DEVIATIONS_FROM_REQUIREMENTS.md README.md CLAUDE.md
git commit -m "docs: record Phase 3 implemented requirements and deviations"
```

---

## Plan Self-Review Notes

**Spec coverage.** Every section of the spec maps to a task: §2 handlers-as-
functions → Task 7; §3 engine → Tasks 8–10; §4 cross-cutting rules → Tasks 4,
8, 9, 20, 22, 24; §5 `set_review_status` → Task 20; §6 projection → Tasks 6 and
22; §7 error handling → Tasks 1 and 22; §8 DAL additions → Task 2; §9
`trigger_generation` → Task 21; §10 testing → every task plus Task 24; §11
deliverables → Task 25; §12 deviations → Task 25.

**Two spec corrections made while planning**, both recorded in Task 25:
- DEV-28 covers **six** DAL methods, not four. The engine needs generic
  `insert_record` and `update_record`; without them each of the 13 creates
  would carry a hand-written lambda naming its own columns, which is the
  duplication the design exists to avoid.
- DEV-34 and DEV-35 are new: validators take an `operation` parameter the LLD
  omits, and `table_hint` is optional rather than required.

**Known coupling to watch during execution.** Task 19 requires a `field`
parameter on `_validate_transition` in `validation/status.py` (Task 4) so that
`update_review_issue` reports `field="status"` while `set_review_status`
reports `field="new_status"`. Whoever executes Task 19 must make that one-line
change in Task 4's module and re-run Task 4's tests.
