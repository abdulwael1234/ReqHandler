"""Status transition validation and parent-child consistency checks.

Implements:
- ARTIFACT_TRANSITIONS and ISSUE_TRANSITIONS matrices (SRS-035b)
- check_parent_can_be_approved() — excludes rejected children (SRS-046, SRS-053, SRS-092a)
- auto_demote_parent_chain() — cascading demotion (SRS-035c)
- PARENT_CHILD_MAP and CHILD_PARENT_MAP registries

See: LLD-02 §6.2 (Status Validators), §3.5 (Parent-Child Registry)
"""
