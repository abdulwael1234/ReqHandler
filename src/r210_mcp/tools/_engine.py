"""Descriptors and shared steps for the regular create/update/query tools.

The 13 creates, 13 updates and 6 queries are one algorithm each, parameterized
by table. Holding that algorithm once means the cross-cutting rules — SRS-091a
status rejection, SRS-082b content demotion, SRS-035c parent demotion — have
exactly one implementation rather than one per tool (DEV-32). This mirrors the
generic core the DAL already uses behind its typed surface (DEV-18).

See: LLD-02 §7 (Tool Handler Implementations), §10 (Update Rules)
"""

import sqlite3
from dataclasses import dataclass
from dataclasses import fields as dataclass_fields
from typing import Any, Protocol
from uuid import uuid4

from ..db.dal import DataAccessLayer
from ..db.models import ARTIFACT_TYPE_TABLE_MAP, CHILD_PARENT_MAP, STRUCTURAL_SUBTYPE_TABLES
from ..duplicate_detection import check_for_duplicates, duplicate_warning
from ..errors import McpResult, McpValidationError
from ..validation.common import validate_choice, validate_uuid_format
from ..validation.status import INITIAL_STATUSES, auto_demote_parent_chain
from .context import ToolContext

# Table → the artifact_type name a ReviewIssue uses to point at it (SRS-074).
ARTIFACT_TYPE_FOR_TABLE: dict[str, str] = {
    table: artifact_type for artifact_type, table in ARTIFACT_TYPE_TABLE_MAP.items()
}


class FieldValidator(Protocol):
    """A common validator, bound to the tool name at call time."""

    def __call__(self, value: Any, field: str, *, operation: str) -> None: ...


def choice_of(permitted: frozenset[str]) -> FieldValidator:
    """Adapt `validate_choice` to the single-value validator shape."""

    def _validate(value: Any, field: str, *, operation: str) -> None:
        validate_choice(value, permitted, field, operation=operation)

    return _validate


@dataclass(frozen=True)
class FieldSpec:
    """One plain column, written from one argument."""

    arg: str
    column: str
    required: bool = False
    validator: FieldValidator | None = None


@dataclass(frozen=True)
class RefSpec:
    """A `*_key` argument resolved to an integer foreign key."""

    arg: str
    column: str
    table: str
    required: bool = False
    parent: bool = False
    may_be_unresolved: bool = False


class PostCreateHook(Protocol):
    """Extra work to run inside the create transaction, after the insert."""

    def __call__(
        self,
        conn: sqlite3.Connection,
        dal: DataAccessLayer,
        unique_key: str,
        source_requirement_id: int | None,
    ) -> None: ...


@dataclass(frozen=True)
class CreateSpec:
    tool: str
    table: str
    fields: tuple[FieldSpec, ...] = ()
    refs: tuple[RefSpec, ...] = ()
    duplicate_name_arg: str | None = None
    duplicate_kind_arg: str | None = None
    has_status: bool = True
    # Runs inside the same transaction as the insert, so a tool whose
    # requirement pairs a record with a ReviewIssue commits both or neither.
    post_create: PostCreateHook | None = None


@dataclass(frozen=True)
class UpdateSpec:
    tool: str
    table: str
    fields: tuple[FieldSpec, ...] = ()
    refs: tuple[RefSpec, ...] = ()
    immutable_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class QuerySpec:
    tool: str
    table: str
    filters: tuple[FieldSpec, ...] = ()


def record_to_dict(record: Any) -> dict[str, Any]:
    """Expand a record dataclass into a response payload."""
    return {field.name: getattr(record, field.name) for field in dataclass_fields(record)}


def _response_data(record: Any, demoted: list[str]) -> dict[str, Any]:
    """The record payload a tool returns: no `id`, no duplicated `unique_key`."""
    data = record_to_dict(record)
    data.pop("id", None)
    data.pop("unique_key", None)
    if demoted:
        data["demoted"] = demoted
    return data


def reject_status_argument(tool: str, arguments: dict[str, Any]) -> None:
    """Reject `status` in an update tool (SRS-091a, LLD-02 §10)."""
    if "status" in arguments:
        raise McpValidationError.of(
            tool,
            "Status cannot be changed through update tools. "
            "Use 'set_review_status' instead (SRS-091a).",
            field="status",
            affected_key=arguments.get("unique_key"),
        )


