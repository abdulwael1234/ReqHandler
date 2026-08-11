"""CLI entry point for database initialization.

Usage:
    python -m r210_db_init init <db_path>
    python -m r210_db_init reset <db_path>  # Development only — destructive

The init command is idempotent and safe to run repeatedly (SRS-098).
The reset command is a development-only destructive operation (SRS-100).

See: LLD-05 §3 (CLI Entry Point)
"""

import sys


def main() -> None:
    """Entry point for r210-init-db console script.

    TODO: Implement argument parsing and dispatch to DatabaseInitializer.
    """
    print("r210-init-db: not yet implemented", file=sys.stderr)
    sys.exit(1)
