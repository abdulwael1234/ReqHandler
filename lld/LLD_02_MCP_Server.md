# Low-Level Design — Python MCP Server

## R210 AUTOSAR Requirements Automation Prototype

| Field              | Value                                                    |
|--------------------|----------------------------------------------------------|
| **Document ID**    | R210-LLD-02                                              |
| **Version**        | 1.2                                                      |
| **Date**           | 2026-08-11                                               |
| **Component**      | Python MCP Server                                        |
| **Source Documents**| R210-SRS-001 v5.2, R210-HLD-001 v3.1, R210-LLD-01 v1.0 |
| **Status**         | Draft                                                    |

---

## 1. Purpose

This document specifies the internal design of the Python MCP Server: its module structure, class hierarchy, validation logic, transaction management, tool handler implementations, and error-reporting conventions. It is the primary reference for implementing the MCP tool surface.

---

## 2. Module Structure

```
r210_mcp/
├── __init__.py
├── server.py                  # MCP server entry point and tool registration
├── db/
│   ├── __init__.py
│   ├── connection.py          # Connection management, pragma setup
│   ├── dal.py                 # Data Access Layer — SQL queries
│   └── models.py              # Dataclass definitions for DB records
├── validation/
│   ├── __init__.py
│   ├── common.py              # Shared validators (UUID, status, position, name normalization)
│   ├── type_definitions.py    # Kind-matching, subtype cardinality
│   ├── port_interfaces.py     # Interface-type matching
│   ├── port_connections.py    # Connection validation (SRS-069–072, SRS-122, SRS-125)
│   └── status.py              # Status transition validation, parent-child checks
├── tools/
│   ├── __init__.py
│   ├── source_requirements.py # create, update, query
│   ├── type_definitions.py    # create, update, query (parent + subtypes + children)
│   ├── port_interfaces.py     # create, update, query (parent + children)
│   ├── port_prototypes.py     # create, update, query (parent + functions)
│   ├── port_connections.py    # create, update, query (parent + members)
│   ├── review_issues.py       # create, update, query
│   ├── review_status.py       # set_review_status
│   ├── reference.py           # resolve_reference
│   └── generation.py          # trigger_generation
├── duplicate_detection.py     # Name-normalization and comparison (SRS-034)
└── errors.py                  # Structured error types
```

---

## 3. Core Classes and Data Structures

### 3.1 Error Response (SRS-083, SRS-109)

```python
@dataclass
class McpError:
    """Structured error returned to MCP callers."""
    operation: str                   # Tool name that failed
    field: Optional[str]             # Invalid field name, or None
    reason: str                      # Human-readable explanation
    affected_key: Optional[str]      # unique_key of affected record, or None

    def to_dict(self) -> dict:
        return {
            "error": {
                "operation": self.operation,
                "field": self.field,
                "reason": self.reason,
                "affected_key": self.affected_key,
            }
        }
```

### 3.2 Success Response

```python
@dataclass
class McpResult:
    """Structured success response returned to MCP callers."""
    unique_key: str
    data: dict                       # Additional fields relevant to the operation
    warnings: list[str]              # Duplicate-detection warnings (SRS-034, SRS-121)

    def to_dict(self) -> dict:
        result = {"unique_key": self.unique_key, **self.data}
        if self.warnings:
            result["warnings"] = self.warnings
        return {"result": result}
```

### 3.3 Database Record Dataclasses

Each table has a corresponding frozen dataclass used for type-safe internal passing. Example:

```python
@dataclass(frozen=True)
class TypeDefinitionRecord:
    id: int
    unique_key: str
    name: str
    kind: str                        # 'simple_typedef' | 'array' | 'struct' | 'enum'
    description: Optional[str]
    source_requirement_id: Optional[int]
    status: str
    review_note: Optional[str]
```

Similar dataclasses exist for every table in LLD-01. All dataclasses are defined in `db/models.py`.

### 3.4 Status Constants

```python
# Artifact status values (SRS-035)
ARTIFACT_STATUSES = frozenset({
    "pending_review", "approved", "rejected", "ambiguous", "out_of_scope"
})

# Review issue status values (SRS-076)
ISSUE_STATUSES = frozenset({"pending", "resolved", "rejected"})

# Permitted artifact status transitions (SRS-035b)
ARTIFACT_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending_review": frozenset({"approved", "rejected", "ambiguous", "out_of_scope"}),
    "approved":       frozenset({"pending_review", "rejected"}),
    "rejected":       frozenset({"pending_review"}),
    "ambiguous":      frozenset({"pending_review", "approved", "rejected", "out_of_scope"}),
    "out_of_scope":   frozenset({"pending_review"}),
}

# Permitted review issue status transitions (SRS-035b)
ISSUE_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending":  frozenset({"resolved", "rejected"}),
    "resolved": frozenset({"pending"}),
    "rejected": frozenset({"pending"}),
}
```

### 3.5 Parent–Child Registry

A compile-time registry that maps parent tables to their child tables and FK columns. Used by `set_review_status` for parent-approval blocking and auto-demotion.

```python
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

# Reverse map: child table → (parent table, fk_column pointing to parent)
CHILD_PARENT_MAP: dict[str, ParentRelation] = {
    "StructElements":          ParentRelation(parent_table="TypeDefinitions", fk_column="struct_type_id"),
    "EnumValues":              ParentRelation(parent_table="TypeDefinitions", fk_column="enum_type_id"),
    "InterfaceDataElements":   ParentRelation(parent_table="PortInterfaces", fk_column="port_interface_id"),
    "ClientServerOperations":  ParentRelation(parent_table="PortInterfaces", fk_column="port_interface_id"),
    "OperationArguments":      ParentRelation(parent_table="ClientServerOperations", fk_column="operation_id"),
    "PortPrototypeFunctions":  ParentRelation(parent_table="PortPrototypes", fk_column="port_prototype_id"),
    "PortConnectionMembers":   ParentRelation(parent_table="PortConnections", fk_column="port_connection_id"),
}
```

---

## 4. Database Connection Management

### 4.1 `db/connection.py`

