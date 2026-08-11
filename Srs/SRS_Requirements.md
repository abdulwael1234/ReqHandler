# Software Requirements Specification

## R210 AUTOSAR Requirements Automation Prototype

| Field              | Value                                                    |
|--------------------|----------------------------------------------------------|
| **Document ID**    | R210-SRS-001                                             |
| **Version**        | 5.3                                                      |
| **Date**           | 2026-08-11                                               |
| **Source Document** | `Sytem_description/system_Description.md`               |
| **Status**         | Draft — Phase 1 implementation decisions incorporated    |

---

## Document Conventions

- Every requirement uses **shall** for mandatory behavior, **should** for recommended behavior, and **may** for optional behavior that the system is permitted but not required to provide.
- **TBD** marks information that must be completed before the requirement is implementable. Each TBD names an owner (who resolves it) and a closure condition (how to verify it is resolved).
- **Stakeholder decision** marks a design choice the SRS has made explicit but that is not directly stated in the source document. It requires stakeholder approval before implementation.
- Data-model table requirements group all fields of one database table into a single requirement for readability. Field-level constraints (CHECK values, nullability rules, uniqueness rules) are broken out as separate requirements to preserve test traceability.
- Source column references sections of `Sytem_description/system_Description.md`.

## Categories

| Code | Category      | Description                                                                 |
|------|---------------|-----------------------------------------------------------------------------|
| F    | Functional    | What the system does — processing, workflow, operations, validations        |
| D    | Data          | Data model — tables, fields, constraints, relationships, storage rules      |
| I    | Interface     | Interfaces between components, MCP tool surface, input/output contracts     |
| C    | Constraint    | Restrictions, prohibitions, limitations, assumptions, environment rules     |
| NF   | Non-Functional| Quality attributes — determinism, idempotency, safety, traceability        |

---

## Requirements

### Prototype Scope and Goals

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-001 | F | The system shall automate the handling of deterministic, generic AUTOSAR requirements for simple type definitions, array data types, structure data types, enumerations, port interfaces, port prototypes, and port connections. | §Prototype Goals |
| SRS-002 | F | The system shall identify information that is ambiguous, incomplete, unsupported, or out of scope and present it for manual review. | §Prototype Goals |
| SRS-003 | C | The system shall not invent missing information. | §Prototype Goals |
| SRS-004 | F | The system shall extract supported artifacts, store them in a structured form, support manual review of the extracted information, and generate R210 AUTOSAR-specific requirements. | §Prototype Scope |
| SRS-005 | F | Complex architectural changes (e.g., adding a new software component) shall be recorded as out of scope rather than silently discarded. | §Prototype Scope |
| SRS-006 | C | The system shall process only the artifact types listed in SRS-001. | §2 |

### User Need and Workflow

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-007 | F | The system shall automate the deterministic and repetitive parts of requirement decomposition while keeping ambiguous decisions under human control. | §1 |
| SRS-008 | F | Gemini CLI shall read the input requirements. | §3 |
| SRS-009 | F | Gemini, guided by the CLI skill, shall determine whether each requirement contains supported, ambiguous, incomplete, or out-of-scope information. | §3 |
| SRS-010 | F | Gemini shall use the MCP server to store structured extraction results and review issues in SQLite. | §3 |
| SRS-011 | F | The system shall allow a user to manually review extracted artifacts and unresolved issues. | §3 |
| SRS-012 | F | Approved artifacts shall be passed to the deterministic generator. | §3 |
| SRS-013 | F | The review report shall be generated from database content by deterministic Python logic. Gemini shall not independently compose the authoritative report. | §3 |

### Constraints, Assumptions, and Dependencies

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-014 | C | Gemini shall be the only LLM used in the system. Gemini CLI shall be the LLM interface. | §2 |
| SRS-015 | C | Work information and real work requirements shall not be transferred outside the work computer. The source document states this as an absolute constraint. **Stakeholder decision:** using Gemini (SRS-014) requires sending input requirement text to the Gemini API, which is an external transfer. This SRS cannot unilaterally authorize that transfer — it requires explicit security/stakeholder approval documenting what data categories may be sent and under what conditions. Until this approval is obtained, the system shall operate with synthetic data only. | §2 |
| SRS-015a | C | When the stakeholder decision in SRS-015 is approved, data sent to the Gemini API shall be limited to: (a) input requirement text needed for the current extraction operation, (b) MCP query results limited to the following fields: `unique_key`, `name`, `kind`, `interface_type`, `status`, `direction`, `source_reference` (for SourceRequirements, which has no `name` field), and `issue_type` (for ReviewIssues, needed for issue-awareness during extraction) — needed for duplicate checking, reference resolution, issue tracking, and determining record usability (per SRS-078), and (c) MCP tool-response metadata: returned `unique_key` values and duplicate-detection warning text. The system shall not send `source_text`, `description`, `review_note`, `resolution`, `component_reference`, `function_name`, generated outputs, or the review report to the Gemini API. MCP query tools shall enforce this boundary by returning only the permitted fields in their response payload when invoked during the Gemini extraction workflow. The Gemini CLI skill definition shall document the exact fields that enter the Gemini model context. | §2 (derived) |
| SRS-016 | C | Development outside the work environment shall use only synthetic requirements and test data. | §2 |
| SRS-017 | C | LLM usage should be minimized to reduce hallucinations and workflow variability. | §2 |
| SRS-018 | F | Manual review shall be the quality gate for the prototype. Only approved artifacts may be exported as final requirements. | §2 |
| SRS-019 | C | The following items are TBD — owner: development team; closure condition: each item is documented with concrete values and validated against real work data on the work computer. Items: (a) supported input formats, (b) source identifiers and their mapping to `source_reference`, (c) exact R210 output templates and file format, (d) file and artifact naming conventions, (e) source-input adapters. | §2, §9 |

