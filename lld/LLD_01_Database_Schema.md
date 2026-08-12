# Low-Level Design — SQLite Database Schema

## R210 AUTOSAR Requirements Automation Prototype

| Field              | Value                                                    |
|--------------------|----------------------------------------------------------|
| **Document ID**    | R210-LLD-01                                              |
| **Version**        | 1.1                                                      |
| **Date**           | 2026-08-12                                               |
| **Component**      | SQLite Database                                          |
| **Source Documents**| R210-SRS-001 v5.4, R210-HLD-001 v3.4                   |
| **Status**         | Draft                                                    |

---

## 1. Purpose

This document specifies the complete SQLite database schema for the R210 prototype, including all tables, columns, data types, constraints, indexes, and triggers. It serves as the single source of truth for database structure and is the direct input for the Database Initializer (R210-LLD-05).

---

## 2. Database Configuration

### 2.1 Connection Pragmas

Every database connection shall execute the following pragmas immediately after opening:

```sql
PRAGMA foreign_keys = ON;       -- SRS-032: FK enforcement
PRAGMA journal_mode = WAL;      -- Write-Ahead Logging for crash safety
PRAGMA busy_timeout = 5000;     -- 5-second wait on lock contention
```

**Rationale:** `foreign_keys` defaults to OFF in SQLite and must be enabled per-connection. WAL mode is selected for crash safety (not concurrency — the prototype is single-writer). `busy_timeout` prevents immediate failures if the CLI and generator briefly contend.

### 2.2 Schema Version Tracking

```sql
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER NOT NULL,
    applied_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    description TEXT
);
```

| Column        | Type    | Constraints           | Description                              |
|---------------|---------|----------------------|------------------------------------------|
| `version`     | INTEGER | NOT NULL              | Monotonically increasing schema version  |
| `applied_at`  | TEXT    | NOT NULL, default now | ISO 8601 UTC timestamp of migration      |
| `description` | TEXT    | —                     | Human-readable migration description     |

**SRS trace:** SRS-097 (record schema version).

---

## 3. Table Definitions

### 3.1 SourceRequirements

**SRS trace:** SRS-039, SRS-040, SRS-041, SRS-035.

```sql
CREATE TABLE SourceRequirements (
    id               INTEGER PRIMARY KEY,
    unique_key       TEXT    NOT NULL UNIQUE,
    source_reference TEXT    NOT NULL,
    source_text      TEXT,                        -- NULL when not retainable (SRS-040)
    status           TEXT    NOT NULL DEFAULT 'pending_review'
                     CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
    review_note      TEXT
);
```

| Column             | Type    | Nullable | Default          | Constraints                    |
|--------------------|---------|----------|------------------|-------------------------------|
| `id`               | INTEGER | No       | autoincrement    | PRIMARY KEY                    |
| `unique_key`       | TEXT    | No       | —                | UNIQUE                         |
| `source_reference` | TEXT    | No       | —                | NOT NULL                       |
| `source_text`      | TEXT    | Yes      | NULL             | —                              |
| `status`           | TEXT    | No       | `pending_review` | CHECK (5-state)                |
| `review_note`      | TEXT    | Yes      | NULL             | —                              |

**Indexes:**

```sql
CREATE INDEX idx_source_requirements_status ON SourceRequirements(status);
CREATE INDEX idx_source_requirements_source_reference ON SourceRequirements(source_reference);
```

---

### 3.2 TypeDefinitions

**SRS trace:** SRS-042, SRS-043, SRS-035, SRS-041.

```sql
CREATE TABLE TypeDefinitions (
    id                      INTEGER PRIMARY KEY,
    unique_key              TEXT    NOT NULL UNIQUE,
    name                    TEXT    NOT NULL,
    kind                    TEXT    NOT NULL
                            CHECK (kind IN ('simple_typedef','array','struct','enum')),
    description             TEXT,
    source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
    status                  TEXT    NOT NULL DEFAULT 'pending_review'
                            CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
    review_note             TEXT
);
```

