"""Base migration class.

Each migration:
- Has a description for the schema_version record
- Implements up() to apply schema changes
- Uses CREATE TABLE IF NOT EXISTS for idempotency (SRS-098)
- Never loses existing content; constraint-changing rebuilds copy all rows and
  run transactionally before replacing an old table (SRS-099, SRS-124)

See: LLD-05 §5.1 (Base Migration Class)
"""

import sqlite3
from abc import ABC, abstractmethod


class Migration(ABC):
    """Base class for database migrations."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of this migration."""

    @abstractmethod
    def up(self, conn: sqlite3.Connection) -> None:
        """Apply this migration's schema changes.

        Runs inside a transaction managed by the initializer.
        Do NOT call conn.commit() or conn.rollback().
        """
