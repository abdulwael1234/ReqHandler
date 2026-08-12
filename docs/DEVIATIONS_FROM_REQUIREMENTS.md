# Deviations from the Requirements and Design Documents

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-DEV-01                                                  |
| **Date**             | 2026-08-12                                                   |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-01 v1.1, R210-LLD-02 v1.4, R210-LLD-05 v1.4 |
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

### DEV-04 — Verification derives its expectations from the migration *(Refinement)*

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
verbatim in twelve table definitions.

**Implementation:** A private `_STATUS_CHECK` constant interpolated into each
definition.

**Rationale:** Twelve hand-copied constraint lists are twelve chances for a
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

### DEV-14 — `ARTIFACT_TABLES` includes `SourceRequirements` *(Gap-fill — approved)*

**Documents say:** SRS-035a speaks of "artifact and reviewable child record".
SourceRequirements is an *input* record, not an extracted artifact, yet LLD-01
§3.1 gives it the same five-state `status` and a `review_note`.

**Implementation:** Grouped with the artifact tables, making it a valid target
for `set_review_status` (SRS-091a).

**Rationale:** A source requirement that carries a review state must be
reviewable, otherwise its `status` column can never leave `pending_review`.

**Decision:** approved. Reviewers are intended to set review states on source
requirements. SRS-035a and SRS-091a v5.3 now explicitly identify
`SourceRequirements` as a reviewable input record.

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

## 4. Decision Records and Remaining Open Items

### DEV-O-01 — `init_db` reports externally damaged schema *(Resolved — approved)*

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

**Decision:** approved as report-only. SRS-096 v5.3 now distinguishes creation
during initialization or pending migrations from verification of a database
whose recorded version is already current. Any future repair capability must
be an explicit administrative operation and must define how altered constraints
and data preservation are handled; simply re-running idempotent DDL is not a
complete schema-repair mechanism.

---

### DEV-O-02 — Nullable unresolved type references *(Resolved — approved)*

**Original question:** whether
`element_type_id` (in `ArrayTypeDefinitions`, `StructElements`) and
`type_definition_id` (in `InterfaceDataElements`, `OperationArguments`) may be
`NULL` while unresolved, as `PortPrototypes.port_interface_id` may be.

**Decision:** allow NULL while unresolved. The MCP boundary must create an
`unresolved_reference` issue and approval/export must remain blocked until the
reference is resolved.

**Implementation:** V002 rebuilds all four tables transactionally and preserves
existing rows, constraints, and indexes. Record dataclass annotations now allow
`None`. MCP issue creation and approval/export validation remain assigned to
their existing later phases.

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

## 4A. Phase 2 Deviations — Connection Layer and DAL

LLD-02 §5.1 presents the DAL as "representative, not exhaustive", so the method
set below it is derived rather than transcribed. These entries record where the
implementation departs from the sketch.

### DEV-17 — DAL returns record dataclasses, not `sqlite3.Row` *(Refinement)*

**LLD-02 §5.1:** `get_source_requirement_by_key(...) -> Optional[Row]`,
`query_source_requirements(...) -> list[Row]`.

**Implementation:** these return `SourceRequirementRecord | None` and
`list[SourceRequirementRecord]`.

**Rationale:** this is what DEV-11 created `TABLE_RECORD_MAP` for — "the DAL
needs to map query results to records". Returning `Row` would push that mapping
into every one of the thirty-odd Phase 3 call sites, where a mis-indexed column
is a silent wrong value rather than a type error. Records also make the layer's
output immutable, matching the frozen dataclasses Phase 1 defined.

---

### DEV-18 — Generic SQL core behind the named method surface *(Refinement)*

**LLD-02 §5.1** implies one hand-written statement per method.

**Implementation:** the public methods the LLD names are thin wrappers over
`_insert`, `_update`, `_get_by`, and `_query`, which build parameterized SQL
from a table registry.

**Rationale:** fifteen tables share four statement shapes. Writing them out
once means a fix to quoting, ordering, or placeholder handling lands
everywhere, and roughly halves the module. The typed wrappers are retained
precisely so that Phase 3 call sites stay checkable under `mypy --strict` —
the generic core is not exposed as the public interface.

**Safety note:** SQLite cannot parameterize identifiers, so building SQL from a
table name is only safe because every table and column name is resolved
through the registry and rejected if unknown. Values are always bound with `?`.

---

### DEV-19 — Column registry derived from the record dataclasses *(Addition)*