### System Composition

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-020 | F | The system shall consist of: Gemini CLI skill, Python MCP server, SQLite database, deterministic generator/exporter, and database initializer. | §4 |
| SRS-021 | F | The Gemini CLI skill shall control the extraction workflow, use the MCP tools, and record ambiguous or unsupported input. | §4 |
| SRS-022 | I | The Python MCP server shall provide controlled operations for creating, updating, querying, and reviewing structured data. Gemini shall have no direct database access. | §4 |
| SRS-023 | D | The SQLite database shall store source requirement references, extracted artifacts, relationships, review states, and review issues. | §4 |
| SRS-024 | F | The deterministic generator/exporter shall validate approved database entries and create both the R210 AUTOSAR requirement files and the review report. | §4 |
| SRS-025 | F | The database initializer shall create and upgrade the database schema safely without deleting existing content. | §4 |

### Data Model — Common Conventions

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-026 | D | Each main record shall have an integer `id` as its local database primary key. | §5.1 |
| SRS-027 | D | Each externally referable record shall have a `unique_key` field, generated as a UUID and constrained to be unique. | §5.1 |
| SRS-028 | D | MCP requests and generated outputs shall refer to records by `unique_key` so that references remain stable outside the database. | §5.1 |
| SRS-029 | D | Internal database relationships shall use foreign keys to local database IDs. | §5.1 |
| SRS-030 | D | A missing optional relationship shall be stored as `NULL`, never as `0`. | §5.1 |
| SRS-031 | D | Repeated and child information shall be stored in child or association tables, not as serialized lists. | §5.1 |
| SRS-032 | D | Foreign-key enforcement shall be enabled in SQLite. | §5.1 |
| SRS-033 | D | UUIDs shall provide stable identity but shall not be used to detect semantically duplicated artifacts. | §5.1 |
| SRS-034 | F | Duplicate detection shall be manual in the prototype. The system may warn when two records share the same kind and the same name after case-insensitive whitespace-normalized comparison. Name normalization rule: trim leading/trailing whitespace, collapse internal whitespace to a single space, compare case-insensitively. | §5.1 |
| SRS-035 | D | The system shall support the following review states for artifacts, reviewable children, and `SourceRequirements` input records: `pending_review`, `approved`, `rejected`, `ambiguous`, `out_of_scope`. | §5.1 |
| SRS-035a | D | Every newly created artifact, reviewable child record, and `SourceRequirements` input record shall have initial status `pending_review`. `SourceRequirements` is a reviewable input record even though it is not an extracted artifact. The Gemini CLI skill may set `ambiguous` or `out_of_scope` at creation time when the input warrants it. Note: subtype detail tables (`SimpleTypeDefinitions`, `ArrayTypeDefinitions`) are structural extensions of their parent `TypeDefinitions` record, not independently reviewable children — they do not carry a `status` field. Reviewable children are: `StructElements`, `EnumValues`, `InterfaceDataElements`, `ClientServerOperations`, `OperationArguments`, `PortConnectionMembers`, `PortPrototypeFunctions`. | §5.1 (derived) |
| SRS-035b | D | The permitted state transitions for artifact, reviewable-child, and `SourceRequirements` status shall be: from `pending_review` to any state; from `ambiguous` to `pending_review`, `approved`, `rejected`, or `out_of_scope`; from `rejected` to `pending_review`; from `out_of_scope` to `pending_review`; from `approved` to `pending_review` or `rejected`. No other transitions shall be permitted. The permitted state transitions for review-issue status shall be: from `pending` to `resolved` or `rejected`; from `resolved` to `pending`; from `rejected` to `pending`. Initial review-issue status shall be `pending`. | §5.1 (derived) |
| SRS-035c | F | When a child record's status changes away from `approved` while its parent record is `approved`, the system shall automatically demote the parent's status to `pending_review` before completing the child status change. Both changes shall occur in a single transaction. This ensures the invariant in SRS-046/SRS-053 is never violated. | §5.3, §5.4 (derived) |
| SRS-036 | D | `PortPrototypes.port_interface_id` shall be stored as `NULL` while the referenced port interface has not yet been extracted. | §5.5 |
| SRS-036a | D | **Stakeholder decision:** whether other cross-artifact foreign keys (`element_type_id` in `ArrayTypeDefinitions` and `StructElements`; `type_definition_id` in `InterfaceDataElements` and `OperationArguments`) may also be stored as `NULL` while unresolved, or whether those references must be resolved at insertion time. Until this decision is made, the interim policy shall reject `NULL` values for these fields at both the schema and MCP tool boundaries. | §5.1 (derived) |
| SRS-037 | D | Every `position` field shall be NOT NULL and shall be unique within its parent record (enforced by a UNIQUE constraint on the combination of parent foreign key and `position`). This ensures deterministic ordering required by SRS-108. | §5.1 |
| SRS-038 | D | Child records (`StructElements`, `EnumValues`, `InterfaceDataElements`, `ClientServerOperations`, `OperationArguments`, `PortConnectionMembers`, `PortPrototypeFunctions`) do not carry their own `source_requirement_id`. Their source traceability is inherited through their parent record's `source_requirement_id`. | §5.2, §5.3, §5.4, §5.5, §5.6 |
| SRS-038a | D | Each `TypeDefinitions` record shall have exactly one corresponding row in its subtype detail table (`SimpleTypeDefinitions`, `ArrayTypeDefinitions`, or a set of `StructElements` or `EnumValues`). This shall be enforced at the MCP tool boundary: creation of a `TypeDefinitions` record shall require the subtype detail in the same operation. | §5.3 (derived) |
| SRS-038b | D | Every `position` value shall be a positive integer (≥ 1). Every `array_size` value shall be a positive integer (≥ 1). These shall be enforced by CHECK constraints. | §5.3, §5.6 (derived) |
| SRS-038c | D | Within a single `TypeDefinitions` record of kind `enum`, no two `EnumValues` rows shall share the same `name`. This shall be enforced by a UNIQUE constraint on (`enum_type_id`, `name`). The same rule applies to `StructElements` within a struct: UNIQUE on (`struct_type_id`, `name`). | §5.3 (derived) |

