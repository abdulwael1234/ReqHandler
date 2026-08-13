"""Status transition rules, parent-approval blocking, and demotion.

Implements:
- ARTIFACT_TRANSITIONS and ISSUE_TRANSITIONS enforcement (SRS-035b)
- check_parent_can_be_approved() — excludes rejected children (SRS-046, SRS-053, SRS-092a)
- auto_demote_parent_chain() — cascading demotion (SRS-035c)
- check_references_resolved() — the approval half of SRS-036a

See: LLD-02 §6.2 (Status Validators), §3.5 (Parent-Child Registry)
"""

import sqlite3
from typing import Any

from ..db.dal import DataAccessLayer
from ..db.models import (
    ARTIFACT_TRANSITIONS,
    CHILD_PARENT_MAP,
    ISSUE_TRANSITIONS,
    PARENT_CHILD_MAP,
)
from ..errors import McpValidationError

# Statuses a create tool may assign. Approval and rejection are review
# outcomes, not creation-time claims (SRS-035a, LLD-02 §7.1).
INITIAL_STATUSES = frozenset({"pending_review", "ambiguous", "out_of_scope"})

# The four cross-artifact type references SRS-036a allows to stay NULL. A
# record holding one of these unresolved may not be approved or exported.
UNRESOLVED_REFERENCE_COLUMNS: dict[str, str] = {
    "ArrayTypeDefinitions": "element_type_id",
    "StructElements": "element_type_id",
    "InterfaceDataElements": "type_definition_id",
    "OperationArguments": "type_definition_id",
}


def _validate_transition(
    matrix: dict[str, frozenset[str]],
    current: str,
    requested: str,
    operation: str,
    affected_key: str | None,
    field: str,
) -> None:
    if requested not in matrix.get(current, frozenset()):
        permitted = ", ".join(sorted(matrix.get(current, frozenset()))) or "(none)"
        raise McpValidationError.of(
            operation,
            f"transition {current!r} -> {requested!r} is not permitted; "
            f"permitted from {current!r}: {permitted}",
            field=field,
            affected_key=affected_key,
        )


def validate_artifact_transition(
    current: str,
    requested: str,
    *,
    operation: str,
    affected_key: str | None = None,
    field: str = "new_status",
) -> None:
    """Reject a transition outside the artifact matrix (SRS-035b)."""
    _validate_transition(ARTIFACT_TRANSITIONS, current, requested, operation, affected_key, field)


def validate_issue_transition(
    current: str,
    requested: str,
    *,
    operation: str,
    affected_key: str | None = None,
    field: str = "new_status",
) -> None:
    """Reject a transition outside the review-issue matrix (SRS-035b).

    `field` is caller-chosen because the two tools name their argument
    differently: `set_review_status` takes `new_status`, `update_review_issue`
    takes `status`. SRS-109 requires the error to name the field the caller
    actually supplied.
    """
    _validate_transition(ISSUE_TRANSITIONS, current, requested, operation, affected_key, field)


def check_parent_can_be_approved(
    conn: sqlite3.Connection, dal: DataAccessLayer, parent_table: str, parent_id: int
) -> list[dict[str, str]]:
    """Children blocking approval of this parent (SRS-046, SRS-053).

    Rejected children are excluded — an incorrectly extracted child must not
    permanently block its parent (SRS-092a).
    """
    blockers: list[dict[str, str]] = []
    for relation in PARENT_CHILD_MAP.get(parent_table, []):
        statuses = dal.get_children_statuses(
            conn, relation.child_table, relation.fk_column, parent_id
        )
        for status in statuses:
            if status not in ("approved", "rejected"):
                blockers.append({"child_table": relation.child_table, "status": status})
    return blockers


def auto_demote_parent_chain(
    conn: sqlite3.Connection, dal: DataAccessLayer, child_table: str, child_id: int
) -> list[str]:
    """Demote every approved ancestor to pending_review (SRS-035c).

    Walks the whole chain rather than stopping at the first non-approved
    ancestor: a grandparent may be approved while the parent is not.
    Returns the demoted unique_keys, for reporting in the tool response.
    """
    demoted: list[str] = []
    current_table, current_id = child_table, child_id
    while current_table in CHILD_PARENT_MAP:
        found = dal.get_parent_record(conn, current_table, current_id)
        if found is None:
            break
        parent_table, parent = found
        if parent.status == "approved":
            dal.update_status(conn, parent_table, parent.id, "pending_review", None)
            demoted.append(str(parent.unique_key))
        current_table, current_id = parent_table, int(parent.id)
    return demoted


def check_references_resolved(
    conn: sqlite3.Connection, dal: DataAccessLayer, table: str, record: Any
) -> list[str]:
    """Columns still NULL that SRS-036a requires resolved before approval.

    A `TypeDefinitions` record of kind `array` carries its reference on the
    `ArrayTypeDefinitions` detail row, which is not independently reviewable
    (SRS-035a), so approving the parent checks the child's column.
    """
    column = UNRESOLVED_REFERENCE_COLUMNS.get(table)
    if column is not None:
        return [column] if getattr(record, column) is None else []

    if table == "TypeDefinitions" and record.kind == "array":
        detail = dal.get_array_type_definition_by_parent(conn, record.id)
        if detail is not None and detail.element_type_id is None:
            return ["element_type_id"]
    return []
