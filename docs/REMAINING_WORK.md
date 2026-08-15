# Remaining Work

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-REM-01                                                  |
| **Date**             | 2026-08-13                                                   |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-03 v1.3, R210-LLD-04 v1.3, R210-LLD-06 v1.2 |
| **Companions**       | `docs/PHASE1_IMPLEMENTED_REQUIREMENTS.md`, `docs/PHASE2_IMPLEMENTED_REQUIREMENTS.md`, `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` |
| **Status**           | Living document — updated as each remaining item closes       |
| **Last update**      | 2026-08-15 — Phase 4 complete; Phase 5 framework delivered (DEV-39) |
| **Superseded by**    | `docs/PHASE4_SCOPE.md`, `docs/PHASE5_SCOPE.md` for phase-level planning |
| **Phase numbering**  | See §1A — authoritative; the original eight-phase map is retired |

---

## 1. Purpose

This document lists everything the prototype still needs, so that remaining
scope is visible in one place rather than inferred from three phase records and
a deviation register.

It covers four kinds of remaining work, which need different things from
different people:

| Kind | Meaning | Who unblocks it |
|------|---------|-----------------|
| **Component** | A designed component whose code is still a stub. | Development |
| **Verification** | Code that exists but has never been executed or independently tested. | Development / test |
| **Decision** | A stakeholder or specification question with no answer yet. | Stakeholder |
| **Configuration** | Work-specific values deliberately absent from this repository copy. | Work-computer setup |

---

## 1A. Phase Numbering — Authoritative Map

The repository has carried two phase maps, and the Phase 3 scope change
(DEV-33) invalidated the second one. **This table is the authoritative map.**
The original eight-phase map is retired; references to "Phase 6/7/8" in
documents written before 2026-08-13 mean the rows below.

| Original eight-phase map | Delivered as | Record |
|--------------------------|--------------|--------|
| 1 — Database foundation | **Phase 1** | `PHASE1_IMPLEMENTED_REQUIREMENTS.md` |
| 2 — Data access layer | **Phase 2** | `PHASE2_IMPLEMENTED_REQUIREMENTS.md` |
| 3 — Tool handlers, status enforcement | **Phase 3** | `PHASE3_IMPLEMENTED_REQUIREMENTS.md` |
| 4 — Parent approval and demotion | **Phase 3** (absorbed, DEV-33) | ” |
| 5 — Connection validation | **Phase 3** (absorbed, DEV-33) | ” |
| 6 — Duplicate detection | **Phase 3** (absorbed, DEV-33) | ” |
| 7 — Deterministic generator | **split** — core and review report to **Phase 4**; R210 rendering to **Phase 5** | `PHASE4_SCOPE.md`, `PHASE5_SCOPE.md` |
| 8 — Local review CLI | **Phase 4** | `PHASE4_SCOPE.md` |
| *(not in the original map)* Gemini CLI Skill, LLD-03 | **Phase 4** | `PHASE4_SCOPE.md` |
| *(new)* Phase 3 remediation, D-01–D-04 | **closed 2026-08-13** on the Phase 3 branch | `PHASE3_IMPLEMENTED_REQUIREMENTS.md` §11 |

Phase numbers now follow delivery order and nothing else. A phase that changes
scope is recorded as a deviation, as DEV-33 was, rather than renumbered.

---

## 2. Current State

Five of six components are complete and the sixth is complete apart from its
work-specific template content. Nothing below is docstring-only scaffolding any
more; §3 records what each component now contains and what is still owed.

| Component | LLD | State |
|-----------|-----|-------|
| Database Schema | LLD-01 | **Complete** (Phase 1) |
| Database Initializer | LLD-05 | **Complete** (Phase 1) |
| MCP Server | LLD-02 | **Complete** (Phases 2–3) — acceptance defects D-01–D-04 fixed 2026-08-13; `run()` corrected and verified 2026-08-15, see §4.1 |
| Gemini CLI Skill | LLD-03 | **Complete** (Phase 4) — see §3.1 |
| Deterministic Generator | LLD-04 | **Complete except R210 template bodies** (Phase 4 + Phase 5 framework) — see §3.2 |
| Local Review CLI | LLD-06 | **Complete** (Phase 4) — see §3.3 |

