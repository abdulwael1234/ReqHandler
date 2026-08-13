# Phase 2 — Implemented Requirements

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-IMPL-02                                                 |
| **Phase**            | Phase 2 — Connection management and Data Access Layer        |
| **Date**             | 2026-08-12                                                   |
| **Branch**           | `feature/phase2-data-access-layer`                           |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-02 v1.4 §3.1–3.2, §4, §5         |
| **Companion**        | `docs/DEVIATIONS_FROM_REQUIREMENTS.md` §4A (DEV-17–DEV-24)   |
| **Design**           | `docs/superpowers/specs/2026-08-12-phase2-data-access-layer-design.md` |
| **Predecessor**      | `docs/PHASE1_IMPLEMENTED_REQUIREMENTS.md`                    |
| **Status**           | Complete — 216 tests passing, ruff clean, mypy strict clean  |

---

## 1. Scope of Phase 2

Phase 1 built the schema and the record models. Phase 2 builds the only layer
permitted to touch them: connection management and the Data Access Layer that
every Phase 3 tool handler will call.

**Delivered:**

| Module | Purpose |
|--------|---------|
| `src/r210_mcp/errors.py` | `McpError`, `McpResult` — the structured response shapes (LLD-02 §3.1–3.2) |
| `src/r210_mcp/db/connection.py` | `DatabaseConnection` — pragmas, `transaction()`, `read_only()` (LLD-02 §4) |
| `src/r210_mcp/db/dal.py` | `DataAccessLayer` — parameterized SQL for all 15 application tables (LLD-02 §5) |

**Explicitly not in Phase 2:** the validation layer, status-transition
enforcement, parent-approval blocking and demotion, duplicate-warning policy,
connection validation, the tool handlers, and the MCP server entry point.
LLD-02 §5.1 states the DAL "never performs validation — that responsibility
belongs to the validation layer", and Phase 2 holds that line.

**Phase numbering.** The repository carries two phase maps. This work follows
the eight-phase map used by `PHASE1_IMPLEMENTED_REQUIREMENTS.md` §9 and DEV-11,
in which Phase 2 is the DAL. `REPOSITORY_REVIEW_REPORT.md` §7 uses a
five-phase map whose "Phase 2" is a larger shared-operations module; that
scope is covered here plus Phases 3–6 of the eight-phase map.

---

## 2. Status Legend

| Marker | Meaning |
|--------|---------|
| **Full** | The requirement is completely satisfied by Phase 2 code. |
| **Mechanism** | Phase 2 provides the operation the requirement needs; the rule that decides *when* to invoke it belongs to a named later phase. This split is the LLD's, not an omission. |

---

## 3. Connection and Transaction Requirements

| SRS | Requirement (abridged) | Status | Implementation | Verified by |
|-----|------------------------|--------|----------------|-------------|
| SRS-032 | Foreign-key enforcement enabled in SQLite | Full | `PRAGMA foreign_keys = ON` in `connect()` | `test_foreign_keys_are_enforced`, `test_foreign_key_violation_is_rejected` |
| SRS-084 | Each write operation wrapped in a database transaction | Full | `transaction()` — `BEGIN IMMEDIATE`, commit on clean exit, rollback and re-raise on failure | `TestTransaction` (4 tests) |
| SRS-106 | All database write paths use transactions | Full | Same context manager; the DAL takes a connection and never opens its own | `test_commits_on_clean_exit`, `test_rolls_back_on_exception` |
| SRS-113 | No concurrency or performance optimization | Full | One connection per operation, no pooling; WAL and `busy_timeout` for crash safety and lock behaviour only | Design; `test_journal_mode_is_wal`, `test_busy_timeout_is_configured` |

Connections are closed in a `finally` block on both the success and failure
paths, so a failed operation leaks no handle — verified by
`test_connection_is_closed_after_an_exception`.

---

## 4. Data Access Requirements