```python
class DatabaseConnection:
    """Manages SQLite connections with required pragmas."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys = ON")      # SRS-032
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for a single write transaction (SRS-084)."""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read_only(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for read-only operations."""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()
```

**Design decisions:**
- `BEGIN IMMEDIATE` acquires a reserved lock immediately, preventing concurrent writers from deadlocking. This is acceptable because the prototype is single-writer.
- Each MCP tool call gets its own connection via `transaction()` or `read_only()`. No connection pooling is needed for the prototype.

---

## 5. Data Access Layer

### 5.1 `db/dal.py`

The DAL provides parameterized SQL methods. It never performs validation — that responsibility belongs to the validation layer. The DAL is organized by domain.

**Key methods (representative, not exhaustive):**

```python
class DataAccessLayer:
    """Low-level SQL operations. All methods accept a connection parameter."""

    # ── Source Requirements ──────────────────────────────────────
    def insert_source_requirement(self, conn, unique_key, source_reference,
                                   source_text, status, review_note) -> int: ...
    def update_source_requirement(self, conn, record_id, **fields) -> None: ...
    def get_source_requirement_by_key(self, conn, unique_key) -> Optional[Row]: ...
    def query_source_requirements(self, conn, filters: dict) -> list[Row]: ...

    # ── Type Definitions ─────────────────────────────────────────
    def insert_type_definition(self, conn, unique_key, name, kind,
                                description, source_requirement_id,
                                status, review_note) -> int: ...
    def insert_simple_type_definition(self, conn, unique_key,
                                       type_definition_id, base_type, size) -> int: ...
    def insert_array_type_definition(self, conn, unique_key,
                                      type_definition_id, element_type_id,
                                      array_size) -> int: ...
    def insert_struct_element(self, conn, unique_key, struct_type_id, name,
                               element_type_id, position, description, status) -> int: ...
    def insert_enum_value(self, conn, unique_key, enum_type_id, name, value,
                           position, description, status) -> int: ...

    # ── Port Interfaces ──────────────────────────────────────────
    def insert_port_interface(self, conn, unique_key, name, description,
                               source_requirement_id, interface_type,
                               status, review_note) -> int: ...
    def insert_interface_data_element(self, conn, ...) -> int: ...
    def insert_client_server_operation(self, conn, ...) -> int: ...
    def insert_operation_argument(self, conn, ...) -> int: ...

    # ── Port Prototypes ──────────────────────────────────────────
    def insert_port_prototype(self, conn, ...) -> int: ...
    def insert_port_prototype_function(self, conn, ...) -> int: ...

    # ── Port Connections ─────────────────────────────────────────
    def insert_port_connection(self, conn, ...) -> int: ...
    def insert_port_connection_member(self, conn, ...) -> int: ...
    def get_connection_members(self, conn, connection_id) -> list[Row]: ...
    def get_port_prototype_by_id(self, conn, prototype_id) -> Optional[Row]: ...

    # ── Review Issues ────────────────────────────────────────────
    def insert_review_issue(self, conn, ...) -> int: ...
    def update_review_issue(self, conn, record_id, **fields) -> None: ...

    # ── Cross-cutting ────────────────────────────────────────────
    def update_status(self, conn, table: str, record_id: int, new_status: str,
                       review_note: Optional[str]) -> None: ...
    def get_record_by_unique_key(self, conn, table: str, unique_key: str) -> Optional[Row]: ...
    def get_children_statuses(self, conn, child_table: str, fk_column: str,
                               parent_id: int) -> list[str]: ...

    # ── Duplicate Detection ──────────────────────────────────────
    def find_duplicates_by_name(self, conn, table: str, name: str,
                                 kind: Optional[str] = None) -> list[Row]: ...

    # ── UUID Resolution ──────────────────────────────────────────
    def resolve_unique_key(self, conn, unique_key: str) -> Optional[tuple[str, Row]]:
        """Search all tables for a record with the given unique_key.
        Returns (table_name, row) or None."""
        ...
```

**SQL parameterization:** All queries use `?` placeholders — never string interpolation.

---

## 6. Validation Layer

### 6.1 Common Validators (`validation/common.py`)

```python
def validate_uuid_format(value: str, field_name: str) -> None:
    """Raise McpError if value is not a valid UUID string."""

def validate_status(value: str, valid_set: frozenset[str], field_name: str) -> None:
    """Raise McpError if value is not in the valid status set."""

def validate_position(value: Any, field_name: str) -> None:
    """Raise McpError if value is not an integer ≥ 1 (SRS-038b)."""

def validate_not_empty(value: Any, field_name: str) -> None:
    """Raise McpError if value is None or empty string."""

def normalize_name(name: str) -> str:
    """Normalize for duplicate detection (SRS-034):
    1. Strip leading/trailing whitespace
    2. Collapse internal whitespace to single space
    3. Return lowercase
    """
    return re.sub(r'\s+', ' ', name.strip()).lower()

def validate_artifact_type(value: Optional[str], field_name: str) -> None:
    """Raise McpError if value is not in the 11 permitted artifact types or None."""
```

### 6.2 Status Transition Validator (`validation/status.py`)

```python
def validate_artifact_transition(current: str, requested: str) -> None:
    """Raise McpError if the transition is not permitted per SRS-035b."""
    if requested not in ARTIFACT_TRANSITIONS.get(current, frozenset()):
        raise McpValidationError(...)

def validate_issue_transition(current: str, requested: str) -> None:
    """Raise McpError if the transition is not permitted per SRS-035b."""

def check_parent_can_be_approved(conn, dal, parent_table, parent_id) -> list[dict]:
    """Return list of non-approved children if parent is being set to 'approved'.
    Excludes rejected children from evaluation (SRS-092a).
    Returns empty list if all non-rejected children are approved."""
    blockers = []
    for child_rel in PARENT_CHILD_MAP.get(parent_table, []):
        statuses = dal.get_children_statuses(
            conn, child_rel.child_table, child_rel.fk_column, parent_id
        )
        for child_status in statuses:
            if child_status != "approved" and child_status != "rejected":
                blockers.append({
                    "child_table": child_rel.child_table,
                    "status": child_status,
                })
    return blockers

def auto_demote_parent_chain(conn, dal, child_table, child_id) -> list[str]:
    """If the child's parent is 'approved', demote it to 'pending_review'.
    Walk the grandparent chain (SRS-035c).
    Returns list of demoted parent unique_keys for reporting."""
    demoted = []
    current_table = child_table
    current_id = child_id
    while current_table in CHILD_PARENT_MAP:
        rel = CHILD_PARENT_MAP[current_table]
        parent = dal.get_parent_record(conn, rel.parent_table, current_table,
                                        rel.fk_column, current_id)
        if parent is None:
            break
        if parent["status"] == "approved":
            dal.update_status(conn, rel.parent_table, parent["id"],
                              "pending_review", None)
            demoted.append(parent["unique_key"])
        current_table = rel.parent_table
        current_id = parent["id"]
    return demoted
```

