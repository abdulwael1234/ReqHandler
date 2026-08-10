# About This Document

## Purpose

This document provides an informal system description for the first stage of requirements engineering. It defines the prototype scope, main components, data model, and processing workflow. A formal Software Requirements Specification (SRS) will be produced in a later stage.

## Prototype Goals

The prototype shall automate the handling of deterministic, generic AUTOSAR requirements for:

1. Simple type definitions
2. Array data types
3. Structure data types
4. Enumerations
5. Port interfaces
6. Port prototypes
7. Port connections

The system shall identify information that is ambiguous, incomplete, unsupported, or out of scope and present it for manual review. It shall not invent missing information.

## Prototype Scope

The prototype focuses on extracting supported artifacts, storing them in a structured form, reviewing the extracted information manually, and generating R210 AUTOSAR-specific requirements.

Complex architectural changes, such as adding a new software component, are outside the prototype scope. Such requirements shall be recorded as out of scope rather than silently discarded.

Advanced operational capabilities, including performance optimization, concurrent processing, automatic recovery, backup management, and automated quality measurement, are future enhancements.

# System Description

## 1. User Need

Requirements are received from other teams and systems and must be decomposed into R210 AUTOSAR-specific requirements. This work is currently performed manually. The prototype shall automate the deterministic and repetitive parts while keeping ambiguous decisions under human control.

## 2. Constraints, Assumptions, and Dependencies

- Gemini is the only LLM approved for use in the work environment. Gemini CLI is therefore the LLM interface for the prototype.
- Work information and real work requirements cannot be transferred outside the work computer.
- Development outside the work environment shall use only synthetic requirements and test data.
- The supported input formats, source identifiers, and exact R210 output format shall be completed and validated on the work computer.
- LLM usage should be minimized to reduce hallucinations and workflow variability.
- Manual review is the quality gate for the prototype. Only approved artifacts may be exported as final requirements.
- The prototype processes only the artifact types listed in the prototype goals.

## 3. Processing Workflow

The prototype workflow is:

1. Gemini CLI reads the input requirements.
2. Gemini, guided by the CLI skill, determines whether each requirement contains supported, ambiguous, incomplete, or out-of-scope information.
3. Gemini uses the MCP server to store structured extraction results and review issues in SQLite.
4. A user manually reviews extracted artifacts and unresolved issues.
5. Approved artifacts are passed to the deterministic generator.
6. The generator creates the R210 AUTOSAR requirement files and a review report.

The review report shall be generated from database content by deterministic Python logic. Gemini may request report generation through MCP, but Gemini shall not independently compose the authoritative report.

## 4. System Composition

The system consists of:

1. **Gemini CLI skill**: Controls the extraction workflow, uses the MCP tools, and records ambiguous or unsupported input.
2. **Python MCP server**: Provides controlled operations for creating, updating, querying, and reviewing structured data. Gemini has no direct database access.
3. **SQLite database**: Stores source requirement references, extracted artifacts, relationships, review states, and review issues.
4. **Deterministic generator/exporter**: Validates approved database entries and creates both the R210 AUTOSAR requirement files and the review report.
5. **Database initializer**: Creates and upgrades the database schema safely without deleting existing content.

## 5. Data Model

### 5.1 Common Conventions

- Each main record has an integer `id` as its local database primary key.
- Each externally referable record has a `unique_key`, generated as a UUID and constrained to be unique.
- MCP requests and generated outputs refer to records by `unique_key` so that references remain stable outside the database.
- Internal database relationships use foreign keys to local database IDs.
- A missing optional relationship is stored as `NULL`, never as `0`.
- Repeated and child information is stored in child or association tables, not as serialized lists.
- Foreign-key enforcement shall be enabled in SQLite.
- UUIDs provide stable identity but do not detect semantically duplicated artifacts. Duplicate detection is manual in the prototype, with an optional warning for records of the same kind and normalized name.

The initial review states are:

- `pending_review`
- `approved`
- `rejected`
- `ambiguous`
- `out_of_scope`

### 5.2 Source Requirements

The `SourceRequirements` table records the origin of every extraction decision. Its exact input mapping will be completed on the work computer.

Initial fields:

- `id`: integer primary key
- `unique_key`: UUID
- `source_reference`: external document or requirement reference
- `source_text`: source requirement text when permitted in the work environment; stored as `NULL` when the text cannot be retained
- `status`: review state
- `review_note`: optional explanation or decision

Every extracted artifact and review issue shall refer to a source requirement when the source is known.

### 5.3 Type Definitions

All supported data types are registered in the `TypeDefinitions` table. Enumerations are registered as a specialized type so that all interface elements and operation arguments can use one consistent type reference.

