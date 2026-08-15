# Phase 4 — Implemented Requirements

## R210 AUTOSAR Requirements Automation Prototype

| Field | Value |
|---|---|
| **Document ID** | R210-IMP-04 |
| **Phase** | Phase 4 — Review CLI, generator core, review report, Gemini skill |
| **Date** | 2026-08-15 |
| **Branch** | `feature/phase4-5-generator-and-review-cli` |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-03 v1.3, R210-LLD-04 v1.3, R210-LLD-06 v1.2 |
| **Predecessor** | `docs/PHASE3_IMPLEMENTED_REQUIREMENTS.md` |
| **Scope** | `docs/PHASE4_SCOPE.md` |
| **Companion** | `docs/PHASE5_IMPLEMENTED_REQUIREMENTS.md` (the framework half of Phase 5) |
| **Status** | Complete |

---

## 1. Summary

Phase 4 delivers the last two components of the prototype and the extraction
skill. After this phase the prototype is usable end to end by a human reviewer
on synthetic data: extract through the MCP tools, review through the CLI,
produce a review report.

| Component | LLD | Before | After |
|---|---|---|---|
| Local Review CLI | LLD-06 | 9 stub modules, ~68 lines | Complete — 12 commands |
| Deterministic Generator | LLD-04 | 14 stub modules, ~110 lines | Complete except R210 template bodies |
| Gemini CLI Skill | LLD-03 | 54 stub lines | Complete — written against the implemented surface |
| MCP stdio adapter | LLD-02 §9 | Never executed | Executed, corrected, tested |

**Test result:** 846 passing (652 at the start of the phase). `ruff check src
tests` and `mypy src` (strict) clean.

---

## 2. Requirements Implemented

| SRS | Requirement (abridged) | Where | Verified by |
|---|---|---|---|
| SRS-090 | Operation to request generation | `tools/generation.py` | `test_assembly.py::TestTriggerGeneration` |
| SRS-101 | Byte-identical output — **review report only**; R210 output verified with synthetic templates, see §5 | `r210/file_writer.py` | `test_file_writer.py`, `test_generator.py::TestDeterminism` |
| SRS-102 | Validate approved records; exclude FK-invalid ones | `validator.py` | `test_validator.py::TestForeignKeyValidation` |
| SRS-104 | Review report, producible independently, eight sections | `report/` | `test_report.py` |
| SRS-104a | Parent exported only when all non-rejected children approved | `validator.py` | `test_validator.py::TestChildApproval` |
| SRS-092a | Rejected children excluded from evaluation and output | `validator.py`, `r210/renderer.py` | `test_validator.py`, `test_renderer.py` |
| SRS-108 | Deterministic child ordering | `loader.py`, `r210/renderer.py` | `test_loader.py`, `test_renderer.py::TestChildOrdering` |
| SRS-118 | Manual review through the MCP tool surface | `r210_review_cli/` | `test_commands.py`, `test_cli.py` |
| SRS-123 | Local review CLI, no Gemini API connection | `r210_review_cli/bridge.py` | `test_isolation.py` — **adversarial** |
| SRS-119 | Review issue lifecycle | `commands/issues.py` | `test_commands.py::TestIssueCommands` |
| SRS-089 | Reviewer sets artifact status | `commands/status.py` | `test_commands.py::TestStatusCommands` |
| SRS-087 | Reference resolution for display | `bridge.py::show` | `test_bridge.py::TestBridgeShow` |
| SRS-036a | Unresolved references block export | `validator.py` | `test_validator.py` |
| SRS-003, SRS-077–SRS-082a, SRS-015a | Extraction behavioural rules | `gemini_skill/r210_extraction.md` | `test_skill_matches_tools.py` |
| SRS-086 | Tool surface discoverable over the protocol | `server.py::build_server` | `test_server_adapter.py` |
| SRS-109 | Structured errors | `server.py`, `display.py` | `test_server_adapter.py`, `test_display.py` |

**Not covered — Phase 5:** SRS-103 (R210 file generation), SRS-064 (AUTOSAR
metamodel mapping), SRS-073 (port connection rendering content).

---

## 3. Definition of Done — `docs/PHASE4_SCOPE.md` §7

| # | Criterion | Status |
|---|---|---|
| 1 | §3.1–§3.5 implemented | **Met** |
| 2 | `pytest` passes | **Met** — 846 passing |
| 3 | `ruff check src tests`, `mypy src` clean | **Met** |
| 4 | `r210-review` runs end to end on a synthetic database | **Met** — §4 |
| 5 | Report byte-identical across two runs; §5.4 decided | **Met** — DEV-46 |
| 6 | `R210McpServer.run()` executed against a real MCP client | **Met** — §5 |
| 7 | This document written; deviations recorded from DEV-38 | **Met** — DEV-39…DEV-50 |
| 8 | `docs/REMAINING_WORK.md` updated | **Met** |

---

## 4. End-to-End Walkthrough (criterion 4)

Run on 2026-08-15 against a synthetic database, entirely through the console
script:

```
r210-review --db <db> list td            → 2 records, both pending_review
r210-review --db <db> show <struct_key>  → fields + 1 child (StructElements)
r210-review --db <db> approve <base_key> → ✓ approved
r210-review --db <db> approve <elem_key> → ✓ approved
r210-review --db <db> approve <td_key>   → ✓ approved
r210-review --db <db> resolve <issue> --resolution "units are mV"  → ✓ resolved
r210-review --db <db> report --output <dir>  → review_report.md written, exit 0
r210-review --db <db> generate --mode both --output <dir>
    → exit 1, naming SRS-019(c), SRS-019(d), SRS-019, SRS-064 as unmet
```

