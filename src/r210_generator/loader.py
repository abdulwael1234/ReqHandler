"""Database query layer — loads all records into an immutable snapshot.

Uses BEGIN transaction for snapshot isolation. All queries use explicit
ORDER BY clauses for determinism.

See: LLD-04 §9 (Data Loading — SRS-101)
"""
