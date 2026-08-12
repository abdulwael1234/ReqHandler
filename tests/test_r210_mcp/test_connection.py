"""Development tests for DatabaseConnection (LLD-02 §4).

Scope: enough to establish that the connection layer behaves as the DAL and the
Phase 3 tool handlers assume. Exhaustive verification is a separate activity.
"""

import sqlite3

import pytest

from r210_mcp.db.connection import BUSY_TIMEOUT_MS, DatabaseConnection


class TestPragmas:
    def test_foreign_keys_are_enforced(self, initialized_db: str) -> None:
        """SRS-032 — the schema's FK constraints are inert without this pragma."""
        db = DatabaseConnection(initialized_db)
        with db.read_only() as conn:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_journal_mode_is_wal(self, initialized_db: str) -> None:
        db = DatabaseConnection(initialized_db)
        with db.read_only() as conn:
            assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    def test_busy_timeout_is_configured(self, initialized_db: str) -> None:
        db = DatabaseConnection(initialized_db)
        with db.read_only() as conn:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == BUSY_TIMEOUT_MS

    def test_rows_are_accessible_by_column_name(self, initialized_db: str) -> None:
        db = DatabaseConnection(initialized_db)
        with db.read_only() as conn:
            row = conn.execute("SELECT 1 AS answer").fetchone()
            assert row["answer"] == 1

    def test_foreign_key_violation_is_rejected(self, initialized_db: str) -> None:
        db = DatabaseConnection(initialized_db)
        with pytest.raises(sqlite3.IntegrityError):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO TypeDefinitions (unique_key, name, kind,"
                    " source_requirement_id) VALUES ('k', 'n', 'struct', 9999)"
                )


class TestTransaction:
    def test_commits_on_clean_exit(self, initialized_db: str) -> None:
        db = DatabaseConnection(initialized_db)
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO SourceRequirements (unique_key, source_reference)"
                " VALUES ('kept', 'REQ-1')"
            )

        with db.read_only() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM SourceRequirements WHERE unique_key = 'kept'"
            ).fetchone()[0]
        assert count == 1

    def test_rolls_back_on_exception(self, initialized_db: str) -> None:
        """SRS-084 — a failure part way through must leave no partial write."""
        db = DatabaseConnection(initialized_db)
        with pytest.raises(RuntimeError):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO SourceRequirements (unique_key, source_reference)"
                    " VALUES ('discarded', 'REQ-2')"
                )
                raise RuntimeError("failure after a write")

        with db.read_only() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM SourceRequirements WHERE unique_key = 'discarded'"
            ).fetchone()[0]
        assert count == 0

    def test_connection_is_closed_after_the_block(self, initialized_db: str) -> None:
        db = DatabaseConnection(initialized_db)
        with db.transaction() as conn:
            pass
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_connection_is_closed_after_an_exception(self, initialized_db: str) -> None:
        db = DatabaseConnection(initialized_db)
        leaked: sqlite3.Connection | None = None
        with pytest.raises(RuntimeError):
            with db.transaction() as conn:
                leaked = conn
                raise RuntimeError("boom")
        assert leaked is not None
        with pytest.raises(sqlite3.ProgrammingError):
            leaked.execute("SELECT 1")


class TestReadOnly:
    def test_closes_the_connection(self, initialized_db: str) -> None:
        db = DatabaseConnection(initialized_db)
        with db.read_only() as conn:
            conn.execute("SELECT 1")
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_exposes_the_configured_path(self, initialized_db: str) -> None:
        assert DatabaseConnection(initialized_db).db_path == initialized_db