Approval order matters and the system enforces it: approving the struct before
its element is refused (SRS-046), and approving the element before its base type
is refused because the element's `element_type_id` would still point at a
non-approved record (SRS-036a).

---

## 5. `R210McpServer.run()` — now verified (criterion 6)

This was the one never-executed path in the codebase. The `mcp` SDK installed
successfully in this environment (version 2.0.0), so it was run — **and it did
not work**. See DEV-50.

LLD-02 §9's `server.call_tool(name)(handler)` registration does not exist in
`mcp` 2.x. `run()` was rewritten against the lowlevel `Server`'s `on_list_tools`
/ `on_call_tool` interface, and `build_server()` split out so the wiring is
testable without opening a transport.

Verified out of band with a real `ClientSession` over stdio, against
`python -m r210_mcp <db> --mode extraction`:

| Check | Result |
|---|---|
| `initialize` | server `r210-automation`, protocol `2025-11-25` |
| `tools/list` | 35 tools |
| `create_type_definition` | returned `unique_key` only (SRS-015a clause c) |
| `query_type_definitions` | returned `unique_key`, `name`, `kind`, `status` — **no `description`** (SRS-015a) |
| `set_review_status` with `caller="review"` | refused, SRS-082a error |
| unknown tool | structured error, `is_error=True` (SRS-109) |

`tests/test_r210_mcp/test_server_adapter.py` locks the wiring in and is skipped
via `importorskip` when the SDK is absent, so the remaining 838 tests still run
without it.

**Known gap:** tools are advertised with a permissive input schema. Generating
per-tool JSON Schema from the existing descriptors is recorded as open work.

---

## 6. Adversarial Verification

`docs/PHASE4_SCOPE.md` §7 carries two areas forward from the Phase 3 precedent
that must be tested adversarially rather than at development level.

### 6.1 Network isolation (SRS-123)

LLD-06 §7 asks for a code review. A code review is not re-runnable, so it was
replaced by two independent automated checks:

| Check | Method |
|---|---|
| Static | AST-walk every module under `r210_review_cli/`, collect every import target, reject any in the forbidden set |
| Dynamic | Import the CLI in a clean subprocess, assert `mcp`, `httpx`, `requests`, `aiohttp`, `websockets` never enter `sys.modules` |

The static scan also asserts it covered a non-zero number of files, and a
control test proves the scanner detects a planted `import httpx`. Both would
fail if `bridge.py` followed LLD-06 §5.1 and imported `R210McpServer` (DEV-40).

### 6.2 Report determinism (SRS-101)

Asserted by comparing the **bytes** of two written reports, not two Python
strings: a string comparison passes even when encoding or line endings differ,
which is exactly what SRS-101 forbids. A separate test asserts the written
report contains no CRLF.

The timestamp question (`docs/PHASE4_SCOPE.md` §5.4) is decided by DEV-46:
injected via `GeneratorConfig.generated_at`, omitted entirely when `None`. A
test asserts two runs differing only in the injected value produce reports that
differ only there.

---

## 7. Defects Found by Running the System

Five faults were found by executing the code rather than by reading the
documents. They are recorded in full in `docs/DEVIATIONS_FROM_REQUIREMENTS.md`
§4C; summarised here because the pattern matters more than any one of them.

| # | Fault | Would have surfaced as | Deviation |
|---|---|---|---|
| 1 | `trigger_generation` defaulted `output_dir` to a relative path | A review report written into whatever directory the server was started in — it landed in the repository root | DEV-48 |
| 2 | `GenerationResult.summary()`'s `warnings` count collided with the MCP envelope's `warnings` list | `TypeError` on **every** successful `r210-review report` | DEV-49 |
| 3 | `run()` used an SDK API that does not exist | The MCP server would not start at all | DEV-50 |
| 4 | LLD-06 §6.2's glyphs are outside cp1252 | `UnicodeEncodeError` on any Windows console | DEV-44 |
| 5 | R210 modes reported success on an empty database | A "successful" generation that produced nothing and never could | DEV-47 |

Faults 2 and 4 passed the test suite. Fault 2 was invisible because no test
called the report command through the CLI; fault 4 because pytest captures
stdout as UTF-8 while a real console does not. Both now have regression tests
that fail without their fix — verified by reverting each fix and observing the
failure.

---

## 8. What Phase 4 Deliberately Did Not Do

| Item | Reason |
|---|---|
| R210 template bodies, AUTOSAR mapping | SRS-019(c) and SRS-064 are work-computer values, deliberately absent (`docs/WORK_MACHINE_CONFIGURATION.md`) |
| Real-data extraction | SRS-015 unapproved — synthetic data only |
| SRS-071 interface compatibility validation | TBD; the SRS-125 fallback from Phase 3 stands |
| Per-tool JSON Schema on the MCP surface | Open work — see §5 |

---

## 9. Traceability

Module docstrings end with `See: LLD-0n §x`. Test docstrings cite the `SRS-nnn`
they verify. Both conventions are followed by every file added in this phase.

New test packages:

| Package | Covers |
|---|---|
| `tests/test_r210_review_cli/` | LLD-06 — bridge, display, commands, CLI, isolation |
| `tests/test_r210_generator/` | LLD-04 — loader, validator, report, file writer, renderer, generator |
| `tests/test_gemini_skill/` | LLD-03 — skill cross-checked against `TOOL_HANDLERS` |
| `tests/test_r210_mcp/test_server_adapter.py` | LLD-02 §9 — the stdio adapter |
| `tests/test_r210_mcp/test_dal_search.py` | DEV-43 |

---

## Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-15 | Initial record. Phase 4 complete; all eight `PHASE4_SCOPE.md` §7 criteria met, including `run()` verification, which the scope had marked conditional. |
