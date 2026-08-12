# Phase 3 — Implemented Requirements

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-IMPL-03                                                 |
| **Phase**            | Phase 3 — Validation layer, 35 MCP tool handlers, server adapter |
| **Date**             | 2026-08-12                                                   |
| **Branch**           | `feature/phase3-tool-handlers`                               |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-02 v1.5 §6–§11                   |
| **Companion**        | `docs/DEVIATIONS_FROM_REQUIREMENTS.md` §4B (DEV-25–DEV-38, closed) |
| **Design**           | `docs/superpowers/specs/2026-08-12-phase3-mcp-tool-surface-design.md` |
| **Plan**             | `docs/superpowers/plans/2026-08-12-phase3-mcp-tool-surface.md` (5 parts) |
| **Predecessor**      | `docs/PHASE2_IMPLEMENTED_REQUIREMENTS.md`                    |
| **Status**           | Complete — 590 tests passing, ruff clean, mypy strict clean  |

---

## 1. Scope of Phase 3

Phase 2 built the only layer permitted to touch the schema. Phase 3 builds
everything between that layer and the MCP protocol.

**Delivered:**

| Module | Purpose |
|--------|---------|
| `errors.py` | `+ McpValidationError` (LLD-02 §6, DEV-25) |
| `db/dal.py` | `+ get_record_by_id`, `get_parent_record`, `get_children`, `query_table`, `insert_record`, `update_record` (DEV-28) |
| `validation/common.py` | UUID, choice, position, non-empty, artifact type, name normalization (§6.1) |
| `validation/status.py` | Transition matrices, parent-approval blocking, demotion chain, reference resolution (§6.2) |
| `validation/type_definitions.py` | Kind values, subtype/kind matching, parent kind (§6.3) |
| `validation/port_interfaces.py` | Interface type, child-type matching, direction vocabularies (§6.4) |
| `validation/port_connections.py` | Connection completeness, SRS-125 fallback (§6.5) |
| `duplicate_detection.py` | Normalized duplicate comparison (§8) |
| `projection.py` | `GEMINI_ALLOWED_FIELDS`, `project_response` (§11) |
| `tools/context.py` | `ToolContext`, `build_context` |
| `tools/_engine.py` | Descriptors, the three engines, the cross-cutting rules (§7, §10) |
| `tools/*.py` | The 35 handlers, grouped as §7.1–7.9 |
| `tools/registry.py` | Dispatch, error boundary, projection boundary, non-MCP helpers (§9) |
| `server.py`, `__main__.py` | The stdio adapter; the only module importing `mcp` |

**Phase scope change.** The eight-phase map assigned parent approval to Phase 4,
connection validation to Phase 5 and duplicate detection to Phase 6. That split
is not implementable in order — LLD-02 §7.7 and §10.1 both call Phase 4
machinery from Phase 3 handlers. Phase 3 absorbs Phases 4–6 (DEV-33, approved
by the project owner). **Phase 7 (generator, LLD-04) and Phase 8 (Local Review
CLI, LLD-06) are the only phases remaining.**

---

## 2. Status Legend

| Marker | Meaning |
|--------|---------|
| **Full** | The requirement is completely satisfied by Phase 3 code. |
| **Partial** | Satisfied for the MCP surface; a named later phase owns the rest. |

---

## 3. Tool Surface Requirements

| SRS | Requirement (abridged) | Status | Implementation | Verified by |
|-----|------------------------|--------|----------------|-------------|
| SRS-083 | All tool inputs validated; invalid input names field and reason | Full | `validation/common.py`; `reject_unknown_arguments`; every descriptor carries validators | `test_common.py` (33), `test_engine.py` |
| SRS-084 | Each write wrapped in a transaction | Full | Every create/update runs in one `transaction()`, reads included | `test_a_failed_insert_leaves_nothing_behind`, `test_a_failed_child_rolls_back_the_parent` |
| SRS-085 | Create/update/query source requirements | Full | `tools/source_requirements.py` | `test_source_requirements.py` (8) |
| SRS-086 | Create/update/query artifacts and children | Full | `tools/{type_definitions,port_interfaces,port_prototypes,port_connections}.py` | `test_type_definitions.py` (14), `test_entity_handlers.py` (32) |
| SRS-087 | Resolve references by UUID | Full | `tools/reference.py` over `resolve_unique_key` | `TestResolveReference` |
| SRS-088 | Create and query review issues | Full | `tools/review_issues.py` | `TestReviewIssues` |
| SRS-089 | Mark artifacts and issues with review states | Full | `set_review_status`; `update_review_issue` for issues | `test_assembly.py` |
| SRS-090 | Request deterministic generation | Partial | `trigger_generation` validates `mode`, reports the generator unavailable (DEV-31) | `TestTriggerGeneration` — *the generator is Phase 7* |
| SRS-091 | Delete excluded from the tool surface | Full | No `DELETE` anywhere; no delete tool registered | `test_no_delete_tool_is_registered` |
| SRS-093 | Destructive operations not exposed | Full | `r210_mcp` never imports `r210_db_init` | `test_the_mcp_package_never_imports_the_initializer` |