| Column                  | Type    | Nullable | Default          | Constraints                                |
|-------------------------|---------|----------|------------------|--------------------------------------------|
| `id`                    | INTEGER | No       | autoincrement    | PRIMARY KEY                                |
| `unique_key`            | TEXT    | No       | —                | UNIQUE                                     |
| `name`                  | TEXT    | No       | —                | NOT NULL                                   |
| `kind`                  | TEXT    | No       | —                | CHECK (4-value enum)                       |
| `description`           | TEXT    | Yes      | NULL             | —                                          |
| `source_requirement_id` | INTEGER | Yes      | NULL             | FK → SourceRequirements(id)                |
| `status`                | TEXT    | No       | `pending_review` | CHECK (5-state)                            |
| `review_note`           | TEXT    | Yes      | NULL             | —                                          |

**Indexes:**

```sql
CREATE INDEX idx_type_definitions_kind ON TypeDefinitions(kind);
CREATE INDEX idx_type_definitions_status ON TypeDefinitions(status);
CREATE INDEX idx_type_definitions_source_req ON TypeDefinitions(source_requirement_id);
CREATE INDEX idx_type_definitions_name_kind ON TypeDefinitions(name COLLATE NOCASE, kind);
```

The `idx_type_definitions_name_kind` index supports the duplicate-detection query (SRS-034).

---

### 3.3 SimpleTypeDefinitions

**SRS trace:** SRS-047.

```sql
CREATE TABLE SimpleTypeDefinitions (
    id                  INTEGER PRIMARY KEY,
    unique_key          TEXT    NOT NULL UNIQUE,
    type_definition_id  INTEGER NOT NULL UNIQUE REFERENCES TypeDefinitions(id),
    base_type           TEXT    NOT NULL,
    size                TEXT                          -- optional (SRS-047)
);
```

| Column               | Type    | Nullable | Constraints                             |
|----------------------|---------|----------|-----------------------------------------|
| `id`                 | INTEGER | No       | PRIMARY KEY                              |
| `unique_key`         | TEXT    | No       | UNIQUE                                   |
| `type_definition_id` | INTEGER | No       | UNIQUE, FK → TypeDefinitions(id)         |
| `base_type`          | TEXT    | No       | NOT NULL                                 |
| `size`               | TEXT    | Yes      | —                                        |

**Note:** `type_definition_id` is UNIQUE to enforce SRS-038a (exactly one subtype row per parent). `size` is TEXT to accommodate values like `"16 bit"`, `"32"`, etc. — the exact format is TBD per SRS-019.

---

### 3.4 ArrayTypeDefinitions

**SRS trace:** SRS-048, SRS-038b.

```sql
CREATE TABLE ArrayTypeDefinitions (
    id                  INTEGER PRIMARY KEY,
    unique_key          TEXT    NOT NULL UNIQUE,
    type_definition_id  INTEGER NOT NULL UNIQUE REFERENCES TypeDefinitions(id),
    element_type_id     INTEGER REFERENCES TypeDefinitions(id),  -- NULL while unresolved (SRS-036a)
    array_size          INTEGER NOT NULL CHECK (array_size >= 1)
);
```

| Column               | Type    | Nullable | Constraints                                       |
|----------------------|---------|----------|--------------------------------------------------|
| `id`                 | INTEGER | No       | PRIMARY KEY                                       |
| `unique_key`         | TEXT    | No       | UNIQUE                                            |
| `type_definition_id` | INTEGER | No       | UNIQUE, FK → TypeDefinitions(id)                  |
| `element_type_id`    | INTEGER | Yes      | FK → TypeDefinitions(id); NULL while unresolved (SRS-036a) |
| `array_size`         | INTEGER | No       | CHECK (≥ 1)                                       |

**Resolution rule (SRS-036a):** a NULL `element_type_id` requires an
`unresolved_reference` review issue and blocks approval/export until resolved.

---

### 3.5 StructElements

**SRS trace:** SRS-049, SRS-037, SRS-038b, SRS-038c.

```sql
CREATE TABLE StructElements (
    id                  INTEGER PRIMARY KEY,
    unique_key          TEXT    NOT NULL UNIQUE,
    struct_type_id      INTEGER NOT NULL REFERENCES TypeDefinitions(id),
    name                TEXT    NOT NULL,
    element_type_id     INTEGER REFERENCES TypeDefinitions(id),  -- NULL while unresolved (SRS-036a)
    position            INTEGER NOT NULL CHECK (position >= 1),
    description         TEXT,
    status              TEXT    NOT NULL DEFAULT 'pending_review'
                        CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),

    UNIQUE (struct_type_id, position),
    UNIQUE (struct_type_id, name)
);
```

