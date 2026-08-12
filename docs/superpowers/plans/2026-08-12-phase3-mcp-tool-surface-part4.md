# Phase 3 Implementation Plan — Part 4: Interface, Prototype, Connection and Issue Handlers

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.
>
> **Read Part 1 first:** `docs/superpowers/plans/2026-08-12-phase3-mcp-tool-surface.md` for Goal, Architecture and Global Constraints. Parts 2 and 3 build the engine and validators these tasks consume.

**Covers:** Tasks 16–19 — the remaining descriptor-driven handler modules.

---

## Task 16: Port-interface handlers

Nine tools: the interface plus its two child types and the operation arguments
that hang off an operation.

**Files:**
- Create: `src/r210_mcp/tools/port_interfaces.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_tools/test_port_interfaces.py`

**Interfaces:**
- Consumes: engine (Parts 2), `INTERFACE_TYPES`, `ARGUMENT_DIRECTIONS`, `CHILD_REQUIRED_INTERFACE_TYPE`, `validate_child_interface_type` (Task 12).
- Produces: `handle_create_port_interface`, `handle_update_port_interface`, `handle_query_port_interfaces`, `handle_create_interface_data_element`, `handle_update_interface_data_element`, `handle_create_client_server_operation`, `handle_update_client_server_operation`, `handle_create_operation_argument`, `handle_update_operation_argument` — each `(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_port_interfaces.py`:

```python
"""Development tests for the port-interface tools (LLD-02 §7.3)."""

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.port_interfaces import (
    handle_create_client_server_operation,
    handle_create_interface_data_element,
    handle_create_operation_argument,
    handle_create_port_interface,
    handle_query_port_interfaces,
    handle_update_port_interface,
)


def _interface(ctx: object, name: str, interface_type: str) -> str:
    response = handle_create_port_interface(
        ctx, {"name": name, "interface_type": interface_type}
    )
    return str(response["result"]["unique_key"])


class TestPortInterface:
    def test_creates_with_an_interface_type(self, initialized_db: str) -> None:
        """SRS-052 — interface_type is sender_receiver or client_server."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_port_interface(
            ctx, {"name": "Speed", "interface_type": "sender_receiver"}
        )
        assert response["result"]["interface_type"] == "sender_receiver"

    def test_rejects_an_unknown_interface_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_interface(ctx, {"name": "X", "interface_type": "broadcast"})
        assert caught.value.error.field == "interface_type"

    def test_query_filters_by_interface_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        _interface(ctx, "A", "sender_receiver")
        _interface(ctx, "B", "client_server")
        response = handle_query_port_interfaces(ctx, {"interface_type": "client_server"})
        assert [r["name"] for r in response["result"]["records"]] == ["B"]

    def test_update_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a — status only through set_review_status."""
        ctx = build_context(initialized_db, "review")
        key = _interface(ctx, "A", "sender_receiver")
        with pytest.raises(McpValidationError):
            handle_update_port_interface(ctx, {"unique_key": key, "status": "approved"})


class TestChildTypeMatching:
    def test_data_element_requires_sender_receiver(self, initialized_db: str) -> None:
        """SRS-055 — a data element cannot hang off a client_server interface."""
        ctx = build_context(initialized_db, "review")
        key = _interface(ctx, "Ops", "client_server")
        with pytest.raises(McpValidationError) as caught:
            handle_create_interface_data_element(
                ctx, {"port_interface_key": key, "name": "value", "position": 1}
            )
        assert caught.value.error.field == "port_interface_key"

    def test_operation_requires_client_server(self, initialized_db: str) -> None:
        """SRS-055 — an operation cannot hang off a sender_receiver interface."""
        ctx = build_context(initialized_db, "review")
        key = _interface(ctx, "Data", "sender_receiver")
        with pytest.raises(McpValidationError):
            handle_create_client_server_operation(
                ctx, {"port_interface_key": key, "name": "Get", "position": 1}
            )

    def test_valid_children_are_created(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        sr_key = _interface(ctx, "Data", "sender_receiver")
        cs_key = _interface(ctx, "Ops", "client_server")
        element = handle_create_interface_data_element(
            ctx, {"port_interface_key": sr_key, "name": "value", "position": 1}
        )
        operation = handle_create_client_server_operation(
            ctx, {"port_interface_key": cs_key, "name": "Get", "position": 1}
        )
        assert element["result"]["name"] == "value"
        assert operation["result"]["name"] == "Get"


class TestOperationArgument:
    def test_creates_with_a_direction(self, initialized_db: str) -> None:
        """SRS-059 — direction is input, output or input_output."""
        ctx = build_context(initialized_db, "review")
        iface = _interface(ctx, "Ops", "client_server")
        operation = handle_create_client_server_operation(
            ctx, {"port_interface_key": iface, "name": "Get", "position": 1}
        )["result"]["unique_key"]
        response = handle_create_operation_argument(
            ctx, {"operation_key": operation, "name": "value", "direction": "input", "position": 1}
        )
        assert response["result"]["direction"] == "input"

    def test_rejects_an_unknown_direction(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        iface = _interface(ctx, "Ops", "client_server")
        operation = handle_create_client_server_operation(
            ctx, {"port_interface_key": iface, "name": "Get", "position": 1}
        )["result"]["unique_key"]
        with pytest.raises(McpValidationError) as caught:
            handle_create_operation_argument(
                ctx,
                {"operation_key": operation, "name": "v", "direction": "sideways", "position": 1},
            )
        assert caught.value.error.field == "direction"

    def test_unresolved_type_reference_creates_an_issue(self, initialized_db: str) -> None:
        """SRS-036a — an unresolved type_definition_id is recorded."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        iface = _interface(ctx, "Ops", "client_server")
        operation = handle_create_client_server_operation(
            ctx, {"port_interface_key": iface, "name": "Get", "position": 1}
        )["result"]["unique_key"]
        response = handle_create_operation_argument(
            ctx,
            {
                "operation_key": operation,
                "name": "value",
                "direction": "input",
                "position": 1,
                "type_definition_key": None,
            },
        )
        key = response["result"]["unique_key"]
        with ctx.db.read_only() as conn:
            issues = dal.query_review_issues(conn, {"artifact_unique_key": key})
        assert issues[0].issue_type == "unresolved_reference"
        assert issues[0].artifact_type == "operation_argument"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_port_interfaces.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'handle_create_port_interface'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/tools/port_interfaces.py`:

