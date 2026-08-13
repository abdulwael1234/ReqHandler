# Phase 4 — Scope

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-SCOPE-04                                                |
| **Phase**            | Phase 4 — Review CLI, generator core, review report, extraction skill |
| **Date**             | 2026-08-13                                                   |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-03 v1.3, R210-LLD-04 v1.3, R210-LLD-06 v1.2 |
| **Predecessor**      | `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md`                    |
| **Successor**        | `docs/PHASE5_SCOPE.md`                                       |
| **Companion**        | `docs/REMAINING_WORK.md` (§1A carries the authoritative phase map) |
| **Status**           | Scope agreed — design spec and implementation plan not yet written |

---

## 1. Purpose

Phase 4 delivers **everything that is not blocked by work-computer
configuration**. It ends at the first point where the prototype is usable by a
human reviewer end to end on synthetic data.

Phase 5 delivers what remains, and cannot begin until its entry criteria close
— two TBDs (SRS-019(c), SRS-064) plus the work-computer configuration values
they depend on, enumerated in `docs/PHASE5_SCOPE.md` §2. That boundary is
forced, not chosen — see §2 below.

**Numbering.** This is Phase 4 in delivery order. It covers what the retired
eight-phase map called Phases 7 and 8, minus the part deferred to Phase 5, plus
the Gemini skill and the Phase 3 remediation in §3.0. See
`docs/REMAINING_WORK.md` §1A.

---

## 2. Why the Work Splits Here

R210 file rendering (LLD-04 §6) writes against templates defined by
**SRS-019(c)** and needs the **SRS-064** selection rule to decide which AUTOSAR
metamodel element `access_point` maps to. Neither value exists in this
repository copy; `docs/WORK_MACHINE_CONFIGURATION.md` records that they are
deliberately deferred until transfer to the work computer. Building that part
now means inventing templates and rewriting them later.

Nothing else is blocked. The generator's own design anticipates this: LLD-04
§11 states that the TBDs "do not block the design of the generator's
architecture — template implementations are pluggable."

The seam is therefore precise and lands on a package boundary:

| Package | Depends on | Phase |
|---------|-----------|-------|
| `r210_generator/` except `r210/` | Database snapshot only | **4** |
| `r210_generator/r210/` | SRS-019(c) templates, SRS-064 mapping | **5** |

---

## 3. Deliverables

### 3.0 Phase 3 defect fixes — **CLOSED 2026-08-13, before Phase 4 begins**

Independent acceptance testing on 2026-08-13 found three behavioural defects
in the Phase 3 surface, plus one architectural conformance issue found by
inspection. All four are verified against LLD-02 and recorded in
`docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` §11.

| ID | Defect | SRS | Severity |
|----|--------|-----|----------|
| D-01 | Connection creation is neither atomic nor validated: `create_port_connection` takes no `members` array and creates the parent alone, and neither it nor `create_port_connection_member` revalidates completeness — an invalid connection persists | SRS-069, SRS-070, SRS-072, SRS-084, SRS-122 | Critical |
| D-02 | `update_type_definition` rejects `subtype`, so an unresolved **array** element type can never be resolved and its issue never closes | SRS-036a | High |
| D-03 | `artifact_type` / `artifact_unique_key` pairing enforced in one direction only | SRS-074 | Medium |
| D-04 | `get_stats` executes SQL directly in `tools/registry.py` instead of through the DAL | — | Architectural conformance (no test failure) |

**Why these come first.** D-01 and D-02 are both prerequisites for work in this
phase. The review CLI's `show` command displays connections and their members
(LLD-06 §6), and the generator's tree evaluation (LLD-04 §4) walks
`PortConnections` → `PortConnectionMembers` deciding exportability — both
inherit whatever invalid connections D-01 allows into the database. D-02 blocks
approval of any array type, so no array can ever reach the R210 export path.
Building on top of them means building on records the system should have
refused.

