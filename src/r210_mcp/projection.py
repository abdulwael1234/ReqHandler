"""Response projection for Gemini-facing tool calls.

SRS-015a limits what may enter the Gemini model context. The projection is
applied once, at the dispatch boundary in `tools/registry.py`, rather than
inside each query handler as LLD-02 §11.2 sketches: a handler cannot omit a
step it does not perform (DEV-30).

See: LLD-02 §11 (Response Projection — SRS-015a)
"""

from typing import Any

# The permitted response fields, verbatim from SRS-015a. `source_reference`
# stands in for `name` on SourceRequirements; `issue_type` supports
# issue-awareness during extraction.
GEMINI_ALLOWED_FIELDS = frozenset(
    {
        "unique_key",
        "name",
        "kind",
        "interface_type",
        "status",
        "direction",
        "source_reference",
        "issue_type",
    }
)

# Response keys that are tool metadata rather than record fields. SRS-015a
# permits returned unique_keys and duplicate-warning text.
_METADATA_KEYS = frozenset({"unique_key", "warnings", "demoted", "table", "count"})


def project_record(record: dict[str, Any]) -> dict[str, Any]:
    """Drop every field outside the SRS-015a allowlist."""
    return {key: value for key, value in record.items() if key in GEMINI_ALLOWED_FIELDS}


def _project_value(value: Any) -> Any:
    if isinstance(value, dict):
        return project_record(value)
    if isinstance(value, list):
        return [_project_value(item) for item in value]
    return value


def project_response(payload: dict[str, Any], *, records_permitted: bool) -> dict[str, Any]:
    """Project a whole tool response (LLD-02 §11.2).

    `records_permitted` distinguishes the two halves of SRS-015a. Clause (b)
    lets *query* results carry the allowlisted record fields, because the skill
    needs them for duplicate checking and reference resolution. Clause (c)
    limits everything else — the response to a create or update — to returned
    `unique_key` values and duplicate-warning text, so a mutating call reflects
    no content back into the Gemini context.

    An error response passes through unchanged: it carries no record fields,
    and SRS-109 requires the operation, field, reason and affected key.
    """
    if "error" in payload:
        return payload
    result = payload.get("result")
    if not isinstance(result, dict):
        return payload

    projected: dict[str, Any] = {}
    for key, value in result.items():
        if key in _METADATA_KEYS:
            projected[key] = value
        elif not records_permitted:
            continue
        elif isinstance(value, dict | list):
            projected[key] = _project_value(value)
        elif key in GEMINI_ALLOWED_FIELDS:
            projected[key] = value
    return {"result": projected}
