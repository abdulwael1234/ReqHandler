# Phase 4/5 Part 1 — Local Review CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Status: executed 2026-08-15, with deviations.** Only Part 1 was written as a
> formal plan; the remaining sub-projects were implemented directly against the
> design spec. Where this plan's illustrative test code differs from what was
> committed, the committed tests are authoritative — several fixtures here were
> written before checking that `create_*` tools generate their own UUIDs and that
> `subtype` is mandatory. See `docs/PHASE4_IMPLEMENTED_REQUIREMENTS.md` for what
> was actually delivered.

**Goal:** Build `r210_review_cli/` — a twelve-command local CLI that lets a human review extracted artifacts through the same validation logic the MCP server uses, with no network capability whatsoever.

**Architecture:** The CLI is a thin shell over the Phase 3 tool surface. `bridge.py` builds a `ToolContext` with `adapter_mode="review"` and calls `r210_mcp.tools.registry.dispatch`; `commands/*.py` translate argv into bridge calls; `display.py` turns response dicts into terminal text. Nothing in the CLI imports `r210_mcp.server`, because that module imports the `mcp` SDK and would break the SRS-123 isolation guarantee (see DEV-40 in the design spec).

**Tech Stack:** Python 3.11+, stdlib only (`argparse`, `sqlite3` transitively), pytest.

**Spec:** `docs/superpowers/specs/2026-08-15-phase4-5-generator-and-review-cli-design.md` §3
**Governing document:** `lld/LLD_06_Local_Review_CLI.md`

## Global Constraints

- `requires-python = ">=3.11"`. No runtime dependency may be added for this part — stdlib only.
- Every module docstring ends with a `See: LLD-06 §x` line. Every test docstring cites the `SRS-nnn` it verifies.
- `python -m pytest tests/ -q -p no:cacheprovider` must pass (652 tests today; the count only grows).
- `python -m ruff check src tests` must be clean.
- `python -m mypy src` must be clean under strict mode. `mypy tests` is **not** a gate (≈36 pre-existing errors in Phase 1 test files).
- This machine denies creation of `.pytest_cache`; always pass `-p no:cacheprovider`.
- **No delete path.** Never add a `DELETE`, and never import `r210_db_init.dev_reset` from `r210_review_cli`.
- **No network.** `r210_review_cli/` must not import `google.generativeai`, `google.genai`, `requests`, `httpx`, `urllib`, `aiohttp`, `websockets`, `socket`, `http`, or `mcp` — directly or transitively.
- **Identifiers are allowlisted, values are bound.** Any new SQL resolves table/column names through `DAL_TABLES` / `TABLE_COLUMNS` and binds every value with `?`.
- Tests assert against a real migrated SQLite database (`initialized_db` fixture), never mocks.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/r210_mcp/db/dal.py` | +`search_by_name_pattern` — the only new SQL | 1 |
| `src/r210_review_cli/bridge.py` | `ReviewToolBridge`: the single seam onto `tools/registry` | 2 |
| `src/r210_review_cli/display.py` | `DisplayFormatter`: response dict → terminal text | 3 |
| `src/r210_review_cli/commands/query.py` | `list`, `show`, `search`, `stats`; entity alias map | 4 |
| `src/r210_review_cli/commands/status.py` | `approve`, `reject`, `mark` | 5 |
| `src/r210_review_cli/commands/issues.py` | `resolve`, `dismiss`, `reopen` | 5 |
| `src/r210_review_cli/commands/generate.py` | `report`, `generate` | 6 |
| `src/r210_review_cli/cli.py` | argparse tree, dispatch, exit codes | 6 |
| `tests/test_r210_review_cli/test_isolation.py` | Adversarial SRS-123 verification | 7 |

Commands are split by responsibility (query / status change / issue lifecycle / generation), matching LLD-06 §3's module list. `bridge.py` is an addition to that list — DEV-41.

---

## Task 1: `DAL.search_by_name_pattern`

Closes `PHASE4_SCOPE.md` §5.1. The DAL does exact equality only; `search --name <pattern>` needs pattern matching.

**Files:**
- Modify: `src/r210_mcp/db/dal.py` (add after `find_duplicates_by_name`, ~line 910)
- Test: `tests/test_r210_mcp/test_dal_search.py` (create)

**Interfaces:**
- Consumes: `DataAccessLayer._check_table`, `._select_list`, `._order_by`, `._to_record`, `TABLE_COLUMNS`, `TABLE_RECORD_MAP` — all already in `dal.py`.
- Produces: `DataAccessLayer.search_by_name_pattern(conn: sqlite3.Connection, table: str, pattern: str) -> list[Any]` — used by Task 2's `ReviewToolBridge.search`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_dal_search.py`:

```python
"""Pattern search over the name column (SRS-118 reviewer inspection)."""

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer


@pytest.fixture
def seeded(initialized_db: str) -> str:
    """Three type definitions with names that differ only by case and prefix."""
    db = DatabaseConnection(initialized_db)
    dal = DataAccessLayer()
    with db.transaction() as conn:
        for key, name in [
            ("11111111-1111-4111-8111-111111111111", "SensorData"),
            ("22222222-2222-4222-8222-222222222222", "sensorConfig"),
            ("33333333-3333-4333-8333-333333333333", "MotorState"),
        ]:
            dal.insert_record(
                conn,
                "TypeDefinitions",
                {"unique_key": key, "name": name, "kind": "struct", "status": "pending_review"},
            )
    return initialized_db


class TestSearchByNamePattern:
    """SRS-118: the reviewer inspects artifacts by name pattern."""

    def test_matches_case_insensitively(self, seeded: str) -> None:
        """SRS-118: 'sensor%' finds both SensorData and sensorConfig."""
        db = DatabaseConnection(seeded)
        dal = DataAccessLayer()
        with db.read_only() as conn:
            found = dal.search_by_name_pattern(conn, "TypeDefinitions", "sensor%")
        assert [r.name for r in found] == ["SensorData", "sensorConfig"]

    def test_non_matching_pattern_returns_empty(self, seeded: str) -> None:
        """SRS-118: a pattern matching nothing yields no rows, not an error."""
        db = DatabaseConnection(seeded)
        dal = DataAccessLayer()
        with db.read_only() as conn:
            assert dal.search_by_name_pattern(conn, "TypeDefinitions", "zzz%") == []

    def test_unknown_table_rejected(self, seeded: str) -> None:
        """SRS-113: identifiers are allowlisted, never interpolated."""
        db = DatabaseConnection(seeded)
        dal = DataAccessLayer()
        with db.read_only() as conn:
            with pytest.raises(ValueError):
                dal.search_by_name_pattern(conn, "TypeDefinitions; DROP TABLE x", "a%")

    def test_table_without_name_column_rejected(self, seeded: str) -> None:
        """SRS-113: a table with no name column is a programming error."""
        db = DatabaseConnection(seeded)
        dal = DataAccessLayer()
        with db.read_only() as conn:
            with pytest.raises(ValueError, match="no name column"):
                dal.search_by_name_pattern(conn, "PortConnections", "a%")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_dal_search.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: 'DataAccessLayer' object has no attribute 'search_by_name_pattern'`

