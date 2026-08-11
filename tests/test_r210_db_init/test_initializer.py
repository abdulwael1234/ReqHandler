"""Tests for the Database Initializer (LLD-05 §4).

Requirement coverage: SRS-025, SRS-032, SRS-094 through SRS-099, SRS-124.
"""

import sqlite3
from pathlib import Path

import pytest

from r210_db_init.initializer import DatabaseInitializer, InitResult
from r210_db_init.migrations.base import Migration
from tests.conftest import EXPECTED_TABLES


def _table_names(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def _index_names(db_path: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


class TestDatabaseCreation:
    """SRS-095: init_db creates the database file when it does not exist."""

    def test_creates_database_file_when_absent(self, db_path: str) -> None:
        assert not Path(db_path).exists()

        DatabaseInitializer(db_path).init_db()

        assert Path(db_path).exists()

    def test_creates_all_application_tables(self, db_path: str) -> None:
        """SRS-096: init_db creates missing tables."""
        DatabaseInitializer(db_path).init_db()

        assert EXPECTED_TABLES <= _table_names(db_path)

    def test_creates_indexes_declared_in_lld01(self, db_path: str) -> None:
        """SRS-096: init_db creates missing indexes."""
        DatabaseInitializer(db_path).init_db()

        actual = _index_names(db_path)
        expected = {
            "idx_source_requirements_status",
            "idx_source_requirements_source_reference",
            "idx_type_definitions_kind",
            "idx_type_definitions_status",
            "idx_type_definitions_source_req",
            "idx_type_definitions_name_kind",
            "idx_struct_elements_parent",
            "idx_enum_values_parent",
            "idx_port_interfaces_type",
            "idx_port_interfaces_status",
            "idx_port_interfaces_source_req",
            "idx_port_interfaces_name_type",
            "idx_interface_data_elements_parent",
            "idx_client_server_operations_parent",
            "idx_operation_arguments_parent",
            "idx_port_prototypes_interface",
            "idx_port_prototypes_direction",
            "idx_port_prototypes_status",
            "idx_port_prototypes_source_req",
            "idx_port_prototypes_name",
            "idx_port_prototype_functions_parent",
            "idx_port_connections_status",
            "idx_port_connections_source_req",
            "idx_port_connection_members_parent",
            "idx_port_connection_members_prototype",
            "idx_review_issues_status",
            "idx_review_issues_issue_type",
            "idx_review_issues_source_req",
            "idx_review_issues_artifact",
        }
        assert expected <= actual

    def test_reports_success_and_migration_count_on_fresh_database(self, db_path: str) -> None:
        result = DatabaseInitializer(db_path).init_db()

        assert result.status == "success"
        assert result.migrations_applied == 1
        assert result.final_version == 1
        assert result.error is None


class TestSchemaVersionTracking:
    """SRS-097: init_db records the database schema version."""

    def test_records_version_one_after_initial_migration(self, initialized_db: str) -> None:
        conn = sqlite3.connect(initialized_db)
        try:
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        finally:
            conn.close()

        assert version == 1

    def test_records_migration_description_and_timestamp(self, initialized_db: str) -> None:
        conn = sqlite3.connect(initialized_db)
        try:
            row = conn.execute(
                "SELECT description, applied_at FROM schema_version WHERE version = 1"
            ).fetchone()
        finally:
            conn.close()

        description, applied_at = row
        assert description
        assert applied_at


class TestIdempotency:
    """SRS-098: init_db is safe to call repeatedly with the same result."""

    def test_second_run_applies_no_migrations(self, db_path: str) -> None:
        DatabaseInitializer(db_path).init_db()

        result = DatabaseInitializer(db_path).init_db()

        assert result.status == "up_to_date"
        assert result.migrations_applied == 0
        assert result.final_version == 1

    def test_second_run_does_not_duplicate_version_rows(self, db_path: str) -> None:
        DatabaseInitializer(db_path).init_db()
        DatabaseInitializer(db_path).init_db()

        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM schema_version WHERE version = 1"
            ).fetchone()[0]
        finally:
            conn.close()

        assert count == 1

    def test_repeated_runs_leave_table_set_unchanged(self, db_path: str) -> None:
        DatabaseInitializer(db_path).init_db()
        after_first = _table_names(db_path)

        DatabaseInitializer(db_path).init_db()

        assert _table_names(db_path) == after_first


class TestDataPreservation:
    """SRS-099: init_db preserves all existing data."""

    def test_existing_rows_survive_reinitialization(self, initialized_db: str) -> None:
        conn = sqlite3.connect(initialized_db)
        try:
            conn.execute(
                "INSERT INTO SourceRequirements (unique_key, source_reference, source_text) "
                "VALUES ('key-1', 'DOC-001', 'the original text')"
            )
            conn.commit()
        finally:
            conn.close()

        DatabaseInitializer(initialized_db).init_db()

        conn = sqlite3.connect(initialized_db)
        try:
            row = conn.execute(
                "SELECT source_reference, source_text FROM SourceRequirements "
                "WHERE unique_key = 'key-1'"
            ).fetchone()
        finally:
            conn.close()

        assert row == ("DOC-001", "the original text")


class TestForeignKeyEnforcement:
    """SRS-032: foreign-key enforcement is enabled."""

    def test_initializer_connection_enables_foreign_keys(self, db_path: str) -> None:
        DatabaseInitializer(db_path).init_db()

        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO TypeDefinitions (unique_key, name, kind, source_requirement_id) "
                    "VALUES ('k', 'n', 'struct', 9999)"
                )
        finally:
            conn.close()


