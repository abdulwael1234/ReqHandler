# Deviations from the Requirements and Design Documents

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-DEV-01                                                  |
| **Date**             | 2026-08-11                                                   |
| **Source Documents** | R210-SRS-001 v5.2, R210-LLD-01 v1.0, R210-LLD-02 v1.2, R210-LLD-05 v1.2 |
| **Companion**        | `docs/PHASE1_IMPLEMENTED_REQUIREMENTS.md`                    |
| **Status**           | Living document — updated as each phase is implemented        |

---

## 1. Purpose

This document records every point where the implementation differs from, or
fills a gap in, the SRS/HLD/LLD. Nothing here is a silent change: each entry
states what the documents say, what the code does, and why.

It also records **open items** — unresolved specification questions the
implementation encountered but did not decide unilaterally.

### Classification

| Type | Meaning | Approval needed |
|------|---------|-----------------|
| **Gap-fill** | The documents referenced something they never defined. The implementation supplies it. | Review recommended |
| **Correction** | The documents specify something that is wrong, unreachable, or self-contradictory. | Review recommended |
| **Refinement** | Same observable behaviour, different structure — chosen for maintainability. | Informational |
| **Addition** | Something the documents require in prose but give no code home. | Review recommended |
| **Open item** | A specification question left unresolved. Implementation followed the documented default. | **Stakeholder decision required** |

---

## 2. Phase 1 Deviations — Database Initializer

### DEV-01 — `InitResult` was never defined *(Gap-fill)*

**Documents say:** LLD-05 §3 and §4.2 both use `InitResult`, reading
`result.final_version`, `result.migrations_applied`, `result.status`, and
`result.error`. No definition appears anywhere in the LLD.

**Implementation:** Defined in `initializer.py` as a frozen dataclass:

```python
@dataclass(frozen=True)
class InitResult:
    final_version: int
    migrations_applied: int
    status: str          # "success" | "up_to_date" | "failed"
    error: str | None = None
```

**Rationale:** The field set is fully determined by the LLD's own usage. The
status vocabulary is taken from LLD-05 §4.2, which returns those three
literals, and from §3, which tests `result.status in ("success", "up_to_date")`.
`error` defaults to `None` so success paths need not pass it.

---

### DEV-02 — Verification failure is returned, not raised *(Correction)*

**Documents say:** LLD-05 §4.3 states `_verify_schema` "raises RuntimeError if
verification fails", and §9 lists the behaviour as "Raises RuntimeError with
missing table list".

**Implementation:** `_verify_schema` still raises `RuntimeError` as specified.
`init_db` now catches it and returns `InitResult(status="failed", error=...)`.

**Rationale:** As written, the two halves of LLD-05 contradict each other. If
`init_db` propagated the exception, the CLI in §3 — which reads `result.error`
and chooses its exit code from `result.status` — would never run; the user
would get an unhandled traceback and an exit code of 1 with no structured
message. SRS-109 requires errors to report the failing operation and the
reason. Catching at the `init_db` boundary delivers exactly the information the
LLD's own CLI expects, through the LLD's own return contract.

**Effect on behaviour:** No information is lost. The RuntimeError message
becomes `InitResult.error` verbatim.

---

### DEV-03 — Explicit transaction control via `isolation_level=None` *(Refinement)*

**Documents say:** LLD-05 §4.2 uses `sqlite3.connect(self._db_path)` and mixes
an explicit `conn.execute("BEGIN IMMEDIATE")` with `conn.commit()` and
`conn.rollback()`.

**Implementation:** `sqlite3.connect(self._db_path, isolation_level=None)`,
with explicit `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` statements.

**Rationale:** Python's `sqlite3` driver in its default (legacy) mode issues
implicit `BEGIN` statements before DML. Interleaving that with a manual
`BEGIN IMMEDIATE` makes transaction boundaries depend on driver internals and
Python version. Disabling implicit transaction management makes the migration
transaction required by SRS-124 unambiguous and explicit.

**Effect on behaviour:** Identical, and no longer version-dependent.

