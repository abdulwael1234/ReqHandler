"""Dataclass definitions for database records.

Mirrors the 16-table schema from LLD-01:
- SourceRequirements, TypeDefinitions, SimpleTypeDefinitions,
  ArrayTypeDefinitions, StructElements, EnumValues, PortInterfaces,
  InterfaceDataElements, ClientServerOperations, OperationArguments,
  PortPrototypes, PortPrototypeFunctions, PortConnections,
  PortConnectionMembers, ReviewIssues, schema_version

Field order in every record dataclass matches the column order of its table so
that a ``sqlite3.Row`` can be expanded positionally into the record.

See: LLD-02 §3 (Core Classes and Data Structures)
"""

from dataclasses import dataclass

# ─────────────────────────────────────────────────────────────────────────────
# Status constants (LLD-02 §3.4)
# ─────────────────────────────────────────────────────────────────────────────

# Artifact status values (SRS-035)
ARTIFACT_STATUSES = frozenset(
    {"pending_review", "approved", "rejected", "ambiguous", "out_of_scope"}
)

# Review issue status values (SRS-076)
ISSUE_STATUSES = frozenset({"pending", "resolved", "rejected"})

# Permitted artifact status transitions (SRS-035b)
ARTIFACT_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending_review": frozenset({"approved", "rejected", "ambiguous", "out_of_scope"}),
    "approved": frozenset({"pending_review", "rejected"}),
    "rejected": frozenset({"pending_review"}),
    "ambiguous": frozenset({"pending_review", "approved", "rejected", "out_of_scope"}),
    "out_of_scope": frozenset({"pending_review"}),
}

# Permitted review issue status transitions (SRS-035b)
ISSUE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"resolved", "rejected"}),
    "resolved": frozenset({"pending"}),
    "rejected": frozenset({"pending"}),
}


# ─────────────────────────────────────────────────────────────────────────────
# Record dataclasses (LLD-02 §3.3)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SchemaVersionRecord:
    version: int
    applied_at: str
    description: str | None


@dataclass(frozen=True)
class SourceRequirementRecord:
    id: int
    unique_key: str
    source_reference: str
    source_text: str | None
    status: str
    review_note: str | None


@dataclass(frozen=True)
class TypeDefinitionRecord:
    id: int
    unique_key: str
    name: str
    kind: str  # 'simple_typedef' | 'array' | 'struct' | 'enum'
    description: str | None
    source_requirement_id: int | None
    status: str
    review_note: str | None


@dataclass(frozen=True)
class SimpleTypeDefinitionRecord:
    id: int
    unique_key: str
    type_definition_id: int
    base_type: str
    size: str | None


@dataclass(frozen=True)
class ArrayTypeDefinitionRecord:
    id: int
    unique_key: str
    type_definition_id: int
    element_type_id: int
    array_size: int


@dataclass(frozen=True)
class StructElementRecord:
    id: int
    unique_key: str
    struct_type_id: int
    name: str
    element_type_id: int
    position: int
    description: str | None
    status: str


@dataclass(frozen=True)
class EnumValueRecord:
    id: int
    unique_key: str
    enum_type_id: int
    name: str
    value: str | None
    position: int
    description: str | None
    status: str


@dataclass(frozen=True)
class PortInterfaceRecord:
    id: int
    unique_key: str
    name: str
    description: str | None
    source_requirement_id: int | None
    interface_type: str  # 'sender_receiver' | 'client_server'
    status: str
    review_note: str | None


@dataclass(frozen=True)
class InterfaceDataElementRecord:
    id: int
    unique_key: str
    port_interface_id: int
    name: str
    type_definition_id: int
    position: int
    description: str | None
    status: str


@dataclass(frozen=True)
class ClientServerOperationRecord:
    id: int
    unique_key: str
    port_interface_id: int
    name: str
    position: int
    description: str | None
    status: str


@dataclass(frozen=True)
class OperationArgumentRecord:
    id: int
    unique_key: str
    operation_id: int
    name: str
    type_definition_id: int
    direction: str  # 'input' | 'output' | 'input_output'
    position: int
    status: str


@dataclass(frozen=True)
class PortPrototypeRecord:
    id: int
    unique_key: str
    name: str
    description: str | None
    source_requirement_id: int | None
    port_interface_id: int | None  # NULL while unresolved (SRS-036)
    direction: str  # 'provider' | 'requester'
    component_reference: str
    status: str
    review_note: str | None


@dataclass(frozen=True)
class PortPrototypeFunctionRecord:
    id: int
    unique_key: str
    port_prototype_id: int
    function_name: str
    relationship_type: str  # 'access_point' | 'trigger'
    status: str


@dataclass(frozen=True)
class PortConnectionRecord:
    id: int
    unique_key: str
    description: str | None
    source_requirement_id: int | None
    status: str
    review_note: str | None


@dataclass(frozen=True)
class PortConnectionMemberRecord:
    id: int
    unique_key: str
    port_connection_id: int
    port_prototype_id: int
    position: int
    status: str


@dataclass(frozen=True)
class ReviewIssueRecord:
    id: int
    unique_key: str
    source_requirement_id: int | None
    artifact_type: str | None
    artifact_unique_key: str | None
    issue_type: str
    message: str
    status: str
    resolution: str | None


