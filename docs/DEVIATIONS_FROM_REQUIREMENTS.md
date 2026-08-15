# Deviations from the Requirements and Design Documents

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-DEV-01                                                  |
| **Date**             | 2026-08-13                                                   |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-01 v1.1, R210-LLD-02 v1.5, R210-LLD-05 v1.4 |
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

### DEV-O-03 — `r210-review` entry point *(Resolved as stated; the tool remains a stub)*

**Originally recorded (Phase 1):** that `src/r210_review_cli/` contained no
`cli.py`, so the `r210-review` console script declared in `pyproject.toml`
would fail to import on any installed build.

**Status at Phase 3:** the premise is out of date. `src/r210_review_cli/cli.py`
exists and defines `main()`, so `r210-review = "r210_review_cli.cli:main"`
resolves correctly. The entry point is not broken.

What remains is not a packaging defect but unimplemented scope: `main()` prints
`r210-review: not yet implemented` to stderr and exits 1. The Local Review CLI
is LLD-06, delivered in Phase 8 (SRS-123).

**Resolution:** closed as a packaging issue. Tracked from here as ordinary
remaining work, not as an open specification item.

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
Approved by the project owner on 2026-08-12.

**Follow-on (2026-08-13):** absorbing three phases retired the original
eight-phase map. What it called Phases 7 and 8 are now Phase 4 and Phase 5,
split at the work-configuration boundary rather than by component. The
authoritative mapping is `docs/REMAINING_WORK.md` §1A; references to "Phase 7"
or "Phase 8" elsewhere in this document are historical and mean those rows.

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

### DEV-38 — The §11.2 mutation restriction extends to update tools *(Refinement)*

**Documents say:** LLD-02 §11.2 (v1.4) restricted *create* tools to returning
`unique_key` and warnings in both modes, and said nothing about update tools.

**Implementation:** In extraction mode, every tool that is not a query or
`resolve_reference` returns only `unique_key`, `warnings` and any `demoted`
keys. Query tools and `resolve_reference` return records projected to the
SRS-015a allowlist.

**Rationale:** SRS-015a splits into clause (b), which permits *query results*
to carry the allowlisted fields because the skill needs them for duplicate
checking and reference resolution, and clause (c), which limits tool-response
metadata to returned `unique_key` values and duplicate-warning text. An update
response is no more a query result than a create response is, so the rule §11.2
already applied to creates applies equally to updates.

**Found by:** re-reading §11.2 while aligning the document. The first Phase 3
implementation returned the full projected record from every tool, which
satisfied the allowlist but exceeded clause (c) — a create handed Gemini
`name`, `kind` and `status` where only the key was permitted. **The code was
corrected to match the document**, not the reverse.

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

## 4C. Phase 4/5 Deviations — Review CLI, Generator, R210 Framework

Recorded on 2026-08-15, on branch `feature/phase4-5-generator-and-review-cli`.
Design spec:
`docs/superpowers/specs/2026-08-15-phase4-5-generator-and-review-cli-design.md`.

---

### DEV-39 — Phase 5 split: framework built, template bodies deferred *(Refinement)*

**Documents say:** `docs/PHASE5_SCOPE.md` §2 makes all of Phase 5 blocked until
four work-computer entry criteria close, and §3.1 lists the whole `r210/`
subpackage as Phase 5 scope. `docs/PHASE4_SCOPE.md` §6 excludes R210 rendering
from Phase 4 entirely.

**Implementation:** Phase 4 is delivered complete, and Phase 5 is split at the
line LLD-04 §6 already draws. §6.1's template *interface*, §6.2's dispatch,
§6.3's artifact ordering, §6.4's child ordering and §6.5's rejected-child
exclusion are implemented and tested. §6.6's and §6.7's template *content* —
the four bodies and the AUTOSAR mapping — remain declared plug-points.

**Rationale:** None of §6.2–§6.5 depends on what a template says, and all of it
is real logic that SRS-101 and SRS-108 constrain. Leaving it unwritten because a
neighbouring section is blocked would defer work that is not blocked, and would
leave the determinism requirement unverified until the one phase that cannot run
in this environment. LLD-04 §11 states the intent this serves: "template
implementations are pluggable — the generator framework is ready for any
template content."