### 6.3 Type Definition Validators (`validation/type_definitions.py`)

```python
KIND_SUBTYPE_MAP = {
    "simple_typedef": "SimpleTypeDefinitions",
    "array": "ArrayTypeDefinitions",
    "struct": "StructElements",
    "enum": "EnumValues",
}

def validate_kind_value(kind: str) -> None:
    """Raise if kind not in permitted set (SRS-043)."""

def validate_subtype_matches_kind(kind: str, provided_subtype: str) -> None:
    """Raise if the provided subtype detail does not match the kind (SRS-044)."""

def validate_subtype_required(kind: str, subtype_detail: Optional[dict]) -> None:
    """Raise if subtype detail is missing (SRS-038a)."""

def validate_kind_immutable(existing_kind: str, update_fields: dict) -> None:
    """Raise if 'kind' appears in update_fields (SRS-120)."""

def validate_struct_element_parent_kind(conn, dal, struct_type_id: int) -> None:
    """Raise if the parent TypeDefinition.kind is not 'struct' (SRS-044)."""

def validate_enum_value_parent_kind(conn, dal, enum_type_id: int) -> None:
    """Raise if the parent TypeDefinition.kind is not 'enum' (SRS-044)."""
```

### 6.4 Port Interface Validators (`validation/port_interfaces.py`)

```python
def validate_interface_type(value: str) -> None:
    """Raise if not 'sender_receiver' or 'client_server' (SRS-052)."""

def validate_child_interface_type(conn, dal, port_interface_id: int,
                                    expected_type: str) -> None:
    """Raise if parent's interface_type does not match expected (SRS-055).
    - InterfaceDataElements require 'sender_receiver'
    - ClientServerOperations require 'client_server'
    """

def validate_direction(value: str) -> None:
    """Raise if not 'input', 'output', or 'input_output' (SRS-059)."""
```

### 6.5 Port Connection Validators (`validation/port_connections.py`)

```python
def validate_connection_complete(conn, dal, connection_id: int) -> list[McpError]:
    """Full connection validation (SRS-122). Called on every member mutation.
    Checks all four rules and returns a list of errors (empty = valid).

    1. Member existence — every port_prototype_id exists (SRS-069)
    2. No duplicates — no repeated port_prototype_id (SRS-070)
    3. Interface compatibility — TBD, currently creates ReviewIssue (SRS-125)
    4. Direction cardinality — ≥1 provider + ≥1 requester (SRS-072)
    """

def check_member_existence(conn, dal, members: list[Row]) -> list[McpError]:
    """SRS-069: verify all port_prototype_ids exist."""

def check_no_duplicate_members(members: list[Row]) -> list[McpError]:
    """SRS-070: verify no repeated port_prototype_id within the connection."""

def check_direction_cardinality(conn, dal, members: list[Row]) -> list[McpError]:
    """SRS-072: verify ≥1 provider and ≥1 requester."""

def create_compatibility_review_issue(conn, dal, connection_key: str,
                                       source_req_id: Optional[int]) -> str:
    """SRS-125: TBD fallback — create ReviewIssue noting compatibility not verified.
    Returns the ReviewIssue unique_key."""
```

---

## 7. Tool Handler Implementations

Each tool handler follows this pattern:

```python
def handle_<tool_name>(arguments: dict) -> dict:
    """
    1. Validate inputs (validation layer)
    2. Open transaction (connection.transaction())
    3. Resolve unique_keys to internal ids
    4. Check duplicate detection (if create operation)
    5. Execute DAL operations
    6. Auto-demote parents if needed
    7. Return McpResult or raise McpError
    """
```

### 7.1 Source Requirement Tools

#### `create_source_requirement`

**Input parameters:**

| Parameter          | Type   | Required | Validation                    |
|-------------------|--------|----------|-------------------------------|
| `source_reference` | string | Yes      | Not empty                     |
| `source_text`      | string | No       | —                             |
| `review_note`      | string | No       | —                             |
| `initial_status`   | string | No       | One of `"pending_review"`, `"ambiguous"`, `"out_of_scope"`. Defaults to `"pending_review"` (SRS-035a). Does NOT accept `"approved"` or `"rejected"`. This parameter allows the Gemini skill to tag uncertain records at creation (LLD-03 §4.5). |

**Algorithm:**
1. Validate `source_reference` not empty.
2. Generate `unique_key` = `uuid4()`.
3. Set `status` = `initial_status` if provided, else `"pending_review"` (SRS-035a).
4. Within transaction: `dal.insert_source_requirement(...)`.
5. Return `McpResult(unique_key=..., data={...}, warnings=[])`.

> **Note:** The `initial_status` parameter follows the same contract in all create tools (`create_type_definition`, `create_port_interface`, `create_port_prototype`, `create_port_connection`, and all child-record create tools). It defaults to `"pending_review"` and only accepts the three non-terminal statuses listed above.

#### `update_source_requirement`

**Input parameters:**

| Parameter          | Type   | Required | Validation                          |
|-------------------|--------|----------|-------------------------------------|
| `unique_key`       | string | Yes      | Valid UUID, record exists            |
| `source_reference` | string | No       | Not empty if provided               |
| `source_text`      | string | No       | —                                   |
| `review_note`      | string | No       | —                                   |