**Implementation:** `TABLE_COLUMNS` in `dal.py` is built from
`dataclasses.fields(TABLE_RECORD_MAP[table])` rather than written out.

**Rationale:** DEV-15 pinned record field order to column order. Deriving the
DAL's column lists from that same source means there is no third list to keep
in sync with the schema and the models — a column added to a table and its
record is automatically writable, and one added to only one of them fails the
existing Phase 1 contract test.

---

### DEV-20 — `schema_version` excluded from the DAL surface *(Refinement)*

**Implementation:** `DAL_TABLES` is `TABLE_RECORD_MAP` minus `schema_version`;
naming it raises `ValueError`.

**Rationale:** the version table is owned by the initializer (LLD-05 §4.3), has
no `unique_key`, and must not be writable through the layer the MCP tools call.

---

### DEV-21 — Default arguments on `insert_*` methods *(Refinement)*

**LLD-02 §5.1** shows every column as a required parameter.

**Implementation:** nullable columns default to `None` and `status` defaults to
`pending_review` / `pending`, matching the schema defaults (SRS-035a).

**Rationale:** the alternative is every call site restating the schema's own
defaults. The database remains the authority — the defaults here only spare
callers from repeating it.

---

### DEV-22 — `update_status` handles structural column differences *(Refinement)*

**Implementation:** `update_status` raises `ValueError` when the target table
has no `status` column. When `review_note` is supplied for a reviewable child
table that has no such column, the note is silently ignored as required by
SRS-091a and the status is still updated.

**Rationale:** SRS-035a gives the seven reviewable child types a review state
but no note column, and gives the two structural subtype tables neither. These
are schema facts, not review policy. Rejecting a table without any state avoids
a confusing SQL failure; ignoring an inapplicable note preserves SRS-091a's
uniform `set_review_status` behavior. Whether a *transition* is permitted
(SRS-035b) remains the validation layer's decision in Phase 3.

---

### DEV-23 — `McpError` and `McpResult` field defaults *(Refinement)*

**Implementation:** `McpError.field` and `McpError.affected_key` default to
`None`; `reason` is a required keyword argument. `McpResult.data` and
`McpResult.warnings` use `default_factory`. Both dataclasses are frozen.

**Rationale:** LLD-02 §3.1–3.2 shows no defaults, but most errors carry no
field name and most results carry no warnings. Every error must still supply
the human-readable reason required by SRS-109. Mutable defaults require
`default_factory` in any case.

---

### DEV-24 — `find_duplicates_by_name` implements only the SQL half of SRS-034 *(Boundary)*

**Implementation:** the query matches case-insensitively via `COLLATE NOCASE`.
The whitespace normalization SRS-034 also specifies — trim, then collapse
internal runs to a single space — is not applied here.

**Rationale:** normalizing inside the query would diverge from the
`COLLATE NOCASE` indexes V001 created for it and degrade the lookup to a table
scan. The caller normalizes before calling. SRS-034 and SRS-121 are assigned to
Phase 6, which owns both the normalization and the decision to warn; Phase 2
supplies only the lookup. Recorded so the split is not mistaken for an omission.

---

## 4B. Phase 3 Deviations — Validation Layer, Tool Handlers, Server Adapter

### DEV-25 — `McpValidationError` was never defined *(Gap-fill)*

**Documents say:** LLD-02 §6.2 raises `McpValidationError(...)` throughout the
validation layer. No definition appears anywhere in the LLD.

**Implementation:** Defined in `errors.py` as an exception carrying a
fully-formed `McpError`, with an `of(...)` constructor.

**Rationale:** Phase 2 built `McpError` as a frozen dataclass — a value, not an
exception. The validation layer needs to *raise*, and the dispatch boundary
needs the structured payload SRS-109 requires. Carrying the payload on the
exception means the boundary serializes it without reconstructing context it
does not have.

---

### DEV-26 — Handlers are functions over a context, not bound methods *(Refinement)*

**Documents say:** LLD-02 §9 defines all 35 handlers as `_handle_*` methods of
`R210McpServer`.

**Implementation:** Module-level functions taking a frozen `ToolContext`
(connection factory, DAL, adapter mode) and returning a `dict`. `server.py`
holds only the binding and the stdio adapter.

**Rationale:** LLD-06 §1 requires the Local Review CLI to invoke handlers
directly without the MCP protocol, and the `mcp` SDK is not installed in this
environment. A design whose handlers are reachable only through a class that
imports the SDK cannot satisfy either constraint. With a context parameter a
test constructs one in a single line.

