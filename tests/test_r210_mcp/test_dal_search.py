"""Pattern search over the name column (SRS-118 reviewer inspection)."""

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer


@pytest.fixture
def seeded(initialized_db: str) -> str:
    """Three type definitions with names that differ by case and prefix."""
    db = DatabaseConnection(initialized_db)
    dal = DataAccessLayer()
    with db.transaction() as conn:
        for key, name in [
            ("11111111-1111-4111-8111-111111111111", "SensorData"),
            ("22222222-2222-4222-8222-222222222222", "sensorConfig"),
            ("33333333-3333-4333-8333-333333333333", "MotorState"),
        ]:
            dal.insert_record(
                conn,
                "TypeDefinitions",
                {"unique_key": key, "name": name, "kind": "struct", "status": "pending_review"},
            )
    return initialized_db


class TestSearchByNamePattern:
    """SRS-118: the reviewer inspects artifacts by name pattern."""

    def test_matches_case_insensitively(self, seeded: str) -> None:
        """SRS-118: 'sensor%' finds both SensorData and sensorConfig."""
        db = DatabaseConnection(seeded)
        dal = DataAccessLayer()
        with db.read_only() as conn:
            found = dal.search_by_name_pattern(conn, "TypeDefinitions", "sensor%")
        assert [r.name for r in found] == ["SensorData", "sensorConfig"]

    def test_non_matching_pattern_returns_empty(self, seeded: str) -> None:
        """SRS-118: a pattern matching nothing yields no rows, not an error."""
        db = DatabaseConnection(seeded)
        dal = DataAccessLayer()
        with db.read_only() as conn:
            assert dal.search_by_name_pattern(conn, "TypeDefinitions", "zzz%") == []

    def test_unknown_table_rejected(self, seeded: str) -> None:
        """SRS-113: identifiers are allowlisted, never interpolated."""
        db = DatabaseConnection(seeded)
        dal = DataAccessLayer()
        with db.read_only() as conn, pytest.raises(ValueError):
            dal.search_by_name_pattern(conn, "TypeDefinitions; DROP TABLE x", "a%")

    def test_table_without_name_column_rejected(self, seeded: str) -> None:
        """SRS-113: a table with no name column is a programming error."""
        db = DatabaseConnection(seeded)
        dal = DataAccessLayer()
        with db.read_only() as conn, pytest.raises(ValueError, match="no name column"):
            dal.search_by_name_pattern(conn, "PortConnections", "a%")

    def test_ordering_is_deterministic(self, seeded: str) -> None:
        """SRS-108: results come back in the table's deterministic order."""
        db = DatabaseConnection(seeded)
        dal = DataAccessLayer()
        with db.read_only() as conn:
            first = dal.search_by_name_pattern(conn, "TypeDefinitions", "%")
            second = dal.search_by_name_pattern(conn, "TypeDefinitions", "%")
        assert [r.id for r in first] == [r.id for r in second] == [1, 2, 3]
