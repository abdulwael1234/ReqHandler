# High-Level Design Document

## R210 AUTOSAR Requirements Automation Prototype

| Field              | Value                                                    |
|--------------------|----------------------------------------------------------|
| **Document ID**    | R210-HLD-001                                             |
| **Version**        | 3.1                                                      |
| **Date**           | 2026-08-10                                               |
| **Source Document** | `Srs/SRS_Requirements.md` (R210-SRS-001 v5.0)          |
| **Status**         | Draft — revised after second architecture review         |

---

## 1. Introduction

### 1.1 Purpose

This High-Level Design (HLD) document describes the software architecture and component design for the R210 AUTOSAR Requirements Automation Prototype. It translates the requirements defined in the SRS into an architectural blueprint that guides detailed design and implementation.

### 1.2 Scope

The system automates the extraction of deterministic AUTOSAR artifacts from input requirements, stores them in a structured database, supports manual review, and generates R210-specific requirement files. The supported artifact types are:

- Simple type definitions
- Array data types
- Structure data types
- Enumerations
- Port interfaces (sender-receiver and client-server)
- Port prototypes
- Port connections

### 1.3 Design Principles

| Principle | Rationale | Derived From |
|-----------|-----------|--------------|
| Separation of deterministic and nondeterministic processing | The LLM (Gemini) handles interpretation; all generation is deterministic Python | SRS-101, SRS-013 |
| No LLM database access | All data operations go through validated MCP tools | SRS-082, SRS-022 |
| No data invention | The system never fabricates missing information | SRS-003, SRS-077 |
| Human-in-the-loop | Manual review is the quality gate before output generation | SRS-018, SRS-011 |
| No deletion by LLM | Incorrect data is marked `rejected`, never deleted | SRS-091, SRS-092 |
| Data integrity by design | Transactions, FK enforcement, validation at boundaries | SRS-084, SRS-032, SRS-083 |
| Data-minimization for API transfer | Input text + MCP query results (keys, names, kinds) for extraction; no review decisions, notes, or generated outputs | SRS-015, SRS-015a |
| Rejected children do not block export | A rejected child is excluded from evaluation — parent remains exportable if all non-rejected children are approved | SRS-092a |

### 1.4 References

- `Srs/SRS_Requirements.md` — Software Requirements Specification v5.0
- `Sytem_description/system_Description.md` — System Description

---

## 2. Architectural Overview

### 2.1 System Context

```
                    ┌─────────────────────────────────────────────────┐
                    │              Gemini API (Google)                  │
                    │  (BLOCKED — requires stakeholder approval,       │
                    │   SRS-015; synthetic data only until then)       │
                    └──────────────────────┬──────────────────────────┘
                                           │ input text only (SRS-015a)
┌──────────────────────────────────────────┼──────────────────────────────────┐
│                         Work Environment │                                   │
│                                          ▼                                   │
│  ┌──────────────┐     ┌────────────────────────────────────────────────┐   │
│  │   Input      │     │          R210 Automation Prototype              │   │
│  │ Requirements │────▶│                                                │   │
│  │  (external)  │     │  Gemini CLI ──MCP──▶ MCP Server ──SQL──▶ DB   │   │
│  └──────────────┘     │                          │                     │   │
│                        │  Reviewer ──MCP──▶ MCP Server (query+status)  │   │
│  ┌──────────────┐     │                          │                     │   │
│  │   R210       │     │  Generator ◀── reads ────┘                     │   │
│  │   Output     │◀────│                                                │   │
│  │   Files      │     └────────────────────────────────────────────────┘   │
│  ├──────────────┤                                                          │
│  │   Review     │                                                          │
│  │   Report     │                                                          │
│  └──────────────┘                                                          │
└────────────────────────────────────────────────────────────────────────────┘
```

**Confidentiality boundary (SRS-015, SRS-015a):** The source document prohibits transferring work information outside the work computer. Using Gemini (SRS-014) requires sending data to the Gemini API — an external transfer that contradicts this rule. **This is a BLOCKING stakeholder decision** (SRS-015): until explicit security/stakeholder approval is obtained, the system operates with synthetic data only. The Gemini CLI skill shall enforce a synthetic-mode gate — it shall verify the approval status before processing any input and refuse to proceed if operating in synthetic-only mode with real work data. When approved, data sent to the API is limited to (a) input requirement text for the current extraction and (b) MCP query results restricted to the fields: `unique_key`, `name`, `kind`, `interface_type`, `status`, `direction`, plus tool-response metadata (returned keys and duplicate-detection warning text) (SRS-015a). MCP query tools enforce this boundary by returning only the permitted fields in their response payload during the extraction workflow. Fields explicitly excluded: `source_text`, `description`, `review_note`, `resolution`, `component_reference`, `function_name`, generated outputs, and the review report. All persistent data remains on the work computer. Development outside the work environment uses synthetic data only (SRS-016).

### 2.2 Component Architecture

The system is composed of six components (five core + one review interface):

```
┌─────────────────────────────────────────────────────────────┐
│                     Gemini CLI Skill                          │
│  (Nondeterministic — LLM-driven extraction and triage)       │
└──────────────────────────┬───────────────────────────────────┘
                           │ MCP Tool Calls (stdio)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python MCP Server                          │
│  (Validation, transaction management, controlled operations) │
│  Also serves as the review interface (SRS-118)               │
└──────────────────────────┬───────────────────────────────────┘
                           ▲                │ SQL (via Python sqlite3)
                           │                ▼
┌──────────────────────────┘  ┌───────────────────────────────┐
│  Local Review CLI            │       SQLite Database          │
│  (SRS-123 — no Gemini API)   │  (Structured storage, FK enf.)│
└──────────────────────────    └──────────────┬────────────────┘
                                              │ Read (all records for report;
                                              │       approved records for R210)
                                              ▼
                              ┌───────────────────────────────┐
                              │  Deterministic Generator       │
                              │  (Validation, R210 files,      │
                              │   review report)               │
                              └───────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                   Database Initializer                        │
│  (Schema creation, migration, version tracking)              │
└─────────────────────────────────────────────────────────────┘
```

**Local Review CLI (SRS-123):** A local Python program that invokes the same MCP tools as the Gemini CLI skill but runs without connecting to the Gemini API. This ensures review decisions and database queries during manual review never leave the work computer. It is not a network-facing service.

### 2.3 Deployment Model

All components run locally on the work computer. The only network connection is Gemini CLI's connection to the Gemini API, which is an approved transfer limited to input text (§2.1).

| Component | Runtime | Notes |
|-----------|---------|-------|
| Gemini CLI Skill | Gemini CLI process | Controlled by skill file; connects to Gemini API only when stakeholder approval (SRS-015) is granted; synthetic-mode gate enforced |
| Python MCP Server | Python process (launched by Gemini CLI) | Communicates via MCP protocol (stdio); also invocable for review |
| Local Review CLI | Python process (local, no API) | Invokes MCP tools without Gemini API connection (SRS-123) |
| SQLite Database | File on local filesystem | Single-writer, no concurrency requirements |
| Deterministic Generator | Python (same application as MCP server or standalone) | Triggered via MCP or direct invocation |
| Database Initializer | Python CLI command | Run before first use and on upgrades |