| SRS | Requirement (abridged) | Status | Implementation | Verified by |
|-----|------------------------|--------|----------------|-------------|
| SRS-026 | Integer `id` primary key per main record | Full | `_insert` excludes `id`; SQLite assigns it and `lastrowid` returns it | `test_every_table_round_trips`, `test_id_cannot_be_written` |
| SRS-027 | Referable records carry a unique `unique_key` | Mechanism | `_get_by(..., "unique_key", ...)`, `resolve_unique_key` | `TestRoundTrip`, `test_resolve_unique_key_finds_the_owning_table` — *UUID generation is Phase 3* |
| SRS-029 | Internal relationships use foreign keys to local IDs | Full | FK columns written as integer values; violations surface from SQLite | `test_foreign_key_violation_reaches_the_caller` |
| SRS-030 | Missing optional relationship stored as `NULL`, never `0` | Full | Nullable parameters default to `None` and are bound as SQL NULL | `test_none_filter_matches_null_not_nothing` |
| SRS-036, SRS-036a | Unresolved type references stored as `NULL` and queryable | Full | `element_type_id` / `type_definition_id` / `port_interface_id` accept `None`; a `None` filter compiles to `IS NULL`, not `= NULL` | `test_none_filter_matches_null_not_nothing` |
| SRS-037, SRS-108 | Deterministic ordering via `position` | Full | `_order_by` sorts ordered child tables by `(parent_fk, position)`, all others by `id`, derived from `CHILD_PARENT_MAP` | `test_children_are_ordered_by_parent_then_position`, `test_get_connection_members_are_position_ordered` |
| SRS-035 | Five review states supported | Mechanism | `update_status` writes any state the schema's CHECK accepts | `test_update_status_sets_state_and_note` — *transition rules are Phase 3* |
| SRS-035a, SRS-091a | Reviewable children carry state; subtypes carry none; inapplicable notes are ignored | Full | `update_status` rejects a status write to a subtype table and silently ignores `review_note` for a child table without that column | `test_update_status_rejects_a_table_without_status`, `test_update_status_ignores_a_note_on_a_table_without_the_column` |
| SRS-035b | Permitted status transitions | Mechanism | Not enforced here by design | *Enforcement is Phase 3 (LLD-02 §6.2)* |
| SRS-038a | Exactly one subtype detail row per `TypeDefinitions` parent | Mechanism | `get_simple_type_definition_by_parent`, `get_array_type_definition_by_parent` resolve the row; `UNIQUE` enforces the cardinality | `test_every_table_round_trips` — *"required in the same operation" is Phase 4* |
| SRS-046, SRS-053 | Parent approval depends on child states | Mechanism | `get_children_statuses` | `test_get_children_statuses` — *the blocking rule is Phase 4* |
| SRS-074 | Typed polymorphic artifact reference | Mechanism | `get_record_by_unique_key(table, key)` resolves a runtime-named table via `ARTIFACT_TYPE_TABLE_MAP` | `test_get_record_by_unique_key_resolves_a_runtime_table` |
| SRS-034, SRS-121 | Duplicate detection by case-insensitive name | Mechanism | `find_duplicates_by_name`, using the `COLLATE NOCASE` indexes from V001 | `test_find_duplicates_by_name_is_case_insensitive`, `test_find_duplicates_by_name_narrows_by_kind` — *whitespace normalization and the warning itself are Phase 6; see DEV-24* |
| SRS-091 | Delete operations excluded from the MCP tool surface | Full | No `DELETE` statement exists anywhere in `dal.py` | Module contents |

---

## 5. Error Reporting Requirements

| SRS | Requirement (abridged) | Status | Implementation | Verified by |
|-----|------------------------|--------|----------------|-------------|
| SRS-083 | Invalid inputs rejected with the field and reason | Mechanism | `McpError(operation, field, reason, affected_key)` | *Input validation is Phase 3; Phase 2 supplies the shape* |
| SRS-109 | Errors report operation, field, reason, and affected identity | Full | `McpError` requires `reason`; `to_dict()` emits all four keys | `test_mcp_error_requires_a_reason`; structure of `errors.py` |

Constraint violations are deliberately **not** translated inside the DAL.
`sqlite3.IntegrityError` propagates to the caller, which is the layer that
knows the tool name and the affected `unique_key` needed to build a complete
`McpError`. Catching it in the DAL would produce errors that cannot satisfy
SRS-109. Verified by `TestConstraintsPropagate` (3 tests).

---

## 6. Design Properties Worth Recording

**The column registry cannot drift.** `TABLE_COLUMNS` is derived from
`dataclasses.fields(TABLE_RECORD_MAP[table])` rather than written out a third
time. Combined with DEV-15, which pins record field order to column order, this
means the schema, the models, and the DAL share one source of truth.
`test_columns_match_the_live_schema` compares the derived registry against
`PRAGMA table_info` for all 15 tables.

