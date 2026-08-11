# Low-Level Design — Database Initializer

## R210 AUTOSAR Requirements Automation Prototype

| Field              | Value                                                    |
|--------------------|----------------------------------------------------------|
| **Document ID**    | R210-LLD-05                                              |
| **Version**        | 1.2                                                      |
| **Date**           | 2026-08-11                                               |
| **Component**      | Database Initializer                                     |
| **Source Documents**| R210-SRS-001 v5.2, R210-HLD-001 v3.1, R210-LLD-01 v1.0 |
| **Status**         | Draft                                                    |

---

## 1. Purpose

This document specifies the internal design of the Database Initializer — the component responsible for creating and upgrading the SQLite database schema safely without deleting existing content. It defines the migration framework, version tracking, and the initial migration that creates all tables defined in LLD-01.

---

## 2. Module Structure

```
r210_db_init/
├── __init__.py
├── cli.py                     # CLI entry point for init_db command
├── initializer.py             # Main initializer orchestration
├── migrations/
│   ├── __init__.py
│   ├── base.py                # Base migration class
│   └── v001_initial_schema.py # Migration: create all tables (LLD-01 §3)
└── dev_reset.py               # Development-only destructive reset (SRS-100)
```

---

## 3. CLI Entry Point (`cli.py`)

```python
"""
CLI entry point for database initialization.

Usage:
    python -m r210_db_init init <db_path>
    python -m r210_db_init reset <db_path>  # Development only — destructive

The init command is idempotent and safe to run repeatedly (SRS-098).
The reset command is a development-only destructive operation (SRS-100).
"""

import argparse
import sys
from .initializer import DatabaseInitializer
from .dev_reset import development_reset

def main():
    parser = argparse.ArgumentParser(description="R210 Database Management")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize or upgrade database")
    init_parser.add_argument("db_path", help="Path to SQLite database file")

    reset_parser = subparsers.add_parser("reset", help="DESTRUCTIVE: Reset database (dev only)")
    reset_parser.add_argument("db_path", help="Path to SQLite database file")
    reset_parser.add_argument("--confirm", action="store_true",
                               help="Required to proceed with destructive reset")

    args = parser.parse_args()

    if args.command == "init":
        initializer = DatabaseInitializer(args.db_path)
        result = initializer.init_db()
        print(f"Database at version {result.final_version}")
        print(f"Migrations applied: {result.migrations_applied}")
        print(f"Status: {result.status}")
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(0 if result.status in ("success", "up_to_date") else 1)

    elif args.command == "reset":
        if not args.confirm:
            print("ERROR: Reset is destructive. Pass --confirm to proceed.")
            sys.exit(1)
        development_reset(args.db_path)
        print("Database reset complete (development only).")
        sys.exit(0)
```

**Design notes:**
- `init` is the safe, idempotent operation (SRS-094, SRS-098).
- `reset` requires `--confirm` flag and is for development use only (SRS-100).
- Neither command is exposed through MCP or the Gemini workflow (SRS-093, SRS-100).

---

## 4. Initializer Orchestration (`initializer.py`)

### 4.1 Class Design

```python
class DatabaseInitializer:
    """Manages database creation, schema migration, and version tracking."""

    # All known migrations in order. Each migration brings the DB from
    # version N-1 to version N.
    MIGRATIONS: list[type[Migration]] = [
        V001InitialSchema,       # version 0 → 1
        # Future migrations added here:
        # V002AddNewColumn,      # version 1 → 2
    ]

    def __init__(self, db_path: str):
        self._db_path = db_path

    def init_db(self) -> InitResult:
        """
        Initialize or upgrade the database.
        Idempotent — safe to call repeatedly (SRS-098).
        Preserves all existing data (SRS-099).

        Algorithm:
        1. Create database file if it does not exist (SRS-095)
        2. Connect and enable FK enforcement
        3. Ensure schema_version table exists
        4. Read current version (0 if fresh database)
        5. Reject if current_version > target_version (newer schema)
        6. Apply pending migrations in order (SRS-096, SRS-124)
        7. Verify final schema state
        8. Return result

        Each migration runs within a single transaction (SRS-124).
        On failure, the transaction rolls back, leaving the database
        at the last successfully applied version.
        """
```

### 4.2 Initialization Algorithm