**Effect on behaviour:** None. `R210McpServer.handle_tool(name, arguments)`
still exists as LLD-02 §9 specifies.

---

### DEV-27 — SRS-036a's approval block had no code home *(Gap-fill)*

**Documents say:** SRS-036a states "a record with an unresolved type reference
shall not be approved or exported." LLD-02 assigns the creation half (create an
`unresolved_reference` issue) but never places the approval block.

**Implementation:** `validation/status.check_references_resolved`, called by
`set_review_status` before any approval. For a `TypeDefinitions` record of kind
`array` it checks the `ArrayTypeDefinitions` detail row, which is not
independently reviewable (SRS-035a).

**Rationale:** Without it the requirement is half-implemented: the issue is
raised at creation and then ignored at the only point where it matters. The
export half remains the generator's (Phase 7).

---

### DEV-28 — Six DAL methods added, not the four the LLD calls *(Addition)*

**Documents say:** LLD-02 §6.2, §10.1 and §9 call `dal.get_record_by_id`,
`dal.get_parent_record`, `dal.get_children` and `dal.query_table`. Phase 2 built
none of them.

**Implementation:** All four, plus generic `insert_record(conn, table, values)`
and `update_record(conn, table, record_id, values)`.

**Rationale:** The four are the LLD's own calls. The two extra exist because
the descriptor engine writes to a table named by a descriptor; without them
each of the 13 create tools would carry a hand-written wrapper naming its own
columns — the duplication DEV-19 removed one layer down. Both follow the DAL's
existing conventions: identifier allowlist, bound values, record returns.

---

### DEV-29 — Records are dataclasses, not dict-subscriptable rows *(Correction)*

**Documents say:** LLD-02 §6.2 and §10.1 subscript records as dictionaries —
`parent["status"]`, `record["unique_key"]`.

**Implementation:** Attribute access throughout — `parent.status`.

**Rationale:** Phase 2 returns frozen record dataclasses (DEV-17), so the
LLD's pseudocode would raise `TypeError` as written.

---

### DEV-30 — Projection is applied once, at the dispatch boundary *(Refinement)*

**Documents say:** LLD-02 §11.2 applies `GEMINI_PROJECTION` inside each query
handler.

**Implementation:** `tools/registry.dispatch` projects every tool response when
`adapter_mode == "extraction"`. `projection.py` holds the allowlist.

**Rationale:** SRS-015a is a confidentiality boundary; a rule enforced in six
places can be forgotten in a seventh. Applied at dispatch, a handler cannot omit
a step it does not perform, and the guarantee is one adversarial test over all
35 tools rather than six hopeful ones.

**Effect on behaviour:** Strictly stronger. Create and update responses are now
projected too, which §11.2 did not cover.

---

### DEV-31 — `trigger_generation` reports the generator unavailable *(Boundary)*

**Documents say:** LLD-02 §7.9 delegates to the generator component (LLD-04).

**Implementation:** The tool is registered and validates `mode` against
`{"r210_only", "report_only", "both"}`, then returns a structured `McpError`
stating that generation is not yet implemented.

**Rationale:** The generator is a later phase. Registering the tool keeps the
surface complete and the contract real; returning a structured error is honest
where a silent success would not be.

---

### DEV-32 — A descriptor engine behind the named handler surface *(Refinement)*

**Documents say:** LLD-02 §7 writes each of the 35 handlers out individually.

**Implementation:** The 13 creates, 13 updates and 6 queries are frozen
descriptors executed by three engines in `tools/_engine.py`. Four irregular
tools — `create_type_definition`, `set_review_status`,
`update_port_connection_member`, `resolve_reference` — are written out.

**Rationale:** The same move Phase 2 recorded as DEV-18. Written out, the
SRS-082b demotion rule would be re-implemented twelve times and the SRS-091a
rejection thirteen; one omission is a silent requirement violation rather than a
test failure. `validate_subtype_matches_kind` returns its narrowed `dict` for
the same reason — so the caller cannot re-derive a fact already proved.

---

### DEV-33 — Phase 3 absorbs Phases 4–6 *(Correction)*

**Documents say:** `PHASE1_IMPLEMENTED_REQUIREMENTS.md` §9 assigns status
enforcement to Phase 3, parent approval and demotion to Phase 4, connection
validation to Phase 5, and duplicate detection to Phase 6.