### Data Model — Source Requirements

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-039 | D | The `SourceRequirements` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `source_reference` (external document or requirement reference), `source_text` (source requirement text or NULL), `status` (review state), `review_note` (optional explanation). | §5.2 |
| SRS-040 | D | `source_text` shall be stored as `NULL` when the text cannot be retained in the work environment. | §5.2 |
| SRS-041 | D | Every extracted artifact and review issue shall refer to a source requirement via `source_requirement_id` when the source is known. When the source is not known, `source_requirement_id` shall be `NULL`. | §5.2 |

### Data Model — Type Definitions

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-042 | D | The `TypeDefinitions` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `name` (extracted from input), `kind`, `description` (extracted from input), `source_requirement_id` (nullable FK to `SourceRequirements`), `status` (review state), `review_note` (optional). | §5.3 |
| SRS-043 | D | `TypeDefinitions.kind` shall be constrained by CHECK to: `simple_typedef`, `array`, `struct`, or `enum`. | §5.3 |
| SRS-044 | D | Each subtype detail table shall only reference a `TypeDefinitions` parent whose `kind` matches: `SimpleTypeDefinitions` → `simple_typedef`, `ArrayTypeDefinitions` → `array`, `StructElements` → `struct`, `EnumValues` → `enum`. This shall be enforced by application-level validation at the MCP tool boundary. | §5.3 |
| SRS-045 | D | Enumerations shall be registered as a specialized type in `TypeDefinitions` so that all interface elements and operation arguments use one consistent type reference. | §5.3 |
| SRS-046 | F | If any non-rejected child record (structure element, enumeration value) has a review status other than `approved`, the parent `TypeDefinitions` record's status shall not be `approved`. Child records with status `rejected` are excluded from this evaluation — a parent whose only non-approved children are all `rejected` may be approved. The reviewer shall determine the specific parent status. **Stakeholder decision:** the source says "marked accordingly" without prescribing an automatic status-propagation rule. This rule is aligned with SRS-092a to prevent rejected children from permanently blocking parent approval when deletion is prohibited (SRS-091). | §5.3 |
| SRS-047 | D | The `SimpleTypeDefinitions` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `type_definition_id` (FK to `TypeDefinitions`), `base_type` (stated in input), `size` (optional, stated in input). | §5.3 |
| SRS-048 | D | The `ArrayTypeDefinitions` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `type_definition_id` (FK to `TypeDefinitions`), `element_type_id` (FK to `TypeDefinitions`), `array_size` (stated in input). | §5.3 |
| SRS-049 | D | The `StructElements` table shall contain one row per structure element with the fields: `id` (integer PK), `unique_key` (UUID), `struct_type_id` (FK to parent structure in `TypeDefinitions`), `name` (element name), `element_type_id` (FK to `TypeDefinitions`), `position` (per SRS-037), `description` (optional, from input), `status` (review state). | §5.3 |
| SRS-050 | D | The `EnumValues` table shall contain one row per enumeration value with the fields: `id` (integer PK), `unique_key` (UUID), `enum_type_id` (FK to parent enum in `TypeDefinitions`), `name` (value name), `value` (optional explicit value from input), `position` (per SRS-037), `description` (optional, from input), `status` (review state). | §5.3 |

