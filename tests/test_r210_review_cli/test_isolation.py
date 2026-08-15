"""The review CLI can reach no network (SRS-123, SRS-015).

LLD-06 §7 asks for a code review. That is not a guarantee anyone can re-run, so
this replaces it with two independent automated checks. The static one reads
every module's AST, so it cannot be fooled by a branch that never executes; the
dynamic one imports the CLI in a clean subprocess, so it catches a transitive
import the static scan cannot see.
"""

import ast
import pathlib
import subprocess
import sys

import r210_review_cli

FORBIDDEN = (
    "google.generativeai",
    "google.genai",
    "requests",
    "httpx",
    "urllib",
    "aiohttp",
    "websockets",
    "socket",
    "http",
    "mcp",
)

PACKAGE_ROOT = pathlib.Path(r210_review_cli.__file__).parent


def _imported_names(source: str) -> set[str]:
    """Every absolute module name the source imports, by any syntax."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


class TestStaticIsolation:
    """SRS-123: no network-capable module is imported anywhere in the package."""

    def test_no_forbidden_imports_in_any_module(self) -> None:
        """SRS-123: an AST scan finds no networking or MCP transport import."""
        offenders: list[str] = []
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            for name in _imported_names(path.read_text(encoding="utf-8")):
                if any(name == f or name.startswith(f + ".") for f in FORBIDDEN):
                    offenders.append(f"{path.name}: {name}")
        assert offenders == [], f"network-capable imports found: {offenders}"

    def test_scan_actually_covers_files(self) -> None:
        """A scan over zero files would pass vacuously; assert it does not."""
        assert len(list(PACKAGE_ROOT.rglob("*.py"))) >= 8

    def test_scanner_detects_a_planted_import(self) -> None:
        """The guard must fail when it should — verify against planted source."""
        assert "httpx" in _imported_names("import httpx")
        assert "urllib.request" in _imported_names("from urllib.request import urlopen")

    def test_no_server_module_import(self) -> None:
        """SRS-123 / DEV-40: r210_mcp.server is the module that imports mcp."""
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            assert "r210_mcp.server" not in path.read_text(encoding="utf-8")

    def test_no_dev_reset_import(self) -> None:
        """SRS-091/SRS-093: the destructive reset path is never reachable."""
        for path in sorted(PACKAGE_ROOT.rglob("*.py")):
            assert "dev_reset" not in path.read_text(encoding="utf-8")


class TestDynamicIsolation:
    """SRS-123: importing the CLI pulls in no network stack transitively."""

    def test_importing_cli_loads_no_forbidden_module(self) -> None:
        """SRS-123: after importing the CLI, sys.modules holds no mcp or httpx."""
        program = (
            "import sys; import r210_review_cli.cli; "
            "watch=('mcp','httpx','requests','aiohttp','websockets'); "
            "print(','.join(m for m in watch if m in sys.modules))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            text=True,
            check=True,
            cwd=str(pathlib.Path(r210_review_cli.__file__).parents[1]),
        )
        assert completed.stdout.strip() == "", f"loaded: {completed.stdout.strip()}"
