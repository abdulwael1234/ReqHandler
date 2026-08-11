"""CLI entry point for database initialization.

Usage:
    python -m r210_db_init init <db_path>
    python -m r210_db_init reset <db_path>  # Development only — destructive

The init command is idempotent and safe to run repeatedly (SRS-098).
The reset command is a development-only destructive operation (SRS-100).

See: LLD-05 §3 (CLI Entry Point)
"""

import argparse
import sys

from .dev_reset import development_reset
from .initializer import DatabaseInitializer


def main() -> None:
    """Entry point for the r210-init-db console script."""
    parser = argparse.ArgumentParser(description="R210 Database Management")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Initialize or upgrade database")
    init_parser.add_argument("db_path", help="Path to SQLite database file")

    reset_parser = subparsers.add_parser(
        "reset", help="DESTRUCTIVE: Reset database (development only)"
    )
    reset_parser.add_argument("db_path", help="Path to SQLite database file")
    reset_parser.add_argument(
        "--confirm", action="store_true", help="Required to proceed with destructive reset"
    )

    args = parser.parse_args()

    if args.command == "init":
        result = DatabaseInitializer(args.db_path).init_db()
        print(f"Database at version {result.final_version}")
        print(f"Migrations applied: {result.migrations_applied}")
        print(f"Status: {result.status}")
        if result.error:
            print(f"Error: {result.error}", file=sys.stderr)
        sys.exit(0 if result.status in ("success", "up_to_date") else 1)

    # args.command == "reset" — subparsers are required, so no other value reaches here.
    if not args.confirm:
        print("ERROR: Reset is destructive. Pass --confirm to proceed.", file=sys.stderr)
        sys.exit(1)
    development_reset(args.db_path)
    print("Database reset complete (development only).")
    sys.exit(0)