**Implementation:** All of it lands in Phase 3.

**Rationale:** The split is not implementable in that order. LLD-02 §7.7 has
`set_review_status` (Phase 3) call `check_parent_can_be_approved` and
`auto_demote_parent_chain` (Phase 4); §10.1 has the Phase 3 content-demotion
rule call the same Phase 4 chain; §7.2 has `create_type_definition` (Phase 3)
call duplicate detection (Phase 6). Shipping Phase 3 alone would mean shipping
handlers that violate their own requirements and repairing them later.
Approved by the project owner on 2026-08-12. Phase 7 (generator) and Phase 8
(review CLI) are unchanged.

---

### DEV-34 — Validators take the operation name *(Refinement)*

**Documents say:** LLD-02 §6.1 gives signatures such as
`validate_position(value, field_name)`.

**Implementation:** Every validator takes a keyword-only `operation`, and
optionally `affected_key`.

**Rationale:** SRS-109 requires an error to identify the failing operation. A
validator that never receives the tool name cannot construct one, so the LLD's
signatures cannot produce a compliant error.

---

### DEV-35 — `table_hint` is optional *(Refinement)*

**Documents say:** LLD-02 §7.7 marks `table_hint` a required parameter of
`set_review_status`.

**Implementation:** Accepted and ignored; the table comes from
`resolve_unique_key`.

**Rationale:** Keys are UUIDs unique across the database (SRS-027), so the hint
adds no information the server cannot derive. A required hint introduces a
second source of truth that can disagree with the first, and the resulting error
would describe the caller's bookkeeping rather than the record.

---

### DEV-36 — Duplicate detection compares normalized forms over candidates *(Correction)*

**Documents say:** DEV-24 recorded that the DAL performs the indexed,
case-insensitive half of SRS-034 and the caller applies whitespace
normalization.

**Implementation:** `check_for_duplicates` queries the table (narrowed by
`kind` where applicable) and compares `normalize_name` on both sides.

**Rationale:** The split DEV-24 describes does not work. `find_duplicates_by_name`
matches with `name = ? COLLATE NOCASE`, so a stored name whose internal spacing
differs from the query never comes back — there is nothing for a caller-side
filter to normalize. Post-filtering an exact-match query cannot widen it. SRS-034
requires normalization on both sides, and SRS-113 rules out performance
optimization for the prototype, so correctness against the requirement is chosen
over the index. Caught by `test_matches_after_whitespace_normalization`.

**Effect on behaviour:** Duplicate detection now finds the cases SRS-034
describes. `find_duplicates_by_name` remains in the DAL, tested, and is no
longer the sole basis for the SRS-034 comparison.

---

### DEV-37 — SRS-070 is enforced by the schema, not the validator *(Correction)*

**Documents say:** LLD-02 §6.5 specifies `check_no_duplicate_members` as an
application-level rule inside `validate_connection_complete`.

**Implementation:** The check exists, but V001 already places a UNIQUE
constraint on `(port_connection_id, port_prototype_id)`, so a duplicate member
cannot be stored through the DAL at all. The validator branch is defence in
depth for rows arriving another way, and the test pins the schema as the real
enforcement point.

**Rationale:** Recorded so that a future reader does not mistake an unreachable
branch for dead code and delete it, and does not mistake the validator for the
requirement's only guard.

---

## 5. Deviation Index