- [ ] **Step 3: Write minimal implementation**

Insert into `src/r210_mcp/db/dal.py` immediately after `find_duplicates_by_name`:

```python
    def search_by_name_pattern(
        self, conn: sqlite3.Connection, table: str, pattern: str
    ) -> list[Any]:
        """Case-insensitive `LIKE` search on `name`, for the review CLI (SRS-118).

        Mirrors `find_duplicates_by_name`: the table is resolved through the
        allowlist, `name` presence is checked against `TABLE_COLUMNS`, and the
        pattern is bound rather than interpolated. `COLLATE NOCASE` matches the
        indexes V001 created for name lookups.
        """
        self._check_table(table)
        if "name" not in TABLE_COLUMNS[table]:
            raise ValueError(f"{table} has no name column")

        sql = (
            f"SELECT {self._select_list(table)} FROM \"{table}\" "
            f'WHERE "name" LIKE ? COLLATE NOCASE ORDER BY {self._order_by(table)}'
        )
        record_type = TABLE_RECORD_MAP[table]
        return [self._to_record(record_type, row) for row in conn.execute(sql, [pattern]).fetchall()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_dal_search.py -q -p no:cacheprovider`
Expected: PASS — 4 passed

- [ ] **Step 5: Run the gates**

Run: `python -m ruff check src tests && python -m mypy src`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add src/r210_mcp/db/dal.py tests/test_r210_mcp/test_dal_search.py
git commit -m "feat(dal): add case-insensitive name pattern search"
```

---

## Task 2: `ReviewToolBridge`

The one seam between the CLI and the tool surface. Every command goes through it.

**Files:**
- Create: `src/r210_review_cli/bridge.py`
- Test: `tests/test_r210_review_cli/test_bridge.py`
- Create: `tests/test_r210_review_cli/__init__.py` (empty)

**Interfaces:**
- Consumes: `r210_mcp.tools.context.build_context(db_path, adapter_mode) -> ToolContext`; `r210_mcp.tools.registry.{dispatch, query_by_table, get_children_for_display, get_stats}`; `r210_mcp.db.connection.DatabaseConnection`; `r210_mcp.db.dal.DataAccessLayer.search_by_name_pattern` (Task 1); `r210_mcp.tools._engine.record_to_dict`.
- Produces: `ReviewToolBridge` with methods `set_review_status`, `update_review_issue`, `query`, `search`, `show`, `stats`, `generate` — all returning `dict[str, Any]` except `query`/`search` which return `list[dict[str, Any]]`. Tasks 4, 5 and 6 call these.

Response shapes come from `r210_mcp/errors.py`: success is `{"result": {...}}`, failure is `{"error": {"operation", "field", "reason", "affected_key"}}`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_review_cli/__init__.py` (empty file), then `tests/test_r210_review_cli/test_bridge.py`:

```python
"""ReviewToolBridge — direct tool invocation without MCP transport (SRS-123)."""

from typing import Any

import pytest

from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import dispatch
from r210_review_cli.bridge import ReviewToolBridge

KEY_TD = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def seeded(initialized_db: str) -> str:
    """One approved-eligible type definition and one pending review issue."""
    ctx = build_context(initialized_db, adapter_mode="extraction")
    dispatch(ctx, "create_type_definition", {
        "unique_key": KEY_TD, "name": "SensorData", "kind": "struct",
    })
    dispatch(ctx, "create_review_issue", {
        "issue_type": "incomplete", "message": "units not stated",
    })
    return initialized_db


class TestBridgeAuthority:
    """SRS-082a: the review adapter may approve; the extraction adapter may not."""

    def test_bridge_can_approve(self, seeded: str) -> None:
        """SRS-082a: adapter_mode='review' structurally permits approval."""
        bridge = ReviewToolBridge(seeded)
        result = bridge.set_review_status(KEY_TD, "approved")
        assert "error" not in result, result

    def test_bridge_passes_caller_review(self, seeded: str) -> None:
        """SRS-082a: caller must match adapter_mode or the tool rejects it."""
        bridge = ReviewToolBridge(seeded)
        result = bridge.set_review_status(KEY_TD, "ambiguous")
        assert result["result"]["unique_key"] == KEY_TD


class TestBridgeProjection:
    """SRS-015a: review mode returns full records, not Gemini projections."""

    def test_query_returns_full_records(self, seeded: str) -> None:
        """SRS-015a: projection applies to extraction only, so name is present."""
        bridge = ReviewToolBridge(seeded)
        records = bridge.query("TypeDefinitions")
        assert records[0]["name"] == "SensorData"


class TestBridgeShow:
    """SRS-087: resolve a key to its table, record and children."""

    def test_show_returns_table_and_children(self, seeded: str) -> None:
        """SRS-087: show resolves the owning table and attaches children."""
        bridge = ReviewToolBridge(seeded)
        result = bridge.show(KEY_TD)
        assert result["result"]["table"] == "TypeDefinitions"
        assert result["result"]["children"] == []

    def test_show_unknown_key_returns_error(self, seeded: str) -> None:
        """SRS-109: an unresolvable key yields a structured error, not a raise."""
        bridge = ReviewToolBridge(seeded)
        result = bridge.show("99999999-9999-4999-8999-999999999999")
        assert result["error"]["operation"] == "resolve_reference"


class TestBridgeSearchAndStats:
    """SRS-118: the reviewer inspects the database without writing SQL."""

    def test_search_matches_case_insensitively(self, seeded: str) -> None:
        """SRS-118: search finds a record by a lowercase prefix pattern."""
        bridge = ReviewToolBridge(seeded)
        assert [r["name"] for r in bridge.search("TypeDefinitions", "sensor%")] == ["SensorData"]

    def test_stats_counts_every_table(self, seeded: str) -> None:
        """SRS-118: stats reports totals and status breakdowns per table."""
        bridge = ReviewToolBridge(seeded)
        stats: dict[str, Any] = bridge.stats()
        assert stats["TypeDefinitions"]["total"] == 1
        assert stats["TypeDefinitions"]["by_status"] == {"pending_review": 1}


class TestBridgeHasNoCreateOrDelete:
    """SRS-091: the review surface exposes no creation and no deletion."""

    def test_bridge_exposes_no_create_or_delete(self) -> None:
        """SRS-091/SRS-093: neither verb appears in the bridge's public API."""
        public = {n for n in dir(ReviewToolBridge) if not n.startswith("_")}
        assert not {n for n in public if "create" in n or "delete" in n}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_review_cli/test_bridge.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'r210_review_cli.bridge'`

- [ ] **Step 3: Write minimal implementation**

Create `src/r210_review_cli/bridge.py`:

