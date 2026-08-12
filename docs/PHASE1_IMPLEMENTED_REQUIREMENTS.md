# Phase 1 — Implemented Requirements

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-IMPL-01                                                 |
| **Phase**            | Phase 1 — Database Foundation (models, migration, initializer)|
| **Date**             | 2026-08-12                                                   |
| **Branch**           | `feature/phase1-database-foundation`                         |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-01 v1.1, R210-LLD-02 v1.4, R210-LLD-05 v1.4 |
| **Companion**        | `docs/DEVIATIONS_FROM_REQUIREMENTS.md`                       |
| **Status**           | Complete — 152 tests passing, ruff clean, mypy strict clean   |

---

## 1. Scope of Phase 1

Phase 1 builds the layer everything else depends on: the SQLite schema, the
component that creates and upgrades it, and the in-memory record models that
mirror it.

**Delivered:**

| Module | Purpose |
|--------|---------|
| `src/r210_db_init/migrations/v001_initial_schema.py` | DDL for all 15 application tables + 29 indexes (LLD-01 §3) |
| `src/r210_db_init/migrations/v002_nullable_type_references.py` | Data-preserving upgrade making four unresolved type-reference FKs nullable (SRS-036a) |
| `src/r210_db_init/initializer.py` | `DatabaseInitializer`, `InitResult` — creation, migration, version tracking, verification (LLD-05 §4) |
| `src/r210_db_init/cli.py` | `init` / `reset` command-line surface (LLD-05 §3) |
| `src/r210_db_init/dev_reset.py` | Development-only destructive reset (LLD-05 §6) |
| `src/r210_mcp/db/models.py` | Record dataclasses, status constants, parent–child registry (LLD-02 §3.3–§3.5) |

**Explicitly not in Phase 1:** the MCP server and its tools, the DAL, the
generator, and the review CLI. Those consume this layer in later phases.

---

## 2. Status Legend

| Marker | Meaning |
|--------|---------|
| **Full** | The requirement is completely satisfied by Phase 1 code. |
| **Schema** | The database-level half is enforced now; the remaining application-level half belongs to a named later phase. This is by design — the SRS/LLD assign that half to the MCP tool boundary. |
| **Interim** | Phase 1 implements the documented safe default, but a stakeholder policy decision may require a later migration. |

---

## 3. Database Initialization Requirements

| SRS | Requirement (abridged) | Status | Implementation | Verified by |
|-----|------------------------|--------|----------------|-------------|
| SRS-025 | Initializer creates and upgrades schema without deleting content | Full | `initializer.py` | `TestDataPreservation`, `TestIdempotency` |
| SRS-094 | Safe `init_db` operation outside the Gemini-facing MCP tools | Full | `cli.py::main`, `DatabaseInitializer.init_db` | `TestInitCommand` |
| SRS-095 | `init_db` creates the database file when absent | Full | `sqlite3.connect()` in `init_db` | `test_creates_database_file_when_absent` |
| SRS-096 | `init_db` creates schema objects during initialization/migration and reports damage to a current-version schema without implicit repair | Full | `V001InitialSchema.up`, `_create_indexes`, `_verify_schema` | `test_creates_all_application_tables`, `test_creates_indexes_declared_in_lld01`, `TestSchemaVerification` |
| SRS-097 | `init_db` records the database schema version | Full | `_ensure_version_table`, version INSERT | `TestSchemaVersionTracking` |
| SRS-098 | `init_db` is idempotent | Full | `CREATE ... IF NOT EXISTS` + version check | `TestIdempotency` (3 tests) |
| SRS-099 | `init_db` preserves all existing data | Full | Transactional V002 rebuilds copy all rows and IDs; failures roll back atomically | `test_existing_rows_survive_reinitialization`, `test_v002_preserves_existing_type_reference_rows` |
| SRS-100 | Destructive reset is development-only, outside the Gemini workflow | Full | `dev_reset.py`, `--confirm` gate | `TestResetCommand`, `TestDevelopmentReset` |
| SRS-124 | Each migration + version update is one transaction, rolling back on failure | Full | `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` in `init_db` | `TestMigrationRollback` (3 tests) |
| SRS-109 | Errors report the operation, reason, and affected identity | Full | `InitResult.error`, CLI stderr output | `test_init_writes_failure_reason_to_stderr` |

