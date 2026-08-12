# Phase 3 — MCP Tool Surface (Design)

| Field | Value |
|---|---|
| **Document ID** | R210-SPEC-P3 |
| **Phase** | Phase 3 — Validation layer, 35 tool handlers, MCP server adapter |
| **Date** | 2026-08-12 |
| **Branch** | `feature/phase3-tool-handlers` |
| **Source Documents** | R210-LLD-02 v1.4 §6–§11, R210-SRS-001 v5.4 |
| **Predecessor** | Phase 2 — Data Access Layer (`docs/superpowers/specs/2026-08-12-phase2-data-access-layer-design.md`) |

---

## 1. Scope

Phase 3 builds everything between the Phase 2 DAL and the MCP protocol: input
validation, the business rules, all 35 tool handlers, and the server entry
point.

**Scope decision.** The repository's eight-phase map splits this work across
Phases 3–6. That split is not implementable as written: LLD-02 §7.7 has
`set_review_status` call `check_parent_can_be_approved` (Phase 4) and
`auto_demote_parent_chain` (Phase 4); §10.1 has the Phase 3 content-demotion
rule call that same Phase 4 chain; §7.2 has `create_type_definition` call
duplicate detection (Phase 6). Rather than ship handlers that violate their own
requirements and repair them later, **Phase 3 absorbs Phases 4, 5 and 6**.
Phase 7 (generator) and Phase 8 (review CLI) are unchanged. Approved by the
project owner on 2026-08-12; recorded as DEV-33.

| File | Contents | LLD |
|---|---|---|
| `errors.py` | `+ McpValidationError` | §3.1 |
| `db/dal.py` | `+ get_record_by_id`, `get_parent_record`, `get_children`, `query_table` | §5 |
| `validation/common.py` | UUID, status, position, non-empty, name normalization, artifact type | §6.1 |
| `validation/status.py` | Transition matrices, parent-approval check, parent-chain demotion | §6.2 |
| `validation/type_definitions.py` | Kind values, subtype/kind matching, kind immutability, parent kind | §6.3 |
| `validation/port_interfaces.py` | Interface type, child-type matching, direction | §6.4 |
| `validation/port_connections.py` | Member existence, duplicates, direction cardinality, SRS-125 fallback | §6.5 |
| `duplicate_detection.py` | Normalized comparison and warning construction | §8 |
| `projection.py` | `GEMINI_PROJECTION` allowlist and `project()` | §11 |
| `tools/_engine.py` | Descriptors, create/update/query engines, shared rules | §7, §10 |
| `tools/*.py` | The 35 handlers, grouped as §7.1–7.9 | §7 |
| `tools/registry.py` | Name→handler dispatch, error boundary, projection boundary, non-MCP helpers | §9 |
| `server.py` | MCP stdio adapter | §9 |

**Not in Phase 3:** the deterministic generator (LLD-04, Phase 7) and the Local
Review CLI (LLD-06, Phase 8).

## 2. Handlers are functions over a context

LLD-02 §9 makes every handler a bound method of `R210McpServer`. Phase 3 makes
them module-level functions instead:

```python
@dataclass(frozen=True)
class ToolContext:
    db: DatabaseConnection
    dal: DataAccessLayer
    adapter_mode: str          # "extraction" | "review"

def handle_create_type_definition(ctx: ToolContext, arguments: dict) -> dict: ...
```

Two requirements force this. LLD-06 §1 requires the Local Review CLI to invoke
handlers "directly" without the MCP protocol; and the `mcp` SDK is not
installed in the development environment, so a design that makes handler tests
depend on importing `mcp` cannot be verified here. With a context parameter a
test builds `ToolContext(DatabaseConnection(path), DataAccessLayer(), "review")`
in one line. `server.py` becomes the only module that imports `mcp`.

Recorded as DEV-26.

## 3. The engine and the descriptors

The 13 creates, 13 updates and 6 queries are one algorithm each, parameterized
by table. `tools/_engine.py` holds that algorithm once; each tool contributes a
frozen descriptor naming its table, its arguments, its validators, its key
references, and its parent relation. The four irregular tools —
`create_type_definition`, `set_review_status`, `update_port_connection_member`,
`resolve_reference` — are written out explicitly.

This is the same shape Phase 2 chose and recorded as DEV-18: a generic core
behind a named, explicitly-typed surface. The alternative — 35 hand-written
handlers — would re-implement the SRS-082b demotion rule twelve times, and one
omission is a silent requirement violation rather than a test failure. Recorded
as DEV-32.

### 3.1 Create algorithm (LLD-02 §7, §10.4)

