"""Review report content and structure (SRS-104, SRS-104a, SRS-101)."""

from typing import Any

import pytest

from r210_generator.models import (
    ExportedArtifact,
    GenerationResult,
    GeneratorConfig,
    ValidationError,
    ValidationWarning,
)
from r210_generator.report.builder import ReportBuilder
from r210_generator.validator import evaluate_exportable_trees

from .conftest import (
    PENDING,
    REJECTED,
    argument,
    base_type,
    connection_member,
    data_element,
    function,
    operation,
    port_connection,
    port_interface,
    port_prototype,
    review_issue,
    simple_detail,
    source_requirement,
    struct_element,
    type_definition,
)

SECTION_ORDER = [
    "## (a) Approved and Generated",
    "## (a2) Excluded - Unresolved References",
    "## (b) Approved but Excluded",
    "## (c) Pending Review",
    "## (d) Ambiguous",
    "## (e) Rejected",
    "## (f) Out of Scope",
    "## (g) Pending Issues",
    "## (h) Decision Log",
]


def _config(**kwargs: Any) -> GeneratorConfig:
    return GeneratorConfig(output_dir="unused", **kwargs)


class TestSectionOrder:
    """LLD-04 §7.1: the sections appear in one fixed order."""

    def test_all_sections_present_in_order(self, make_snapshot: Any) -> None:
        """SRS-104: eight sections plus (a2), always, in document order."""
        report = ReportBuilder().build(make_snapshot(), GenerationResult(), _config())
        positions = [report.index(heading) for heading in SECTION_ORDER]
        assert positions == sorted(positions)

    def test_report_builds_on_an_empty_database(self, make_snapshot: Any) -> None:
        """SRS-104: the report is produced even when nothing was extracted."""
        report = ReportBuilder().build(make_snapshot(), GenerationResult(), _config())
        assert "No artifacts were approved and generated." in report
        assert "No issues are pending." in report


