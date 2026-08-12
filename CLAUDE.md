# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -e ".[dev]"                      # editable install (not required for tests)

python -m pytest tests/ -q                   # full suite
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

`r210-review` (the console script in `pyproject.toml`) is a stub that exits 1 — see DEV-O-03.

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
gap in the documents, as numbered entries (`DEV-01`…`DEV-24`, plus `DEV-O-nn` open items awaiting
stakeholder decision). Each entry states what the documents say, what the code does, and why,
classified as Gap-fill / Correction / Refinement / Addition / Open item. Adding a deviation without
an entry is the failure mode this document exists to prevent.

Each completed phase also gets a `docs/PHASEn_IMPLEMENTED_REQUIREMENTS.md` mapping SRS IDs to
implementation and to the tests that verify them.

## Implementation state

Nearly every module under `src/` is a docstring-only stub describing what it will contain. Only two
phases are built:

- **Phase 1** — `r210_db_init/` (migrations, initializer, CLI, dev_reset) and `r210_mcp/db/models.py`
- **Phase 2** — `r210_mcp/errors.py`, `r210_mcp/db/connection.py`, `r210_mcp/db/dal.py`

Everything else (`validation/`, `tools/`, `server.py`, `duplicate_detection.py`, `r210_generator/`,
`r210_review_cli/`) is scaffolding. A file's docstring tells you what belongs there.

**Two conflicting phase maps exist.** The repository follows the **eight-phase map** used by
`PHASE1_IMPLEMENTED_REQUIREMENTS.md` §9 and the Phase 2 docs: 3 = tool handlers + status
enforcement, 4 = parent/child approval rules, 5 = connection validation, 6 = duplicate detection,
7 = generator, 8 = review CLI. `REPOSITORY_REVIEW_REPORT.md` §7 uses an older five-phase map;
ignore its numbering.

## Architecture

Layering, strictly one-directional:

```
migrations (owns DDL) → initializer → [database]
models.py (record dataclasses + registries)
      ↓
dal.py (all SQL) ← connection.py (pragmas, transactions)
      ↓
validation/ + tools/ (Phase 3+) → server.py
```

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
