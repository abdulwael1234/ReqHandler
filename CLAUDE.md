# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"                      # editable install (not required for tests)

python -m pytest tests/ -q                   # full suite: 650 tests, 11 expected failures (D-01-D-03)
python -m pytest tests/test_r210_mcp/test_dal.py -q
python -m pytest tests/test_r210_mcp/test_dal.py::TestRoundTrip::test_every_table_round_trips -q

python -m ruff check src tests               # gate: must be clean
python -m mypy src                           # gate: strict, must be clean

python -m r210_db_init init r210.db          # create/upgrade a database
python -m r210_db_init reset r210.db --confirm   # destructive, dev only
```

`pyproject.toml` sets `pythonpath = ["src"]`, so pytest imports the packages without an install.

This machine denies creation of `.pytest_cache` in the repo directory. Append `-p no:cacheprovider`
to silence the resulting `PytestCacheWarning` — it does not affect results.

`mypy src` is clean; `mypy tests` reports ~36 pre-existing errors in the Phase 1 test files. The
recorded gate is sources only.

**The suite is not green, and that is the current expected state.** 639 pass, 11 fail. All eleven
are `tests/test_r210_mcp/test_phase3_acceptance.py` cases for defects D-01–D-03. Do not "fix" them
by changing the tests — they are written against LLD-02 and are correct. `ruff` and `mypy` are clean.

`r210-review` (the console script in `pyproject.toml`) resolves but exits 1; the CLI is Phase 4.

## This is a document-driven project

The specifications are normative and precede the code. Before changing behaviour, read the governing
document; a change that contradicts it is a deviation and must be recorded, not made silently.

| Document | Path |
|---|---|
| SRS (requirement IDs `SRS-nnn`) | `Srs/SRS_Requirements.md` |
| HLD | `archi/HLD_High_Level_Design.md` |
| LLD-01 Database Schema | `lld/LLD_01_Database_Schema.md` |
| LLD-02 MCP Server (largest; §3–§11 drive most code) | `lld/LLD_02_MCP_Server.md` |
| LLD-03…06 | `lld/LLD_0{3,4,5,6}_*.md` |

Traceability is enforced by convention, not tooling: module docstrings end with `See: LLD-0n §x`,
and test docstrings cite the `SRS-nnn` they verify. Keep both when adding code.

### Deviations must be written down

`docs/DEVIATIONS_FROM_REQUIREMENTS.md` records every point where the code differs from or fills a
gap in the documents, as numbered entries (`DEV-01`…`DEV-38`, plus `DEV-O-nn` open items awaiting
stakeholder decision; Phase 3's are closed against LLD-02 v1.5). Each entry states what the documents say, what the code does, and why,
classified as Gap-fill / Correction / Refinement / Addition / Open item. Adding a deviation without
an entry is the failure mode this document exists to prevent.

Each completed phase also gets a `docs/PHASEn_IMPLEMENTED_REQUIREMENTS.md` mapping SRS IDs to
implementation and to the tests that verify them.

## Implementation state

`r210_mcp/` is implemented but carries three known acceptance defects plus one architectural
conformance issue (D-01–D-04, `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` §11), scheduled for
remediation at the start of Phase 4.

`r210_generator/` and `r210_review_cli/` are still docstring-only stubs — a file's docstring tells
you what belongs there. `r210-review` therefore exits 1.

- **Phase 1** — `r210_db_init/` (migrations, initializer, CLI, dev_reset) and `r210_mcp/db/models.py`
- **Phase 2** — `r210_mcp/errors.py`, `db/connection.py`, `db/dal.py`
- **Phase 3** — `validation/`, `duplicate_detection.py`, `projection.py`, `tools/`, `server.py`

**Phase numbering is delivery order, and `docs/REMAINING_WORK.md` §1A is authoritative.** Phase 3
absorbed what the original eight-phase map called Phases 4–6 (DEV-33), which retired that map.
Remaining work is **Phase 4** (`docs/PHASE4_SCOPE.md` — Phase 3 remediation, review CLI, generator
core, review report, Gemini skill) and **Phase 5** (`docs/PHASE5_SCOPE.md` — R210 rendering, blocked
on SRS-019(c) and SRS-064). Older documents saying "Phase 7/8" mean these; `REPOSITORY_REVIEW_REPORT.md`
§7 uses a third, five-phase map — ignore its numbering.

`R210McpServer.run()` has never been executed — the `mcp` SDK is not installed here. It is the one
unverified path; everything else is reachable through `handle_tool`.

## Architecture

Layering, strictly one-directional:

```
migrations (owns DDL) → initializer → [database]
models.py (record dataclasses + registries)
      ↓
dal.py (all SQL) ← connection.py (pragmas, transactions)
      ↓
validation/ + duplicate_detection.py
      ↓
tools/_engine.py (descriptors) → tools/<entity>.py (35 handlers)
      ↓
