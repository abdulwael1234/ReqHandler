"""SQLite connection management with pragma setup.

Provides DatabaseConnection class that:
- Opens connections with FK enforcement (PRAGMA foreign_keys = ON)
- Configures WAL journal mode
- Provides transaction() and read_only() context managers

See: LLD-02 §4 (Connection Management — SRS-032, SRS-084)
"""
