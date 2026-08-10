"""Main initializer orchestration.

Implements DatabaseInitializer class that:
- Creates the database file if it doesn't exist (SRS-095)
- Applies pending migrations in order (SRS-096, SRS-124)
- Tracks schema version (SRS-097)
- Verifies schema integrity (tables, indexes, FK constraints)
- Preserves all existing data (SRS-099)

See: LLD-05 §4 (Initializer Orchestration)
"""