| ID | Type | Area | Approval |
|----|------|------|----------|
| DEV-01 | Gap-fill | `InitResult` definition | Approved |
| DEV-02 | Correction | Verification failure returned, not raised | Approved |
| DEV-03 | Refinement | Explicit transaction control | Approved |
| DEV-04 | Refinement | Verification derived from migration DDL | Approved with independent requirements tests |
| DEV-05 | Refinement | DDL as module-level mappings | Approved |
| DEV-06 | Refinement | Shared status CHECK constant | Approved |
| DEV-07 | Correction | `dev_reset` skips all internal tables | Approved |
| DEV-08 | Correction | `dev_reset` reports re-init failure | Approved |
| DEV-09 | Refinement | Reset refusal to stderr | Approved |
| DEV-10 | Refinement | CLI dispatch structure | Approved |
| DEV-11 | Addition | `TABLE_RECORD_MAP` | Approved |
| DEV-12 | Addition | Table-grouping constants | Approved |
| DEV-13 | Addition | `ARTIFACT_TYPE_TABLE_MAP` | Approved |
| DEV-14 | Gap-fill | `SourceRequirements` treated as reviewable input | Approved; incorporated into SRS v5.3 |
| DEV-15 | Refinement | Field order pinned to column order | Approved |
| DEV-16 | Refinement | PEP 604 optional syntax | Approved |
| DEV-17 | Refinement | DAL returns records, not `Row` | Phase 2 — pending review |
| DEV-18 | Refinement | Generic SQL core behind named methods | Phase 2 — pending review |
| DEV-19 | Addition | Column registry derived from dataclasses | Phase 2 — pending review |
| DEV-20 | Refinement | `schema_version` outside the DAL surface | Phase 2 — pending review |
| DEV-21 | Refinement | Default arguments on `insert_*` | Phase 2 — pending review |
| DEV-22 | Refinement | `update_status` structural column handling | Phase 2 — pending review |
| DEV-23 | Refinement | `McpError` / `McpResult` field defaults | Phase 2 — pending review |
| DEV-24 | Boundary | SRS-034 normalization deferred to Phase 6 | Phase 2 — superseded by DEV-36 |
| DEV-25 | Gap-fill | `McpValidationError` definition | Phase 3 — pending review |
| DEV-26 | Refinement | Handlers are functions over `ToolContext` | Phase 3 — pending review |
| DEV-27 | Gap-fill | SRS-036a approval block (`check_references_resolved`) | Phase 3 — pending review |
| DEV-28 | Addition | Six DAL methods for the graph and the engine | Phase 3 — pending review |
| DEV-29 | Correction | Records are dataclasses, not dict rows | Phase 3 — pending review |
| DEV-30 | Refinement | Projection applied at the dispatch boundary | Phase 3 — pending review |
| DEV-31 | Boundary | `trigger_generation` reports generator unavailable | Phase 3 — pending review |
| DEV-32 | Refinement | Descriptor engine behind the named handlers | Phase 3 — pending review |
| DEV-33 | Correction | Phase 3 absorbs Phases 4–6 | **Approved by owner 2026-08-12** |
| DEV-34 | Refinement | Validators take the operation name | Phase 3 — pending review |
| DEV-35 | Refinement | `table_hint` optional on `set_review_status` | Phase 3 — pending review |
| DEV-36 | Correction | SRS-034 compares normalized forms over candidates | Phase 3 — pending review |
| DEV-37 | Correction | SRS-070 enforced by the schema, not the validator | Phase 3 — pending review |
| DEV-O-01 | Resolved decision | Report-only behavior for damaged current-version schema | Approved; incorporated into SRS v5.3 |
| DEV-O-02 | Resolved decision | Nullable unresolved cross-artifact type references | Approved and implemented in V002 |
| DEV-O-03 | Open item | Broken `r210-review` entry point | Fix in Phase 8 |
| DEV-O-04 | Open item | SRS-015 external data transfer | **Blocking, pre-existing** |

All Phase 1 interpretations and deviations are explicitly recorded. Approved
items are incorporated into the v5.4 requirements baseline. Remaining entries
are either scheduled future-phase work or the external SRS-015 authorization.

DEV-17 through DEV-24 record Phase 2 and have not yet been reviewed. DEV-25
through DEV-37 record Phase 3; only DEV-33, the phase-scope change, has been
approved. DEV-36 supersedes DEV-24: the Phase 2 split of SRS-034 between an
indexed DAL query and caller-side normalization does not work, because an
exact-match query returns nothing for a caller to normalize.

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-11 | Initial version covering Phase 1 (database foundation). |
| 1.1     | 2026-08-11 | Recorded approval of DEV-01 through DEV-16, resolved DEV-O-01 as report-only, incorporated source-requirement reviewability into SRS v5.3, and retained DEV-O-02 as the remaining Phase 1 stakeholder decision. |
| 1.2     | 2026-08-12 | Resolved DEV-O-02 by approving nullable unresolved type references and implementing V002. Recorded that work-specific configuration is intentionally deferred until transfer to the work computer. |
| 1.3     | 2026-08-12 | Added section 4A covering Phase 2 (connection layer and DAL): DEV-17 through DEV-24. |
| 1.4     | 2026-08-12 | Added section 4B covering Phase 3 (validation layer, 35 tool handlers, server adapter): DEV-25 through DEV-37. Recorded owner approval of DEV-33, the decision that Phase 3 absorbs Phases 4–6. DEV-36 supersedes DEV-24. |
