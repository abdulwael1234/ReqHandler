"""Development tests for duplicate detection (LLD-02 §8)."""

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.duplicate_detection import check_for_duplicates, duplicate_warning


class TestCheckForDuplicates:
    def test_matches_ignoring_case(self, initialized_db: str) -> None:
        """SRS-034 — comparison is case-insensitive."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Speed", "struct")
        with db.read_only() as conn:
            matches = check_for_duplicates(conn, dal, "TypeDefinitions", "speed", "struct")
        assert [match["unique_key"] for match in matches] == ["td"]

    def test_matches_after_whitespace_normalization(self, initialized_db: str) -> None:
        """SRS-034 — trim and collapse internal whitespace before comparing."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Vehicle Speed", "struct")
        with db.read_only() as conn:
            matches = check_for_duplicates(
                conn, dal, "TypeDefinitions", "  Vehicle   Speed  ", "struct"
            )
        assert [match["unique_key"] for match in matches] == ["td"]

    def test_a_different_kind_is_not_a_duplicate(self, initialized_db: str) -> None:
        """SRS-034 — duplicates share the same kind and the same name."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            dal.insert_type_definition(conn, "td", "Speed", "struct")
        with db.read_only() as conn:
            assert check_for_duplicates(conn, dal, "TypeDefinitions", "Speed", "enum") == []

    def test_no_match_returns_empty(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.read_only() as conn:
            assert check_for_duplicates(conn, dal, "TypeDefinitions", "Absent", "struct") == []


class TestDuplicateWarning:
    def test_names_the_table_and_the_matches(self) -> None:
        """SRS-121 — the warning is returned in the create response."""
        text = duplicate_warning(
            "TypeDefinitions", "Speed", [{"unique_key": "k", "name": "Speed"}]
        )
        assert "Speed" in text
        assert "k" in text