```python
def init_db(self) -> InitResult:
    # Step 1: Create file if needed (SRS-095)
    # sqlite3.connect() creates the file automatically

    conn = sqlite3.connect(self._db_path)
    conn.execute("PRAGMA foreign_keys = ON")    # SRS-032
    conn.execute("PRAGMA journal_mode = WAL")

    try:
        # Step 2: Ensure schema_version table exists
        self._ensure_version_table(conn)

        # Step 3: Read current version
        current_version = self._get_current_version(conn)
        target_version = len(self.MIGRATIONS)

        # Step 4: Reject newer schema versions
        if current_version > target_version:
            return InitResult(
                final_version=current_version,
                migrations_applied=0,
                status="failed",
                error=f"Database schema version {current_version} is newer than "
                      f"this application supports ({target_version}). "
                      f"Upgrade the application or use a compatible database.",
            )

        # Step 5: Apply pending migrations (SRS-096, SRS-124)
        applied = 0
        if current_version < target_version:
            for i in range(current_version, target_version):
                migration = self.MIGRATIONS[i]()
                new_version = i + 1

                try:
                    conn.execute("BEGIN IMMEDIATE")

                    # Apply the migration
                    migration.up(conn)

                    # Record the version (SRS-097)
                    conn.execute(
                        "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                        (new_version, migration.description),
                    )

                    conn.commit()
                    applied += 1

                except Exception as e:
                    conn.rollback()  # SRS-124: rollback on failure
                    return InitResult(
                        final_version=current_version + applied,
                        migrations_applied=applied,
                        status="failed",
                        error=f"Migration v{new_version:03d} failed: {e}",
                    )

        # Step 6: Verify final schema state — runs even when version
        # is already current, to catch external corruption or manual
        # schema edits (SRS-098 idempotency guarantee).
        self._verify_schema(conn, max(current_version, target_version))

        final_version = max(current_version, target_version)
        return InitResult(
            final_version=final_version,
            migrations_applied=applied,
            status="success" if applied > 0 else "up_to_date",
        )

    finally:
        conn.close()
```

### 4.3 Helper Methods

```python
def _ensure_version_table(self, conn: sqlite3.Connection) -> None:
    """Create schema_version table if it doesn't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER NOT NULL,
            applied_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            description TEXT
        )
    """)
    conn.commit()

def _get_current_version(self, conn: sqlite3.Connection) -> int:
    """Return the highest applied schema version, or 0 for a fresh database."""
    cursor = conn.execute("SELECT MAX(version) FROM schema_version")
    row = cursor.fetchone()
    return row[0] if row[0] is not None else 0

def _verify_schema(self, conn: sqlite3.Connection, expected_version: int) -> None:
    """Verify schema integrity after migrations.
    Checks tables, indexes, and FK enforcement.
    Raises RuntimeError if verification fails."""

    errors = []

    # --- 1. Table presence ---
    expected_tables = {
        "schema_version",
        "SourceRequirements",
        "TypeDefinitions",
        "SimpleTypeDefinitions",
        "ArrayTypeDefinitions",
        "StructElements",
        "EnumValues",
        "PortInterfaces",
        "InterfaceDataElements",
        "ClientServerOperations",
        "OperationArguments",
        "PortPrototypes",
        "PortPrototypeFunctions",
        "PortConnections",
        "PortConnectionMembers",
        "ReviewIssues",
    }
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )
    actual_tables = {row[0] for row in cursor.fetchall()}
    missing_tables = expected_tables - actual_tables
    if missing_tables:
        errors.append(f"Missing tables: {missing_tables}")

    # --- 2. Index presence ---
    expected_indexes = {
        # Key indexes — names must match DDL in V001InitialSchema._create_indexes()
        "idx_source_requirements_status",
        "idx_type_definitions_kind",
        "idx_type_definitions_status",
        "idx_port_interfaces_type",
        "idx_port_interfaces_status",
        "idx_port_prototypes_interface",
        "idx_port_prototypes_direction",
        "idx_port_prototypes_status",
        "idx_port_connections_status",
        "idx_review_issues_status",
    }
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    )
    actual_indexes = {row[0] for row in cursor.fetchall()}
    missing_indexes = expected_indexes - actual_indexes
    if missing_indexes:
        errors.append(f"Missing indexes: {missing_indexes}")

    # --- 3. FK enforcement ---
    cursor = conn.execute("PRAGMA foreign_key_check")
    fk_violations = cursor.fetchall()
    if fk_violations:
        errors.append(
            f"Foreign key violations found: {len(fk_violations)} records"
        )

    if errors:
        raise RuntimeError(
            f"Schema verification failed at version {expected_version}: "
            + "; ".join(errors)
        )
```

