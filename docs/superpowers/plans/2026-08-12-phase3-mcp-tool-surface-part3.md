# Phase 3 Implementation Plan — Part 3: Entity Validators and the First Handlers

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Read Part 1 first:** `docs/superpowers/plans/2026-08-12-phase3-mcp-tool-surface.md` for Goal, Architecture and Global Constraints. **Part 2** (`...-part2.md`) builds the engine these tasks consume.

**Covers:** Tasks 11–15 — the three entity validator modules, and the source-requirement and type-definition handlers.

---

## Task 11: `validation/type_definitions.py`

**Files:**
- Create: `src/r210_mcp/validation/type_definitions.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_validation/test_type_definitions.py`

**Interfaces:**
- Consumes: `McpValidationError` (Task 1), `validate_choice` (Task 3), `DataAccessLayer.get_type_definition_by_id`.
- Produces:
  - `KINDS: frozenset[str]` — `{"simple_typedef", "array", "struct", "enum"}`
  - `KIND_SUBTYPE_MAP: dict[str, str]` — kind → the table holding its detail
  - `validate_kind_value(kind, *, operation) -> None`
  - `validate_subtype_matches_kind(kind, subtype, *, operation) -> None`
  - `validate_parent_kind(conn, dal, type_definition_id, expected_kind, *, operation, field) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_validation/test_type_definitions.py`:

```python
"""Development tests for the type-definition validators (LLD-02 §6.3)."""

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.validation.type_definitions import (
    KIND_SUBTYPE_MAP,
    KINDS,
    validate_kind_value,
    validate_parent_kind,
    validate_subtype_matches_kind,
)


class TestKinds:
    def test_the_four_permitted_kinds(self) -> None:
        """SRS-043 — kind is one of four values."""
        assert KINDS == frozenset({"simple_typedef", "array", "struct", "enum"})
        assert set(KIND_SUBTYPE_MAP) == KINDS

    def test_rejects_an_unknown_kind(self) -> None:
        with pytest.raises(McpValidationError) as caught:
            validate_kind_value("record", operation="create_type_definition")
        assert caught.value.error.field == "kind"


class TestSubtypeMatchesKind:
    def test_accepts_the_matching_shape(self) -> None:
        """SRS-038a, SRS-044 — the subtype detail must match the kind."""
        validate_subtype_matches_kind(
            "simple_typedef", {"base_type": "uint8"}, operation="create_type_definition"
        )
        validate_subtype_matches_kind(
            "array", {"array_size": 4}, operation="create_type_definition"
        )
        validate_subtype_matches_kind(
            "struct", {"elements": []}, operation="create_type_definition"
        )
        validate_subtype_matches_kind("enum", {"values": []}, operation="create_type_definition")

    def test_missing_subtype_is_rejected(self) -> None:
        """SRS-038a — the subtype detail is required."""
        with pytest.raises(McpValidationError) as caught:
            validate_subtype_matches_kind("array", None, operation="create_type_definition")
        assert caught.value.error.field == "subtype"

    def test_wrong_shape_is_rejected(self) -> None:
        """SRS-044 — an array subtype on a struct kind is a mismatch."""
        with pytest.raises(McpValidationError):
            validate_subtype_matches_kind(
                "struct", {"array_size": 4}, operation="create_type_definition"
            )


class TestParentKind:
    def test_accepts_the_expected_kind(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Mode", "enum")
        with db.read_only() as conn:
            validate_parent_kind(
                conn, dal, parent_id, "enum", operation="create_enum_value", field="enum_type_key"
            )

    def test_rejects_the_wrong_parent_kind(self, initialized_db: str) -> None:
        """SRS-044 — an EnumValue may only hang off an enum."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            parent_id = dal.insert_type_definition(conn, "td", "Speed", "struct")
        with db.read_only() as conn:
            with pytest.raises(McpValidationError) as caught:
                validate_parent_kind(
                    conn,
                    dal,
                    parent_id,
                    "enum",
                    operation="create_enum_value",
                    field="enum_type_key",
                )
        assert caught.value.error.field == "enum_type_key"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_validation/test_type_definitions.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'KINDS'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/validation/type_definitions.py`:

```python
"""Type-definition kind and subtype validators.

See: LLD-02 §6.3 (Type Definition Validators — SRS-038a, SRS-043, SRS-044)
"""

import sqlite3
from typing import Any

from ..db.dal import DataAccessLayer
from ..errors import McpValidationError
from .common import validate_choice

# The four permitted values of TypeDefinitions.kind (SRS-043).
KINDS = frozenset({"simple_typedef", "array", "struct", "enum"})

# kind → the table that carries its detail. `simple_typedef` and `array` use a
# structural subtype row; `struct` and `enum` use reviewable child rows.
KIND_SUBTYPE_MAP: dict[str, str] = {
    "simple_typedef": "SimpleTypeDefinitions",
    "array": "ArrayTypeDefinitions",
    "struct": "StructElements",
    "enum": "EnumValues",
}

# kind → the subtype key that must be present in the `subtype` object.
_KIND_REQUIRED_FIELD: dict[str, str] = {
    "simple_typedef": "base_type",
    "array": "array_size",
    "struct": "elements",
    "enum": "values",
}


def validate_kind_value(kind: Any, *, operation: str) -> None:
    """Reject a kind outside the permitted four (SRS-043)."""
    validate_choice(kind, KINDS, "kind", operation=operation)


def validate_subtype_matches_kind(kind: str, subtype: Any, *, operation: str) -> None:
    """Reject a missing or mismatched subtype detail (SRS-038a, SRS-044)."""
    if not isinstance(subtype, dict):
        raise McpValidationError.of(
            operation,
            f"subtype is required for kind {kind!r} and must be an object (SRS-038a)",
            field="subtype",
        )
    required = _KIND_REQUIRED_FIELD[kind]
    if required not in subtype:
        raise McpValidationError.of(
            operation,
            f"subtype for kind {kind!r} must contain {required!r} (SRS-044)",
            field="subtype",
        )


def validate_parent_kind(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    type_definition_id: int,
    expected_kind: str,
    *,
    operation: str,
    field: str,
) -> None:
    """Reject a child hung off a parent of the wrong kind (SRS-044)."""
    parent = dal.get_type_definition_by_id(conn, type_definition_id)
    if parent is None:
        raise McpValidationError.of(
            operation, f"{field} does not resolve to a TypeDefinitions record", field=field
        )
    if parent.kind != expected_kind:
        raise McpValidationError.of(
            operation,
            f"parent TypeDefinition kind is {parent.kind!r}, expected {expected_kind!r}",
            field=field,
            affected_key=str(parent.unique_key),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_validation/ -q -p no:cacheprovider && python -m mypy src`
Expected: PASS, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/validation/type_definitions.py tests/test_r210_mcp/test_validation/test_type_definitions.py
git commit -m "feat(validation): add type-definition kind and subtype validators"
```

---

## Task 12: `validation/port_interfaces.py`

**Files:**
- Create: `src/r210_mcp/validation/port_interfaces.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_validation/test_port_interfaces.py`

**Interfaces:**
- Produces:
  - `INTERFACE_TYPES: frozenset[str]` — `{"sender_receiver", "client_server"}`
  - `ARGUMENT_DIRECTIONS: frozenset[str]` — `{"input", "output", "input_output"}`
  - `PORT_DIRECTIONS: frozenset[str]` — `{"provider", "requester"}`
  - `RELATIONSHIP_TYPES: frozenset[str]` — `{"access_point", "trigger"}`
  - `CHILD_REQUIRED_INTERFACE_TYPE: dict[str, str]`
  - `validate_child_interface_type(conn, dal, port_interface_id, child_table, *, operation, field) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_validation/test_port_interfaces.py`:

```python
"""Development tests for the port-interface validators (LLD-02 §6.4)."""

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.validation.port_interfaces import (
    ARGUMENT_DIRECTIONS,
    CHILD_REQUIRED_INTERFACE_TYPE,
    INTERFACE_TYPES,
    PORT_DIRECTIONS,
    RELATIONSHIP_TYPES,
    validate_child_interface_type,
)


class TestVocabularies:
    def test_match_the_schema_check_constraints(self) -> None:
        """SRS-052, SRS-059, SRS-061, SRS-063 — the permitted value sets."""
        assert INTERFACE_TYPES == frozenset({"sender_receiver", "client_server"})
        assert ARGUMENT_DIRECTIONS == frozenset({"input", "output", "input_output"})
        assert PORT_DIRECTIONS == frozenset({"provider", "requester"})
        assert RELATIONSHIP_TYPES == frozenset({"access_point", "trigger"})

    def test_children_require_the_right_interface_type(self) -> None:
        """SRS-055 — data elements need sender_receiver, operations client_server."""
        assert CHILD_REQUIRED_INTERFACE_TYPE["InterfaceDataElements"] == "sender_receiver"
        assert CHILD_REQUIRED_INTERFACE_TYPE["ClientServerOperations"] == "client_server"


