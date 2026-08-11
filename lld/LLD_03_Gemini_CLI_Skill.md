# Low-Level Design — Gemini CLI Skill

## R210 AUTOSAR Requirements Automation Prototype

| Field              | Value                                                    |
|--------------------|----------------------------------------------------------|
| **Document ID**    | R210-LLD-03                                              |
| **Version**        | 1.2                                                      |
| **Date**           | 2026-08-11                                               |
| **Component**      | Gemini CLI Skill                                         |
| **Source Documents**| R210-SRS-001 v5.2, R210-HLD-001 v3.1                   |
| **Status**         | Draft                                                    |

---

## 1. Purpose

This document specifies the internal design of the Gemini CLI Skill — the LLM-driven extraction component that reads input requirements, classifies them, and invokes MCP tools to store structured results. The skill is a markdown file that instructs Gemini how to process requirements. This LLD defines the skill's structure, classification logic, MCP invocation sequences, and the exact behavioral rules Gemini must follow.

---

## 2. Skill File Structure

The skill is delivered as a single Gemini CLI skill file (`.md`). Its structure:

```
gemini_skill/
└── r210_extraction.md         # The Gemini CLI skill file
```

### 2.1 Skill File Sections

| Section | Content |
|---------|---------|
| **Header** | Skill metadata (name, description, version) |
| **MCP Configuration** | MCP server connection details (Python server, stdio) |
| **Role Definition** | System prompt defining Gemini's role as an AUTOSAR requirement extractor |
| **Behavioral Rules** | Mandatory constraints from SRS (no invention, query-first, etc.) |
| **Classification Guide** | How to classify input requirements by artifact type |
| **Extraction Procedures** | Step-by-step procedures for each supported artifact type |
| **Issue Recording Guide** | When and how to record review issues |
| **MCP Tool Reference** | Quick reference for all available MCP tools |

---

## 3. Role Definition

The skill's system prompt defines Gemini's role:

```markdown
You are an AUTOSAR requirement extraction assistant. Your task is to:
1. Read input requirements provided by the user.
2. Classify each requirement into supported artifact types or identify issues.
3. Use MCP tools to store structured extraction results.
4. Record anything ambiguous, incomplete, or unsupported as review issues.

You must NEVER invent, infer, or assume information not explicitly stated
in the input requirements.
```

---

## 4. Behavioral Rules

These rules are embedded in the skill file as mandatory instructions. Each maps to an SRS requirement.

### 4.0 Synthetic-Mode Gate (SRS-015)

> **Architecture note:** This gate is NOT enforced inside the Gemini skill itself.
> By the time the skill executes, input text has already been transmitted to the
> Gemini API. The gate is a **local preflight** in the launcher script that
> invokes `gemini --skill`.

```
ENFORCEMENT POINT: Local launcher script (before Gemini CLI invocation).

Procedure:
  1. Read the configuration flag "approved_for_real_data" (default: false)
     from the MCP server or environment configuration.
  2. If NOT approved (default):
     - Print to the local terminal: "Real-data operation requires stakeholder
       approval per SRS-015. Currently operating in synthetic-data-only mode."
     - Exit without invoking Gemini CLI. No data leaves the work computer.
  3. If approved:
     - Invoke Gemini CLI with the skill file.
     - Extraction proceeds subject to all data-minimization rules (§4.7, §11).

The skill file itself includes a redundant advisory note reminding the LLM
that only synthetic data should be processed, but this is defense-in-depth —
the binding enforcement is the local preflight.
```

### 4.1 No Invention Rule (SRS-003, SRS-077)

```
RULE: Extract ONLY information explicitly stated in the input.
- Do NOT infer names, types, sizes, relationships, or values.
- Do NOT generate default values for missing fields.
- If information is missing, record a review issue — do not fill in gaps.
- If the input says "a data type" without specifying which, record it as
  ambiguous — do not guess.
```

### 4.2 Query-First Rule (SRS-078)

```
RULE: Before creating any new record that references another record,
query existing records via MCP to check if the referenced record already exists.

Procedure:
1. Use query_type_definitions to search for type references by name.
2. Use query_port_interfaces to search for interface references by name.
3. Use query_port_prototypes to search for prototype references by name.
4. If a match is found, use its unique_key for the reference.
5. If no match is found, check if the missing record is in the current
   input batch — if so, create it first, then reference its unique_key.
6. If no match and not in the input, create a review issue with
   issue_type = "unresolved_reference".
```

### 4.3 Stable UUID Rule (SRS-079)

```
RULE: Always use unique_key (UUID) values returned by MCP tools when
referring to existing records. Never fabricate or reuse UUID values.
```