```python
"""Port-interface tools: the interface, its children, and operation arguments.

The two child creates pre-check the parent's `interface_type` before the
engine inserts, because SRS-055 is an application-level rule the schema cannot
express.

See: LLD-02 §7.3 (Port Interface Tools — SRS-052, SRS-055, SRS-059, SRS-086)
"""

from typing import Any

from ..db.models import ARTIFACT_STATUSES
from ..validation.common import validate_not_empty, validate_position
from ..validation.port_interfaces import (
    ARGUMENT_DIRECTIONS,
    INTERFACE_TYPES,
    validate_child_interface_type,
)
from ._engine import (
    CreateSpec,
    FieldSpec,
    QuerySpec,
    RefSpec,
    UpdateSpec,
    choice_of,
    run_create,
    run_query,
    run_update,
)
from .context import ToolContext

_SOURCE_REF = RefSpec("source_requirement_key", "source_requirement_id", "SourceRequirements")

_CREATE = CreateSpec(
    tool="create_port_interface",
    table="PortInterfaces",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("description", "description"),
        FieldSpec("interface_type", "interface_type", True, choice_of(INTERFACE_TYPES)),
    ),
    refs=(_SOURCE_REF,),
    duplicate_name_arg="name",
)

_UPDATE = UpdateSpec(
    tool="update_port_interface",
    table="PortInterfaces",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("description", "description"),
        FieldSpec("interface_type", "interface_type", validator=choice_of(INTERFACE_TYPES)),
    ),
    refs=(_SOURCE_REF,),
)

_QUERY = QuerySpec(
    tool="query_port_interfaces",
    table="PortInterfaces",
    filters=(
        FieldSpec("name", "name"),
        FieldSpec("interface_type", "interface_type", validator=choice_of(INTERFACE_TYPES)),
        FieldSpec("status", "status", validator=choice_of(ARTIFACT_STATUSES)),
    ),
)

_CREATE_DATA_ELEMENT = CreateSpec(
    tool="create_interface_data_element",
    table="InterfaceDataElements",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("position", "position", True, validate_position),
        FieldSpec("description", "description"),
    ),
    refs=(
        RefSpec(
            "port_interface_key", "port_interface_id", "PortInterfaces", required=True, parent=True
        ),
        RefSpec(
            "type_definition_key", "type_definition_id", "TypeDefinitions", may_be_unresolved=True
        ),
    ),
)

_UPDATE_DATA_ELEMENT = UpdateSpec(
    tool="update_interface_data_element",
    table="InterfaceDataElements",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("position", "position", validator=validate_position),
        FieldSpec("description", "description"),
    ),
    refs=(RefSpec("type_definition_key", "type_definition_id", "TypeDefinitions"),),
)

_CREATE_OPERATION = CreateSpec(
    tool="create_client_server_operation",
    table="ClientServerOperations",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("position", "position", True, validate_position),
        FieldSpec("description", "description"),
    ),
    refs=(
        RefSpec(
            "port_interface_key", "port_interface_id", "PortInterfaces", required=True, parent=True
        ),
    ),
)

_UPDATE_OPERATION = UpdateSpec(
    tool="update_client_server_operation",
    table="ClientServerOperations",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("position", "position", validator=validate_position),
        FieldSpec("description", "description"),
    ),
)

_CREATE_ARGUMENT = CreateSpec(
    tool="create_operation_argument",
    table="OperationArguments",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("direction", "direction", True, choice_of(ARGUMENT_DIRECTIONS)),
        FieldSpec("position", "position", True, validate_position),
    ),
    refs=(
        RefSpec(
            "operation_key", "operation_id", "ClientServerOperations", required=True, parent=True
        ),
        RefSpec(
            "type_definition_key", "type_definition_id", "TypeDefinitions", may_be_unresolved=True
        ),
    ),
)

_UPDATE_ARGUMENT = UpdateSpec(
    tool="update_operation_argument",
    table="OperationArguments",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("direction", "direction", validator=choice_of(ARGUMENT_DIRECTIONS)),
        FieldSpec("position", "position", validator=validate_position),
    ),
    refs=(RefSpec("type_definition_key", "type_definition_id", "TypeDefinitions"),),
)


def _check_interface_type(ctx: ToolContext, arguments: dict[str, Any], child_table: str,
                          tool: str) -> None:
    """Pre-check the parent interface_type before inserting (SRS-055)."""
    key = arguments.get("port_interface_key")
    if not isinstance(key, str):
        return
    with ctx.db.read_only() as conn:
        parent = ctx.dal.get_port_interface_by_key(conn, key)
        if parent is None:
            return
        validate_child_interface_type(
            conn, ctx.dal, parent.id, child_table, operation=tool, field="port_interface_key"
        )


def handle_create_port_interface(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a port interface (SRS-052, SRS-086)."""
    return run_create(ctx, _CREATE, arguments)


def handle_update_port_interface(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a port interface."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_port_interfaces(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query port interfaces (SRS-086)."""
    return run_query(ctx, _QUERY, arguments)


def handle_create_interface_data_element(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Create a data element on a sender_receiver interface (SRS-055)."""
    _check_interface_type(
        ctx, arguments, "InterfaceDataElements", "create_interface_data_element"
    )
    return run_create(ctx, _CREATE_DATA_ELEMENT, arguments)


def handle_update_interface_data_element(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update an interface data element."""
    return run_update(ctx, _UPDATE_DATA_ELEMENT, arguments)


def handle_create_client_server_operation(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Create an operation on a client_server interface (SRS-055)."""
    _check_interface_type(
        ctx, arguments, "ClientServerOperations", "create_client_server_operation"
    )
    return run_create(ctx, _CREATE_OPERATION, arguments)


def handle_update_client_server_operation(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update a client-server operation."""
    return run_update(ctx, _UPDATE_OPERATION, arguments)


def handle_create_operation_argument(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Create an operation argument (SRS-059)."""
    return run_create(ctx, _CREATE_ARGUMENT, arguments)


def handle_update_operation_argument(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update an operation argument."""
    return run_update(ctx, _UPDATE_ARGUMENT, arguments)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/port_interfaces.py tests/test_r210_mcp/test_tools/test_port_interfaces.py
git commit -m "feat(tools): add port-interface handlers"
```

