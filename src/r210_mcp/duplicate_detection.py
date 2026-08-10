"""Name-normalization and duplicate comparison logic.

Implements duplicate detection per SRS-034:
- Normalize names (case-insensitive, whitespace-collapsed)
- Compare against existing records
- Return warnings (never block creation)

See: LLD-02 §8 (Duplicate Detection)
"""
