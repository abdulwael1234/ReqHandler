"""Development-only destructive database reset.

WARNING: This deletes all data. Requires --confirm flag (SRS-100).
Not exposed through MCP or the Gemini workflow (SRS-093, SRS-100).

See: LLD-05 §6 (Development Reset)
"""

import sqlite3

from .initializer import DatabaseInitializer


def development_reset(db_path: str) -> None:
    """DESTRUCTIVE: Drop all tables and recreate the schema from scratch.

    This function is for DEVELOPMENT USE ONLY.
    It is NOT exposed through MCP (SRS-093).
    It is NOT part of the Gemini workflow (SRS-100).

    Raises:
        RuntimeError: if the database cannot be re-initialized afterwards.
    """
    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        # Internal SQLite tables (sqlite_sequence, sqlite_stat1, ...) cannot be
        # dropped and are not ours to remove.
        tables = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]

        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        for table in tables:
            conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.execute("COMMIT")
    finally:
        conn.close()

    result = DatabaseInitializer(db_path).init_db()
    if result.status == "failed":
        raise RuntimeError(f"Database reset failed to re-initialize the schema: {result.error}")