---

## Task 17: Port-prototype handlers

**Files:**
- Create: `src/r210_mcp/tools/port_prototypes.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_tools/test_port_prototypes.py`

**Interfaces:**
- Consumes: engine; `PORT_DIRECTIONS`, `RELATIONSHIP_TYPES` (Task 12).
- Produces: `handle_create_port_prototype`, `handle_update_port_prototype`, `handle_query_port_prototypes`, `handle_create_port_prototype_function`, `handle_update_port_prototype_function`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_port_prototypes.py`:

```python
"""Development tests for the port-prototype tools (LLD-02 §7.4)."""

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.port_prototypes import (
    handle_create_port_prototype,
    handle_create_port_prototype_function,
    handle_query_port_prototypes,
    handle_update_port_prototype,
)

BASE = {"name": "SpeedPort", "direction": "provider", "component_reference": "ECU_Main"}


class TestPortPrototype:
    def test_creates_with_a_direction(self, initialized_db: str) -> None:
        """SRS-061 — direction is provider or requester."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_port_prototype(ctx, dict(BASE))
        assert response["result"]["direction"] == "provider"
        assert response["result"]["component_reference"] == "ECU_Main"

    def test_rejects_an_unknown_direction(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_prototype(ctx, dict(BASE, direction="both"))
        assert caught.value.error.field == "direction"

    def test_requires_a_component_reference(self, initialized_db: str) -> None:
        """SRS-062 — component_reference is NOT NULL in the schema."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_prototype(ctx, {"name": "P", "direction": "provider"})
        assert caught.value.error.field == "component_reference"

    def test_port_interface_key_may_stay_unresolved(self, initialized_db: str) -> None:
        """SRS-036 — a missing optional relationship is stored as NULL."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        key = handle_create_port_prototype(ctx, dict(BASE))["result"]["unique_key"]
        with ctx.db.read_only() as conn:
            record = dal.get_port_prototype_by_key(conn, key)
        assert record.port_interface_id is None

    def test_query_filters_by_direction(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        handle_create_port_prototype(ctx, dict(BASE))
        handle_create_port_prototype(ctx, dict(BASE, name="Other", direction="requester"))
        response = handle_query_port_prototypes(ctx, {"direction": "requester"})
        assert [r["name"] for r in response["result"]["records"]] == ["Other"]

    def test_update_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_port_prototype(ctx, dict(BASE))["result"]["unique_key"]
        with pytest.raises(McpValidationError):
            handle_update_port_prototype(ctx, {"unique_key": key, "status": "approved"})


class TestPortPrototypeFunction:
    def test_creates_with_a_relationship_type(self, initialized_db: str) -> None:
        """SRS-063 — relationship_type is access_point or trigger."""
        ctx = build_context(initialized_db, "review")
        parent = handle_create_port_prototype(ctx, dict(BASE))["result"]["unique_key"]
        response = handle_create_port_prototype_function(
            ctx,
            {
                "port_prototype_key": parent,
                "function_name": "ReadSpeed",
                "relationship_type": "access_point",
            },
        )
        assert response["result"]["relationship_type"] == "access_point"

    def test_rejects_an_unknown_relationship_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        parent = handle_create_port_prototype(ctx, dict(BASE))["result"]["unique_key"]
        with pytest.raises(McpValidationError) as caught:
            handle_create_port_prototype_function(
                ctx,
                {
                    "port_prototype_key": parent,
                    "function_name": "ReadSpeed",
                    "relationship_type": "callback",
                },
            )
        assert caught.value.error.field == "relationship_type"

    def test_demotes_an_approved_parent(self, initialized_db: str) -> None:
        """SRS-035c — a new pending child invalidates the parent's approval."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        parent = handle_create_port_prototype(ctx, dict(BASE))["result"]["unique_key"]
        with ctx.db.transaction() as conn:
            record = dal.get_port_prototype_by_key(conn, parent)
            dal.update_status(conn, "PortPrototypes", record.id, "approved")
        response = handle_create_port_prototype_function(
            ctx,
            {
                "port_prototype_key": parent,
                "function_name": "ReadSpeed",
                "relationship_type": "trigger",
            },
        )
        assert response["result"]["demoted"] == [parent]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_port_prototypes.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'handle_create_port_prototype'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/tools/port_prototypes.py`:

```python
"""Port-prototype tools: the prototype and its function references.

`port_interface_key` is optional: SRS-036 stores a missing relationship as
NULL rather than 0. It is not one of the four SRS-036a columns, so leaving it
unresolved does not create a ReviewIssue.

See: LLD-02 §7.4 (Port Prototype Tools — SRS-061, SRS-063, SRS-086)
"""