### 4.4 Issue Recording Rule (SRS-080, SRS-081)

```
RULE: Record the following as review issues:
- Missing information → issue_type: "incomplete"
- Ambiguous information → issue_type: "ambiguous"
- Unresolved references → issue_type: "unresolved_reference"
- Unsupported features → issue_type: "unsupported"
- Complex architectural changes → issue_type: "out_of_scope"
```

### 4.5 No Approval Authority (SRS-082a)

```
RULE: You must NEVER set any artifact or child record status to "approved".
- Approval is reserved for manual review by human reviewers.
- When calling set_review_status, always pass caller = "extraction".
- You may set status to "ambiguous" or "out_of_scope" at creation time
  when the input warrants it (SRS-035a).
- You may set status to "pending_review" when appropriate.
- You must NOT attempt to approve, even if asked by the user in the prompt.
```

### 4.6 No Direct Database Access (SRS-082)

```
RULE: Never attempt to access the SQLite database directly.
All database operations must go through MCP tools.
```

### 4.7 Data Minimization (SRS-015a)

```
RULE: The following data enters your context from MCP query results:
- unique_key values
- name fields (source_reference for SourceRequirements)
- kind/interface_type fields
- status fields (for determining if a record can be referenced)
- direction (for PortPrototypes — connection cardinality checking)
- issue_type (for ReviewIssues — extraction issue awareness)

The following data must NEVER be sent to the API or included in prompts:
- review_note fields
- resolution fields from review issues
- generated output content
- review report content
```

---

## 5. Classification Logic

### 5.1 Supported Artifact Types

The skill classifies each input requirement into one of these artifact types (SRS-001):

| Artifact Type | Classification Criteria |
|---------------|------------------------|
| Simple Type Definition | Input describes a basic data type with a base type and optional size |
| Array Data Type | Input describes an array with element type and size |
| Structure Data Type | Input describes a composite structure with named elements |
| Enumeration | Input describes a set of named values |
| Sender-Receiver Port Interface | Input describes a port interface with data elements |
| Client-Server Port Interface | Input describes a port interface with operations and arguments |
| Port Prototype | Input describes a port on a component with direction and interface reference |
| Port Connection | Input describes connections between port prototypes |

### 5.2 Classification Decision Tree

```
Input Requirement
│
├─ Mentions data type/typedef?
│   ├─ Has base type → Simple Type Definition
│   ├─ Has element type + size → Array Data Type
│   ├─ Has named elements/members → Structure Data Type
│   └─ Has enumeration values → Enumeration
│
├─ Mentions port interface?
│   ├─ Has data elements (sender/receiver pattern) → Sender-Receiver Interface
│   └─ Has operations/services (client/server pattern) → Client-Server Interface
│
├─ Mentions port/port prototype?
│   └─ Has direction + component + optional interface → Port Prototype
│
├─ Mentions connection/wiring/assembly?
│   └─ Has port references → Port Connection
│
├─ Mentions complex architecture (new SWC, etc.)?
│   └─ Out of Scope → record ReviewIssue (SRS-005)
│
├─ Multiple artifact types in one requirement?
│   └─ Extract each artifact separately, link all to same SourceRequirement
│
└─ Cannot classify?
    └─ Record ReviewIssue with issue_type = "ambiguous" or "unsupported"
```

### 5.3 Multi-Artifact Requirements

A single input requirement may contain multiple artifacts (e.g., a type definition and an interface that uses it). The skill shall:

1. Create one `SourceRequirement` record for the input.
2. Extract each artifact separately, linking each to the same `source_requirement_key`.
3. Process artifacts in dependency order: types before interfaces, interfaces before prototypes, prototypes before connections.

---

## 6. Extraction Procedures

### 6.1 Common Preamble (applied to every extraction)

```
For each input requirement:
  1. Create a SourceRequirement via create_source_requirement:
     - source_reference: the external document/requirement ID
     - source_text: the requirement text (if permitted)
  2. Classify the requirement using the decision tree (§5.2)
  3. Follow the artifact-specific procedure below
  4. If any step fails, record a ReviewIssue explaining what went wrong
```

### 6.2 Simple Type Definition

```
Inputs needed: name, base_type, size (optional), description (optional)

Procedure:
  1. Query existing type definitions: query_type_definitions(name=<name>, kind="simple_typedef")
  2. Always call create_type_definition — the MCP server handles duplicate
     detection (SRS-034) and returns a warning if a match exists. Do NOT
     skip creation on the skill side; the server may still create the record.
  3. Call create_type_definition:
     - name: <extracted name>
     - kind: "simple_typedef"
     - description: <extracted description or null>
     - source_requirement_key: <from step 1 of preamble>
     - subtype: { "base_type": <extracted>, "size": <extracted or null> }
  4. If base_type is unclear → create ReviewIssue(issue_type="ambiguous")
```

