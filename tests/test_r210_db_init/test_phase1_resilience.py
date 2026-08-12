"""Phase 1 lifecycle, corruption-detection, and destructive-reset tests."""

import sqlite3

from r210_db_init.dev_reset import development_reset
from r210_db_init.initializer import DatabaseInitializer
from r210_mcp.db.models import TABLE_RECORD_MAP


class TestMigrationHistoryContract:
    def test_history_is_consecutive_and_descriptions_are_nonempty(
        self, initialized_db: str
    ) -> None:
        connection = sqlite3.connect(initialized_db)
        try:
            rows = connection.execute(
                "SELECT version, description FROM schema_version ORDER BY version"
            ).fetchall()
        finally:
            connection.close()

        assert [row[0] for row in rows] == list(range(1, len(DatabaseInitializer.MIGRATIONS) + 1))
        assert all(description and description.strip() for _, description in rows)

    def test_history_timestamps_use_sortable_utc_format(self, initialized_db: str) -> None:
        connection = sqlite3.connect(initialized_db)
        try:
            timestamps = [
                row[0]
                for row in connection.execute(
                    "SELECT applied_at FROM schema_version ORDER BY version"
                )
            ]
        finally:
            connection.close()

        assert timestamps == sorted(timestamps)
        assert all(timestamp.endswith("Z") and "T" in timestamp for timestamp in timestamps)

    def test_completed_migration_leaves_no_temporary_rebuild_tables(
        self, initialized_db: str
    ) -> None:
        connection = sqlite3.connect(initialized_db)
        try:
            temporary = connection.execute(
                "SELECT name FROM sqlite_master WHERE name LIKE '_v002_%'"
            ).fetchall()
        finally:
            connection.close()

        assert temporary == []


class TestCorruptionDetection:
    def test_initializer_reports_all_missing_object_categories_together(
        self, initialized_db: str
    ) -> None:
        connection = sqlite3.connect(initialized_db)
        try:
            connection.execute("DROP TABLE ReviewIssues")
            connection.execute("DROP INDEX idx_port_prototypes_name")
            connection.commit()
        finally:
            connection.close()

        result = DatabaseInitializer(initialized_db).init_db()

        assert result.status == "failed"
        assert result.error is not None
        assert "Missing tables" in result.error
        assert "ReviewIssues" in result.error
        assert "Missing indexes" in result.error
        assert "idx_port_prototypes_name" in result.error

    def test_initializer_detects_foreign_key_corruption_created_externally(
        self, initialized_db: str
    ) -> None:
        connection = sqlite3.connect(initialized_db)
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "INSERT INTO TypeDefinitions "
                "(unique_key, name, kind, source_requirement_id) "
                "VALUES ('orphan', 'Orphan', 'struct', 999999)"
            )
            connection.commit()
        finally:
            connection.close()

        result = DatabaseInitializer(initialized_db).init_db()

        assert result.status == "failed"
        assert result.error is not None
        assert "Foreign key violations found: 1 records" in result.error

    def test_failed_verification_does_not_add_history_rows(self, initialized_db: str) -> None:
        connection = sqlite3.connect(initialized_db)
        try:
            before = connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
            connection.execute("DROP INDEX idx_review_issues_status")
            connection.commit()
        finally:
            connection.close()

        DatabaseInitializer(initialized_db).init_db()

        connection = sqlite3.connect(initialized_db)
        try:
            after = connection.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
        finally:
            connection.close()
        assert after == before


class TestResetAcrossDependencies:
    def test_reset_removes_rows_from_every_table_and_rebuilds_constraints(
        self, initialized_db: str
    ) -> None:
        connection = sqlite3.connect(initialized_db)
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            source_id = connection.execute(
                "INSERT INTO SourceRequirements (unique_key, source_reference) "
                "VALUES ('source', 'SRS-1')"
            ).lastrowid
            type_id = connection.execute(
                "INSERT INTO TypeDefinitions (unique_key, name, kind, source_requirement_id) "
                "VALUES ('type', 'Type', 'struct', ?)",
                (source_id,),
            ).lastrowid
            connection.execute(
                "INSERT INTO StructElements "
                "(unique_key, struct_type_id, name, element_type_id, position) "
                "VALUES ('field', ?, 'field', NULL, 1)",
                (type_id,),
            )
            connection.commit()
        finally:
            connection.close()

        development_reset(initialized_db)

        connection = sqlite3.connect(initialized_db)
        try:
            counts = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in set(TABLE_RECORD_MAP) - {"schema_version"}
            }
            fk_count = sum(
                len(connection.execute(f'PRAGMA foreign_key_list("{table}")').fetchall())
                for table in TABLE_RECORD_MAP
            )
        finally:
            connection.close()
        assert set(counts.values()) == {0}
        assert fk_count > 0

    def test_reset_replaces_unrelated_user_tables_with_the_phase_schema(
        self, initialized_db: str
    ) -> None:
        connection = sqlite3.connect(initialized_db)
        try:
            connection.execute("CREATE TABLE DeveloperScratch (value TEXT)")
            connection.execute("INSERT INTO DeveloperScratch VALUES ('temporary')")
            connection.commit()
        finally:
            connection.close()

        development_reset(initialized_db)

        connection = sqlite3.connect(initialized_db)
        try:
            scratch = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'DeveloperScratch'"
            ).fetchone()
        finally:
            connection.close()
        assert scratch is None
