"""R210 rendering framework (SRS-101, SRS-103, SRS-108, SRS-092a).

The four real templates are SRS-019(c) work-computer values and are absent from
this repository copy, so every test here injects a synthetic `TemplateSet`.
That is the point of the injected design (DEV-47): dispatch, ordering,
exclusion and byte-determinism are real logic and are verified now, leaving
only the template bodies for the work computer.
"""

from typing import Any

import pytest

from r210_generator.models import ArtifactTree, DatabaseSnapshot, GeneratorConfig
from r210_generator.r210.renderer import Renderer, sort_children, sort_trees, type_sort_key
from r210_generator.r210.templates import (
    UNCONFIGURED_ACCESS_POINTS,
    UNCONFIGURED_NAMING,
    UNCONFIGURED_TEMPLATES,
    AccessPointPolicy,
    NamingPolicy,
    TemplateNotConfigured,
    TemplateSet,
    unmet_criteria,
)

from .conftest import (
    REJECTED,
    base_type,
    connection_member,
    enum_value,
    port_connection,
    port_interface,
    port_prototype,
    struct_element,
    type_definition,
)


def _label(record: Any) -> str:
    return str(getattr(record, "name", None) or getattr(record, "description", None) or "")


def synthetic_template(kind: str) -> Any:
    """A deterministic stand-in that records what it was given."""

    def render(record: Any, children: list[tuple[str, Any]], _snapshot: Any, _config: Any) -> str:
        names = ",".join(_label(child) for _, child in children)
        return f"{kind}:{_label(record)}[{names}]"

    return render


SYNTHETIC_TEMPLATES = TemplateSet(
    simple_typedef=synthetic_template("simple"),
    array_type=synthetic_template("array"),
    struct_type=synthetic_template("struct"),
    enum_type=synthetic_template("enum"),
    sender_receiver=synthetic_template("sr"),
    client_server=synthetic_template("cs"),
    port_prototype=synthetic_template("pp"),
    port_connection=synthetic_template("pc"),
)

SYNTHETIC_NAMING = NamingPolicy(
    file_path=lambda table, record, _config: f"{table}/{record.unique_key}.txt"
)

SYNTHETIC_ACCESS_POINTS = AccessPointPolicy(
    access_point_element=lambda _f, _p, _i: "DataReadAccess"
)


def synthetic_config(output_dir: str = "unused") -> GeneratorConfig:
    """A fully configured generator, as the work computer would supply it."""
    return GeneratorConfig(
        output_dir=output_dir,
        templates=SYNTHETIC_TEMPLATES,
        naming=SYNTHETIC_NAMING,
        access_points=SYNTHETIC_ACCESS_POINTS,
    )


def tree(table: str, record: Any, children: tuple[tuple[str, Any], ...] = ()) -> ArtifactTree:
    return ArtifactTree(table=table, record=record, active_children=children)


class TestUnconfiguredTemplates:
    """SRS-019(c): the real templates live only on the work computer."""

    def test_every_default_template_raises(self) -> None:
        """DEV-47: an unconfigured render is refused, not silently empty."""
        for name in (
            "simple_typedef",
            "array_type",
            "struct_type",
            "enum_type",
            "sender_receiver",
            "client_server",
            "port_prototype",
            "port_connection",
        ):
            with pytest.raises(TemplateNotConfigured):
                getattr(UNCONFIGURED_TEMPLATES, name)()

    def test_error_names_the_missing_criterion(self) -> None:
        """PHASE5_SCOPE §2: the operator is told what is missing."""
        with pytest.raises(TemplateNotConfigured, match="SRS-019"):
            UNCONFIGURED_TEMPLATES.struct_type()

    def test_naming_and_access_points_also_raise(self) -> None:
        """SRS-019(d), SRS-064: the other two plug-points behave the same."""
        with pytest.raises(TemplateNotConfigured, match="SRS-019"):
            UNCONFIGURED_NAMING.file_path()
        with pytest.raises(TemplateNotConfigured, match="SRS-064"):
            UNCONFIGURED_ACCESS_POINTS.access_point_element()

    def test_trigger_element_is_already_known(self) -> None:
        """LLD-04 §6.7: only access_point is TBD; trigger has a fixed answer."""
        assert UNCONFIGURED_ACCESS_POINTS.trigger_element == "ExternalTriggeringPoint"

    def test_unmet_criteria_lists_all_four(self) -> None:
        """PHASE5_SCOPE §2: four open criteria with nothing configured."""
        assert unmet_criteria(
            UNCONFIGURED_TEMPLATES, UNCONFIGURED_NAMING, UNCONFIGURED_ACCESS_POINTS
        ) == ("SRS-019(c)", "SRS-019(d)", "SRS-019", "SRS-064")

    def test_configured_set_reports_nothing_unmet(self) -> None:
        """DEV-47: supplying the three policies closes all four criteria."""
        assert unmet_criteria(SYNTHETIC_TEMPLATES, SYNTHETIC_NAMING, SYNTHETIC_ACCESS_POINTS) == ()