---

## 4. Review-State Requirements

| SRS | Requirement (abridged) | Status | Implementation | Verified by |
|-----|------------------------|--------|----------------|-------------|
| SRS-035 | Five review states | Full | `set_review_status` writes any state the matrix permits | `test_assembly.py` |
| SRS-035a | New records start `pending_review`; creates may tag uncertainty | Full | `initial_status` accepts only the three non-terminal states | `test_initial_status_defaults_and_restricts` |
| SRS-035b | Permitted transitions, artifact and issue | Full | `validate_artifact_transition`, `validate_issue_transition` | `TestTransitions` (13 parametrized) |
| SRS-035c | Approved parent demoted when a child changes; one transaction | Full | `auto_demote_parent_chain`, walking the grandparent chain | `test_walks_the_grandparent_chain`, `test_child_leaving_approved_demotes_the_parent` |
| SRS-046, SRS-053 | Parent approval blocked by non-approved children | Full | `check_parent_can_be_approved` | `test_pending_child_blocks_approval` |
| SRS-092a | Rejected children excluded from the evaluation | Full | Same function skips `rejected` | `test_rejected_child_does_not_block` |
| SRS-082a | Extraction authority may not approve | Full | `caller` must equal `adapter_mode`; approval rejected in extraction mode | `test_extraction_cannot_approve_whatever_caller_is_forged` (4 parametrized), `test_extraction_cannot_approve_a_child_either` |
| SRS-082b | Changing approved content demotes it | Full | `demote_if_approved` in the update engine | `test_demotes_an_approved_record`, `test_child_update_demotes_the_parent_chain` |
| SRS-091a | Status only via `set_review_status`; note ignored where absent | Full | `reject_status_argument`; `update_status` drops the note | `test_every_update_tool_rejects_status` (13 parametrized), `test_ignores_a_note_on_a_table_without_the_column` |
| SRS-119 | Issue status through `update_review_issue` | Full | The one update tool that accepts `status` | `test_resolves_an_issue`, `test_reopening_is_permitted` |
| SRS-120 | `kind` immutable after creation | Full | `immutable_args=("kind",)` | `test_rejects_a_kind_change` |

---

## 5. Data-Model Requirements

