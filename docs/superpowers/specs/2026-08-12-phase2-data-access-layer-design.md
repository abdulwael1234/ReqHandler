# Phase 2 — Data Access Layer (Design)

| Field | Value |
|---|---|
| **Document ID** | R210-SPEC-P2 |
| **Phase** | Phase 2 — Connection management and Data Access Layer |
| **Date** | 2026-08-12 |
| **Branch** | `feature/phase2-data-access-layer` |
| **Source Documents** | R210-LLD-02 §3.1–3.2, §4, §5 |
| **Predecessor** | Phase 1 — Database Foundation (`docs/PHASE1_IMPLEMENTED_REQUIREMENTS.md`) |

---

## 1. Scope

Phase 2 builds the persistence access layer that every later phase calls. It is
the layer between the Phase 1 schema and the Phase 3 MCP tool handlers.

| File | Contents | LLD |
|---|---|---|
| `src/r210_mcp/errors.py` | `McpError`, `McpResult` | §3.1–3.2 |
| `src/r210_mcp/db/connection.py` | `DatabaseConnection` | §4 |
| `src/r210_mcp/db/dal.py` | `DataAccessLayer` | §5 |

Dependencies flow one way: `dal → models`. `connection` and `errors` depend on
nothing inside the project.

**Explicitly not in Phase 2:** validation, status-transition enforcement,
parent demotion, duplicate-detection *policy*, tool handlers, and the MCP
server entry point. LLD-02 §5.1 states the DAL "never performs validation —
that responsibility belongs to the validation layer." Phase 2 honours that
boundary: it provides `find_duplicates_by_name` (the query) but not the warning
rule, and `update_status` (the write) but not the transition check.

## 2. Phase numbering

The repository contains two phase maps. `docs/PHASE1_IMPLEMENTED_REQUIREMENTS.md`
§9 and DEV-11 use an eight-phase map in which Phase 2 is the DAL;
`docs/REPOSITORY_REVIEW_REPORT.md` §7 uses a five-phase map in which Phase 2 is
a larger "shared operations module". **This phase follows the eight-phase map**,
which is the one Phase 1 was delivered against.

## 3. `DatabaseConnection` (LLD-02 §4)

`connect()` returns a `sqlite3.Connection` configured with:

| Setting | Reason |
|---|---|
| `PRAGMA foreign_keys = ON` | SRS-032 |
| `PRAGMA journal_mode = WAL` | Crash safety (LLD-01 §2.1) |
| `PRAGMA busy_timeout = 5000` | LLD-02 §4.1 |
| `row_factory = sqlite3.Row` | LLD-02 §4.1 |
| `isolation_level = None` | Per DEV-03 — disables the driver's implicit transaction so the explicit `BEGIN IMMEDIATE` below is the only transaction control |

`transaction()` is a context manager that issues `BEGIN IMMEDIATE`, yields the
connection, commits on clean exit, rolls back and re-raises on any exception,
and closes the connection in `finally` (SRS-084). `read_only()` yields a
connection and closes it without opening a transaction.

Each call gets its own connection. No pooling — the prototype is single-writer.

## 4. `DataAccessLayer` (LLD-02 §5)

### 4.1 Column registry derived from the record dataclasses

Column names for each table come from
`dataclasses.fields(TABLE_RECORD_MAP[table])`, not from a separately maintained
list. Phase 1 pins record field order to database column order — stated in the
`models.py` module docstring and enforced by
`test_dataclass_fields_match_table_columns_in_order` — so deriving columns from
the dataclasses means there is no second list that can fall out of sync with
the schema. This is the use DEV-11 created `TABLE_RECORD_MAP` for.

`schema_version` is excluded from the DAL's table set: it is owned by the
initializer (Phase 1) and carries no `unique_key`.

### 4.2 Generic core

Private methods, each taking an open connection as its first argument:

| Method | Behaviour |
|---|---|
| `_insert(conn, table, values)` | Builds a parameterized `INSERT`, returns `lastrowid` |
| `_update(conn, table, record_id, fields)` | Builds a parameterized `UPDATE ... WHERE id = ?`; no-op when `fields` is empty |
| `_get_by_id(conn, table, record_id)` | Single record or `None` |
| `_get_by_unique_key(conn, table, unique_key)` | Single record or `None` |
| `_query(conn, table, filters)` | Records matching equality filters, deterministically ordered |
| `_to_record(table, row)` | Positional expansion of a row into `TABLE_RECORD_MAP[table]` |

**Identifier safety.** SQLite cannot parameterize table or column names, so
every identifier is resolved through the registry and rejected with
`ValueError` if unknown. Values are always bound with `?` placeholders, never
interpolated. This is what keeps a table-driven DAL from opening an injection
path.

**Deterministic ordering (SRS-108).** A table that appears in `CHILD_PARENT_MAP`
and has a `position` field is ordered by `(parent_fk, position)`; every other
table is ordered by `id`. Both are derived from Phase 1 registries rather than
hardcoded.

### 4.3 Public surface

The methods named in LLD-02 §5.1 as thin, fully typed wrappers over the core —
`insert_source_requirement`, `insert_type_definition`,
`insert_simple_type_definition`, `insert_array_type_definition`,
`insert_struct_element`, `insert_enum_value`, `insert_port_interface`,
`insert_interface_data_element`, `insert_client_server_operation`,
`insert_operation_argument`, `insert_port_prototype`,
`insert_port_prototype_function`, `insert_port_connection`,
`insert_port_connection_member`, `insert_review_issue`, the corresponding
`update_*` and `get_*_by_key` / `query_*` methods, plus the cross-cutting five:

- `update_status(conn, table, record_id, new_status, review_note)`
- `get_record_by_unique_key(conn, table, unique_key)`
- `get_children_statuses(conn, child_table, fk_column, parent_id)`
- `find_duplicates_by_name(conn, table, name, kind=None)` — case-insensitive,
  matching the `COLLATE NOCASE` indexes created in V001
- `resolve_unique_key(conn, unique_key)` — searches every DAL table, returns
  `(table_name, record)` or `None`

Explicit signatures keep the call sites Phase 3 writes checkable under
`mypy --strict`; the generic core keeps the SQL in one place.

## 5. Return types

Public read methods return record dataclasses, not `sqlite3.Row`. LLD-02 §5.1
sketches `Optional[Row]` / `list[Row]`; returning records is the direct
consequence of the table-driven design and of DEV-11's stated purpose. Recorded
as a Phase 2 deviation.

## 6. Error handling

`sqlite3.IntegrityError` from a foreign-key, `CHECK`, or `UNIQUE` violation
propagates unchanged. Translating it into `McpError` belongs at the Phase 3
tool boundary, which knows the operation name and the affected key; catching it
here would hide constraint failures behind a layer that cannot describe them.

`ValueError` is raised only for an unknown table or column — a programming
error, never caller-supplied data.

## 7. Testing

Development-level tests only. A separate tester performs thorough verification
after this phase, so Phase 2 tests establish that the layer works rather than
attempting exhaustive coverage:

- `tests/test_r210_mcp/test_connection.py` — pragmas applied, commit persists,
  exception rolls back, connections close.
- `tests/test_r210_mcp/test_dal.py` — round-trip insert → get for every table
  in the registry, the cross-cutting five, deterministic ordering, and
  identifier rejection.

Tests run against a real initialized SQLite database through the existing
`initialized_db` fixture in `tests/conftest.py`.

## 8. Deliverables

1. The three source files above.
2. Development tests.
3. `ruff check`, `mypy --strict`, and `pytest` all clean.
4. `docs/PHASE2_IMPLEMENTED_REQUIREMENTS.md` and a Phase 2 section appended to
   `docs/DEVIATIONS_FROM_REQUIREMENTS.md`.

## Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-12 | Initial Phase 2 design, approved before implementation. |
