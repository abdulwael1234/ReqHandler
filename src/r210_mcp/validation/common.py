"""Shared field validators and name normalization.

Every validator takes the `operation` (tool) name because `McpError` requires
it — SRS-109 mandates that an error identify the failing operation, and a
validator that does not receive the tool name cannot build one. LLD-02 §6.1
omits the parameter (DEV-34).

See: LLD-02 §6.1 (Common Validators — SRS-083)
"""

import re
from typing import Any
from uuid import UUID

from ..db.models import ARTIFACT_TYPE_TABLE_MAP
from ..errors import McpValidationError

_WHITESPACE = re.compile(r"\s+")


def _fail(operation: str, field: str, reason: str, affected_key: str | None) -> None:
    raise McpValidationError.of(operation, reason, field=field, affected_key=affected_key)


def validate_not_empty(
    value: Any, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject None, a non-string, or a string that is empty after stripping."""
    if not isinstance(value, str) or not value.strip():
        _fail(operation, field, f"{field} must be a non-empty string", affected_key)


def validate_uuid_format(
    value: Any, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject anything that is not a UUID string (SRS-027)."""
    if not isinstance(value, str):
        _fail(operation, field, f"{field} must be a UUID string", affected_key)
        return
    try:
        UUID(value)
    except ValueError:
        _fail(operation, field, f"{field} is not a valid UUID: {value!r}", affected_key)


def validate_choice(
    value: Any,
    permitted: frozenset[str],
    field: str,
    *,
    operation: str,
    affected_key: str | None = None,
) -> None:
    """Reject a value outside the permitted set, naming the permitted values."""
    if value not in permitted:
        allowed = ", ".join(sorted(permitted))
        _fail(operation, field, f"{field} must be one of: {allowed}", affected_key)


def _is_int(value: Any) -> bool:
    # bool is a subclass of int; True is not a position.
    return isinstance(value, int) and not isinstance(value, bool)


def validate_position(
    value: Any, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject a position that is not an integer >= 1 (SRS-038b)."""
    if not _is_int(value) or value < 1:
        _fail(operation, field, f"{field} must be an integer >= 1", affected_key)


def validate_positive_int(
    value: Any, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject a size that is not an integer >= 1 (SRS-038b)."""
    if not _is_int(value) or value < 1:
        _fail(operation, field, f"{field} must be an integer >= 1", affected_key)


def validate_artifact_type(
    value: str | None, field: str, *, operation: str, affected_key: str | None = None
) -> None:
    """Reject an artifact_type outside the eleven permitted values (SRS-074)."""
    if value is None:
        return
    if value not in ARTIFACT_TYPE_TABLE_MAP:
        allowed = ", ".join(sorted(ARTIFACT_TYPE_TABLE_MAP))
        _fail(operation, field, f"{field} must be one of: {allowed}", affected_key)


def normalize_name(name: str) -> str:
    """Trim, collapse internal whitespace, lowercase (SRS-034)."""
    return _WHITESPACE.sub(" ", name.strip()).lower()
