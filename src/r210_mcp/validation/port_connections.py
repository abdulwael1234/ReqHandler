"""Port connection validators: member existence, uniqueness, cardinality, compatibility.

Validates:
- All members reference existing port prototypes (SRS-069)
- No duplicate members within a connection (SRS-070)
- Interface compatibility — TBD, creates ReviewIssue (SRS-071, SRS-125)
- Direction cardinality: ≥1 provider, ≥1 requester (SRS-072)
- Whole-connection revalidation within single transaction (SRS-122)

See: LLD-02 §6.5 (Port Connection Validators)
"""
