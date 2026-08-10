"""Data Access Layer — all SQL queries for CRUD operations.

Provides DataAccessLayer class with methods for:
- Record insertion (all 16 tables)
- Record update (permitted fields only)
- Record query with filters
- Unique-key resolution across tables
- Status updates

See: LLD-02 §7 (Tool Handlers reference DAL for all DB operations)
"""