from typing import Any

from ..db.models import ARTIFACT_STATUSES
from ..validation.common import validate_not_empty
from ..validation.port_interfaces import PORT_DIRECTIONS, RELATIONSHIP_TYPES
from ._engine import (
    CreateSpec,
    FieldSpec,
    QuerySpec,
    RefSpec,
    UpdateSpec,
    choice_of,
    run_create,
    run_query,
    run_update,
)
from .context import ToolContext

_SOURCE_REF = RefSpec("source_requirement_key", "source_requirement_id", "SourceRequirements")
_INTERFACE_REF = RefSpec("port_interface_key", "port_interface_id", "PortInterfaces")

_CREATE = CreateSpec(
    tool="create_port_prototype",
    table="PortPrototypes",
    fields=(
        FieldSpec("name", "name", True, validate_not_empty),
        FieldSpec("description", "description"),
        FieldSpec("direction", "direction", True, choice_of(PORT_DIRECTIONS)),
        FieldSpec("component_reference", "component_reference", True, validate_not_empty),
    ),
    refs=(_SOURCE_REF, _INTERFACE_REF),
    duplicate_name_arg="name",
)

_UPDATE = UpdateSpec(
    tool="update_port_prototype",
    table="PortPrototypes",
    fields=(
        FieldSpec("name", "name", validator=validate_not_empty),
        FieldSpec("description", "description"),
        FieldSpec("direction", "direction", validator=choice_of(PORT_DIRECTIONS)),
        FieldSpec("component_reference", "component_reference", validator=validate_not_empty),
    ),
    refs=(_SOURCE_REF, _INTERFACE_REF),
)

_QUERY = QuerySpec(
    tool="query_port_prototypes",
    table="PortPrototypes",
    filters=(
        FieldSpec("name", "name"),
        FieldSpec("direction", "direction", validator=choice_of(PORT_DIRECTIONS)),
        FieldSpec("component_reference", "component_reference"),
        FieldSpec("status", "status", validator=choice_of(ARTIFACT_STATUSES)),
    ),
)

_CREATE_FUNCTION = CreateSpec(
    tool="create_port_prototype_function",
    table="PortPrototypeFunctions",
    fields=(
        FieldSpec("function_name", "function_name", True, validate_not_empty),
        FieldSpec("relationship_type", "relationship_type", True, choice_of(RELATIONSHIP_TYPES)),
    ),
    refs=(
        RefSpec(
            "port_prototype_key",
            "port_prototype_id",
            "PortPrototypes",
            required=True,
            parent=True,
        ),
    ),
)

_UPDATE_FUNCTION = UpdateSpec(
    tool="update_port_prototype_function",
    table="PortPrototypeFunctions",
    fields=(
        FieldSpec("function_name", "function_name", validator=validate_not_empty),
        FieldSpec(
            "relationship_type", "relationship_type", validator=choice_of(RELATIONSHIP_TYPES)
        ),
    ),
)