### Data Model — Port Interfaces

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-051 | D | The `PortInterfaces` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `name` (extracted from input), `description` (extracted from input), `source_requirement_id` (nullable FK to `SourceRequirements`), `interface_type`, `status` (review state), `review_note` (optional). | §5.4 |
| SRS-052 | D | `PortInterfaces.interface_type` shall be constrained by CHECK to: `sender_receiver` or `client_server`. | §5.4 |
| SRS-053 | F | If any non-rejected child record (data element, operation, or operation argument) has a review status other than `approved`, the parent `PortInterfaces` record's status shall not be `approved`. Child records with status `rejected` are excluded from this evaluation, consistent with SRS-046 and SRS-092a. The reviewer shall determine the specific parent status. **Stakeholder decision:** same rationale as SRS-046. | §5.4 |
| SRS-054 | D | Sender-receiver data elements and client-server operations shall be stored in separate child tables. | §5.4 |
| SRS-055 | D | `InterfaceDataElements` rows shall only reference a `PortInterfaces` parent whose `interface_type` is `sender_receiver`. `ClientServerOperations` rows shall only reference a `PortInterfaces` parent whose `interface_type` is `client_server`. This shall be enforced by application-level validation at the MCP tool boundary. | §5.4 |
| SRS-056 | D | The `InterfaceDataElements` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `port_interface_id` (FK to `PortInterfaces`), `name` (element name), `type_definition_id` (FK to `TypeDefinitions`), `position` (per SRS-037), `description` (optional, from input), `status` (review state). | §5.4 |
| SRS-057 | D | The `ClientServerOperations` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `port_interface_id` (FK to `PortInterfaces`), `name` (operation name), `position` (per SRS-037), `description` (optional, from input), `status` (review state). | §5.4 |
| SRS-058 | D | The `OperationArguments` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `operation_id` (FK to `ClientServerOperations`), `name` (argument name), `type_definition_id` (FK to `TypeDefinitions`), `direction`, `position` (per SRS-037), `status` (review state). | §5.4 |
| SRS-059 | D | `OperationArguments.direction` shall be constrained to: `input`, `output`, or `input_output`. Note: the source document uses `input/output`; the database stores this as `input_output` (slash replaced with underscore to avoid ambiguity in serialized formats). | §5.4 |

### Data Model — Port Prototypes

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-060 | D | The `PortPrototypes` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `name` (extracted from input), `description` (extracted from input), `source_requirement_id` (nullable FK to `SourceRequirements`), `port_interface_id` (FK to `PortInterfaces`, `NULL` while the reference is unresolved — see SRS-036), `direction`, `component_reference` (component name or reference stated in input), `status` (review state), `review_note` (optional). | §5.5 |
| SRS-061 | D | `PortPrototypes.direction` shall be constrained to: `provider` or `requester`. | §5.5 |
| SRS-062 | D | The `PortPrototypeFunctions` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `port_prototype_id` (FK to `PortPrototypes`), `function_name` (referenced function name), `relationship_type`, `status` (review state). | §5.5 |
| SRS-063 | D | `PortPrototypeFunctions.relationship_type` shall be constrained to: `access_point` or `trigger`. | §5.5 |
| SRS-064 | F | During R210 output generation, `access_point` shall map to the AUTOSAR metamodel elements DataReadAccess, DataWriteAccess, or ServerCallPoint; `trigger` shall map to ExternalTriggeringPoint. TBD — owner: development team; closure condition: the complete selection rule (which inputs determine which specific metamodel element) is documented and validated against real AUTOSAR configurations on the work computer. | §5.5 |

### Data Model — Port Connections

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-065 | D | The `PortConnections` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `description` (extracted from input), `source_requirement_id` (nullable FK to `SourceRequirements`), `status` (review state), `review_note` (optional). | §5.6 |
| SRS-066 | D | The `PortConnectionMembers` table shall contain one row per connected port prototype with the fields: `id` (integer PK), `unique_key` (UUID), `port_connection_id` (FK to `PortConnections`), `port_prototype_id` (FK to `PortPrototypes`), `position` (per SRS-037), `status` (review state). | §5.6 |
| SRS-067 | D | A port connection shall represent one global logical connection containing all connected port prototypes. A connection may contain multiple provider ports and multiple requester ports. | §5.6 |
| SRS-068 | D | Provider/requester direction shall be defined only by each `PortPrototype`. Direction shall not be stored in `PortConnections` or `PortConnectionMembers`. | §5.6 |
| SRS-069 | F | Connection validation shall verify that every `port_prototype_id` referenced in `PortConnectionMembers` exists in `PortPrototypes`. | §5.6 |
| SRS-070 | F | Connection validation shall verify that a `port_prototype_id` is not repeated within the same `port_connection_id`. | §5.6 |
| SRS-071 | F | Connection validation shall verify that the port interfaces of all connected port prototypes are compatible. TBD — owner: development team; closure condition: compatibility rules are documented and validated against real work configurations on the work computer. | §5.6 |
| SRS-072 | F | Connection validation shall verify that the connection contains the required provider/requester directions, determined from the `direction` field of the referenced port prototypes. **Stakeholder decision:** the source says "required provider/requester directions" without specifying minimum cardinality. This SRS interprets this as at least one provider and at least one requester per connection. | §5.6 |
| SRS-073 | F | The deterministic generator shall preserve each connection as one global multi-port connection. It shall not automatically expand connections into pairwise provider/requester combinations. | §5.6 |