`TypeDefinitions` fields:

- `id`: integer primary key
- `unique_key`: UUID
- `name`: name extracted from the input requirement
- `kind`: `simple_typedef`, `array`, `struct`, or `enum` (enforced by CHECK constraint)
- `description`: description extracted from the input requirement
- `source_requirement_id`: nullable foreign key to `SourceRequirements`
- `status`: review state
- `review_note`: optional reviewer explanation or decision

If any child record (structure element, enumeration value) is ambiguous or problematic, the parent `TypeDefinitions` record shall also be marked accordingly.

Type-specific information is stored as follows:

#### Simple Type Definitions

The `SimpleTypeDefinitions` table contains:

- `id`: integer primary key
- `unique_key`: UUID
- `type_definition_id`: foreign key to `TypeDefinitions`
- `base_type`: base type stated in the input requirement
- `size`: optional size stated in the input requirement

#### Array Type Definitions

The `ArrayTypeDefinitions` table contains:

- `id`: integer primary key
- `unique_key`: UUID
- `type_definition_id`: foreign key to `TypeDefinitions`
- `element_type_id`: foreign key to the referenced `TypeDefinitions` record
- `array_size`: array size stated in the input requirement

#### Structure Elements

The `StructElements` table contains one row for each structure element:

- `id`: integer primary key
- `unique_key`: UUID
- `struct_type_id`: foreign key to the parent structure in `TypeDefinitions`
- `name`: element name
- `element_type_id`: foreign key to the referenced `TypeDefinitions` record
- `position`: deterministic element order
- `description`: optional description from the input requirement
- `status`: review state

#### Enumeration Values

The `EnumValues` table contains one row for each enumeration value:

- `id`: integer primary key
- `unique_key`: UUID
- `enum_type_id`: foreign key to the parent enumeration in `TypeDefinitions`
- `name`: enumeration value name
- `value`: optional explicit value from the input requirement
- `position`: deterministic value order
- `description`: optional description from the input requirement
- `status`: review state

### 5.4 Port Interfaces

The `PortInterfaces` table contains:

- `id`: integer primary key
- `unique_key`: UUID
- `name`: name extracted from the input requirement
- `description`: description extracted from the input requirement
- `source_requirement_id`: nullable foreign key to `SourceRequirements`
- `interface_type`: `sender_receiver` or `client_server` (enforced by CHECK constraint)
- `status`: review state
- `review_note`: optional reviewer explanation or decision

If any child record (data element, operation, or argument) is ambiguous or problematic, the parent `PortInterfaces` record shall also be marked accordingly.

Sender-receiver data elements and client-server operations are stored in separate child tables.

#### Sender-Receiver Data Elements

The `InterfaceDataElements` table contains:

- `id`: integer primary key
- `unique_key`: UUID
- `port_interface_id`: foreign key to `PortInterfaces`
- `name`: data element name
- `type_definition_id`: foreign key to `TypeDefinitions`
- `position`: deterministic element order
- `description`: optional description from the input requirement
- `status`: review state

#### Client-Server Operations

The `ClientServerOperations` table contains:

- `id`: integer primary key
- `unique_key`: UUID
- `port_interface_id`: foreign key to `PortInterfaces`
- `name`: operation name
- `position`: deterministic operation order
- `description`: optional description from the input requirement
- `status`: review state

Operation arguments are stored in the `OperationArguments` table:

- `id`: integer primary key
- `unique_key`: UUID
- `operation_id`: foreign key to `ClientServerOperations`
- `name`: argument name
- `type_definition_id`: foreign key to `TypeDefinitions`
- `direction`: input, output, or input/output, as supported by the final work configuration
- `position`: deterministic argument order
- `status`: review state

### 5.5 Port Prototypes

The `PortPrototypes` table contains:

- `id`: integer primary key
- `unique_key`: UUID
- `name`: name extracted from the input requirement
- `description`: description extracted from the input requirement
- `source_requirement_id`: nullable foreign key to `SourceRequirements`
- `port_interface_id`: foreign key to `PortInterfaces`; it is `NULL` while the reference is unresolved
- `direction`: `provider` or `requester`
- `component_reference`: component name or reference stated in the input requirement
- `status`: review state
- `review_note`: optional reviewer explanation or decision

Access points and triggers are stored as child records in `PortPrototypeFunctions`. The `relationship_type` values simplify the AUTOSAR metamodel, where access points map to DataReadAccess, DataWriteAccess, or ServerCallPoint, and triggers map to ExternalTriggeringPoint.

- `id`: integer primary key
- `unique_key`: UUID
- `port_prototype_id`: foreign key to `PortPrototypes`
- `function_name`: referenced function name
- `relationship_type`: `access_point` or `trigger`
- `status`: review state