tools/registry.py (dispatch, error boundary, projection boundary)
      ↓
server.py (stdio adapter — the only module that imports `mcp`)
```

**Handlers are functions, not methods** (DEV-26): `handle_x(ctx: ToolContext, arguments: dict)
-> dict`. `ToolContext` carries the connection factory, the DAL and `adapter_mode`
(`"extraction"` | `"review"`). That is what lets LLD-06's review CLI call tools directly and what
keeps handler tests runnable without the SDK.

**The registry is the only boundary that converts exceptions to responses**, and the only place
SRS-015a projection is applied (DEV-30). A handler that returned a record with `source_text` in it
is still safe in extraction mode; a handler that forgot to project would not be, which is why
projection does not live in the handlers.

**The 26 CRUD tools are descriptors, not code** (DEV-32). To add or change a field, edit the
`CreateSpec`/`UpdateSpec`/`QuerySpec` in the entity module. The cross-cutting rules — SRS-091a
status rejection, SRS-082b demotion, SRS-035c parent chaining, SRS-036a issue lifecycle — live once
in `tools/_engine.py`. Four tools are irregular and written out: `create_type_definition`,
`set_review_status`, `update_port_connection_member`, `resolve_reference`.

**The schema has one source of truth, and everything else derives from it.**
`migrations/v001_initial_schema.py` exposes `TABLE_DDL` / `INDEX_DDL`; the initializer's
`_verify_schema` derives its expectations from those maps rather than restating them (DEV-04).
`models.py` pins each record dataclass's field order to its table's column order, so a
`sqlite3.Row` expands positionally into a record; `dal.py` then derives `TABLE_COLUMNS` from
`dataclasses.fields(...)` rather than listing columns a third time (DEV-19). Tests cross-check the
derived registries against `PRAGMA table_info` on a live database. When you change the schema, add
a migration — never edit V001 — and the registries follow automatically.

**`models.py` registries** (`ARTIFACT_TABLES`, `REVIEWABLE_CHILD_TABLES`,
`STRUCTURAL_SUBTYPE_TABLES`, `PARENT_CHILD_MAP` / `CHILD_PARENT_MAP`, `ARTIFACT_TYPE_TABLE_MAP`,
`TABLE_RECORD_MAP`) are the table-driven backbone. Later phases dispatch through them; prefer
extending a registry over adding a branch.

**The DAL never validates.** LLD-02 §5.1 draws this line and the code holds it: no status-transition
checks, no duplicate-warning policy, no parent demotion. `sqlite3.IntegrityError` is deliberately
*not* caught there — only the caller knows the tool name and `unique_key` needed to build a complete
`McpError` (SRS-109). The DAL is a generic core of 12 private methods behind ~69 explicitly typed
public wrappers; the wrappers exist so Phase 3 call sites stay checkable under `mypy --strict`.

**Identifiers are allowlisted, values are bound.** SQLite cannot parameterize table or column names,
so every identifier in `dal.py` is resolved through `DAL_TABLES` / `TABLE_COLUMNS` and rejected with
`ValueError` if unknown; every value uses a `?` placeholder. Preserve this in any new SQL.

**Transactions.** Connections use `isolation_level=None` to disable the driver's implicit
transactions, so the explicit `BEGIN IMMEDIATE` in `DatabaseConnection.transaction()` (and in the
initializer's migration loop) is the only transaction control (DEV-03). Each operation opens its own
connection; there is no pooling, by requirement (SRS-113 forbids concurrency/performance work).

## Standing constraints

- **No delete path.** SRS-091/SRS-093 exclude deletion from the MCP surface. `dal.py` contains no
  `DELETE`. `development_reset` lives in `r210_db_init` and must never be imported by `r210_mcp` —
  a test asserts this.
- **Synthetic data only.** SRS-015 (external transfer of requirement text to Gemini) is unresolved
  and blocking. `docs/WORK_MACHINE_CONFIGURATION.md` lists the work-specific values (templates,
  AUTOSAR paths, compatibility rules) deliberately absent from this copy; do not invent them.
- **Unresolved references are `NULL`, never `0`** (SRS-030, SRS-036a). A `None` filter in the DAL
  compiles to `IS NULL`, not `= NULL`.
- **Ordering is deterministic** (SRS-037, SRS-108): ordered child tables sort by `(parent_fk,
  position)`, everything else by `id`.

## Testing conventions

Tests mirror `src/` under `tests/test_<package>/`, grouped into `class Test*` blocks with the
verified `SRS-nnn` in the test docstring. `tests/conftest.py` provides `db_path` (a path to a
not-yet-created file), `initialized_db` (migrated to the current version), and `conn`.

Phase 1 was developed test-first and mutation-checked; Phase 2 tests are described as
development-level rather than an exhaustive verification campaign. New tests should assert against a
real migrated SQLite database rather than mocks — that is what keeps the schema, models, and DAL
from drifting apart.