| Column            | Type    | Nullable | Constraints                                          |
|-------------------|---------|----------|------------------------------------------------------|
| `id`              | INTEGER | No       | PRIMARY KEY                                           |
| `unique_key`      | TEXT    | No       | UNIQUE                                                |
| `struct_type_id`  | INTEGER | No       | FK → TypeDefinitions(id)                              |
| `name`            | TEXT    | No       | NOT NULL; UNIQUE within struct                        |
| `element_type_id` | INTEGER | Yes      | FK → TypeDefinitions(id); NULL while unresolved (SRS-036a) |
| `position`        | INTEGER | No       | CHECK ≥ 1; UNIQUE within struct                       |
| `description`     | TEXT    | Yes      | —                                                     |
| `status`          | TEXT    | No       | CHECK (5-state)                                       |

**Indexes:**

```sql
CREATE INDEX idx_struct_elements_parent ON StructElements(struct_type_id);
```

---

### 3.6 EnumValues

**SRS trace:** SRS-050, SRS-037, SRS-038b, SRS-038c.

```sql
CREATE TABLE EnumValues (
    id                  INTEGER PRIMARY KEY,
    unique_key          TEXT    NOT NULL UNIQUE,
    enum_type_id        INTEGER NOT NULL REFERENCES TypeDefinitions(id),
    name                TEXT    NOT NULL,
    value               TEXT,                         -- optional explicit value (SRS-050)
    position            INTEGER NOT NULL CHECK (position >= 1),
    description         TEXT,
    status              TEXT    NOT NULL DEFAULT 'pending_review'
                        CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),

    UNIQUE (enum_type_id, position),
    UNIQUE (enum_type_id, name)
);
```

| Column         | Type    | Nullable | Constraints                      |
|---------------|---------|----------|----------------------------------|
| `id`          | INTEGER | No       | PRIMARY KEY                       |
| `unique_key`  | TEXT    | No       | UNIQUE                            |
| `enum_type_id`| INTEGER | No       | FK → TypeDefinitions(id)          |
| `name`        | TEXT    | No       | NOT NULL; UNIQUE within enum      |
| `value`       | TEXT    | Yes      | optional explicit value           |
| `position`    | INTEGER | No       | CHECK ≥ 1; UNIQUE within enum     |
| `description` | TEXT    | Yes      | —                                 |
| `status`      | TEXT    | No       | CHECK (5-state)                   |

**Indexes:**

```sql
CREATE INDEX idx_enum_values_parent ON EnumValues(enum_type_id);
```

---

### 3.7 PortInterfaces

**SRS trace:** SRS-051, SRS-052, SRS-035, SRS-041.

```sql
CREATE TABLE PortInterfaces (
    id                      INTEGER PRIMARY KEY,
    unique_key              TEXT    NOT NULL UNIQUE,
    name                    TEXT    NOT NULL,
    description             TEXT,
    source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
    interface_type          TEXT    NOT NULL
                            CHECK (interface_type IN ('sender_receiver','client_server')),
    status                  TEXT    NOT NULL DEFAULT 'pending_review'
                            CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
    review_note             TEXT
);
```

| Column                  | Type    | Nullable | Constraints                       |
|-------------------------|---------|----------|-----------------------------------|
| `id`                    | INTEGER | No       | PRIMARY KEY                        |
| `unique_key`            | TEXT    | No       | UNIQUE                             |
| `name`                  | TEXT    | No       | NOT NULL                           |
| `description`           | TEXT    | Yes      | —                                  |
| `source_requirement_id` | INTEGER | Yes      | FK → SourceRequirements(id)        |
| `interface_type`        | TEXT    | No       | CHECK (2-value)                    |
| `status`                | TEXT    | No       | CHECK (5-state)                    |
| `review_note`           | TEXT    | Yes      | —                                  |

**Indexes:**

```sql
CREATE INDEX idx_port_interfaces_type ON PortInterfaces(interface_type);
CREATE INDEX idx_port_interfaces_status ON PortInterfaces(status);
CREATE INDEX idx_port_interfaces_source_req ON PortInterfaces(source_requirement_id);
CREATE INDEX idx_port_interfaces_name_type ON PortInterfaces(name COLLATE NOCASE, interface_type);
```