```python
"""Direct invocation of the MCP tool handlers, without MCP transport.

LLD-06 §5.1 imports `R210McpServer`. That module imports the `mcp` SDK, which
would both break in an environment without the SDK and violate LLD-06 §7's own
network-isolation rule. Phase 3 made the handlers plain functions over a
`ToolContext` (DEV-26) precisely so this layer could exist; the bridge targets
`tools/registry` instead (DEV-40). Every guarantee §5.2 asks for is preserved:
identical validation, identical transactions, identical errors.

See: LLD-06 §5 (Tool Invocation Layer)
"""

from typing import Any

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.tools._engine import record_to_dict
from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import (
    dispatch,
    get_children_for_display,
    get_stats,
    query_by_table,
)

# Entity type → the table a dedicated query tool covers (LLD-06 §5.2).
QUERY_TOOLS: dict[str, str] = {
    "SourceRequirements": "query_source_requirements",
    "TypeDefinitions": "query_type_definitions",
    "PortInterfaces": "query_port_interfaces",
    "PortPrototypes": "query_port_prototypes",
    "PortConnections": "query_port_connections",
    "ReviewIssues": "query_review_issues",
}


class ReviewToolBridge:
    """Invoke tool handlers directly, with review authority (SRS-082a, SRS-123).

    Provides no create operations (extraction's job) and no delete operations
    (never exposed — SRS-091, SRS-093).
    """

    def __init__(self, db_path: str) -> None:
        self._ctx = build_context(db_path, adapter_mode="review")
        self._db = DatabaseConnection(db_path)
        self._dal = DataAccessLayer()

    def set_review_status(
        self,
        unique_key: str,
        new_status: str,
        table_hint: str | None = None,
        review_note: str | None = None,
    ) -> dict[str, Any]:
        """Set an artifact's review state (SRS-089)."""
        args: dict[str, Any] = {
            "unique_key": unique_key,
            "new_status": new_status,
            "caller": "review",
        }
        if table_hint is not None:
            args["table_hint"] = table_hint
        if review_note is not None:
            args["review_note"] = review_note
        return dispatch(self._ctx, "set_review_status", args)

    def update_review_issue(
        self,
        unique_key: str,
        status: str | None = None,
        resolution: str | None = None,
    ) -> dict[str, Any]:
        """Change an issue's lifecycle state (SRS-119)."""
        args: dict[str, Any] = {"unique_key": unique_key}
        if status is not None:
            args["status"] = status
        if resolution is not None:
            args["resolution"] = resolution
        return dispatch(self._ctx, "update_review_issue", args)

    def query(
        self, table: str, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """List records, preferring the dedicated query tool when one exists."""
        tool = QUERY_TOOLS.get(table)
        if tool is None:
            return query_by_table(self._ctx, table, filters)
        response = dispatch(self._ctx, tool, filters or {})
        if "error" in response:
            return []
        records: list[dict[str, Any]] = response["result"]["records"]
        return records

    def search(self, table: str, pattern: str) -> list[dict[str, Any]]:
        """Case-insensitive name search (SRS-118)."""
        with self._db.read_only() as conn:
            records = self._dal.search_by_name_pattern(conn, table, pattern)
        return [record_to_dict(record) for record in records]

    def show(self, unique_key: str) -> dict[str, Any]:
        """Resolve a key to its table and record, with children attached."""
        response = dispatch(self._ctx, "resolve_reference", {"unique_key": unique_key})
        if "error" in response:
            return response
        result = response["result"]
        record_id = result["record"].get("id")
        result["children"] = (
            get_children_for_display(self._ctx, result["table"], int(record_id))
            if record_id is not None
            else []
        )
        return response

    def stats(self) -> dict[str, Any]:
        """Row and status counts per table (SRS-118)."""
        return get_stats(self._ctx)

    def generate(self, mode: str) -> dict[str, Any]:
        """Trigger generation (SRS-090). Part 3 makes report_only operative."""
        return dispatch(self._ctx, "trigger_generation", {"mode": mode})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_review_cli/test_bridge.py -q -p no:cacheprovider`
Expected: PASS — 8 passed

If `test_show_returns_table_and_children` fails because `resolve_reference` pops `id` from its payload (it does — see `reference.py`), fix `show` to re-resolve the id through the DAL rather than reading it from the response:

```python
        with self._db.read_only() as conn:
            found = self._dal.resolve_unique_key(conn, unique_key)
        result["children"] = (
            get_children_for_display(self._ctx, found[0], int(found[1].id))
            if found is not None
            else []
        )
```

- [ ] **Step 5: Run the gates**

Run: `python -m ruff check src tests && python -m mypy src`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add src/r210_review_cli/bridge.py tests/test_r210_review_cli/
git commit -m "feat(review-cli): add ReviewToolBridge over tools/registry"
```

---

## Task 3: `DisplayFormatter`

**Files:**
- Modify: `src/r210_review_cli/display.py` (currently docstring-only)
- Test: `tests/test_r210_review_cli/test_display.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — pure formatting over plain dicts.
- Produces: `DisplayFormatter(color: bool = False)` with `format_list(records, table) -> str`, `format_detail(result) -> str`, `format_stats(stats) -> str`, `format_result(response) -> str`, and module constant `STATUS_GLYPH`. Tasks 4, 5 and 6 call these.

Colour is decided by the *caller* (Task 6 passes `sys.stdout.isatty()`), so the formatter itself stays deterministic and testable — DEV-44.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_review_cli/test_display.py`:

```python
"""Terminal formatting for the review CLI (SRS-118)."""

from r210_review_cli.display import DisplayFormatter


class TestFormatList:
    """SRS-118: the reviewer sees artifacts in a scannable table."""

    def test_list_has_header_and_one_row_per_record(self) -> None:
        """SRS-118: a header line plus one row per record."""
        fmt = DisplayFormatter(color=False)
        out = fmt.format_list(
            [
                {"unique_key": "a" * 8 + "-x", "name": "SensorData", "status": "approved"},
                {"unique_key": "b" * 8 + "-y", "name": "MotorState", "status": "rejected"},
            ],
            "TypeDefinitions",
        )
        lines = out.splitlines()
        assert "TypeDefinitions (2 records)" in lines[0]
        assert "SensorData" in out and "MotorState" in out

    def test_empty_list_says_so(self) -> None:
        """SRS-118: an empty result is stated, not printed as a blank table."""
        fmt = DisplayFormatter(color=False)
        assert "0 records" in fmt.format_list([], "TypeDefinitions")


class TestColorGating:
    """SRS-118: redirected output must stay plain text (DEV-44)."""

    def test_no_ansi_when_color_disabled(self) -> None:
        """SRS-118: escape sequences never reach a pipe or file."""
        fmt = DisplayFormatter(color=False)
        out = fmt.format_list(
            [{"unique_key": "k", "name": "N", "status": "approved"}], "TypeDefinitions"
        )
        assert "\x1b[" not in out

    def test_ansi_present_when_color_enabled(self) -> None:
        """SRS-118: a terminal gets colour."""
        fmt = DisplayFormatter(color=True)
        out = fmt.format_list(
            [{"unique_key": "k", "name": "N", "status": "approved"}], "TypeDefinitions"
        )
        assert "\x1b[" in out


class TestFormatResult:
    """SRS-109: errors and demotions are surfaced, never swallowed."""

    def test_error_response_is_marked(self) -> None:
        """SRS-109: an error response prints its reason."""
        fmt = DisplayFormatter(color=False)
        out = fmt.format_result(
            {"error": {"operation": "set_review_status", "field": "new_status",
                       "reason": "bad transition", "affected_key": "k"}}
        )
        assert "set_review_status" in out and "bad transition" in out

    def test_demoted_parents_are_reported(self) -> None:
        """SRS-035c: auto-demoted parents must be visible to the reviewer."""
        fmt = DisplayFormatter(color=False)
        out = fmt.format_result(
            {"result": {"unique_key": "k", "status": "rejected", "demoted": ["p1", "p2"]}}
        )
        assert "p1" in out and "p2" in out


