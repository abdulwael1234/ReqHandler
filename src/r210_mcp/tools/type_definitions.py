"""Type-definition tools: the parent, its subtype detail, and its children.

`create_type_definition` writes a parent row, one subtype detail row, and any
number of child rows in a single transaction, with a shape that depends on
`kind` (LLD-02 §7.2). That is not the engine's regular shape, so it is written
out; everything else here is a descriptor.

See: LLD-02 §7.2 (Type Definition Tools — SRS-038a, SRS-043, SRS-044, SRS-086)
"""

import sqlite3
from typing import Any
from uuid import uuid4

from ..db.models import ARTIFACT_STATUSES
from ..duplicate_detection import check_for_duplicates, duplicate_warning
from ..errors import McpResult, McpValidationError
from ..validation.common import (
    validate_not_empty,
    validate_position,
    validate_positive_int,
    validate_uuid_format,
)
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
    collect_fields,
    create_unresolved_issue,
    demote_if_approved,
    initial_status,
    record_to_dict,
    reject_status_argument,
    reject_unknown_arguments,
    reopen_or_create_reference_issue,
    resolve_reference_issues,
    resolve_refs,
    run_create,
    run_query,
    run_update,
)
from .context import ToolContext

_CREATE_TOOL = "create_type_definition"

_CREATE_ARGUMENTS = frozenset(
    {"name", "kind", "description", "source_requirement_key", "subtype", "initial_status"}
)

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
    refs=(
        RefSpec("element_type_key", "element_type_id", "TypeDefinitions", may_be_unresolved=True),
    ),
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
    tool = "create_struct_element" if kind == "struct" else "create_enum_value"
    with ctx.db.read_only() as conn:
        parent = ctx.dal.get_type_definition_by_key(conn, key)
        if parent is None:
            return
        validate_parent_kind(conn, ctx.dal, parent.id, kind, operation=tool, field=arg)


def _resolve_element_type(
    ctx: ToolContext, conn: sqlite3.Connection, key: Any, field: str
) -> int | None:
    """Resolve a type reference, or None while unresolved (SRS-036a)."""
    if key is None:
        return None
    target = ctx.dal.get_type_definition_by_key(conn, str(key))
    if target is None:
        raise McpValidationError.of(
            _CREATE_TOOL,
            f"{field} does not resolve to an existing TypeDefinitions record",
            field=field,
            affected_key=str(key),
        )
    return int(target.id)


def _insert_subtype(
    ctx: ToolContext,
    conn: sqlite3.Connection,
    kind: str,
    subtype: dict[str, Any],
    parent_id: int,
    parent_key: str,
    source_requirement_id: int | None,
) -> None:
    """Insert the kind-specific detail rows (LLD-02 §7.2 steps 7-8)."""
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
        element_type_id = _resolve_element_type(
            ctx, conn, subtype.get("element_type_key"), "subtype.element_type_key"
        )
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
            validate_not_empty(
                element.get("name"), "subtype.elements[].name", operation=_CREATE_TOOL
            )
            validate_position(
                element.get("position"), "subtype.elements[].position", operation=_CREATE_TOOL
            )
            child_key = str(uuid4())
            element_type_id = _resolve_element_type(
                ctx, conn, element.get("element_type_key"), "subtype.elements[].element_type_key"
            )
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
                    conn,
                    ctx.dal,
                    "StructElements",
                    child_key,
                    "element_type_id",
                    source_requirement_id,
                )
        return

    for value in subtype.get("values", []):
        validate_not_empty(value.get("name"), "subtype.values[].name", operation=_CREATE_TOOL)
        validate_position(
            value.get("position"), "subtype.values[].position", operation=_CREATE_TOOL
        )
        ctx.dal.insert_enum_value(
            conn,
            str(uuid4()),
            parent_id,
            str(value["name"]),
            value.get("value"),
            int(value["position"]),
            value.get("description"),
        )