**Identifiers are allowlisted, values are bound.** SQLite cannot parameterize a
table or column name, so a table-driven DAL has to guard them explicitly. Every
identifier is resolved through the registry and rejected with `ValueError` if
unknown; every value uses a `?` placeholder. `TestIdentifierAllowlist` (6
tests) covers unknown tables, unknown columns on insert / update / filter,
`schema_version`, and attempts to write `id`.

**The typed surface survives.** The generic core is 12 private methods. The 69
public ones carry explicit signatures, so Phase 3 call sites remain checkable under
`mypy --strict` — the reason for keeping wrappers rather than exposing
`insert(table, dict)`.

---

## 7. Verification Summary

```
216 tests passing (173 from Phase 1, 43 added)
  11  test_connection.py  — pragmas, commit, rollback, connection closure
  31  test_dal.py         — registries, round-trip, query, cross-cutting,
                            identifier allowlist, constraint propagation
   1  test_errors.py      — required structured-error reason

ruff check src tests   → All checks passed
mypy (strict) src      → Success: no issues found in 59 source files
```

**Testing method:** development-level, by agreement. These tests establish that
the layer works and that its boundaries hold; they are not an exhaustive
verification suite. Independent testing of Phase 2 is a separate activity
performed by a dedicated tester after this hand-off, and the coverage above
should be treated as a starting point rather than a completed test campaign.

Note: `mypy` on `tests/` reports 36 pre-existing errors in the Phase 1 test
files (missing annotations, `int | None` assignments). These are untouched by
Phase 2 — the three new test modules type-check clean under
`MYPYPATH=src mypy tests/test_r210_mcp/test_dal.py tests/test_r210_mcp/test_connection.py tests/test_r210_mcp/test_errors.py`.
Phase 1's recorded gate was `mypy` over sources only.

### Running the tests

```
python -m pytest tests/ -q
```

As in Phase 1, this machine denies creation of `.pytest_cache` in the
repository directory; append `-p no:cacheprovider` to silence the warning.

---

## 8. What Phase 2 Deliberately Does Not Do

> **Superseded numbering (2026-08-13).** The phase column below uses the
> original eight-phase map, now retired. `docs/REMAINING_WORK.md` §1A carries
> the authoritative old-to-new mapping: its Phases 4–6 were absorbed into
> Phase 3 (DEV-33), and its Phases 7–8 are now Phase 4 and Phase 5.

| SRS | Requirement | Owning phase |
|-----|-------------|--------------|
| SRS-035b, SRS-082a, SRS-082b, SRS-091a | Status transition enforcement, approval authority, content-change demotion | Phase 3 |
| SRS-083 | Tool input validation | Phase 3 |
| SRS-035c, SRS-046, SRS-053, SRS-092a | Parent approval blocking and automatic demotion | Phase 4 |
| SRS-044, SRS-055 | Subtype kind-matching, interface-type matching | Phase 4–5 |
| SRS-069, SRS-071, SRS-072, SRS-122, SRS-125 | Connection validation and transactional revalidation | Phase 5 |
| SRS-034, SRS-121 | Name normalization and the duplicate warning itself | Phase 6 |
| SRS-085–SRS-090 | The MCP tool surface and server entry point | Phase 3–6 |
| SRS-101–SRS-104a | Deterministic generation and reporting | Phase 7 |
| SRS-118, SRS-123 | Review workflow and local review CLI | Phase 8 |

---

## 9. Hand-off Notes for Testing

Areas most worth independent scrutiny, in the order I would attack them:

1. **`_where` with `None` filters** — the `IS NULL` branch is the one place
   where a filter changes SQL shape rather than just parameters.
2. **`_order_by` for tables in `CHILD_PARENT_MAP` without a `position` column**
   (`PortPrototypeFunctions`) — should fall through to `id`.
3. **`update_status` on all 15 tables** — the status/review_note column matrix
   is asserted for two tables here, not all of them.
4. **`resolve_unique_key` collision behaviour** — it returns the first match in
   sorted table order and assumes SRS-027 global uniqueness, which the schema
   enforces only per-table.
5. **`find_duplicates_by_name`** on `PortInterfaces` and `PortPrototypes` —
   only `TypeDefinitions` is covered here.
6. **Insert with an explicitly-passed `None`** versus an omitted argument —
   both should produce SQL NULL, and the schema default should apply only when
   the column is omitted entirely.

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-12 | Initial record of Phase 2 implementation. |
