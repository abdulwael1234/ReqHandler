"""Name-normalized duplicate detection.

SRS-034 compares names *after* normalization on both sides: trim, collapse
internal whitespace, case-insensitive. The DAL's `find_duplicates_by_name`
matches with `= ? COLLATE NOCASE` against the indexes V001 created, which
covers case but not whitespace — and post-filtering an exact-match query
cannot recover a stored name whose internal spacing differs, because such a
row never comes back to be filtered.

This module therefore compares normalized forms over the candidate rows.
SRS-113 rules out performance optimization for the prototype, so correctness
against the requirement is chosen over the index (DEV-36).

See: LLD-02 §8 (Duplicate Detection — SRS-034, SRS-121)
"""

import sqlite3

from .db.dal import TABLE_COLUMNS, DataAccessLayer
from .validation.common import normalize_name


def check_for_duplicates(
    conn: sqlite3.Connection,
    dal: DataAccessLayer,
    table: str,
    name: str,
    kind: str | None = None,
) -> list[dict[str, str]]:
    """Existing records whose normalized name equals this one (SRS-034)."""
    if "name" not in TABLE_COLUMNS.get(table, ()):
        raise ValueError(f"{table} has no name column")

    target = normalize_name(name)
    filters = {"kind": kind} if kind is not None else None
    return [
        {"unique_key": str(record.unique_key), "name": str(record.name)}
        for record in dal.query_table(conn, table, filters)
        if normalize_name(str(record.name)) == target
    ]


def duplicate_warning(table: str, name: str, matches: list[dict[str, str]]) -> str:
    """Human-readable warning returned in the create response (SRS-121)."""
    keys = ", ".join(match["unique_key"] for match in matches)
    return (
        f"Possible duplicate: {table} already contains {len(matches)} record(s) "
        f"named {name!r} (unique_key: {keys}). Review before approving."
    )
