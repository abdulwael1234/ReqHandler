"""Internal data structures for generation.

`DatabaseSnapshot` is the generator's whole view of the database: everything
downstream is a pure function over it, which is what lets the tree evaluation
and FK validation be tested without a database at all.

`GeneratorConfig` is the single carrier of every work-computer value. Its
defaults are the *unconfigured* policies, so a generator built without work
configuration is constructible and testable, and fails only at the point where
it would have to invent a template (SRS-019c, SRS-019d, SRS-064).

See: LLD-04 §9.1 (Database Snapshot), §10 (Generation Result)
"""

from dataclasses import dataclass, field
from typing import Any

from r210_mcp.db.models import (
    ArrayTypeDefinitionRecord,
    ClientServerOperationRecord,
    EnumValueRecord,
    InterfaceDataElementRecord,
    OperationArgumentRecord,
    PortConnectionMemberRecord,
    PortConnectionRecord,
    PortInterfaceRecord,
    PortPrototypeFunctionRecord,
    PortPrototypeRecord,
    ReviewIssueRecord,
    SimpleTypeDefinitionRecord,
    SourceRequirementRecord,
    StructElementRecord,
    TypeDefinitionRecord,
)

from .r210.templates import (
    UNCONFIGURED_ACCESS_POINTS,
    UNCONFIGURED_NAMING,
    UNCONFIGURED_TEMPLATES,
    AccessPointPolicy,
    NamingPolicy,
    TemplateSet,
)

# The three modes of SRS-090 / LLD-04 §3.2.
GENERATION_MODES = frozenset({"r210_only", "report_only", "both"})


@dataclass(frozen=True)
class DatabaseSnapshot:
    """Immutable snapshot of all database records (LLD-04 §9.1)."""

    source_requirements: tuple[SourceRequirementRecord, ...] = ()
    type_definitions: tuple[TypeDefinitionRecord, ...] = ()
    simple_type_definitions: tuple[SimpleTypeDefinitionRecord, ...] = ()
    array_type_definitions: tuple[ArrayTypeDefinitionRecord, ...] = ()
    struct_elements: tuple[StructElementRecord, ...] = ()
    enum_values: tuple[EnumValueRecord, ...] = ()
    port_interfaces: tuple[PortInterfaceRecord, ...] = ()
    interface_data_elements: tuple[InterfaceDataElementRecord, ...] = ()
    client_server_operations: tuple[ClientServerOperationRecord, ...] = ()
    operation_arguments: tuple[OperationArgumentRecord, ...] = ()
    port_prototypes: tuple[PortPrototypeRecord, ...] = ()
    port_prototype_functions: tuple[PortPrototypeFunctionRecord, ...] = ()
    port_connections: tuple[PortConnectionRecord, ...] = ()
    port_connection_members: tuple[PortConnectionMemberRecord, ...] = ()
    review_issues: tuple[ReviewIssueRecord, ...] = ()

    def type_definitions_by_id(self) -> dict[int, TypeDefinitionRecord]:
        """Index type definitions for reference resolution."""
        return {record.id: record for record in self.type_definitions}

    def port_prototypes_by_id(self) -> dict[int, PortPrototypeRecord]:
        """Index port prototypes for connection member resolution."""
        return {record.id: record for record in self.port_prototypes}

    def port_interfaces_by_id(self) -> dict[int, PortInterfaceRecord]:
        """Index port interfaces for prototype resolution."""
        return {record.id: record for record in self.port_interfaces}

    def source_reference_of(self, source_requirement_id: int | None) -> str | None:
        """The source reference behind an artifact, when it has one.

        Only the reference is exposed, never `source_text` — the report is a
        work-computer artifact but the projection discipline of SRS-015a is
        cheaper to keep than to reinstate.
        """
        if source_requirement_id is None:
            return None
        for record in self.source_requirements:
            if record.id == source_requirement_id:
                return record.source_reference
        return None


@dataclass(frozen=True)
class GeneratorConfig:
    """Everything the work computer supplies, plus the output location.

    Every work-specific field defaults to its unconfigured policy, so the
    generator is fully constructible in this repository copy and the report
    path works end to end. Only R210 rendering touches the missing values.
    """

    output_dir: str
    templates: TemplateSet = UNCONFIGURED_TEMPLATES
    naming: NamingPolicy = UNCONFIGURED_NAMING
    access_points: AccessPointPolicy = UNCONFIGURED_ACCESS_POINTS
    # Injected rather than read from the clock, so that two runs over an
    # unchanged database are byte-identical (SRS-101, DEV-46). When None the
    # report omits the timestamp line entirely.
    generated_at: str | None = None
    report_filename: str = "review_report.md"


@dataclass(frozen=True)
class ArtifactTree:
    """An approved parent with the children that will be exported.

    `excluded_children` are the rejected ones: excluded from evaluation and
    from the rendered output, but recorded so the report can say so (SRS-092a).
    """

    table: str
    record: Any
    active_children: tuple[tuple[str, Any], ...] = ()
    excluded_children: tuple[tuple[str, Any], ...] = ()

    @property
    def unique_key(self) -> str:
        return str(self.record.unique_key)

    @property
    def label(self) -> str:
        """`name` for most tables; `description` for PortConnections."""
        return str(getattr(self.record, "name", None) or self.record.description or "")


@dataclass(frozen=True)
class ValidationWarning:
    """An approved parent held back by a non-approved child (SRS-104a)."""

    table: str
    unique_key: str
    label: str
    reason: str
    blocking_children: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationError:
    """An artifact excluded from R210 output by an unresolved FK (SRS-102)."""

    table: str
    unique_key: str
    label: str
    reason: str


@dataclass(frozen=True)
class ExportedArtifact:
    """One artifact that reached the R210 output."""

    table: str
    unique_key: str
    label: str
    path: str


@dataclass(frozen=True)
class R210File:
    """A rendered file, before it is written."""

    path: str
    content: str


@dataclass
class ExportableSet:
    """Trees that passed §4 evaluation, and the parents that did not."""

    trees: list[ArtifactTree] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)


@dataclass
class ValidatedSet:
    """Trees that also passed §5 FK validation, and those that did not."""

    trees: list[ArtifactTree] = field(default_factory=list)
    errors: list[ValidationError] = field(default_factory=list)


@dataclass
class GenerationResult:
    """Output of the generator (LLD-04 §10)."""

    r210_files: list[R210File] = field(default_factory=list)
    report_file: str | None = None
    r210_warnings: list[ValidationWarning] = field(default_factory=list)
    r210_errors: list[ValidationError] = field(default_factory=list)
    exported_artifacts: list[ExportedArtifact] = field(default_factory=list)
    # Unmet Phase 5 entry criteria, when R210 rendering was requested but the
    # work configuration is absent. Empty in every other case.
    unconfigured: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.r210_errors and not self.unconfigured

    def summary(self) -> dict[str, Any]:
        """The dict `trigger_generation` returns to its caller (SRS-090)."""
        return {
            "r210_files_generated": len(self.r210_files),
            "report_generated": self.report_file is not None,
            "report_file": self.report_file,
            "warnings": len(self.r210_warnings),
            "errors": len(self.r210_errors),
            "exported_artifacts": len(self.exported_artifacts),
        }