**Algorithm:**
1. Validate `unique_key` format.
2. **Reject `status` if present in update fields** (SRS-091a).
3. Within transaction: resolve key → id, update provided fields.
4. Return updated record.

#### `query_source_requirements`

**Input parameters:**

| Parameter  | Type   | Required | Validation |
|-----------|--------|----------|------------|
| `status`   | string | No       | Valid status if provided |
| `source_reference` | string | No | — |

**Algorithm:**
1. Validate filter values.
2. Read-only connection: `dal.query_source_requirements(conn, filters)`.
3. Return list of records.

---

### 7.2 Type Definition Tools

#### `create_type_definition`

**Input parameters:**

| Parameter               | Type   | Required | Validation                                |
|------------------------|--------|----------|-------------------------------------------|
| `name`                  | string | Yes      | Not empty                                 |
| `kind`                  | string | Yes      | One of 4 permitted values (SRS-043)       |
| `description`           | string | No       | —                                         |
| `source_requirement_key`| string | No       | Valid UUID, record exists if provided      |
| `subtype`               | object | Yes      | Required (SRS-038a); must match kind      |

**Subtype object structure by kind:**

- `simple_typedef`: `{ "base_type": str, "size": str? }`
- `array`: `{ "element_type_key": str, "array_size": int }` — `array_size ≥ 1`
- `struct`: `{ "elements": [{ "name": str, "element_type_key": str, "position": int, "description": str? }] }`
- `enum`: `{ "values": [{ "name": str, "value": str?, "position": int, "description": str? }] }`

**Algorithm:**
1. Validate `name`, `kind`, `subtype` presence and kind-matching (SRS-038a, SRS-044).
2. Validate subtype-specific fields (position ≥ 1, array_size ≥ 1, etc.).
3. Validate name uniqueness within struct elements / enum values (SRS-038c).
4. Resolve `source_requirement_key` → id if provided.
5. Resolve `element_type_key` references → ids. Reject NULL (SRS-036a default).
6. Run duplicate-detection on `(name, kind)` (SRS-034).
7. Within transaction:
   a. Insert `TypeDefinitions` row.
   b. Insert subtype detail row(s).
   c. For struct/enum with elements: insert all child rows.
8. Return `McpResult` with warnings if duplicate detected.
9. If duplicate detected and configured, also create `ReviewIssue` (SRS-121).

#### `update_type_definition`

1. Reject `kind` if present (SRS-120: immutable).
2. Reject `status` if present (SRS-091a).
3. Update permitted fields only.

#### `create_struct_element` / `create_enum_value`

1. Validate parent kind matches (SRS-044).
2. Validate position ≥ 1, unique within parent (SRS-037).
3. Validate name unique within parent (SRS-038c).
4. Resolve `element_type_key` → id. Reject NULL (SRS-036a default).
5. Set `status` = `"pending_review"` (SRS-035a).
6. Insert row.
7. Return result.

---

### 7.3 Port Interface Tools

#### `create_port_interface`

**Input parameters:**

| Parameter               | Type   | Required | Validation                            |
|------------------------|--------|----------|---------------------------------------|
| `name`                  | string | Yes      | Not empty                             |
| `interface_type`        | string | Yes      | `sender_receiver` or `client_server`  |
| `description`           | string | No       | —                                     |
| `source_requirement_key`| string | No       | Valid UUID if provided                 |
| `children`              | array  | No       | Must match `interface_type` (SRS-055) |

**Algorithm:**
1. Validate inputs.
2. If children provided, validate they match `interface_type`:
   - `sender_receiver` → data elements only
   - `client_server` → operations (with optional arguments) only
3. Duplicate detection on `(name, interface_type)`.
4. Within transaction:
   a. Insert `PortInterfaces` row.
   b. Insert child rows (data elements, operations, arguments).
5. Return result with warnings.

#### `create_interface_data_element`

1. Validate parent `interface_type` = `sender_receiver` (SRS-055).
2. Validate position ≥ 1, unique within parent.
3. Resolve `type_definition_key` → id.
4. Insert row.

#### `create_client_server_operation`

1. Validate parent `interface_type` = `client_server` (SRS-055).
2. Validate position ≥ 1, unique within parent.
3. Insert row.

#### `create_operation_argument`

1. Validate `direction` ∈ {`input`, `output`, `input_output`} (SRS-059).
2. Validate position ≥ 1, unique within operation.
3. Resolve `type_definition_key` → id.
4. Insert row.

---

### 7.4 Port Prototype Tools

#### `create_port_prototype`

**Input parameters:**

| Parameter               | Type   | Required | Validation                              |
|------------------------|--------|----------|-----------------------------------------|
| `name`                  | string | Yes      | Not empty                               |
| `description`           | string | No       | Free text (SRS-060)                     |
| `direction`             | string | Yes      | `provider` or `requester` (SRS-061)     |
| `port_interface_key`    | string | No       | Nullable — NULL if unresolved (SRS-036) |
| `component_reference`   | string | Yes      | Not empty                               |
| `source_requirement_key`| string | No       | Valid UUID if provided                   |
| `functions`             | array  | No       | PortPrototypeFunctions to create         |

**Algorithm:**
1. Validate inputs.
2. If `port_interface_key` is NULL, create `ReviewIssue` with `issue_type = "unresolved_reference"`.
3. Duplicate detection on `name`.
4. Within transaction:
   a. Insert `PortPrototypes` row.
   b. Insert function rows if provided.
   c. Insert `ReviewIssue` if interface unresolved.
5. Return result.

#### `create_port_prototype_function`

1. Validate `relationship_type` ∈ {`access_point`, `trigger`} (SRS-063).
2. Set `status` = `"pending_review"`.
3. Insert row.

---

### 7.5 Port Connection Tools

#### `create_port_connection`

**Input parameters:**

| Parameter               | Type   | Required | Validation                                |
|------------------------|--------|----------|-------------------------------------------|
| `description`           | string | No       | —                                         |
| `source_requirement_key`| string | No       | Valid UUID if provided                     |
| `members`               | array  | Yes      | Array of `{ port_prototype_key, position }`|

