"""Type definition validators: kind-matching, subtype cardinality.

Validates:
- kind ∈ {simple_typedef, array, struct, enum} (SRS-043)
- Subtype detail matches kind (SRS-044, SRS-038a)
- Kind is immutable on update (SRS-120)

See: LLD-02 §6.3 (Type Definition Validators)
"""