---

## 3. Component Design

### 3.1 Gemini CLI Skill

**Responsibility:** Control the extraction workflow — read input requirements, classify each requirement, invoke MCP tools to store results, and raise review issues for anything the system cannot handle deterministically.

**Design:**

| Aspect | Decision |
|--------|----------|
| Implementation | Gemini CLI skill file (markdown with structured prompts) |
| Interface to MCP | MCP tool calls defined by the Python MCP server |
| State | Stateless — all persistent state lives in the database |
| Error handling | Failures from MCP tools are reported to the user within the CLI session |
| Data sent to API | Input requirement text + MCP query results (projected: unique_key, name, kind, interface_type, status, direction) + tool-response metadata (returned keys, duplicate warnings). All other fields excluded by MCP projection (SRS-015a) |

**Behavioral rules (from SRS):**

1. Extract only explicitly stated information (SRS-077)
2. Query existing records before creating references (SRS-078)
3. Use `unique_key` (UUID) for all cross-references (SRS-079)
4. Record missing/ambiguous information as review issues (SRS-080)
5. Record unsupported/complex requirements as out-of-scope issues (SRS-081)
6. Never access SQLite directly (SRS-082)

**Workflow sequence:**

```
For each input requirement:
  1. Parse and classify the requirement content
  2. If supported artifact type:
     a. Query MCP for existing records (duplicate check per SRS-078)
     b. Create SourceRequirement record via MCP (status: pending_review)
     c. Create artifact record(s) via MCP (status: pending_review per SRS-035a)
        - Subtype detail is required in the same create operation (SRS-038a)
     d. For PortPrototypes only: if port_interface_id is unresolved,
        store NULL (SRS-036) + create ReviewIssue (type: unresolved_reference)
     e. For other cross-artifact FKs (element_type_id): do NOT store NULL
        — reject the create or create a ReviewIssue (SRS-036a, pending stakeholder decision)
  3. If ambiguous/incomplete:
     a. Create SourceRequirement record via MCP
     b. Create ReviewIssue (type: ambiguous/incomplete) via MCP
     c. Optionally create the artifact with status: ambiguous (SRS-035a)
  4. If out of scope:
     a. Create SourceRequirement record via MCP
     b. Create ReviewIssue (type: out_of_scope) via MCP
```

### 3.2 Python MCP Server

**Responsibility:** Provide the sole interface between Gemini and the database, and the sole interface for manual review. Validate all inputs, enforce business rules, and manage transactions.

**Design:**

| Aspect | Decision |
|--------|----------|
| Implementation | Python application using MCP SDK (stdio transport) |
| Protocol | Model Context Protocol (MCP) over stdin/stdout |
| Validation | Input validation at tool boundary before any DB operation (SRS-083) |
| Transactions | Each write operation wrapped in a transaction (SRS-084) |
| Error reporting | Structured errors with operation, invalid field, reason, and affected `unique_key` (SRS-083, SRS-109) |

**Tool Surface (grouped by domain):**

| Tool Group | Operations | SRS Reference |
|------------|-----------|---------------|
| Source Requirements | create, update, query | SRS-085 |
| Type Definitions | create (with subtype), update, query | SRS-086, SRS-038a |
| Type Definition Children | create, update, query child records (StructElements, EnumValues) | SRS-086 |
| Port Interfaces | create (with children), update, query | SRS-086 |
| Port Interface Children | create, update, query child records (InterfaceDataElements, ClientServerOperations, OperationArguments) | SRS-086 |
| Port Prototypes | create (with functions), update, query | SRS-086 |
| Port Prototype Children | create, update, query child records (PortPrototypeFunctions) | SRS-086 |
| Port Connections | create (with members), update, query | SRS-086 |
| Port Connection Children | create, update, query child records (PortConnectionMembers) | SRS-086 |
| Review Issues | create, update (including resolution), query | SRS-088, SRS-119 |
| Review State Management | set status on artifacts and issues (with transition validation) | SRS-089, SRS-035b |
| Reference Resolution | resolve UUID to record | SRS-087 |
| Generation Trigger | request R210 output, report, or both | SRS-090 |

**Excluded operations (by design):**

- Delete any record (SRS-091)
- Clear tables or reset database (SRS-093)
- Direct SQL execution
- Change `TypeDefinitions.kind` after creation (SRS-120)
- Change `status` via general-purpose update tools — status only changes through `set_review_status` or automatic parent-demotion (SRS-091a)

**Validation rules enforced at tool boundary:**

| Rule | Applies To | SRS Reference |
|------|-----------|---------------|
| Kind-matching for subtypes | SimpleTypeDefinitions → `simple_typedef`, ArrayTypeDefinitions → `array`, StructElements → `struct`, EnumValues → `enum` | SRS-044 |
| Interface-type matching for children | InterfaceDataElements → `sender_receiver`, ClientServerOperations → `client_server` | SRS-055 |
| Direction value constraints | PortPrototypes: `provider`/`requester`; OperationArguments: `input`/`output`/`input_output` | SRS-061, SRS-059 |
| Position uniqueness and positivity | All ordered child tables: position ≥ 1, UNIQUE(parent_fk, position) | SRS-037, SRS-038b |
| Positive size values | `array_size` ≥ 1 | SRS-038b |
| Status value constraints | Artifacts: 5-state; Issues: 3-state | SRS-035, SRS-076 |
| Status transition validation | Only permitted transitions per SRS-035b | SRS-035b |
| Parent status propagation check | Parent cannot be `approved` if any non-rejected child is not `approved` | SRS-046, SRS-053, SRS-092a |
| Extraction caller cannot approve | When `caller` = `"extraction"`, transitions to `approved` are rejected | SRS-082a |
| Content-change demotion | Updating non-status fields of an approved record demotes it to `pending_review` | SRS-082b |
| Subtype cardinality | Each TypeDefinition must have exactly one subtype detail row | SRS-038a |
| Child name uniqueness | StructElements unique name within struct; EnumValues unique name within enum | SRS-038c |
| NULL-while-unresolved FK (established) | `PortPrototypes.port_interface_id` may be NULL | SRS-036 |
| NULL-while-unresolved FK (pending) | Other cross-artifact FKs (`element_type_id`) rejected if NULL until stakeholder decision | SRS-036a |
| Duplicate-name warning | Case-insensitive, whitespace-normalized comparison on create; warning returned in response; optionally persisted as ReviewIssue | SRS-034, SRS-121 |
| artifact_type/artifact_unique_key pairing | If `artifact_unique_key` is set, `artifact_type` must also be set | SRS-074 |
| Status only via set_review_status | Update tools shall reject `status` as an updatable field; status changes go through `set_review_status` only | SRS-091a |
| Automatic parent-demotion | When a child's status changes away from `approved` while its parent is `approved`, the parent is demoted to `pending_review` in the same transaction | SRS-035c |