**Algorithm:**
1. Validate members array is not empty.
2. Validate each member's position ≥ 1, unique across members.
3. Resolve all `port_prototype_key` → ids.
4. Within transaction (SRS-122 — single transaction):
   a. Insert `PortConnections` row.
   b. Insert all `PortConnectionMembers` rows.
   c. Run `validate_connection_complete()`:
      - Check member existence (SRS-069).
      - Check no duplicates (SRS-070).
      - Check direction cardinality ≥1 provider, ≥1 requester (SRS-072).
      - Interface compatibility: TBD — create `ReviewIssue` (SRS-125).
   d. If validation fails → rollback entire transaction.
5. Return result.

#### `create_port_connection_member`

**Algorithm:**
1. Validate inputs (position, prototype key).
2. Within transaction (SRS-122):
   a. Insert member row.
   b. Re-run `validate_connection_complete()` on the entire connection.
   c. If validation fails → rollback.
3. Return result.

---

### 7.6 Review Issue Tools

#### `create_review_issue`

**Input parameters:**

| Parameter               | Type   | Required | Validation                                |
|------------------------|--------|----------|-------------------------------------------|
| `source_requirement_key`| string | No       | Valid UUID if provided                     |
| `artifact_type`         | string | No       | One of 11 permitted values or NULL         |
| `artifact_unique_key`   | string | No       | Must be set together with `artifact_type` (SRS-074) |
| `issue_type`            | string | Yes      | One of 5 permitted values (SRS-075)       |
| `message`               | string | Yes      | Not empty                                 |

**Algorithm:**
1. Validate `issue_type` ∈ permitted values.
2. Validate pairing: `artifact_type` and `artifact_unique_key` must both be set or both be NULL (SRS-074).
3. Set `status` = `"pending"`.
4. Within transaction: insert row.
5. Return result.

#### `update_review_issue`

**Input parameters:**

| Parameter   | Type   | Required | Validation                          |
|------------|--------|----------|-------------------------------------|
| `unique_key`| string | Yes      | Valid UUID, record exists            |
| `status`    | string | No       | Valid transition per SRS-035b       |
| `resolution`| string | No       | —                                   |
| `message`   | string | No       | Not empty if provided               |

**Algorithm:**
1. Resolve unique_key → record.
2. If `status` provided: validate transition (SRS-035b for issues).
3. Within transaction: update fields.
4. Return updated record.

---

### 7.7 Review Status Tool

#### `set_review_status`

This is the sole mechanism for changing artifact and reviewable-child status (SRS-091a). It does NOT handle `ReviewIssues` (use `update_review_issue` per SRS-119) or structural subtype tables (`SimpleTypeDefinitions`, `ArrayTypeDefinitions`) which have no `status` field.

**Input parameters:**

| Parameter    | Type   | Required | Validation                              |
|-------------|--------|----------|-----------------------------------------|
| `unique_key` | string | Yes      | Valid UUID, record exists                |
| `table_hint` | string | Yes      | Table name to search                    |
| `new_status` | string | Yes      | Valid artifact status (SRS-035)          |
| `review_note`| string | No       | Stored only when the target table has a `review_note` column; silently ignored otherwise |
| `caller`     | string | Yes      | `"extraction"` when called from Gemini skill; `"review"` for manual review. The server validates this against its configured adapter mode (set at construction time) — an adapter constructed in extraction mode rejects `caller="review"` and vice versa, preventing parameter forgery. |

**Algorithm:**

```
1. Validate caller matches self._adapter_mode:
   → If caller != self._adapter_mode, raise McpError(
     "caller does not match server adapter_mode")
2. Resolve unique_key → (table, record)
3. Reject if table is ReviewIssues:
   → raise McpError("Use update_review_issue for review-issue status changes")
4. Reject if table is SimpleTypeDefinitions or ArrayTypeDefinitions:
   → raise McpError("Structural subtype tables do not have a status field")
5. Validate transition: current status → new_status (SRS-035b, ARTIFACT_TRANSITIONS)
6. If new_status == "approved":
   a. If self._adapter_mode == "extraction" → raise McpError(
      "Approval is reserved for manual review (SRS-082a)")
   b. If table is a parent table:
      check_parent_can_be_approved(conn, dal, table, record.id)
      — Excludes rejected children from evaluation (SRS-046, SRS-053, SRS-092a)
      If blockers found → raise McpError listing non-approved children
7. Within transaction:
   a. Update status
   b. If table has review_note column AND review_note provided: update review_note
   c. If the table is a child table AND new_status != "approved":
      auto_demote_parent_chain(conn, dal, table, record.id) → demoted_keys
      (SRS-035c)
8. Return result including any demoted parent keys
```

**Tables with `review_note` column:** SourceRequirements, TypeDefinitions, PortInterfaces, PortPrototypes, PortConnections. All other reviewable tables (StructElements, EnumValues, InterfaceDataElements, ClientServerOperations, OperationArguments, PortConnectionMembers, PortPrototypeFunctions) do not have `review_note`.

**Parent-approval check detail (SRS-046, SRS-053, SRS-092a):**

When approving a parent, query all children. Exclude children with `status = "rejected"`. All remaining children must be `status = "approved"`. If any non-rejected child is not approved, block the approval with a descriptive error listing the blocking children and their statuses.

---

### 7.8 Reference Resolution Tool

#### `resolve_reference`

**Input:** `unique_key: str`

**Algorithm:**
1. Search each table in order: SourceRequirements, TypeDefinitions, SimpleTypeDefinitions, ArrayTypeDefinitions, StructElements, EnumValues, PortInterfaces, InterfaceDataElements, ClientServerOperations, OperationArguments, PortPrototypes, PortPrototypeFunctions, PortConnections, PortConnectionMembers, ReviewIssues.
2. Return first match: `{ "table": table_name, "record": row_as_dict }`.
3. If not found, return error.

---

### 7.9 Generation Trigger Tool

#### `trigger_generation`