---

### DEV-04 — Verification derives its expectations from the migration *(Correction)*

**Documents say:** LLD-05 §4.3 hardcodes a set of expected table names and a
subset of ten "key indexes" inside `_verify_schema`, separate from the DDL in
§5.2.

**Implementation:** The migration module exposes `TABLE_DDL` and `INDEX_DDL` as
the single source of truth. `_verify_schema` derives its expected sets from
them and therefore checks **all 29 indexes**, not ten.

**Rationale:** LLD-05's own revision history (v1.2, finding H-01) records that
the hardcoded verification names had drifted out of sync with the DDL and had
to be corrected. Duplicating the list is what caused that defect; deriving it
removes the possibility permanently. Checking all indexes is also strictly
stronger — a dropped index is a real schema regression whether or not it
appeared on the abbreviated list.

---

### DEV-05 — Migration DDL held as module-level mappings *(Refinement)*

**Documents say:** LLD-05 §5.2 writes each `CREATE TABLE` as an inline
`conn.execute("""...""")` call inside `up()`, and the index list as a local
variable inside `_create_indexes()`.

**Implementation:** `TABLE_DDL: dict[str, str]` and
`INDEX_DDL: dict[str, tuple[str, str]]` at module level; `up()` iterates them.

**Rationale:** Enables DEV-04. The SQL text is unchanged.

---

### DEV-06 — Shared constant for the repeated status CHECK *(Refinement)*

**Documents say:** LLD-05 §5.2 repeats the five-value status CHECK clause
verbatim in thirteen table definitions.

**Implementation:** A private `_STATUS_CHECK` constant interpolated into each
definition.

**Rationale:** Thirteen hand-copied constraint lists are thirteen chances for a
typo that SQLite accepts silently. The generated SQL is byte-identical.

---

### DEV-07 — `dev_reset` skips all internal SQLite tables *(Correction)*

**Documents say:** LLD-05 §6 selects tables with
`WHERE type='table' AND name != 'sqlite_sequence'`.

**Implementation:** `WHERE type='table' AND name NOT LIKE 'sqlite_%'`.

**Rationale:** `sqlite_sequence` is not the only internal table SQLite creates.
`sqlite_stat1` appears after `ANALYZE`, and `DROP TABLE sqlite_stat1` raises
`table sqlite_stat1 may not be dropped`. The specified filter would make reset
fail on any database that had been analysed. Internal tables are not ours to
remove in any case.

---

### DEV-08 — `dev_reset` reports re-initialization failure *(Correction)*

**Documents say:** LLD-05 §6 calls `initializer.init_db()` as the last
statement and discards the result.

**Implementation:** The result is checked; a `"failed"` status raises
`RuntimeError` naming the underlying error.

**Rationale:** As specified, a reset that successfully dropped every table but
then failed to recreate them would report success and leave the developer with
an empty, schema-less database — the exact failure mode most likely to be
misread as data loss.

---

### DEV-09 — Reset refusal is written to stderr *(Refinement)*

**Documents say:** LLD-05 §3 prints `"ERROR: Reset is destructive..."` to
stdout.

**Implementation:** Printed to stderr.

**Rationale:** It is an error accompanying a non-zero exit. The `init` failure
path in the same CLI already writes to stderr; this makes the two consistent
and keeps stdout parseable.

---

### DEV-10 — CLI dispatch avoids an unreachable branch *(Refinement)*

**Documents say:** LLD-05 §3 dispatches with `if ... elif args.command ==
"reset":`, leaving an implicit fall-through.

**Implementation:** The `init` branch exits; the `reset` path follows
unconditionally, with a comment noting that `required=True` on the subparsers
makes any other value unreachable.

**Rationale:** Equivalent behaviour, and it satisfies `mypy --strict`, which
flags the fall-through as an implicit `None` return from a function the LLD
declares as never returning normally.

---

## 3. Phase 1 Deviations — Model Layer