---

## 5. Migration Framework

### 5.1 Base Migration Class (`migrations/base.py`)

```python
from abc import ABC, abstractmethod
import sqlite3

class Migration(ABC):
    """Base class for database migrations.

    Each migration:
    - Has a description for the schema_version record
    - Implements up() to apply schema changes
    - Uses CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS
      to be safe for re-runs (SRS-098)
    - Never drops or truncates existing tables (SRS-099)
    """

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of this migration."""

    @abstractmethod
    def up(self, conn: sqlite3.Connection) -> None:
        """Apply this migration's schema changes.

        This method runs inside a transaction managed by the initializer.
        Do NOT call conn.commit() or conn.rollback() — the caller handles this.

        Use:
        - CREATE TABLE IF NOT EXISTS (idempotent)
        - CREATE INDEX IF NOT EXISTS (idempotent)
        - ALTER TABLE ... ADD COLUMN (check column existence first)
        """
```

### 5.2 Initial Schema Migration (`migrations/v001_initial_schema.py`)

This migration creates all tables defined in LLD-01 §3.

```python
class V001InitialSchema(Migration):
    """Create all initial tables, constraints, and indexes."""

    @property
    def description(self) -> str:
        return "Initial schema — all tables per LLD-01 v1.0"

    def up(self, conn: sqlite3.Connection) -> None:
        # ── SourceRequirements ──────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS SourceRequirements (
                id               INTEGER PRIMARY KEY,
                unique_key       TEXT    NOT NULL UNIQUE,
                source_reference TEXT    NOT NULL,
                source_text      TEXT,
                status           TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                review_note      TEXT
            )
        """)

        # ── TypeDefinitions ─────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS TypeDefinitions (
                id                      INTEGER PRIMARY KEY,
                unique_key              TEXT    NOT NULL UNIQUE,
                name                    TEXT    NOT NULL,
                kind                    TEXT    NOT NULL
                    CHECK (kind IN ('simple_typedef','array','struct','enum')),
                description             TEXT,
                source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
                status                  TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                review_note             TEXT
            )
        """)

        # ── SimpleTypeDefinitions ───────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS SimpleTypeDefinitions (
                id                  INTEGER PRIMARY KEY,
                unique_key          TEXT    NOT NULL UNIQUE,
                type_definition_id  INTEGER NOT NULL UNIQUE REFERENCES TypeDefinitions(id),
                base_type           TEXT    NOT NULL,
                size                TEXT
            )
        """)

        # ── ArrayTypeDefinitions ────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ArrayTypeDefinitions (
                id                  INTEGER PRIMARY KEY,
                unique_key          TEXT    NOT NULL UNIQUE,
                type_definition_id  INTEGER NOT NULL UNIQUE REFERENCES TypeDefinitions(id),
                element_type_id     INTEGER NOT NULL REFERENCES TypeDefinitions(id),
                array_size          INTEGER NOT NULL CHECK (array_size >= 1)
            )
        """)

        # ── StructElements ──────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS StructElements (
                id                  INTEGER PRIMARY KEY,
                unique_key          TEXT    NOT NULL UNIQUE,
                struct_type_id      INTEGER NOT NULL REFERENCES TypeDefinitions(id),
                name                TEXT    NOT NULL,
                element_type_id     INTEGER NOT NULL REFERENCES TypeDefinitions(id),
                position            INTEGER NOT NULL CHECK (position >= 1),
                description         TEXT,
                status              TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                UNIQUE (struct_type_id, position),
                UNIQUE (struct_type_id, name)
            )
        """)

        # ── EnumValues ──────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS EnumValues (
                id                  INTEGER PRIMARY KEY,
                unique_key          TEXT    NOT NULL UNIQUE,
                enum_type_id        INTEGER NOT NULL REFERENCES TypeDefinitions(id),
                name                TEXT    NOT NULL,
                value               TEXT,
                position            INTEGER NOT NULL CHECK (position >= 1),
                description         TEXT,
                status              TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                UNIQUE (enum_type_id, position),
                UNIQUE (enum_type_id, name)
            )
        """)

        # ── PortInterfaces ──────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS PortInterfaces (
                id                      INTEGER PRIMARY KEY,
                unique_key              TEXT    NOT NULL UNIQUE,
                name                    TEXT    NOT NULL,
                description             TEXT,
                source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
                interface_type          TEXT    NOT NULL
                    CHECK (interface_type IN ('sender_receiver','client_server')),
                status                  TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                review_note             TEXT
            )
        """)

        # ── InterfaceDataElements ───────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS InterfaceDataElements (
                id                  INTEGER PRIMARY KEY,
                unique_key          TEXT    NOT NULL UNIQUE,
                port_interface_id   INTEGER NOT NULL REFERENCES PortInterfaces(id),
                name                TEXT    NOT NULL,
                type_definition_id  INTEGER NOT NULL REFERENCES TypeDefinitions(id),
                position            INTEGER NOT NULL CHECK (position >= 1),
                description         TEXT,
                status              TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                UNIQUE (port_interface_id, position)
            )
        """)

        # ── ClientServerOperations ──────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ClientServerOperations (
                id                  INTEGER PRIMARY KEY,
                unique_key          TEXT    NOT NULL UNIQUE,
                port_interface_id   INTEGER NOT NULL REFERENCES PortInterfaces(id),
                name                TEXT    NOT NULL,
                position            INTEGER NOT NULL CHECK (position >= 1),
                description         TEXT,
                status              TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                UNIQUE (port_interface_id, position)
            )
        """)

        # ── OperationArguments ──────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS OperationArguments (
                id                  INTEGER PRIMARY KEY,
                unique_key          TEXT    NOT NULL UNIQUE,
                operation_id        INTEGER NOT NULL REFERENCES ClientServerOperations(id),
                name                TEXT    NOT NULL,
                type_definition_id  INTEGER NOT NULL REFERENCES TypeDefinitions(id),
                direction           TEXT    NOT NULL
                    CHECK (direction IN ('input','output','input_output')),
                position            INTEGER NOT NULL CHECK (position >= 1),
                status              TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                UNIQUE (operation_id, position)
            )
        """)

        # ── PortPrototypes ──────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS PortPrototypes (
                id                      INTEGER PRIMARY KEY,
                unique_key              TEXT    NOT NULL UNIQUE,
                name                    TEXT    NOT NULL,
                description             TEXT,
                source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
                port_interface_id       INTEGER REFERENCES PortInterfaces(id),
                direction               TEXT    NOT NULL
                    CHECK (direction IN ('provider','requester')),
                component_reference     TEXT    NOT NULL,
                status                  TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                review_note             TEXT
            )
        """)

        # ── PortPrototypeFunctions ──────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS PortPrototypeFunctions (
                id                  INTEGER PRIMARY KEY,
                unique_key          TEXT    NOT NULL UNIQUE,
                port_prototype_id   INTEGER NOT NULL REFERENCES PortPrototypes(id),
                function_name       TEXT    NOT NULL,
                relationship_type   TEXT    NOT NULL
                    CHECK (relationship_type IN ('access_point','trigger')),
                status              TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope'))
            )
        """)

        # ── PortConnections ─────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS PortConnections (
                id                      INTEGER PRIMARY KEY,
                unique_key              TEXT    NOT NULL UNIQUE,
                description             TEXT,
                source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
                status                  TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                review_note             TEXT
            )
        """)

        # ── PortConnectionMembers ───────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS PortConnectionMembers (
                id                  INTEGER PRIMARY KEY,
                unique_key          TEXT    NOT NULL UNIQUE,
                port_connection_id  INTEGER NOT NULL REFERENCES PortConnections(id),
                port_prototype_id   INTEGER NOT NULL REFERENCES PortPrototypes(id),
                position            INTEGER NOT NULL CHECK (position >= 1),
                status              TEXT    NOT NULL DEFAULT 'pending_review'
                    CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
                UNIQUE (port_connection_id, position),
                UNIQUE (port_connection_id, port_prototype_id)
            )
        """)

        # ── ReviewIssues ────────────────────────────────────────
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ReviewIssues (
                id                      INTEGER PRIMARY KEY,
                unique_key              TEXT    NOT NULL UNIQUE,
                source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
                artifact_type           TEXT
                    CHECK (artifact_type IN (
                        'type_definition','struct_element','enum_value',
                        'port_interface','interface_data_element',
                        'client_server_operation','operation_argument',
                        'port_prototype','port_prototype_function',
                        'port_connection','port_connection_member'
                    ) OR artifact_type IS NULL),
                artifact_unique_key     TEXT,
                issue_type              TEXT    NOT NULL
                    CHECK (issue_type IN ('ambiguous','incomplete','unresolved_reference','unsupported','out_of_scope')),
                message                 TEXT    NOT NULL,
                status                  TEXT    NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','resolved','rejected')),
                resolution              TEXT,
                CHECK (artifact_unique_key IS NULL OR artifact_type IS NOT NULL)
            )
        """)

        # ── Indexes ─────────────────────────────────────────────
        self._create_indexes(conn)

    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """Create all indexes using IF NOT EXISTS for idempotency."""
        indexes = [
            # SourceRequirements
            ("idx_source_requirements_status", "SourceRequirements", "status"),
            ("idx_source_requirements_source_reference", "SourceRequirements", "source_reference"),
            # TypeDefinitions
            ("idx_type_definitions_kind", "TypeDefinitions", "kind"),
            ("idx_type_definitions_status", "TypeDefinitions", "status"),
            ("idx_type_definitions_source_req", "TypeDefinitions", "source_requirement_id"),
            ("idx_type_definitions_name_kind", "TypeDefinitions", "name COLLATE NOCASE, kind"),
            # StructElements
            ("idx_struct_elements_parent", "StructElements", "struct_type_id"),
            # EnumValues
            ("idx_enum_values_parent", "EnumValues", "enum_type_id"),
            # PortInterfaces
            ("idx_port_interfaces_type", "PortInterfaces", "interface_type"),
            ("idx_port_interfaces_status", "PortInterfaces", "status"),
            ("idx_port_interfaces_source_req", "PortInterfaces", "source_requirement_id"),
            ("idx_port_interfaces_name_type", "PortInterfaces", "name COLLATE NOCASE, interface_type"),
            # InterfaceDataElements
            ("idx_interface_data_elements_parent", "InterfaceDataElements", "port_interface_id"),
            # ClientServerOperations
            ("idx_client_server_operations_parent", "ClientServerOperations", "port_interface_id"),
            # OperationArguments
            ("idx_operation_arguments_parent", "OperationArguments", "operation_id"),
            # PortPrototypes
            ("idx_port_prototypes_interface", "PortPrototypes", "port_interface_id"),
            ("idx_port_prototypes_direction", "PortPrototypes", "direction"),
            ("idx_port_prototypes_status", "PortPrototypes", "status"),
            ("idx_port_prototypes_source_req", "PortPrototypes", "source_requirement_id"),
            ("idx_port_prototypes_name", "PortPrototypes", "name COLLATE NOCASE"),
            # PortPrototypeFunctions
            ("idx_port_prototype_functions_parent", "PortPrototypeFunctions", "port_prototype_id"),
            # PortConnections
            ("idx_port_connections_status", "PortConnections", "status"),
            ("idx_port_connections_source_req", "PortConnections", "source_requirement_id"),
            # PortConnectionMembers
            ("idx_port_connection_members_parent", "PortConnectionMembers", "port_connection_id"),
            ("idx_port_connection_members_prototype", "PortConnectionMembers", "port_prototype_id"),
            # ReviewIssues
            ("idx_review_issues_status", "ReviewIssues", "status"),
            ("idx_review_issues_issue_type", "ReviewIssues", "issue_type"),
            ("idx_review_issues_source_req", "ReviewIssues", "source_requirement_id"),
            ("idx_review_issues_artifact", "ReviewIssues", "artifact_type, artifact_unique_key"),
        ]
        for name, table, columns in indexes:
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS {name} ON {table}({columns})"
            )
```