**Current result (2026-08-15):** 865 tests passing, including the 60-case
independent acceptance suite. `ruff check src tests` and `mypy src` (strict)
are clean.

**Three of six components were stubs on 2026-08-13. None is now.** What remains
is four R210 template bodies and one mapping table, all work-computer values —
see `docs/PHASE5_IMPLEMENTED_REQUIREMENTS.md` §4.

---

## 3. Component Status

Phase 4 and the Phase 5 framework closed §3.1–§3.3 as they stood on 2026-08-13.
This section now records what each component contains and what is still owed.
Full records: `docs/PHASE4_IMPLEMENTED_REQUIREMENTS.md`,
`docs/PHASE5_IMPLEMENTED_REQUIREMENTS.md`.

### 3.1 Gemini CLI Skill (LLD-03) — **complete**

**File:** `src/gemini_skill/r210_extraction.md` — was 54 stub lines, now the
full LLD-03 §4–§11 content: the synthetic-mode gate, seven behavioural rules,
the classification decision tree, nine extraction procedures, issue recording,
dependency-ordered processing, error handling, the 35-tool quick reference and
the data-boundary statement.

Written against `TOOL_HANDLERS`, not LLD-03's sketch. §12 of the skill records
four places the two differ; three are LLD-03 naming arguments the tools reject
(`create_port_interface(children=…)`, `create_port_prototype(functions=…)`, a
required `table_hint`). `tests/test_gemini_skill/` cross-checks the prose
against the registry and the SRS-015a allowlist so it cannot drift silently.

**Still true:** SRS-015 is unapproved, so the skill cannot be exercised against
real requirement text (§5.1). It is written and reviewable; it is not cleared to
run on real data.

### 3.2 Deterministic Generator (LLD-04) — **complete except template bodies**

**Files:** `src/r210_generator/` — was 14 stubs, now implemented.

| LLD-04 § | Module | Status |
|---|---|---|
| §3 | `generator.py` | **Done** — all three modes run the pipeline |
| §4 | `validator.py` | **Done** — including §4.3's recursive client-server case |
| §5 | `validator.py` | **Done** — §5.1's six mandatory references |
| §6.1–6.5 | `r210/renderer.py`, `r210/templates/__init__.py` | **Done** — dispatch, ordering, exclusion, plug-point contract |
| §6.6–6.7 | `r210/templates/*.py` | **Open** — template bodies and AUTOSAR mapping; SRS-019(c), SRS-064 |
| §7 | `report/builder.py`, `report/sections.py` | **Done** — nine sections in fixed order |
| §8 | `r210/file_writer.py` | **Done** — UTF-8/LF, byte-identical |
| §9 | `loader.py` | **Done** — via `read_snapshot()` and the DAL (DEV-45) |
| §10 | `models.py` | **Done** |

**`trigger_generation` now delegates.** `report_only` is fully operative;
`r210_only` and `both` run the pipeline and report their unmet Phase 5 entry
criteria by SRS number. DEV-31 is amended, not closed — it closes when the
templates are installed.

**Export half of SRS-036a is done:** `validate_fk_completeness` excludes and
reports any artifact whose mandatory references are unresolved.

**Remaining work is one module.** See
`docs/PHASE5_IMPLEMENTED_REQUIREMENTS.md` §4.1 for the exact signatures.

### 3.3 Local Review CLI (LLD-06) — **complete**

**Files:** `src/r210_review_cli/` — was 9 stubs, now all twelve LLD-06 §4.1
commands, the tool bridge, display formatting and the network-isolation
guarantee. `r210-review` runs end to end; the walkthrough is recorded in
`docs/PHASE4_IMPLEMENTED_REQUIREMENTS.md` §4.

The bridge targets `tools/registry` rather than `R210McpServer` as LLD-06 §5.1
shows, because that module imports the `mcp` SDK and would break §7's own
isolation requirement (DEV-40). Isolation is asserted by an AST scan and a
subprocess import check rather than by the code review §7 asks for.

