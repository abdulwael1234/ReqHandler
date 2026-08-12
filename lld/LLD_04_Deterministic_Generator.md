# Low-Level Design — Deterministic Generator/Exporter

## R210 AUTOSAR Requirements Automation Prototype

| Field              | Value                                                    |
|--------------------|----------------------------------------------------------|
| **Document ID**    | R210-LLD-04                                              |
| **Version**        | 1.3                                                      |
| **Date**           | 2026-08-12                                               |
| **Component**      | Deterministic Generator / Exporter                       |
| **Source Documents**| R210-SRS-001 v5.4, R210-HLD-001 v3.4, R210-LLD-01 v1.1 |
| **Status**         | Draft                                                    |

---

## 1. Purpose

This document specifies the internal design of the Deterministic Generator/Exporter — the component that validates approved database content and produces R210 AUTOSAR-specific requirement files and a review report. This component is entirely deterministic: given the same inputs, it produces byte-identical output.

---

## 2. Module Structure

```
r210_generator/
├── __init__.py
├── generator.py               # Main generator orchestrator
├── loader.py                  # Database query layer (loads all records)
├── validator.py               # Pre-generation validation
├── r210/
│   ├── __init__.py
│   ├── renderer.py            # R210 template application
│   ├── templates/             # R210 output templates (TBD — SRS-019c)
│   │   ├── type_definition.py
│   │   ├── port_interface.py
│   │   ├── port_prototype.py
│   │   └── port_connection.py
│   └── file_writer.py         # Deterministic file output
├── report/
│   ├── __init__.py
│   ├── builder.py             # Review report assembly
│   └── sections.py            # Individual report sections
└── models.py                  # Internal data structures for generation
```

---

## 3. Generator Orchestrator (`generator.py`)

### 3.1 Entry Point

```python
class Generator:
    """Main deterministic generator. Produces R210 files and/or review report."""

    def __init__(self, db_path: str, output_dir: str, config: GeneratorConfig):
        self._db_path = db_path
        self._output_dir = output_dir
        self._config = config  # TBD: templates, naming, AUTOSAR package paths

    def generate(self, mode: str) -> GenerationResult:
        """
        Main generation entry point.

        Args:
            mode: "r210_only", "report_only", or "both"

        Returns:
            GenerationResult with file paths, counts, errors, and warnings.
        """
```

### 3.2 Generation Modes (SRS-090, SRS-104)

| Mode | Behavior | Precondition |
|------|----------|-------------|
| `r210_only` | Generate R210 requirement files only | ≥ 1 fully-approved artifact |
| `report_only` | Generate review report only | None — always succeeds (SRS-104) |
| `both` | Generate both R210 files and review report | ≥ 1 fully-approved artifact for R210 portion |

### 3.3 Processing Pipeline

```python
def generate(self, mode: str) -> GenerationResult:
    """
    Pipeline:
    1. Load all records from database (inside BEGIN for snapshot consistency)
    2. Evaluate parent-child exportable trees (§4) — always, because the
       review report Section (b) needs this even in report_only mode
    3. If mode includes R210:
       a. Validate FK completeness (§5)
       b. Render R210 files for valid artifacts (§6)
    4. If mode includes report:
       a. Build review report from all records (§7)
    5. Write files deterministically (§8)
    6. Return result
    """
    snapshot = self._loader.load_all(self._db_path)

    result = GenerationResult()

    # Always evaluate exportable trees — report Section (b) needs
    # the "approved but excluded" warnings even in report_only mode.
    exportable = self._evaluate_exportable_trees(snapshot)
    result.r210_warnings = exportable.warnings

    if mode in ("r210_only", "both"):
        validated = self._validate_fk_completeness(exportable)
        r210_files = self._render_r210(validated)
        result.r210_files = r210_files
        result.r210_errors = validated.errors
        result.exported_artifacts = validated.artifacts()

    if mode in ("report_only", "both"):
        report_file = self._build_report(snapshot, result)
        result.report_file = report_file

    self._write_files(result)
    return result
```

