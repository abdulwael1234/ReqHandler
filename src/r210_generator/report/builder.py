"""Review report assembly.

SRS-104 requires the report to be producible independently of R210 generation
and "even when no approved artifacts exist", so `build` takes an optional
result and every section renders an explicit empty state rather than vanishing.

See: LLD-04 §7 (Review Report Builder)
"""

from ..models import DatabaseSnapshot, GenerationResult, GeneratorConfig
from .sections import (
    section_approved_excluded,
    section_approved_generated,
    section_artifacts_by_status,
    section_decision_log,
    section_fk_validation_errors,
    section_pending_issues,
)

# LLD-04 §7.1 sections (c)-(f): the four non-approved review states, in order.
STATUS_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("pending_review", "c", "Pending Review"),
    ("ambiguous", "d", "Ambiguous"),
    ("rejected", "e", "Rejected"),
    ("out_of_scope", "f", "Out of Scope"),
)


class ReportBuilder:
    """Assemble the review report in LLD-04 §7.1's fixed section order."""

    def build(
        self,
        snapshot: DatabaseSnapshot,
        result: GenerationResult,
        config: GeneratorConfig,
    ) -> str:
        """Render the complete report as one string.

        The header carries `generated_at` only when the caller supplied one.
        Reading the clock here would make two runs over an unchanged database
        differ and break SRS-101 (DEV-46).
        """
        lines: list[str] = ["# R210 Review Report", ""]
        if config.generated_at is not None:
            lines.extend([f"Generated: {config.generated_at}", ""])

        lines.extend(self._summary(snapshot, result))
        lines.extend(section_approved_generated(result.exported_artifacts))
        lines.extend(section_fk_validation_errors(result.r210_errors))
        lines.extend(section_approved_excluded(result.r210_warnings))
        for status, letter, title in STATUS_SECTIONS:
            lines.extend(section_artifacts_by_status(snapshot, status, letter, title))
        lines.extend(section_pending_issues(snapshot))
        lines.extend(section_decision_log(snapshot))
        return "\n".join(lines)

    @staticmethod
    def _summary(snapshot: DatabaseSnapshot, result: GenerationResult) -> list[str]:
        """A counts block, so the report opens with the state of the review."""
        artifacts = (
            len(snapshot.source_requirements)
            + len(snapshot.type_definitions)
            + len(snapshot.port_interfaces)
            + len(snapshot.port_prototypes)
            + len(snapshot.port_connections)
        )
        pending_issues = sum(1 for issue in snapshot.review_issues if issue.status == "pending")
        return [
            "## Summary",
            "",
            f"- artifacts: {artifacts}",
            f"- review issues: {len(snapshot.review_issues)} ({pending_issues} pending)",
            f"- R210 files generated: {len(result.r210_files)}",
            f"- excluded (children not approved): {len(result.r210_warnings)}",
            f"- excluded (unresolved references): {len(result.r210_errors)}",
            "",
        ]