### Data Model — Review Issues

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-074 | D | The `ReviewIssues` table shall contain the fields: `id` (integer PK), `unique_key` (UUID), `source_requirement_id` (nullable FK to `SourceRequirements`), `artifact_type` (optional — identifies which table the affected artifact belongs to), `artifact_unique_key` (optional UUID of the affected artifact), `issue_type`, `message` (explanation based only on the input — not LLM-generated conclusions), `status`, `resolution` (optional user decision). When `artifact_unique_key` is set, `artifact_type` shall also be set. `artifact_type` shall be constrained to: `type_definition`, `struct_element`, `enum_value`, `port_interface`, `interface_data_element`, `client_server_operation`, `operation_argument`, `port_prototype`, `port_prototype_function`, `port_connection`, `port_connection_member`, or `NULL`. The pair (`artifact_type`, `artifact_unique_key`) is a typed polymorphic reference; it is not enforced by a foreign key because it spans multiple tables. Consumers shall resolve it by querying the table identified by `artifact_type` for the given `unique_key`. | §5.7 |
| SRS-075 | D | `ReviewIssues.issue_type` shall be constrained to: `ambiguous`, `incomplete`, `unresolved_reference`, `unsupported`, or `out_of_scope`. | §5.7 |
| SRS-076 | D | `ReviewIssues.status` shall be constrained to: `pending`, `resolved`, or `rejected`. | §5.7 |

### LLM Core and Gemini CLI Skill

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-077 | F | The Gemini CLI skill shall extract only information explicitly stated in the input. It shall not infer, assume, or generate names, types, sizes, relationships, or values. | §6 |
| SRS-078 | F | The Gemini CLI skill shall query existing records via MCP before creating new references to avoid duplicates. | §6 |
| SRS-079 | F | The Gemini CLI skill shall use stable UUIDs (`unique_key`) when referring to existing records. | §6 |
| SRS-080 | F | The Gemini CLI skill shall record missing or ambiguous information as a review issue with the appropriate `issue_type`. | §6 |
| SRS-081 | F | The Gemini CLI skill shall record unsupported complex requirements as review issues with `issue_type` = `out_of_scope`. | §6 |
| SRS-082 | C | The Gemini CLI skill shall not access the SQLite database directly. All database operations shall go through MCP tools. | §6 |
| SRS-082a | C | The Gemini CLI skill shall not set any artifact, reviewable child, or `SourceRequirements` input-record status to `approved`. Approval is reserved for manual review through the Local Review CLI (SRS-123) or direct MCP tool invocation by a human reviewer. The MCP server shall enforce this through the required `caller` parameter on `set_review_status`; when `caller` is `"extraction"`, transitions to `approved` shall be rejected. The Gemini CLI skill shall always pass `caller` = `"extraction"`. | §6 (derived) |
| SRS-082b | F | When any non-status field of an artifact, reviewable child, or `SourceRequirements` input record is changed through an update tool while the record's status is `approved`, the system shall automatically demote the record's status to `pending_review` within the same transaction. This ensures approved content is re-reviewed after modification. | §6 (derived) |

