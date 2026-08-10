"""CLI entry point for database initialization.

Usage:
    python -m r210_db_init init <db_path>
    python -m r210_db_init reset <db_path>  # Development only — destructive

The init command is idempotent and safe to run repeatedly (SRS-098).
The reset command is a development-only destructive operation (SRS-100).

See: LLD-05 §3 (CLI Entry Point)
"""