| SRS | Requirement (abridged) | Status | Implementation | Verified by |
|-----|------------------------|--------|----------------|-------------|
| SRS-027 | Referable records carry a unique `unique_key` | Full | `uuid4()` at create time | `test_inserts_and_returns_a_uuid_key` |
| SRS-034, SRS-121 | Duplicate warning after normalized comparison | Full | `check_for_duplicates` normalizes both sides (DEV-36); warning returned and an `ambiguous` issue created | `test_duplicate_produces_a_warning_and_an_issue`, `test_matches_after_whitespace_normalization` |
| SRS-036, SRS-030 | Missing optional relationship is NULL | Full | Optional refs bind NULL; an absent update argument never clears a column | `test_port_interface_key_may_stay_unresolved`, `test_an_absent_reference_argument_does_not_clear_the_column` |
| SRS-036a | Unresolved reference creates an issue; blocks approval; resolvable later | Full | `create_unresolved_issue`, `sync_unresolved_issues`, `check_references_resolved` (DEV-27) | `test_unresolved_reference_creates_an_issue`, `test_resolving_a_reference_resolves_its_issue`, `test_unresolved_reference_blocks_approval` |
| SRS-037, SRS-108 | Deterministic ordering by position | Full | Inherited from the DAL's `_order_by` | `test_records_are_deterministically_ordered` |
| SRS-038a | Exactly one subtype detail row per parent | Full | `create_type_definition` writes parent, detail and children in one transaction | `test_creates_a_simple_typedef_with_its_detail_row` |
| SRS-038b | `position` and `array_size` are integers ≥ 1 | Full | `validate_position`, `validate_positive_int` | `TestValidatePosition`, `test_rejects_an_array_size_below_one` |
| SRS-038c | Names unique within a struct or enum parent | Full | Schema UNIQUE; the failure surfaces as a structured error at the boundary | `test_a_failed_child_rolls_back_the_parent`, `test_constraint_violation_becomes_a_response` |
| SRS-043 | Four permitted kinds | Full | `validate_kind_value` | `test_rejects_an_unknown_kind` |
| SRS-044 | Subtype and child kind matching | Full | `validate_subtype_matches_kind`, `validate_parent_kind` | `test_struct_element_requires_a_struct_parent`, `test_enum_value_requires_an_enum_parent` |
| SRS-052, SRS-055 | Interface type; children match it | Full | `INTERFACE_TYPES`, `validate_child_interface_type` | `TestChildTypeMatching` |
| SRS-059, SRS-061, SRS-063 | Argument direction, port direction, relationship type | Full | Vocabularies in `validation/port_interfaces.py` | `TestOperationArgument`, `TestPortPrototype`, `TestPortPrototypeFunction` |
| SRS-069, SRS-072 | Member existence; ≥1 provider and ≥1 requester | Full | `validate_connection_complete` | `TestValidateConnectionComplete` |
| SRS-070 | No duplicate prototype per connection | Full | Enforced by a schema UNIQUE constraint; the validator branch is defence in depth (DEV-37) | `test_a_duplicate_prototype_cannot_be_stored` |
| SRS-074 | Typed polymorphic artifact reference | Full | `ARTIFACT_TYPE_FOR_TABLE`; `artifact_type` required alongside `artifact_unique_key` | `test_rejects_an_unknown_artifact_type`, `test_rejects_an_artifact_key_without_a_type` |
| SRS-122 | Member mutation revalidates the connection transactionally | Full | `update_port_connection_member` revalidates inside its own transaction | `test_update_revalidates_the_whole_connection` |
| SRS-125 | Unverifiable compatibility creates an `incomplete` issue | Full | `create_compatibility_review_issue`, run through `CreateSpec.post_create` inside the create transaction so the connection and its issue commit together | `test_creates_and_records_the_compatibility_issue` |

---

## 6. Confidentiality and Error Requirements

| SRS | Requirement (abridged) | Status | Implementation | Verified by |
|-----|------------------------|--------|----------------|-------------|
| SRS-015a | Gemini-facing responses limited to the allowlist | Full | `project_response` applied once at the dispatch boundary (DEV-30), split by clause: (b) query results carry allowlisted fields, (c) mutations return only `unique_key`, warnings and demoted keys (DEV-38) | `test_no_tool_leaks_a_forbidden_field_in_extraction_mode` (35 parametrized), `test_a_create_returns_only_metadata_to_extraction`, `test_projection.py` |
| SRS-109 | Errors report operation, field, reason, affected key | Full | `McpValidationError` carries `McpError`; the boundary also translates `sqlite3.IntegrityError` | `test_validation_error_becomes_a_response`, `test_constraint_violation_becomes_a_response` |
| SRS-113 | No concurrency or performance optimization | Full | One connection per operation; duplicate detection favours correctness over the index (DEV-36) | Design |

---

## 7. Design Properties Worth Recording

**The confidentiality boundary cannot be forgotten.** Projection is applied in
`dispatch`, not in the handlers. A tool added later is covered the moment it is
registered, and `test_no_tool_leaks_a_forbidden_field_in_extraction_mode`
parametrizes over `TOOL_HANDLERS` rather than a hand-written list.

**The cross-cutting rules have one implementation each.** SRS-091a rejection,
SRS-082b demotion and SRS-035c chaining live in `_engine.py`; the 26 CRUD tools
are descriptors. The rule suites parametrize over the registries, so a table or
tool added without the rule fails the suite.

**Constraint translation happens where the context exists.** Phase 2 refused to
convert `sqlite3.IntegrityError` because the DAL cannot name the tool or the
affected key. `registry.dispatch` does both, completing SRS-109.