---

### 3.8 InterfaceDataElements

**SRS trace:** SRS-056, SRS-037, SRS-038b.

```sql
CREATE TABLE InterfaceDataElements (
    id                  INTEGER PRIMARY KEY,
    unique_key          TEXT    NOT NULL UNIQUE,
    port_interface_id   INTEGER NOT NULL REFERENCES PortInterfaces(id),
    name                TEXT    NOT NULL,
    type_definition_id  INTEGER REFERENCES TypeDefinitions(id),  -- NULL while unresolved (SRS-036a)
    position            INTEGER NOT NULL CHECK (position >= 1),
    description         TEXT,
    status              TEXT    NOT NULL DEFAULT 'pending_review'
                        CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),

    UNIQUE (port_interface_id, position)
);
```

**Indexes:**

```sql
CREATE INDEX idx_interface_data_elements_parent ON InterfaceDataElements(port_interface_id);
```

---

### 3.9 ClientServerOperations

**SRS trace:** SRS-057, SRS-037, SRS-038b.

```sql
CREATE TABLE ClientServerOperations (
    id                  INTEGER PRIMARY KEY,
    unique_key          TEXT    NOT NULL UNIQUE,
    port_interface_id   INTEGER NOT NULL REFERENCES PortInterfaces(id),
    name                TEXT    NOT NULL,
    position            INTEGER NOT NULL CHECK (position >= 1),
    description         TEXT,
    status              TEXT    NOT NULL DEFAULT 'pending_review'
                        CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),

    UNIQUE (port_interface_id, position)
);
```

**Indexes:**

```sql
CREATE INDEX idx_client_server_operations_parent ON ClientServerOperations(port_interface_id);
```

---

### 3.10 OperationArguments

**SRS trace:** SRS-058, SRS-059, SRS-037, SRS-038b.

```sql
CREATE TABLE OperationArguments (
    id                  INTEGER PRIMARY KEY,
    unique_key          TEXT    NOT NULL UNIQUE,
    operation_id        INTEGER NOT NULL REFERENCES ClientServerOperations(id),
    name                TEXT    NOT NULL,
    type_definition_id  INTEGER REFERENCES TypeDefinitions(id),  -- NULL while unresolved (SRS-036a)
    direction           TEXT    NOT NULL
                        CHECK (direction IN ('input','output','input_output')),
    position            INTEGER NOT NULL CHECK (position >= 1),
    status              TEXT    NOT NULL DEFAULT 'pending_review'
                        CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),

    UNIQUE (operation_id, position)
);
```

**Indexes:**

```sql
CREATE INDEX idx_operation_arguments_parent ON OperationArguments(operation_id);
```

---

### 3.11 PortPrototypes

**SRS trace:** SRS-060, SRS-061, SRS-036, SRS-041.

```sql
CREATE TABLE PortPrototypes (
    id                      INTEGER PRIMARY KEY,
    unique_key              TEXT    NOT NULL UNIQUE,
    name                    TEXT    NOT NULL,
    description             TEXT,
    source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
    port_interface_id       INTEGER REFERENCES PortInterfaces(id),    -- nullable per SRS-036
    direction               TEXT    NOT NULL
                            CHECK (direction IN ('provider','requester')),
    component_reference     TEXT    NOT NULL,
    status                  TEXT    NOT NULL DEFAULT 'pending_review'
                            CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
    review_note             TEXT
);
```

**Indexes:**

```sql
CREATE INDEX idx_port_prototypes_interface ON PortPrototypes(port_interface_id);
CREATE INDEX idx_port_prototypes_direction ON PortPrototypes(direction);
CREATE INDEX idx_port_prototypes_status ON PortPrototypes(status);
CREATE INDEX idx_port_prototypes_source_req ON PortPrototypes(source_requirement_id);
CREATE INDEX idx_port_prototypes_name ON PortPrototypes(name COLLATE NOCASE);
```

---

### 3.12 PortPrototypeFunctions

**SRS trace:** SRS-062, SRS-063.