**Input:** `mode: str` — `"r210_only"`, `"report_only"`, or `"both"`.

**Algorithm:**
1. Validate mode.
2. Invoke the deterministic generator (LLD-04) with the requested mode.
3. Return the generation result (file paths, counts, validation errors/warnings).

This tool delegates to the Generator component — see LLD-04 for the generation logic.

---

## 8. Duplicate Detection (`duplicate_detection.py`)

**SRS trace:** SRS-034, SRS-121.

```python
def check_for_duplicates(conn, dal, table: str, name: str,
                          kind: Optional[str] = None) -> list[dict]:
    """
    1. Normalize name: strip, collapse whitespace, lowercase
    2. Query existing records of same table (and kind if applicable)
    3. Normalize each existing name and compare
    4. Return list of potential duplicates with unique_key and name
    """
    normalized = normalize_name(name)
    candidates = dal.find_duplicates_by_name(conn, table, normalized, kind)
    return [
        {"unique_key": c["unique_key"], "name": c["name"]}
        for c in candidates
        if normalize_name(c["name"]) == normalized
    ]
```

---

## 9. MCP Server Entry Point (`server.py`)

```python
class R210McpServer:
    """MCP server main class. Registers all tools and dispatches calls.

    The adapter_mode parameter binds the server's authority at construction
    time (SRS-082a). When adapter_mode="extraction" (Gemini workflow),
    approval transitions are structurally forbidden and query results are
    projected per §11. When adapter_mode="review" (Local Review CLI),
    approval is permitted and full records are returned.
    """

    VALID_MODES = frozenset({"extraction", "review"})

    def __init__(self, db_path: str, adapter_mode: str = "extraction"):
        if adapter_mode not in self.VALID_MODES:
            raise ValueError(f"adapter_mode must be one of {self.VALID_MODES}")
        self._adapter_mode = adapter_mode
        self._db = DatabaseConnection(db_path)
        self._dal = DataAccessLayer()
        self._mcp = McpServer("r210-automation")
        self._register_tools()

    def _register_tools(self):
        """Register all MCP tools with the server."""
        self._tools = tools = {
            "create_source_requirement": self._handle_create_source_requirement,
            "update_source_requirement": self._handle_update_source_requirement,
            "query_source_requirements": self._handle_query_source_requirements,
            "create_type_definition": self._handle_create_type_definition,
            "update_type_definition": self._handle_update_type_definition,
            "query_type_definitions": self._handle_query_type_definitions,
            "create_struct_element": self._handle_create_struct_element,
            "update_struct_element": self._handle_update_struct_element,
            "create_enum_value": self._handle_create_enum_value,
            "update_enum_value": self._handle_update_enum_value,
            "create_port_interface": self._handle_create_port_interface,
            "update_port_interface": self._handle_update_port_interface,
            "query_port_interfaces": self._handle_query_port_interfaces,
            "create_interface_data_element": self._handle_create_interface_data_element,
            "update_interface_data_element": self._handle_update_interface_data_element,
            "create_client_server_operation": self._handle_create_client_server_operation,
            "update_client_server_operation": self._handle_update_client_server_operation,
            "create_operation_argument": self._handle_create_operation_argument,
            "update_operation_argument": self._handle_update_operation_argument,
            "create_port_prototype": self._handle_create_port_prototype,
            "update_port_prototype": self._handle_update_port_prototype,
            "query_port_prototypes": self._handle_query_port_prototypes,
            "create_port_prototype_function": self._handle_create_port_prototype_function,
            "update_port_prototype_function": self._handle_update_port_prototype_function,
            "create_port_connection": self._handle_create_port_connection,
            "update_port_connection": self._handle_update_port_connection,
            "query_port_connections": self._handle_query_port_connections,
            "create_port_connection_member": self._handle_create_port_connection_member,
            "update_port_connection_member": self._handle_update_port_connection_member,
            "create_review_issue": self._handle_create_review_issue,
            "update_review_issue": self._handle_update_review_issue,
            "query_review_issues": self._handle_query_review_issues,
            "set_review_status": self._handle_set_review_status,
            "resolve_reference": self._handle_resolve_reference,
            "trigger_generation": self._handle_trigger_generation,
        }
        for name, handler in tools.items():
            self._mcp.register_tool(name, handler)

    def run(self):
        """Start the MCP server on stdio transport."""
        self._mcp.run(transport="stdio")

    # ── Public interface for non-MCP callers (e.g., Local Review CLI) ──

    def handle_tool(self, tool_name: str, arguments: dict) -> dict:
        """Dispatch a tool call by name. Used by the Local Review CLI to
        invoke tools without going through the MCP protocol layer."""
        handler = self._tools.get(tool_name)
        if handler is None:
            raise ValueError(f"Unknown tool: {tool_name}")
        return handler(arguments)

    def query_by_table(self, table: str, filters: dict) -> list[dict]:
        """Query a table that has no dedicated query tool (child tables).
        Returns full records when adapter_mode="review"."""
        with self._db.read_only() as conn:
            return self._dal.query_table(conn, table, filters)

    def get_children_for_display(self, table: str, record: dict) -> list[dict]:
        """Load child records for a parent record (display purposes)."""
        from r210_mcp.validation.status import PARENT_CHILD_MAP
        children = []
        with self._db.read_only() as conn:
            for child_rel in PARENT_CHILD_MAP.get(table, []):
                rows = self._dal.get_children(
                    conn, child_rel.child_table,
                    child_rel.fk_column, record["id"]
                )
                children.extend([
                    {"table": child_rel.child_table, "record": dict(r)}
                    for r in rows
                ])
        return children

    def get_stats(self) -> dict:
        """Return database statistics: counts by table and status."""
        TABLES_WITH_STATUS = {
            "SourceRequirements", "TypeDefinitions",
            "StructElements", "EnumValues",
            "PortInterfaces", "InterfaceDataElements",
            "ClientServerOperations", "OperationArguments",
            "PortPrototypes", "PortPrototypeFunctions",
            "PortConnections", "PortConnectionMembers",
            "ReviewIssues",
        }
        TABLES_WITHOUT_STATUS = {
            "SimpleTypeDefinitions", "ArrayTypeDefinitions",
        }
        with self._db.read_only() as conn:
            stats = {}
            for table in TABLES_WITH_STATUS | TABLES_WITHOUT_STATUS:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                total = cursor.fetchone()[0]
                by_status = {}
                if table in TABLES_WITH_STATUS:
                    cursor = conn.execute(
                        f"SELECT status, COUNT(*) FROM {table} GROUP BY status"
                    )
                    by_status = {row[0]: row[1] for row in cursor.fetchall()}
                stats[table] = {"total": total, "by_status": by_status}
        return stats
```