---

## 3A. Open Work Introduced by Phase 4

Small, and none of it blocking.

| Item | Detail | Raised by |
|---|---|---|
| Per-tool JSON Schema on the MCP surface | Tools are advertised with `{"type": "object", "additionalProperties": true}`. The `CreateSpec`/`UpdateSpec`/`QuerySpec` descriptors already hold the argument names and could generate real schemas, which would make the surface self-describing to an LLM client | DEV-50 |
| `mcp` floor raised to 2.0 | Only 2.x is verified. If 1.x support is wanted, `build_server()` needs a compatibility branch | DEV-50 |
| Phase 2 deviations still unreviewed | DEV-17–DEV-24 have never been through review | pre-existing |

---

## 4. Verification Still Owed

### 4.1 `R210McpServer.run()` — **closed 2026-08-15**

The `mcp` SDK installed successfully (version 2.0.0), so the stdio transport was
run for the first time — and **it did not work**. LLD-02 §9's
`server.call_tool(name)(handler)` registration does not exist in `mcp` 2.x.

`run()` was rewritten against the lowlevel `Server`'s `on_list_tools` /
`on_call_tool` interface (DEV-50), and verified against a real `ClientSession`
over stdio: 35 tools listed, create and query round-tripped, SRS-015a projection
confirmed on the wire, SRS-082a approval denied, unknown tool returned a
structured error. `tests/test_r210_mcp/test_server_adapter.py` locks the wiring
in and skips when the SDK is absent, so the suite still runs without it.

This was the last unverified path in the codebase.

### 4.2 Independent testing of Phases 2 and 3

Both phases were developed to a **development-level** standard by agreement:
the tests establish that each layer works and that its boundaries hold, not
that it is exhaustively verified. Independent testing is a separate activity.

Ranked starting points are recorded in
`docs/PHASE2_IMPLEMENTED_REQUIREMENTS.md` §9 and
`docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` §10.

### 4.3 Phase 3 acceptance defects — closed

Independent acceptance testing on 2026-08-13 found three behavioural defects
and one architectural conformance issue, all verified against LLD-02. **All
four were fixed the same day**, on the Phase 3 branch and before it merged, so
`master` never carried the critical connection defect. Recorded in
`docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` §11.

### 4.4 Phase 2 deviations are still unreviewed

DEV-17 through DEV-24 remain marked "Phase 2 — pending review". DEV-24 is
already known to be wrong: DEV-36 supersedes it, because the split it describes
between an indexed DAL query and caller-side normalization cannot work. The
other seven deserve the same scrutiny.

Phase 1 (DEV-01–16) is approved. Phase 3 (DEV-25–38) is closed against
LLD-02 v1.5.

---

## 5. Decisions and TBDs Not Yet Resolved

### 5.1 SRS-015 — external data transfer *(BLOCKING)*

The source document prohibits external transfer absolutely; using Gemini
requires sending data to Google. The SRS cannot resolve this itself. Until a
stakeholder approves it, **the system operates on synthetic data only**, and
no real requirement text may reach the Gemini API.

This blocks real-data operation of the whole extraction workflow. It does not
block building any remaining component.

### 5.2 SRS-019 — work-specific deferrals

Deferred until the repository is on the work computer: (a) supported input
formats, (b) source identifiers and their mapping to `source_reference`,
(c) exact R210 output templates and format, (d) file and artifact naming
conventions and output paths.

SRS-116 depends on (c): the single output format is defined in SRS-019.

### 5.3 SRS-064 — AUTOSAR metamodel mapping *(TBD)*

`access_point` must map to `DataReadAccess`, `DataWriteAccess` or
`ServerCallPoint`; `trigger` maps to `ExternalTriggeringPoint`. The *selection
rule* — which inputs determine which element — is undocumented.

**Owner:** development team. **Closure:** rule documented and validated against
real AUTOSAR configurations on the work computer. **Blocks:** LLD-04 §6.7.

### 5.4 SRS-071 — interface compatibility rules *(TBD)*

Connection validation should verify that connected port interfaces are
compatible. The rules are undefined.

