"""SQLite connection management with pragma setup.

Provides DatabaseConnection class that:
- Opens connections with FK enforcement (PRAGMA foreign_keys = ON)
- Configures WAL journal mode
- Provides transaction() and read_only() context managers

See: LLD-02 §4 (Connection Management — SRS-032, SRS-084)
"""

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager

# Milliseconds a blocked connection waits for a lock before raising
# sqlite3.OperationalError (LLD-02 §4.1).
BUSY_TIMEOUT_MS = 5000


class DatabaseConnection:
    """Manages SQLite connections with the pragmas the schema requires."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> str:
        return self._db_path

    def connect(self) -> sqlite3.Connection:
        """Open a connection with foreign keys on, WAL, and row access by name.

        ``isolation_level=None`` disables the driver's implicit transaction
        handling so that the explicit ``BEGIN IMMEDIATE`` in ``transaction()``
        is the only transaction control in play. Phase 1 established this for
        the initializer (DEV-03); the same reasoning applies here.
        """
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.execute("PRAGMA foreign_keys = ON")  # SRS-032
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """Run a single write transaction, rolling back on any failure (SRS-084).

        ``BEGIN IMMEDIATE`` takes the reserved lock up front rather than on the
        first write, so a second writer fails fast instead of deadlocking part
        way through. The prototype is single-writer, so this costs nothing.
        """
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def read_only(self) -> Generator[sqlite3.Connection, None, None]:
        """Open a connection for reads, with no transaction started."""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()