# Table name → record dataclass. Lets the DAL map query results generically and
# keeps the model layer verifiable against the real schema.
TABLE_RECORD_MAP: dict[str, type] = {
    "schema_version": SchemaVersionRecord,
    "SourceRequirements": SourceRequirementRecord,
    "TypeDefinitions": TypeDefinitionRecord,
    "SimpleTypeDefinitions": SimpleTypeDefinitionRecord,
    "ArrayTypeDefinitions": ArrayTypeDefinitionRecord,
    "StructElements": StructElementRecord,
    "EnumValues": EnumValueRecord,
    "PortInterfaces": PortInterfaceRecord,
    "InterfaceDataElements": InterfaceDataElementRecord,
    "ClientServerOperations": ClientServerOperationRecord,
    "OperationArguments": OperationArgumentRecord,
    "PortPrototypes": PortPrototypeRecord,
    "PortPrototypeFunctions": PortPrototypeFunctionRecord,
    "PortConnections": PortConnectionRecord,
    "PortConnectionMembers": PortConnectionMemberRecord,
    "ReviewIssues": ReviewIssueRecord,
}


# ─────────────────────────────────────────────────────────────────────────────
# Table groupings (SRS-035a, SRS-091a)
# ─────────────────────────────────────────────────────────────────────────────

# Top-level records carrying both `status` and `review_note`. Together with
# REVIEWABLE_CHILD_TABLES these are the tables `set_review_status` may target
# (SRS-091a). SourceRequirements is included: it carries a review state even
# though it is an input record rather than an extracted artifact.
ARTIFACT_TABLES = frozenset(
    {
        "SourceRequirements",
        "TypeDefinitions",
        "PortInterfaces",
        "PortPrototypes",
        "PortConnections",
    }
)

# The seven reviewable child record types enumerated in SRS-035a.
REVIEWABLE_CHILD_TABLES = frozenset(
    {
        "StructElements",
        "EnumValues",
        "InterfaceDataElements",
        "ClientServerOperations",
        "OperationArguments",
        "PortConnectionMembers",
        "PortPrototypeFunctions",
    }
)

# Structural extensions of TypeDefinitions — not independently reviewable and
# therefore carrying no `status` column (SRS-035a).
STRUCTURAL_SUBTYPE_TABLES = frozenset({"SimpleTypeDefinitions", "ArrayTypeDefinitions"})


# ReviewIssues.artifact_type → the table that resolves artifact_unique_key.
# SRS-074 requires consumers to resolve the typed polymorphic reference by
# querying the table identified by artifact_type; this is that mapping.
ARTIFACT_TYPE_TABLE_MAP: dict[str, str] = {
    "type_definition": "TypeDefinitions",
    "struct_element": "StructElements",
    "enum_value": "EnumValues",
    "port_interface": "PortInterfaces",
    "interface_data_element": "InterfaceDataElements",
    "client_server_operation": "ClientServerOperations",
    "operation_argument": "OperationArguments",
    "port_prototype": "PortPrototypes",
    "port_prototype_function": "PortPrototypeFunctions",
    "port_connection": "PortConnections",
    "port_connection_member": "PortConnectionMembers",
}


# ─────────────────────────────────────────────────────────────────────────────
# Parent–child registry (LLD-02 §3.5)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ChildRelation:
    """A child table and the column by which it references its parent."""

    child_table: str
    fk_column: str


@dataclass(frozen=True)
class ParentRelation:
    """A parent table and the child column that references it."""

    parent_table: str
    fk_column: str


# Used by set_review_status for parent-approval blocking (SRS-046, SRS-053)
# and automatic parent demotion (SRS-035c).
PARENT_CHILD_MAP: dict[str, list[ChildRelation]] = {
    "TypeDefinitions": [
        ChildRelation(child_table="StructElements", fk_column="struct_type_id"),
        ChildRelation(child_table="EnumValues", fk_column="enum_type_id"),
    ],
    "PortInterfaces": [
        ChildRelation(child_table="InterfaceDataElements", fk_column="port_interface_id"),
        ChildRelation(child_table="ClientServerOperations", fk_column="port_interface_id"),
    ],
    "ClientServerOperations": [
        ChildRelation(child_table="OperationArguments", fk_column="operation_id"),
    ],
    "PortPrototypes": [
        ChildRelation(child_table="PortPrototypeFunctions", fk_column="port_prototype_id"),
    ],
    "PortConnections": [
        ChildRelation(child_table="PortConnectionMembers", fk_column="port_connection_id"),
    ],
}

# Reverse map: child table → (parent table, fk_column pointing to parent).
# OperationArguments → ClientServerOperations → PortInterfaces forms the
# grandparent chain that SRS-035c must walk in a single transaction.
CHILD_PARENT_MAP: dict[str, ParentRelation] = {
    "StructElements": ParentRelation(parent_table="TypeDefinitions", fk_column="struct_type_id"),
    "EnumValues": ParentRelation(parent_table="TypeDefinitions", fk_column="enum_type_id"),
    "InterfaceDataElements": ParentRelation(
        parent_table="PortInterfaces", fk_column="port_interface_id"
    ),
    "ClientServerOperations": ParentRelation(
        parent_table="PortInterfaces", fk_column="port_interface_id"
    ),
    "OperationArguments": ParentRelation(
        parent_table="ClientServerOperations", fk_column="operation_id"
    ),
    "PortPrototypeFunctions": ParentRelation(
        parent_table="PortPrototypes", fk_column="port_prototype_id"
    ),
    "PortConnectionMembers": ParentRelation(
        parent_table="PortConnections", fk_column="port_connection_id"
    ),
}