LLD-02 §3.3 gives one example dataclass (`TypeDefinitionRecord`) and states
"Similar dataclasses exist for every table in LLD-01". The remaining fifteen
were derived directly from the LLD-01 §3 column lists.

### DEV-11 — Added `TABLE_RECORD_MAP` *(Addition)*

**Implementation:** A `dict[str, type]` mapping each table name to its record
dataclass.

**Rationale:** The DAL (Phase 2) needs to map query results to records
generically rather than with sixteen bespoke branches. It also makes the model
layer verifiable: the test suite walks this map and compares each dataclass
against `PRAGMA table_info`, so schema and models cannot drift apart.

---

### DEV-12 — Added table-grouping constants *(Addition)*

**Implementation:** `ARTIFACT_TABLES`, `REVIEWABLE_CHILD_TABLES`,
`STRUCTURAL_SUBTYPE_TABLES`.

**Rationale:** SRS-035a enumerates the seven reviewable child types and the two
structural subtype tables in prose, and SRS-091a scopes `set_review_status` by
referring to those groups. The rules are unimplementable until the groups exist
as data. Defining them in Phase 1 keeps the enumeration in one place.

---

### DEV-13 — Added `ARTIFACT_TYPE_TABLE_MAP` *(Addition)*

**Implementation:** A mapping from each of the eleven `ReviewIssues.
artifact_type` values to the table that resolves `artifact_unique_key`.

**Rationale:** SRS-074 requires consumers to resolve the typed polymorphic
reference "by querying the table identified by `artifact_type`", but neither
LLD-01 nor LLD-02 provides that mapping. A test asserts it stays consistent
with the CHECK constraint in the schema.

---

### DEV-14 — `ARTIFACT_TABLES` includes `SourceRequirements` *(Gap-fill — review recommended)*

**Documents say:** SRS-035a speaks of "artifact and reviewable child record".
SourceRequirements is an *input* record, not an extracted artifact, yet LLD-01
§3.1 gives it the same five-state `status` and a `review_note`.

**Implementation:** Grouped with the artifact tables, making it a valid target
for `set_review_status` (SRS-091a).

**Rationale:** A source requirement that carries a review state must be
reviewable, otherwise its `status` column can never leave `pending_review`.

**Requested confirmation:** that reviewers are intended to set review states on
source requirements. If not, `SourceRequirements.status` and `review_note`
should be removed from LLD-01 §3.1 instead.

---

### DEV-15 — Record field order pinned to column order *(Refinement)*

**Implementation:** Each dataclass declares its fields in the exact order of
its table's columns, enforced by test.

**Rationale:** Permits positional expansion of a `sqlite3.Row` into a record in
the DAL. Not stated by LLD-02; harmless if unused.

---

### DEV-16 — PEP 604 optional syntax *(Refinement)*

**Documents say:** LLD-02 §3.3 annotates with `Optional[str]`.

**Implementation:** `str | None`.

**Rationale:** The repository's own `pyproject.toml` enables ruff's `UP`
ruleset against `target-version = "py311"`, which rejects `Optional[...]`. The
implementation follows the project's configured lint policy over the LLD's
illustrative snippet.

---

## 4. Open Items — Stakeholder Decision Required

### DEV-O-01 — Does `init_db` repair an externally damaged schema?

**Tension:** SRS-096 says "`init_db` shall create missing tables, constraints,
and indexes." LLD-05 §9 says schema verification failure "Raises RuntimeError
with missing table list."

If a table is dropped *after* its version was recorded, the migration does not
re-run (the recorded version already equals the target), so `init_db` **detects
and reports** the damage but does not repair it.

**Implemented:** the LLD-05 behaviour — report, do not repair.

**Why not repair:** silently recreating a table a developer or DBA deliberately
dropped would mask corruption and could resurrect a schema inconsistent with
the data around it. Reporting is the safer default for a component whose stated
purpose (SRS-099) is to preserve existing content.

**Decision needed:** confirm report-only, or specify a repair mode. If repair is
wanted, a `--repair` flag re-running the idempotent DDL is the natural form.