```
1. Validate required arguments present and non-empty (SRS-083).
2. Validate field values: position ≥ 1, array_size ≥ 1, enum/direction/
   relationship_type membership, initial_status ∈ {pending_review, ambiguous,
   out_of_scope} (SRS-035a, SRS-038b, SRS-059, SRS-061, SRS-063).
3. Generate unique_key = str(uuid4()) (SRS-027).
4. Read-only pass: resolve every *_key argument to an internal id.
   A required key that resolves to nothing is an error; one of the four
   SRS-036a columns may resolve to NULL and stay unresolved.
5. Read-only pass: duplicate detection on (name, kind) where the table has a
   name column (SRS-034, SRS-121).
6. Within one transaction:
   a. Insert the row(s).
   b. For each unresolved SRS-036a reference, insert an
      `unresolved_reference` ReviewIssue.
   c. If a duplicate was found, insert an `ambiguous` ReviewIssue (SRS-121).
   d. For a child table, demote an approved parent and walk the chain
      (SRS-035c, LLD-02 §10.4).
7. Return McpResult(unique_key, data, warnings).
```

SRS-034 and SRS-121 both say the system *may* warn and *may* create the issue,
and LLD-02 §7.2 step 10 says "if duplicate detected and configured" without
defining any configuration. Phase 3 resolves this to **always**: a duplicate
always produces both the response warning and the `ambiguous` ReviewIssue.
Inventing a configuration surface the requirements never specify would be a
larger deviation than choosing the safe branch of a permission.

### 3.2 Update algorithm (LLD-02 §10.2)

```
1. Validate unique_key format (SRS-083).
2. Reject `status` if present (SRS-091a).
3. Reject immutable fields if present — `kind` on TypeDefinitions (SRS-120).
4. Within one transaction:
   a. Resolve unique_key → (table, record). Unknown key is an error.
   b. Re-run the create-side field validations for supplied fields.
   c. Apply the update.
   d. If the record was `approved` and any non-status field changed, demote it
      to `pending_review` and walk the parent chain (SRS-082b, SRS-035c).
   e. Resolve or reopen the associated `unresolved_reference` issue when an
      SRS-036a column changes (LLD-02 §7.2).
5. Return the updated record plus any demoted keys.
```

An update to a structural subtype row (`SimpleTypeDefinitions`,
`ArrayTypeDefinitions`) has no status of its own, so it demotes its parent
`TypeDefinitions` record instead (LLD-02 §10.1).

### 3.3 Query algorithm

Validate filter values, open a read-only connection, delegate to the DAL, return
records in the DAL's deterministic order (SRS-108). Projection is not applied
here — see §6.

## 4. Cross-cutting rules, one home each

| Rule | SRS | Home |
|---|---|---|
| `status` rejected by update tools | 091a | `_engine.reject_status_argument` |
| Content-change demotion | 082b | `_engine.demote_if_approved` |
| Parent demotion on child create | 035c | `validation.status.auto_demote_parent_chain` |
| Transition legality | 035b | `validation.status.validate_artifact_transition` / `validate_issue_transition` |
| Extraction may not approve | 082a | `tools/review_status.py`, from `ctx.adapter_mode` |
| Parent approval blocking, rejected children excluded | 046, 053, 092a | `validation.status.check_parent_can_be_approved` |
| Unresolved reference blocks approval | 036a | `validation.status.check_references_resolved` |
| Duplicate warning and issue | 034, 121 | `duplicate_detection.check_for_duplicates` |
| Unresolved reference creates an issue | 036a | `_engine` reference-resolution step |
| Connection revalidation | 069, 070, 072, 122 | `validation.port_connections.validate_connection_complete` |
| Compatibility unverifiable → issue | 125 | `validation.port_connections.create_compatibility_review_issue` |
| Response projection | 015a | `tools/registry.py` dispatch boundary |

`check_references_resolved` implements the half of SRS-036a that the LLD never
placed: "a record with an unresolved type reference shall not be approved or
exported." Blocking approval belongs to `set_review_status`; blocking export is
Phase 7's. Recorded as DEV-27.

## 5. `set_review_status` (LLD-02 §7.7)

The only tool that writes status directly, and the only one that consults
`adapter_mode` for authority.

```
1. Reject caller ≠ ctx.adapter_mode (parameter forgery, SRS-082a).
2. Resolve unique_key → (table, record).
3. Reject ReviewIssues (use update_review_issue, SRS-119).
4. Reject SimpleTypeDefinitions / ArrayTypeDefinitions (no status, SRS-091a).
5. Validate transition current → new_status (SRS-035b).
6. If new_status == "approved":
   a. Reject when adapter_mode == "extraction" (SRS-082a).
   b. Reject when a non-rejected child is not approved (SRS-046, 053, 092a).
   c. Reject when an SRS-036a reference is still NULL.
7. Within one transaction: write status, write review_note where the column
   exists, and for a child moving away from `approved`, demote the parent
   chain (SRS-035c).
8. Return the new status plus demoted parent keys.
```

`review_note` on a table without that column is silently ignored, not an error —
SRS-091a says so explicitly, and the DAL already implements it.

## 6. Projection at the boundary (SRS-015a, LLD-02 §11)

`GEMINI_PROJECTION` maps each table to its permitted response fields:
`unique_key`, `name`, `kind`, `interface_type`, `status`, `direction`,
`source_reference`, `issue_type`. Everything else — `source_text`,
`description`, `review_note`, `resolution`, `component_reference`,
`function_name` — is withheld.