class TestFormatStats:
    """SRS-118: database statistics summarise review progress."""

    def test_stats_lists_tables_with_totals(self) -> None:
        """SRS-118: each table's total and status breakdown appear."""
        fmt = DisplayFormatter(color=False)
        out = fmt.format_stats(
            {"TypeDefinitions": {"total": 3, "by_status": {"approved": 1, "pending_review": 2}}}
        )
        assert "TypeDefinitions" in out and "3" in out and "approved" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_review_cli/test_display.py -q -p no:cacheprovider`
Expected: FAIL — `ImportError: cannot import name 'DisplayFormatter'`

- [ ] **Step 3: Write minimal implementation**

Replace `src/r210_review_cli/display.py` with:

```python
"""Output formatting for terminal display.

ANSI colour is a constructor flag rather than an ambient decision, so the
formatter is deterministic under test and the caller (cli.py) can gate it on
`sys.stdout.isatty()` — redirected output must stay plain text (DEV-44).

See: LLD-06 §6 (Display Formatting)
"""

from typing import Any

# LLD-06 §6.1. Values are ANSI SGR codes rather than colour names.
STATUS_COLORS: dict[str, str] = {
    "pending_review": "33",
    "approved": "32",
    "rejected": "31",
    "ambiguous": "35",
    "out_of_scope": "36",
    "pending": "33",
    "resolved": "32",
}

STATUS_GLYPH = "■"  # ■
_RESET = "\x1b[0m"
_RULE = "─" * 62