D-04 is small and worth doing while the surrounding code is open: it needs a
DAL method for row and status counts, after which `registry.py` holds no SQL.

**Done.** All four were fixed on the Phase 3 branch rather than deferred, so
`master` never carried the critical connection defect. Acceptance is 60 of 60,
the full suite is 652 passing, and the four requirement rows are back to Full.
This section is retained as the record of what was fixed; **Phase 4 starts at
§3.1**.

### 3.1 Local Review CLI (LLD-06, SRS-123)

**Package:** `src/r210_review_cli/` — currently 9 stub modules, ~68 lines.

Twelve commands (LLD-06 §4.1):

| Command | Behaviour |
|---------|-----------|
| `list <entity_type>` | List artifacts or issues by type |
| `show <unique_key>` | Detailed record with children |
| `search <entity_type> --name <pattern>` | Search by name pattern |
| `approve <unique_key> [--note]` | Set status `approved` |
| `reject <unique_key> [--note]` | Set status `rejected` |
| `mark <unique_key> <status> [--note]` | Set any permitted status |
| `resolve <issue_key> --resolution <text>` | Resolve a review issue |
| `dismiss <issue_key>` | Reject a review issue |
| `reopen <issue_key>` | Reopen a resolved or rejected issue |
| `report [--output <path>]` | Generate the review report |
| `generate [--mode] [--output <dir>]` | Trigger R210 generation |
| `stats` | Database statistics |

Six entity types with aliases (LLD-06 §4.2): `sources`/`src`, `types`/`td`,
`interfaces`/`pi`, `prototypes`/`pp`, `connections`/`pc`, `issues`/`ri`.

Plus the tool-invocation bridge (§5), display formatting (§6), and the network
isolation guarantee (§7): this component must never import anything that
reaches the Gemini API.

**Ready to build.** Phase 3 produced the seam deliberately. Handlers are plain
functions over a `ToolContext` (DEV-26), and `tools/registry.py` already
exposes `dispatch`, `query_by_table`, `get_children_for_display` and
`get_stats` without importing the MCP SDK. The CLI constructs its context with
`adapter_mode="review"`, which is what permits approval (SRS-082a) and returns
full records rather than projected ones.

### 3.2 Generator core, excluding R210 rendering (LLD-04)

**Package:** `src/r210_generator/` — currently 14 stub modules, ~110 lines.
Everything except the `r210/` subpackage.

| LLD-04 § | Module | Responsibility | SRS |
|----------|--------|----------------|-----|
| §3 | `generator.py` | Orchestrator; `report_only` mode operative, `r210_only`/`both` deferred to Phase 5 | SRS-090, SRS-104 |
| §4 | `validator.py` | Exportable-tree evaluation; rejected children excluded | SRS-104a, SRS-092a |
| §5 | `validator.py` | Foreign-key validation; invalid records reported and excluded | SRS-102 |
| §7 | `report/builder.py`, `report/sections.py` | Review report, eight sections (a)–(h) | SRS-104 |
| §8 | `r210/file_writer.py` | UTF-8, LF, byte-identical output | SRS-101 |
| §9 | `loader.py` | Database snapshot loading | SRS-101 |
| §10 | `models.py` | `GenerationResult` | SRS-090 |

The report has a fixed section order (LLD-04 §7.1): (a) approved & generated,
(b) approved but excluded, (c) pending review, (d) ambiguous, (e) rejected,
(f) out of scope, (g) pending issues grouped by `issue_type`, (h) decision log.

**Why the report is not blocked.** SRS-104 requires the report to be producible
independently of R210 generation, and to be generated "even when no approved
artifacts exist". Its input is the complete database snapshot, not the work
templates. LLD-04 §3.2 confirms `report_only` has no precondition.

`file_writer.py` lives under `r210/` by module path but implements §8's
general file-output rules, which both outputs share. It belongs to Phase 4.

### 3.3 `trigger_generation` delegation (SRS-090)