def handle_create_type_definition(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Create a type definition with its subtype detail (SRS-038a, SRS-086)."""
    reject_unknown_arguments(_CREATE_TOOL, arguments, _CREATE_ARGUMENTS)
    name = arguments.get("name")
    validate_not_empty(name, "name", operation=_CREATE_TOOL)
    kind = arguments.get("kind")
    validate_kind_value(kind, operation=_CREATE_TOOL)
    subtype = validate_subtype_matches_kind(
        str(kind), arguments.get("subtype"), operation=_CREATE_TOOL
    )

    status = initial_status(_CREATE_TOOL, arguments)
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
            status,
        )
        _insert_subtype(
            ctx, conn, str(kind), subtype, parent_id, unique_key, source_requirement_id
        )

        if duplicates:
            ctx.dal.insert_review_issue(
                conn,
                unique_key=str(uuid4()),
                issue_type="ambiguous",
                message=warnings[0],
                source_requirement_id=source_requirement_id,
                artifact_type="type_definition",
                artifact_unique_key=unique_key,
            )
        created = ctx.dal.get_record_by_id(conn, "TypeDefinitions", parent_id)

    data = record_to_dict(created)
    data.pop("id", None)
    data.pop("unique_key", None)
    return McpResult(unique_key=unique_key, data=data, warnings=warnings).to_dict()


_UPDATE_TOOL = "update_type_definition"
_UPDATE_ARGUMENTS = frozenset(
    {"unique_key", "name", "description", "source_requirement_key", "subtype"}
)


def handle_update_type_definition(ctx: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
    """Update a type definition; `kind` and `status` are rejected.

    For an array, `subtype.element_type_key` is updatable (LLD-02 §7.2 step 3).
    That is the only way an unresolved array reference can ever be resolved:
    the detail row lives on `ArrayTypeDefinitions`, which is not independently
    reviewable (SRS-035a) and so has no update tool of its own.
    """
    if "subtype" not in arguments:
        return run_update(ctx, _UPDATE, arguments)

    reject_status_argument(_UPDATE_TOOL, arguments)
    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=_UPDATE_TOOL)
    if "kind" in arguments:
        raise McpValidationError.of(
            _UPDATE_TOOL,
            "kind cannot be changed after creation (SRS-120)",
            field="kind",
            affected_key=str(key),
        )
    reject_unknown_arguments(_UPDATE_TOOL, arguments, _UPDATE_ARGUMENTS)

    subtype = arguments["subtype"]
    if not isinstance(subtype, dict) or "element_type_key" not in subtype:
        raise McpValidationError.of(
            _UPDATE_TOOL,
            "subtype must be an object containing element_type_key; it is the only "
            "updatable subtype field (LLD-02 §7.2)",
            field="subtype",
            affected_key=str(key),
        )

    values = collect_fields(_UPDATE_TOOL, _UPDATE.fields, arguments, require=False)

    with ctx.db.transaction() as conn:
        record = ctx.dal.get_type_definition_by_key(conn, str(key))
        if record is None:
            raise McpValidationError.of(
                _UPDATE_TOOL,
                f"no TypeDefinitions record with unique_key {key!r}",
                field="unique_key",
                affected_key=str(key),
            )
        if record.kind != "array":
            raise McpValidationError.of(
                _UPDATE_TOOL,
                f"subtype.element_type_key applies to kind 'array'; this record is "
                f"{record.kind!r}",
                field="subtype",
                affected_key=str(key),
            )
        detail = ctx.dal.get_array_type_definition_by_parent(conn, record.id)
        if detail is None:
            raise McpValidationError.of(
                _UPDATE_TOOL,
                "array record has no ArrayTypeDefinitions detail row (SRS-038a)",
                field="subtype",
                affected_key=str(key),
            )

        element_type_id = _resolve_element_type(
            ctx, conn, subtype.get("element_type_key"), "subtype.element_type_key"
        )
        ctx.dal.update_record(
            conn, "ArrayTypeDefinitions", detail.id, {"element_type_id": element_type_id}
        )

        # The subtype row is not an independently reviewable artifact type
        # (SRS-035a, SRS-074), so its issue is tracked against the parent.
        if element_type_id is None:
            reopen_or_create_reference_issue(
                conn,
                ctx.dal,
                "TypeDefinitions",
                str(key),
                "element_type_id",
                record.source_requirement_id,
            )
        else:
            resolve_reference_issues(conn, ctx.dal, str(key))

        ref_values, _unresolved, _parent = resolve_refs(
            conn, ctx.dal, _UPDATE_TOOL, _UPDATE.refs, arguments, fill_absent=False
        )
        changed = {**values, **ref_values}
        if changed:
            ctx.dal.update_record(conn, "TypeDefinitions", record.id, changed)

        # A subtype change is a content change on the parent (LLD-02 §10.1),
        # so it demotes an approved parent even when no parent column moved.
        demoted = demote_if_approved(
            conn, ctx.dal, "TypeDefinitions", record.id, {**changed, "subtype": True}
        )
        updated = ctx.dal.get_record_by_id(conn, "TypeDefinitions", record.id)

    data = record_to_dict(updated)
    data.pop("id", None)
    data.pop("unique_key", None)
    if demoted:
        data["demoted"] = demoted
    return McpResult(unique_key=str(key), data=data).to_dict()


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