class DisplayFormatter:
    """Format tool responses for terminal output (LLD-06 §6)."""

    def __init__(self, color: bool = False) -> None:
        self._color = color

    def _status(self, status: str | None) -> str:
        """Render a status with its glyph, coloured only when enabled."""
        if status is None:
            return ""
        text = f"{STATUS_GLYPH} {status}"
        code = STATUS_COLORS.get(status)
        if self._color and code is not None:
            return f"\x1b[{code}m{text}{_RESET}"
        return text

    def format_list(self, records: list[dict[str, Any]], table: str) -> str:
        """One header line, a rule, then one row per record."""
        lines = [f"{table} ({len(records)} records)", _RULE]
        if not records:
            return "\n".join(lines)
        lines.append(f"{'UUID':<38}{'Name':<20}Status")
        for record in records:
            key = str(record.get("unique_key", ""))
            name = str(record.get("name") or record.get("description") or "")
            lines.append(f"{key:<38}{name:<20}{self._status(record.get('status'))}")
        return "\n".join(lines)

    def format_detail(self, result: dict[str, Any]) -> str:
        """A single record's fields, with its children nested underneath."""
        payload = result.get("result", result)
        record: dict[str, Any] = payload.get("record", {})
        lines = [f"{payload.get('table', '')} {payload.get('unique_key', '')}", _RULE]
        for name, value in record.items():
            if name == "id":
                continue
            rendered = self._status(value) if name == "status" else str(value)
            lines.append(f"  {name + ':':<22}{rendered}")
        children: list[dict[str, Any]] = payload.get("children", [])
        if children:
            lines.extend(["", f"  Children: {len(children)} records", f"  {_RULE}"])
            for index, child in enumerate(children, start=1):
                body = child["record"]
                label = body.get("name") or body.get("description") or ""
                lines.append(
                    f"  {index:<3}{child['table']:<26}{label:<20}"
                    f"{self._status(body.get('status'))}"
                )
        return "\n".join(lines)

    def format_stats(self, stats: dict[str, Any]) -> str:
        """Totals and status breakdown, one block per table."""
        lines = ["Database statistics", _RULE]
        for table in sorted(stats):
            entry = stats[table]
            lines.append(f"{table:<28}{entry['total']:>6}")
            for status in sorted(entry["by_status"]):
                lines.append(f"    {status:<24}{entry['by_status'][status]:>6}")
        return "\n".join(lines)

    def format_result(self, response: dict[str, Any]) -> str:
        """A command outcome: either a structured error or a success summary."""
        if "error" in response:
            error = response["error"]
            parts = [f"✗ {error['operation']}: {error['reason']}"]
            if error.get("field"):
                parts.append(f"  field: {error['field']}")
            if error.get("affected_key"):
                parts.append(f"  key:   {error['affected_key']}")
            return "\n".join(parts)

        result = response.get("result", {})
        lines = [f"✓ {result.get('unique_key', '')}"]
        if result.get("status") is not None:
            lines.append(f"  status: {self._status(result['status'])}")
        for key in ("demoted", "warnings"):
            for item in result.get(key, []):
                lines.append(f"  ⚠ {key[:-1]}: {item}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_review_cli/test_display.py -q -p no:cacheprovider`
Expected: PASS — 7 passed

- [ ] **Step 5: Run the gates**

Run: `python -m ruff check src tests && python -m mypy src`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add src/r210_review_cli/display.py tests/test_r210_review_cli/test_display.py
git commit -m "feat(review-cli): add DisplayFormatter with isatty-gated colour"
```

---

## Task 4: Query commands — `list`, `show`, `search`, `stats`

**Files:**
- Modify: `src/r210_review_cli/commands/query.py`
- Test: `tests/test_r210_review_cli/test_commands_query.py`

**Interfaces:**
- Consumes: `ReviewToolBridge` (Task 2), `DisplayFormatter` (Task 3).
- Produces: `ENTITY_TABLES: dict[str, str]`, `resolve_entity(alias) -> str`, and four functions `cmd_list`, `cmd_show`, `cmd_search`, `cmd_stats`, each `(bridge, fmt, args: argparse.Namespace) -> tuple[str, int]` returning `(text_to_print, exit_code)`. Task 6's `cli.py` calls them.

Returning `(text, exit_code)` rather than printing keeps the commands testable without capturing stdout.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_review_cli/test_commands_query.py`:

```python
"""Query commands: list, show, search, stats (SRS-118)."""

import argparse

import pytest

from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import dispatch
from r210_review_cli.bridge import ReviewToolBridge
from r210_review_cli.commands import query
from r210_review_cli.display import DisplayFormatter

KEY_TD = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def seeded(initialized_db: str) -> str:
    """One struct type definition."""
    ctx = build_context(initialized_db, adapter_mode="extraction")
    dispatch(ctx, "create_type_definition", {
        "unique_key": KEY_TD, "name": "SensorData", "kind": "struct",
    })
    return initialized_db


def _args(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


class TestEntityAliases:
    """LLD-06 §4.2: six entity types, each with a short alias."""

    def test_every_alias_resolves(self) -> None:
        """SRS-118: both long and short forms address the same table."""
        assert query.resolve_entity("types") == query.resolve_entity("td") == "TypeDefinitions"
        assert query.resolve_entity("issues") == query.resolve_entity("ri") == "ReviewIssues"

    def test_all_six_entities_present(self) -> None:
        """LLD-06 §4.2: exactly six entity types, twelve spellings."""
        assert len(set(query.ENTITY_TABLES.values())) == 6
        assert len(query.ENTITY_TABLES) == 12


class TestListCommand:
    """SRS-118: the reviewer lists artifacts by type."""

    def test_list_returns_records_and_zero_exit(self, seeded: str) -> None:
        """SRS-118: listing a populated table succeeds."""
        text, code = query.cmd_list(
            ReviewToolBridge(seeded), DisplayFormatter(),
            _args(entity_type="td", status=None, kind=None, issue_type=None),
        )
        assert code == 0
        assert "SensorData" in text

    def test_list_filters_by_status(self, seeded: str) -> None:
        """SRS-118: --status narrows the result set."""
        text, code = query.cmd_list(
            ReviewToolBridge(seeded), DisplayFormatter(),
            _args(entity_type="td", status="approved", kind=None, issue_type=None),
        )
        assert code == 0
        assert "0 records" in text


class TestShowCommand:
    """SRS-087: show resolves a key to its record."""

    def test_show_known_key(self, seeded: str) -> None:
        """SRS-087: a known key prints its table and fields."""
        text, code = query.cmd_show(
            ReviewToolBridge(seeded), DisplayFormatter(), _args(unique_key=KEY_TD)
        )
        assert code == 0
        assert "TypeDefinitions" in text

    def test_show_unknown_key_exits_one(self, seeded: str) -> None:
        """SRS-109: an unresolvable key is an error, exit code 1."""
        text, code = query.cmd_show(
            ReviewToolBridge(seeded), DisplayFormatter(),
            _args(unique_key="99999999-9999-4999-8999-999999999999"),
        )
        assert code == 1
        assert "resolve_reference" in text


class TestSearchAndStats:
    """SRS-118: name search and database statistics."""

    def test_search_finds_by_pattern(self, seeded: str) -> None:
        """SRS-118: a lowercase prefix matches a mixed-case name."""
        text, code = query.cmd_search(
            ReviewToolBridge(seeded), DisplayFormatter(),
            _args(entity_type="td", name="sensor%"),
        )
        assert code == 0
        assert "SensorData" in text

    def test_stats_reports_totals(self, seeded: str) -> None:
        """SRS-118: stats includes every table."""
        text, code = query.cmd_stats(ReviewToolBridge(seeded), DisplayFormatter(), _args())
        assert code == 0
        assert "TypeDefinitions" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_review_cli/test_commands_query.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'r210_review_cli.commands.query' has no attribute 'resolve_entity'`

- [ ] **Step 3: Write minimal implementation**

Replace `src/r210_review_cli/commands/query.py` with:

```python
"""Query commands: list, show, search, stats.

Each command returns `(text, exit_code)` rather than printing, so that the
whole command surface is testable without capturing stdout.

See: LLD-06 §6.1 (Query Commands)
"""

import argparse
from typing import Any

from ..bridge import ReviewToolBridge
from ..display import DisplayFormatter

# LLD-06 §4.2. Both the long form and the alias map to the same table.
ENTITY_TABLES: dict[str, str] = {
    "sources": "SourceRequirements",
    "src": "SourceRequirements",
    "types": "TypeDefinitions",
    "td": "TypeDefinitions",
    "interfaces": "PortInterfaces",
    "pi": "PortInterfaces",
    "prototypes": "PortPrototypes",
    "pp": "PortPrototypes",
    "connections": "PortConnections",
    "pc": "PortConnections",
    "issues": "ReviewIssues",
    "ri": "ReviewIssues",
}


def resolve_entity(alias: str) -> str:
    """Map an entity type or alias to its table name (LLD-06 §4.2)."""
    table = ENTITY_TABLES.get(alias)
    if table is None:
        raise KeyError(f"unknown entity type: {alias}")
    return table


def _filters(args: argparse.Namespace) -> dict[str, Any]:
    """Collect the optional --status/--kind/--issue-type filters."""
    filters: dict[str, Any] = {}
    for attribute, field in (("status", "status"), ("kind", "kind"), ("issue_type", "issue_type")):
        value = getattr(args, attribute, None)
        if value is not None:
            filters[field] = value
    return filters


def cmd_list(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """List artifacts or issues by type (SRS-118)."""
    table = resolve_entity(args.entity_type)
    return fmt.format_list(bridge.query(table, _filters(args)), table), 0


def cmd_show(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Show one record with its children (SRS-087)."""
    response = bridge.show(args.unique_key)
    if "error" in response:
        return fmt.format_result(response), 1
    return fmt.format_detail(response), 0


def cmd_search(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Search a table by name pattern (SRS-118)."""
    table = resolve_entity(args.entity_type)
    return fmt.format_list(bridge.search(table, args.name), table), 0


def cmd_stats(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Report row and status counts per table (SRS-118)."""
    return fmt.format_stats(bridge.stats()), 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_review_cli/test_commands_query.py -q -p no:cacheprovider`
Expected: PASS — 8 passed

- [ ] **Step 5: Run the gates**

Run: `python -m ruff check src tests && python -m mypy src`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add src/r210_review_cli/commands/query.py tests/test_r210_review_cli/test_commands_query.py
git commit -m "feat(review-cli): add list, show, search and stats commands"
```

---

## Task 5: Status and issue commands

`approve`/`reject`/`mark` in `status.py`; `resolve`/`dismiss`/`reopen` in `issues.py`. Both are thin — the validation lives in the tool handlers, which is the point of SRS-123.

Issue lifecycle mapping (`ISSUE_STATUSES` is `{"pending", "resolved", "rejected"}`):

| Command | `update_review_issue` arguments |
|---|---|
| `resolve` | `status="resolved"`, `resolution=<text>` |
| `dismiss` | `status="rejected"` |
| `reopen` | `status="pending"` |

**Files:**
- Modify: `src/r210_review_cli/commands/status.py`
- Modify: `src/r210_review_cli/commands/issues.py`
- Test: `tests/test_r210_review_cli/test_commands_status.py`

**Interfaces:**
- Consumes: `ReviewToolBridge` (Task 2), `DisplayFormatter` (Task 3).
- Produces: `status.cmd_approve`, `status.cmd_reject`, `status.cmd_mark`, `issues.cmd_resolve`, `issues.cmd_dismiss`, `issues.cmd_reopen` — all `(bridge, fmt, args) -> tuple[str, int]`. Task 6 calls them.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_review_cli/test_commands_status.py`:

```python
"""Status and issue-lifecycle commands (SRS-089, SRS-119)."""

import argparse

import pytest

from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import dispatch
from r210_review_cli.bridge import ReviewToolBridge
from r210_review_cli.commands import issues, status
from r210_review_cli.display import DisplayFormatter

KEY_TD = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def seeded(initialized_db: str) -> tuple[str, str]:
    """A type definition and a pending review issue; returns (db_path, issue_key)."""
    ctx = build_context(initialized_db, adapter_mode="extraction")
    dispatch(ctx, "create_type_definition", {
        "unique_key": KEY_TD, "name": "SensorData", "kind": "struct",
    })
    created = dispatch(ctx, "create_review_issue", {
        "issue_type": "incomplete", "message": "units not stated",
    })
    return initialized_db, created["result"]["unique_key"]


def _args(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


class TestStatusCommands:
    """SRS-089: the reviewer sets artifact review state."""

    def test_approve_succeeds(self, seeded: tuple[str, str]) -> None:
        """SRS-082a: review authority permits approval."""
        db, _ = seeded
        text, code = status.cmd_approve(
            ReviewToolBridge(db), DisplayFormatter(), _args(unique_key=KEY_TD, note=None)
        )
        assert code == 0
        assert "✓" in text

    def test_reject_records_the_note(self, seeded: tuple[str, str]) -> None:
        """SRS-089: --note is passed through as review_note."""
        db, _ = seeded
        text, code = status.cmd_reject(
            ReviewToolBridge(db), DisplayFormatter(),
            _args(unique_key=KEY_TD, note="wrong units"),
        )
        assert code == 0

    def test_mark_rejects_an_invalid_transition(self, seeded: tuple[str, str]) -> None:
        """SRS-035b: an impermissible transition fails with exit code 1."""
        db, _ = seeded
        bridge = ReviewToolBridge(db)
        status.cmd_mark(bridge, DisplayFormatter(),
                        _args(unique_key=KEY_TD, status="out_of_scope", note=None))
        text, code = status.cmd_mark(
            bridge, DisplayFormatter(),
            _args(unique_key=KEY_TD, status="approved", note=None),
        )
        assert code == 1
        assert "set_review_status" in text

    def test_unknown_key_exits_one(self, seeded: tuple[str, str]) -> None:
        """SRS-109: an unresolvable key is a structured error."""
        db, _ = seeded
        text, code = status.cmd_approve(
            ReviewToolBridge(db), DisplayFormatter(),
            _args(unique_key="99999999-9999-4999-8999-999999999999", note=None),
        )
        assert code == 1


class TestIssueCommands:
    """SRS-119: issues move pending → resolved / rejected → pending."""

    def test_resolve_sets_resolved_and_text(self, seeded: tuple[str, str]) -> None:
        """SRS-119: resolve records the resolution text."""
        db, issue_key = seeded
        text, code = issues.cmd_resolve(
            ReviewToolBridge(db), DisplayFormatter(),
            _args(unique_key=issue_key, resolution="units are mV"),
        )
        assert code == 0

    def test_dismiss_then_reopen(self, seeded: tuple[str, str]) -> None:
        """SRS-119: a dismissed issue can be reopened."""
        db, issue_key = seeded
        bridge = ReviewToolBridge(db)
        _, dismiss_code = issues.cmd_dismiss(
            bridge, DisplayFormatter(), _args(unique_key=issue_key)
        )
        _, reopen_code = issues.cmd_reopen(
            bridge, DisplayFormatter(), _args(unique_key=issue_key)
        )
        assert (dismiss_code, reopen_code) == (0, 0)

    def test_set_review_status_refuses_issues(self, seeded: tuple[str, str]) -> None:
        """SRS-119: issue status goes through update_review_issue only."""
        db, issue_key = seeded
        text, code = status.cmd_approve(
            ReviewToolBridge(db), DisplayFormatter(), _args(unique_key=issue_key, note=None)
        )
        assert code == 1
        assert "update_review_issue" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_review_cli/test_commands_status.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module ... has no attribute 'cmd_approve'`

- [ ] **Step 3a: Write `status.py`**

Replace `src/r210_review_cli/commands/status.py` with:

```python
"""Status change commands: approve, reject, mark.

Every one delegates to `set_review_status` with `caller="review"`, so the
transition matrix (SRS-035b), the parent-approval check (SRS-046, SRS-053,
SRS-092a) and parent auto-demotion (SRS-035c) are enforced by the same code
the extraction adapter runs.

See: LLD-06 §6.2 (Status Commands)
"""

import argparse

from ..bridge import ReviewToolBridge
from ..display import DisplayFormatter


def _set(
    bridge: ReviewToolBridge,
    fmt: DisplayFormatter,
    unique_key: str,
    new_status: str,
    note: str | None,
) -> tuple[str, int]:
    """Apply one status change and render its outcome."""
    response = bridge.set_review_status(unique_key, new_status, review_note=note)
    return fmt.format_result(response), (1 if "error" in response else 0)


def cmd_approve(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Set status to approved (SRS-089)."""
    return _set(bridge, fmt, args.unique_key, "approved", args.note)


def cmd_reject(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Set status to rejected (SRS-089)."""
    return _set(bridge, fmt, args.unique_key, "rejected", args.note)


def cmd_mark(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Set any permitted status (SRS-089)."""
    return _set(bridge, fmt, args.unique_key, args.status, args.note)
```

- [ ] **Step 3b: Write `issues.py`**

Replace `src/r210_review_cli/commands/issues.py` with:

```python
"""Review issue lifecycle commands: resolve, dismiss, reopen.

`ISSUE_STATUSES` is {"pending", "resolved", "rejected"} (LLD-01), so the three
commands are three target states of one tool. Transition legality is checked by
`update_review_issue`, not here (SRS-119).

See: LLD-06 §6.3 (Issue Commands)
"""

import argparse

from ..bridge import ReviewToolBridge
from ..display import DisplayFormatter


def cmd_resolve(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Resolve an issue, recording its resolution text (SRS-119)."""
    response = bridge.update_review_issue(
        args.unique_key, status="resolved", resolution=args.resolution
    )
    return fmt.format_result(response), (1 if "error" in response else 0)


def cmd_dismiss(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Reject an issue without resolving it (SRS-119)."""
    response = bridge.update_review_issue(args.unique_key, status="rejected")
    return fmt.format_result(response), (1 if "error" in response else 0)


def cmd_reopen(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Return a resolved or rejected issue to pending (SRS-119)."""
    response = bridge.update_review_issue(args.unique_key, status="pending")
    return fmt.format_result(response), (1 if "error" in response else 0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_review_cli/test_commands_status.py -q -p no:cacheprovider`
Expected: PASS — 7 passed

- [ ] **Step 5: Run the gates**

Run: `python -m ruff check src tests && python -m mypy src`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add src/r210_review_cli/commands/status.py src/r210_review_cli/commands/issues.py tests/test_r210_review_cli/test_commands_status.py
git commit -m "feat(review-cli): add status and issue lifecycle commands"
```

---

## Task 6: `cli.py` — argparse tree, dispatch, exit codes

**Files:**
- Modify: `src/r210_review_cli/commands/generate.py`
- Modify: `src/r210_review_cli/cli.py` (replace the stub wholesale)
- Test: `tests/test_r210_review_cli/test_cli.py`

**Interfaces:**
- Consumes: every `cmd_*` from Tasks 4 and 5, `ReviewToolBridge`, `DisplayFormatter`.
- Produces: `generate.cmd_report`, `generate.cmd_generate`; `cli.build_parser() -> argparse.ArgumentParser`; `cli.run(argv: list[str] | None = None) -> int`; `cli.main() -> None` (the console-script entry point that calls `sys.exit(run())`).

`run()` returning an int rather than exiting is what makes the whole CLI testable in-process.

Exit codes (DEV-42): `0` success, `1` tool error, `2` argparse usage error.

**Note on `generate`/`report` in this part:** they route to `trigger_generation`, which still returns the DEV-31 "not yet implemented" error until Part 3. That is correct behaviour for this part — the commands work, the generator does not exist yet. The test asserts exit code 1 and the DEV-31 reason; Part 3 updates it.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_review_cli/test_cli.py`:

```python
"""CLI entry point: parsing, dispatch and exit codes (SRS-118, SRS-123)."""

import pytest

from r210_mcp.tools.context import build_context
from r210_mcp.tools.registry import dispatch
from r210_review_cli import cli

KEY_TD = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def seeded(initialized_db: str) -> str:
    """One struct type definition."""
    ctx = build_context(initialized_db, adapter_mode="extraction")
    dispatch(ctx, "create_type_definition", {
        "unique_key": KEY_TD, "name": "SensorData", "kind": "struct",
    })
    return initialized_db


class TestParser:
    """LLD-06 §4.1: twelve commands, not the stub docstring's nine."""

    def test_all_twelve_commands_registered(self) -> None:
        """SRS-118: every LLD-06 §4.1 command is reachable."""
        parser = cli.build_parser()
        actions = [a for a in parser._actions if hasattr(a, "choices") and a.dest == "command"]
        assert set(actions[0].choices) == {
            "list", "show", "search", "approve", "reject", "mark",
            "resolve", "dismiss", "reopen", "report", "generate", "stats",
        }

    def test_missing_command_exits_two(self) -> None:
        """SRS-118: a usage error is exit code 2, argparse's convention."""
        with pytest.raises(SystemExit) as exc:
            cli.build_parser().parse_args([])
        assert exc.value.code == 2


class TestRun:
    """SRS-118: commands run end to end against a real database."""

    def test_list_exits_zero(self, seeded: str, capsys: pytest.CaptureFixture[str]) -> None:
        """SRS-118: listing a populated table succeeds."""
        assert cli.run(["--db", seeded, "list", "td"]) == 0
        assert "SensorData" in capsys.readouterr().out

    def test_approve_then_show(self, seeded: str, capsys: pytest.CaptureFixture[str]) -> None:
        """SRS-082a: the CLI carries review authority."""
        assert cli.run(["--db", seeded, "approve", KEY_TD]) == 0
        assert cli.run(["--db", seeded, "show", KEY_TD]) == 0
        assert "approved" in capsys.readouterr().out

    def test_tool_error_exits_one(self, seeded: str) -> None:
        """SRS-109: a tool error becomes exit code 1."""
        assert cli.run(["--db", seeded, "show", "99999999-9999-4999-8999-999999999999"]) == 1

    def test_stats_exits_zero(self, seeded: str) -> None:
        """SRS-118: stats runs against every table."""
        assert cli.run(["--db", seeded, "stats"]) == 0


class TestGenerationNotYetWired:
    """SRS-090: the command exists; the generator arrives in Part 3."""

    def test_report_reports_unavailable(self, seeded: str, capsys: pytest.CaptureFixture[str]) -> None:
        """SRS-090: trigger_generation still reports the generator unavailable."""
        assert cli.run(["--db", seeded, "report"]) == 1
        assert "not yet implemented" in capsys.readouterr().out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_review_cli/test_cli.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'r210_review_cli.cli' has no attribute 'build_parser'`

- [ ] **Step 3a: Write `generate.py`**

Replace `src/r210_review_cli/commands/generate.py` with:

```python
"""Generation trigger commands: report, generate.

Both delegate to the `trigger_generation` tool. Until the generator lands
(LLD-04), that tool reports unavailability rather than pretending to succeed
(DEV-31), and these commands surface it faithfully.

See: LLD-06 §6.4 (Generate Commands)
"""

import argparse

from ..bridge import ReviewToolBridge
from ..display import DisplayFormatter


def cmd_report(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Generate the review report only (SRS-104)."""
    response = bridge.generate("report_only")
    return fmt.format_result(response), (1 if "error" in response else 0)


def cmd_generate(
    bridge: ReviewToolBridge, fmt: DisplayFormatter, args: argparse.Namespace
) -> tuple[str, int]:
    """Trigger generation in the requested mode (SRS-090)."""
    response = bridge.generate(args.mode)
    return fmt.format_result(response), (1 if "error" in response else 0)
```

- [ ] **Step 3b: Write `cli.py`**

Replace `src/r210_review_cli/cli.py` wholesale:

```python
"""CLI entry point and argument parsing.

Twelve commands, per LLD-06 §4.1. (The previous stub docstring listed nine; it
predated LLD-06 v1.2 and was stale.)

Usage:
    r210-review [--db <path>] <command> [arguments] [options]

Commands:
    list    <entity_type>                     List artifacts/issues by type
    show    <unique_key>                      Show detailed record
    search  <entity_type> --name <pattern>    Search by name
    approve <unique_key> [--note <text>]      Set status to approved
    reject  <unique_key> [--note <text>]      Set status to rejected
    mark    <unique_key> <status> [--note]    Set any valid status
    resolve <issue_key> --resolution <text>   Resolve a review issue
    dismiss <issue_key>                       Reject a review issue
    reopen  <issue_key>                       Reopen a resolved/rejected issue
    report  [--output <path>]                 Generate review report
    generate [--mode <mode>] [--output <dir>] Trigger R210 generation
    stats                                     Show database statistics

Exit codes: 0 success, 1 tool error, 2 usage error (DEV-42).

See: LLD-06 §4 (CLI Entry Point)
"""

import argparse
import sys
from collections.abc import Callable

from .bridge import ReviewToolBridge
from .commands import generate, issues, query, status
from .display import DisplayFormatter

ENTITY_CHOICES = [
    "sources", "src", "types", "td", "interfaces", "pi",
    "prototypes", "pp", "connections", "pc", "issues", "ri",
]

ARTIFACT_STATUS_CHOICES = [
    "pending_review", "approved", "rejected", "ambiguous", "out_of_scope",
]

Command = Callable[[ReviewToolBridge, DisplayFormatter, argparse.Namespace], tuple[str, int]]

COMMANDS: dict[str, Command] = {
    "list": query.cmd_list,
    "show": query.cmd_show,
    "search": query.cmd_search,
    "stats": query.cmd_stats,
    "approve": status.cmd_approve,
    "reject": status.cmd_reject,
    "mark": status.cmd_mark,
    "resolve": issues.cmd_resolve,
    "dismiss": issues.cmd_dismiss,
    "reopen": issues.cmd_reopen,
    "report": generate.cmd_report,
    "generate": generate.cmd_generate,
}


def build_parser() -> argparse.ArgumentParser:
    """Construct the full twelve-command parser (LLD-06 §4.3)."""
    parser = argparse.ArgumentParser(
        prog="r210-review",
        description="R210 Local Review CLI - review artifacts without Gemini API",
    )
    parser.add_argument("--db", default="r210.db", help="Path to SQLite database file")
    sub = parser.add_subparsers(dest="command", required=True)

    listp = sub.add_parser("list", help="List artifacts by type")
    listp.add_argument("entity_type", choices=ENTITY_CHOICES)
    listp.add_argument("--status", help="Filter by status")
    listp.add_argument("--kind", help="Filter by kind (types only)")
    listp.add_argument("--issue-type", dest="issue_type", help="Filter by issue_type")

    showp = sub.add_parser("show", help="Show record details")
    showp.add_argument("unique_key", help="UUID of the record")

    searchp = sub.add_parser("search", help="Search by name")
    searchp.add_argument("entity_type", choices=ENTITY_CHOICES)
    searchp.add_argument("--name", required=True, help="Name pattern to search")

    for name, helptext in (("approve", "Approve an artifact"), ("reject", "Reject an artifact")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("unique_key")
        p.add_argument("--note", help="Review note")

    markp = sub.add_parser("mark", help="Set artifact status")
    markp.add_argument("unique_key")
    markp.add_argument("status", choices=ARTIFACT_STATUS_CHOICES)
    markp.add_argument("--note", help="Review note")

    resolvep = sub.add_parser("resolve", help="Resolve a review issue")
    resolvep.add_argument("unique_key")
    resolvep.add_argument("--resolution", required=True, help="Resolution text")

    for name, helptext in (("dismiss", "Reject a review issue"), ("reopen", "Reopen an issue")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("unique_key")

    reportp = sub.add_parser("report", help="Generate review report")
    reportp.add_argument("--output", help="Output file path")

    genp = sub.add_parser("generate", help="Trigger R210 generation")
    genp.add_argument("--mode", choices=["r210_only", "report_only", "both"], default="both")
    genp.add_argument("--output", help="Output directory")

    sub.add_parser("stats", help="Show database statistics")
    return parser


def run(argv: list[str] | None = None) -> int:
    """Parse, dispatch, print, and return the exit code."""
    args = build_parser().parse_args(argv)
    bridge = ReviewToolBridge(args.db)
    formatter = DisplayFormatter(color=sys.stdout.isatty())
    text, code = COMMANDS[args.command](bridge, formatter, args)
    print(text)
    return code


def main() -> None:
    """Entry point for the r210-review console script."""
    sys.exit(run())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_review_cli/ -q -p no:cacheprovider`
Expected: PASS — all tests in the package

- [ ] **Step 5: Run the gates**

Run: `python -m ruff check src tests && python -m mypy src`
Expected: both clean

- [ ] **Step 6: Commit**

```bash
git add src/r210_review_cli/cli.py src/r210_review_cli/commands/generate.py tests/test_r210_review_cli/test_cli.py
git commit -m "feat(review-cli): wire the twelve-command argparse entry point"
```

---

## Task 7: Adversarial network-isolation verification (SRS-123)

LLD-06 §7 asks for a code review. `PHASE4_SCOPE.md` §7 requires this be written adversarially instead — it is one of two tests carried forward from the Phase 3 precedent.

**Files:**
- Test: `tests/test_r210_review_cli/test_isolation.py`

**Interfaces:**
- Consumes: nothing — it reads source files and spawns a subprocess.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Write the test (it must pass immediately — it is a guard, not a driver)**

Create `tests/test_r210_review_cli/test_isolation.py`:

```python
"""The review CLI can reach no network (SRS-123, SRS-015).

Two independent checks. The static one reads every module's AST, so it cannot
be fooled by code that is never executed; the dynamic one imports the CLI in a
clean subprocess, so it catches a transitive import the static scan misses.
"""

import ast
import pathlib
import subprocess
import sys

import r210_review_cli

FORBIDDEN = (
    "google.generativeai",
    "google.genai",
    "requests",
    "httpx",
    "urllib",
    "aiohttp",
    "websockets",
    "socket",
    "http",
    "mcp",
)

PACKAGE_ROOT = pathlib.Path(r210_review_cli.__file__).parent


def _imported_names(source: str) -> set[str]:
    """Every module name the source imports, by any syntax."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


class TestStaticIsolation:
    """SRS-123: no network-capable module is imported anywhere in the package."""

    def test_no_forbidden_imports_in_any_module(self) -> None:
        """SRS-123: an AST scan finds no networking or MCP transport import."""
        offenders: list[str] = []
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            for name in _imported_names(path.read_text(encoding="utf-8")):
                if any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                    offenders.append(f"{path.name}: {name}")
        assert offenders == [], f"network-capable imports found: {offenders}"

    def test_scan_actually_covers_files(self) -> None:
        """A scan over zero files would pass vacuously; assert it does not."""
        assert len(list(PACKAGE_ROOT.rglob("*.py"))) >= 7

    def test_no_dev_reset_import(self) -> None:
        """SRS-091/SRS-093: the destructive reset path is never reachable."""
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            assert "dev_reset" not in path.read_text(encoding="utf-8")


class TestDynamicIsolation:
    """SRS-123: importing the CLI pulls in no network stack transitively."""

    def test_importing_cli_loads_no_forbidden_module(self) -> None:
        """SRS-123: after importing the CLI, sys.modules holds no mcp or socket."""
        program = (
            "import sys; import r210_review_cli.cli; "
            "bad=[m for m in ('mcp','socket','httpx','requests') if m in sys.modules]; "
            "print(','.join(bad))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True, text=True, check=True,
        )
        assert completed.stdout.strip() == "", f"loaded: {completed.stdout.strip()}"
```

- [ ] **Step 2: Run it**

Run: `python -m pytest tests/test_r210_review_cli/test_isolation.py -q -p no:cacheprovider`
Expected: PASS — 4 passed

If `test_importing_cli_loads_no_forbidden_module` fails on `socket`, find which import pulls it in (`python -X importtime -c "import r210_review_cli.cli"`) and remove it. Do **not** relax the assertion — the failing case is the requirement working.

- [ ] **Step 3: Run the full suite and all gates**

Run: `python -m pytest tests/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: all pass, both gates clean

- [ ] **Step 4: Verify the console script end to end**

Run: `python -m r210_db_init init /tmp/r210_smoke.db && python -m r210_review_cli --db /tmp/r210_smoke.db stats`
Expected: exit 0, a statistics table listing every table with `total 0`

- [ ] **Step 5: Commit**

```bash
git add tests/test_r210_review_cli/test_isolation.py
git commit -m "test(review-cli): assert network isolation statically and dynamically"
```

---

## Part 1 Definition of Done

1. All seven tasks committed.
2. `python -m pytest tests/ -q -p no:cacheprovider` passes.
3. `python -m ruff check src tests` and `python -m mypy src` clean.
4. `r210-review --db <db> stats` runs and exits 0 against a freshly initialised database.
5. All twelve LLD-06 §4.1 commands parse and dispatch. `report`/`generate` correctly report the generator unavailable — Part 3 wires them.
6. Network isolation asserted by two independent tests.

**Deviations introduced here**, to be written into `docs/DEVIATIONS_FROM_REQUIREMENTS.md` in Part 4: DEV-40 (bridge targets `tools/registry`), DEV-41 (`bridge.py` added to LLD-06 §3's module list), DEV-42 (exit codes defined), DEV-43 (`search_by_name_pattern` added to the DAL), DEV-44 (colour gated on `isatty()`).

**Next:** `docs/superpowers/plans/2026-08-15-phase4-5-part2-generator-core.md`