**Effect on the phase boundary:** Phase 5 on the work computer becomes "write one
module returning a populated `TemplateSet`, `NamingPolicy` and
`AccessPointPolicy`, and pass it to `GeneratorConfig`". No framework code
changes. `docs/PHASE5_SCOPE.md` §5 predicted this shape; this entry records that
the seam moved one step further into Phase 5 than that document drew it.

---

### DEV-40 — The review CLI bridge does not import `R210McpServer` *(Correction)*

**Documents say:** LLD-06 §5.1 specifies
`from r210_mcp.server import R210McpServer`, and §5.2 constructs one.

**Implementation:** `r210_review_cli/bridge.py` calls
`build_context(db_path, adapter_mode="review")` and `tools.registry.dispatch`.
It never imports `r210_mcp.server`.

**Rationale:** LLD-06 contradicts itself. `server.py` is the only module in the
repository that imports the `mcp` SDK, so following §5.1 would (a) make the
review CLI unusable unless the SDK is installed, and (b) violate **LLD-06 §7
item 2**, the network-isolation guarantee the same document states — "No MCP
protocol", no import of "any MCP transport module". §7 carries the requirement
(SRS-123); §5.1 is a code sketch written before Phase 3 existed. Phase 3 then
created the seam that resolves it deliberately (DEV-26).

Every guarantee §5.2 asks for is preserved: identical validation, identical
transactions, identical errors, approval permitted structurally by
`adapter_mode` (SRS-082a), and full unprojected records.

**Verification:** `tests/test_r210_review_cli/test_isolation.py` asserts it two
ways — an AST scan of every module in the package, and a subprocess import that
checks `mcp` never enters `sys.modules`.

---

### DEV-41 — `ReviewToolBridge` lives in `bridge.py` *(Gap-fill)*

**Documents say:** LLD-06 §3's module list contains `cli.py`, `commands/` and
`display.py`. §5.2 specifies a `ReviewToolBridge` class but names no file.

**Implementation:** `src/r210_review_cli/bridge.py`.

**Rationale:** Argument parsing and tool invocation are separately testable
concerns, and the bridge is what LLD-06 §5 spends its whole section on. Burying
it in `cli.py` would leave the module that §5 cares most about without a file of
its own.

---

### DEV-42 — CLI exit codes defined *(Gap-fill)*

**Documents say:** LLD-06 specifies no exit codes.

**Implementation:** `0` success, `1` tool error, `2` usage error — argparse's own
convention, left untouched.

**Rationale:** A CLI that exits 0 on failure cannot be scripted. The three-value
split is conventional, and keeping argparse's `2` avoids overriding behaviour the
library already gets right.

---

### DEV-43 — `DAL.search_by_name_pattern` added *(Gap-fill)*

**Documents say:** LLD-06 §4.2 specifies `search <entity_type> --name <pattern>`.
The DAL, completed in Phase 2, matches only by equality — `_where` builds
`"name" = ?`. `docs/PHASE4_SCOPE.md` §5.1 leaves the resolution open.

**Implementation:** One additive DAL method using `LIKE ? COLLATE NOCASE`, with
the table resolved through `DAL_TABLES`, `name` presence checked against
`TABLE_COLUMNS`, and the pattern bound as a parameter.

**Rationale:** It follows `find_duplicates_by_name` exactly, the precedent this
project already set for the same shape of problem. The alternative — filtering
client-side over `query_by_table` — avoids touching a finished layer but loads
whole tables to discard most rows, and puts a second, divergent notion of
"matching" outside the DAL. The identifier allowlist is untouched, which was
`docs/PHASE4_SCOPE.md` §9's stated risk.

---

### DEV-44 — Terminal colour gated on `isatty()` *(Refinement)*

**Documents say:** LLD-06 §6.1 defines `STATUS_COLORS` but not when to apply
them.

**Implementation:** `DisplayFormatter(color: bool)`; `cli.run` passes
`sys.stdout.isatty()`. The glyph and all text are identical either way.

**Rationale:** ANSI escapes written into a redirected file or a pipe corrupt it.
Making colour a constructor argument rather than an ambient check also keeps the
formatter deterministic under test.