---

## 4. Parent–Child Tree Evaluation (SRS-104a, SRS-092a)

### 4.1 Exportable Tree Definition

An artifact tree is exportable when:
1. The parent record has `status = "approved"`.
2. All non-rejected children have `status = "approved"` (SRS-092a).
3. Children with `status = "rejected"` are excluded from evaluation AND from the generated output.

### 4.2 Evaluation Algorithm

```python
def _evaluate_exportable_trees(self, snapshot: DatabaseSnapshot) -> ExportableSet:
    """
    For each parent table:
      1. Select records where status = 'approved'
      2. For each approved parent:
         a. Get all children
         b. Partition children into: rejected, non-rejected
         c. Check all non-rejected children are 'approved'
         d. If yes → parent + non-rejected children are exportable
         e. If no → parent excluded; record as validation warning
      3. Collect exportable artifacts and warnings
    """
    exportable = ExportableSet()

    for parent in snapshot.approved_parents():
        children = snapshot.get_children(parent)
        rejected = [c for c in children if c.status == "rejected"]
        active = [c for c in children if c.status != "rejected"]
        non_approved = [c for c in active if c.status != "approved"]

        if non_approved:
            # Parent excluded — not all active children are approved
            exportable.add_warning(ValidationWarning(
                parent=parent,
                reason="Not all non-rejected children are approved",
                blocking_children=non_approved,
            ))
        else:
            # Parent + active children are exportable
            exportable.add(parent, active_children=active, excluded_children=rejected)

    return exportable
```

### 4.3 Parent Tables and Their Children

| Parent Table | Child Table(s) | Grandchild Table(s) |
|-------------|----------------|---------------------|
| TypeDefinitions (kind=struct) | StructElements | — |
| TypeDefinitions (kind=enum) | EnumValues | — |
| TypeDefinitions (kind=simple_typedef) | — (SimpleTypeDefinitions is structural, not reviewable) | — |
| TypeDefinitions (kind=array) | — (ArrayTypeDefinitions is structural, not reviewable) | — |
| PortInterfaces (sender_receiver) | InterfaceDataElements | — |
| PortInterfaces (client_server) | ClientServerOperations | OperationArguments |
| PortPrototypes | PortPrototypeFunctions | — |
| PortConnections | PortConnectionMembers | — |

**Grandchild handling:** For `PortInterfaces` of type `client_server`, the evaluation is recursive:
1. Check `ClientServerOperations` children are approved.
2. For each approved operation, check `OperationArguments` children are approved.
3. If any argument is not approved (and not rejected), the operation fails, and the parent interface fails.

---

## 5. Foreign Key Validation (SRS-102)

### 5.1 Validation Rules

Before generating R210 output for an artifact, validate all references required
for export are resolved. The four SRS-036a type references are nullable during
extraction but mandatory at this boundary:

| Artifact Type | Mandatory FK Fields to Validate |
|---------------|--------------------------------|
| ArrayTypeDefinitions | `element_type_id` resolved (non-NULL); target exists |
| StructElements | `element_type_id` resolved (non-NULL); target exists |
| InterfaceDataElements | `type_definition_id` resolved (non-NULL); target exists |
| OperationArguments | `type_definition_id` resolved (non-NULL); target exists |
| PortPrototypes | `port_interface_id` NOT NULL; target exists |
| PortConnectionMembers | `port_prototype_id` NOT NULL; target exists |

### 5.2 Validation Algorithm

```python
def _validate_fk_completeness(self, exportable: ExportableSet) -> ValidatedSet:
    """
    For each exportable artifact:
      1. Check all mandatory FK fields are non-NULL
      2. Check all FK targets exist in the database
      3. If any FK is NULL or target missing:
         a. Exclude artifact from R210 output
         b. Record as validation error
      4. Return validated set
    """
    validated = ValidatedSet()

    for artifact in exportable.artifacts():
        fk_errors = self._check_fk_references(artifact)
        if fk_errors:
            validated.add_error(artifact, fk_errors)
        else:
            validated.add(artifact)

    return validated
```