### Python MCP Server

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-083 | I | The MCP server shall validate all tool inputs before executing database operations. Invalid inputs shall be rejected with an error message identifying the invalid field and the reason. | §7 |
| SRS-084 | NF | The MCP server shall wrap each write operation in a database transaction. | §7 |
| SRS-085 | I | The MCP server shall provide operations to create, update, and query source requirements. | §7 |
| SRS-086 | I | The MCP server shall provide operations to create, update, and query supported artifacts and their child records. | §7 |
| SRS-087 | I | The MCP server shall provide operations to resolve references by UUID. | §7 |
| SRS-088 | I | The MCP server shall provide operations to create and query review issues. | §7 |
| SRS-089 | I | The MCP server shall provide operations to mark artifacts and issues with review states. | §7 |
| SRS-090 | I | The MCP server shall provide an operation to request deterministic output and report generation. | §7 |
| SRS-091 | C | Delete operations shall be excluded from the MCP tool surface. LLM-initiated deletion of records shall not be possible. | §7 |
| SRS-091a | C | The `status` field of any artifact, reviewable child, or `SourceRequirements` input record shall only be changeable through the `set_review_status` tool (or the automatic parent-demotion in SRS-035c, or the content-change demotion in SRS-082b). General-purpose update tools shall not accept `status` as an updatable field. `set_review_status` shall operate only on artifacts, reviewable children, and `SourceRequirements` — not on `ReviewIssues` (whose status is changed through `update_review_issue` per SRS-119) and not on structural subtype tables (`SimpleTypeDefinitions`, `ArrayTypeDefinitions`) which have no `status` field. When the target record's table has no `review_note` column, the `review_note` parameter shall be silently ignored rather than causing an error. | §7 (derived) |
| SRS-092 | C | Artifacts that are incorrect shall be marked as `rejected` rather than deleted. | §7 |
| SRS-092a | F | When evaluating parent-child approval for R210 export (SRS-104a), child records with status `rejected` shall be excluded from the evaluation. A parent with all non-rejected children `approved` and one or more children `rejected` is exportable — the rejected children are omitted from the generated output. This prevents an incorrectly extracted child from permanently blocking its parent. | §7 (derived) |
| SRS-093 | C | Destructive table-clearing operations and database reset operations shall not be exposed through the MCP tool surface. | §7 |

### Database Initialization

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-094 | F | The Python application shall provide a safe `init_db` operation outside the Gemini-facing MCP tools. | §8 |
| SRS-095 | F | `init_db` shall create the database file when it does not exist. | §8 |
| SRS-096 | F | On a new database or while applying a pending schema migration, `init_db` shall create the tables, constraints, and indexes required by that migration. When the recorded schema version is already current, `init_db` shall verify the expected tables and indexes and shall report detected schema damage without modifying or automatically repairing the damaged schema. Schema repair, if introduced later, shall be an explicit administrative operation rather than implicit `init_db` behavior. | §8 |
| SRS-097 | F | `init_db` shall record the database schema version. | §8 |
| SRS-098 | NF | `init_db` shall be idempotent — safe to call repeatedly with the same result. | §8 |
| SRS-099 | F | `init_db` shall preserve all existing data. | §8 |
| SRS-100 | C | A destructive database reset may be implemented as a development-only administrative command but shall be outside the Gemini workflow. | §8 |

### Deterministic Generation and Reporting

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-101 | NF | Given the same database content, generator version, and work configuration, the generator shall produce byte-identical output (determinism). For R210 files, the relevant input is the set of fully-approved artifact trees. For the review report, the relevant input is the complete database snapshot (all records, all statuses, all issues). | §9 |
| SRS-102 | F | The generator shall validate all approved records before generation. Records with unresolved foreign-key references (NULL values in mandatory FK fields) shall be reported as validation errors and excluded from the generated output. | §9 |
| SRS-103 | F | The generator shall generate R210 AUTOSAR-specific requirement files for the supported artifact types listed in SRS-001. | §9 |
| SRS-104 | F | The generator shall produce a review report directly from the database. The report shall be producible independently of R210 file generation — a report shall be generated even when no approved artifacts exist. The report shall include: (a) artifacts with status `approved` that were included in the generated output (empty when no R210 generation occurred), (b) artifacts with status `pending_review`, (c) artifacts with status `ambiguous`, (d) artifacts with status `rejected`, (e) artifacts with status `out_of_scope`, (f) review issues with status `pending` grouped by `issue_type` (covering `incomplete`, `unresolved_reference`, `unsupported`, and other issue types), (g) review issues with status `resolved` or `rejected` as a decision log. | §9 |
| SRS-104a | F | The generator shall only include a parent artifact and its non-rejected children in the R210 output when the parent and all of its non-rejected children have status `approved` (SRS-092a). Children with status `rejected` are excluded from evaluation. If the parent is `approved` but any non-rejected child is not `approved`, the parent and all its children shall be excluded from R210 output and reported as a validation warning in the review report. | §9 (derived) |

### Prototype Quality Requirements

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-105 | NF | The system shall validate inputs at the MCP tool boundary (per SRS-083) and at the generator boundary (per SRS-102). | §10 |
| SRS-106 | NF | All database write paths shall use transactions (per SRS-084). | §10 |
| SRS-107 | NF | The system shall maintain traceability from extracted artifacts back to source requirements when the source is known (per SRS-041). Child records inherit traceability through their parent (per SRS-038). | §10 |
| SRS-108 | NF | The system shall maintain deterministic ordering for all ordered records via `position` fields that are NOT NULL and unique within their parent (per SRS-037). Applies to: `StructElements`, `EnumValues`, `InterfaceDataElements`, `ClientServerOperations`, `OperationArguments`, and `PortConnectionMembers`. | §10 |
| SRS-109 | NF | The system shall report errors with: the operation that failed, the invalid field (for input validation errors), the reason for failure, and the identity (`unique_key`) of the affected record when applicable. | §10 |
| SRS-110 | C | The prototype shall not maintain an audit trail for review state transitions. A record's current `status` reflects the latest decision without history of prior states. | §10 |

