"""CLI entry point: parsing, dispatch and exit codes (SRS-118, SRS-123)."""

import sys
from typing import Any

import pytest

from r210_review_cli import cli

from .conftest import Seeded

UNKNOWN_KEY = "99999999-9999-4999-8999-999999999999"

EXPECTED_COMMANDS = {
    "list",
    "show",
    "search",
    "approve",
    "reject",
    "mark",
    "resolve",
    "dismiss",
    "reopen",
    "report",
    "generate",
    "stats",
}


class TestParser:
    """LLD-06 §4.1: twelve commands, not the stub docstring's nine."""

    def test_all_twelve_commands_registered(self) -> None:
        """SRS-118: every LLD-06 §4.1 command is reachable."""
        assert set(cli.COMMANDS) == EXPECTED_COMMANDS

    def test_parser_exposes_the_same_twelve(self) -> None:
        """SRS-118: the parser and the dispatch table cannot drift apart."""
        subparsers = [
            action
            for action in cli.build_parser()._subparsers._group_actions  # noqa: SLF001
            if action.choices is not None
        ]
        assert set(subparsers[0].choices) == EXPECTED_COMMANDS

    def test_missing_command_exits_two(self) -> None:
        """SRS-118: a usage error is exit code 2, argparse's convention."""
        with pytest.raises(SystemExit) as exc:
            cli.build_parser().parse_args([])
        assert exc.value.code == 2

    def test_unknown_entity_type_exits_two(self) -> None:
        """SRS-118: an entity type outside LLD-06 §4.2 is a usage error."""
        with pytest.raises(SystemExit) as exc:
            cli.build_parser().parse_args(["list", "widgets"])
        assert exc.value.code == 2

    def test_db_defaults_to_r210_db(self) -> None:
        """LLD-06 §4.3: --db defaults to r210.db."""
        assert cli.build_parser().parse_args(["stats"]).db == "r210.db"


class TestRun:
    """SRS-118: commands run end to end against a real database."""

    def test_list_exits_zero(self, seeded: Seeded, capsys: pytest.CaptureFixture[str]) -> None:
        """SRS-118: listing a populated table succeeds."""
        assert cli.run(["--db", seeded.db_path, "list", "td"]) == 0
        assert "SensorData" in capsys.readouterr().out

    def test_approve_then_show(self, seeded: Seeded, capsys: pytest.CaptureFixture[str]) -> None:
        """SRS-082a: the CLI carries review authority."""
        assert cli.run(["--db", seeded.db_path, "approve", seeded.base_type_key]) == 0
        assert cli.run(["--db", seeded.db_path, "show", seeded.base_type_key]) == 0
        assert "approved" in capsys.readouterr().out

    def test_tool_error_exits_one(self, seeded: Seeded) -> None:
        """SRS-109: a tool error becomes exit code 1."""
        assert cli.run(["--db", seeded.db_path, "show", UNKNOWN_KEY]) == 1

    def test_stats_exits_zero(self, seeded: Seeded) -> None:
        """SRS-118: stats runs against every table."""
        assert cli.run(["--db", seeded.db_path, "stats"]) == 0

    def test_search_by_alias(self, seeded: Seeded, capsys: pytest.CaptureFixture[str]) -> None:
        """LLD-06 §4.2: the short alias works as well as the long form."""
        assert cli.run(["--db", seeded.db_path, "search", "td", "--name", "float%"]) == 0
        assert "Float32" in capsys.readouterr().out

    def test_resolve_requires_resolution(self, seeded: Seeded) -> None:
        """LLD-06 §4.3: --resolution is mandatory for resolve."""
        with pytest.raises(SystemExit) as exc:
            cli.run(["--db", seeded.db_path, "resolve", seeded.issue_key])
        assert exc.value.code == 2

    def test_full_review_walkthrough(self, seeded: Seeded) -> None:
        """SRS-118: approve a tree bottom-up and resolve an issue, all via argv."""
        db = seeded.db_path
        assert cli.run(["--db", db, "approve", seeded.base_type_key]) == 0
        assert cli.run(["--db", db, "approve", seeded.struct_element_key]) == 0
        assert cli.run(["--db", db, "approve", seeded.type_key]) == 0
        assert cli.run(
            ["--db", db, "resolve", seeded.issue_key, "--resolution", "units are mV"]
        ) == 0


class TestColorIsGated:
    """SRS-118: captured (non-tty) output carries no escape sequences."""

    def test_no_ansi_in_captured_output(
        self, seeded: Seeded, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """DEV-44: pytest's captured stdout is not a tty, so colour is off."""
        cli.run(["--db", seeded.db_path, "list", "td"])
        assert "\x1b[" not in capsys.readouterr().out


class TestOutputEncoding:
    """SRS-118: LLD-06 §6.2's glyphs must reach a non-UTF-8 console."""

    def test_cli_survives_a_cp1252_stdout(self, seeded: Seeded, tmp_path: object) -> None:
        """SRS-118: a Windows cp1252 console must not crash the CLI.

        Regression: `─`, `■`, `✓`, `✗` and `⚠` are outside cp1252, so printing
        a formatted table raised UnicodeEncodeError before `run` reconfigured
        stdout. pytest's own capture is UTF-8, which is why this needs a real
        cp1252 stream rather than capsys.
        """
        import io

        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding="cp1252", newline="")
        original = sys.stdout
        sys.stdout = stream
        try:
            code = cli.run(["--db", seeded.db_path, "list", "td"])
            stream.flush()
        finally:
            sys.stdout = original
        assert code == 0
        assert b"SensorData" in buffer.getvalue()


class TestGenerationCommands:
    """SRS-090, SRS-104: report and generate run the real generator."""

    def test_report_command_writes_a_report(
        self, seeded: Seeded, tmp_path: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """SRS-104: `report` produces a file and exits 0.

        Regression: GenerationResult.summary() names a count `warnings`
        (LLD-04 §10), which collides with the MCP envelope's list of
        duplicate-detection warnings. The formatter iterated it and raised
        TypeError before the counts were renamed at the tool boundary.
        """
        code = cli.run(["--db", seeded.db_path, "report", "--output", str(tmp_path)])
        assert code == 0
        assert (tmp_path / "review_report.md").exists()
        assert "report_file" in capsys.readouterr().out

    def test_generate_reports_unmet_criteria(
        self, seeded: Seeded, tmp_path: Any, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """PHASE5_SCOPE §2: R210 modes name what configuration is missing."""
        code = cli.run(["--db", seeded.db_path, "generate", "--mode", "r210_only",
                        "--output", str(tmp_path)])
        assert code == 1
        assert "SRS-019(c)" in capsys.readouterr().out

    def test_generate_defaults_to_an_explicit_output_dir(self) -> None:
        """DEV-48: the CLI states its default rather than inheriting one."""
        assert cli.build_parser().parse_args(["generate"]).output == cli.DEFAULT_OUTPUT_DIR