def handle_create_port_prototype(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a port prototype (SRS-061, SRS-086)."""
    return run_create(ctx, _CREATE, arguments)


def handle_update_port_prototype(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a port prototype."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_port_prototypes(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query port prototypes (SRS-086)."""
    return run_query(ctx, _QUERY, arguments)


def handle_create_port_prototype_function(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Create a function reference on a prototype (SRS-063)."""
    return run_create(ctx, _CREATE_FUNCTION, arguments)


def handle_update_port_prototype_function(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update a prototype function reference."""
    return run_update(ctx, _UPDATE_FUNCTION, arguments)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/port_prototypes.py tests/test_r210_mcp/test_tools/test_port_prototypes.py
git commit -m "feat(tools): add port-prototype handlers"
```

---

## Task 18: Port-connection handlers

`update_port_connection_member` is irregular: LLD-02 §10.3 requires the whole
connection to be revalidated inside the same transaction, so a failure rolls
the member change back. It is written out rather than driven by the engine.

**Files:**
- Create: `src/r210_mcp/tools/port_connections.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_tools/test_port_connections.py`

**Interfaces:**
- Consumes: engine; `validate_connection_complete`, `create_compatibility_review_issue` (Task 13); `demote_if_approved`, `demote_parent_on_child_creation` (Tasks 8–9).
- Produces: `handle_create_port_connection`, `handle_update_port_connection`, `handle_query_port_connections`, `handle_create_port_connection_member`, `handle_update_port_connection_member`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_port_connections.py`:

```python
"""Development tests for the port-connection tools (LLD-02 §7.5, §10.3)."""

import pytest

from r210_mcp.db.dal import DataAccessLayer
from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.port_connections import (
    handle_create_port_connection,
    handle_create_port_connection_member,
    handle_update_port_connection_member,
)
from r210_mcp.tools.port_prototypes import handle_create_port_prototype


def _prototype(ctx: object, name: str, direction: str) -> str:
    response = handle_create_port_prototype(
        ctx, {"name": name, "direction": direction, "component_reference": "ECU"}
    )
    return str(response["result"]["unique_key"])


class TestCreateConnection:
    def test_creates_and_records_the_compatibility_issue(self, initialized_db: str) -> None:
        """SRS-125 — compatibility is unverified, so an issue is created."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        key = handle_create_port_connection(ctx, {"description": "link"})["result"]["unique_key"]
        with ctx.db.read_only() as conn:
            issues = dal.query_review_issues(conn, {"artifact_unique_key": key})
        assert len(issues) == 1
        assert issues[0].issue_type == "incomplete"


class TestMembers:
    def test_adds_members(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        connection = handle_create_port_connection(ctx, {})["result"]["unique_key"]
        provider = _prototype(ctx, "P", "provider")
        response = handle_create_port_connection_member(
            ctx,
            {"port_connection_key": connection, "port_prototype_key": provider, "position": 1},
        )
        assert response["result"]["position"] == 1

    def test_update_revalidates_the_whole_connection(self, initialized_db: str) -> None:
        """SRS-122 — a member change revalidates the connection transactionally."""
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        connection = handle_create_port_connection(ctx, {})["result"]["unique_key"]
        provider = _prototype(ctx, "P", "provider")
        requester = _prototype(ctx, "R", "requester")
        handle_create_port_connection_member(
            ctx,
            {"port_connection_key": connection, "port_prototype_key": provider, "position": 1},
        )
        member = handle_create_port_connection_member(
            ctx,
            {"port_connection_key": connection, "port_prototype_key": requester, "position": 2},
        )["result"]["unique_key"]

        # Repointing the requester at the provider leaves two providers and no
        # requester, and creates a duplicate: the update must be rejected.
        with pytest.raises(McpValidationError):
            handle_update_port_connection_member(
                ctx, {"unique_key": member, "port_prototype_key": provider}
            )

        with ctx.db.read_only() as conn:
            unchanged = dal.get_port_connection_member_by_key(conn, member)
            target = dal.get_port_prototype_by_key(conn, requester)
        assert unchanged.port_prototype_id == target.id

    def test_valid_member_update_is_applied(self, initialized_db: str) -> None:
        ctx, dal = build_context(initialized_db, "review"), DataAccessLayer()
        connection = handle_create_port_connection(ctx, {})["result"]["unique_key"]
        provider = _prototype(ctx, "P", "provider")
        requester = _prototype(ctx, "R", "requester")
        other = _prototype(ctx, "R2", "requester")
        handle_create_port_connection_member(
            ctx,
            {"port_connection_key": connection, "port_prototype_key": provider, "position": 1},
        )
        member = handle_create_port_connection_member(
            ctx,
            {"port_connection_key": connection, "port_prototype_key": requester, "position": 2},
        )["result"]["unique_key"]
        handle_update_port_connection_member(
            ctx, {"unique_key": member, "port_prototype_key": other}
        )
        with ctx.db.read_only() as conn:
            updated = dal.get_port_connection_member_by_key(conn, member)
            target = dal.get_port_prototype_by_key(conn, other)
        assert updated.port_prototype_id == target.id

    def test_member_update_rejects_status(self, initialized_db: str) -> None:
        """SRS-091a."""
        ctx = build_context(initialized_db, "review")
        connection = handle_create_port_connection(ctx, {})["result"]["unique_key"]
        provider = _prototype(ctx, "P", "provider")
        member = handle_create_port_connection_member(
            ctx,
            {"port_connection_key": connection, "port_prototype_key": provider, "position": 1},
        )["result"]["unique_key"]
        with pytest.raises(McpValidationError) as caught:
            handle_update_port_connection_member(
                ctx, {"unique_key": member, "status": "approved"}
            )
        assert caught.value.error.field == "status"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_port_connections.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'handle_create_port_connection'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/tools/port_connections.py`:

```python
"""Port-connection tools: the connection and its members.

`update_port_connection_member` revalidates the entire connection inside the
member's own transaction, so an update that would leave the connection invalid
rolls back rather than committing a broken graph (SRS-122, LLD-02 §10.3).

See: LLD-02 §7.5 (Port Connection Tools), §10.3 (Transactional Revalidation)
"""

from typing import Any
from uuid import uuid4

from ..db.models import ARTIFACT_STATUSES
from ..errors import McpResult, McpValidationError
from ..validation.common import validate_position, validate_uuid_format
from ..validation.port_connections import (
    create_compatibility_review_issue,
    validate_connection_complete,
)
from ._engine import (
    CreateSpec,
    FieldSpec,
    QuerySpec,
    RefSpec,
    UpdateSpec,
    demote_if_approved,
    record_to_dict,
    reject_status_argument,
    reject_unknown_arguments,
    run_create,
    run_query,
    run_update,
    choice_of,
)
from .context import ToolContext

_MEMBER_UPDATE_TOOL = "update_port_connection_member"

_CREATE = CreateSpec(
    tool="create_port_connection",
    table="PortConnections",
    fields=(FieldSpec("description", "description"),),
    refs=(RefSpec("source_requirement_key", "source_requirement_id", "SourceRequirements"),),
)

_UPDATE = UpdateSpec(
    tool="update_port_connection",
    table="PortConnections",
    fields=(FieldSpec("description", "description"),),
    refs=(RefSpec("source_requirement_key", "source_requirement_id", "SourceRequirements"),),
)

_QUERY = QuerySpec(
    tool="query_port_connections",
    table="PortConnections",
    filters=(FieldSpec("status", "status", validator=choice_of(ARTIFACT_STATUSES)),),
)

_CREATE_MEMBER = CreateSpec(
    tool="create_port_connection_member",
    table="PortConnectionMembers",
    fields=(FieldSpec("position", "position", True, validate_position),),
    refs=(
        RefSpec(
            "port_connection_key",
            "port_connection_id",
            "PortConnections",
            required=True,
            parent=True,
        ),
        RefSpec("port_prototype_key", "port_prototype_id", "PortPrototypes", required=True),
    ),
)


def handle_create_port_connection(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a connection and record that compatibility is unverified (SRS-125)."""
    response = run_create(ctx, _CREATE, arguments)
    connection_key = str(response["result"]["unique_key"])
    with ctx.db.transaction() as conn:
        connection = ctx.dal.get_record_by_unique_key(conn, "PortConnections", connection_key)
        create_compatibility_review_issue(
            conn, ctx.dal, connection_key, connection.source_requirement_id
        )
    return response


def handle_update_port_connection(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a port connection."""
    return run_update(ctx, _UPDATE, arguments)


def handle_query_port_connections(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query port connections (SRS-086)."""
    return run_query(ctx, _QUERY, arguments)


def handle_create_port_connection_member(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Add a member to a connection (SRS-069, SRS-070)."""
    return run_create(ctx, _CREATE_MEMBER, arguments)


def handle_update_port_connection_member(
    ctx: ToolContext, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Update a member and revalidate the whole connection (SRS-122).

    Written out rather than driven by the engine because the revalidation must
    happen inside the same transaction as the update: `transaction()` rolls
    back on the raised error, so a rejected revalidation undoes the change
    (LLD-02 §10.3).
    """
    reject_status_argument(_MEMBER_UPDATE_TOOL, arguments)
    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=_MEMBER_UPDATE_TOOL)
    reject_unknown_arguments(
        _MEMBER_UPDATE_TOOL,
        arguments,
        frozenset({"unique_key", "port_prototype_key", "position"}),
    )

    with ctx.db.transaction() as conn:
        member = ctx.dal.get_record_by_unique_key(conn, "PortConnectionMembers", str(key))
        if member is None:
            raise McpValidationError.of(
                _MEMBER_UPDATE_TOOL,
                f"no PortConnectionMembers record with unique_key {key!r}",
                field="unique_key",
                affected_key=str(key),
            )

        changed: dict[str, Any] = {}
        if "position" in arguments:
            validate_position(
                arguments["position"], "position", operation=_MEMBER_UPDATE_TOOL
            )
            changed["position"] = arguments["position"]
        if "port_prototype_key" in arguments:
            target = ctx.dal.get_record_by_unique_key(
                conn, "PortPrototypes", str(arguments["port_prototype_key"])
            )
            if target is None:
                raise McpValidationError.of(
                    _MEMBER_UPDATE_TOOL,
                    "port_prototype_key does not resolve to an existing PortPrototypes record",
                    field="port_prototype_key",
                    affected_key=str(arguments["port_prototype_key"]),
                )
            changed["port_prototype_id"] = target.id

        if changed:
            ctx.dal.update_record(conn, "PortConnectionMembers", member.id, changed)
        demoted = demote_if_approved(
            conn, ctx.dal, "PortConnectionMembers", member.id, changed
        )
        validate_connection_complete(
            conn, ctx.dal, int(member.port_connection_id), operation=_MEMBER_UPDATE_TOOL
        )
        updated = ctx.dal.get_record_by_id(conn, "PortConnectionMembers", member.id)

    data = record_to_dict(updated)
    data.pop("id", None)
    data.pop("unique_key", None)
    if demoted:
        data["demoted"] = demoted
    return McpResult(unique_key=str(key), data=data).to_dict()
```

Note the unused `uuid4` import must not be left behind — ruff `F401` will flag
it. Remove any import the final module does not use.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/port_connections.py tests/test_r210_mcp/test_tools/test_port_connections.py
git commit -m "feat(tools): add port-connection handlers with transactional revalidation"
```

---

## Task 19: Review-issue handlers

`update_review_issue` owns issue status changes (SRS-119), so unlike every
other update tool it *accepts* a status — validated against the issue
transition matrix, not the artifact one.

**Files:**
- Create: `src/r210_mcp/tools/review_issues.py` (replaces the stub)
- Test: `tests/test_r210_mcp/test_tools/test_review_issues.py`

**Interfaces:**
- Consumes: engine; `validate_issue_transition` (Task 4); `validate_artifact_type` (Task 3); `ISSUE_STATUSES` from `db.models`.
- Produces: `handle_create_review_issue`, `handle_update_review_issue`, `handle_query_review_issues`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_r210_mcp/test_tools/test_review_issues.py`:

```python
"""Development tests for the review-issue tools (LLD-02 §7.6)."""

import pytest

from r210_mcp.errors import McpValidationError
from r210_mcp.tools.context import build_context
from r210_mcp.tools.review_issues import (
    handle_create_review_issue,
    handle_query_review_issues,
    handle_update_review_issue,
)

BASE = {"issue_type": "ambiguous", "message": "Unclear wording"}


class TestCreate:
    def test_creates_a_pending_issue(self, initialized_db: str) -> None:
        """SRS-088, SRS-035b — issues start pending."""
        ctx = build_context(initialized_db, "review")
        response = handle_create_review_issue(ctx, dict(BASE))
        assert response["result"]["status"] == "pending"

    def test_rejects_an_unknown_issue_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_review_issue(ctx, dict(BASE, issue_type="confusing"))
        assert caught.value.error.field == "issue_type"

    def test_rejects_an_unknown_artifact_type(self, initialized_db: str) -> None:
        """SRS-074 — artifact_type is one of eleven values."""
        ctx = build_context(initialized_db, "review")
        with pytest.raises(McpValidationError) as caught:
            handle_create_review_issue(
                ctx, dict(BASE, artifact_type="widget", artifact_unique_key="k")
            )
        assert caught.value.error.field == "artifact_type"


class TestUpdate:
    def test_resolves_an_issue(self, initialized_db: str) -> None:
        """SRS-119 — issue status changes through update_review_issue."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_review_issue(ctx, dict(BASE))["result"]["unique_key"]
        response = handle_update_review_issue(
            ctx, {"unique_key": key, "status": "resolved", "resolution": "Clarified"}
        )
        assert response["result"]["status"] == "resolved"
        assert response["result"]["resolution"] == "Clarified"

    def test_rejects_a_forbidden_transition(self, initialized_db: str) -> None:
        """SRS-035b — resolved may only return to pending."""
        ctx = build_context(initialized_db, "review")
        key = handle_create_review_issue(ctx, dict(BASE))["result"]["unique_key"]
        handle_update_review_issue(ctx, {"unique_key": key, "status": "resolved"})
        with pytest.raises(McpValidationError) as caught:
            handle_update_review_issue(ctx, {"unique_key": key, "status": "rejected"})
        assert caught.value.error.field == "status"

    def test_reopening_is_permitted(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        key = handle_create_review_issue(ctx, dict(BASE))["result"]["unique_key"]
        handle_update_review_issue(ctx, {"unique_key": key, "status": "resolved"})
        response = handle_update_review_issue(ctx, {"unique_key": key, "status": "pending"})
        assert response["result"]["status"] == "pending"


class TestQuery:
    def test_filters_by_issue_type(self, initialized_db: str) -> None:
        ctx = build_context(initialized_db, "review")
        handle_create_review_issue(ctx, dict(BASE))
        handle_create_review_issue(ctx, dict(BASE, issue_type="incomplete"))
        response = handle_query_review_issues(ctx, {"issue_type": "incomplete"})
        assert response["result"]["count"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_r210_mcp/test_tools/test_review_issues.py -q -p no:cacheprovider`
Expected: FAIL with `ImportError: cannot import name 'handle_create_review_issue'`

- [ ] **Step 3: Write minimal implementation**

Replace the contents of `src/r210_mcp/tools/review_issues.py`:

```python
"""Review-issue tools: create, update, query.

`update_review_issue` is the one update tool that accepts `status`: SRS-091a
routes artifact status through `set_review_status` but leaves issue status
here (SRS-119), validated against the issue transition matrix.

See: LLD-02 §7.6 (Review Issue Tools — SRS-088, SRS-119)
"""

from typing import Any
from uuid import uuid4

from ..db.models import ISSUE_STATUSES
from ..errors import McpResult, McpValidationError
from ..validation.common import (
    validate_artifact_type,
    validate_choice,
    validate_not_empty,
    validate_uuid_format,
)
from ..validation.status import validate_issue_transition
from ._engine import FieldSpec, QuerySpec, choice_of, record_to_dict, reject_unknown_arguments, run_query
from .context import ToolContext

_CREATE_TOOL = "create_review_issue"
_UPDATE_TOOL = "update_review_issue"

# The five values the ReviewIssues.issue_type CHECK constraint permits.
ISSUE_TYPES = frozenset(
    {"ambiguous", "incomplete", "unresolved_reference", "unsupported", "out_of_scope"}
)

_QUERY = QuerySpec(
    tool="query_review_issues",
    table="ReviewIssues",
    filters=(
        FieldSpec("issue_type", "issue_type", validator=choice_of(ISSUE_TYPES)),
        FieldSpec("status", "status", validator=choice_of(ISSUE_STATUSES)),
        FieldSpec("artifact_type", "artifact_type"),
        FieldSpec("artifact_unique_key", "artifact_unique_key"),
    ),
)


def handle_create_review_issue(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a review issue (SRS-088)."""
    reject_unknown_arguments(
        _CREATE_TOOL,
        arguments,
        frozenset(
            {
                "issue_type",
                "message",
                "artifact_type",
                "artifact_unique_key",
                "source_requirement_key",
            }
        ),
    )
    validate_choice(arguments.get("issue_type"), ISSUE_TYPES, "issue_type", operation=_CREATE_TOOL)
    validate_not_empty(arguments.get("message"), "message", operation=_CREATE_TOOL)
    artifact_type = arguments.get("artifact_type")
    validate_artifact_type(artifact_type, "artifact_type", operation=_CREATE_TOOL)
    artifact_key = arguments.get("artifact_unique_key")
    if artifact_key is not None and artifact_type is None:
        raise McpValidationError.of(
            _CREATE_TOOL,
            "artifact_type is required when artifact_unique_key is given (SRS-074)",
            field="artifact_type",
            affected_key=str(artifact_key),
        )

    unique_key = str(uuid4())
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
        record_id = ctx.dal.insert_review_issue(
            conn,
            unique_key,
            source_requirement_id,
            artifact_type,
            None if artifact_key is None else str(artifact_key),
            str(arguments["issue_type"]),
            str(arguments["message"]),
        )
        created = ctx.dal.get_record_by_id(conn, "ReviewIssues", record_id)

    data = record_to_dict(created)
    data.pop("id", None)
    data.pop("unique_key", None)
    return McpResult(unique_key=unique_key, data=data).to_dict()


def handle_update_review_issue(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update an issue's status, message or resolution (SRS-119)."""
    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=_UPDATE_TOOL)
    reject_unknown_arguments(
        _UPDATE_TOOL, arguments, frozenset({"unique_key", "status", "message", "resolution"})
    )

    with ctx.db.transaction() as conn:
        issue = ctx.dal.get_record_by_unique_key(conn, "ReviewIssues", str(key))
        if issue is None:
            raise McpValidationError.of(
                _UPDATE_TOOL,
                f"no ReviewIssues record with unique_key {key!r}",
                field="unique_key",
                affected_key=str(key),
            )
        changed: dict[str, Any] = {}
        if "status" in arguments:
            validate_choice(
                arguments["status"], ISSUE_STATUSES, "status", operation=_UPDATE_TOOL
            )
            validate_issue_transition(
                str(issue.status),
                str(arguments["status"]),
                operation=_UPDATE_TOOL,
                affected_key=str(key),
            )
            changed["status"] = arguments["status"]
        if "message" in arguments:
            validate_not_empty(arguments["message"], "message", operation=_UPDATE_TOOL)
            changed["message"] = arguments["message"]
        if "resolution" in arguments:
            changed["resolution"] = arguments["resolution"]
        if changed:
            ctx.dal.update_record(conn, "ReviewIssues", issue.id, changed)
        updated = ctx.dal.get_record_by_id(conn, "ReviewIssues", issue.id)

    data = record_to_dict(updated)
    data.pop("id", None)
    data.pop("unique_key", None)
    return McpResult(unique_key=str(key), data=data).to_dict()


def handle_query_review_issues(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Query review issues (SRS-088)."""
    return run_query(ctx, _QUERY, arguments)
```

`validate_issue_transition` raises with `field="new_status"`; the test asserts
`field == "status"`. Pass the field explicitly by wrapping the call, or change
`_validate_transition` in Task 4 to accept a `field` parameter defaulting to
`"new_status"` and pass `field="status"` here. Take the second option — it is
one parameter and keeps both tools' error payloads accurate.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_r210_mcp/ -q -p no:cacheprovider && python -m ruff check src tests && python -m mypy src`
Expected: PASS, ruff clean, mypy `Success`

- [ ] **Step 5: Commit**

```bash
git add src/r210_mcp/tools/review_issues.py src/r210_mcp/validation/status.py tests/test_r210_mcp/test_tools/test_review_issues.py
git commit -m "feat(tools): add review-issue handlers"
```

---

**Tasks 20–25 continue in `docs/superpowers/plans/2026-08-12-phase3-mcp-tool-surface-part5.md`.**