**Connection validation (allocated to MCP server, enforced on create and update of PortConnections):**

| Rule | Description | SRS Reference |
|------|-------------|---------------|
| Member existence | Every `port_prototype_id` in members must exist in PortPrototypes | SRS-069 |
| No duplicate members | A `port_prototype_id` shall not appear twice within the same connection | SRS-070 |
| Interface compatibility | Connected port prototypes must have compatible port interfaces | SRS-071 (TBD — rules not yet defined) |
| Direction cardinality | Connection must contain ≥1 provider and ≥1 requester (stakeholder decision per SRS-072) | SRS-072 |
| Member mutation revalidation | Any create or update of `PortConnectionMembers` revalidates the complete connection (all four rules above) as a single transaction; partial states that violate the rules are not persisted | SRS-122 |
| TBD compatibility fallback | Until SRS-071 rules are defined, the server accepts connections without compatibility validation but creates a `ReviewIssue` (`issue_type` = `incomplete`, message: compatibility not verified) to prevent silent acceptance | SRS-125 |

### 3.3 SQLite Database

**Responsibility:** Persistent structured storage of all extraction results, review states, and relationships.

**Design:**

| Aspect | Decision |
|--------|----------|
| Engine | SQLite (file-based, single-user) |
| FK enforcement | `PRAGMA foreign_keys = ON` on every connection (SRS-032) |
| Identity | Integer `id` (internal PK) + UUID `unique_key` (external identity) (SRS-026, SRS-027) |
| Relationships | FK on integer `id` for internal joins; `unique_key` for MCP/external (SRS-028, SRS-029) |
| NULL semantics | Missing optional FK = NULL, never 0 (SRS-030) |
| Normalization | Child data in separate tables, no serialized lists (SRS-031) |

**Schema Overview (tables and relationships):**

```
SourceRequirements
  │
  ├──▶ TypeDefinitions ──┬──▶ SimpleTypeDefinitions
  │         │            ├──▶ ArrayTypeDefinitions
  │         │            ├──▶ StructElements
  │         │            └──▶ EnumValues
  │         │
  │         ▼ (referenced by element_type_id)
  │    StructElements, ArrayTypeDefinitions,
  │    InterfaceDataElements, OperationArguments
  │
  ├──▶ PortInterfaces ──┬──▶ InterfaceDataElements
  │         │           └──▶ ClientServerOperations ──▶ OperationArguments
  │         │
  │         ▼ (referenced by port_interface_id — nullable per SRS-036)
  │    PortPrototypes
  │
  ├──▶ PortPrototypes ──▶ PortPrototypeFunctions
  │         │
  │         ▼ (referenced by port_prototype_id)
  │    PortConnectionMembers
  │
  ├──▶ PortConnections ──▶ PortConnectionMembers
  │
  └──▶ ReviewIssues (artifact_type + artifact_unique_key — typed polymorphic, not FK-enforced)
```

**Database-level constraints (complete list):**

| Table | Constraint Type | Constraint | SRS Reference |
|-------|-----------------|------------|---------------|
| All tables | PK | `id` INTEGER PRIMARY KEY | SRS-026 |
| All externally-referable tables | UNIQUE | `unique_key` UNIQUE NOT NULL | SRS-027 |
| All artifact tables | CHECK | `status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')` | SRS-035 |
| TypeDefinitions | CHECK | `kind IN ('simple_typedef','array','struct','enum')` | SRS-043 |
| PortInterfaces | CHECK | `interface_type IN ('sender_receiver','client_server')` | SRS-052 |
| PortPrototypes | CHECK | `direction IN ('provider','requester')` | SRS-061 |
| OperationArguments | CHECK | `direction IN ('input','output','input_output')` | SRS-059 |
| PortPrototypeFunctions | CHECK | `relationship_type IN ('access_point','trigger')` | SRS-063 |
| ReviewIssues | CHECK | `issue_type IN ('ambiguous','incomplete','unresolved_reference','unsupported','out_of_scope')` | SRS-075 |
| ReviewIssues | CHECK | `status IN ('pending','resolved','rejected')` | SRS-076 |
| ReviewIssues | CHECK | `artifact_type IN ('type_definition','struct_element','enum_value','port_interface','interface_data_element','client_server_operation','operation_argument','port_prototype','port_prototype_function','port_connection','port_connection_member') OR artifact_type IS NULL` | SRS-074 |
| StructElements | UNIQUE | (`struct_type_id`, `position`) | SRS-037 |
| StructElements | UNIQUE | (`struct_type_id`, `name`) | SRS-038c |
| StructElements | CHECK | `position >= 1` | SRS-038b |
| EnumValues | UNIQUE | (`enum_type_id`, `position`) | SRS-037 |
| EnumValues | UNIQUE | (`enum_type_id`, `name`) | SRS-038c |
| EnumValues | CHECK | `position >= 1` | SRS-038b |
| InterfaceDataElements | UNIQUE | (`port_interface_id`, `position`) | SRS-037 |
| InterfaceDataElements | CHECK | `position >= 1` | SRS-038b |
| ClientServerOperations | UNIQUE | (`port_interface_id`, `position`) | SRS-037 |
| ClientServerOperations | CHECK | `position >= 1` | SRS-038b |
| OperationArguments | UNIQUE | (`operation_id`, `position`) | SRS-037 |
| OperationArguments | CHECK | `position >= 1` | SRS-038b |
| PortConnectionMembers | UNIQUE | (`port_connection_id`, `position`) | SRS-037 |
| PortConnectionMembers | UNIQUE | (`port_connection_id`, `port_prototype_id`) | SRS-070 |
| PortConnectionMembers | CHECK | `position >= 1` | SRS-038b |
| ArrayTypeDefinitions | CHECK | `array_size >= 1` | SRS-038b |
| PortPrototypes | FK nullable | `port_interface_id` REFERENCES PortInterfaces(`id`) — nullable | SRS-036 |
| All source_requirement_id fields | FK nullable | REFERENCES SourceRequirements(`id`) — nullable | SRS-041 |
| All other FK fields | FK NOT NULL | Standard FK constraints | SRS-029 |

**Nullability rules:**

| Field | Nullable | Reason |
|-------|----------|--------|
| `source_requirement_id` (all tables) | Yes | Source may be unknown (SRS-041) |
| `PortPrototypes.port_interface_id` | Yes | May be unresolved (SRS-036) |
| `source_text` | Yes | May not be retainable (SRS-040) |
| `review_note` | Yes | Optional explanation |
| `description` (all tables) | Yes | Optional from input |
| `SimpleTypeDefinitions.size` | Yes | Optional in input (SRS-047) |
| `EnumValues.value` | Yes | Optional explicit value (SRS-050) |
| `ReviewIssues.resolution` | Yes | Set when issue is resolved |
| `ReviewIssues.artifact_unique_key` | Yes | Issue may not target a specific artifact |
| `ReviewIssues.artifact_type` | Yes | NULL when `artifact_unique_key` is NULL |
| Other cross-artifact FKs (`element_type_id`) | Pending stakeholder decision (SRS-036a) — default: NOT NULL | SRS-036a |