**Owner:** development team. **Closure:** rules documented and validated
against real work configurations. **Currently handled by** SRS-125: Phase 3
accepts the connection and creates an `incomplete` ReviewIssue recording that
compatibility was not verified, so nothing is silently treated as validated.
When SRS-071 closes, that fallback is replaced by a real check.

### 5.5 Approved decisions requiring no further action

SRS-036a, SRS-046/053/092a and SRS-072 were approved on 2026-08-12 and are
implemented.

---

## 6. Work-Computer Configuration

`docs/WORK_MACHINE_CONFIGURATION.md` holds the full checklist. It is
deliberately unfilled: this repository copy contains no real work documents,
identifiers, paths, templates, AUTOSAR configuration, or proprietary
compatibility rules, and completed values must not be copied back.

Summarised, before real-data operation: obtain SRS-015 authorization; define
input formats and source identifiers; install the R210 output templates and
select the output format; define naming conventions, output paths, AUTOSAR
package paths and metamodel identifiers; define the SRS-064 selection rule; and
define and validate the SRS-071 compatibility rules.

---

## 7. What Is Left

Items 1–5 of the previous ordering are done. What remains is listed by who can
unblock it, because none of it is now a development question.

### On the work computer — Phase 5 completion

1. **Close the four entry criteria** (`docs/PHASE5_SCOPE.md` §2): R210 output
   templates (SRS-019c), naming conventions and output paths (SRS-019d),
   AUTOSAR package paths and version identifiers (SRS-019), and the
   `access_point` selection rule (SRS-064).
2. **Write one configuration module** returning a populated `TemplateSet`,
   `NamingPolicy` and `AccessPointPolicy`, and pass it to `GeneratorConfig`.
   Exact signatures: `docs/PHASE5_IMPLEMENTED_REQUIREMENTS.md` §4.1. No
   framework code should need to change; if it does, that is a deviation worth
   recording, because the seam was drawn in the wrong place.
3. **Verify byte-identity against the approved templates**, and across two runs.

### From stakeholders

4. **SRS-015** — authorization for real requirement text to reach Gemini. Until
   it is granted, the system stays in synthetic-data-only mode even on the work
   computer. This blocks *use*, not development.
5. **SRS-071** — interface compatibility rules. Until then the SRS-125 fallback
   stands: connections are accepted with an `incomplete` review issue.

### Development, optional

6. **Per-tool JSON Schema** on the MCP surface (§3A) — would make the tool
   surface self-describing to an LLM client rather than permissive.
7. **Review DEV-17–DEV-24** (Phase 2) and **DEV-39–DEV-50** (Phase 4/5).
8. **Independent acceptance testing** of Phase 4, as was done for Phase 3.
   Phase 3's independent suite found four defects the development tests missed;
   Phase 4's own testing already found five faults by execution
   (`docs/PHASE4_IMPLEMENTED_REQUIREMENTS.md` §7), which suggests the same
   exercise would be worth repeating.

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-12 | Initial listing, written after Phase 3 implementation. |
| 1.1     | 2026-08-13 | Added §1A, the authoritative phase map, retiring the original eight-phase numbering. Recorded the acceptance defects (§4.3), corrected the MCP Server status to "implemented with known acceptance defects", updated the current test result to 650/639/11, corrected the review report to eight sections and the CLI to twelve commands. |
| 1.2     | 2026-08-13 | Acceptance defects D-01–D-04 fixed; MCP Server back to Complete; current result 652 passing. |
| 1.3     | 2026-08-15 | Phase 4 complete and the Phase 5 framework delivered (DEV-39). Sections 3.1-3.3 rewritten from "still to build" to component status; §4.1 closed - `run()` was executed for the first time, found broken against `mcp` 2.x, corrected and verified (DEV-50). Added §3A for open work Phase 4 introduced, and rewrote §7 by who can unblock each item rather than by build order. Current result 846 passing. |
| 1.4     | 2026-08-15 | Expanded Phase 4/5 acceptance coverage after documentation review. Corrected SRS-104 report-only semantics and completed report child summaries; current result 865 passing. |