The tool currently validates `mode` and returns a structured "not yet
implemented" error (DEV-31). Phase 4 wires `report_only` to the generator.
`r210_only` and `both` continue to report unavailability until Phase 5.

### 3.4 Gemini CLI Skill (LLD-03)

**File:** `src/gemini_skill/r210_extraction.md` — currently 54 lines,
self-declared a stub. LLD-03 specifies roughly ten times that content: seven
behavioural rules (§4.0–4.7), the classification decision tree (§5), nine
extraction procedures (§6), issue recording (§7), dependency-ordered
processing (§8), error handling (§9), the tool quick reference (§10), and the
explicit data-boundary statement (§11).

**Must be written against the implemented surface, not the LLD's sketch.** Two
Phase 3 outcomes change what the skill can rely on:

- `set_review_status` treats `table_hint` as optional (DEV-35).
- An extraction-mode create or update returns **only** `unique_key`, warnings
  and demoted keys — no record fields (DEV-38). A skill written to read `name`
  or `status` back from a create response will not work.

The skill can be written and reviewed now. It cannot be *exercised against real
requirement text* until SRS-015 is approved (§6.1).

### 3.5 Verify `R210McpServer.run()`

The stdio transport has never been executed; the `mcp` SDK is not installed in
this environment. Install it, run `python -m r210_mcp <db> --mode extraction`,
and confirm a client can list and call tools. Correct `run()` if the SDK API
differs from the current sketch — no test depends on its internals, and it
carries `# pragma: no cover` today.

This closes the last untested path in an otherwise complete component.

---

## 4. Requirements Covered

| SRS | Requirement (abridged) | Deliverable |
|-----|------------------------|-------------|
| SRS-090 | Operation to request generation | §3.3 (`report_only`) |
| SRS-101 | Byte-identical output — **Partial**: this phase can satisfy determinism for the *review report* only. R210-output determinism is verified in Phase 5, so SRS-101 stays Partial until then | §3.2 |
| SRS-102 | Validate approved records; exclude FK-invalid ones | §3.2 |
| SRS-104 | Review report, producible independently, eight sections | §3.2 |
| SRS-104a | Parent exported only when all non-rejected children approved | §3.2 |
| SRS-092a | Rejected children excluded from evaluation | §3.2 |
| SRS-108 | Deterministic child ordering | §3.2 |
| SRS-118 | Manual review through the MCP tool surface | §3.1 |
| SRS-123 | Local review CLI, no Gemini API connection | §3.1 |
| SRS-003, SRS-077–SRS-082a, SRS-015a | Extraction behavioural rules | §3.4 |
| SRS-036a (export half) | Unresolved references block export | §3.2 |

SRS-103 (R210 file generation) is **not** covered — it is Phase 5.

---

## 5. Known Gaps to Resolve During the Phase

These are specification or code gaps found while scoping. Each needs a decision
early, not mid-implementation.

**5.1 `search --name <pattern>` has no DAL support.** LLD-06 §4.2 specifies
pattern search, but the DAL only does exact equality — `_where` builds
`"name" = ?`. Either add a pattern-matching method to the DAL following its
existing identifier-allowlist conventions, or filter client-side over
`query_by_table`. The DAL addition is cleaner and matches how Phase 3 handled
`find_duplicates_by_name`; client-side filtering avoids touching a completed
layer. Decide before writing `commands/query.py`.

**5.2 The `cli.py` stub docstring lists nine commands; LLD-06 §4.1 lists
twelve.** The stub omits `dismiss`, `reopen`, and the separate `report`
command, and it is the older list. LLD-06 is normative; the docstring is stale
and should be corrected rather than treated as the specification.

**5.3 `file_writer.py` sits under `r210/` but is shared.** LLD-04 §8's rules
serve both outputs. Phase 4 implements it where it is rather than moving it, so
Phase 5 inherits it unchanged; a move would churn a module Phase 5 depends on.

