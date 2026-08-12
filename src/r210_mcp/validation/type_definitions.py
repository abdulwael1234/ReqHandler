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
