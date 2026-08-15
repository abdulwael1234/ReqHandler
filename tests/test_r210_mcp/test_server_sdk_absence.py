"""The server must fail legibly where the `mcp` SDK cannot be installed.

Deliberately **not** in `test_server_adapter.py`: that module opens with
`importorskip("mcp")`, so on a machine without the SDK it is skipped entirely —
which is precisely the machine these assertions are about. The work computer
may have no package index, and `ModuleNotFoundError: No module named 'anyio'`
tells an operator nothing about what to install or what still works (DEV-51).

Nothing here imports the SDK, so these run everywhere.
"""

from r210_mcp.server import SdkNotInstalled


class TestSdkNotInstalledMessage:
    """DEV-51: the failure explains itself."""

    def test_names_the_dependency_and_the_fix(self) -> None:
        """DEV-51: the message carries the install command."""
        message = str(SdkNotInstalled(ImportError("No module named 'anyio'")))
        assert "pip install 'mcp>=2.0'" in message

    def test_states_the_major_version_constraint(self) -> None:
        """DEV-50: 1.x and 2.x are not interchangeable."""
        message = str(SdkNotInstalled(ImportError("boom")))
        assert "2.x is required" in message

    def test_says_what_still_works(self) -> None:
        """SRS-123: the review CLI and generator are SDK-free by design."""
        message = str(SdkNotInstalled(ImportError("boom")))
        assert "r210-review" in message
        assert "Everything else works without it" in message

    def test_preserves_the_original_cause(self) -> None:
        """The underlying ImportError stays reachable for diagnosis."""
        cause = ImportError("No module named 'anyio'")
        assert SdkNotInstalled(cause).cause is cause

    def test_is_a_runtime_error(self) -> None:
        """A caller catching RuntimeError should catch this too."""
        assert issubclass(SdkNotInstalled, RuntimeError)


class TestImportableWithoutSdk:
    """SRS-123 / DEV-26: importing the server module must not need the SDK."""

    def test_server_module_imports_without_sdk_loaded(self) -> None:
        """The SDK import lives in build_server(), not at module scope."""
        import ast
        import pathlib

        import r210_mcp.server as server_module

        source = pathlib.Path(server_module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        module_level = {
            alias.name.split(".")[0]
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in getattr(node, "names", [])
        }
        module_level |= {
            node.module.split(".")[0]
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "mcp" not in module_level
        assert "anyio" not in module_level