**5.4 Report determinism needs a fixed clock.** SRS-101 requires byte-identical
output for the same database content. If the report embeds a generation
timestamp, two runs over an unchanged database differ. Either exclude the
timestamp from the deterministic comparison or inject it, and say which in the
design spec.

---

## 6. Explicitly Not in Phase 4

| Item | Reason | Owner |
|------|--------|-------|
| R210 file rendering, four templates, AUTOSAR mapping | SRS-019(c) and SRS-064 unresolved | Phase 5 |
| `r210_only` and `both` generation modes | Depend on the above | Phase 5 |
| Real-data extraction | SRS-015 unapproved — synthetic data only | Stakeholder |
| SRS-071 interface compatibility validation | TBD; SRS-125 fallback stays in place | Work computer |
| Work-specific configuration | Deliberately absent from this copy | Work computer |

---

## 7. Definition of Done

1. All deliverables in §3.1–§3.5 implemented (§3.0 is already closed).
2. `python -m pytest tests/ -q -p no:cacheprovider` passes.
3. `ruff check src tests` and `mypy src` (strict) clean.
4. `r210-review` runs end to end against a synthetic database: create records
   through the MCP tools, list and show them, approve one, resolve an issue,
   and produce a review report.
5. Report generation is verified byte-identical across two runs over an
   unchanged database (SRS-101), with §5.4 decided.
6. `R210McpServer.run()` executed against a real MCP client at least once.
7. `docs/PHASE4_IMPLEMENTED_REQUIREMENTS.md` written, and any new deviations
   recorded in `docs/DEVIATIONS_FROM_REQUIREMENTS.md` continuing from DEV-38.
8. `docs/REMAINING_WORK.md` updated to reflect what is left.

**Testing standard:** development-level, as agreed for Phases 2 and 3 —
establishing that each layer works and its boundaries hold, with independent
testing as a separate activity. Two exceptions carry forward from the Phase 3
precedent and should be written adversarially: the CLI's network isolation
(SRS-123) and the report's determinism (SRS-101).

---

## 8. Suggested Order

1. ~~Phase 3 defect fixes (§3.0)~~ — done 2026-08-13, before this phase starts.
2. **Review CLI** — unblocked, and it makes everything downstream inspectable
   by a human instead of by tool calls.
3. **Loader and validator** — the generator's database-facing half; the tree
   evaluation is shared with Phase 5.
4. **Review report and file writer** — completes `report_only`.
5. **`trigger_generation` delegation** — small, once the generator exists.
6. **Verify `run()`** — independent of the rest; can happen at any point on a
   machine with the SDK.
7. **Gemini skill** — last, so it documents a surface that is finished and
   demonstrated rather than one still moving.

---

## 9. Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Report determinism is harder than expected (timestamps, dict ordering, locale) | SRS-101 is a hard requirement | Decide §5.4 in the design spec; assert byte-identity in tests from the first commit |
| The CLI's display formatting invites scope creep | Phase inflates | LLD-06 §6.2 fixes the output formats; treat them as the specification |
| The Gemini skill drifts from the implemented tool surface | Skill fails at runtime, long after writing | Write it last (§8); cross-check §10 and §11 against `TOOL_HANDLERS` and DEV-38 |
| `search` pattern matching reopens the completed DAL | Phase 2 regression risk | Decide §5.1 before implementation; prefer the smallest change that keeps the identifier allowlist intact |

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-13 | Initial scope, agreed after the Phase 3 hand-off. |
| 1.1     | 2026-08-13 | Review fixes: clarified the delivery-order numbering against the retired eight-phase map; marked SRS-101 Partial for this phase, since R210-output determinism belongs to Phase 5; widened D-01 to cover both creation paths; reclassified D-04 as an architectural conformance issue rather than a defect; stated the Phase 5 entry criteria as more than two TBDs. |
| 1.2     | 2026-08-13 | §3.0 closed: D-01–D-04 fixed on the Phase 3 branch before merge. |
