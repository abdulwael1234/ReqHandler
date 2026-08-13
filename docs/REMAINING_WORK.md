# Remaining Work

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-REM-01                                                  |
| **Date**             | 2026-08-13                                                   |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-03 v1.3, R210-LLD-04 v1.3, R210-LLD-06 v1.2 |
| **Companions**       | `docs/PHASE1_IMPLEMENTED_REQUIREMENTS.md`, `docs/PHASE2_IMPLEMENTED_REQUIREMENTS.md`, `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` |
| **Status**           | Living document — updated as each remaining item closes       |
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
| *(new)* Phase 3 remediation, D-01–D-04 | **Phase 4** §3.0 | `PHASE4_SCOPE.md` |

Phase numbers now follow delivery order and nothing else. A phase that changes
scope is recorded as a deviation, as DEV-33 was, rather than renumbered.

---

## 2. Current State

Three of six components are complete. Nothing below is partially built: each
remaining component is docstring-only scaffolding whose modules describe what
they will contain.

| Component | LLD | State |
|-----------|-----|-------|
| Database Schema | LLD-01 | **Complete** (Phase 1) |
| Database Initializer | LLD-05 | **Complete** (Phase 1) |
| MCP Server | LLD-02 | **Implemented with known acceptance defects** (Phases 2–3) — D-01–D-04, see §4.3; `run()` unverified, see §4.1 |
| Gemini CLI Skill | LLD-03 | **Stub** — see §3.1 |
| Deterministic Generator | LLD-04 | **Stub** — see §3.2 |
| Local Review CLI | LLD-06 | **Stub** — see §3.3 |

**Current result (2026-08-13):** 650 tests collected, 639 passed, 11 failed.
The 11 failures are the acceptance cases for defects D-01–D-03 (§4.3).
`ruff check src tests` and `mypy src` (strict) are clean.

The 590-passing figure quoted in the Phase 3 record is the *pre-acceptance*
result, before the independent suite was added. It is historical, not current.

---

## 3. Components Still To Build

### 3.1 Gemini CLI Skill (LLD-03)

**File:** `src/gemini_skill/r210_extraction.md` — 54 lines, self-declared
`Status: Stub — behavioral rules and extraction procedures TBD`.

The file currently carries the MCP server configuration and an outline of the
role. LLD-03 specifies roughly ten times that content. Missing:

| LLD-03 § | Content | SRS |
|----------|---------|-----|
| §4.0 | Synthetic-mode gate | SRS-015 |
| §4.1 | No-invention rule | SRS-003, SRS-077 |
| §4.2 | Query-first rule | SRS-078 |
| §4.3 | Stable UUID rule | SRS-079 |
| §4.4 | Issue recording rule | SRS-080, SRS-081 |
| §4.5 | No approval authority — always pass `caller="extraction"` | SRS-082a |
| §4.6 | No direct database access | SRS-082 |
| §4.7 | Data minimization | SRS-015a |
| §5 | Classification decision tree, multi-artifact requirements | — |
| §6.1–6.9 | Nine extraction procedures, one per artifact type | — |
| §7 | When and how to create review issues | SRS-080, SRS-081 |
| §8 | Dependency-ordered processing | — |
| §9 | MCP tool error handling and batch failure | — |
| §10 | MCP tool quick reference — all 35 tools | — |
| §11 | The exact fields that enter and never enter Gemini context | SRS-015a |

**Note on §10 and §11.** These must be written against the *implemented* tool
surface, not the LLD's earlier sketch. Two Phase 3 outcomes change what the
skill can expect: `set_review_status` treats `table_hint` as optional (DEV-35),
and an extraction-mode create or update now returns only `unique_key`,
warnings and demoted keys — no record fields (DEV-38). A skill written to read
`name` or `status` back from a create response will not work.

**Blocked by:** nothing technical. Note that SRS-015 remains unapproved (§5.1),
so the skill cannot be exercised against real requirement text regardless.

### 3.2 Deterministic Generator (LLD-04) — Phases 4 and 5

**Files:** `src/r210_generator/` — 14 modules totalling ~110 lines of
docstrings. Every one is a stub.

| LLD-04 § | Module | Responsibility | SRS |
|----------|--------|----------------|-----|
| §3 | `generator.py` | Orchestrator, three generation modes | SRS-090, SRS-104 |
| §4 | `validator.py` | Parent–child exportable-tree evaluation | SRS-104a, SRS-092a |
| §5 | `validator.py` | Foreign-key validation | SRS-102 |
| §6 | `r210/renderer.py`, `r210/templates/*` | R210 file rendering, four templates | SRS-103, SRS-073 |
| §6.3–6.5 | `r210/renderer.py` | Artifact and child ordering; rejected-child exclusion | SRS-101, SRS-108, SRS-092a |
| §6.7 | `r210/templates/*` | AUTOSAR metamodel mapping | SRS-064 — **TBD, see §5.3** |
| §7 | `report/builder.py`, `report/sections.py` | Review report, eight sections (a)–(h) | SRS-104 |
| §8 | `r210/file_writer.py` | UTF-8/LF, byte-identical output | SRS-101 |
| §9 | `loader.py` | Database snapshot loading | SRS-101 |
| §10 | `models.py` | `GenerationResult` | SRS-090 |