### 6.3 Array Data Type

```
Inputs needed: name, element type reference, array_size, description (optional)

Procedure:
  1. Query existing: query_type_definitions(name=<name>, kind="array")
  2. Resolve element type reference:
     a. Query: query_type_definitions(name=<element_type_name>)
     b. If found → use unique_key
     c. If not found → create ReviewIssue(issue_type="unresolved_reference")
        and STOP (cannot create array without element type — SRS-036a default)
  3. Validate array_size is a positive integer
  4. Call create_type_definition:
     - kind: "array"
     - subtype: { "element_type_key": <resolved>, "array_size": <extracted> }
```

### 6.4 Structure Data Type

```
Inputs needed: name, elements (each: name, type reference, position, description)

Procedure:
  1. Query existing: query_type_definitions(name=<name>, kind="struct")
  2. For each element, resolve the element type reference (query-first)
     - If any type unresolved → record ReviewIssue, STOP (SRS-036a default)
  3. Assign positions starting from 1 in the order the elements appear in the input
  4. Call create_type_definition:
     - kind: "struct"
     - subtype: { "elements": [ { name, element_type_key, position, description }, ... ] }
  5. If any element is ambiguous → set the element's initial status to "ambiguous"
     via the create call, and the parent will be handled by the MCP server
```

### 6.5 Enumeration

```
Inputs needed: name, values (each: name, explicit value (optional), position, description)

Procedure:
  1. Query existing: query_type_definitions(name=<name>, kind="enum")
  2. Assign positions starting from 1 in the order values appear
  3. Call create_type_definition:
     - kind: "enum"
     - subtype: { "values": [ { name, value, position, description }, ... ] }
  4. If any value name or explicit value is unclear → record ReviewIssue
```

### 6.6 Sender-Receiver Port Interface

```
Inputs needed: name, data elements (each: name, type reference, position, description)

Procedure:
  1. Query existing: query_port_interfaces(name=<name>, interface_type="sender_receiver")
  2. Resolve type references for each data element (query-first)
  3. Assign positions in input order
  4. Call create_port_interface:
     - interface_type: "sender_receiver"
     - children: [ { name, type_definition_key, position, description }, ... ]
```

### 6.7 Client-Server Port Interface

```
Inputs needed: name, operations (each: name, position, arguments, description)

Procedure:
  1. Query existing: query_port_interfaces(name=<name>, interface_type="client_server")
  2. For each operation's arguments, resolve type references
  3. Assign positions for operations and arguments in input order
  4. Call create_port_interface:
     - interface_type: "client_server"
     - children: [
         { name, position, description,
           arguments: [ { name, type_definition_key, direction, position }, ... ]
         }, ...
       ]
```

### 6.8 Port Prototype

```
Inputs needed: name, direction, interface reference, component_reference, functions (optional)

Procedure:
  1. Query existing: query_port_prototypes(name=<name>)
  2. Resolve port interface reference:
     a. Query: query_port_interfaces(name=<interface_name>)
     b. If found → use unique_key
     c. If not found → set port_interface_key to null (SRS-036 allows NULL)
        MCP server will create unresolved_reference ReviewIssue
  3. Determine direction: "provider" or "requester"
     - If unclear → create ReviewIssue(issue_type="ambiguous")
  4. Call create_port_prototype:
     - direction: <extracted>
     - port_interface_key: <resolved or null>
     - component_reference: <extracted>
     - functions: [ { function_name, relationship_type }, ... ] if present
```

### 6.9 Port Connection

```
Inputs needed: port prototype references, description (optional)

Procedure:
  1. Resolve all port prototype references:
     a. Query: query_port_prototypes(name=<name>)
     b. If all found → collect unique_keys
     c. If any not found → create ReviewIssue(issue_type="unresolved_reference"), STOP
  2. Assign positions in input order
  3. Call create_port_connection:
     - members: [ { port_prototype_key, position }, ... ]
  4. MCP server will validate cardinality and compatibility (§7.5 of LLD-02)
```

---

## 7. Review Issue Recording

### 7.1 When to Create Review Issues