### 3.4 Deterministic Generator/Exporter

**Responsibility:** Validate database content, produce R210 AUTOSAR requirement files from approved records, and produce a review report from all records. The review report is independently producible — it does not require approved artifacts to exist. All output is deterministic given the same inputs.

**Design:**

| Aspect | Decision |
|--------|----------|
| Implementation | Python module (pure deterministic logic) |
| Trigger | MCP tool call or direct CLI invocation |
| Input (R210 files) | Approved records where parent AND all children are `approved` |
| Input (review report) | All records regardless of status |
| Output | R210 AUTOSAR requirement files + review report (independent operations) |
| Determinism guarantee (R210 files) | Same set of fully-approved artifact trees + same generator version + same config → byte-identical R210 output (SRS-101) |
| Determinism guarantee (review report) | Same complete database snapshot (all records, all statuses, all issues) + same generator version → byte-identical report (SRS-101) |

**Processing pipeline:**

```
1. Load records from database
2. For R210 file generation (requires ≥1 approved artifact):
   a. Select approved parent records
   b. For each approved parent, evaluate children (SRS-104a, SRS-092a):
      - Exclude children with status `rejected` from evaluation
      - Check all remaining (non-rejected) children are `approved`
      - If any non-rejected child is not approved → exclude parent and all children
      - Report as validation warning in review report
      - Rejected children are omitted from generated output
   c. Check for unresolved FK references (NULL in mandatory fields)
      - Report validation errors and exclude invalid records (SRS-102)
   d. For each valid, fully-approved artifact:
      - Apply R210 template for the artifact type
      - Generate output file content (excluding rejected children)
3. Generate review report (always producible, even with no approved artifacts):
   - Section (a): Approved artifacts included in R210 output
   - Section (b): Approved parents excluded due to non-approved children (validation warnings)
   - Section (c): Artifacts with status pending_review
   - Section (d): Artifacts with status ambiguous
   - Section (e): Artifacts with status rejected (including rejected children omitted from output)
   - Section (f): Artifacts with status out_of_scope
   - Section (g): Review issues with status pending, grouped by issue_type
   - Section (h): Review issues with status resolved or rejected (decision log)
4. Write output files deterministically (see §7.1)
```

**Connection handling:** Port connections are preserved as global multi-port connections. No automatic expansion into pairwise provider/requester combinations (SRS-073).

**AUTOSAR metamodel mapping (for port prototype functions):**

| relationship_type | Maps to AUTOSAR |
|-------------------|-----------------|
| `access_point` | DataReadAccess, DataWriteAccess, or ServerCallPoint (TBD — exact selection rule per SRS-064) |
| `trigger` | ExternalTriggeringPoint |

### 3.5 Database Initializer

**Responsibility:** Create and maintain the database schema safely, preserving existing data.

**Design:**

| Aspect | Decision |
|--------|----------|
| Implementation | Python CLI command (`init_db`) |
| Invocation | Manual — before first use and on version upgrades |
| Idempotency | Safe to call repeatedly (SRS-098) |
| Data preservation | Never drops or truncates existing tables (SRS-099) |
| Versioning | Records schema version in metadata table (SRS-097) |

**Initialization sequence:**

```
1. Create database file if it does not exist (SRS-095)
2. Enable FK enforcement (PRAGMA foreign_keys = ON)
3. Read current schema version (or 0 if fresh)
4. For each migration from current version to target (SRS-124):
   a. BEGIN TRANSACTION
   b. CREATE TABLE IF NOT EXISTS for new tables
   c. Add new columns / constraints as needed
   d. Create indexes
   e. Update schema version record
   f. COMMIT
   — If any step fails, ROLLBACK; database remains at last successful version
5. Verify final schema state (all tables, constraints, indexes present)
```

**Migration transaction guarantee (SRS-124):** Each migration step and its schema-version update execute within a single database transaction. On failure, the transaction rolls back, leaving the database at the last successfully applied version. This prevents half-applied migrations.

**Development reset (separate from init):** A destructive reset command may exist for development use only. It is not exposed through MCP or the Gemini workflow (SRS-100).

---

## 4. Data Flow

### 4.1 Extraction Flow (LLM-driven)

```
Input Requirements
       │
       ▼
┌──────────────┐    MCP: create_source_requirement    ┌──────────────┐
│  Gemini CLI  │ ──────────────────────────────────▶  │  MCP Server  │
│    Skill     │    MCP: create_type_definition        │              │
│              │ ──────────────────────────────────▶  │  Validates   │
│  (classifies,│    MCP: create_review_issue           │  Transacts   │
│   extracts)  │ ──────────────────────────────────▶  │  Stores      │
└──────────────┘                                       └──────┬───────┘
                                                              │
                                                              ▼
                                                       ┌──────────────┐
                                                       │    SQLite    │
                                                       │   Database   │
                                                       └──────────────┘
```

### 4.2 Review Flow (Human-driven, through MCP)

```
┌──────────────┐    MCP: query_* tools          ┌──────────────┐
│    User      │ ◀─────────────────────────────│  MCP Server  │
│  (Reviewer)  │                                │              │
│              │    MCP: set_review_status       │  Validates   │
│              │ ──────────────────────────────▶│  transitions │
│              │    MCP: update_review_issue     │  Checks      │
│              │ ──────────────────────────────▶│  parent-     │
│              │    (set resolution)             │  child       │
└──────────────┘                                └──────┬───────┘
                                                       │
                                                       ▼
                                                ┌──────────────┐
                                                │    SQLite    │
                                                │   Database   │
                                                └──────────────┘
```

**Review interface (SRS-118):** All review operations go through the MCP tool surface. The reviewer uses `query_*` tools to inspect artifacts and issues, `set_review_status` to approve/reject/mark artifacts, and `update_review_issue` to set resolution and close issues. No direct database modification is required. This ensures all validation rules (status transitions per SRS-035b, parent-child consistency per SRS-046/053, status-only-via-set_review_status per SRS-091a) are enforced during review.

**Local Review CLI (SRS-123):** The reviewer accesses MCP tools through a local Python CLI that runs without connecting to the Gemini API. This guarantees review decisions and all associated database queries never leave the work computer. The review CLI is a local program, not a network-facing service.

**Automatic parent-demotion (SRS-035c):** When a child's status changes away from `approved` while its parent is `approved`, the system automatically demotes the parent to `pending_review` in the same transaction. This maintains the invariant that an approved parent has all reviewable children approved.