**Tool count:** 35 registered tools (13 create + 13 update + 6 query + 3 cross-cutting).

---

## 10. Update Tool: Status Rejection Rule

**SRS trace:** SRS-091a.

Every `update_*` handler enforces the following at the start:

```python
def _reject_status_in_update(arguments: dict, tool_name: str) -> None:
    """Raise McpError if caller attempts to set 'status' through an update tool."""
    if "status" in arguments:
        raise McpValidationError(
            operation=tool_name,
            field="status",
            reason="Status cannot be changed through update tools. "
                   "Use 'set_review_status' instead (SRS-091a).",
            affected_key=arguments.get("unique_key"),
        )
```

### 10.1 Content-Change Demotion Rule

**SRS trace:** SRS-082b.

Every `update_*` handler for artifact or reviewable-child tables enforces the following after applying the update:

```python
def _demote_if_approved(conn, dal, table: str, record_id: int,
                         updated_fields: dict) -> Optional[str]:
    """If the record is currently 'approved' and non-status fields were changed,
    demote to 'pending_review' to force re-review (SRS-082b).
    Returns the demoted unique_key, or None."""
    record = dal.get_record_by_id(conn, table, record_id)
    if record["status"] == "approved" and updated_fields:
        dal.update_status(conn, table, record_id, "pending_review", None)
        # Also demote parents if this is a child table (SRS-035c chain)
        if table in CHILD_PARENT_MAP:
            auto_demote_parent_chain(conn, dal, table, record_id)
        return record["unique_key"]
    return None
```

This applies to: SourceRequirements, TypeDefinitions, PortInterfaces, PortPrototypes, PortConnections, StructElements, EnumValues, InterfaceDataElements, ClientServerOperations, OperationArguments, PortConnectionMembers, PortPrototypeFunctions.

It does NOT apply to structural subtype tables (`SimpleTypeDefinitions`, `ArrayTypeDefinitions`) which have no `status` field — updates to their fields shall trigger demotion on their parent `TypeDefinitions` record instead.

### 10.2 Common Update Algorithm

All `update_*` handlers (except `update_review_issue` which has its own flow) share this algorithm:

```
1. Validate unique_key format.
2. Reject 'status' if present (SRS-091a) — call _reject_status().
3. Reject immutable fields if present (e.g., 'kind' on TypeDefinitions — SRS-120).
4. Within transaction:
   a. Resolve unique_key → (table, record_id).
   b. Apply field-specific validations (same rules as the create counterpart):
      - position ≥ 1, unique within parent (SRS-037)
      - name not empty, unique within parent where applicable (SRS-038c)
      - direction ∈ permitted values (SRS-061, SRS-059)
      - relationship_type ∈ permitted values (SRS-063)
      - FK references resolved where provided
   c. Update permitted fields.
   d. Call _demote_if_approved(conn, dal, table, record_id, updated_fields)
      → may demote the record and its parent chain (SRS-082b, SRS-035c).
5. Return updated record with demotion info.
```

### 10.3 `update_port_connection_member` — Transactional Revalidation

**SRS trace:** SRS-122.

When a port connection member is updated (e.g., `port_prototype_key` or `position` changed), the entire connection must be revalidated within the same transaction:

```python
def _handle_update_port_connection_member(self, args: dict) -> dict:
    """
    1. Resolve member unique_key → record.
    2. Reject 'status' (SRS-091a).
    3. Within transaction:
       a. Update the member record fields.
       b. Call _demote_if_approved() on the member (SRS-082b).
       c. Load the parent PortConnection.
       d. Re-run validate_connection_complete() on the entire connection
          (SRS-069, SRS-070, SRS-072, SRS-122):
          - All members still resolve to existing prototypes?
          - No duplicate prototypes?
          - Direction cardinality still ≥1 provider, ≥1 requester?
       e. If revalidation fails → rollback entire transaction.
    4. Return result.
    """
```

### 10.4 Parent Demotion on Child Creation

**SRS trace:** SRS-035c, SRS-082b.

When a new child record is created on a parent that is already `approved`, the parent's approved status is no longer valid (the new child is `pending_review`). Every `create_*` handler for child tables enforces:

```python
def _demote_parent_on_child_creation(conn, dal, child_table: str,
                                       parent_id: int) -> Optional[str]:
    """If the parent is 'approved', demote it to 'pending_review' because
    a new non-approved child was added. Returns demoted parent unique_key."""
    parent_table = CHILD_PARENT_MAP[child_table].parent_table
    parent = dal.get_record_by_id(conn, parent_table, parent_id)
    if parent["status"] == "approved":
        dal.update_status(conn, parent_table, parent_id, "pending_review", None)
        # Continue chain upward (e.g., OperationArgument → Operation → Interface)
        if parent_table in CHILD_PARENT_MAP:
            auto_demote_parent_chain(conn, dal, parent_table, parent_id)
        return parent["unique_key"]
    return None
```

Applies to all child-creation tools: `create_struct_element`, `create_enum_value`, `create_interface_data_element`, `create_client_server_operation`, `create_operation_argument`, `create_port_prototype_function`, `create_port_connection_member`.

---

## 11. Response Projection for Gemini-Facing Queries

**SRS trace:** SRS-015a.

MCP query tools must restrict their response payload when invoked during the Gemini extraction workflow. This prevents confidential or work-sensitive fields from entering the Gemini API context.

### 11.1 Projection Mechanism