**Related, found by running it:** `cli.run` also reconfigures stdout to UTF-8.
LLD-06 §6.2's specified output uses box-drawing and status glyphs (`─`, `■`, `✓`,
`✗`, `⚠`) that cp1252 — the Windows console default — cannot encode, and printing
a formatted table raised `UnicodeEncodeError`. pytest captures as UTF-8, so only
a real cp1252 stream reproduces it; `TestOutputEncoding` uses one.

---

### DEV-45 — The loader uses the existing layers, not raw `sqlite3` *(Correction)*

**Documents say:** LLD-04 §9.2 shows the loader opening `sqlite3.connect`,
setting `PRAGMA foreign_keys`, setting `row_factory`, and issuing its own
`BEGIN`.

**Implementation:** `loader.py` calls `DatabaseConnection.read_snapshot()` and
`DataAccessLayer.query_table()`. It contains no SQL. `read_snapshot()` is a new
context manager in `db/connection.py` issuing a deferred `BEGIN` and always
rolling back.

**Rationale:** Following §9.2 literally would add a fourth copy of the connection
setup and a second module that writes SQL, against the architecture the project
holds everywhere else. Putting the `BEGIN` in `connection.py` rather than in the
generator is what preserves DEV-03 — transaction control lives in one module.
`BEGIN` is deferred rather than `IMMEDIATE` because this is a reader and must not
take a write lock.

**Also covered:** §9.2 orders `TypeDefinitions` by `kind, name COLLATE NOCASE,
id`, where the DAL orders by `id`. The loader applies the LLD's ordering in
Python after loading, rather than adding a second ordering path to the finished
DAL. The snapshot is already fully in memory; a Python sort is equally
deterministic.

---

### DEV-46 — The report timestamp is injected, not read from a clock *(Gap-fill)*

**Documents say:** SRS-101 requires byte-identical output for the same database
content, generator version and work configuration. LLD-04 §7 does not say
whether the report carries a generation timestamp. `docs/PHASE4_SCOPE.md` §5.4
requires the question be decided in the design.

**Implementation:** `GeneratorConfig.generated_at: str | None = None`. When
`None` the report omits the timestamp line entirely; when set, the value is
rendered verbatim. The CLI supplies a real timestamp; tests supply a fixed one.

**Rationale:** SRS-101's own wording — "and work configuration" — covers an
injected timestamp, so determinism holds without weakening the requirement. The
alternative, excluding the timestamp from the comparison, makes the test weaker
than the requirement and leaves a live source of nondeterminism in the product
to protect the test from.

**Verification:** determinism is asserted by comparing the **bytes** of two
written reports, not two Python strings — a string comparison passes even when
encoding or line endings differ, which is precisely what SRS-101 forbids.

---

### DEV-47 — R210 templates are injected as a `TemplateSet` *(Refinement)*

**Documents say:** LLD-04 §2 places four template modules under
`r210/templates/`, and §6.1 defines their functions. §6.7 sketches a
module-level `RELATIONSHIP_TYPE_MAP`.

**Implementation:** A frozen `TemplateSet` dataclass of eight callables, carried
on `GeneratorConfig`, alongside `NamingPolicy` (SRS-019d) and
`AccessPointPolicy` (SRS-064). The four modules remain where §2 puts them and
keep §6.1's names and signatures; their bodies delegate to
`UNCONFIGURED_TEMPLATES`, which raises `TemplateNotConfigured` naming the unmet
entry criterion.

**Rationale:** The framework must be testable. §6.2's dispatch, §6.3's ordering,
§6.4's child ordering, §6.5's exclusion and SRS-101's byte-determinism are all
real logic with nothing to do with template content, and injecting a synthetic
`TemplateSet` exercises every one of them end to end. Module-level stubs would
leave that logic reachable only through monkeypatching, and would make installing
the work templates an edit to committed source rather than a configuration value.

**Effect on DEV-31:** amended, not closed. `trigger_generation` now delegates.
`report_only` is fully operative; `r210_only` and `both` run the pipeline and
report the unmet Phase 5 entry criteria by SRS number, instead of a blanket "not
yet implemented". DEV-31 closes when real templates are installed.

The unmet criteria are checked **before** rendering rather than by catching a
template raise: an empty database calls no template at all, and reporting success
for an R210 mode that could never produce a file would misreport the
configuration rather than the data.

---

### DEV-48 — `trigger_generation` requires `output_dir` *(Correction)*

