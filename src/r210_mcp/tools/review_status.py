"""Tool handler for set_review_status — the sole mechanism for changing
artifact and reviewable-child status.

Implements:
- Status transition validation (SRS-035b)
- Caller-based approval gate (SRS-082a)
- Parent approval check excluding rejected children (SRS-046, SRS-053, SRS-092a)
- Automatic parent-chain demotion (SRS-035c)
- Scope restriction: artifacts and reviewable children only (SRS-091a)

See: LLD-02 §7.7 (Review Status Tool)
"""
