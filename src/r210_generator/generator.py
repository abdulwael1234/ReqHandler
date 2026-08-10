"""Main generator orchestrator.

Implements the generation pipeline:
1. Load database snapshot (inside BEGIN for consistency)
2. Evaluate parent-child exportable trees (always — report needs it too)
3. If R210 mode: validate FK completeness, render R210 files
4. If report mode: build review report
5. Write files deterministically

See: LLD-04 §3 (Generator Orchestrator — SRS-024, SRS-090, SRS-104)
"""
