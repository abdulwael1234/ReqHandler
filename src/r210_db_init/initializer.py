"""Main initializer orchestration.

Implements DatabaseInitializer class that:
- Creates the database file if it doesn't exist (SRS-095)
- Applies pending migrations in order (SRS-096, SRS-124)
- Tracks schema version (SRS-097)
- Verifies schema integrity (tables, indexes, FK constraints)
- Preserves all existing data (SRS-099)

See: LLD-05 §4 (Initializer Orchestration)
"""

import sqlite3
from dataclasses import dataclass

from .migrations.base import Migration
from .migrations.v001_initial_schema import INDEX_DDL, TABLE_DDL, V001InitialSchema

# The version-tracking table is created by the initializer, not by a migration
# (LLD-05 §4.3), so it is not part of TABLE_DDL.
VERSION_TABLE = "schema_version"


@dataclass(frozen=True)
class InitResult:
    """Outcome of an init_db run (LLD-05 §3, §4.2).

    status is one of:
        "success"    — one or more migrations were applied
        "up_to_date" — schema already current, nothing to apply
        "failed"     — migration or verification failed; see error
    """

    final_version: int
    migrations_applied: int
    status: str
    error: str | None = None


class DatabaseInitializer:
    """Manages database creation, schema migration, and version tracking."""

    # All known migrations in order. Each migration brings the DB from
    # version N-1 to version N.
    MIGRATIONS: list[type[Migration]] = [
        V001InitialSchema,  # version 0 → 1
        # Future migrations added here:
        # V002AddNewColumn,      # version 1 → 2
    ]

    def __init__(self, db_path: str):
        self._db_path = db_path

    def init_db(self) -> InitResult:
        """Initialize or upgrade the database.

        Idempotent — safe to call repeatedly (SRS-098).
        Preserves all existing data (SRS-099).

        Each migration and its version record run in a single transaction;
        on failure the transaction rolls back, leaving the database at the
        last successfully applied version (SRS-124).
        """
        # sqlite3.connect() creates the file when it does not exist (SRS-095).
        # isolation_level=None disables the driver's implicit transaction
        # handling so that BEGIN/COMMIT below are the only transaction control.
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        try:
            conn.execute("PRAGMA foreign_keys = ON")  # SRS-032
            conn.execute("PRAGMA journal_mode = WAL")

            self._ensure_version_table(conn)

            current_version = self._get_current_version(conn)
            target_version = len(self.MIGRATIONS)

            if current_version > target_version:
                return InitResult(
                    final_version=current_version,
                    migrations_applied=0,
                    status="failed",
                    error=(
                        f"Database schema version {current_version} is newer than "
                        f"this application supports ({target_version}). "
                        f"Upgrade the application or use a compatible database."
                    ),
                )

            applied = 0
            for index in range(current_version, target_version):
                migration = self.MIGRATIONS[index]()
                new_version = index + 1
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    migration.up(conn)
                    conn.execute(
                        f"INSERT INTO {VERSION_TABLE} (version, description) VALUES (?, ?)",
                        (new_version, migration.description),
                    )
                    conn.execute("COMMIT")
                    applied += 1
                except Exception as exc:  # noqa: BLE001 — reported, not swallowed
                    conn.execute("ROLLBACK")  # SRS-124
                    return InitResult(
                        final_version=current_version + applied,
                        migrations_applied=applied,
                        status="failed",
                        error=f"Migration v{new_version:03d} failed: {exc}",
                    )

            final_version = max(current_version, target_version)

            # Verification runs even when the version is already current, to
            # catch external corruption or manual schema edits (SRS-098).
            try:
                self._verify_schema(conn, final_version)
            except RuntimeError as exc:
                return InitResult(
                    final_version=final_version,
                    migrations_applied=applied,
                    status="failed",
                    error=str(exc),
                )

            return InitResult(
                final_version=final_version,
                migrations_applied=applied,
                status="success" if applied > 0 else "up_to_date",
            )
        finally:
            conn.close()

    def _ensure_version_table(self, conn: sqlite3.Connection) -> None:
        """Create the schema_version table if it doesn't exist (SRS-097)."""
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (
                version     INTEGER NOT NULL,
                applied_at  TEXT    NOT NULL
                            DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                description TEXT
            )
            """
        )

    def _get_current_version(self, conn: sqlite3.Connection) -> int:
        """Return the highest applied schema version, or 0 for a fresh database."""
        row = conn.execute(f"SELECT MAX(version) FROM {VERSION_TABLE}").fetchone()
        return row[0] if row[0] is not None else 0

    def _verify_schema(self, conn: sqlite3.Connection, expected_version: int) -> None:
        """Verify schema integrity after migrations.

        Checks tables, indexes, and referential integrity.
        Raises RuntimeError if verification fails (LLD-05 §4.3).
        """
        errors: list[str] = []

        expected_tables = {VERSION_TABLE} | set(TABLE_DDL)
        actual_tables = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        missing_tables = expected_tables - actual_tables
        if missing_tables:
            errors.append(f"Missing tables: {sorted(missing_tables)}")

        actual_indexes = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        missing_indexes = set(INDEX_DDL) - actual_indexes
        if missing_indexes:
            errors.append(f"Missing indexes: {sorted(missing_indexes)}")

        fk_violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if fk_violations:
            errors.append(f"Foreign key violations found: {len(fk_violations)} records")

        if errors:
            raise RuntimeError(
                f"Schema verification failed at version {expected_version}: " + "; ".join(errors)
            )