**Kind-correction workflow (SRS-120):** When a `TypeDefinitions.kind` is wrong, the reviewer rejects the incorrect record and requests creation of a new record with the correct kind. The `kind` field is immutable after creation because subtype detail tables are structurally different, and the system cannot safely migrate data between them.

### 4.3 Generation Flow (Deterministic)

```
┌──────────────┐                              ┌──────────────────┐
│   MCP Server │    Trigger generation        │    Generator     │
│   (or CLI)   │ ──────────────────────────▶ │                  │
└──────────────┘                              │  1. Load all     │
                                              │  2. Validate     │
       ┌──────────────┐                       │  3. Generate R210│
       │    SQLite    │ ◀──── Read all ───── │     (approved    │
       │   Database   │       records         │     + children)  │
       └──────────────┘                       │  4. Report       │
                                              │     (all status) │
                                              └────────┬─────────┘
                                                       │
                                          ┌────────────┼────────────┐
                                          ▼                         ▼
                                   ┌──────────────┐         ┌──────────────┐
                                   │  R210 Output │         │   Review     │
                                   │    Files     │         │   Report     │
                                   │ (may be      │         │ (always      │
                                   │  empty)      │         │  produced)   │
                                   └──────────────┘         └──────────────┘
```

---

## 5. Interface Design

### 5.1 MCP Tool Interface Contract

All MCP tools follow a consistent pattern:

**Request structure:**
```
{
  "tool": "<tool_name>",
  "arguments": {
    // Tool-specific validated parameters
    // References use unique_key (UUID), not internal id
  }
}
```

**Success response:**
```
{
  "result": {
    "unique_key": "<uuid>",
    // Additional fields relevant to the operation
    "warnings": [
      // Optional: duplicate-detection warnings (SRS-034, SRS-121)
    ]
  }
}
```

**Error response (SRS-083, SRS-109):**
```
{
  "error": {
    "operation": "<tool_name>",
    "field": "<invalid_field_name or null>",
    "reason": "<human-readable explanation>",
    "affected_key": "<unique_key or null>"
  }
}
```

### 5.2 MCP Tool Catalog

**Note:** All `update_*` tools exclude `status` as an updatable field (SRS-091a). Status changes go exclusively through `set_review_status` (or the automatic parent-demotion in SRS-035c).

#### Source Requirements

| Tool Name | Input | Output | Validation |
|-----------|-------|--------|------------|
| `create_source_requirement` | source_reference, source_text (optional) | unique_key | source_reference not empty |
| `update_source_requirement` | unique_key, fields to update | updated record | record exists |
| `query_source_requirements` | filters (optional) | list of records | — |

#### Type Definitions (parent + subtype created atomically)

| Tool Name | Input | Output | Validation |
|-----------|-------|--------|------------|
| `create_type_definition` | name, kind, description, source_requirement_key (opt), subtype details (required) | unique_key | kind valid; subtype required and matches kind (SRS-038a, SRS-044) |
| `update_type_definition` | unique_key, fields to update (kind excluded) | updated record | record exists; kind immutable (SRS-120) |
| `query_type_definitions` | filters (kind, name, status) | list of records with subtypes and children | — |

#### Type Definition Children

| Tool Name | Input | Output | Validation |
|-----------|-------|--------|------------|
| `create_struct_element` | struct_type_key, name, element_type_key, position, description (opt) | unique_key | parent kind=struct (SRS-044); position ≥ 1 unique within parent (SRS-037); name unique within struct (SRS-038c) |
| `update_struct_element` | unique_key, fields to update | updated record | record exists |
| `create_enum_value` | enum_type_key, name, value (opt), position, description (opt) | unique_key | parent kind=enum (SRS-044); position ≥ 1 unique within parent; name unique within enum (SRS-038c) |
| `update_enum_value` | unique_key, fields to update | updated record | record exists |

#### Port Interfaces

| Tool Name | Input | Output | Validation |
|-----------|-------|--------|------------|
| `create_port_interface` | name, interface_type, description, source_requirement_key (opt), children (opt) | unique_key | interface_type valid; children match type (SRS-055) |
| `update_port_interface` | unique_key, fields to update | updated record | record exists |
| `query_port_interfaces` | filters | list of records with children | — |

#### Port Interface Children

| Tool Name | Input | Output | Validation |
|-----------|-------|--------|------------|
| `create_interface_data_element` | port_interface_key, name, type_definition_key, position, description (opt) | unique_key | parent type=sender_receiver (SRS-055); position rules |
| `update_interface_data_element` | unique_key, fields to update | updated record | record exists |
| `create_client_server_operation` | port_interface_key, name, position, description (opt) | unique_key | parent type=client_server (SRS-055); position rules |
| `update_client_server_operation` | unique_key, fields to update | updated record | record exists |
| `create_operation_argument` | operation_key, name, type_definition_key, direction, position | unique_key | direction valid (SRS-059); position rules |
| `update_operation_argument` | unique_key, fields to update | updated record | record exists |

#### Port Prototypes

| Tool Name | Input | Output | Validation |
|-----------|-------|--------|------------|
| `create_port_prototype` | name, description (opt), direction, port_interface_key (nullable), component_reference, source_requirement_key (opt), functions (opt) | unique_key | direction valid (SRS-061) |
| `update_port_prototype` | unique_key, fields to update | updated record | record exists |
| `query_port_prototypes` | filters | list of records with functions | — |
| `create_port_prototype_function` | port_prototype_key, function_name, relationship_type | unique_key | relationship_type valid (SRS-063) |
| `update_port_prototype_function` | unique_key, fields to update | updated record | record exists |

#### Port Connections

| Tool Name | Input | Output | Validation |
|-----------|-------|--------|------------|
| `create_port_connection` | description, source_requirement_key (opt), members | unique_key | members exist (SRS-069); no duplicate members (SRS-070); direction cardinality (SRS-072); interface compatibility (SRS-071, TBD) |
| `update_port_connection` | unique_key, fields to update | updated record | record exists |
| `query_port_connections` | filters | list of records with members | — |
| `create_port_connection_member` | port_connection_key, port_prototype_key, position | unique_key | prototype exists; not duplicate within connection; position rules |
| `update_port_connection_member` | unique_key, fields to update | updated record | record exists |

#### Review Issues

| Tool Name | Input | Output | Validation |
|-----------|-------|--------|------------|
| `create_review_issue` | source_requirement_key (opt), artifact_type (opt), artifact_unique_key (opt), issue_type, message | unique_key | issue_type valid (SRS-075); if artifact_unique_key set then artifact_type required (SRS-074) |
| `update_review_issue` | unique_key, resolution (opt), status (opt) | updated record | record exists; status valid (SRS-076); status transition valid |
| `query_review_issues` | filters (issue_type, status) | list of records | — |

#### Cross-cutting