---

## 6. Development Reset (`dev_reset.py`)

**SRS trace:** SRS-100 — development-only, outside Gemini workflow.

```python
def development_reset(db_path: str) -> None:
    """DESTRUCTIVE: Drop all tables and recreate from scratch.

    This function is for DEVELOPMENT USE ONLY.
    It is NOT exposed through MCP (SRS-093).
    It is NOT part of the Gemini workflow (SRS-100).

    It drops all application tables and re-runs init_db.
    """
    conn = sqlite3.connect(db_path)
    try:
        # Get all table names
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name != 'sqlite_sequence'"
        )
        tables = [row[0] for row in cursor.fetchall()]

        # Disable FK enforcement for drop operations
        conn.execute("PRAGMA foreign_keys = OFF")

        # Drop all tables
        for table in tables:
            conn.execute(f"DROP TABLE IF EXISTS {table}")

        conn.commit()
    finally:
        conn.close()

    # Re-initialize
    from .initializer import DatabaseInitializer
    initializer = DatabaseInitializer(db_path)
    initializer.init_db()
```

---

## 7. Future Migration Pattern

When schema changes are needed after the initial release:

```python
# migrations/v002_add_new_column.py
class V002AddNewColumn(Migration):
    """Add a new column to TypeDefinitions."""

    @property
    def description(self) -> str:
        return "Add category column to TypeDefinitions"

    def up(self, conn: sqlite3.Connection) -> None:
        # Check if column already exists (for idempotency)
        cursor = conn.execute("PRAGMA table_info(TypeDefinitions)")
        columns = {row[1] for row in cursor.fetchall()}

        if "category" not in columns:
            conn.execute(
                "ALTER TABLE TypeDefinitions ADD COLUMN category TEXT"
            )
```