**Documents say:** LLD-02 §7.9 gives `trigger_generation` a `mode` argument and
no destination. LLD-04 §3.1 gives `Generator` an `output_dir` constructor
argument without saying where it comes from.

**Implementation:** `output_dir` is a required tool argument with no default.

**Rationale:** Found by running the tool rather than by testing it. With a
relative default, `trigger_generation` wrote a review report into the repository
root — wherever the server process happened to be started. Output paths are work
configuration (SRS-019d) and this repository copy has none, so any default is a
guess, and a relative one is a guess that writes to an arbitrary directory. The
review CLI supplies its own documented default (`DEFAULT_OUTPUT_DIR`), because a
local interactive program may reasonably resolve against the working directory —
but it states that default rather than inheriting one.

---

### DEV-49 — Generation summary keys renamed at the tool boundary *(Correction)*

**Documents say:** LLD-04 §10 defines `GenerationResult.summary()` with keys
`r210_files_generated`, `report_generated`, `warnings`, `errors`,
`exported_artifacts`.

**Implementation:** `summary()` keeps LLD-04's names. The `trigger_generation`
tool maps `warnings` → `excluded_pending_children` and `errors` →
`excluded_unresolved_references` when building its response.

**Rationale:** `warnings` already means something else in an MCP response
envelope — the list of duplicate-detection strings of SRS-034/SRS-121. Splicing
the generator's integer count in under the same name produced a response whose
`warnings` was sometimes a list and sometimes an int; the review CLI's display
layer iterated it and raised `TypeError`. Renaming at the boundary that owns the
response shape leaves LLD-04 §10 intact for the generator's own API.

---

### DEV-50 — `run()` rewritten against the MCP SDK's actual API *(Correction)*

**Documents say:** LLD-02 §9 registers each tool with
`server.call_tool(name)(handler)` on `mcp.server.Server`.

**Implementation:** `mcp.server.lowlevel.Server` constructed with `on_list_tools`
and `on_call_tool` callables. `build_server()` is split out from `run()` so the
wiring is testable without opening a transport.

**Rationale:** The sketch does not work. `Server` has no `call_tool` attribute in
the SDK installed here (`mcp` 2.0.0); the lowlevel server dispatches by name
itself, which is closer to what `tools/registry.py` already does. This was the
one never-executed path in the codebase (`docs/REMAINING_WORK.md` §4.1), and
running it is what found the defect.

**Consequences:** `pyproject.toml` moves from `mcp>=1.0` to `mcp>=2.0` — only 2.x
is verified, and the 1.x registration API is not what this code calls. An
`McpError` is returned as a `CallToolResult` with `is_error=True` rather than
raised, because SRS-109 requires the caller receive the operation, field, reason
and affected key.

**Known gap:** tools are advertised with a permissive input schema
(`{"type": "object", "additionalProperties": true}`). Per-tool JSON Schema
generation from the existing `CreateSpec`/`UpdateSpec`/`QuerySpec` descriptors is
open work, recorded in `docs/REMAINING_WORK.md`.

**Verification:** driven out of band against a real `ClientSession` over stdio —
35 tools listed, create and query round-tripped, SRS-015a projection confirmed on
the wire, SRS-082a approval denied, unknown tool returned a structured error.
`tests/test_r210_mcp/test_server_adapter.py` locks the wiring in, skipped when
the SDK is absent.

---

### DEV-51 — A missing SDK is reported, not raised as a traceback *(Gap-fill)*

**Documents say:** nothing. LLD-02 §9 assumes the SDK is present.

**Implementation:** `run()` raises `SdkNotInstalled`, and `__main__` prints it
and exits 1. The message names the dependency, gives the install command, states
the 2.x constraint, and says that the review CLI, the generator and the tool
handlers all work without it.

**Rationale:** Found by rehearsing the transfer in a virtualenv with no `mcp`
installed. The server died with `ModuleNotFoundError: No module named 'anyio'` —
a *transitive* dependency, so the message named neither `mcp` nor anything the
operator could act on, and gave no hint that the rest of the prototype was
unaffected. The work computer may have no package index, which makes this the
likely first experience there rather than an edge case.