| Tool Name | Input | Output | Validation |
|-----------|-------|--------|------------|
| `set_review_status` | unique_key, table_hint, new_status, review_note (opt), caller (opt) | updated record | Artifacts and reviewable children only — rejects ReviewIssues and structural subtypes (SRS-091a); status valid; transition valid (SRS-035b); caller="extraction" blocks approval (SRS-082a); parent-child consistency with rejected exclusion (SRS-046, SRS-053, SRS-092a); triggers automatic parent-demotion if child changes away from approved (SRS-035c); review_note silently ignored when column absent |
| `resolve_reference` | unique_key | record with table and details | record found across all tables |
| `trigger_generation` | mode: `r210_only`, `report_only`, or `both` | generation result or error list | `r210_only`/`both`: ≥1 fully-approved artifact; `report_only`: always succeeds (SRS-104) |

### 5.3 Internal Interface: MCP Server ↔ Database

The MCP server interacts with SQLite through a data-access layer:

```
MCP Tool Handler
       │
       ▼
┌──────────────────────────┐
│   Validation Layer       │  ← Input validation, status transitions,
│                          │    parent-child checks, kind-matching,
│                          │    connection validation (SRS-069–072)
├──────────────────────────┤
│   Data Access Layer      │  ← SQL construction, transaction mgmt
├──────────────────────────┤
│   SQLite Connection      │  ← PRAGMA foreign_keys=ON, WAL mode
└──────────────────────────┘
```

### 5.4 Internal Interface: Generator ↔ Database

The generator reads the database directly (not through MCP) since it is a trusted, deterministic component:

```
Generator
       │
       ▼
┌──────────────────────────┐
│   Query Layer            │  ← Load all records (report) + approved (R210)
├──────────────────────────┤
│   Parent-Child Checker   │  ← Verify all children of approved parents
│                          │    are also approved (SRS-104a)
├──────────────────────────┤
│   FK Validation Layer    │  ← Check FK resolution, completeness (SRS-102)
├──────────────────────────┤
│   Template Engine        │  ← Apply R210 templates per artifact type
├──────────────────────────┤
│   Report Builder         │  ← Aggregate all statuses into report
├──────────────────────────┤
│   File Writer            │  ← Deterministic file output (see §7.1)
└──────────────────────────┘
```

---

## 6. Error Handling Strategy

### 6.1 Error Categories

| Category | Source | Handling |
|----------|--------|----------|
| Input validation failure | MCP tool boundary | Reject with structured error: operation, invalid field, reason, affected key (SRS-083, SRS-109) |
| Invalid status transition | MCP status update | Reject with current status, requested status, and list of permitted transitions (SRS-035b) |
| Status via update tool | MCP update tool | Reject — status not accepted as an updatable field; direct to `set_review_status` (SRS-091a) |
| Referential integrity violation | Database FK constraint | Reject with affected unique_key and reason |
| Parent-child status conflict | MCP status update | Block parent approval; return list of non-approved children with their statuses (SRS-046, SRS-053) |
| Auto parent-demotion | MCP child status change | Automatically demote parent from `approved` to `pending_review` in same transaction (SRS-035c) |
| Connection member revalidation failure | MCP member create/update | Reject the member mutation; connection remains in prior valid state (SRS-122) |
| TBD compatibility unverified | MCP connection create/update | Accept connection but create ReviewIssue noting compatibility not verified (SRS-125) |
| Unresolved reference at generation | Generator validation | Exclude artifact from R210 output, report in review report (SRS-102) |
| Non-approved children at generation | Generator parent-child check | Exclude parent+children from R210 output (rejected children excluded from evaluation per SRS-092a), report as validation warning (SRS-104a) |
| Duplicate warning | Name-based detection on create | Warn in response; optionally persist as ReviewIssue (SRS-034, SRS-121) |
| Migration step failure | Database initializer | Roll back transaction; database remains at last successful version (SRS-124) |

### 6.2 Error Message Format

All errors include (per SRS-083, SRS-109):
1. **Operation** — which tool or process failed
2. **Field** — which input field was invalid (for validation errors; null otherwise)
3. **Reason** — why it failed
4. **Affected record** — `unique_key` when applicable

### 6.3 Duplicate Detection (SRS-034, SRS-121)

When creating a new record, the MCP server performs name-based duplicate detection:

1. **Normalize** the new record's name: trim leading/trailing whitespace, collapse internal whitespace to a single space
2. **Compare** case-insensitively against existing records of the same kind
3. If a match is found:
   - Return a warning in the create response (record is still created)
   - Optionally create a `ReviewIssue` with `issue_type` = `ambiguous` referencing the new record

---

## 7. Non-Functional Design Decisions

### 7.1 Determinism (SRS-101)

Determinism applies to two independent scopes:

- **R210 files:** The relevant input is the set of fully-approved artifact trees (parents with all non-rejected children approved). Same trees + same generator version + same config → byte-identical R210 output.
- **Review report:** The relevant input is the complete database snapshot (all records, all statuses, all issues). Same snapshot + same generator version → byte-identical report.

Common determinism rules:

- Generator uses sorted queries (`ORDER BY position, id`) to ensure consistent record ordering
- No randomness in template application or file naming
- Python `dict` iteration order (insertion-ordered in 3.7+) is not relied upon; explicit sorting is used
- File encoding: UTF-8 without BOM
- Line endings: LF (Unix-style)
- Top-level artifact ordering in output: sorted by artifact type, then by name within type
- TBD items that affect determinism and must be resolved before byte-identical output can be verified: output templates (SRS-019c), file naming conventions (SRS-019d), AUTOSAR package paths, metamodel version identifiers. See §9 for the complete TBD list.

### 7.2 Idempotency (SRS-098)

- `init_db` uses `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`
- Schema version checks prevent re-running migrations
- Multiple calls produce the same final state

### 7.3 Traceability (SRS-107, SRS-038)

- Every artifact links to its `SourceRequirements` record via `source_requirement_id`
- Child records inherit traceability from their parent (no separate `source_requirement_id`)
- The review report traces each output back through the chain

### 7.4 Data Safety

- No delete operations in MCP surface (SRS-091)
- No table-clearing operations (SRS-093)
- Rejection instead of deletion (SRS-092)
- Kind correction via reject + recreate (SRS-120)
- Database initializer preserves all data (SRS-099)
- Write operations use transactions (SRS-084)

### 7.5 Confidentiality (SRS-015, SRS-015a, SRS-016)

- **BLOCKING stakeholder decision (SRS-015):** The source document prohibits external transfer absolutely. Using Gemini requires sending data to the Gemini API (external transfer). This contradiction requires explicit security/stakeholder approval before real-data operation. Until approved, the system operates on synthetic data only.
- When the stakeholder decision is approved, data sent to the Gemini API is limited to: (a) input requirement text for the current extraction, and (b) MCP query results (unique_keys, names, kinds, types) for duplicate checking and reference resolution (SRS-015a)
- The Gemini CLI skill definition shall document the exact fields returned by MCP query tools that enter the Gemini model context (SRS-015a)
- Review decisions, review notes, generated outputs, and the review report are never sent to the Gemini API
- The Local Review CLI (SRS-123) operates without any Gemini API connection, ensuring review-phase data never leaves the work computer
- All persistent data (database, generated files, reports) remains on the work computer
- Development outside the work environment uses synthetic data only (SRS-016)
- Source text stored as NULL when retention is not permitted in the work environment (SRS-040)

