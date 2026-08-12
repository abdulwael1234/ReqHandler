"""Tests for the development-only destructive reset (LLD-05 §6).

Requirement coverage: SRS-100.
"""

import sqlite3

import pytest

from r210_db_init.dev_reset import development_reset
from tests.conftest import EXPECTED_TABLES


def _tables(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _scalar(db_path: str, sql: str):
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(sql).fetchone()[0]
    finally:
        conn.close()


class TestDevelopmentReset:
    def test_removes_all_rows(self, initialized_db: str) -> None:
        conn = sqlite3.connect(initialized_db)
        try:
            conn.execute(
                "INSERT INTO SourceRequirements (unique_key, source_reference) "
                "VALUES ('s', 'DOC-1')"
            )
            conn.commit()
        finally:
            conn.close()

        development_reset(initialized_db)

        assert _scalar(initialized_db, "SELECT COUNT(*) FROM SourceRequirements") == 0

    def test_recreates_the_full_schema(self, initialized_db: str) -> None:
        development_reset(initialized_db)

        assert EXPECTED_TABLES <= _tables(initialized_db)

    def test_leaves_database_at_current_schema_version(self, initialized_db: str) -> None:
        development_reset(initialized_db)

        assert _scalar(initialized_db, "SELECT MAX(version) FROM schema_version") == 2

    def test_records_one_row_per_applied_migration(self, initialized_db: str) -> None:
        development_reset(initialized_db)

        assert _scalar(initialized_db, "SELECT COUNT(*) FROM schema_version") == 2

    def test_works_on_a_database_that_does_not_exist_yet(self, db_path: str) -> None:
        development_reset(db_path)

        assert EXPECTED_TABLES <= _tables(db_path)

    def test_reports_failure_when_reinitialization_fails(self, initialized_db: str, monkeypatch):
        """A silent failure would leave the developer with an empty, unusable database."""
        from r210_db_init import dev_reset as dev_reset_module
        from r210_db_init.initializer import InitResult

        def _failing_init(self):
            return InitResult(
                final_version=0, migrations_applied=0, status="failed", error="disk on fire"
            )

        monkeypatch.setattr(
            dev_reset_module.DatabaseInitializer, "init_db", _failing_init
        )

        with pytest.raises(RuntimeError, match="disk on fire"):
            development_reset(initialized_db)