The projection is applied **once, in `tools/registry.py`, to every handler's
return value when `adapter_mode == "extraction"`**, rather than inside each
query handler as §11.2 sketches. A handler cannot forget a step it does not
perform, and the guarantee becomes one adversarial test over all 35 tools
instead of six hopeful ones. Recorded as DEV-30.

## 7. Error handling

`McpValidationError` is a new exception carrying an `McpError` payload. LLD-02
§6 raises it throughout; Phase 2 built only the `McpError` dataclass, which is
frozen and not an exception. Recorded as DEV-25.

`tools/registry.py` is the single boundary that converts exceptions to
responses:

| Exception | Response |
|---|---|
| `McpValidationError` | `error.to_dict()` |
| `sqlite3.IntegrityError` | `McpError(operation=tool, reason=<constraint>, affected_key=<arguments unique_key>)` |
| `ValueError` from the DAL | Programming error — allowed to propagate |

This is the caller Phase 2 deferred to: the DAL refuses to translate
constraint violations because only this layer knows the tool name and the
affected key that SRS-109 requires. Rollback is already automatic —
`DatabaseConnection.transaction()` rolls back and re-raises.

## 8. DAL additions

The LLD calls four methods Phase 2 did not build. They are added to `dal.py`
following its existing conventions — identifier allowlist, bound values,
record dataclass returns:

| Method | Called by |
|---|---|
| `get_record_by_id(conn, table, record_id)` | §10.1, §10.4 |
| `get_parent_record(conn, child_table, child_id)` | §6.2 `auto_demote_parent_chain` |
| `get_children(conn, child_table, fk_column, parent_id)` | §9 `get_children_for_display` |
| `query_table(conn, table, filters)` | §9 `query_by_table` |

The LLD's pseudocode subscripts records as dicts (`parent["status"]`); Phase 2
returns frozen dataclasses (DEV-17), so Phase 3 uses attribute access
throughout. Recorded as DEV-28 and DEV-29.

## 9. `trigger_generation`

The generator is Phase 7. The tool is registered and validates `mode` against
`{"r210_only", "report_only", "both"}`, then returns a structured `McpError`
stating that generation is unavailable until LLD-04 is implemented. The
contract is real; only the delegation is missing. Recorded as DEV-31.

## 10. Testing

Development-level throughout, as Phase 2 established and the project owner
confirmed for this phase. Independent verification is a separate activity.

Tests live in `tests/test_r210_mcp/test_tools/` mirroring the source modules,
plus `test_validation/` for the validation layer. The leverage is
parametrization over the registries rather than per-tool repetition:

| Test | Parametrized over | Proves |
|---|---|---|
| `test_update_tools_reject_status` | 13 update tools | SRS-091a |
| `test_update_demotes_approved_record` | 12 status-bearing tables | SRS-082b |
| `test_child_creation_demotes_approved_parent` | 7 child creates | SRS-035c |
| `test_transition_matrix` | `ARTIFACT_TRANSITIONS` entries | SRS-035b |
| `test_approval_blocked_by_child` | 5 parent tables | SRS-046, 053 |
| `test_rejected_child_does_not_block` | 5 parent tables | SRS-092a |

Two adversarial tests are written regardless of the development-level standard,
because `REPOSITORY_REVIEW_REPORT.md` §7 names them:

1. **Extraction cannot approve.** An `extraction` context attempting
   `set_review_status(new_status="approved")` is rejected for every reviewable
   table, including when `caller="review"` is forged in the arguments.
2. **Projection never leaks.** Every one of the 35 tools invoked under an
   `extraction` context, asserting no response key falls outside
   `GEMINI_PROJECTION` — driven off the tool registry, so a tool added later
   without a projection entry fails the test.

Tests run against a real migrated database through the existing
`initialized_db` fixture.

## 11. Deliverables

1. The source files in §1.
2. Development tests per §10.
3. `ruff check src tests`, `mypy src` (strict), and `pytest` all clean.
4. `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md`.
5. A Phase 3 section in `docs/DEVIATIONS_FROM_REQUIREMENTS.md` covering
   DEV-25 through DEV-33.

## 12. Deviations this design commits to

| ID | Type | Summary |
|---|---|---|
| DEV-25 | Gap-fill | `McpValidationError` defined; LLD raises it but never defines it |
| DEV-26 | Refinement | Handlers are functions over `ToolContext`, not bound methods |
| DEV-27 | Gap-fill | SRS-036a's approval block implemented as `check_references_resolved` |
| DEV-28 | Addition | Four DAL methods the LLD calls but Phase 2 did not build |
| DEV-29 | Correction | Records are dataclasses, not dict-subscriptable rows |
| DEV-30 | Refinement | Projection applied once at the dispatch boundary |
| DEV-31 | Boundary | `trigger_generation` registered but reports generation unavailable |
| DEV-32 | Refinement | Descriptor-driven engine behind the named handler surface |
| DEV-33 | Correction | Phase 3 absorbs Phases 4–6; the documented split is not implementable |

## Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-12 | Initial Phase 3 design, approved before implementation. |