---

## 6. R210 File Rendering (SRS-103)

### 6.1 Template Architecture

Each supported artifact type has a dedicated template module. Templates are Python functions (not Jinja or external template engines) to ensure determinism and zero external dependencies.

```python
# r210/templates/type_definition.py
def render_simple_typedef(typedef: TypeDefinitionRecord,
                           detail: SimpleTypeDefinitionRecord,
                           config: GeneratorConfig) -> str:
    """Render R210 requirement text for a simple type definition."""

def render_array_type(typedef: TypeDefinitionRecord,
                       detail: ArrayTypeDefinitionRecord,
                       element_type: TypeDefinitionRecord,
                       config: GeneratorConfig) -> str:
    """Render R210 requirement text for an array type definition."""

def render_struct_type(typedef: TypeDefinitionRecord,
                        elements: list[StructElementRecord],
                        element_types: dict[int, TypeDefinitionRecord],
                        config: GeneratorConfig) -> str:
    """Render R210 requirement text for a structure type definition."""

def render_enum_type(typedef: TypeDefinitionRecord,
                      values: list[EnumValueRecord],
                      config: GeneratorConfig) -> str:
    """Render R210 requirement text for an enumeration type definition."""
```

**TBD (SRS-019c, SRS-019d):** The exact template content, file format, naming conventions, and AUTOSAR package paths are determined on the work computer. This LLD defines the template interface; the template implementations are TBD.

### 6.2 Rendering Pipeline

```python
def _render_r210(self, validated: ValidatedSet) -> list[R210File]:
    """
    For each validated artifact:
      1. Determine artifact type
      2. Load complete artifact data (parent + children + referenced types)
      3. Apply the appropriate template
      4. Determine output file path per naming conventions (TBD)
      5. Collect rendered content
    """
    files = []
    for artifact in sorted(validated.artifacts(),
                            key=lambda a: (a.type_sort_key,
                                           (a.sort_field or "").lower(),
                                           a.id)):
        content = self._apply_template(artifact)
        file_path = self._determine_file_path(artifact)
        files.append(R210File(path=file_path, content=content))
    return files

    # sort_field is `name` for most artifact types;
    # `description` for PortConnections (which has no name column).
    # See §6.3 Sort Field table above.
```

### 6.3 Artifact Ordering (SRS-101 — determinism)

Artifacts in the R210 output are sorted by:
1. **Primary:** Artifact type sort key (defined below).
2. **Secondary:** Sort field (alphabetical, case-insensitive) — see table below.
3. **Tertiary:** `id` (as tiebreaker for truly identical sort-field values).

**Note:** Most artifact tables use `name` as the secondary sort field.
`PortConnections` has no `name` column; it uses `description` instead (see LLD-01 §4.13).

| Artifact Type | Sort Key | Sort Field |
|--------------|----------|------------|
| Simple Type Definition | 1 | `name` |
| Array Data Type | 2 | `name` |
| Structure Data Type | 3 | `name` |
| Enumeration | 4 | `name` |
| Sender-Receiver Port Interface | 5 | `name` |
| Client-Server Port Interface | 6 | `name` |
| Port Prototype | 7 | `name` |
| Port Connection | 8 | `description` |

### 6.4 Child Record Ordering (SRS-108)

Within each artifact, child records are ordered by `position` (ascending). If two children have the same position (should not happen due to UNIQUE constraint), order by `id`.

```python
def sort_children(children: list[ChildRecord]) -> list[ChildRecord]:
    return sorted(children, key=lambda c: (c.position, c.id))
```

### 6.5 Rejected Child Exclusion (SRS-092a)