```sql
CREATE TABLE PortPrototypeFunctions (
    id                  INTEGER PRIMARY KEY,
    unique_key          TEXT    NOT NULL UNIQUE,
    port_prototype_id   INTEGER NOT NULL REFERENCES PortPrototypes(id),
    function_name       TEXT    NOT NULL,
    relationship_type   TEXT    NOT NULL
                        CHECK (relationship_type IN ('access_point','trigger')),
    status              TEXT    NOT NULL DEFAULT 'pending_review'
                        CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope'))
);
```

**Indexes:**

```sql
CREATE INDEX idx_port_prototype_functions_parent ON PortPrototypeFunctions(port_prototype_id);
```

---

### 3.13 PortConnections

**SRS trace:** SRS-065, SRS-041.

```sql
CREATE TABLE PortConnections (
    id                      INTEGER PRIMARY KEY,
    unique_key              TEXT    NOT NULL UNIQUE,
    description             TEXT,
    source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
    status                  TEXT    NOT NULL DEFAULT 'pending_review'
                            CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),
    review_note             TEXT
);
```

**Indexes:**

```sql
CREATE INDEX idx_port_connections_status ON PortConnections(status);
CREATE INDEX idx_port_connections_source_req ON PortConnections(source_requirement_id);
```

---

### 3.14 PortConnectionMembers

**SRS trace:** SRS-066, SRS-070, SRS-037, SRS-038b.

```sql
CREATE TABLE PortConnectionMembers (
    id                  INTEGER PRIMARY KEY,
    unique_key          TEXT    NOT NULL UNIQUE,
    port_connection_id  INTEGER NOT NULL REFERENCES PortConnections(id),
    port_prototype_id   INTEGER NOT NULL REFERENCES PortPrototypes(id),
    position            INTEGER NOT NULL CHECK (position >= 1),
    status              TEXT    NOT NULL DEFAULT 'pending_review'
                        CHECK (status IN ('pending_review','approved','rejected','ambiguous','out_of_scope')),

    UNIQUE (port_connection_id, position),
    UNIQUE (port_connection_id, port_prototype_id)
);
```

The second UNIQUE constraint enforces SRS-070 (no duplicate members within a connection).

**Indexes:**

```sql
CREATE INDEX idx_port_connection_members_parent ON PortConnectionMembers(port_connection_id);
CREATE INDEX idx_port_connection_members_prototype ON PortConnectionMembers(port_prototype_id);
```

---

### 3.15 ReviewIssues

**SRS trace:** SRS-074, SRS-075, SRS-076.

```sql
CREATE TABLE ReviewIssues (
    id                      INTEGER PRIMARY KEY,
    unique_key              TEXT    NOT NULL UNIQUE,
    source_requirement_id   INTEGER REFERENCES SourceRequirements(id),
    artifact_type           TEXT
                            CHECK (artifact_type IN (
                                'type_definition','struct_element','enum_value',
                                'port_interface','interface_data_element',
                                'client_server_operation','operation_argument',
                                'port_prototype','port_prototype_function',
                                'port_connection','port_connection_member'
                            ) OR artifact_type IS NULL),
    artifact_unique_key     TEXT,
    issue_type              TEXT    NOT NULL
                            CHECK (issue_type IN ('ambiguous','incomplete','unresolved_reference','unsupported','out_of_scope')),
    message                 TEXT    NOT NULL,
    status                  TEXT    NOT NULL DEFAULT 'pending'
                            CHECK (status IN ('pending','resolved','rejected')),
    resolution              TEXT,

    -- SRS-074: if artifact_unique_key is set, artifact_type must also be set
    CHECK (artifact_unique_key IS NULL OR artifact_type IS NOT NULL)
);
```

**Indexes:**

```sql
CREATE INDEX idx_review_issues_status ON ReviewIssues(status);
CREATE INDEX idx_review_issues_issue_type ON ReviewIssues(issue_type);
CREATE INDEX idx_review_issues_source_req ON ReviewIssues(source_requirement_id);
CREATE INDEX idx_review_issues_artifact ON ReviewIssues(artifact_type, artifact_unique_key);
```

---

## 4. Referential Integrity Map

This table summarizes all foreign-key relationships.