```python
# Fields permitted in Gemini-facing query responses (SRS-015a)
GEMINI_PROJECTION: dict[str, list[str]] = {
    "SourceRequirements":       ["unique_key", "source_reference", "status"],
    "TypeDefinitions":          ["unique_key", "name", "kind", "status"],
    "SimpleTypeDefinitions":    ["unique_key"],
    "ArrayTypeDefinitions":     ["unique_key"],
    "StructElements":           ["unique_key", "name", "status"],
    "EnumValues":               ["unique_key", "name", "status"],
    "PortInterfaces":           ["unique_key", "name", "interface_type", "status"],
    "InterfaceDataElements":    ["unique_key", "name", "status"],
    "ClientServerOperations":   ["unique_key", "name", "status"],
    "OperationArguments":       ["unique_key", "name", "direction", "status"],
    "PortPrototypes":           ["unique_key", "name", "direction", "status"],
    "PortPrototypeFunctions":   ["unique_key", "status"],
    "PortConnections":          ["unique_key", "status"],
    "PortConnectionMembers":    ["unique_key", "status"],
    "ReviewIssues":             ["unique_key", "issue_type", "status"],
}

def project_for_gemini(table: str, record: dict) -> dict:
    """Return only the fields permitted for Gemini context."""
    allowed = GEMINI_PROJECTION.get(table, ["unique_key"])
    return {k: v for k, v in record.items() if k in allowed}
```

### 11.2 Applying Projections

- **Query tools** (`query_*`): When `self._adapter_mode == "extraction"`, apply `project_for_gemini()` to each record in the response list. When `self._adapter_mode == "review"`, return full records. This binds data visibility to the adapter identity, not the transport.
- **Create tools** (`create_*`): Return only `unique_key` and `warnings`. No record fields are included (both modes).
- **Local Review CLI** (LLD-06): Constructs the server with `adapter_mode="review"`, so queries return full records and approval transitions are permitted.

### 11.3 Notes

- `SourceRequirements` does not have a `name` field; `source_reference` serves as its external identifier in the projection.
- `ReviewIssues` includes `issue_type` to allow the skill to be aware of existing issues during extraction.
- Both `source_reference` and `issue_type` are included in the SRS-015a allowlist.

---

## 12. Traceability Matrix (LLD-02 → SRS)

| LLD Section | SRS Requirements |
|-------------|-----------------|
| §3.1 Error Response | SRS-083, SRS-109 |
| §3.4 Status Constants | SRS-035, SRS-035b, SRS-076 |
| §3.5 Parent–Child Registry | SRS-046, SRS-053, SRS-035c |
| §4 Connection Mgmt | SRS-032, SRS-084 |
| §6.1 Common Validators | SRS-034, SRS-038b, SRS-074 |
| §6.2 Status Validators | SRS-035b, SRS-046, SRS-053, SRS-092a, SRS-035c |
| §6.3 Type Def Validators | SRS-043, SRS-044, SRS-038a, SRS-120 |
| §6.4 Port Interface Validators | SRS-052, SRS-055, SRS-059 |
| §6.5 Port Connection Validators | SRS-069, SRS-070, SRS-071, SRS-072, SRS-122, SRS-125 |
| §7.1 Source Req Tools | SRS-085, SRS-035a, SRS-091a |
| §7.2 Type Def Tools | SRS-086, SRS-038a, SRS-044, SRS-034, SRS-121, SRS-036a, SRS-120 |
| §7.3 Port Interface Tools | SRS-086, SRS-055 |
| §7.4 Port Prototype Tools | SRS-086, SRS-036, SRS-061, SRS-063 |
| §7.5 Port Connection Tools | SRS-086, SRS-069, SRS-070, SRS-072, SRS-122, SRS-125 |
| §7.6 Review Issue Tools | SRS-088, SRS-119, SRS-074, SRS-075, SRS-076 |
| §7.7 Review Status Tool | SRS-082a, SRS-089, SRS-091a, SRS-035b, SRS-035c, SRS-046, SRS-053, SRS-092a |
| §7.8 Reference Resolution | SRS-087 |
| §7.9 Generation Trigger | SRS-090 |
| §8 Duplicate Detection | SRS-034, SRS-121 |
| §10 Status Rejection | SRS-091a |
| §10.1 Content-Change Demotion | SRS-082b, SRS-035c |
| §10.2 Common Update Algorithm | SRS-091a, SRS-037, SRS-038c, SRS-082b |
| §10.3 Connection Member Update | SRS-122, SRS-069, SRS-070, SRS-072 |
| §10.4 Parent Demotion on Child Creation | SRS-035c, SRS-082b |

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-10 | Initial LLD derived from SRS v5.0, HLD v3.0, and LLD-01 v1.0. |
| 1.1     | 2026-08-10 | Post-review amendments: Fixed tool count from 33 to 35 (§9). Rewrote §7.7 `set_review_status`: scoped to artifacts/reviewable children only; added `caller` parameter for SRS-082a enforcement; ReviewIssues and structural subtypes rejected with explicit error; `review_note` silently ignored when column absent. Added §10.1 content-change demotion (SRS-082b). Added §11 response projection for Gemini-facing queries with `GEMINI_PROJECTION` dict and `project_for_gemini()` (SRS-015a). Added `description` parameter to `create_port_prototype` (SRS-060). Added §10.2 common update algorithm with full validation. Added §10.3 transactional revalidation for `update_port_connection_member` (SRS-122). Added §10.4 parent demotion on child creation (SRS-035c). Renumbered traceability matrix to §12. |
| 1.2     | 2026-08-11 | Review-driven fixes: Made `caller` required and validated against `adapter_mode` (C-04). Added `adapter_mode` to server constructor binding authority structurally (SRS-082a). Projection now conditional on adapter_mode, not transport (M-07). Fixed SourceRequirements projection from `name` to `source_reference` (C-05). Added `initial_status` parameter to all create tools (H-02). Fixed ReviewIssue `artifact_type`/`artifact_unique_key` pairing to be bidirectional (M-05). Added SRS-082a to §7.7 traceability (M-01). Updated source references to SRS v5.2, HLD v3.1. |