---

### DEV-O-02 — SRS-036a remains unresolved

**Status in SRS:** listed as an open Stakeholder Decision. It asks whether
`element_type_id` (in `ArrayTypeDefinitions`, `StructElements`) and
`type_definition_id` (in `InterfaceDataElements`, `OperationArguments`) may be
`NULL` while unresolved, as `PortPrototypes.port_interface_id` may be.

**Implemented:** the documented default — `NOT NULL` on all four columns, per
LLD-01 §3.4/§3.5 and the note in LLD-01 §4.

**Cost of a later change:** SQLite cannot drop a `NOT NULL` constraint in place.
Reversing this decision requires a V002 migration that rebuilds all four tables
(create new, copy, drop old, rename) — safe but not trivial.

**Recommendation:** resolve before Phase 4 (type-definition MCP tools), when
extraction begins creating records whose type references may not yet exist.

---

### DEV-O-03 — `pyproject.toml` points at a module that does not exist

**Observed, not fixed** — outside Phase 1 scope.

`pyproject.toml` declares:

```toml
[project.scripts]
r210-review = "r210_review_cli.cli:main"
```

`src/r210_review_cli/` contains `__main__.py`, `display.py`, and `commands/`,
but no `cli.py`. The `r210-review` console script will fail on any installed
build. (`r210-init-db = "r210_db_init.cli:main"` is correct and now works.)

**Resolution:** create `r210_review_cli/cli.py` in Phase 8, or repoint the entry
to `r210_review_cli.__main__:main`.

---

### DEV-O-04 — SRS-015 remains BLOCKING

Recorded here for visibility, unchanged by Phase 1. The SRS marks SRS-015 as a
blocking stakeholder decision: using Gemini requires transferring requirement
text off the work computer, which the source document prohibits absolutely.
Until approved, the system operates on synthetic data only.

Phase 1 touches no external service and is unaffected. Phase 3 onward cannot
process real work data until this is resolved.

---

## 5. Deviation Index

| ID | Type | Area | Approval |
|----|------|------|----------|
| DEV-01 | Gap-fill | `InitResult` definition | Review recommended |
| DEV-02 | Correction | Verification failure returned, not raised | Review recommended |
| DEV-03 | Refinement | Explicit transaction control | Informational |
| DEV-04 | Correction | Verification derived from migration DDL | Review recommended |
| DEV-05 | Refinement | DDL as module-level mappings | Informational |
| DEV-06 | Refinement | Shared status CHECK constant | Informational |
| DEV-07 | Correction | `dev_reset` skips all internal tables | Review recommended |
| DEV-08 | Correction | `dev_reset` reports re-init failure | Review recommended |
| DEV-09 | Refinement | Reset refusal to stderr | Informational |
| DEV-10 | Refinement | CLI dispatch structure | Informational |
| DEV-11 | Addition | `TABLE_RECORD_MAP` | Review recommended |
| DEV-12 | Addition | Table-grouping constants | Review recommended |
| DEV-13 | Addition | `ARTIFACT_TYPE_TABLE_MAP` | Review recommended |
| DEV-14 | Gap-fill | `SourceRequirements` treated as reviewable | **Confirmation requested** |
| DEV-15 | Refinement | Field order pinned to column order | Informational |
| DEV-16 | Refinement | PEP 604 optional syntax | Informational |
| DEV-O-01 | Open item | Repair vs. report on damaged schema | **Decision required** |
| DEV-O-02 | Open item | SRS-036a nullable cross-artifact FKs | **Decision required** |
| DEV-O-03 | Open item | Broken `r210-review` entry point | Fix in Phase 8 |
| DEV-O-04 | Open item | SRS-015 external data transfer | **Blocking, pre-existing** |

**No requirement was skipped, weakened, or silently reinterpreted.** Every
Phase 1 requirement listed in `PHASE1_IMPLEMENTED_REQUIREMENTS.md` is
implemented and tested.

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-11 | Initial version covering Phase 1 (database foundation). |