**Also unblocks:** `trigger_generation` currently registers, validates `mode`,
and returns a structured "not yet implemented" error (DEV-31). It needs no
caller changes when the generator lands — only the delegation.

**Also completes:** the export half of SRS-036a. Phase 3 implemented the
approval block (`check_references_resolved`); "shall not be **exported**"
belongs here.

**Blocked by:** SRS-064 and SRS-019(c) for R210 file output (§5.3, §6). The
**review report is not blocked** — `REPOSITORY_REVIEW_REPORT.md` §7 recommends
building report-only generation first for exactly this reason, since it depends
on the database snapshot rather than on work-specific templates.

### 3.3 Local Review CLI (LLD-06) — Phase 4

**Files:** `src/r210_review_cli/` — 9 modules totalling ~68 lines. `cli.py`
defines `main()`, which prints `r210-review: not yet implemented` and exits 1.
The `r210-review` console script therefore resolves correctly; it simply has no
behaviour yet (see DEV-O-03, closed).

| LLD-06 § | Module | Responsibility | SRS |
|----------|--------|----------------|-----|
| §4 | `cli.py` | Argument parsing, twelve commands | SRS-123 |
| §5 | `commands/*` | Review tool bridge over the MCP handlers | SRS-118, SRS-123 |
| §6 | `display.py` | Record and tree display formatting | — |
| §7 | — | Network isolation guarantee | SRS-123 |

Commands specified (LLD-06 §4.1): `list`, `show`, `search`, `approve`,
`reject`, `mark`, `resolve`, `dismiss`, `reopen`, `report`, `generate`,
`stats`. The `cli.py` stub docstring lists only nine and is stale — LLD-06 is
normative.

**Ready to build.** Phase 3 deliberately produced the surface this component
needs: handlers are plain functions over a `ToolContext` (DEV-26), and
`tools/registry.py` exposes `dispatch`, `query_by_table`,
`get_children_for_display` and `get_stats` without importing the MCP SDK. The
CLI constructs its context with `adapter_mode="review"`, which is what permits
approval (SRS-082a) and returns full records.

**Blocked by:** nothing. This is the least-blocked remaining component and the
one that makes the system usable by a human reviewer.

---

## 4. Verification Still Owed

### 4.1 `R210McpServer.run()` has never been executed

The `mcp` SDK is not installed in this environment, so the stdio transport
wiring in `server.py` has never run. It is marked `# pragma: no cover`, and
`mypy` carries an `ignore_missing_imports` override for `mcp.*` and `anyio`.

Everything else is reachable without the SDK through `handle_tool`, which is
what LLD-06 requires, so the tool surface itself is fully tested — but the
protocol adapter is not.

**Closure condition:** install the SDK, run `python -m r210_mcp <db> --mode
extraction`, and confirm a client can list and call tools. Correct `run()` if
the SDK's API differs from the sketch; no test depends on its internals.

### 4.2 Independent testing of Phases 2 and 3

Both phases were developed to a **development-level** standard by agreement:
the tests establish that each layer works and that its boundaries hold, not
that it is exhaustively verified. Independent testing is a separate activity.

Ranked starting points are recorded in
`docs/PHASE2_IMPLEMENTED_REQUIREMENTS.md` §9 and
`docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` §10.

### 4.3 Phase 3 defects found in acceptance testing

Independent acceptance testing on 2026-08-13 found three behavioural defects
and one architectural finding, all verified against LLD-02: non-atomic port
connection creation (D-01, critical), unresolvable array references (D-02,
high), one-directional typed-reference pairing (D-03), and SQL outside the DAL
(D-04). Recorded in `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` §11 and scheduled
as the first deliverable of Phase 4 (`docs/PHASE4_SCOPE.md` §3.0).

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

## 7. Suggested Order

1. **Local Review CLI (LLD-06).** Unblocked, and it is what makes the
   implemented tool surface usable by a human reviewer. Until it exists, review
   requires direct MCP tool calls.
2. **Review-report generation (LLD-04 §7).** The half of the generator that
   depends on the database snapshot rather than on work-specific templates, so
   it can be built and golden-file tested now.
3. **Verify `run()`** on a machine with the SDK — small, and it closes the last
   untested path in a complete component.
4. **Gemini CLI Skill (LLD-03).** Writable now, but not exercisable against
   real data until SRS-015 is approved.
5. **R210 file generation (LLD-04 §6).** Genuinely blocked on SRS-019(c) and
   SRS-064; attempting it earlier means guessing at templates.

Items 1–3 need no decisions from anyone. Items 4–5 do.

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-12 | Initial listing, written after Phase 3 implementation. |
| 1.1     | 2026-08-13 | Added §1A, the authoritative phase map, retiring the original eight-phase numbering. Recorded the acceptance defects (§4.3), corrected the MCP Server status to "implemented with known acceptance defects", updated the current test result to 650/639/11, corrected the review report to eight sections and the CLI to twelve commands. |