| Child Table               | Child Column            | Parent Table            | Parent Column | Nullable | Notes                      |
|---------------------------|-------------------------|-------------------------|---------------|----------|----------------------------|
| TypeDefinitions           | source_requirement_id   | SourceRequirements      | id            | Yes      | SRS-041                    |
| SimpleTypeDefinitions     | type_definition_id      | TypeDefinitions         | id            | No       | 1:1 — also UNIQUE          |
| ArrayTypeDefinitions      | type_definition_id      | TypeDefinitions         | id            | No       | 1:1 — also UNIQUE          |
| ArrayTypeDefinitions      | element_type_id         | TypeDefinitions         | id            | Yes      | NULL while unresolved; issue + approval/export gate (SRS-036a) |
| StructElements            | struct_type_id          | TypeDefinitions         | id            | No       |                            |
| StructElements            | element_type_id         | TypeDefinitions         | id            | Yes      | NULL while unresolved; issue + approval/export gate (SRS-036a) |
| EnumValues                | enum_type_id            | TypeDefinitions         | id            | No       |                            |
| PortInterfaces            | source_requirement_id   | SourceRequirements      | id            | Yes      | SRS-041                    |
| InterfaceDataElements     | port_interface_id       | PortInterfaces          | id            | No       |                            |
| InterfaceDataElements     | type_definition_id      | TypeDefinitions         | id            | Yes      | NULL while unresolved; issue + approval/export gate (SRS-036a) |
| ClientServerOperations    | port_interface_id       | PortInterfaces          | id            | No       |                            |
| OperationArguments        | operation_id            | ClientServerOperations  | id            | No       |                            |
| OperationArguments        | type_definition_id      | TypeDefinitions         | id            | Yes      | NULL while unresolved; issue + approval/export gate (SRS-036a) |
| PortPrototypes            | source_requirement_id   | SourceRequirements      | id            | Yes      | SRS-041                    |
| PortPrototypes            | port_interface_id       | PortInterfaces          | id            | Yes      | SRS-036: NULL while unresolved |
| PortPrototypeFunctions    | port_prototype_id       | PortPrototypes          | id            | No       |                            |
| PortConnections           | source_requirement_id   | SourceRequirements      | id            | Yes      | SRS-041                    |
| PortConnectionMembers     | port_connection_id      | PortConnections         | id            | No       |                            |
| PortConnectionMembers     | port_prototype_id       | PortPrototypes          | id            | No       |                            |
| ReviewIssues              | source_requirement_id   | SourceRequirements      | id            | Yes      | SRS-041                    |

**Note:** `ReviewIssues.artifact_unique_key` is a typed polymorphic reference (SRS-074), NOT a FK. It is resolved at application level by querying the table identified by `artifact_type`.

---

## 5. Parent–Child Relationship Map

This table defines which tables participate in parent–child review-status relationships (SRS-046, SRS-053, SRS-035c).

| Parent Table         | Child Table              | Parent FK Column in Child  | Auto-Demotion Applies |
|----------------------|--------------------------|----------------------------|-----------------------|
| TypeDefinitions      | StructElements           | struct_type_id             | Yes (SRS-035c)        |
| TypeDefinitions      | EnumValues               | enum_type_id               | Yes (SRS-035c)        |
| PortInterfaces       | InterfaceDataElements    | port_interface_id          | Yes (SRS-035c)        |
| PortInterfaces       | ClientServerOperations   | port_interface_id          | Yes (SRS-035c)        |
| ClientServerOperations| OperationArguments      | operation_id               | Yes (SRS-035c)        |
| PortPrototypes       | PortPrototypeFunctions   | port_prototype_id          | Yes (SRS-035c)        |
| PortConnections      | PortConnectionMembers    | port_connection_id         | Yes (SRS-035c)        |

**Note:** `SimpleTypeDefinitions` and `ArrayTypeDefinitions` are structural extensions, NOT reviewable children (SRS-035a). They do not carry a `status` field and are not subject to parent–child status propagation.

**Grandparent chain:** `OperationArguments` → `ClientServerOperations` → `PortInterfaces`. When an `OperationArguments` status changes away from `approved`, the system must check and potentially demote both `ClientServerOperations` (direct parent) and `PortInterfaces` (grandparent) in the same transaction.

---

## 6. Status Transition Rules

### 6.1 Artifact Status Transitions (SRS-035b)