---

## 4. Data Model — Common Conventions

| SRS | Requirement (abridged) | Status | Implementation | Verified by |
|-----|------------------------|--------|----------------|-------------|
| SRS-026 | Each main record has an integer `id` primary key | Full | `id INTEGER PRIMARY KEY` on all 15 tables | `test_dataclass_fields_match_table_columns_in_order` |
| SRS-027 | Each referable record has a unique `unique_key` | Schema | `unique_key TEXT NOT NULL UNIQUE` | `TestUniqueKeys` — *UUID generation is Phase 3 (MCP)* |
| SRS-029 | Internal relationships use foreign keys to local IDs | Full | `REFERENCES` clauses per LLD-01 §4 | `TestReferentialIntegrity` |
| SRS-030 | Missing optional relationship stored as `NULL`, never `0` | Schema | Nullable FK columns | `TestNullability` — *"never 0" discipline is Phase 3* |
| SRS-031 | Repeated/child information in child tables, not serialized lists | Full | 7 child tables + 2 subtype tables | Schema structure |
| SRS-032 | Foreign-key enforcement enabled in SQLite | Full | `PRAGMA foreign_keys = ON` | `TestForeignKeyEnforcement` |
| SRS-035 | Five review states supported | Full | 5-value CHECK on every `status` column | `TestStatusConstraints` (8 tests) |
| SRS-035a | New records default to `pending_review`; subtypes carry no `status` | Full | Column `DEFAULT 'pending_review'`; no `status` on subtype tables | `test_new_records_default_to_pending_review`, `test_structural_subtype_tables_carry_no_status_column` |
| SRS-035b | Permitted status transitions (five-state reviewable records and issues) | Schema | `ARTIFACT_TRANSITIONS`, `ISSUE_TRANSITIONS` in `models.py` | `TestStatusTransitions` (7 tests) — *enforcement is Phase 3* |
| SRS-036 | `PortPrototypes.port_interface_id` is `NULL` while unresolved | Full | Nullable FK column | `test_port_prototype_interface_may_be_null_while_unresolved` |
| SRS-036a | Four cross-artifact type-reference FKs allow `NULL` while unresolved | Schema | V002 table rebuilds; nullable model fields | `TestNullability`, `test_v002_preserves_existing_type_reference_rows` — *issue creation and approval/export gates belong to later phases* |
| SRS-037 | `position` NOT NULL and unique within parent | Full | `NOT NULL` + `UNIQUE (parent_fk, position)` on all 6 ordered tables | `TestPositionConstraints` (4 tests) |
| SRS-038 | Child records inherit traceability through their parent | Full | No `source_requirement_id` on any child table | Schema structure |
| SRS-038a | Exactly one subtype detail row per `TypeDefinitions` parent | Schema | `UNIQUE` on `type_definition_id` | `TestSubtypeCardinality` — *"required in same operation" is Phase 4* |
| SRS-038b | `position` ≥ 1 and `array_size` ≥ 1 | Full | CHECK constraints | `test_position_must_be_positive`, `test_array_size_must_be_positive` |
| SRS-038c | Element/enum-value names unique within parent | Full | `UNIQUE (parent_fk, name)` | `TestChildNameUniqueness` |
| SRS-108 | Deterministic ordering via `position` | Full | Same constraints as SRS-037 | `TestPositionConstraints` |
| SRS-110 | No audit trail for review state transitions | Full | No history table exists — satisfied by omission | Schema structure |

---

## 5. Data Model — Table Definitions