### 5.6 Port Connections

A port connection is one global logical connection containing all connected port prototypes. A connection may contain multiple provider ports and multiple requester ports.

Provider/requester direction is defined only by each `PortPrototype`. It is not duplicated in the connection or its membership records.

The `PortConnections` table contains:

- `id`: integer primary key
- `unique_key`: UUID
- `description`: description extracted from the input requirement
- `source_requirement_id`: nullable foreign key to `SourceRequirements`
- `status`: review state
- `review_note`: optional reviewer explanation or decision

The `PortConnectionMembers` table contains one row for each connected port prototype:

- `id`: integer primary key
- `unique_key`: UUID
- `port_connection_id`: foreign key to `PortConnections`
- `port_prototype_id`: foreign key to `PortPrototypes`
- `position`: deterministic member order
- `status`: review state

Connection validation shall verify that:

- Every referenced port prototype exists.
- A port prototype is not repeated within the same connection.
- The connected port interfaces are compatible according to the supported work configuration.
- The connection contains the required provider/requester directions, determined from the referenced port prototypes.

The deterministic generator shall preserve the connection as one global multi-port connection. It shall not expand it automatically into provider/requester pairs.

### 5.7 Review Issues

The `ReviewIssues` table stores information that Gemini cannot resolve without human input:

- `id`: integer primary key
- `unique_key`: UUID
- `source_requirement_id`: nullable foreign key to `SourceRequirements`
- `artifact_unique_key`: optional UUID of the affected artifact
- `issue_type`: ambiguous, incomplete, unresolved reference, unsupported, or out of scope
- `message`: explanation based only on the input
- `status`: pending, resolved, or rejected
- `resolution`: optional user decision

## 6. LLM Core and Gemini CLI Skill

Gemini processes human-readable input and converts supported information into structured MCP operations. It is the nondeterministic part of the system.

The Gemini CLI skill shall:

- Extract only information explicitly supported by the input.
- Query existing records before creating references.
- Use stable UUIDs when referring to existing records.
- Record missing or ambiguous information as a review issue.
- Record unsupported complex requirements as out of scope.
- Avoid inventing names, types, sizes, relationships, or values.
- Avoid direct access to the SQLite database.

## 7. Python MCP Server

The MCP server is the controlled interface between Gemini and the database. It shall validate tool inputs and use database transactions.

The prototype MCP surface includes operations to:

- Create, update, and query source requirements.
- Create, update, and query supported artifacts and their child records.
- Resolve references by UUID.
- Create and query review issues.
- Mark artifacts and issues with review states.
- Request deterministic output and report generation.

Delete operations are intentionally excluded from the MCP surface to prevent LLM-initiated data loss. Artifacts that are incorrect shall be marked as `rejected` rather than deleted.

Destructive table-clearing operations and database reset operations shall not be exposed to Gemini.

## 8. Database Initialization

The Python application shall provide a safe `init_db` operation outside the Gemini-facing MCP tools. It shall:

- Create the database when it does not exist.
- Create missing tables, constraints, and indexes.
- Record the database schema version.
- Be safe to call repeatedly.
- Preserve all existing data.

A destructive database reset may be implemented as a development-only administrative command, but it is outside the Gemini workflow.

## 9. Deterministic Generation and Reporting

Requirement extraction is nondeterministic because Gemini interprets human-written input. Generation is deterministic after review: the same approved database content, generator version, and work configuration shall produce the same output.

The deterministic generator/exporter shall:

- Validate approved records before generation.
- Reject or report unresolved references rather than inventing values.
- Generate R210 AUTOSAR-specific requirement files for the supported artifact types.
- Preserve each global port connection as one multi-port connection.
- Generate an authoritative review report directly from the database.

The report shall include:

- Approved and generated artifacts
- Items pending review
- Ambiguous or incomplete requirements
- Unresolved references
- Rejected items
- Out-of-scope requirements

The exact R210 templates, file format, naming conventions, and source input adapters shall be completed on the work computer.

## 10. Prototype Limitations and Future Enhancements

The initial prototype relies on manual review and does not require automated extraction-quality metrics. The following capabilities are deferred:

- Automated precision and coverage measurement
- Advanced semantic duplicate detection
- Concurrency and large-volume performance optimization
- Automatic retry and recovery policies
- Backup and restore management
- Multiple output formats
- Complex component and architecture generation

The prototype does not maintain an audit trail for review state transitions. A record's current `status` reflects the latest decision without history of prior states.

Basic validation, transaction safety, traceability, deterministic ordering, and clear error reporting remain required for the prototype.