When rendering an exportable artifact, rejected children are omitted from the output:

```python
def get_active_children(children: list[ChildRecord]) -> list[ChildRecord]:
    """Exclude rejected children from rendered output."""
    return [c for c in children if c.status != "rejected"]
```

### 6.6 Port Connection Rendering (SRS-073)

Port connections are rendered as global multi-port connections. The generator does NOT expand them into pairwise provider/requester combinations.

```python
def render_port_connection(connection: PortConnectionRecord,
                            members: list[PortConnectionMemberRecord],
                            prototypes: dict[int, PortPrototypeRecord],
                            config: GeneratorConfig) -> str:
    """Render one global multi-port connection.
    All members are listed within a single connection block.
    No pairwise expansion."""
```

### 6.7 AUTOSAR Metamodel Mapping (SRS-064)

```python
# TBD — exact mapping rules determined on work computer
RELATIONSHIP_TYPE_MAP = {
    "access_point": {
        # TBD: selection rule for DataReadAccess vs DataWriteAccess vs ServerCallPoint
        # Depends on port direction and interface type
    },
    "trigger": "ExternalTriggeringPoint",
}
```

---

## 7. Review Report Builder (SRS-104)

### 7.1 Report Structure

The review report contains the following sections in fixed order:

| Section | Label | Content | Source |
|---------|-------|---------|--------|
| (a) | Approved & Generated | Artifacts included in R210 output | SRS-104(a) |
| (b) | Approved but Excluded | Approved parents excluded due to non-approved children | SRS-104a (validation warnings) |
| (c) | Pending Review | Artifacts with status `pending_review` | SRS-104(b) |
| (d) | Ambiguous | Artifacts with status `ambiguous` | SRS-104(c) |
| (e) | Rejected | Artifacts with status `rejected` | SRS-104(d) |
| (f) | Out of Scope | Artifacts with status `out_of_scope` | SRS-104(e) |
| (g) | Pending Issues | Review issues with `status = "pending"`, grouped by `issue_type` | SRS-104(f) |
| (h) | Decision Log | Review issues with `status` = `"resolved"` or `"rejected"` | SRS-104(g) |

### 7.2 Report Builder Algorithm

```python
class ReportBuilder:
    def build(self, snapshot: DatabaseSnapshot,
              generation_result: Optional[R210Result]) -> str:
        """
        Build the complete review report.
        The report is always producible — even when no R210 generation occurred.
        """
        sections = []

        # Section (a): Approved & Generated
        if generation_result and generation_result.r210_files:
            sections.append(self._section_approved_generated(
                generation_result.exported_artifacts
            ))
        else:
            sections.append(self._section_approved_generated_empty())

        # Section (a2): FK Validation Errors
        if generation_result and generation_result.r210_errors:
            sections.append(self._section_fk_validation_errors(
                generation_result.r210_errors
            ))

        # Section (b): Approved but Excluded (validation warnings)
        sections.append(self._section_approved_excluded(
            generation_result.r210_warnings if generation_result else []
        ))

        # Sections (c)–(f): Artifacts by status
        for status, label in [
            ("pending_review", "Pending Review"),
            ("ambiguous", "Ambiguous"),
            ("rejected", "Rejected"),
            ("out_of_scope", "Out of Scope"),
        ]:
            sections.append(self._section_artifacts_by_status(
                snapshot, status, label
            ))

        # Section (g): Pending issues grouped by issue_type
        sections.append(self._section_pending_issues(snapshot))

        # Section (h): Decision log
        sections.append(self._section_decision_log(snapshot))

        return self._assemble(sections)
```

### 7.3 Artifact Listing in Report

Each artifact in the report includes:

| Field | Description |
|-------|-------------|
| `unique_key` | Stable identifier |
| `type` | Artifact type (e.g., "Type Definition (struct)") |
| `name` | Artifact name |
| `status` | Current status |
| `source_reference` | Linked source requirement reference (if known) |
| `children_summary` | Count and status summary of children |