def reject_unknown_arguments(
    tool: str, arguments: dict[str, Any], permitted: frozenset[str]
) -> None:
    """Reject any argument the tool does not define (SRS-083)."""
    unknown = sorted(set(arguments) - permitted)
    if unknown:
        raise McpValidationError.of(
            tool,
            f"unknown argument for {tool}: {unknown[0]}",
            field=unknown[0],
            affected_key=arguments.get("unique_key"),
        )


def collect_fields(
    tool: str,
    fields: tuple[FieldSpec, ...],
    arguments: dict[str, Any],
    *,
    require: bool,
) -> dict[str, Any]:
    """Validate the supplied arguments and map them to column names.

    `require=True` on the create path enforces presence; `require=False` on the
    update path validates only what the caller actually supplied.
    """
    values: dict[str, Any] = {}
    for spec in fields:
        if spec.arg not in arguments:
            if require and spec.required:
                raise McpValidationError.of(
                    tool,
                    f"{spec.arg} is required",
                    field=spec.arg,
                    affected_key=arguments.get("unique_key"),
                )
            continue
        value = arguments[spec.arg]
        if spec.validator is not None and not (value is None and not spec.required):
            spec.validator(value, spec.arg, operation=tool)
        values[spec.column] = value
    return values


def initial_status(tool: str, arguments: dict[str, Any]) -> str:
    """The status a create tool assigns (SRS-035a, LLD-02 §7.1).

    Only the three non-terminal states are accepted; `approved` and `rejected`
    are review outcomes that no create tool may claim (SRS-082a).
    """
    value = arguments.get("initial_status")
    if value is None:
        return "pending_review"
    if value not in INITIAL_STATUSES:
        permitted = ", ".join(sorted(INITIAL_STATUSES))
        raise McpValidationError.of(
            tool,
            f"initial_status must be one of: {permitted}",
            field="initial_status",
        )
    return str(value)


def resolve_refs(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    tool: str,
    refs: tuple[RefSpec, ...],
    arguments: dict[str, Any],
    *,
    fill_absent: bool,
) -> tuple[dict[str, Any], list[str], int | None]:
    """Resolve every `*_key` argument to an integer id.

    Returns the column values, the columns left unresolved (SRS-036a), and the
    parent record's id when one of the refs is marked `parent`.

    `fill_absent=True` on the create path writes NULL for an omitted optional
    reference; on the update path an omitted argument is left untouched, so an
    absent key never silently clears an existing foreign key.
    """
    values: dict[str, Any] = {}
    unresolved: list[str] = []
    parent_id: int | None = None

    for spec in refs:
        if spec.arg not in arguments and not fill_absent:
            continue

        key = arguments.get(spec.arg)
        if key is None:
            if spec.required:
                raise McpValidationError.of(tool, f"{spec.arg} is required", field=spec.arg)
            values[spec.column] = None
            if spec.may_be_unresolved:
                unresolved.append(spec.column)
            continue

        record = dal.get_record_by_unique_key(conn, spec.table, str(key))
        if record is None:
            raise McpValidationError.of(
                tool,
                f"{spec.arg} does not resolve to an existing {spec.table} record",
                field=spec.arg,
                affected_key=str(key),
            )
        values[spec.column] = record.id
        if spec.parent:
            parent_id = int(record.id)

    return values, unresolved, parent_id


def create_unresolved_issue(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    table: str,
    artifact_key: str,
    column: str,
    source_requirement_id: int | None,
) -> str:
    """Record an unresolved type reference for review (SRS-036a).

    A structural subtype row is not an independently reviewable artifact type
    (SRS-035a, SRS-074), so an unresolved `ArrayTypeDefinitions` reference is
    reported against the parent `TypeDefinitions` record (LLD-02 §7.2 step 8).
    """
    issue_key = str(uuid4())
    dal.insert_review_issue(
        conn,
        unique_key=issue_key,
        issue_type="unresolved_reference",
        message=f"{table}.{column} is unresolved; resolve it before approval (SRS-036a).",
        source_requirement_id=source_requirement_id,
        artifact_type=ARTIFACT_TYPE_FOR_TABLE[table],
        artifact_unique_key=artifact_key,
    )
    return issue_key


def _reference_issues(
    conn: sqlite3.Connection, dal: DataAccessLayer, artifact_key: str
) -> list[Any]:
    """Every `unresolved_reference` issue for one artifact, whatever its status."""
    return dal.query_review_issues(
        conn, {"artifact_unique_key": artifact_key, "issue_type": "unresolved_reference"}
    )