class TestArtifactOrdering:
    """LLD-04 §6.3: type sort key, then sort field, then id (SRS-101)."""

    def test_type_sort_keys_match_the_table(self) -> None:
        """LLD-04 §6.3: eight artifact types in the documented order."""
        assert type_sort_key(tree("TypeDefinitions", base_type(1))) == 1
        assert type_sort_key(tree("TypeDefinitions", type_definition(2, "A", kind="array"))) == 2
        assert type_sort_key(tree("TypeDefinitions", type_definition(3, "S", kind="struct"))) == 3
        assert type_sort_key(tree("TypeDefinitions", type_definition(4, "E", kind="enum"))) == 4
        assert (
            type_sort_key(
                tree("PortInterfaces", port_interface(1, "I", interface_type="sender_receiver"))
            )
            == 5
        )
        assert type_sort_key(tree("PortInterfaces", port_interface(2, "J"))) == 6
        assert type_sort_key(tree("PortPrototypes", port_prototype(1, "P"))) == 7
        assert type_sort_key(tree("PortConnections", port_connection(1, "C"))) == 8

    def test_type_precedes_name(self) -> None:
        """SRS-101: the primary key is the artifact type, not the name."""
        ordered = sort_trees(
            [
                tree("TypeDefinitions", type_definition(1, "aaa", kind="struct")),
                tree("TypeDefinitions", base_type(2, "zzz")),
            ]
        )
        assert [t.label for t in ordered] == ["zzz", "aaa"]

    def test_name_sort_is_case_insensitive(self) -> None:
        """LLD-04 §6.3: the secondary sort is case-insensitive."""
        ordered = sort_trees(
            [
                tree("TypeDefinitions", type_definition(1, "beta", kind="struct")),
                tree("TypeDefinitions", type_definition(2, "Alpha", kind="struct")),
            ]
        )
        assert [t.label for t in ordered] == ["Alpha", "beta"]

    def test_connection_sorts_on_description(self) -> None:
        """LLD-04 §6.3: PortConnections has no name; it sorts on description."""
        ordered = sort_trees(
            [
                tree("PortConnections", port_connection(1, "zebra bus")),
                tree("PortConnections", port_connection(2, "alpha bus")),
            ]
        )
        assert [t.label for t in ordered] == ["alpha bus", "zebra bus"]

    def test_null_description_does_not_crash(self) -> None:
        """LLD-04 v1.2 H-06: a nullable sort field must not break ordering."""
        from r210_mcp.db.models import PortConnectionRecord

        nameless = PortConnectionRecord(
            id=1, unique_key="pc-1", description=None, source_requirement_id=None,
            status="approved", review_note=None,
        )
        assert sort_trees([tree("PortConnections", nameless)])[0].label == ""

    def test_id_breaks_ties(self) -> None:
        """LLD-04 §6.3: identical names fall back to id."""
        ordered = sort_trees(
            [
                tree("TypeDefinitions", type_definition(9, "same", kind="struct")),
                tree("TypeDefinitions", type_definition(2, "same", kind="struct")),
            ]
        )
        assert [t.record.id for t in ordered] == [2, 9]


class TestChildOrdering:
    """LLD-04 §6.4 / SRS-108: children order by (position, id)."""

    def test_children_sort_by_position(self) -> None:
        """SRS-108: declaration order is preserved in the output."""
        children = (
            ("StructElements", struct_element(1, 2, "third", 3)),
            ("StructElements", struct_element(2, 2, "first", 1)),
            ("StructElements", struct_element(3, 2, "second", 2)),
        )
        assert [c.name for _, c in sort_children(children)] == ["first", "second", "third"]

    def test_equal_positions_fall_back_to_id(self) -> None:
        """LLD-04 §6.4: equal positions order by id."""
        children = (
            ("EnumValues", enum_value(9, 1, "later", 1)),
            ("EnumValues", enum_value(2, 1, "earlier", 1)),
        )
        assert [c.id for _, c in sort_children(children)] == [2, 9]