### Review Workflow

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-118 | F | Manual review shall be performed through the MCP tool surface. The reviewer shall use query tools to inspect source inputs, artifacts, and issues, and `set_review_status` to record decisions for `SourceRequirements`, artifacts, and reviewable children. No direct database modification shall be required for review. | §3, §7 (derived) |
| SRS-119 | I | The MCP server shall provide an operation to update review issues, including setting the `resolution` field and changing the `status`. | §7 (derived) |
| SRS-120 | F | `TypeDefinitions.kind` shall not be changed after creation. To correct a wrongly classified type, the reviewer shall reject the incorrect record and the Gemini CLI skill (or a manual MCP operation) shall create a new record with the correct kind. | §5.3 (derived) |
| SRS-121 | F | The duplicate-detection warning described in SRS-034 shall be returned as part of the MCP create-operation response. If a potential duplicate is found, the system may additionally create a `ReviewIssue` with `issue_type` = `ambiguous` to ensure visibility during review. | §5.1 (derived) |
| SRS-122 | F | Any mutation to `PortConnectionMembers` (create or update) shall revalidate the complete connection — member existence (SRS-069), no duplicates (SRS-070), interface compatibility (SRS-071), and direction cardinality (SRS-072) — as a single transaction. Partial connection states that violate these rules shall not be persisted. | §5.6 (derived) |
| SRS-123 | F | The Python application shall provide a local review CLI outside the Gemini workflow. This CLI shall invoke the same MCP tools as the Gemini CLI skill but shall run without connecting to the Gemini API, ensuring that review decisions and database queries during review do not leave the work computer. The review CLI is a local Python program, not a network-facing service. | §3, §7 (derived) |
| SRS-124 | NF | Each `init_db` migration step and its corresponding schema-version update shall execute within a single database transaction. If any step fails, the transaction shall roll back, leaving the database at the last successfully applied version. | §8 (derived) |
| SRS-125 | F | Until the interface-compatibility rules required by SRS-071 are defined (TBD), the MCP server shall accept connections without compatibility validation but shall create a `ReviewIssue` with `issue_type` = `incomplete` and `message` indicating that compatibility has not been verified. This ensures connections are not silently treated as validated. | §5.6 (derived) |

### Scope Exclusions

The following capabilities are explicitly deferred from the prototype scope. They are recorded here to prevent silent omission and to support future planning.

| ID | Category | Requirement | Source |
|----|----------|-------------|--------|
| SRS-111 | C | The prototype shall not provide automated precision or coverage measurement of extraction results. | §10 |
| SRS-112 | C | The prototype shall not provide advanced semantic duplicate detection. Duplicate detection is limited to the name-matching warning described in SRS-034. | §10 |
| SRS-113 | C | The prototype shall not provide concurrency or large-volume performance optimization. | §10 |
| SRS-114 | C | The prototype shall not provide automatic retry or recovery policies. | §10 |
| SRS-115 | C | The prototype shall not provide backup or restore management. | §10 |
| SRS-116 | C | The prototype shall not provide multiple output formats. The single output format is defined in SRS-019 (TBD). | §10 |
| SRS-117 | C | The prototype shall not generate complex component or architecture requirements (per SRS-005). | §Prototype Scope, §10 |

---

## Stakeholder Decisions Register

The following requirements contain design decisions that are not directly stated in the source document and require stakeholder approval.

| Requirement | Decision Made | Rationale | Status |
|-------------|---------------|-----------|--------|
| SRS-015 | Authorization to transfer work requirement text to Gemini API | Source document prohibits external transfer absolutely. Using Gemini requires sending data to Google. This contradiction cannot be resolved by the SRS — it requires explicit security/stakeholder approval. | **BLOCKING — must be approved before real-data operation** |
| SRS-036a | NULL-while-unresolved for cross-artifact FKs other than `port_interface_id` | Source only defines NULL-while-unresolved explicitly for `PortPrototypes.port_interface_id`. Whether the four type-reference FKs follow the same pattern needs confirmation. SRS-036a defaults to rejecting NULL at both schema and MCP boundaries until decided. | Pending |
| SRS-046, SRS-053, SRS-092a | Parent status blocked from `approved` when any non-rejected child is not `approved`; rejected children excluded from approval and export evaluation; reviewer picks the specific parent status | Source says "marked accordingly" without prescribing an automatic propagation rule. v4.0 tightened to "other than approved". v5.0 added SRS-035c auto-demotion and SRS-092a rejected-child exclusion. v5.1 aligned SRS-046/053 with SRS-092a, resolving the contradiction where rejected children permanently blocked parent approval despite deletion being prohibited (SRS-091). | Pending — implementable as designed |
| SRS-072 | At least one provider and one requester per connection | Source says "required provider/requester directions" without defining minimum cardinality. | Pending — implementable as designed |

---

## Summary

