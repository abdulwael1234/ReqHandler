"""Review report content and structure (SRS-104, SRS-104a, SRS-101)."""

from typing import Any

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
    base_type,
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

    def test_section_a_lists_trees_when_nothing_rendered(self, make_snapshot: Any) -> None:
        """SRS-104: report_only still shows which trees would generate."""
        snapshot = make_snapshot(
            type_definitions=[base_type(1)], simple_type_definitions=[simple_detail(1, 1)]
        )
        result = GenerationResult(exportable_trees=evaluate_exportable_trees(snapshot).trees)
        report = ReportBuilder().build(snapshot, result, _config())
        assert "No R210 files were generated in this run" in report
        assert "Float32" in report

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