Every table required by LLD-01 §3 exists with the specified columns, types,
nullability, defaults, and constraints. The column set and column *order* of
each table is pinned by `test_dataclass_fields_match_table_columns_in_order`.

| SRS | Table / constraint | Status | Verified by |
|-----|--------------------|--------|-------------|
| SRS-039, SRS-040, SRS-041 | `SourceRequirements`; nullable `source_text`; nullable `source_requirement_id` on all artifacts | Full | `TestNullability` |
| SRS-042, SRS-043 | `TypeDefinitions`; `kind` CHECK (4 values) | Full | `test_type_definition_kind_is_restricted`, `test_type_definition_accepts_each_supported_kind` |
| SRS-045 | Enumerations registered as a `TypeDefinitions` kind | Full | `kind = 'enum'` accepted |
| SRS-047 | `SimpleTypeDefinitions` | Full | Schema + model tests |
| SRS-048 | `ArrayTypeDefinitions` | Full | Schema + model tests |
| SRS-049 | `StructElements` | Full | Schema + model tests |
| SRS-050 | `EnumValues` | Full | Schema + model tests |
| SRS-051, SRS-052 | `PortInterfaces`; `interface_type` CHECK (2 values) | Full | `test_interface_type_is_restricted` |
| SRS-054 | Data elements and operations in separate child tables | Full | Schema structure |
| SRS-056 | `InterfaceDataElements` | Full | Schema + model tests |
| SRS-057 | `ClientServerOperations` | Full | Schema + model tests |
| SRS-058, SRS-059 | `OperationArguments`; `direction` CHECK (`input`/`output`/`input_output`) | Full | `test_operation_argument_direction_is_restricted` |
| SRS-060, SRS-061 | `PortPrototypes`; `direction` CHECK (2 values) | Full | `test_port_prototype_direction_is_restricted` |
| SRS-062, SRS-063 | `PortPrototypeFunctions`; `relationship_type` CHECK (2 values) | Full | `test_port_prototype_function_relationship_type_is_restricted` |
| SRS-065, SRS-067 | `PortConnections` as one global logical connection | Full | Schema structure |
| SRS-066 | `PortConnectionMembers` | Full | Schema + model tests |
| SRS-068 | Direction stored only on `PortPrototypes` | Full | `test_connection_members_carry_no_direction_column` |
| SRS-070 | A port prototype appears at most once per connection | Schema | `TestPortConnectionMembership` — *full revalidation (SRS-122) is Phase 5* |
| SRS-074 | `ReviewIssues`; typed polymorphic artifact reference | Full | `TestReviewIssueArtifactReference` (4 tests), `TestArtifactTypeMap` |
| SRS-075 | `issue_type` CHECK (5 values) | Full | `test_review_issue_type_is_restricted` |
| SRS-076 | `ReviewIssues.status` CHECK (3 values) | Full | `test_review_issue_status_is_restricted` |

---

## 6. Model Layer (LLD-02 §3.3–§3.5)

| Item | SRS trace | Verified by |
|------|-----------|-------------|
| 16 frozen record dataclasses, one per table, field order matching column order | SRS-026, SRS-039–SRS-076 | `TestRecordDataclasses` (33 tests) |
| `ARTIFACT_STATUSES`, `ISSUE_STATUSES` | SRS-035, SRS-076 | `TestStatusConstants` |
| `ARTIFACT_TRANSITIONS`, `ISSUE_TRANSITIONS` | SRS-035b | `TestStatusTransitions` |
| `ARTIFACT_TABLES`, `REVIEWABLE_CHILD_TABLES`, `STRUCTURAL_SUBTYPE_TABLES` | SRS-035a, SRS-091a | `TestTableGroupings` (17 tests) |
| `PARENT_CHILD_MAP`, `CHILD_PARENT_MAP` | SRS-035c, SRS-046, SRS-053 | `TestParentChildRegistry` (6 tests) |
| `ARTIFACT_TYPE_TABLE_MAP` | SRS-074 | `TestArtifactTypeMap` (4 tests) |
| `TABLE_RECORD_MAP` | — (addition, see DEV-11) | `test_every_table_in_the_schema_has_a_record_dataclass` |