| Category           | Count |
|--------------------|-------|
| Functional (F)     | 48    |
| Data (D)           | 49    |
| Interface (I)      | 9     |
| Constraint (C)     | 23    |
| Non-Functional (NF)| 9     |
| **Total**          | **138** |

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-10 | Initial extraction from system description. |
| 2.0     | 2026-08-10 | Post-review revision addressing 15 findings. See v2.0 notes. |
| 3.0     | 2026-08-10 | Post-second-review revision addressing 14 findings: added `may` to modality convention (SRS-034, SRS-067, SRS-100); rewrote parent-status propagation as reviewer-decided constraint, not automatic cascade (SRS-046, SRS-053); added subtype integrity enforcement for kind-matching (SRS-044) and interface-type-matching (SRS-055); clarified report predicates to separate artifact-status queries from review-issue-type queries (SRS-104); added position NOT NULL + UNIQUE-within-parent constraint (SRS-037); added child traceability inheritance rule (SRS-038); defined unresolved cross-artifact FK policy as stakeholder decision (SRS-036); removed "per port interface type" assumption from AUTOSAR mapping TBD (SRS-064); added owner and closure condition to all TBDs (SRS-064, SRS-071); changed MCP transactions to write operations only (SRS-084); added `input/output` → `input_output` serialization note (SRS-059); marked connection cardinality as stakeholder decision (SRS-072); consolidated duplicate no-pairwise-expansion requirement; documented polymorphic `artifact_unique_key` (SRS-074); added Stakeholder Decisions Register. |
| 4.0     | 2026-08-10 | Post-architecture-review revision. See v4.0 notes. |
| 5.0     | 2026-08-10 | Post-second-architecture-review revision addressing 16 findings. **Critical:** SRS-015 rewritten as blocking stakeholder decision — SRS cannot unilaterally authorize API transfer; system operates on synthetic data until approved. SRS-015a rewritten to acknowledge MCP query results (unique_keys, names, kinds) DO enter Gemini context for duplicate/reference resolution, with explicit allowlist requirement. **High:** SRS-035a clarified that SimpleTypeDefinitions/ArrayTypeDefinitions are structural extensions without status, not reviewable children — enumerated the 7 reviewable child types. Added SRS-035c for automatic parent-demotion when approved child changes status (single-transaction invariant). Added SRS-092a: rejected children excluded from parent export evaluation, preventing permanent parent blockage. Added SRS-091a: status only changeable via set_review_status, not general update tools. Added SRS-122: connection member mutations must revalidate the complete connection transactionally. Added SRS-123: local review CLI that invokes MCP tools without Gemini API. Added SRS-125: TBD compatibility (SRS-071) handled by creating ReviewIssue rather than silently accepting. **Medium:** SRS-035b extended with review-issue transitions (pending→resolved/rejected, reopenable). SRS-101 split determinism scope: R210 depends on approved trees, report depends on full DB snapshot. SRS-074 artifact_type expanded to include all 11 child/parent types. SRS-037 cross-reference corrected (SRS-096→SRS-108). Added SRS-124: migration transactions with rollback. Updated Stakeholder Decisions Register with status column and SRS-015 as BLOCKING. |
| 5.1     | 2026-08-10 | Post-LLD-review amendments. Added SRS-082a (Constraint): Gemini extraction skill cannot approve artifacts — MCP enforces via caller parameter. Added SRS-082b (Functional): content-change demotion — modifying approved records forces re-review. Amended SRS-015a: expanded allowlist to include `direction` field; added explicit exclusion list (`source_text`, `description`, `review_note`, `resolution`, `component_reference`, `function_name`); added MCP projection enforcement. Amended SRS-046 and SRS-053: changed "any child" to "any non-rejected child" for approval blocking, aligned with SRS-092a. Amended SRS-091a: scoped `set_review_status` to artifact/reviewable-child tables only; excludes ReviewIssues and structural subtypes. Updated summary counts to 138 (F:48, D:49, I:9, C:23, NF:9). Updated Stakeholder Decisions Register. |
| 5.2     | 2026-08-11 | Review-driven fixes. Amended SRS-104a: changed "all children" to "all non-rejected children" aligning with SRS-092a (L-05). Amended SRS-015a: added `source_reference` (for SourceRequirements) and `issue_type` (for ReviewIssues) to the permitted field allowlist (C-05). Fixed Stakeholder Decisions Register "v6.0" reference to "v5.1" (L-02). |
| 5.3     | 2026-08-11 | Incorporated approved Phase 1 implementation decisions. Amended SRS-035, SRS-035a, SRS-035b, SRS-082a, SRS-082b, SRS-091a, and SRS-118 to explicitly classify `SourceRequirements` as a reviewable input record with the same state, transition, approval-authority, and content-demotion rules as artifacts and reviewable children. Amended SRS-096 to distinguish schema creation during initialization/migration from report-only verification of an externally damaged current-version schema; any future repair is an explicit administrative operation. Corrected the four column names and interim enforcement wording in SRS-036a, and consolidated SRS-092a with its parent-child stakeholder decision. |
