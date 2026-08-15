"""The individual review report sections.

Each builder is a pure function returning the section's lines. Keeping them
separate from the assembly in `builder.py` is what makes the fixed section
order of LLD-04 §7.1 checkable on its own.

Every listing is explicitly sorted. Nothing here reads a clock, a locale or a
dict's insertion order, which is what lets SRS-101 hold for the report.

See: LLD-04 §7 (Review Report Builder)
"""

from typing import Any

from ..models import (
    ArtifactTree,
    DatabaseSnapshot,
    ExportedArtifact,
    ValidationError,
    ValidationWarning,
)

# LLD-04 §7.5: pending issues group by issue_type in this fixed order.
ISSUE_TYPE_ORDER: tuple[str, ...] = (
    "incomplete",
    "unresolved_reference",
    "ambiguous",
    "unsupported",
    "out_of_scope",
)

# The artifact tables the status sections (c)-(f) scan, and how each is titled.
ARTIFACT_SOURCES: tuple[tuple[str, str], ...] = (
    ("source_requirements", "Source Requirement"),
    ("type_definitions", "Type Definition"),
    ("port_interfaces", "Port Interface"),
    ("port_prototypes", "Port Prototype"),
    ("port_connections", "Port Connection"),
)

# Reviewable children (SRS-035a), scanned alongside their parents so a pending
# child is visible in the report rather than only implied by its parent's row.
CHILD_SOURCES: tuple[tuple[str, str], ...] = (
    ("struct_elements", "Struct Element"),
    ("enum_values", "Enum Value"),
    ("interface_data_elements", "Interface Data Element"),
    ("client_server_operations", "Client-Server Operation"),
    ("operation_arguments", "Operation Argument"),
    ("port_prototype_functions", "Port Prototype Function"),
    ("port_connection_members", "Port Connection Member"),
)


def _label(record: Any) -> str:
    """`name` for most records; `description` for PortConnections."""
    return str(getattr(record, "name", None) or getattr(record, "description", None) or "")


def _type_title(table_label: str, record: Any) -> str:
    """A human artifact type, e.g. 'Type Definition (struct)'."""
    kind = getattr(record, "kind", None) or getattr(record, "interface_type", None)
    return f"{table_label} ({kind})" if kind else table_label


def _heading(letter: str, title: str, count: int) -> list[str]:
    """A section heading carrying its own count, so an empty one still reads."""
    return [f"## ({letter}) {title} - {count}", ""]


def _artifact_line(type_title: str, record: Any, source_reference: str | None) -> str:
    """One artifact row (LLD-04 §7.3)."""
    parts = [f"- `{record.unique_key}` {type_title}: {_label(record)}", f"status={record.status}"]
    if source_reference:
        parts.append(f"source={source_reference}")
    return "  ".join(parts)


def section_approved_generated(
    exported: list[ExportedArtifact], trees: list[ArtifactTree]
) -> list[str]:
    """(a) Artifacts included in the R210 output (SRS-104(a)).

    When no R210 generation ran, the exportable trees are still listed: they
    are what *would* be generated, which is the reviewer's actual question.
    """
    lines = _heading("a", "Approved and Generated", len(exported))
    if exported:
        for item in sorted(exported, key=lambda a: (a.table, a.label.lower(), a.unique_key)):
            lines.append(f"- `{item.unique_key}` {item.table}: {item.label}  file={item.path}")
        return [*lines, ""]

    if trees:
        lines.append("No R210 files were generated in this run. Fully approved trees:")
        lines.append("")
        for tree in sorted(trees, key=lambda t: (t.table, t.label.lower(), t.unique_key)):
            lines.append(f"- `{tree.unique_key}` {tree.table}: {tree.label}")
    else:
        lines.append("No artifacts were approved and generated.")
    return [*lines, ""]


def section_fk_validation_errors(errors: list[ValidationError]) -> list[str]:
    """(a2) Approved artifacts excluded by unresolved references (SRS-102)."""
    lines = _heading("a2", "Excluded - Unresolved References", len(errors))
    if not errors:
        lines.append("No approved artifact was excluded for an unresolved reference.")
        return [*lines, ""]
    for error in sorted(errors, key=lambda e: (e.table, e.label.lower(), e.unique_key)):
        lines.append(f"- `{error.unique_key}` {error.table}: {error.label}")
        lines.append(f"  - {error.reason}")
    return [*lines, ""]