**Approval has three independent guards.** Authority (`adapter_mode`),
child state (SRS-046/053/092a) and reference resolution (SRS-036a) are checked
separately, and each has its own error naming its own reason.

---

## 8. Verification Summary

```
590 tests passing (297 before Phase 3, 293 added)

  Phase 3 additions:
   68  test_cross_cutting.py                  — rule suites and the two adversarial tests
   37  test_tools/test_engine.py              — descriptors, create/update/query engines
   35  test_tools/test_assembly.py            — set_review_status, registry, server adapter
   32  test_tools/test_entity_handlers.py     — interface, prototype, connection, issue tools
   33  test_validation/test_common.py         — field validators
   25  test_validation/test_status.py         — transitions, blocking, demotion, references
   16  test_validation/test_entity_validators.py — kind, interface type, connection rules
   14  test_tools/test_type_definitions.py    — the irregular create and its children
    8  test_tools/test_source_requirements.py
   10  test_projection.py
    5  test_duplicate_detection.py
    8  test_dal.py (extended)                 — the six added DAL methods
    3  test_errors.py (extended)              — McpValidationError

ruff check src tests   → All checks passed
mypy (strict) src      → Success: no issues found in 63 source files
```

**Testing method:** development-level, by agreement with the project owner.
These tests establish that the layer works and that its boundaries hold; they
are not an exhaustive verification campaign. Independent testing is a separate
activity performed by a dedicated tester after this hand-off.

Two exceptions were written to a higher standard because
`REPOSITORY_REVIEW_REPORT.md` §7 names them explicitly: the projection-leak test
covers all 35 tools under hostile arguments, and the approval-authority test
covers a forged `caller` on both an artifact and a reviewable child.

### Running the tests

```
python -m pytest tests/ -q -p no:cacheprovider
```

The `-p no:cacheprovider` flag is required on this machine, which denies
`.pytest_cache` creation in the repository directory.

---

## 9. What Phase 3 Deliberately Does Not Do

| SRS | Requirement | Owning phase |
|-----|-------------|--------------|
| SRS-071 | Interface-compatibility rules | **TBD** — undefined in the requirements; SRS-125 fallback implemented instead |
| SRS-101–SRS-104a | Deterministic generation and reporting | Phase 7 (LLD-04) |
| SRS-036a (export half) | Unresolved references block *export* | Phase 7 |
| SRS-118, SRS-123 | Review workflow and Local Review CLI | Phase 8 (LLD-06) |
| SRS-015 | External data transfer authorization | **Blocking stakeholder decision, unchanged** |

`R210McpServer.run()` is unverified. The `mcp` SDK is not installed in this
environment, so the stdio transport wiring has never been executed; it is marked
`# pragma: no cover` and must be exercised on a machine with the SDK before the
server is used through the MCP protocol. Every other path is reachable without
the SDK through `handle_tool`, which is what LLD-06 requires.

---

## 10. Hand-off Notes for Testing

Areas most worth independent scrutiny, in the order I would attack them:

1. **`run()` against a real MCP client** — the one unexecuted code path.
2. **`sync_unresolved_issues`** — it resolves *every* pending
   `unresolved_reference` issue on the record, not the one matching the specific
   column. A record with two unresolvable columns is not currently possible, but
   the assumption is worth confirming against the schema.
3. **`resolve_unique_key` collision behaviour** — inherited from Phase 2; keys
   are assumed globally unique but the schema enforces uniqueness per table.
4. **Projection metadata keys** — `warnings`, `demoted`, `table`, `count`,
   `records`, `record` pass through unprojected by design. Confirm none of them
   can carry a record field.
5. **`initial_status` on child creates** — accepted on every create tool; confirm
   that a child created as `out_of_scope` interacts correctly with parent
   approval blocking.
6. **`CreateSpec.post_create`** — the hook that pairs a connection with its
   SRS-125 issue inside one transaction. Confirm the ordering holds if a second
   tool ever adopts it.

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-12 | Initial record of Phase 3 implementation. |
| 1.1     | 2026-08-12 | Tightened SRS-015a(c): a create or update now returns only `unique_key`, warnings and demoted keys to an extraction-mode caller, matching LLD-02 §11.2 (DEV-38). Updated counts to 590. Source document is now LLD-02 v1.5, into which DEV-25 through DEV-38 are incorporated. |
