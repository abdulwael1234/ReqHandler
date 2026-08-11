"""Tests for the database initializer CLI (LLD-05 §3).

Requirement coverage: SRS-094, SRS-098, SRS-100, SRS-109.
"""

import sqlite3
from pathlib import Path

import pytest

from r210_db_init.cli import main
from r210_db_init.initializer import DatabaseInitializer


def _run(monkeypatch, *argv: str) -> int:
    monkeypatch.setattr("sys.argv", ["r210-init-db", *argv])
    with pytest.raises(SystemExit) as excinfo:
        main()
    return excinfo.value.code


def _source_requirement_count(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM SourceRequirements").fetchone()[0]
    finally:
        conn.close()


def _insert_row(db_path: str, key: str = "row-1") -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO SourceRequirements (unique_key, source_reference) VALUES (?, 'DOC-1')",
            (key,),
        )
        conn.commit()
    finally:
        conn.close()


class TestInitCommand:
    """SRS-094: a safe init_db operation outside the Gemini-facing MCP tools."""

    def test_init_creates_database_and_exits_zero(self, monkeypatch, db_path: str) -> None:
        code = _run(monkeypatch, "init", db_path)

        assert code == 0
        assert Path(db_path).exists()

    def test_init_reports_final_version(self, monkeypatch, db_path: str, capsys) -> None:
        _run(monkeypatch, "init", db_path)

        assert "1" in capsys.readouterr().out

    def test_repeated_init_still_exits_zero(self, monkeypatch, db_path: str) -> None:
        _run(monkeypatch, "init", db_path)

        assert _run(monkeypatch, "init", db_path) == 0

    def test_init_exits_nonzero_when_initialization_fails(
        self, monkeypatch, initialized_db: str
    ) -> None:
        """SRS-109: failures are reported, not silently swallowed."""
        conn = sqlite3.connect(initialized_db)
        try:
            conn.execute("INSERT INTO schema_version (version) VALUES (99)")
            conn.commit()
        finally:
            conn.close()

        assert _run(monkeypatch, "init", initialized_db) == 1

    def test_init_writes_failure_reason_to_stderr(
        self, monkeypatch, initialized_db: str, capsys
    ) -> None:
        conn = sqlite3.connect(initialized_db)
        try:
            conn.execute("INSERT INTO schema_version (version) VALUES (99)")
            conn.commit()
        finally:
            conn.close()

        _run(monkeypatch, "init", initialized_db)

        assert "99" in capsys.readouterr().err


class TestResetCommand:
    """SRS-100: destructive reset is development-only and gated behind --confirm."""

    def test_reset_without_confirm_exits_nonzero(self, monkeypatch, initialized_db: str) -> None:
        assert _run(monkeypatch, "reset", initialized_db) == 1

    def test_reset_without_confirm_preserves_data(self, monkeypatch, initialized_db: str) -> None:
        _insert_row(initialized_db)

        _run(monkeypatch, "reset", initialized_db)

        assert _source_requirement_count(initialized_db) == 1

    def test_reset_with_confirm_clears_data(self, monkeypatch, initialized_db: str) -> None:
        _insert_row(initialized_db)

        code = _run(monkeypatch, "reset", initialized_db, "--confirm")

        assert code == 0
        assert _source_requirement_count(initialized_db) == 0


class TestArgumentHandling:
    def test_missing_command_exits_nonzero(self, monkeypatch) -> None:
        assert _run(monkeypatch) != 0

    def test_unknown_command_exits_nonzero(self, monkeypatch, db_path: str) -> None:
        assert _run(monkeypatch, "drop-everything", db_path) != 0


class TestMcpSurfaceExclusion:
    """SRS-093 / SRS-100: reset is not reachable from the MCP tool surface."""

    def test_reset_is_not_importable_from_the_mcp_package(self) -> None:
        import r210_mcp

        assert not hasattr(r210_mcp, "development_reset")

    def test_initializer_exposes_no_drop_helpers(self) -> None:
        public_names = [name for name in dir(DatabaseInitializer) if not name.startswith("_")]

        assert not any("drop" in name.lower() or "reset" in name.lower() for name in public_names)