### 7.4 Issue Listing in Report

Each review issue includes:

| Field | Description |
|-------|-------------|
| `unique_key` | Issue identifier |
| `issue_type` | Issue classification |
| `message` | Explanation |
| `status` | Current issue status |
| `artifact_reference` | Linked artifact (type + key) if applicable |
| `source_reference` | Linked source requirement reference |
| `resolution` | Resolution text (for resolved/rejected issues) |

### 7.5 Issue Grouping (Section g)

Pending issues are grouped by `issue_type` in this fixed order:

1. `incomplete` — information missing from input
2. `unresolved_reference` — references that could not be resolved
3. `ambiguous` — multiple interpretations possible
4. `unsupported` — features not supported by prototype
5. `out_of_scope` — complex requirements beyond prototype scope

Within each group, issues are sorted by `source_reference` (if available), then by `id`.

---

## 8. Deterministic File Output (SRS-101)

### 8.1 File Writing Rules

| Rule | Value | Rationale |
|------|-------|-----------|
| Encoding | UTF-8 without BOM | Cross-platform consistency |
| Line endings | LF (`\n`) | Unix-style; avoids CRLF/LF inconsistency |
| Trailing newline | Single `\n` at end of file | POSIX convention |
| File ordering | Sorted by artifact type, then name | Deterministic file creation order |
| Directory creation | Create output directories before writing | Ensure paths exist |

### 8.2 File Writer Implementation

```python
class DeterministicFileWriter:
    """Write files with strict determinism guarantees."""

    def __init__(self, output_dir: str):
        self._output_dir = output_dir

    def write_file(self, relative_path: str, content: str) -> str:
        """Write content to file with deterministic encoding and line endings.

        Returns absolute path of written file.
        """
        # Normalize line endings to LF
        content = content.replace('\r\n', '\n').replace('\r', '\n')

        # Ensure trailing newline
        if not content.endswith('\n'):
            content += '\n'

        full_path = os.path.join(self._output_dir, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)

        with open(full_path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)

        return full_path
```

**Note:** `newline=''` prevents Python from adding platform-specific line endings. The content already has LF line endings.

---

## 9. Data Loading (`loader.py`)

### 9.1 Database Snapshot

The loader creates an immutable snapshot of all database records for the generator:

```python
@dataclass(frozen=True)
class DatabaseSnapshot:
    """Immutable snapshot of all database records."""
    source_requirements: list[SourceRequirementRecord]
    type_definitions: list[TypeDefinitionRecord]
    simple_type_definitions: list[SimpleTypeDefinitionRecord]
    array_type_definitions: list[ArrayTypeDefinitionRecord]
    struct_elements: list[StructElementRecord]
    enum_values: list[EnumValueRecord]
    port_interfaces: list[PortInterfaceRecord]
    interface_data_elements: list[InterfaceDataElementRecord]
    client_server_operations: list[ClientServerOperationRecord]
    operation_arguments: list[OperationArgumentRecord]
    port_prototypes: list[PortPrototypeRecord]
    port_prototype_functions: list[PortPrototypeFunctionRecord]
    port_connections: list[PortConnectionRecord]
    port_connection_members: list[PortConnectionMemberRecord]
    review_issues: list[ReviewIssueRecord]
```

### 9.2 Loading Strategy

```python
class Loader:
    """Load complete database state for generation."""

    def load_all(self, db_path: str) -> DatabaseSnapshot:
        """
        Load all records from all tables.
        Each table loaded with ORDER BY position, id (where applicable).
        Uses a single read-only connection with BEGIN to guarantee
        snapshot consistency — all SELECTs see the same database state
        even if another process writes between queries.
        """
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")  # snapshot isolation

        try:
            return DatabaseSnapshot(
                source_requirements=self._load_table(conn, "SourceRequirements",
                                                      order="id"),
                type_definitions=self._load_table(conn, "TypeDefinitions",
                                                   order="kind, name COLLATE NOCASE, id"),
                # ... all other tables with deterministic ordering ...
            )
        finally:
            conn.rollback()  # read-only — no changes to commit
            conn.close()
```

