"""Shared pytest fixtures for the R210 test suite."""

import sqlite3
from pathlib import Path

import pytest

from r210_db_init.initializer import DatabaseInitializer

# All application tables plus the version table (LLD-05 §4.3).
EXPECTED_TABLES = frozenset({
    "schema_version",
    "SourceRequirements",
    "TypeDefinitions",
    "SimpleTypeDefinitions",
    "ArrayTypeDefinitions",
    "StructElements",
    "EnumValues",
    "PortInterfaces",
    "InterfaceDataElements",
    "ClientServerOperations",
    "OperationArguments",
    "PortPrototypes",
    "PortPrototypeFunctions",
    "PortConnections",
    "PortConnectionMembers",
    "ReviewIssues",
})


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Path to a database file that does not exist yet."""
    return str(tmp_path / "r210.db")


@pytest.fixture
def initialized_db(db_path: str) -> str:
    """Path to a freshly initialized database at the current schema version."""
    result = DatabaseInitializer(db_path).init_db()
    assert result.status == "success", f"fixture setup failed: {result.error}"
    return db_path


@pytest.fixture
def conn(initialized_db: str):
    """Open connection to an initialized database with FK enforcement on."""
    connection = sqlite3.connect(initialized_db)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
    finally:
        connection.close()