**Note on the tests:** they live in `tests/test_r210_mcp/test_server_sdk_absence.py`,
not in `test_server_adapter.py`, because that module opens with
`importorskip("mcp")` and would skip exactly on the machine these assertions are
about.

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
| DEV-25 | Gap-fill | `McpValidationError` definition | Incorporated into LLD-02 v1.5 |
| DEV-26 | Refinement | Handlers are functions over `ToolContext` | Incorporated into LLD-02 v1.5 |
| DEV-27 | Gap-fill | SRS-036a approval block (`check_references_resolved`) | Incorporated into LLD-02 v1.5 |
| DEV-28 | Addition | Six DAL methods for the graph and the engine | Incorporated into LLD-02 v1.5 |
| DEV-29 | Correction | Records are dataclasses, not dict rows | Incorporated into LLD-02 v1.5 |
| DEV-30 | Refinement | Projection applied at the dispatch boundary | Incorporated into LLD-02 v1.5 |
| DEV-31 | Boundary | `trigger_generation` reports generator unavailable | Incorporated into LLD-02 v1.5 |
| DEV-32 | Refinement | Descriptor engine behind the named handlers | Incorporated into LLD-02 v1.5 |
| DEV-33 | Correction | Phase 3 absorbs Phases 4–6 | **Approved by owner 2026-08-12** |
| DEV-34 | Refinement | Validators take the operation name | Incorporated into LLD-02 v1.5 |
| DEV-35 | Refinement | `table_hint` optional on `set_review_status` | Incorporated into LLD-02 v1.5 |
| DEV-36 | Correction | SRS-034 compares normalized forms over candidates | Incorporated into LLD-02 v1.5 |
| DEV-37 | Correction | SRS-070 enforced by the schema, not the validator | Incorporated into LLD-02 v1.5 |
| DEV-38 | Refinement | §11.2 mutation restriction extends to update tools | Incorporated into LLD-02 v1.5; code corrected to match |
| DEV-39 | Refinement | Phase 5 split: framework built, template bodies deferred | Phase 4/5 — pending review |
| DEV-40 | Correction | Review CLI bridge targets `tools/registry`, not `server` | Phase 4/5 — pending review |
| DEV-41 | Gap-fill | `ReviewToolBridge` in `bridge.py` | Phase 4/5 — pending review |
| DEV-42 | Gap-fill | CLI exit codes 0/1/2 | Phase 4/5 — pending review |
| DEV-43 | Gap-fill | `DAL.search_by_name_pattern` | Phase 4/5 — pending review |
| DEV-44 | Refinement | Colour gated on `isatty()`; stdout forced to UTF-8 | Phase 4/5 — pending review |
| DEV-45 | Correction | Loader uses `connection.py`/`dal.py`, not raw `sqlite3` | Phase 4/5 — pending review |
| DEV-46 | Gap-fill | Report timestamp injected via `generated_at` | Phase 4/5 — pending review |
| DEV-47 | Refinement | R210 templates injected as a `TemplateSet` | Phase 4/5 — pending review |
| DEV-48 | Correction | `trigger_generation` requires `output_dir` | Phase 4/5 — pending review |
| DEV-49 | Correction | Generation summary keys renamed at the tool boundary | Phase 4/5 — pending review |
| DEV-50 | Correction | `run()` rewritten against the real MCP SDK API | Phase 4/5 — pending review |
| DEV-51 | Gap-fill | Missing SDK reported actionably, not as a traceback | Phase 4/5 — pending review |
| DEV-O-01 | Resolved decision | Report-only behavior for damaged current-version schema | Approved; incorporated into SRS v5.3 |
| DEV-O-02 | Resolved decision | Nullable unresolved cross-artifact type references | Approved and implemented in V002 |
| DEV-O-03 | Resolved decision | `r210-review` entry point | Closed at Phase 3 — the entry point resolves; the CLI itself is Phase 8 scope |
| DEV-O-04 | Open item | SRS-015 external data transfer | **Blocking, pre-existing** |

All Phase 1 interpretations and deviations are explicitly recorded. Approved
items are incorporated into the v5.4 requirements baseline. Remaining entries
are either scheduled future-phase work or the external SRS-015 authorization.

DEV-17 through DEV-24 record Phase 2 and have not yet been reviewed.

