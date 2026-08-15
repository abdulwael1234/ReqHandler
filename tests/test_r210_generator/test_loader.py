"""Database snapshot loading (SRS-101, SRS-108)."""

from typing import Any

from r210_generator.loader import SNAPSHOT_TABLES, Loader
from r210_generator.models import DatabaseSnapshot


class TestSnapshotCoverage:
    """LLD-04 §9.1: the snapshot carries all fifteen application tables."""

    def test_every_snapshot_field_is_loaded(self) -> None:
        """SRS-101: a table the loader forgets would silently vanish."""
        fields = {name for name in DatabaseSnapshot.__dataclass_fields__}
        assert {attribute for attribute, _ in SNAPSHOT_TABLES} == fields

    def test_fifteen_tables(self) -> None:
        """LLD-04 §9.1 enumerates fifteen tables; schema_version is not one."""
        assert len(SNAPSHOT_TABLES) == 15
        assert "schema_version" not in {table for _, table in SNAPSHOT_TABLES}


class TestLoadAll:
    """SRS-101: the loader reads a consistent view of every table."""

    def test_loads_records_from_a_real_database(self, populated_db: str) -> None:
        """SRS-101: records created through the tools come back in the snapshot."""
        snapshot = Loader().load_all(populated_db)
        # Ordered by kind first: "simple_typedef" sorts before "struct".
        assert [t.name for t in snapshot.type_definitions] == ["Float32", "SensorData"]
        assert [e.name for e in snapshot.struct_elements] == ["temperature"]
        assert len(snapshot.review_issues) == 1

    def test_empty_database_yields_empty_snapshot(self, initialized_db: str) -> None:
        """SRS-104: generation must work when nothing has been extracted yet."""
        snapshot = Loader().load_all(initialized_db)
        assert snapshot.type_definitions == ()
        assert snapshot.review_issues == ()

    def test_type_definitions_ordered_by_kind_then_name(self, initialized_db: str) -> None:
        """LLD-04 §9.2: TypeDefinitions sort by kind, name (nocase), id."""
        from r210_mcp.tools.context import build_context
        from r210_mcp.tools.registry import dispatch

        ctx = build_context(initialized_db, adapter_mode="extraction")
        for name, kind, subtype in [
            ("zebra", "struct", {"elements": []}),
            ("Alpha", "struct", {"elements": []}),
            ("beta", "enum", {"values": []}),
        ]:
            dispatch(
                ctx, "create_type_definition", {"name": name, "kind": kind, "subtype": subtype}
            )

        snapshot = Loader().load_all(initialized_db)
        assert [(t.kind, t.name) for t in snapshot.type_definitions] == [
            ("enum", "beta"),
            ("struct", "Alpha"),
            ("struct", "zebra"),
        ]

    def test_loading_twice_is_identical(self, populated_db: str) -> None:
        """SRS-101: the same database yields the same snapshot every time."""
        loader = Loader()
        assert loader.load_all(populated_db) == loader.load_all(populated_db)

    def test_children_ordered_by_position(self, initialized_db: str) -> None:
        """SRS-108: ordered children come back in declaration order."""
        from r210_mcp.tools.context import build_context
        from r210_mcp.tools.registry import dispatch

        ctx = build_context(initialized_db, adapter_mode="extraction")
        struct = str(
            dispatch(
                ctx,
                "create_type_definition",
                {"name": "S", "kind": "struct", "subtype": {"elements": []}},
            )["result"]["unique_key"]
        )
        for name, position in [("third", 3), ("first", 1), ("second", 2)]:
            dispatch(
                ctx,
                "create_struct_element",
                {"struct_type_key": struct, "name": name, "position": position},
            )

        snapshot = Loader().load_all(initialized_db)
        assert [e.name for e in snapshot.struct_elements] == ["first", "second", "third"]


class TestSnapshotHelpers:
    """LLD-04 §9.1: the snapshot indexes its own records for reference lookup."""

    def test_indexes_by_id(self, approved_struct_snapshot: DatabaseSnapshot) -> None:
        """SRS-102: FK validation resolves targets through these indexes."""
        assert approved_struct_snapshot.type_definitions_by_id()[1].name == "Float32"

    def test_source_reference_lookup(self, make_snapshot: Any) -> None:
        """SRS-104: the report cites an artifact's source reference."""
        from .conftest import source_requirement

        snapshot = make_snapshot(source_requirements=[source_requirement(1, "REQ-042")])
        assert snapshot.source_reference_of(1) == "REQ-042"
        assert snapshot.source_reference_of(None) is None
        assert snapshot.source_reference_of(99) is None