```
                    ┌────────────────┐
                    │ pending_review │◀──────────────────────────┐
                    └───────┬────────┘                           │
                            │                                    │
              ┌─────────────┼─────────────┬──────────────┐      │
              ▼             ▼             ▼              ▼      │
        ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┤
        │ approved │  │ rejected │  │ ambiguous│  │out_of_scope│
        └────┬─────┘  └────┬─────┘  └────┬─────┘  └─────┬──────┘
             │              │             │              │
             │              └─────────────┼──────────────┘
             │                            │
             │              to: pending_review
             │
             └──▶ pending_review, rejected
```

**Transition matrix:**

| From \ To          | pending_review | approved | rejected | ambiguous | out_of_scope |
|---------------------|:-:|:-:|:-:|:-:|:-:|
| **pending_review**  | — | ✓ | ✓ | ✓ | ✓ |
| **approved**        | ✓ | — | ✓ | ✗ | ✗ |
| **rejected**        | ✓ | ✗ | — | ✗ | ✗ |
| **ambiguous**       | ✓ | ✓ | ✓ | — | ✓ |
| **out_of_scope**    | ✓ | ✗ | ✗ | ✗ | — |

### 6.2 Review Issue Status Transitions (SRS-035b)

| From \ To    | pending | resolved | rejected |
|--------------|:-:|:-:|:-:|
| **pending**  | — | ✓ | ✓ |
| **resolved** | ✓ | — | ✗ |
| **rejected** | ✓ | ✗ | — |

---

## 7. Naming Conventions for Generated UUIDs

All `unique_key` values shall be generated using Python's `uuid.uuid4()` and stored as lowercase hyphenated strings (e.g., `"a1b2c3d4-e5f6-4789-abcd-ef0123456789"`).

**SRS trace:** SRS-027, SRS-028.

---

## 8. Traceability Matrix (LLD-01 → SRS)

| LLD Section | SRS Requirements |
|-------------|-----------------|
| §2.1 Pragmas | SRS-032 |
| §2.2 Schema Version | SRS-097 |
| §3.1 SourceRequirements | SRS-039, SRS-040, SRS-041, SRS-035 |
| §3.2 TypeDefinitions | SRS-042, SRS-043, SRS-035, SRS-041, SRS-026, SRS-027 |
| §3.3 SimpleTypeDefinitions | SRS-047, SRS-038a |
| §3.4 ArrayTypeDefinitions | SRS-048, SRS-038a, SRS-038b, SRS-036a |
| §3.5 StructElements | SRS-049, SRS-037, SRS-038b, SRS-038c, SRS-035 |
| §3.6 EnumValues | SRS-050, SRS-037, SRS-038b, SRS-038c, SRS-035 |
| §3.7 PortInterfaces | SRS-051, SRS-052, SRS-035, SRS-041 |
| §3.8 InterfaceDataElements | SRS-056, SRS-037, SRS-038b, SRS-035 |
| §3.9 ClientServerOperations | SRS-057, SRS-037, SRS-038b, SRS-035 |
| §3.10 OperationArguments | SRS-058, SRS-059, SRS-037, SRS-038b, SRS-035 |
| §3.11 PortPrototypes | SRS-060, SRS-061, SRS-036, SRS-041, SRS-035 |
| §3.12 PortPrototypeFunctions | SRS-062, SRS-063, SRS-035 |
| §3.13 PortConnections | SRS-065, SRS-041, SRS-035 |
| §3.14 PortConnectionMembers | SRS-066, SRS-070, SRS-037, SRS-038b, SRS-035 |
| §3.15 ReviewIssues | SRS-074, SRS-075, SRS-076 |
| §4 FK Map | SRS-029, SRS-030, SRS-036, SRS-036a, SRS-041 |
| §5 Parent–Child Map | SRS-046, SRS-053, SRS-035c, SRS-035a |
| §6 Status Transitions | SRS-035b |
| §7 UUID Conventions | SRS-027, SRS-028 |

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-10 | Initial LLD derived from SRS v5.0 and HLD v3.0. |
| 1.1     | 2026-08-12 | Aligned with approved SRS-036a: made the four cross-artifact type-reference columns nullable while unresolved and specified issue creation plus approval/export blocking. Existing v1 databases upgrade through LLD-05 V002. |