def section_approved_excluded(warnings: list[ValidationWarning]) -> list[str]:
    """(b) Approved parents held back by non-approved children (SRS-104a)."""
    lines = _heading("b", "Approved but Excluded", len(warnings))
    if not warnings:
        lines.append("No approved artifact was excluded.")
        return [*lines, ""]
    for warning in sorted(warnings, key=lambda w: (w.table, w.label.lower(), w.unique_key)):
        lines.append(f"- `{warning.unique_key}` {warning.table}: {warning.label}")
        lines.append(f"  - {warning.reason}")
        for blocker in sorted(warning.blocking_children):
            lines.append(f"    - {blocker}")
    return [*lines, ""]


def section_artifacts_by_status(
    snapshot: DatabaseSnapshot, status: str, letter: str, title: str
) -> list[str]:
    """(c)-(f) Every artifact and reviewable child in one review state."""
    rows: list[tuple[str, str, Any]] = []
    for attribute, table_label in ARTIFACT_SOURCES + CHILD_SOURCES:
        for record in getattr(snapshot, attribute):
            if record.status == status:
                rows.append((table_label, _label(record), record))

    lines = _heading(letter, title, len(rows))
    if not rows:
        lines.append(f"No artifacts are {status}.")
        return [*lines, ""]

    for table_label, label, record in sorted(rows, key=lambda r: (r[0], r[1].lower(), r[2].id)):
        lines.append(
            _artifact_line(
                _type_title(table_label, record),
                record,
                snapshot.source_reference_of(getattr(record, "source_requirement_id", None)),
            )
        )
    return [*lines, ""]


def _issue_line(snapshot: DatabaseSnapshot, issue: Any) -> list[str]:
    """One issue row (LLD-04 §7.4)."""
    lines = [f"- `{issue.unique_key}` {issue.issue_type}: {issue.message}"]
    if issue.artifact_type and issue.artifact_unique_key:
        lines.append(f"  - artifact: {issue.artifact_type} `{issue.artifact_unique_key}`")
    reference = snapshot.source_reference_of(issue.source_requirement_id)
    if reference:
        lines.append(f"  - source: {reference}")
    if issue.resolution:
        lines.append(f"  - resolution: {issue.resolution}")
    return lines


def section_pending_issues(snapshot: DatabaseSnapshot) -> list[str]:
    """(g) Pending issues grouped by issue_type (SRS-104(f), LLD-04 §7.5)."""
    pending = [issue for issue in snapshot.review_issues if issue.status == "pending"]
    lines = _heading("g", "Pending Issues", len(pending))
    if not pending:
        lines.append("No issues are pending.")
        return [*lines, ""]

    for issue_type in ISSUE_TYPE_ORDER:
        group = [issue for issue in pending if issue.issue_type == issue_type]
        if not group:
            continue
        lines.append(f"### {issue_type} - {len(group)}")
        lines.append("")
        # §7.5: within a group, by source_reference then id. A missing
        # reference sorts last rather than crashing the comparison.
        for issue in sorted(
            group,
            key=lambda i: (snapshot.source_reference_of(i.source_requirement_id) or "~", i.id),
        ):
            lines.extend(_issue_line(snapshot, issue))
        lines.append("")
    return lines


def section_decision_log(snapshot: DatabaseSnapshot) -> list[str]:
    """(h) Resolved and rejected issues (SRS-104(g))."""
    decided = [
        issue for issue in snapshot.review_issues if issue.status in ("resolved", "rejected")
    ]
    lines = _heading("h", "Decision Log", len(decided))
    if not decided:
        lines.append("No issues have been resolved or rejected.")
        return [*lines, ""]
    for issue in sorted(decided, key=lambda i: (i.status, i.issue_type, i.id)):
        lines.append(f"- [{issue.status}] `{issue.unique_key}` {issue.issue_type}: {issue.message}")
        if issue.resolution:
            lines.append(f"  - resolution: {issue.resolution}")
    return [*lines, ""]