The model tests query the database that the initializer actually creates. A
constant that drifts from the schema — a renamed column, a reordered field, a
registry entry naming a foreign key the database does not declare — fails the
suite. The two layers cannot silently diverge.

---

## 7. Constraint Requirements Satisfied

| SRS | Requirement | How Phase 1 satisfies it |
|-----|-------------|--------------------------|
| SRS-091 | Delete operations excluded from the MCP surface | No delete path exists in any Phase 1 module |
| SRS-093 | Destructive operations not exposed through MCP | `development_reset` lives in `r210_db_init`, never imported by `r210_mcp`; asserted by `TestMcpSurfaceExclusion` |
| SRS-113 | No concurrency/performance optimization | WAL selected for crash safety only, single-writer as designed (LLD-01 §2.1) |
| SRS-115 | No backup or restore management | Not implemented, by design |

---

## 8. Verification Summary

```
152 tests passing
  19  test_initializer.py        — creation, versioning, idempotency, rollback, verification, V002 preservation
  46  test_schema_constraints.py — CHECK / UNIQUE / NULL / FK behaviour
  12  test_cli.py                — init and reset command surface
   6  test_dev_reset.py          — destructive reset behaviour
  69  test_models.py             — model layer cross-checked against the live schema

ruff check src tests   → All checks passed
mypy (strict)          → Success: no issues found in 9 source files
```

**Development method:** test-driven. Every test was written and observed
failing before the corresponding implementation existed. The suite was
additionally mutation-checked — a removed CHECK constraint and a reordered
dataclass field were each independently detected — confirming the tests fail
for the right reasons rather than passing vacuously.

**End-to-end verification** (`python -m r210_db_init`):

| Command | Result |
|---------|--------|
| `init` on a fresh path | exit 0 — version 2, 2 migrations applied, 16 tables, 29 indexes, WAL |
| `init` again | exit 0 — version 2, 0 migrations, `up_to_date` |
| `reset` without `--confirm` | exit 1 — data preserved |
| `reset --confirm` | exit 0 — data cleared, schema recreated at version 2 |

### Running the tests

```
python -m pytest tests/ -q
```

Note: on this machine the repository directory denies creation of
`.pytest_cache`, producing a `PytestCacheWarning`. It does not affect results;
append `-p no:cacheprovider` to silence it. This is an environment permission
issue, not a defect in the code or configuration.

---

## 9. What Phase 1 Deliberately Does Not Do

These requirements are assigned by the SRS/LLD to the MCP tool boundary or the
generator, and are correctly absent from Phase 1:

| SRS | Requirement | Owning phase |
|-----|-------------|--------------|
| SRS-034, SRS-121 | Duplicate-detection warning and name normalization | Phase 6 (the supporting index exists now) |
| SRS-035b | *Enforcement* of status transitions | Phase 3 |
| SRS-035c, SRS-046, SRS-053, SRS-092a | Parent–child approval blocking and auto-demotion | Phase 4 (the registry exists now) |
| SRS-044, SRS-055 | Subtype kind-matching and interface-type matching | Phase 4–5 — explicitly application-level per SRS |
| SRS-069, SRS-071, SRS-072, SRS-122, SRS-125 | Connection validation | Phase 5 |
| SRS-082a, SRS-082b, SRS-091a | Caller-based approval restriction, content-change demotion | Phase 3 |
| SRS-083–SRS-090 | MCP tool surface | Phase 3–6 |
| SRS-101–SRS-104a | Deterministic generation and reporting | Phase 7 |
| SRS-118, SRS-123 | Review workflow and local review CLI | Phase 8 |

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-11 | Initial record of Phase 1 implementation. |
| 1.1     | 2026-08-12 | Added approved SRS-036a behavior through data-preserving V002, updated models/tests, and advanced the current schema to version 2. |