class TestRendering:
    """LLD-04 §6.2: dispatch to the right template with prepared children."""

    def test_dispatches_by_artifact_type(self) -> None:
        """SRS-103: each artifact type reaches its own template."""
        trees = [
            tree("TypeDefinitions", base_type(1)),
            tree("TypeDefinitions", type_definition(2, "S", kind="struct")),
            tree("PortInterfaces", port_interface(1, "I")),
            tree("PortPrototypes", port_prototype(1, "P")),
            tree("PortConnections", port_connection(1, "C")),
        ]
        files = Renderer(synthetic_config()).render(trees, DatabaseSnapshot())
        assert [f.content for f in files] == [
            "simple:Float32[]",
            "struct:S[]",
            "cs:I[]",
            "pp:P[]",
            "pc:C[]",
        ]

    def test_children_reach_the_template_ordered(self) -> None:
        """LLD-04 §6.4: a template receives children already sorted."""
        subject = tree(
            "TypeDefinitions",
            type_definition(2, "SensorData", kind="struct"),
            (
                ("StructElements", struct_element(1, 2, "second", 2)),
                ("StructElements", struct_element(2, 2, "first", 1)),
            ),
        )
        files = Renderer(synthetic_config()).render([subject], DatabaseSnapshot())
        assert files[0].content == "struct:SensorData[first,second]"

    def test_rejected_children_never_reach_the_template(self) -> None:
        """SRS-092a: a rejected child is excluded from rendered output.

        `active_children` is what the validator hands over, so this asserts the
        renderer honours the split rather than re-deriving it.
        """
        subject = ArtifactTree(
            table="TypeDefinitions",
            record=type_definition(2, "SensorData", kind="struct"),
            active_children=(("StructElements", struct_element(1, 2, "kept", 1)),),
            excluded_children=(
                ("StructElements", struct_element(2, 2, "dropped", 2, status=REJECTED)),
            ),
        )
        files = Renderer(synthetic_config()).render([subject], DatabaseSnapshot())
        assert "dropped" not in files[0].content
        assert "kept" in files[0].content

    def test_file_path_comes_from_the_naming_policy(self) -> None:
        """SRS-019(d): output paths are a configured policy, not hard-coded."""
        files = Renderer(synthetic_config()).render(
            [tree("TypeDefinitions", base_type(1))], DatabaseSnapshot()
        )
        assert files[0].path == "TypeDefinitions/td-1.txt"

    def test_unconfigured_renderer_raises(self) -> None:
        """DEV-47: with no templates, rendering refuses rather than inventing."""
        renderer = Renderer(GeneratorConfig(output_dir="unused"))
        with pytest.raises(TemplateNotConfigured):
            renderer.render([tree("TypeDefinitions", base_type(1))], DatabaseSnapshot())

    def test_rendering_is_deterministic(self) -> None:
        """SRS-101: the same trees render to the same files, in the same order."""
        trees = [
            tree("PortConnections", port_connection(1, "zebra")),
            tree("TypeDefinitions", base_type(2)),
            tree("TypeDefinitions", type_definition(3, "S", kind="struct")),
        ]
        renderer = Renderer(synthetic_config())
        first = renderer.render(list(trees), DatabaseSnapshot())
        second = renderer.render(list(reversed(trees)), DatabaseSnapshot())
        assert [(f.path, f.content) for f in first] == [(f.path, f.content) for f in second]


class TestConnectionMembersAreNotExpanded:
    """SRS-073: a connection renders as one global multi-port block."""

    def test_all_members_go_to_one_render_call(self) -> None:
        """SRS-073: no pairwise provider/requester expansion."""
        subject = tree(
            "PortConnections",
            port_connection(1, "brake bus"),
            (
                ("PortConnectionMembers", connection_member(1, 1, 1, 1)),
                ("PortConnectionMembers", connection_member(2, 1, 2, 2)),
                ("PortConnectionMembers", connection_member(3, 1, 3, 3)),
            ),
        )
        files = Renderer(synthetic_config()).render([subject], DatabaseSnapshot())
        assert len(files) == 1