def reopen_or_create_reference_issue(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    table: str,
    artifact_key: str,
    column: str,
    source_requirement_id: int | None,
) -> None:
    """Record that a reference is unresolved, reusing the existing issue.

    A reference that is resolved and then cleared again must **reopen** its
    original issue rather than accumulate a second one: SRS-036a describes one
    tracking issue per unresolved reference, not one per edit.
    """
    existing = _reference_issues(conn, dal, artifact_key)
    if not existing:
        create_unresolved_issue(conn, dal, table, artifact_key, column, source_requirement_id)
        return
    for issue in existing:
        if issue.status != "pending":
            dal.update_record(
                conn,
                "ReviewIssues",
                issue.id,
                {"status": "pending", "resolution": None},
            )


def resolve_reference_issues(
    conn: sqlite3.Connection, dal: DataAccessLayer, artifact_key: str
) -> None:
    """Close the tracking issues once the reference resolves (SRS-036a)."""
    for issue in _reference_issues(conn, dal, artifact_key):
        if issue.status == "pending":
            dal.update_record(
                conn,
                "ReviewIssues",
                issue.id,
                {"status": "resolved", "resolution": "Reference resolved by update."},
            )


def sync_unresolved_issues(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    table: str,
    record: Any,
    changed: dict[str, Any],
    refs: tuple[RefSpec, ...],
) -> None:
    """Open or resolve the reference issue when an SRS-036a column changes.

    LLD-02 §7.2 step 4 requires the issue to follow the reference: resolving a
    reference resolves its issue, clearing one reopens it. Both happen inside
    the caller's transaction.
    """
    for spec in refs:
        if not spec.may_be_unresolved or spec.column not in changed:
            continue
        artifact_key = str(record.unique_key)
        if changed[spec.column] is None:
            reopen_or_create_reference_issue(
                conn,
                dal,
                table,
                artifact_key,
                spec.column,
                getattr(record, "source_requirement_id", None),
            )
        else:
            resolve_reference_issues(conn, dal, artifact_key)


def demote_parent_on_child_creation(
    conn: sqlite3.Connection, dal: DataAccessLayer, child_table: str, parent_id: int
) -> list[str]:
    """Demote an approved parent when a pending child is added (LLD-02 §10.4)."""
    relation = CHILD_PARENT_MAP.get(child_table)
    if relation is None:
        return []
    parent = dal.get_record_by_id(conn, relation.parent_table, parent_id)
    if parent is None:
        return []
    demoted: list[str] = []
    if parent.status == "approved":
        dal.update_status(conn, relation.parent_table, parent_id, "pending_review", None)
        demoted.append(str(parent.unique_key))
    demoted.extend(auto_demote_parent_chain(conn, dal, relation.parent_table, parent_id))
    return demoted


def demote_if_approved(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    table: str,
    record_id: int,
    changed: dict[str, Any],
) -> list[str]:
    """Demote an approved record whose content changed (SRS-082b, §10.1).

    A structural subtype row has no status of its own (SRS-035a), so its
    change demotes the parent `TypeDefinitions` record instead.
    """
    if not changed:
        return []

    record = dal.get_record_by_id(conn, table, record_id)
    if record is None:
        return []

    if table in STRUCTURAL_SUBTYPE_TABLES:
        parent = dal.get_record_by_id(conn, "TypeDefinitions", record.type_definition_id)
        if parent is None or parent.status != "approved":
            return []
        dal.update_status(conn, "TypeDefinitions", parent.id, "pending_review", None)
        return [str(parent.unique_key)]

    demoted: list[str] = []
    if record.status == "approved":
        dal.update_status(conn, table, record_id, "pending_review", None)
        demoted.append(str(record.unique_key))
    if table in CHILD_PARENT_MAP:
        demoted.extend(auto_demote_parent_chain(conn, dal, table, record_id))
    return demoted


def _permitted_create_arguments(spec: CreateSpec) -> frozenset[str]:
    names = {field.arg for field in spec.fields} | {ref.arg for ref in spec.refs}
    if spec.has_status:
        names.add("initial_status")
    return frozenset(names)


def _permitted_update_arguments(spec: UpdateSpec) -> frozenset[str]:
    names = {field.arg for field in spec.fields} | {ref.arg for ref in spec.refs}
    names.add("unique_key")
    return frozenset(names)