DEV-39 through DEV-51 record Phase 4 and the Phase 5 framework, and have not yet
been reviewed. Six of the thirteen were found by **running** the system rather
than by reading the documents, and each corrects a real fault:

- **DEV-48** — `trigger_generation` wrote a review report into the repository
  root, because its `output_dir` defaulted to a relative path.
- **DEV-49** — the review CLI raised `TypeError` on every successful `report`,
  because LLD-04 §10 names an integer count `warnings` and an MCP envelope
  already uses that name for a list.
- **DEV-50** — `run()` could not have worked against any installed SDK; LLD-02
  §9's registration call does not exist in `mcp` 2.x.
- **DEV-44** (second half) — the CLI died with `UnicodeEncodeError` on a Windows
  console, because LLD-06 §6.2's specified glyphs are outside cp1252.
- **DEV-47** (second half) — R210 modes reported success on an empty database,
  because no template was called and so nothing raised.

DEV-31 is **amended, not closed** (see DEV-47): `trigger_generation` now
delegates to the generator, `report_only` is operative, and the R210 modes name
their unmet entry criteria. It closes when the work templates are installed.

DEV-25 through DEV-38 record Phase 3 and are **closed**: LLD-02 v1.5 has been
amended so the document and the implementation agree, and each entry names the
section that now carries it. DEV-36 supersedes DEV-24 — the Phase 2 split of
SRS-034 between an indexed DAL query and caller-side normalization does not
work, because an exact-match query returns nothing for a caller to normalize;
LLD-02 §8 now describes the working algorithm.

One of the fourteen went the other way. DEV-38 records a case where the
document was right and the code was wrong: LLD-02 §11.2 already restricted
create responses to `unique_key` and warnings, and the implementation was
returning full projected records. **The code was corrected**, and §11.2 extended
to cover update tools for the same reason.

No Phase 3 entry required an SRS amendment. Every one resolved against LLD-02,
which is the level at which they arose.

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-11 | Initial version covering Phase 1 (database foundation). |
| 1.1     | 2026-08-11 | Recorded approval of DEV-01 through DEV-16, resolved DEV-O-01 as report-only, incorporated source-requirement reviewability into SRS v5.3, and retained DEV-O-02 as the remaining Phase 1 stakeholder decision. |
| 1.2     | 2026-08-12 | Resolved DEV-O-02 by approving nullable unresolved type references and implementing V002. Recorded that work-specific configuration is intentionally deferred until transfer to the work computer. |
| 1.3     | 2026-08-12 | Added section 4A covering Phase 2 (connection layer and DAL): DEV-17 through DEV-24. |
| 1.4     | 2026-08-12 | Added section 4B covering Phase 3 (validation layer, 35 tool handlers, server adapter): DEV-25 through DEV-37. Recorded owner approval of DEV-33, the decision that Phase 3 absorbs Phases 4–6. DEV-36 supersedes DEV-24. |
| 1.5     | 2026-08-12 | Closed the Phase 3 register. DEV-25 through DEV-38 are incorporated into LLD-02 v1.5, which now matches the implementation section by section. Added DEV-38, the one entry resolved by correcting the code rather than the document: §11.2 already restricted create responses to `unique_key` and warnings, the implementation was returning full projected records, and the restriction now extends to update tools. Closed DEV-O-03 — its premise (a missing `cli.py`) is out of date; the entry point resolves and the CLI itself is Phase 8 scope. No Phase 3 entry required an SRS amendment. |
| 1.6     | 2026-08-13 | Recorded that absorbing three phases retired the original eight-phase map (DEV-33 follow-on) and pointed at `docs/REMAINING_WORK.md` §1A as the authoritative old-to-new mapping. References to "Phase 7"/"Phase 8" in earlier entries are historical. |
| 1.7     | 2026-08-15 | Added section 4C covering Phase 4 and the Phase 5 framework: DEV-39 through DEV-50. Recorded that five of the twelve were found by executing the system rather than by document review, including three that would have failed in the field (DEV-44, DEV-48, DEV-49) and one path that could never have worked (DEV-50). DEV-31 amended rather than closed. |
| 1.8     | 2026-08-15 | Added DEV-51, found by rehearsing the transfer in a virtualenv without the `mcp` SDK: the server reported a missing transitive dependency (`anyio`) instead of the SDK, the install command, or the fact that everything else still works. |
