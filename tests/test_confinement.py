"""Generated output must not be committable.

`docs/WORK_MACHINE_CONFIGURATION.md` requires, before enabling work-specific
generation: "Confirm no real work data, completed configuration, generated
output, or review report is committed or transferred back outside the work
computer."

On the work computer that content is real. `.gitignore` is the last line of
defence against `git add -A`, and it is the kind of file that silently drifts
from the code — it listed `output/` while the CLI wrote to `r210_output/`.
These tests tie it to the constants it must cover.
"""

import pathlib
import subprocess
import sys

import pytest

from r210_generator.models import GeneratorConfig
from r210_review_cli.cli import DEFAULT_OUTPUT_DIR

REPO_ROOT = pathlib.Path(__file__).parents[1]
GITIGNORE = REPO_ROOT / ".gitignore"


def _is_ignored(relative_path: str) -> bool:
    """Whether git would ignore this path, asked of git itself.

    Pattern-matching `.gitignore` by hand would re-implement git's rules and
    get them subtly wrong; `check-ignore` is the authority.
    """
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", relative_path],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    return completed.returncode == 0


class TestGeneratedOutputIsIgnored:
    """WORK_MACHINE_CONFIGURATION: generated output stays on the work computer."""

    def test_cli_default_output_dir_is_ignored(self) -> None:
        """Everything written with no --output must be uncommittable.

        Probed with an arbitrary filename, not `review_report.md`: that name
        has its own ignore rule, so testing it would pass even with the
        directory rule missing — which is how this test first passed against
        the very bug it exists to catch.
        """
        assert _is_ignored(f"{DEFAULT_OUTPUT_DIR}/anything-at-all.txt"), (
            f"the review CLI writes to {DEFAULT_OUTPUT_DIR}/ by default, "
            "but .gitignore does not cover the directory"
        )

    def test_report_filename_is_ignored_anywhere(self) -> None:
        """The report must not be committable from any directory."""
        name = GeneratorConfig(output_dir="unused").report_filename
        assert _is_ignored(name)
        assert _is_ignored(f"some/nested/dir/{name}")

    def test_databases_are_ignored(self) -> None:
        """SRS-015: a populated database holds requirement text."""
        assert _is_ignored("r210.db")
        assert _is_ignored("nested/work.sqlite3")

    @pytest.mark.parametrize("path", ["out.arxml", "r210_output/Type_Sensor.arxml"])
    def test_r210_artifacts_are_ignored(self, path: str) -> None:
        """SRS-103: rendered R210 files are work output."""
        assert _is_ignored(path)


class TestNoWorkDataCommitted:
    """This repository copy carries no real work data, by requirement."""

    def test_no_database_is_tracked(self) -> None:
        """A committed database would carry requirement text off-machine."""
        tracked = subprocess.run(
            ["git", "ls-files"], cwd=str(REPO_ROOT), capture_output=True, text=True
        ).stdout.splitlines()
        offenders = [
            name
            for name in tracked
            if name.endswith((".db", ".sqlite", ".sqlite3", ".arxml"))
        ]
        assert offenders == [], f"data files are tracked: {offenders}"

    def test_gitignore_documents_why(self) -> None:
        """The patterns must carry their reason, or they get 'tidied' away."""
        text = GITIGNORE.read_text(encoding="utf-8")
        assert "WORK_MACHINE_CONFIGURATION.md" in text


@pytest.mark.skipif(sys.platform not in ("win32", "linux", "darwin"), reason="needs git")
class TestGitIsAvailable:
    """The tests above are vacuous if `git check-ignore` cannot run."""

    def test_check_ignore_detects_a_known_pattern(self) -> None:
        """A control: __pycache__ is ignored, a source file is not."""
        assert _is_ignored("__pycache__/x.pyc")
        assert not _is_ignored("src/r210_mcp/server.py")