def run_create(ctx: ToolContext, spec: CreateSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a create descriptor (LLD-02 §7).

    Everything runs inside one transaction, reads included: resolving a key and
    then inserting against it in a separate transaction would leave a window in
    which the target disappears (SRS-084).
    """
    reject_unknown_arguments(spec.tool, arguments, _permitted_create_arguments(spec))
    values = collect_fields(spec.tool, spec.fields, arguments, require=True)
    status = initial_status(spec.tool, arguments) if spec.has_status else None
    unique_key = str(uuid4())
    warnings: list[str] = []

    with ctx.db.transaction() as conn:
        ref_values, unresolved, parent_id = resolve_refs(
            conn, ctx.dal, spec.tool, spec.refs, arguments, fill_absent=True
        )
        row: dict[str, Any] = {"unique_key": unique_key, **values, **ref_values}
        if status is not None:
            row["status"] = status

        duplicates: list[dict[str, str]] = []
        if spec.duplicate_name_arg is not None:
            name = arguments.get(spec.duplicate_name_arg)
            kind = (
                arguments.get(spec.duplicate_kind_arg)
                if spec.duplicate_kind_arg is not None
                else None
            )
            if isinstance(name, str):
                duplicates = check_for_duplicates(conn, ctx.dal, spec.table, name, kind)
                if duplicates:
                    warnings.append(duplicate_warning(spec.table, name, duplicates))

        record_id = ctx.dal.insert_record(conn, spec.table, row)
        source_requirement_id = ref_values.get("source_requirement_id")

        for column in unresolved:
            create_unresolved_issue(
                conn, ctx.dal, spec.table, unique_key, column, source_requirement_id
            )

        if duplicates and spec.table in ARTIFACT_TYPE_FOR_TABLE:
            ctx.dal.insert_review_issue(
                conn,
                unique_key=str(uuid4()),
                issue_type="ambiguous",
                message=warnings[0],
                source_requirement_id=source_requirement_id,
                artifact_type=ARTIFACT_TYPE_FOR_TABLE[spec.table],
                artifact_unique_key=unique_key,
            )

        if spec.post_create is not None:
            spec.post_create(conn, ctx.dal, unique_key, source_requirement_id)

        demoted: list[str] = []
        if parent_id is not None:
            demoted = demote_parent_on_child_creation(conn, ctx.dal, spec.table, parent_id)

        created = ctx.dal.get_record_by_id(conn, spec.table, record_id)

    return McpResult(
        unique_key=unique_key, data=_response_data(created, demoted), warnings=warnings
    ).to_dict()


def run_update(ctx: ToolContext, spec: UpdateSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute an update descriptor (LLD-02 §10.2)."""
    reject_status_argument(spec.tool, arguments)
    key = arguments.get("unique_key")
    validate_uuid_format(key, "unique_key", operation=spec.tool)

    for name in spec.immutable_args:
        if name in arguments:
            raise McpValidationError.of(
                spec.tool,
                f"{name} cannot be changed after creation (SRS-120)",
                field=name,
                affected_key=str(key),
            )

    reject_unknown_arguments(spec.tool, arguments, _permitted_update_arguments(spec))
    values = collect_fields(spec.tool, spec.fields, arguments, require=False)

    with ctx.db.transaction() as conn:
        record = ctx.dal.get_record_by_unique_key(conn, spec.table, str(key))
        if record is None:
            raise McpValidationError.of(
                spec.tool,
                f"no {spec.table} record with unique_key {key!r}",
                field="unique_key",
                affected_key=str(key),
            )
        ref_values, _unresolved, _parent_id = resolve_refs(
            conn, ctx.dal, spec.tool, spec.refs, arguments, fill_absent=False
        )
        changed = {**values, **ref_values}
        if changed:
            ctx.dal.update_record(conn, spec.table, record.id, changed)
        sync_unresolved_issues(conn, ctx.dal, spec.table, record, changed, spec.refs)
        demoted = demote_if_approved(conn, ctx.dal, spec.table, record.id, changed)
        updated = ctx.dal.get_record_by_id(conn, spec.table, record.id)

    return McpResult(unique_key=str(key), data=_response_data(updated, demoted)).to_dict()


def run_query(ctx: ToolContext, spec: QuerySpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute a query descriptor (LLD-02 §7.1).

    Read-only: no transaction is opened. Projection is not applied here — the
    dispatch boundary owns it, so a handler cannot omit it (DEV-30).
    """
    permitted = frozenset({field.arg for field in spec.filters})
    reject_unknown_arguments(spec.tool, arguments, permitted)
    filters = collect_fields(spec.tool, spec.filters, arguments, require=False)

    with ctx.db.read_only() as conn:
        records = ctx.dal.query_table(conn, spec.table, filters or None)

    payload = [record_to_dict(record) for record in records]
    for row in payload:
        row.pop("id", None)
    return {"result": {"table": spec.table, "count": len(payload), "records": payload}}