---

## 8. Technology Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| LLM Interface | Gemini CLI | Only approved LLM (SRS-014) |
| LLM Skill | Gemini CLI skill file | Guides extraction behavior |
| MCP Server | Python + MCP SDK | Controlled tool interface |
| Database | SQLite | Local, file-based, no server needed |
| Generator | Python | Deterministic logic, template rendering |
| Transport | stdio (MCP protocol) | Standard Gemini CLI ↔ MCP communication |

---

## 9. Open Items and TBDs

These items from the SRS remain unresolved and affect detailed design. **No implementation baseline shall be established until the items marked "blocks baseline" are resolved.**

| Item | Description | Owner | Closure Condition | Impact on HLD | Blocks Baseline? |
|------|-------------|-------|-------------------|---------------|-------------------|
| SRS-015 | **BLOCKING:** Authorization to transfer work data to Gemini API | Stakeholders / Security | Explicit approval documenting data categories and conditions | System cannot process real data; operates on synthetic data only until resolved | **Yes — BLOCKING** |
| SRS-019(a) | Supported input formats | Dev team | Documented and validated on work computer | Gemini skill input parsing | Yes |
| SRS-019(b) | Source identifiers and mapping to `source_reference` | Dev team | Documented and validated | SourceRequirements field format | Yes |
| SRS-019(c) | Exact R210 output templates and file format | Dev team | Documented and validated | Generator template design; determinism verification | Yes |
| SRS-019(d) | File and artifact naming conventions | Dev team | Documented and validated | Generator output paths; determinism verification | Yes |
| SRS-019(e) | Source-input adapters | Dev team | Documented and validated | Pre-processing pipeline | No (can be added incrementally) |
| SRS-064 | AUTOSAR metamodel mapping for access_point/trigger | Dev team | Complete selection rule documented and validated | Generator mapping logic | Yes |
| SRS-071 | Port interface compatibility rules for connections | Dev team | Compatibility rules documented and validated | Connection validation in MCP server (§3.2). Until defined, connections accepted with ReviewIssue created (SRS-125) | No (TBD fallback designed) |
| SRS-036a | NULL-while-unresolved for non-port_interface FKs | Stakeholders | Decision documented | MCP validation rules for element_type_id | Yes |
| SRS-046/053 | Parent-child approval rule (tightened in SRS v4.0) | Stakeholders | Confirmed or revised | Generator parent-child check | No (SRS v4.0 made a concrete choice; v5.0 added SRS-035c auto-demotion and SRS-092a rejected-child exclusion) |
| SRS-072 | Connection direction cardinality (≥1 provider + ≥1 requester) | Stakeholders | Confirmed or revised | Connection validation | No (SRS v4.0 made a concrete choice) |
| — | AUTOSAR package paths, metamodel/version info for templates | Dev team | Determined from real work data | Generator template inputs | Yes |

---

## 10. Stakeholder Decisions

The SRS contains four stakeholder decisions. This HLD does **not** assume any particular outcome for pending decisions; it designs for both options and documents what changes with each decision.

| Decision | Options | HLD If (A) | HLD If (B) | SRS Reference | Status |
|----------|---------|------------|------------|---------------|--------|
| Authorization to transfer work data to Gemini API | (A) Approved with documented conditions; (B) Not approved | System processes real data with data-minimization per SRS-015a | System operates on synthetic data only; no real-data processing | SRS-015 | **BLOCKING** |
| NULL-while-unresolved for cross-artifact FKs beyond `port_interface_id` | (A) Only `port_interface_id` nullable; others NOT NULL at insert | MCP rejects create with NULL `element_type_id`; extraction must resolve types before referencing them | MCP allows NULL `element_type_id`; adds `unresolved_reference` ReviewIssue; generator excludes records with NULL FKs | SRS-036a | Pending |
| Parent-child approval (SRS v4.0 chose: all children must be approved) | (A) All non-rejected children approved; (B) Pending children allowed | Generator exports fully-approved trees; rejected children excluded per SRS-092a; parent auto-demoted per SRS-035c | Generator must define child handling for pending children in output | SRS-046, SRS-053 | Pending — implementable as designed |
| Connection cardinality (SRS v4.0 chose: ≥1 each) | (A) ≥1 provider + ≥1 requester; (B) Other rules | MCP validates cardinality on connection create/update | Different validation rule | SRS-072 | Pending — implementable as designed |

---

## 11. Traceability Matrix (HLD → SRS)

