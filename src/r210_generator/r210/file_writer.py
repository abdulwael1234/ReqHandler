"""Deterministic file output.

Writes files with:
- UTF-8 encoding without BOM
- LF line endings (no CRLF)
- Single trailing newline
- Sorted file creation order

See: LLD-04 §8 (Deterministic File Output — SRS-101)
"""