class TestSectionContent:
    """SRS-104(a)-(g): each section lists what the requirement says it does."""

    def test_section_a_lists_exported_artifacts(self, make_snapshot: Any) -> None:
        """SRS-104(a): generated artifacts, with the file each produced."""
        result = GenerationResult(
            exported_artifacts=[
                ExportedArtifact("TypeDefinitions", "td-1", "SensorData", "out/SensorData.arxml")
            ]
        )
        report = ReportBuilder().build(make_snapshot(), result, _config())
        assert "SensorData" in report and "out/SensorData.arxml" in report

    def test_section_a_is_empty_when_nothing_rendered(self, make_snapshot: Any) -> None:
        """SRS-104(a): approved trees are not reported as generated files."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1)], simple_type_definitions=[simple_detail(1, 1)]
        )
        result = GenerationResult(exportable_trees=evaluate_exportable_trees(snapshot).trees)
        report = ReportBuilder().build(snapshot, result, _config())
        generated_section = report[
            report.index("## (a) Approved and Generated") : report.index(
                "## (a2) Excluded - Unresolved References"
            )
        ]
        assert "No artifacts were approved and generated." in generated_section
        assert "Float32" not in generated_section

    def test_section_a2_lists_fk_errors(self, make_snapshot: Any) -> None:
        """SRS-102: artifacts excluded for unresolved references are listed."""
        result = GenerationResult(
            r210_errors=[
                ValidationError("TypeDefinitions", "td-2", "SensorData", "element_type_id is null")
            ]
        )
        report = ReportBuilder().build(make_snapshot(), result, _config())
        assert "element_type_id is null" in report

    def test_section_b_lists_blocking_children(self, make_snapshot: Any) -> None:
        """SRS-104a: an excluded parent names the children that blocked it."""
        result = GenerationResult(
            r210_warnings=[
                ValidationWarning(
                    "TypeDefinitions",
                    "td-2",
                    "SensorData",
                    "Not all non-rejected children are approved",
                    ("StructElements temperature is pending_review",),
                )
            ]
        )
        report = ReportBuilder().build(make_snapshot(), result, _config())
        assert "StructElements temperature is pending_review" in report

    def test_sections_c_to_f_list_by_status(self, make_snapshot: Any) -> None:
        """SRS-104(b)-(e): each review state gets its own section."""
        snapshot = make_snapshot(
            type_definitions=[
                type_definition(1, "PendingType", status=PENDING),
                type_definition(2, "AmbiguousType", status="ambiguous"),
                type_definition(3, "RejectedType", status=REJECTED),
                type_definition(4, "ScopedOut", status="out_of_scope"),
            ]
        )
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        for name in ("PendingType", "AmbiguousType", "RejectedType", "ScopedOut"):
            assert name in report

    def test_reviewable_children_appear_by_status(self, make_snapshot: Any) -> None:
        """SRS-035a: a pending child is visible, not merely implied."""
        snapshot = make_snapshot(
            type_definitions=[type_definition(2, "SensorData")],
            struct_elements=[struct_element(1, 2, "temperature", 1, status=PENDING)],
        )
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        assert "Struct Element: temperature" in report

    def test_parent_row_summarizes_child_statuses(self, make_snapshot: Any) -> None:
        """LLD-04 §7.3: every parent row summarizes its direct children."""
        snapshot = make_snapshot(
            type_definitions=[type_definition(2, "SensorData", status=PENDING)],
            struct_elements=[
                struct_element(1, 2, "approved", 1),
                struct_element(2, 2, "pending", 2, status=PENDING),
                struct_element(3, 2, "rejected", 3, status=REJECTED),
            ],
        )
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        parent_row = next(line for line in report.splitlines() if "SensorData" in line)
        assert "children=3 (approved=1, pending_review=1, rejected=1)" in parent_row

    def test_leaf_row_reports_zero_children(self, make_snapshot: Any) -> None:
        """LLD-04 §7.3: leaf artifacts carry an explicit empty summary."""
        snapshot = make_snapshot(
            type_definitions=[type_definition(1, "Leaf", status=PENDING)]
        )
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        leaf_row = next(line for line in report.splitlines() if "Leaf" in line)
        assert "children=0" in leaf_row

    def test_function_child_uses_its_domain_name(self, make_snapshot: Any) -> None:
        """LLD-04 §7.3: a function row includes its function_name."""
        snapshot = make_snapshot(
            port_prototypes=[port_prototype(1, "SensorPort")],
            port_prototype_functions=[function(1, 1, "ReadTemperature", status=PENDING)],
        )
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        assert "Port Prototype Function: ReadTemperature" in report

    @pytest.mark.parametrize(
        ("snapshot_rows", "parent_label"),
        [
            (
                {
                    "type_definitions": [type_definition(10, "Struct", status=PENDING)],
                    "struct_elements": [struct_element(1, 10, "field", 1)],
                },
                "Struct",
            ),
            (
                {
                    "port_interfaces": [port_interface(20, "Interface", status=PENDING)],
                    "interface_data_elements": [data_element(1, 20, "signal", 1)],
                },
                "Interface",
            ),
            (
                {
                    "client_server_operations": [
                        operation(30, 20, "Operation", 1, status=PENDING)
                    ],
                    "operation_arguments": [argument(1, 30, "value", 1)],
                },
                "Operation",
            ),
            (
                {
                    "port_prototypes": [port_prototype(40, "Prototype", status=PENDING)],
                    "port_prototype_functions": [function(1, 40)],
                },
                "Prototype",
            ),
            (
                {
                    "port_connections": [port_connection(50, "Connection", status=PENDING)],
                    "port_connection_members": [connection_member(1, 50, 40, 1)],
                },
                "Connection",
            ),
        ],
    )
    def test_each_parent_relationship_is_summarized(
        self, make_snapshot: Any, snapshot_rows: dict[str, list[Any]], parent_label: str
    ) -> None:
        """LLD-04 §7.3: every designed parent relation contributes to the count."""
        report = ReportBuilder().build(
            make_snapshot(**snapshot_rows), GenerationResult(), _config()
        )
        parent_row = next(line for line in report.splitlines() if parent_label in line)
        assert "children=1 (approved=1)" in parent_row

    def test_section_g_groups_by_issue_type_in_order(self, make_snapshot: Any) -> None:
        """LLD-04 §7.5: five issue types in a fixed group order."""
        snapshot = make_snapshot(
            review_issues=[
                review_issue(1, issue_type="out_of_scope"),
                review_issue(2, issue_type="incomplete"),
                review_issue(3, issue_type="ambiguous"),
            ]
        )
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        assert report.index("### incomplete") < report.index("### ambiguous")
        assert report.index("### ambiguous") < report.index("### out_of_scope")

    def test_section_h_lists_decided_issues(self, make_snapshot: Any) -> None:
        """SRS-104(g): resolved and rejected issues form the decision log."""
        snapshot = make_snapshot(
            review_issues=[
                review_issue(1, status="resolved", resolution="units are mV"),
                review_issue(2, status="rejected"),
                review_issue(3, status="pending"),
            ]
        )
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        log = report[report.index("## (h)") :]
        assert "units are mV" in log
        assert "## (h) Decision Log - 2" in report

    def test_source_reference_is_shown(self, make_snapshot: Any) -> None:
        """SRS-104: an artifact cites the requirement it came from."""
        snapshot = make_snapshot(
            source_requirements=[source_requirement(1, "REQ-042")],
            type_definitions=[
                type_definition(1, "SensorData", status=PENDING),
            ],
        )
        object.__setattr__(snapshot.type_definitions[0], "source_requirement_id", 1)
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        assert "source=REQ-042" in report

    def test_source_text_never_appears(self, make_snapshot: Any) -> None:
        """SRS-015a: the report cites references, never requirement text."""
        snapshot = make_snapshot(source_requirements=[source_requirement(1, "REQ-042")])
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        assert "synthetic requirement text" not in report


class TestTimestamp:
    """SRS-101 / DEV-46: the timestamp is injected, never read from a clock."""

    def test_omitted_when_not_supplied(self, make_snapshot: Any) -> None:
        """SRS-101: with no timestamp the header line is absent entirely."""
        report = ReportBuilder().build(make_snapshot(), GenerationResult(), _config())
        assert "Generated:" not in report

    def test_rendered_verbatim_when_supplied(self, make_snapshot: Any) -> None:
        """SRS-101: the injected value is used exactly as given."""
        report = ReportBuilder().build(
            make_snapshot(), GenerationResult(), _config(generated_at="2026-08-15T00:00:00+00:00")
        )
        assert "Generated: 2026-08-15T00:00:00+00:00" in report


class TestDeterminism:
    """SRS-101: identical input yields an identical report."""

    def test_two_builds_are_identical(self, make_snapshot: Any) -> None:
        """SRS-101: no clock, locale or dict ordering leaks into the output."""
        snapshot = make_snapshot(
            type_definitions=[
                type_definition(3, "zebra", status=PENDING),
                type_definition(1, "Alpha", status=PENDING),
                type_definition(2, "middle", status=PENDING),
            ],
            review_issues=[review_issue(1), review_issue(2, issue_type="ambiguous")],
        )
        builder = ReportBuilder()
        first = builder.build(snapshot, GenerationResult(), _config())
        second = builder.build(snapshot, GenerationResult(), _config())
        assert first == second

    def test_listing_order_is_alphabetical(self, make_snapshot: Any) -> None:
        """SRS-101: listings sort case-insensitively, not by insertion order."""
        snapshot = make_snapshot(
            type_definitions=[
                type_definition(3, "zebra", status=PENDING),
                type_definition(1, "Alpha", status=PENDING),
                type_definition(2, "middle", status=PENDING),
            ]
        )
        report = ReportBuilder().build(snapshot, GenerationResult(), _config())
        assert report.index("Alpha") < report.index("middle") < report.index("zebra")