| Situation | issue_type | Message Template |
|-----------|-----------|------------------|
| Missing type name | `incomplete` | "Type definition missing name in requirement <ref>" |
| Missing base type for simple typedef | `incomplete` | "Simple type '<name>' missing base type" |
| Ambiguous type reference (multiple matches) | `ambiguous` | "Type reference '<name>' matches multiple definitions" |
| Unresolved type reference | `unresolved_reference` | "Type '<name>' referenced but not found" |
| Unresolved port interface | `unresolved_reference` | "Port interface '<name>' referenced but not found" |
| Unresolved port prototype | `unresolved_reference` | "Port prototype '<name>' referenced but not found" |
| Unclear direction | `ambiguous` | "Port prototype '<name>' direction unclear" |
| Unsupported feature | `unsupported` | "Feature '<description>' not supported by prototype" |
| Complex architecture change | `out_of_scope` | "Requirement describes complex architecture: <description>" |
| Multiple interpretations | `ambiguous` | "Requirement has multiple interpretations: <description>" |

### 7.2 Issue Creation Procedure

```
For each issue:
  1. Call create_review_issue:
     - source_requirement_key: <source requirement UUID if known>
     - artifact_type: <type of affected artifact if known>
     - artifact_unique_key: <UUID of affected artifact if it was created>
     - issue_type: <from table above>
     - message: <specific explanation based only on input text>
  2. The message must describe what was found in the input —
     not what Gemini thinks should be there
```

---

## 8. Dependency-Ordered Processing

When processing a batch of requirements, the skill shall order extractions by dependency to minimize unresolved references:

```
Processing Order:
  1. Source Requirements (all — creates the traceability anchors)
  2. Simple Type Definitions (no dependencies on other artifacts)
  3. Enumerations (no dependencies on other artifacts)
  4. Array Data Types (depend on element type — must exist)
  5. Structure Data Types (depend on element types — must exist)
  6. Sender-Receiver Port Interfaces (depend on type definitions)
  7. Client-Server Port Interfaces (depend on type definitions)
  8. Port Prototypes (depend on port interfaces — can be NULL)
  9. Port Connections (depend on port prototypes)
```

Within each artifact type, process in the order they appear in the input.

---

## 9. Error Handling

### 9.1 MCP Tool Errors

When an MCP tool returns an error:

```
1. Log the error details within the CLI session
2. Create a ReviewIssue documenting the failure (SRS-121)
3. Continue with the next requirement
4. Never silently skip a failed extraction
5. Never retry the failed operation (SRS-114 — the skill does NOT
   implement automatic retry logic; all resilience is in the MCP server)
```

### 9.2 Batch Processing Failure

If multiple errors accumulate during a batch:

```
1. Continue processing remaining requirements (do not abort)
2. Summarize all failures at the end of the batch
3. Each failure has a corresponding ReviewIssue in the database
```

---

## 10. MCP Tool Quick Reference

This section is embedded in the skill file for Gemini's reference during execution.

| Tool | Purpose | Key Parameters |
|------|---------|---------------|
| `create_source_requirement` | Record input requirement | source_reference, source_text |
| `query_source_requirements` | Find existing sources | status, source_reference |
| `create_type_definition` | Create type with subtype | name, kind, subtype (required) |
| `query_type_definitions` | Find existing types | name, kind, status |
| `create_struct_element` | Add element to struct | struct_type_key, name, element_type_key, position |
| `create_enum_value` | Add value to enum | enum_type_key, name, value, position |
| `create_port_interface` | Create interface with children | name, interface_type, children |
| `query_port_interfaces` | Find existing interfaces | name, interface_type |
| `create_interface_data_element` | Add data element to SR interface | port_interface_key, name, type_definition_key, position |
| `create_client_server_operation` | Add operation to CS interface | port_interface_key, name, position |
| `create_operation_argument` | Add argument to operation | operation_key, name, type_definition_key, direction, position |
| `create_port_prototype` | Create port prototype | name, direction, port_interface_key, component_reference |
| `query_port_prototypes` | Find existing prototypes | name, direction |
| `create_port_prototype_function` | Add function to prototype | port_prototype_key, function_name, relationship_type |
| `create_port_connection` | Create connection with members | members (required) |
| `create_review_issue` | Record extraction issue | issue_type, message |
| `resolve_reference` | Look up any record by UUID | unique_key |

---

## 11. Data Sent to Gemini API (SRS-015a)

The skill file shall include an explicit data boundary section:

### 11.1 Data Entering Gemini Context

The following fields are the **only** data permitted to enter Gemini context (SRS-015a). MCP query tools enforce this by returning only these fields in their response payload during the extraction workflow (see LLD-02 §11 Response Projection).