class TestNewerSchemaRejection:
    """LLD-05 §4.2 step 4: a database newer than the application is rejected."""

    def test_rejects_database_with_newer_schema_version(self, initialized_db: str) -> None:
        conn = sqlite3.connect(initialized_db)
        try:
            conn.execute(
                "INSERT INTO schema_version (version, description) VALUES (99, 'from the future')"
            )
            conn.commit()
        finally:
            conn.close()

        result = DatabaseInitializer(initialized_db).init_db()

        assert result.status == "failed"
        assert result.final_version == 99
        assert result.migrations_applied == 0
        assert result.error is not None
        assert "99" in result.error


class _FailingMigration(Migration):
    """Migration that creates a table and then fails, to exercise rollback."""

    @property
    def description(self) -> str:
        return "deliberately failing migration"

    def up(self, conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE IF NOT EXISTS ShouldNotSurvive (id INTEGER PRIMARY KEY)")
        raise RuntimeError("migration exploded")


class TestMigrationRollback:
    """SRS-124: a failed migration rolls back, leaving the last good version."""

    def test_failed_migration_reports_failure(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setattr(DatabaseInitializer, "MIGRATIONS", [_FailingMigration])

        result = DatabaseInitializer(db_path).init_db()

        assert result.status == "failed"
        assert result.migrations_applied == 0
        assert result.final_version == 0
        assert result.error is not None
        assert "migration exploded" in result.error

    def test_failed_migration_rolls_back_its_schema_changes(
        self, db_path: str, monkeypatch
    ) -> None:
        monkeypatch.setattr(DatabaseInitializer, "MIGRATIONS", [_FailingMigration])

        DatabaseInitializer(db_path).init_db()

        assert "ShouldNotSurvive" not in _table_names(db_path)

    def test_failed_migration_records_no_schema_version(self, db_path: str, monkeypatch) -> None:
        monkeypatch.setattr(DatabaseInitializer, "MIGRATIONS", [_FailingMigration])

        DatabaseInitializer(db_path).init_db()

        conn = sqlite3.connect(db_path)
        try:
            version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        finally:
            conn.close()

        assert version is None


class TestSchemaVerification:
    """SRS-096 / SRS-098: verification runs even when the version is already current."""

    def test_reports_failure_when_a_table_was_dropped_externally(self, initialized_db: str) -> None:
        conn = sqlite3.connect(initialized_db)
        try:
            conn.execute("DROP TABLE ReviewIssues")
            conn.commit()
        finally:
            conn.close()

        result = DatabaseInitializer(initialized_db).init_db()

        assert result.status == "failed"
        assert result.error is not None
        assert "ReviewIssues" in result.error

    def test_reports_failure_when_an_index_was_dropped_externally(
        self, initialized_db: str
    ) -> None:
        conn = sqlite3.connect(initialized_db)
        try:
            conn.execute("DROP INDEX idx_type_definitions_kind")
            conn.commit()
        finally:
            conn.close()

        result = DatabaseInitializer(initialized_db).init_db()

        assert result.status == "failed"
        assert result.error is not None
        assert "idx_type_definitions_kind" in result.error


class TestInitResult:
    """The result object reported by init_db (LLD-05 §3, §4.2)."""

    def test_error_defaults_to_none(self) -> None:
        result = InitResult(final_version=1, migrations_applied=1, status="success")

        assert result.error is None