class TestChildInterfaceType:
    def test_accepts_a_matching_parent(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            iface_id = dal.insert_port_interface(conn, "pi", "Iface", "sender_receiver")
        with db.read_only() as conn:
            validate_child_interface_type(
                conn,
                dal,
                iface_id,
                "InterfaceDataElements",
                operation="create_interface_data_element",
                field="port_interface_key",
            )

    def test_rejects_a_mismatched_parent(self, initialized_db: str) -> None:
        """SRS-055 — a data element cannot hang off a client_server interface."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            iface_id = dal.insert_port_interface(conn, "pi", "Iface", "client_server")
        with db.read_only() as conn:
            with pytest.raises(McpValidationError) as caught:
                validate_child_interface_type(
                    conn,
                    dal,
                    iface_id,
                    "InterfaceDataElements",
                    operation="create_interface_data_element",
                    field="port_interface_key",
                )
        assert caught.value.error.field == "port_interface_key"
        assert "sender_receiver" in caught.value.error.reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_validation/test_port_interfaces.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'INTERFACE_TYPES'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/validation/port_interfaces.py`:

```python
"""Port-interface vocabularies and child-type matching.

The value sets repeat the CHECK constraints in V001 so that a bad value is
rejected with a structured SRS-083 error naming the field, rather than
surfacing as a raw `sqlite3.IntegrityError`.

See: LLD-02 §6.4 (Port Interface Validators — SRS-052, SRS-055, SRS-059)
"""

import sqlite3

from ..db.dal import DataAccessLayer
from ..errors import McpValidationError

INTERFACE_TYPES = frozenset({"sender_receiver", "client_server"})  # SRS-052
ARGUMENT_DIRECTIONS = frozenset({"input", "output", "input_output"})  # SRS-059
PORT_DIRECTIONS = frozenset({"provider", "requester"})  # SRS-061
RELATIONSHIP_TYPES = frozenset({"access_point", "trigger"})  # SRS-063

# Child table → the parent interface_type it requires (SRS-055).
CHILD_REQUIRED_INTERFACE_TYPE: dict[str, str] = {
    "InterfaceDataElements": "sender_receiver",
    "ClientServerOperations": "client_server",
}


def validate_child_interface_type(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    port_interface_id: int,
    child_table: str,
    *,
    operation: str,
    field: str,
) -> None:
    """Reject a child whose parent interface is of the wrong type (SRS-055)."""
    expected = CHILD_REQUIRED_INTERFACE_TYPE[child_table]
    parent = dal.get_port_interface_by_id(conn, port_interface_id)
    if parent is None:
        raise McpValidationError.of(
            operation, f"{field} does not resolve to a PortInterfaces record", field=field
        )
    if parent.interface_type != expected:
        raise McpValidationError.of(
            operation,
            f"{child_table} requires a {expected!r} interface; "
            f"parent is {parent.interface_type!r}",
            field=field,
            affected_key=str(parent.unique_key),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_validation/ -q -p no:cacheprovider && python -m mypy src`
Expected: PASS, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/validation/port_interfaces.py tests/test_r210_mcp/test_validation/test_port_interfaces.py
git commit -m "feat(validation): add port-interface vocabularies and child matching"
```

---

## Task 13: `validation/port_connections.py`

**Files:**
- Create: `src/r210_mcp/validation/port_connections.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_validation/test_port_connections.py`

**Interfaces:**
- Consumes: `DataAccessLayer.get_children`, `.get_record_by_id`, `.insert_review_issue`.
- Produces:
  - `validate_connection_complete(conn, dal, connection_id, *, operation) -> None` — raises on the first failure
  - `create_compatibility_review_issue(conn, dal, connection_key, source_requirement_id) -> str`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_validation/test_port_connections.py`:

```python
"""Development tests for connection validation (LLD-02 §6.5)."""

import pytest

from r210_mcp.db.connection import DatabaseConnection
from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.validation.port_connections import (
    create_compatibility_review_issue,
    validate_connection_complete,
)


def _prototype(dal: DataAccessLayer, conn: object, key: str, direction: str) -> int:
    return dal.insert_port_prototype(conn, key, f"Port{key}", None, None, direction, "ECU")


class TestValidateConnectionComplete:
    def test_accepts_one_provider_and_one_requester(self, initialized_db: str) -> None:
        """SRS-072 — a valid connection has at least one of each."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            provider = _prototype(dal, conn, "p", "provider")
            requester = _prototype(dal, conn, "r", "requester")
            connection_id = dal.insert_port_connection(conn, "pc")
            dal.insert_port_connection_member(conn, "m1", connection_id, provider, 1)
            dal.insert_port_connection_member(conn, "m2", connection_id, requester, 2)
        with db.read_only() as conn:
            validate_connection_complete(
                conn, dal, connection_id, operation="update_port_connection_member"
            )

    def test_rejects_a_missing_requester(self, initialized_db: str) -> None:
        """SRS-072 — direction cardinality requires >=1 provider and >=1 requester."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            provider = _prototype(dal, conn, "p", "provider")
            connection_id = dal.insert_port_connection(conn, "pc")
            dal.insert_port_connection_member(conn, "m1", connection_id, provider, 1)
        with db.read_only() as conn:
            with pytest.raises(McpValidationError) as caught:
                validate_connection_complete(
                    conn, dal, connection_id, operation="update_port_connection_member"
                )
        assert "requester" in caught.value.error.reason

    def test_rejects_a_duplicate_prototype(self, initialized_db: str) -> None:
        """SRS-070 — a prototype appears at most once per connection."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            provider = _prototype(dal, conn, "p", "provider")
            requester = _prototype(dal, conn, "r", "requester")
            connection_id = dal.insert_port_connection(conn, "pc")
            dal.insert_port_connection_member(conn, "m1", connection_id, provider, 1)
            dal.insert_port_connection_member(conn, "m2", connection_id, requester, 2)
            dal.insert_port_connection_member(conn, "m3", connection_id, provider, 3)
        with db.read_only() as conn:
            with pytest.raises(McpValidationError) as caught:
                validate_connection_complete(
                    conn, dal, connection_id, operation="update_port_connection_member"
                )
        assert "duplicate" in caught.value.error.reason.lower()

    def test_rejects_an_empty_connection(self, initialized_db: str) -> None:
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            connection_id = dal.insert_port_connection(conn, "pc")
        with db.read_only() as conn:
            with pytest.raises(McpValidationError):
                validate_connection_complete(
                    conn, dal, connection_id, operation="create_port_connection_member"
                )


class TestCompatibilityIssue:
    def test_creates_an_incomplete_issue(self, initialized_db: str) -> None:
        """SRS-125 — compatibility is TBD, so record it rather than assume it."""
        db, dal = DatabaseConnection(initialized_db), DataAccessLayer()
        with db.transaction() as conn:
            dal.insert_port_connection(conn, "pc")
            create_compatibility_review_issue(conn, dal, "pc", None)
        with db.read_only() as conn:
            issues = dal.query_review_issues(conn, {"artifact_unique_key": "pc"})
        assert len(issues) == 1
        assert issues[0].issue_type == "incomplete"
        assert issues[0].artifact_type == "port_connection"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_validation/test_port_connections.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'validate_connection_complete'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/validation/port_connections.py`:

```python
"""Port-connection completeness validation.

SRS-071 leaves interface compatibility undefined (TBD). SRS-125 therefore
requires the server to accept the connection but record an `incomplete`
ReviewIssue, so that an unverified connection is never silently treated as
validated.

See: LLD-02 §6.5 (Port Connection Validators — SRS-069–072, SRS-122, SRS-125)
"""

import sqlite3
from uuid import uuid4

from ..db.dal import DataAccessLayer
from ..errors import McpValidationError


def validate_connection_complete(
    conn: sqlite3.Connection, dal: DataAccessLayer, connection_id: int, *, operation: str
) -> None:
    """Re-check every rule over a whole connection (SRS-122).

    Raises on the first failure so that the caller's transaction rolls back;
    LLD-02 §6.5 returns a list, but a partially-valid connection must not be
    committed, and `transaction()` rolls back on the exception (LLD-02 §10.3).
    """
    connection = dal.get_record_by_id(conn, "PortConnections", connection_id)
    affected_key = None if connection is None else str(connection.unique_key)

    members = dal.get_children(conn, "PortConnectionMembers", "port_connection_id", connection_id)
    if not members:
        raise McpValidationError.of(
            operation,
            "connection has no members; at least one provider and one requester "
            "are required (SRS-072)",
            field="port_connection_key",
            affected_key=affected_key,
        )

    prototype_ids = [member.port_prototype_id for member in members]
    if len(set(prototype_ids)) != len(prototype_ids):
        raise McpValidationError.of(
            operation,
            "connection contains a duplicate port_prototype reference (SRS-070)",
            field="port_prototype_key",
            affected_key=affected_key,
        )

    directions: list[str] = []
    for prototype_id in prototype_ids:
        prototype = dal.get_record_by_id(conn, "PortPrototypes", prototype_id)
        if prototype is None:
            raise McpValidationError.of(
                operation,
                f"member references PortPrototypes id {prototype_id}, which does "
                "not exist (SRS-069)",
                field="port_prototype_key",
                affected_key=affected_key,
            )
        directions.append(str(prototype.direction))

    for required in ("provider", "requester"):
        if required not in directions:
            raise McpValidationError.of(
                operation,
                f"connection requires at least one {required} member (SRS-072)",
                field="port_prototype_key",
                affected_key=affected_key,
            )


def create_compatibility_review_issue(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    connection_key: str,
    source_requirement_id: int | None,
) -> str:
    """Record that compatibility could not be verified (SRS-125)."""
    issue_key = str(uuid4())
    dal.insert_review_issue(
        conn,
        issue_key,
        source_requirement_id,
        "port_connection",
        connection_key,
        "incomplete",
        "Interface compatibility was not verified: the SRS-071 compatibility "
        "rules are not yet defined (SRS-125).",
    )
    return issue_key
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_validation/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/validation/port_connections.py tests/test_r210_mcp/test_validation/test_port_connections.py
git commit -m "feat(validation): add connection completeness rules and SRS-125 fallback"
```

---

## Task 14: Source-requirement handlers

**Files:**
- Create: `src/r210_mcp/tools/source_requirements.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_tools/test_source_requirements.py`

**Interfaces:**
- Consumes: `run_create`, `run_update`, `run_query`, `CreateSpec`, `UpdateSpec`, `QuerySpec`, `FieldSpec`, `choice_of` (Tasks 7–10); `ARTIFACT_STATUSES` from `db.models`.
- Produces:
  - `handle_create_source_requirement(ctx, arguments) -> dict[str, Any]`
  - `handle_update_source_requirement(ctx, arguments) -> dict[str, Any]`
  - `handle_query_source_requirements(ctx, arguments) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_source_requirements.py`:

```python
"""Development tests for the source-requirement tools (LLD-02 §7.1)."""

import pytest

from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.source_requirements import (
    handle_create_source_requirement,
    handle_query_source_requirements,
    handle_update_source_requirement,
)


class TestCreate:
    def test_creates_with_a_generated_key(self, initialized_db: str) -> None:
        """SRS-085 — the server creates source requirements."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_source_requirement(
            ctx, {"source_reference": "REQ-1", "source_text": "The ECU shall..."}
        )
        assert response["result"]["source_reference"] == "REQ-1"
        assert response["result"]["status"] == "pending_review"

    def test_rejects_an_empty_reference(self, initialized_db: str) -> None:
        """SRS-083 — invalid input names the field."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_source_requirement(ctx, {"source_reference": "  "})
        assert caught.value.error.field == "source_reference"

    def test_accepts_an_initial_status(self, initialized_db: str) -> None:
        """SRS-035a — the skill may tag an uncertain record at creation."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_source_requirement(
            ctx, {"source_reference": "REQ-2", "initial_status": "ambiguous"}
        )
        assert response["result"]["status"] == "ambiguous"

    def test_rejects_approved_as_an_initial_status(self, initialized_db: str) -> None:
        """SRS-082a — a create tool cannot claim approval."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError):
            handle_create_source_requirement(
                ctx, {"source_reference": "REQ-3", "initial_status": "approved"}
            )


class TestUpdate:
    def test_updates_the_text(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = handle_create_source_requirement(ctx, {"source_reference": "REQ-1"})["result"][
            "unique_key"
        ]
        response = handle_update_source_requirement(
            ctx, {"unique_key": key, "source_text": "revised"}
        )
        assert response["result"]["source_text"] == "revised"

    def test_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a — status only through set_review_status."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_source_requirement(ctx, {"source_reference": "REQ-1"})["result"][
            "unique_key"
        ]
        with pytest.raises(McpValidationError) as caught:
            handle_update_source_requirement(ctx, {"unique_key": key, "status": "approved"})
        assert caught.value.error.field == "status"


class TestQuery:
    def test_filters_by_status(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        handle_create_source_requirement(ctx, {"source_reference": "REQ-1"})
        handle_create_source_requirement(
            ctx, {"source_reference": "REQ-2", "initial_status": "out_of_scope"}
        )
        response = handle_query_source_requirements(ctx, {"status": "out_of_scope"})
        assert response["result"]["count"] == 1
        assert response["result"]["records"][0]["source_reference"] == "REQ-2"

    def test_rejects_an_invalid_status_filter(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError):
            handle_query_source_requirements(ctx, {"status": "bogus"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_source_requirements.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'handle_create_source_requirement'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/tools/source_requirements.py`:

```python
"""Source-requirement tools: create, update, query.

See: LLD-02 §7.1 (Source Requirement Tools — SRS-085)
"""

from typing import Any

from ..db.models import ARTIFACT_STATUSES
from ..validation.common import validate_not_empty
from ._engine import (
    CreateSpec,
    FieldSpec,
    QuerySpec,
    UpdateSpec,
    choice_of,
    run_create,
    run_query,
    run_update,
)
from .context import ToolContext

_CREATE = CreateSpec(
    tool="create_source_requirement",
    table="SourceRequirements",
    fields=(
        FieldSpec("source_reference", "source_reference", True, validate_not_empty),
        FieldSpec("source_text", "source_text"),
        FieldSpec("review_note", "review_note"),
    ),
)

_UPDATE = UpdateSpec(
    tool="update_source_requirement",
    table="SourceRequirements",
    fields=(
        FieldSpec("source_reference", "source_reference", validator=validate_not_empty),
        FieldSpec("source_text", "source_text"),
        FieldSpec("review_note", "review_note"),
    ),
)

_QUERY = QuerySpec(
    tool="query_source_requirements",
    table="SourceRequirements",
    filters=(
        FieldSpec("status", "status", validator=choice_of(ARTIFACT_STATUSES)),
        FieldSpec("source_reference", "source_reference"),
    ),
)


def handle_create_source_requirement(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a source requirement (SRS-085)."""
    return run_create(ctx, _CREATE, arguments)


def handle_update_source_requirement(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a source requirement; `status` is rejected (SRS-091a)."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_source_requirements(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Query source requirements (SRS-085)."""
    return run_query(ctx, _QUERY, arguments)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/test_tools/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/source_requirements.py tests/test_r210_mcp/test_tools/test_source_requirements.py
git commit -m "feat(tools): add source-requirement handlers"
```

---

## Task 15: Type-definition handlers

`create_type_definition` is the one create tool the engine cannot drive: it
writes a parent row, a subtype row, and N child rows in a single transaction,
with kind-dependent shapes (LLD-02 §7.2). It is written out explicitly. The
update and query tools use the engine; the struct-element and enum-value
handlers use the engine with a parent-kind pre-check.

**Files:**
- Create: `src/r210_mcp/tools/type_definitions.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_tools/test_type_definitions.py`

**Interfaces:**
- Consumes: Tasks 7–11; `validate_kind_value`, `validate_subtype_matches_kind`, `validate_parent_kind`, `KIND_SUBTYPE_MAP` (Task 11); `check_for_duplicates`, `duplicate_warning` (Task 5); `create_unresolved_issue`, `demote_parent_on_child_creation` (Task 8).
- Produces:
  - `handle_create_type_definition(ctx, arguments) -> dict[str, Any]`
  - `handle_update_type_definition(ctx, arguments) -> dict[str, Any]`
  - `handle_query_type_definitions(ctx, arguments) -> dict[str, Any]`
  - `handle_create_struct_element(ctx, arguments) -> dict[str, Any]`
  - `handle_update_struct_element(ctx, arguments) -> dict[str, Any]`
  - `handle_create_enum_value(ctx, arguments) -> dict[str, Any]`
  - `handle_update_enum_value(ctx, arguments) -> dict[str, Any]`

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_type_definitions.py`:

```python
"""Development tests for the type-definition tools (LLD-02 §7.2)."""

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.type_definitions import (
    handle_create_enum_value,
    handle_create_struct_element,
    handle_create_type_definition,
    handle_query_type_definitions,
    handle_update_type_definition,
)


class TestCreateTypeDefinition:
    def test_creates_a_simple_typedef_with_its_detail_row(self, initialized_db: str) -> None:
        """SRS-038a — exactly one subtype detail row per parent."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        response = handle_create_type_definition(
            ctx,
            {"name": "Speed", "kind": "simple_typedef", "subtype": {"base_type": "uint8"}},
        )
        key = response["result"]["unique_key"]
        with ctx.db.read_only() as conn:
            parent = dal.get_type_definition_by_key(conn, key)
            detail = dal.get_simple_type_definition_by_parent(conn, parent.id)
        assert detail.base_type == "uint8"

    def test_creates_an_enum_with_its_values(self, initialized_db: str) -> None:
        """SRS-037 — children are stored with their declaration positions."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        response = handle_create_type_definition(
            ctx,
            {
                "name": "Mode",
                "kind": "enum",
                "subtype": {
                    "values": [
                        {"name": "RED", "value": "0", "position": 1},
                        {"name": "GREEN", "value": "1", "position": 2},
                    ]
                },
            },
        )
        with ctx.db.read_only() as conn:
            parent = dal.get_type_definition_by_key(conn, response["result"]["unique_key"])
            children = dal.get_children(conn, "EnumValues", "enum_type_id", parent.id)
        assert [child.name for child in children] == ["RED", "GREEN"]

    def test_missing_subtype_is_rejected(self, initialized_db: str) -> None:
        """SRS-038a — the subtype detail is required."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_type_definition(ctx, {"name": "Speed", "kind": "array"})
        assert caught.value.error.field == "subtype"

    def test_unresolved_array_reference_targets_the_parent(self, initialized_db: str) -> None:
        """SRS-036a, SRS-074 — subtype rows are not reviewable artifact types."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        response = handle_create_type_definition(
            ctx, {"name": "Buffer", "kind": "array", "subtype": {"array_size": 8}}
        )
        key = response["result"]["unique_key"]
        with ctx.db.read_only() as conn:
            issues = dal.query_review_issues(conn, {"artifact_unique_key": key})
        assert issues[0].issue_type == "unresolved_reference"
        assert issues[0].artifact_type == "type_definition"

    def test_duplicate_name_and_kind_warns(self, initialized_db: str) -> None:
        """SRS-034, SRS-121 — the warning rides on the create response."""
        ctx = build_context(initialized_db, "review")
        payload = {"name": "Speed", "kind": "struct", "subtype": {"elements": []}}
        handle_create_type_definition(ctx, payload)
        response = handle_create_type_definition(ctx, dict(payload, name=" speed "))
        assert response["result"]["warnings"]

    def test_a_failed_child_rolls_back_the_parent(self, initialized_db: str) -> None:
        """SRS-084 — the parent, subtype and children are one transaction."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        with pytest.raises(Exception):
            handle_create_type_definition(
                ctx,
                {
                    "name": "Mode",
                    "kind": "enum",
                    "subtype": {
                        "values": [
                            {"name": "RED", "position": 1},
                            {"name": "RED", "position": 2},
                        ]
                    },
                },
            )
        with ctx.db.read_only() as conn:
            assert dal.query_type_definitions(conn, {"name": "Mode"}) == []


class TestUpdateTypeDefinition:
    def test_rejects_a_kind_change(self, initialized_db: str) -> None:
        """SRS-120 — kind is immutable."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_type_definition(
            ctx, {"name": "Speed", "kind": "struct", "subtype": {"elements": []}}
        )["result"]["unique_key"]
        with pytest.raises(McpValidationError) as caught:
            handle_update_type_definition(ctx, {"unique_key": key, "kind": "enum"})
        assert caught.value.error.field == "kind"


class TestChildTools:
    def test_struct_element_requires_a_struct_parent(self, initialized_db: str) -> None:
        """SRS-044 — the parent kind must match the child type."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_type_definition(
            ctx, {"name": "Mode", "kind": "enum", "subtype": {"values": []}}
        )["result"]["unique_key"]
        with pytest.raises(McpValidationError) as caught:
            handle_create_struct_element(
                ctx, {"struct_type_key": key, "name": "value", "position": 1}
            )
        assert caught.value.error.field == "struct_type_key"

    def test_enum_value_is_created_on_an_enum_parent(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = handle_create_type_definition(
            ctx, {"name": "Mode", "kind": "enum", "subtype": {"values": []}}
        )["result"]["unique_key"]
        response = handle_create_enum_value(
            ctx, {"enum_type_key": key, "name": "RED", "position": 1}
        )
        assert response["result"]["name"] == "RED"


class TestQuery:
    def test_filters_by_kind(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        handle_create_type_definition(
            ctx, {"name": "Mode", "kind": "enum", "subtype": {"values": []}}
        )
        handle_create_type_definition(
            ctx, {"name": "Speed", "kind": "struct", "subtype": {"elements": []}}
        )
        response = handle_query_type_definitions(ctx, {"kind": "enum"})
        assert [r["name"] for r in response["result"]["records"]] == ["Mode"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_type_definitions.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'handle_create_type_definition'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/tools/type_definitions.py`:

```python
"""Type-definition tools: the parent, its subtype detail, and its children.

`create_type_definition` writes a parent row, one subtype detail row, and any
number of child rows in a single transaction, with a shape that depends on
`kind` (LLD-02 §7.2). That is not the engine's regular shape, so it is written
out; everything else here is a descriptor.

See: LLD-02 §7.2 (Type Definition Tools — SRS-038a, SRS-043, SRS-044, SRS-086)
"""

from typing import Any
from uuid import uuid4

from ..db.models import ARTIFACT_STATUSES
from ..duplicate_detection import check_for_duplicates, duplicate_warning
from ..errors import McpResult, McpValidationError
from ..validation.common import validate_not_empty, validate_position, validate_positive_int
from ..validation.type_definitions import (
    KINDS,
    validate_kind_value,
    validate_parent_kind,
    validate_subtype_matches_kind,
)
from ._engine import (
    CreateSpec,
    FieldSpec,
    QuerySpec,
    RefSpec,
    UpdateSpec,
    choice_of,
    create_unresolved_issue,
    record_to_dict,
    run_create,
    run_query,
    run_update,
)
from .context import ToolContext

_CREATE_TOOL = "create_type_definition"

_UPDATE = UpdateSpec(
    tool="update_type_definition",
    table="TypeDefinitions",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("description", "description"),
    ),
    refs=(RefSpec("source_requirement_key", "source_requirement_id", "SourceRequirements"),),
    immutable_args=("kind",),
)

_QUERY = QuerySpec(
    tool="query_type_definitions",
    table="TypeDefinitions",
    filters=(
        FieldSpec("name", "name"),
        FieldSpec("kind", "kind", validator=choice_of(KINDS)),
        FieldSpec("status", "status", validator=choice_of(ARTIFACT_STATUSES)),
    ),
)

_CREATE_STRUCT_ELEMENT = CreateSpec(
    tool="create_struct_element",
    table="StructElements",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("position", "position", True, validate_position),
        FieldSpec("description", "description"),
    ),
    refs=(
        RefSpec("struct_type_key", "struct_type_id", "TypeDefinitions", required=True, parent=True),
        RefSpec("element_type_key", "element_type_id", "TypeDefinitions", may_be_unresolved=True),
    ),
)

_UPDATE_STRUCT_ELEMENT = UpdateSpec(
    tool="update_struct_element",
    table="StructElements",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("position", "position", validator=validate_position),
        FieldSpec("description", "description"),
    ),
    refs=(RefSpec("element_type_key", "element_type_id", "TypeDefinitions"),),
)

_CREATE_ENUM_VALUE = CreateSpec(
    tool="create_enum_value",
    table="EnumValues",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("value", "value"),
        FieldSpec("position", "position", True, validate_position),
        FieldSpec("description", "description"),
    ),
    refs=(RefSpec("enum_type_key", "enum_type_id", "TypeDefinitions", required=True, parent=True),),
)

_UPDATE_ENUM_VALUE = UpdateSpec(
    tool="update_enum_value",
    table="EnumValues",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("value", "value"),
        FieldSpec("position", "position", validator=validate_position),
        FieldSpec("description", "description"),
    ),
)


def _check_parent_kind(ctx: ToolContext, arguments: dict[str, Any], arg: str, kind: str) -> None:
    """Pre-check the parent kind before the engine inserts (SRS-044)."""
    key = arguments.get(arg)
    if not isinstance(key, str):
        return
    with ctx.db.read_only() as conn:
        parent = ctx.dal.get_type_definition_by_key(conn, key)
        if parent is None:
            return
        validate_parent_kind(
            conn,
            ctx.dal,
            parent.id,
            kind,
            operation=f"create_{'struct_element' if kind == 'struct' else 'enum_value'}",
            field=arg,
        )


def handle_create_type_definition(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a type definition with its subtype detail (SRS-038a, SRS-086)."""
    name = arguments.get("name")
    validate_not_empty(name, "name", operation=_CREATE_TOOL)
    kind = arguments.get("kind")
    validate_kind_value(kind, operation=_CREATE_TOOL)
    subtype = arguments.get("subtype")
    validate_subtype_matches_kind(str(kind), subtype, operation=_CREATE_TOOL)

    unique_key = str(uuid4())
    warnings: list[str] = []

    with ctx.db.transaction() as conn:
        source_requirement_id: int | None = None
        source_key = arguments.get("source_requirement_key")
        if source_key is not None:
            source = ctx.dal.get_source_requirement_by_key(conn, str(source_key))
            if source is None:
                raise McpValidationError.of(
                    _CREATE_TOOL,
                    "source_requirement_key does not resolve to an existing record",
                    field="source_requirement_key",
                    affected_key=str(source_key),
                )
            source_requirement_id = source.id

        duplicates = check_for_duplicates(conn, ctx.dal, "TypeDefinitions", str(name), str(kind))
        if duplicates:
            warnings.append(duplicate_warning("TypeDefinitions", str(name), duplicates))

        parent_id = ctx.dal.insert_type_definition(
            conn,
            unique_key,
            str(name),
            str(kind),
            arguments.get("description"),
            source_requirement_id,
        )
        _insert_subtype(ctx, conn, str(kind), dict(subtype), parent_id, unique_key,
                        source_requirement_id)

        if duplicates:
            ctx.dal.insert_review_issue(
                conn,
                str(uuid4()),
                source_requirement_id,
                "type_definition",
                unique_key,
                "ambiguous",
                warnings[0],
            )
        created = ctx.dal.get_record_by_id(conn, "TypeDefinitions", parent_id)

    data = record_to_dict(created)
    data.pop("id", None)
    data.pop("unique_key", None)
    return McpResult(unique_key=unique_key, data=data, warnings=warnings).to_dict()


def _insert_subtype(
    ctx: ToolContext,
    conn: Any,
    kind: str,
    subtype: dict[str, Any],
    parent_id: int,
    parent_key: str,
    source_requirement_id: int | None,
) -> None:
    """Insert the kind-specific detail rows (LLD-02 §7.2 steps 7–8)."""
    if kind == "simple_typedef":
        validate_not_empty(subtype.get("base_type"), "subtype.base_type", operation=_CREATE_TOOL)
        ctx.dal.insert_simple_type_definition(
            conn, str(uuid4()), parent_id, str(subtype["base_type"]), subtype.get("size")
        )
        return

    if kind == "array":
        validate_positive_int(
            subtype.get("array_size"), "subtype.array_size", operation=_CREATE_TOOL
        )
        element_type_id = _resolve_element_type(ctx, conn, subtype.get("element_type_key"))
        ctx.dal.insert_array_type_definition(
            conn, str(uuid4()), parent_id, element_type_id, int(subtype["array_size"])
        )
        if element_type_id is None:
            # The subtype row is not an independently reviewable artifact type
            # (SRS-035a, SRS-074), so the issue targets the parent.
            create_unresolved_issue(
                conn,
                ctx.dal,
                "TypeDefinitions",
                parent_key,
                "element_type_id",
                source_requirement_id,
            )
        return

    if kind == "struct":
        for element in subtype.get("elements", []):
            validate_not_empty(element.get("name"), "subtype.elements[].name",
                               operation=_CREATE_TOOL)
            validate_position(element.get("position"), "subtype.elements[].position",
                              operation=_CREATE_TOOL)
            child_key = str(uuid4())
            element_type_id = _resolve_element_type(ctx, conn, element.get("element_type_key"))
            ctx.dal.insert_struct_element(
                conn,
                child_key,
                parent_id,
                str(element["name"]),
                element_type_id,
                int(element["position"]),
                element.get("description"),
            )
            if element_type_id is None:
                create_unresolved_issue(
                    conn, ctx.dal, "StructElements", child_key, "element_type_id",
                    source_requirement_id,
                )
        return

    for value in subtype.get("values", []):
        validate_not_empty(value.get("name"), "subtype.values[].name", operation=_CREATE_TOOL)
        validate_position(value.get("position"), "subtype.values[].position",
                          operation=_CREATE_TOOL)
        ctx.dal.insert_enum_value(
            conn,
            str(uuid4()),
            parent_id,
            str(value["name"]),
            value.get("value"),
            int(value["position"]),
            value.get("description"),
        )


def _resolve_element_type(ctx: ToolContext, conn: Any, key: Any) -> int | None:
    """Resolve a type reference, or None while unresolved (SRS-036a)."""
    if key is None:
        return None
    target = ctx.dal.get_type_definition_by_key(conn, str(key))
    if target is None:
        raise McpValidationError.of(
            _CREATE_TOOL,
            "element_type_key does not resolve to an existing TypeDefinitions record",
            field="element_type_key",
            affected_key=str(key),
        )
    return int(target.id)


def handle_update_type_definition(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a type definition; `kind` and `status` are rejected."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_type_definitions(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query type definitions (SRS-086)."""
    return run_query(ctx, _QUERY, arguments)


def handle_create_struct_element(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a struct element on a struct parent (SRS-044)."""
    _check_parent_kind(ctx, arguments, "struct_type_key", "struct")
    return run_create(ctx, _CREATE_STRUCT_ELEMENT, arguments)


def handle_update_struct_element(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a struct element."""
    return run_update(ctx, _UPDATE_STRUCT_ELEMENT, arguments)


def handle_create_enum_value(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create an enum value on an enum parent (SRS-044)."""
    _check_parent_kind(ctx, arguments, "enum_type_key", "enum")
    return run_create(ctx, _CREATE_ENUM_VALUE, arguments)


def handle_update_enum_value(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update an enum value."""
    return run_update(ctx, _UPDATE_ENUM_VALUE, arguments)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/type_definitions.py tests/test_r210_mcp/test_tools/test_type_definitions.py
git commit -m "feat(tools): add type-definition and child handlers"
```

---

**Tasks 16–19 continue in `docs/superpowers/plans/2026-08-12-phase3-mcp-tool-surface-part4.md`.**