| Data Category | Source | Enters Context | Justification |
|--------------|--------|---------------|---------------|
| Input requirement text | User input | Yes | Primary extraction input |
| MCP query result: `unique_key` | query_* tools | Yes | Reference resolution (SRS-078) |
| MCP query result: `name` | query_* tools | Yes | Duplicate checking (SRS-034) |
| MCP query result: `kind` / `interface_type` | query_* tools | Yes | Classification and kind-matching |
| MCP query result: `status` | query_* tools | Yes | Determine if record is usable for referencing |
| MCP query result: `direction` | query_port_prototypes | Yes | Connection cardinality checking |
| MCP query result: `source_reference` | query_source_requirements | Yes | External identifier for SourceRequirements (no `name` field) |
| MCP query result: `issue_type` | query_review_issues | Yes | Extraction issue awareness |
| MCP create result: `unique_key` | create_* tools | Yes | Reference newly created records |
| MCP create result: `warnings` | create_* tools | Yes | Duplicate-detection alert text (SRS-121) |

### 11.2 Data That Must NOT Enter Gemini Context

| Data Category | Reason |
|--------------|--------|
| `source_text` | Contains original requirement text from previous extractions |
| `description` | Free-text content that may contain work-sensitive information |
| `review_note` | Review decisions stay local |
| `resolution` fields from ReviewIssues | Review decisions stay local |
| `component_reference` | May contain internal project identifiers |
| `function_name` | May contain internal implementation details |
| `value` (EnumValues) | May contain work-specific values |
| `base_type`, `size` (SimpleTypeDefinitions) | Detail fields beyond the allowlist |
| `array_size` (ArrayTypeDefinitions) | Detail field beyond the allowlist |
| Generated R210 output content | Generated content stays local |
| Review report content | Report stays local |

**Enforcement:** MCP query tools apply a field projection that returns only the fields listed in §11.1. This projection is enforced by the MCP server's response formatting layer (LLD-02 §11). Query tools used by the Local Review CLI (LLD-06) return full records since that path does not send data to the Gemini API.

---

## 12. Traceability Matrix (LLD-03 → SRS)

| LLD Section | SRS Requirements |
|-------------|-----------------|
| §3 Role Definition | SRS-007, SRS-009, SRS-021 |
| §4.0 Synthetic-Mode Gate | SRS-015 |
| §4.1 No Invention | SRS-003, SRS-077 |
| §4.2 Query-First | SRS-078 |
| §4.3 Stable UUID | SRS-079 |
| §4.4 Issue Recording | SRS-080, SRS-081 |
| §4.5 No Approval Authority | SRS-082a |
| §4.6 No Direct DB | SRS-082 |
| §4.7 Data Minimization | SRS-015a |
| §5 Classification | SRS-001, SRS-002, SRS-005, SRS-006, SRS-009 |
| §6.1 Common Preamble | SRS-008, SRS-010, SRS-035a |
| §6.2–6.5 Type Extractions | SRS-042–050 (data model for types) |
| §6.6–6.7 Interface Extractions | SRS-051–059 (data model for interfaces) |
| §6.8 Port Prototype | SRS-060–063, SRS-036 |
| §6.9 Port Connection | SRS-065–068 |
| §7 Issue Recording | SRS-074, SRS-075, SRS-080, SRS-081 |
| §8 Dependency Order | SRS-078 (derived: process in dependency order) |
| §11 Data Boundary | SRS-015, SRS-015a, SRS-017 |

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-10 | Initial LLD derived from SRS v5.0 and HLD v3.0. |
| 1.1     | 2026-08-10 | Post-review amendments: Added §4.0 synthetic-mode gate. Added §4.5 no-approval-authority rule (caller="extraction", SRS-082a). Renumbered §4.5→§4.6, §4.6→§4.7. Expanded §11.1 data boundary with justification column and `direction`/`warnings` fields. Expanded §11.2 exclusion list with all specific fields. Removed retry logic from §9.1 (SRS-114). Fixed duplicate handling in §6.2: always create record, let MCP server handle duplicates (SRS-034). |
| 1.2     | 2026-08-11 | Review-driven fixes: Moved §4.0 synthetic-mode gate to local preflight (C-03 — gate was post-transfer). Fixed duplicate §4.6 numbering (M-02). Fixed cross-reference from LLD-02 §7.10 to §11 (M-02). Removed duplicate warnings row in §11.1 (M-02). Added `source_reference` and `issue_type` to §4.7 and §11.1 field lists (C-05). Fixed traceability matrix: §4.0 added, §4.5 relabeled to "No Approval Authority" (M-02). Updated source references to SRS v5.2, HLD v3.1. |