**Deterministic ordering:** All queries use explicit `ORDER BY` clauses. No reliance on insertion order or `dict` iteration order.

---

## 10. Generation Result

```python
@dataclass
class GenerationResult:
    """Output of the generator."""
    r210_files: list[R210File] = field(default_factory=list)
    report_file: Optional[str] = None
    r210_warnings: list[ValidationWarning] = field(default_factory=list)
    r210_errors: list[ValidationError] = field(default_factory=list)
    exported_artifacts: list[ExportedArtifact] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.r210_errors) == 0

    def summary(self) -> dict:
        return {
            "r210_files_generated": len(self.r210_files),
            "report_generated": self.report_file is not None,
            "warnings": len(self.r210_warnings),
            "errors": len(self.r210_errors),
            "exported_artifacts": len(self.exported_artifacts),
        }
```

---

## 11. TBD Items Affecting This Component

| TBD | Impact | SRS Reference |
|-----|--------|---------------|
| R210 output templates | Template content not yet defined | SRS-019(c) |
| File naming conventions | Output file paths not yet defined | SRS-019(d) |
| AUTOSAR package paths | Package structure in templates | SRS-019 |
| AUTOSAR metamodel mapping for access_point/trigger | Selection rule for DataReadAccess/WriteAccess/ServerCallPoint | SRS-064 |
| Interface compatibility rules | Validation logic for connection interface compatibility | SRS-071 |

**Note:** These TBDs do not block the design of the generator's architecture. Template implementations are pluggable — the generator framework is ready for any template content.

---

## 12. Traceability Matrix (LLD-04 → SRS)

| LLD Section | SRS Requirements |
|-------------|-----------------|
| §3 Orchestrator | SRS-024, SRS-090, SRS-104 |
| §4 Tree Evaluation | SRS-104a, SRS-092a, SRS-046, SRS-053 |
| §5 FK Validation | SRS-102 |
| §6.1–6.2 Template Architecture | SRS-103, SRS-019 |
| §6.3 Artifact Ordering | SRS-101, SRS-108 |
| §6.4 Child Ordering | SRS-108, SRS-037 |
| §6.5 Rejected Exclusion | SRS-092a |
| §6.6 Connection Rendering | SRS-073, SRS-067 |
| §6.7 AUTOSAR Mapping | SRS-064 |
| §7 Report Builder | SRS-104, SRS-013 |
| §8 File Output | SRS-101 |
| §9 Data Loading | SRS-101 (snapshot consistency) |
| §10 Generation Result | SRS-090 (result reporting) |

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-10 | Initial LLD derived from SRS v5.0, HLD v3.0, and LLD-01 v1.0. |
| 1.1     | 2026-08-10 | Post-review amendments: Moved exportable-tree evaluation before mode check so report_only mode populates Section (b) warnings. Fixed PortConnections sort key from `name` (nonexistent) to `description`. Added `BEGIN` transaction to loader for snapshot consistency. Added `sort_field` column to artifact ordering table. |
| 1.2     | 2026-08-11 | Review-driven fixes: Assigned `exported_artifacts` in pipeline (H-05). Fixed nullable sort_field crash with `(a.sort_field or "").lower()` (H-06). Added Section (a2) FK validation errors to report builder (M-06). Updated source references to SRS v5.2, HLD v3.1. |
| 1.3     | 2026-08-12 | Aligned with approved SRS-036a and LLD-01 v1.1: nullable type references remain mandatory at the generator boundary, so unresolved records are excluded and reported. Work-specific templates, paths, mappings, and metamodel information remain deferred to the work machine. |