Then add to the initializer's migration list:

```python
MIGRATIONS = [
    V001InitialSchema,
    V002AddNewColumn,     # version 1 → 2
]
```

---

## 8. Idempotency Guarantees (SRS-098)

| Operation | Idempotency Mechanism |
|-----------|----------------------|
| Create database file | `sqlite3.connect()` creates if absent, opens if present |
| Create schema_version table | `CREATE TABLE IF NOT EXISTS` |
| Create application tables | `CREATE TABLE IF NOT EXISTS` in each migration |
| Create indexes | `CREATE INDEX IF NOT EXISTS` |
| Add columns | Check `PRAGMA table_info()` before `ALTER TABLE` |
| Record version | Checked by `_get_current_version()` — migration skipped if already applied |

---

## 9. Error Scenarios

| Scenario | Behavior | SRS Reference |
|----------|----------|---------------|
| Database file does not exist | Created automatically | SRS-095 |
| Schema is already up to date | Returns success with 0 migrations applied | SRS-098 |
| Migration SQL fails | Transaction rolls back; database stays at last good version | SRS-124 |
| Schema verification fails | Raises RuntimeError with missing table list | SRS-096 |
| Permission error on file | Raises OS error with file path | — |
| Corrupt database file | SQLite raises error; not handled by initializer | — |