| HLD Section | SRS Requirements Covered |
|-------------|--------------------------|
| §1.2 Scope | SRS-001, SRS-006 |
| §1.3 Design Principles | SRS-003, SRS-011, SRS-013, SRS-015, SRS-015a, SRS-018, SRS-022, SRS-032, SRS-077, SRS-082, SRS-083, SRS-084, SRS-091, SRS-092, SRS-092a, SRS-101 |
| §2.1 System Context | SRS-002, SRS-004, SRS-005, SRS-014, SRS-015, SRS-015a, SRS-016 |
| §2.2 Component Architecture | SRS-020, SRS-118, SRS-123 |
| §2.3 Deployment Model | SRS-014, SRS-015, SRS-123 |
| §3.1 Gemini CLI Skill | SRS-007, SRS-008, SRS-009, SRS-010, SRS-021, SRS-034, SRS-035a, SRS-036, SRS-036a, SRS-077, SRS-078, SRS-079, SRS-080, SRS-081, SRS-082, SRS-121 |
| §3.2 MCP Server | SRS-022, SRS-034, SRS-035, SRS-035a, SRS-035b, SRS-035c, SRS-036, SRS-036a, SRS-037, SRS-038a, SRS-038b, SRS-038c, SRS-044, SRS-046, SRS-053, SRS-055, SRS-059, SRS-061, SRS-069, SRS-070, SRS-071, SRS-072, SRS-074, SRS-075, SRS-076, SRS-082a, SRS-082b, SRS-083, SRS-084, SRS-085, SRS-086, SRS-087, SRS-088, SRS-089, SRS-090, SRS-091, SRS-091a, SRS-092, SRS-093, SRS-109, SRS-118, SRS-119, SRS-120, SRS-121, SRS-122, SRS-125 |
| §3.3 SQLite Database | SRS-023, SRS-026, SRS-027, SRS-028, SRS-029, SRS-030, SRS-031, SRS-032, SRS-033, SRS-035, SRS-036, SRS-036a, SRS-037, SRS-038, SRS-038a, SRS-038b, SRS-038c, SRS-039, SRS-040, SRS-041, SRS-042, SRS-043, SRS-044, SRS-045, SRS-047, SRS-048, SRS-049, SRS-050, SRS-051, SRS-052, SRS-054, SRS-055, SRS-056, SRS-057, SRS-058, SRS-059, SRS-060, SRS-061, SRS-062, SRS-063, SRS-065, SRS-066, SRS-067, SRS-068, SRS-074, SRS-075, SRS-076 |
| §3.4 Generator | SRS-012, SRS-013, SRS-024, SRS-064, SRS-073, SRS-092a, SRS-101, SRS-102, SRS-103, SRS-104, SRS-104a |
| §3.5 Database Initializer | SRS-025, SRS-094, SRS-095, SRS-096, SRS-097, SRS-098, SRS-099, SRS-100, SRS-124 |
| §4.1 Extraction Flow | SRS-004, SRS-008, SRS-009, SRS-010, SRS-035a |
| §4.2 Review Flow | SRS-011, SRS-018, SRS-035c, SRS-046, SRS-053, SRS-091a, SRS-118, SRS-119, SRS-120, SRS-123 |
| §4.3 Generation Flow | SRS-012, SRS-013, SRS-024, SRS-092a, SRS-101, SRS-102, SRS-103, SRS-104, SRS-104a |
| §5 Interface Design | SRS-022, SRS-028, SRS-034, SRS-035b, SRS-035c, SRS-069, SRS-070, SRS-071, SRS-072, SRS-074, SRS-083, SRS-085, SRS-086, SRS-087, SRS-088, SRS-089, SRS-090, SRS-091a, SRS-109, SRS-119, SRS-120, SRS-121, SRS-122, SRS-125 |
| §6 Error Handling | SRS-034, SRS-035b, SRS-035c, SRS-046, SRS-053, SRS-083, SRS-091a, SRS-092a, SRS-102, SRS-104a, SRS-109, SRS-121, SRS-122, SRS-124, SRS-125 |
| §7.1 Determinism | SRS-101, SRS-108 |
| §7.2 Idempotency | SRS-098 |
| §7.3 Traceability | SRS-038, SRS-041, SRS-107 |
| §7.4 Data Safety | SRS-084, SRS-091, SRS-092, SRS-093, SRS-099, SRS-106, SRS-120 |
| §7.5 Confidentiality | SRS-015, SRS-015a, SRS-016, SRS-040, SRS-123 |
| §8 Technology Stack | SRS-014, SRS-020 |
| §9 Open Items | SRS-015, SRS-017, SRS-019, SRS-064, SRS-071, SRS-125 |
| §10 Stakeholder Decisions | SRS-015, SRS-036a, SRS-046, SRS-053, SRS-072 |
| Scope exclusions (not designed) | SRS-111, SRS-112, SRS-113, SRS-114, SRS-115, SRS-116, SRS-117 |
| Quality cross-refs | SRS-105, SRS-106, SRS-107, SRS-108, SRS-109, SRS-110 |

**Coverage: 138/138 SRS requirements traced.** New v5.0 requirements SRS-035c, SRS-091a, SRS-092a, SRS-122, SRS-123, SRS-124, SRS-125 are traced to their design sections. SRS-082a and SRS-082b added during LLD review. Scope-exclusion requirements (SRS-111–117) are listed as explicitly not designed.

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-10 | Initial HLD derived from SRS v3.0. |
| 2.0     | 2026-08-10 | Post-architecture-review revision addressing all findings. **Critical:** resolved confidentiality contradiction by documenting approved Gemini API transfer with data-minimization boundary (§2.1, §7.5); defined manual-review interface through MCP tools, not direct DB access (§4.2, SRS-118). **High:** closed pending-children export loophole — parent+children excluded from R210 if any child not approved (§3.4, SRS-104a); completed MCP tool catalog with update_source_requirement, child record CRUD, update_review_issue with resolution (§5.2); fixed report generation gating — report producible independently of R210 files (§3.4, §5.2 trigger_generation modes); added complete database constraint table with NOT NULL, UNIQUE, CHECK, and nullability rules (§3.3); allocated connection validation (SRS-069–072) to MCP server with explicit rule table (§3.2); stopped assuming stakeholder decisions — HLD designs for both options (§10). **Medium:** added invalid field to error response format (§6.2, aligning SRS-083/109); specified duplicate detection normalization, comparison, and persistence rules (§6.3); added determinism design details — encoding, line endings, ordering, TBD blockers (§7.1); improved ReviewIssues polymorphic reference with typed (artifact_type, artifact_unique_key) pair (§3.3, §5.2); documented kind-correction workflow via reject+recreate (§4.2, SRS-120). **Traceability:** expanded matrix to cover all 129 SRS v4.0 requirements individually. |
| 3.0     | 2026-08-10 | Post-second-architecture-review revision aligned with SRS v5.0 (137 requirements). **Critical:** confidentiality rewritten as BLOCKING stakeholder decision — SRS cannot unilaterally authorize API transfer; system operates on synthetic data until approved (§2.1, §7.5, §9, §10); SRS-015a expanded to acknowledge MCP query results (keys, names, kinds) enter Gemini context. **High:** added Local Review CLI component (SRS-123) — local Python program invoking MCP tools without Gemini API connection (§2.2, §2.3, §4.2, §7.5); status restricted to `set_review_status` only — update tools reject status field (SRS-091a, §3.2, §5.2); automatic parent-demotion when child changes away from approved (SRS-035c, §3.2, §4.2); rejected children excluded from export evaluation — prevents permanent parent blockage (SRS-092a, §1.3, §3.4); connection member revalidation as single transaction (SRS-122, §3.2); TBD compatibility fallback creates ReviewIssue instead of silently accepting (SRS-125, §3.2, §9). **Medium:** migration transactions — each step + version update in single transaction with rollback on failure (SRS-124, §3.5); split determinism scope — R210 files from approved trees, report from full snapshot (SRS-101, §3.4, §7.1); expanded artifact_type CHECK to 11 types covering all child tables (SRS-074, §3.3); added Status column to Stakeholder Decisions table (§10). **Traceability:** expanded matrix to 137/137 SRS v5.0 requirements. |
| 3.1     | 2026-08-10 | Post-LLD-review amendments aligned with SRS v5.1 (138 requirements). Changed diagram annotation from "approved external transfer" to "BLOCKED — requires stakeholder approval" (§2.1). Expanded §2.1 confidentiality with synthetic-mode gate and full projection/exclusion field lists. Updated §3.1 data-sent row. Added conditional deployment note. Added 3 new validation rules in §3.2: extraction caller cannot approve (SRS-082a), content-change demotion (SRS-082b), rejected-child exclusion in parent approval check (SRS-092a). Updated §5.2 set_review_status with caller parameter and scope restrictions. Added `description` to `create_port_prototype` input. Added SRS-082a, SRS-082b to traceability matrix. Updated coverage to 138/138. |