---

## 10. Traceability Matrix (LLD-05 → SRS)

| LLD Section | SRS Requirements |
|-------------|-----------------|
| §3 CLI Entry Point | SRS-094, SRS-100 |
| §4 Initializer | SRS-094, SRS-095, SRS-096, SRS-097, SRS-098, SRS-099, SRS-124 |
| §5.1 Base Migration | SRS-098, SRS-099 |
| §5.2 Initial Migration | SRS-096 (creates all tables from LLD-01) |
| §6 Development Reset | SRS-100, SRS-093 |
| §8 Idempotency | SRS-098 |
| §9 Error Scenarios | SRS-095, SRS-096, SRS-098, SRS-124 |

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-10 | Initial LLD derived from SRS v5.0, HLD v3.0, and LLD-01 v1.0. |
| 1.1     | 2026-08-10 | Post-review amendments: Fixed CLI exit code to check `result.status` instead of always exiting 0. Removed early return that skipped `_verify_schema` when version is current. Enhanced `_verify_schema` to check indexes and FK integrity, not just table names. |
| 1.2     | 2026-08-11 | Review-driven fixes: Fixed verification index names to match DDL — `idx_source_requirements_status`, `idx_type_definitions_kind`, `idx_type_definitions_status` (H-01). Added newer-schema-version rejection (M-04). Updated source references to SRS v5.2, HLD v3.1. |
