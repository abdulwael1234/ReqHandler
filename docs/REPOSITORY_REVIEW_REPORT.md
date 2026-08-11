# R210 Repository Architecture and Requirements Review

**Review date:** 2026-08-11  
**Repository state:** `master` at `7b40e6f` (single clean initial commit)  
**Review scope:** System Description → SRS → HLD → LLD → repository structure → implementation and verification

## 1. Executive Summary

The repository is a substantial **design package with implementation scaffolding**, not an operational prototype. The documentation is unusually detailed and the HLD traceability matrix names all 138 SRS requirements, but the baseline is not ready for implementation or acceptance:

- All six runtime areas are missing or stubbed: Gemini skill, MCP server, database initializer, database schema migration, generator, and review CLI.
- The documented quick-start commands do not run.
- No tests exist; `pytest` reports that no tests were collected.
- The security design is not enforceable as written. The synthetic-data gate is inside the Gemini workflow, after data may already have crossed the API boundary, and approval authority is selected using a caller-supplied tool parameter.
- The SRS contains a direct contradiction in rejected-child export behavior.
- The LLD contains executable-design defects, including database index-name mismatches that would make schema verification fail and CLI/tool contracts that do not match.
- The design documents are all marked Draft, several baseline-blocking decisions remain open, and document source-version metadata is stale despite the README claiming “Design complete.”

**Overall assessment:** Red / not executable / not ready for real-data use. The repository is useful as a requirements and design draft, but it should not be presented as a working prototype or an approved implementation baseline.

## 2. Review Method and Evidence

The review treated the current tree as the target because the repository has one root commit and no later comparison point. It covered:

1. Source-document decomposition and forward traceability.
2. Cross-document consistency and requirement allocation.
3. HLD module and interface design.
4. LLD contract and pseudocode consistency.
5. Actual Python/package structure and executable behavior.
6. Test, compile, and command checks.

Measured repository facts:

| Measure | Result |
|---|---:|
| SRS requirements | 138 |
| HLD traceability matrix coverage | 138/138 IDs named |
| LLD traceability-matrix union | 111/138 IDs named |
| Files under `src/` | 58 |
| Python files under `src/` | 57 |
| Actual concrete/abstract class definitions | 2 |
| Test modules | 0 |
| Tests collected | 0 |

The two class definitions are `Migration` and `V001InitialSchema`; the latter's `up()` method is a `pass` placeholder.

## 3. Requirements Breakdown Review

### 3.1 System Description

The System Description gives a coherent high-level problem statement:

- Seven supported artifact families.
- Human review as the quality gate.
- Gemini for nondeterministic extraction.
- MCP as controlled persistence access.
- SQLite for local structured storage.
- Deterministic generation after approval.

Its strongest feature is scope clarity. It explicitly excludes complex architecture generation, large-volume/concurrent processing, recovery, backup, and automated extraction-quality measurement.

Its main unresolved problem is foundational: `Sytem_description/system_Description.md:37-38` requires Gemini while prohibiting transfer of real work information outside the work computer. The SRS correctly recognizes this as a blocking stakeholder/security decision, but the downstream design does not yet provide a technically enforceable control.

The source document also lacks stable requirement IDs. SRS rows cite source sections rather than source requirement identifiers, so backward traceability is human-readable but not mechanically reliable.

### 3.2 SRS

The SRS expands the source into 138 requirements across functional, data, interface, constraint, and non-functional categories. It adds useful detail around:

- Status transitions and parent/child invariants.
- Stable UUID references.
- Transaction boundaries.
- Typed review-issue references.
- Deterministic ordering and reporting.
- A local review CLI.
- Migration atomicity.

However, it is not an approved baseline:

- Its status is Draft (`Srs/SRS_Requirements.md:11`).
- SRS-015 blocks real-data use.
- SRS-019 leaves input formats, source mapping, templates, output format, naming, and input adapters unresolved.
- SRS-036a, SRS-046/SRS-053, SRS-064, SRS-071, SRS-072, and SRS-092a still require decisions or validation.
- Twenty mandatory requirements are marked as derived rather than directly sourced. Their approval state is not consistently represented in the Stakeholder Decisions Register.

#### SRS contradictions and quality issues

1. **Rejected-child export contradiction.** SRS-092a permits a parent to be exported when rejected children exist, omitting those children (`Srs/SRS_Requirements.md:204`). SRS-104a says all children must be approved and any non-approved child excludes the entire parent (`:227`). HLD and LLD select the SRS-092a interpretation, but the SRS remains internally inconsistent.

2. **System composition drift.** SRS-020 defines five system parts (`:76`), while SRS-123 adds a Local Review CLI and the HLD declares six components (`archi/HLD_High_Level_Design.md:88`). SRS-020 should be amended or explicitly distinguish core components from adapters/interfaces.

3. **Modality-rule violations.** The SRS says every requirement uses shall/should/may (`Srs/SRS_Requirements.md:17`), but SRS-019 (`:70`) and SRS-038 (`:103`) use none of them.

4. **Stale revision text.** The Stakeholder Decisions Register says “v6.0 aligned SRS-046/053” (`:277`) although the current document is v5.1.

5. **Derived-decision governance is unclear.** SRS-015a, SRS-035a/b/c, SRS-038a/b/c, SRS-082a/b, SRS-091a, SRS-092a, SRS-104a, and SRS-118–125 are marked derived. Some are technical refinements; others materially define behavior not present in the source. The document convention says design choices not directly stated in the source require stakeholder approval, but the register does not consistently track them.

### 3.3 HLD

The HLD has strong component descriptions, data-flow diagrams, tool allocation, error categories, determinism rules, and an explicit 138/138 SRS ID matrix. Automated inspection confirmed all 138 SRS identifiers appear in that matrix.

That numeric coverage does not prove consistency or implementability. Key problems are:

1. **Stale baseline metadata.** HLD v3.1 still names SRS v5.0 as its source (`archi/HLD_High_Level_Design.md:10,48`), although its own revision history says v3.1 aligned with SRS v5.1 (`:878`).

2. **Security-boundary contradictions.** The context diagram labels the API flow “input text only” (`:63`) while SRS-015a and the surrounding HLD text also permit selected MCP results. The deployment narrative calls the API connection “an approved transfer limited to input text” (`:127`) even though approval is still blocking and the permitted payload is broader.

3. **Baseline claim conflict.** HLD §9 says no implementation baseline shall be established until baseline-blocking items are resolved (`:805`), while the README says design is complete (`README.md:94`).

4. **Architecture seam is misplaced.** The designed `R210McpServer` combines protocol registration, dispatch, database lifecycle, validation orchestration, and tool logic. The review CLI then calls private `_handle_*` methods and private DAL state. There is no stable public application module interface shared by the MCP and CLI adapters.

5. **Security role is data, not authority.** The design gives `set_review_status` an optional caller parameter. A Gemini tool call can omit it or supply `caller="review"`; the server has no trustworthy basis for distinguishing extraction from human review.

### 3.4 LLD

The six LLDs broadly mirror the planned component tree, and their file/module layouts match the scaffolded `src/` tree. They provide useful pseudocode and schemas, but they are Draft documents with several contract defects.

The union of their traceability matrices names 111 of the 138 SRS IDs after expanding numeric ranges. Some omissions are system-level or deliberate scope exclusions, but important implementation requirements are also unallocated in the matrices, including SRS-023, SRS-025, SRS-031, SRS-038, SRS-082a, SRS-091, SRS-105, SRS-106, and SRS-107.

All amended LLD v1.1 headers still cite SRS v5.0/HLD v3.0 rather than SRS v5.1/HLD v3.1.

## 4. Findings by Severity

### Critical

#### C-01 — No operational implementation exists

Nearly every Python module contains only a descriptive docstring. Examples:

- `src/r210_mcp/server.py:1-10`
- `src/r210_mcp/db/dal.py:1-10`
- `src/r210_generator/generator.py:1-11`
- `src/r210_review_cli/cli.py:1-18`
- `src/r210_db_init/initializer.py:1-10`

The only concrete migration explicitly does nothing (`src/r210_db_init/migrations/v001_initial_schema.py:24-27`). Therefore the database, MCP, extraction, review, generation, transaction, validation, traceability, and report requirements are not implemented.

**Impact:** No end-to-end scenario can run; no requirement can be accepted through executable evidence.

#### C-02 — Advertised commands are broken

- `python -m r210_db_init --help` fails because `r210_db_init.cli` has no `main`.
- `python -m r210_review_cli --help` fails because `r210_review_cli.cli` has no `main`.
- The skill launches `python -m r210_mcp` (`src/gemini_skill/r210_extraction.md:10-13`), but `r210_mcp/__main__.py` does not exist.
- `pyproject.toml:24-25` publishes console scripts targeting the same nonexistent functions.

**Impact:** The README quick start cannot initialize, review, or launch MCP.

#### C-03 — The confidentiality gate is on the wrong side of the trust boundary

LLD-03 places the synthetic/real-data check inside the Gemini skill (`lld/LLD_03_Gemini_CLI_Skill.md:67-84`) and asks the skill to decide whether input “appears” real. By the time a cloud-hosted Gemini skill can inspect the requirement, that requirement may already have been transmitted to the Gemini API.

**Impact:** The design cannot enforce SRS-015's prohibition. It relies on post-transfer classification to prevent transfer.

**Required correction:** Put an explicit local preflight/launcher before Gemini CLI. The local control must require an approved configuration and an operator-selected data classification before any prompt is sent. Do not ask the LLM to determine whether it was allowed to receive the data.

#### C-04 — Approval authorization is bypassable by tool arguments

SRS-082a requires the MCP server to prevent Gemini from approving records. LLD-02 implements this by accepting optional `caller` input and only rejecting approval when `caller == "extraction"` (`lld/LLD_02_MCP_Server.md:753-774`). A caller can omit the value or claim `"review"`.

**Impact:** Prompt injection, model error, or a malformed client can bypass the human approval gate.

**Required correction:** Bind the role to a trusted adapter/session configuration. Prefer separate extraction and reviewer interfaces, or construct the operations module with immutable authority. Never accept authority as an untrusted tool argument.

#### C-05 — The documented Gemini allowlist is violated by the LLD

SRS-015a permits only `unique_key`, `name`, `kind`, `interface_type`, `status`, and `direction` from queries. LLD-02 additionally projects `issue_type` (`lld/LLD_02_MCP_Server.md:1054`) and substitutes `source_reference` (`:1071-1075`). The same section first lists a nonexistent `SourceRequirements.name` field (`:1040`) and then overrides it.

**Impact:** Implementing the LLD literally would violate the declared confidentiality control.

### High

#### H-01 — Database initializer verification uses the wrong index names

LLD-05 verifies `idx_source_req_status`, `idx_type_def_kind`, and `idx_type_def_status` (`lld/LLD_05_Database_Initializer.md:258-270`), but its migration creates `idx_source_requirements_status`, `idx_type_definitions_kind`, and `idx_type_definitions_status` (`:586-603`). LLD-01 uses the longer names as well.

**Impact:** A literal implementation of the design would create the schema successfully and then always report schema verification failure.

#### H-02 — Initial ambiguous/out-of-scope status cannot be expressed

SRS-035a and LLD-03 say extraction may set `ambiguous` or `out_of_scope` at creation time (`lld/LLD_03_Gemini_CLI_Skill.md:132-140,291-293`). LLD-02 create contracts do not accept an initial status and set new records to `pending_review` (`lld/LLD_02_MCP_Server.md:484-499,575-583`).

**Impact:** The skill instructions cannot be implemented through the declared tool interface.

#### H-03 — Review CLI and MCP status contracts do not match

LLD-02 marks `table_hint` as required for `set_review_status` (`lld/LLD_02_MCP_Server.md:753-761`). LLD-06 calls `_handle_set_review_status` without it (`lld/LLD_06_Local_Review_CLI.md:213-224`).

**Impact:** Approve/reject/mark commands would fail validation if both documents are implemented literally.

#### H-04 — Review CLI bypasses the claimed shared tool interface

LLD-06 says it invokes the same MCP tool functions, but directly accesses `_handle_*`, `_dal`, and database reads for child tables (`lld/LLD_06_Local_Review_CLI.md:179-211,237-267`). These are private implementation details, not a stable interface.

**Impact:** Validation and projection behavior can diverge between Gemini and review paths; refactoring the transport server can break the CLI.

**Architecture correction:** Create a deep `R210Operations` module whose public interface owns validation, transactions, status invariants, and queries. The MCP server and Local Review CLI become two adapters at that seam. Keep SQLite/DAL details internal until a second storage adapter genuinely exists.

#### H-05 — Generator result construction is incomplete in the LLD

The generator assigns rendered files, errors, and warnings but never assigns `exported_artifacts` (`lld/LLD_04_Deterministic_Generator.md:98-118`). The report's “Approved & Generated” section reads `generation_result.exported_artifacts` (`:389-395`).

**Impact:** A combined generation/report run can create files while reporting no approved/generated artifacts.

#### H-06 — Nullable connection descriptions can break deterministic sorting

`PortConnections.description` is nullable (`lld/LLD_01_Database_Schema.md:455-463`), but the generator uses it as a sort field and calls `.lower()` (`lld/LLD_04_Deterministic_Generator.md:277-287,298-310`).

**Impact:** An approved connection without a description can raise an exception during generation.

#### H-07 — Design completeness is overstated

README says “Design complete” (`README.md:94`), while SRS, HLD, and all LLDs are Draft and HLD §9 lists baseline blockers. R210 templates and naming, input formats/adapters, AUTOSAR mapping, and security approval remain unresolved.

**Impact:** Stakeholders may treat an unapproved, partially contradictory draft as an implementation baseline.

#### H-08 — Runtime dependency and packaging configuration is incomplete

HLD selects “Python + MCP SDK” (`archi/HLD_High_Level_Design.md:796`), but `pyproject.toml:13` declares no runtime dependencies. The Gemini skill is a loose Markdown file with no package-data configuration, and the MCP package has no module entry point.

**Impact:** Even completed source code would not be reproducibly installable or launchable from the current package metadata.

#### H-09 — No verification assets exist

Every tracked test file is an empty `__init__.py`; there are no fixtures, contract tests, integration tests, golden outputs, or end-to-end synthetic samples.

**Impact:** None of the 138 requirements, transaction invariants, confidentiality projections, or determinism claims have executable evidence.

### Medium

#### M-01 — LLD traceability is incomplete

The following SRS IDs are absent from the six LLD traceability matrices:

`SRS-004, 011, 012, 014, 016, 018, 020, 022, 023, 025, 031, 033, 038, 082a, 091, 092, 105, 106, 107, 110–117`.

Some are architectural, environmental, or explicit exclusions, but the matrices should still allocate implementation, verification, or “not applicable by design” ownership. SRS-082a is especially notable because LLD-02 and LLD-03 discuss it but omit it from their matrices.

#### M-02 — LLD-03 structure and cross-references are inconsistent

- Two sections are numbered §4.6 (`lld/LLD_03_Gemini_CLI_Skill.md:144,151`).
- The traceability matrix labels §4.5 “No Direct DB,” omitting the actual §4.5 approval rule and §4.0 security gate (`:529-546`).
- The allowed-data table duplicates the warnings row (`:503-505`).
- It points to LLD-02 §7.10 for projection (`:493,523`), while projection is actually LLD-02 §11.
- The shorter §4.6 allowlist omits fields/exclusions later added in §11.

#### M-03 — Schema verification does not verify the claimed schema

LLD-05 checks table names, selected index names, and current FK violations. It does not verify column definitions, nullability, CHECK/UNIQUE/FK constraints, all indexes, or whether `PRAGMA foreign_keys` is enabled (`lld/LLD_05_Database_Initializer.md:223-291`). `CREATE TABLE IF NOT EXISTS` also cannot repair a malformed existing table.

**Impact:** SRS-096's “missing tables, constraints, and indexes” guarantee is not met by the designed verification algorithm.

#### M-04 — Newer database versions are not rejected

The initializer uses `target_version = len(MIGRATIONS)` and treats any current version at or above it as up to date (`lld/LLD_05_Database_Initializer.md:152-197`). It has no explicit `current_version > target_version` error.

**Impact:** Older application code may run against a newer, incompatible schema.

#### M-05 — ReviewIssue parameter documentation conflicts with the SRS and algorithm

The input table says `artifact_unique_key` is required when `artifact_type` is set (`lld/LLD_02_MCP_Server.md:713-719`), while SRS-074 and the handler algorithm only require `artifact_type` when a key is set (`:721-725`).

#### M-06 — Validation results are not clearly included in the authoritative report

HLD says unresolved FKs are reported as validation errors (`archi/HLD_High_Level_Design.md:386-387`), but LLD-04's report sections only include parent/child warnings and status/issue buckets (`lld/LLD_04_Deterministic_Generator.md:364-375`). It is unclear where FK errors appear in the authoritative report.

#### M-07 — Query projection is tied to transport, not authority

LLD-02 applies the Gemini projection to all query handlers invoked through MCP and removes it only for direct Local Review CLI calls (`lld/LLD_02_MCP_Server.md:1063-1067`). A human reviewer using MCP cannot request full records, while the local CLI obtains them through private/direct paths.

**Impact:** Data visibility, authorization, and transport are conflated.

### Low / Repository Hygiene

1. `Sytem_description` is misspelled; directory capitalization and naming styles are inconsistent (`Srs`, `archi`, `lld`, `system_Description.md`).
2. README advertises `docs/` and mirrored test suites, but `docs/` was empty and tests do not mirror functionality.
3. There is no CI workflow, sample synthetic input, sample generated output, example configuration, or acceptance-test mapping.
4. `schema_version` has no primary key/uniqueness rule on version and no explicit monotonicity protection in the schema.
5. README calls LLD-01 v1.0 while generally describing all LLDs as v1.1 in the initial commit message; version wording should be kept exact.

## 5. Component Readiness Matrix

| Area | Design state | Code state | Verification state | Readiness |
|---|---|---|---|---|
| System/SRS baseline | Detailed but Draft; blockers and contradictions | N/A | No approval evidence | Red |
| Database schema | Detailed LLD-01 | Migration `pass` | No schema tests | Red |
| Database initializer | Detailed but contains verification defects | CLI/orchestrator absent | Command fails | Red |
| MCP server | 35-tool design; security/interface defects | Docstrings only | No contract/integration tests | Red |
| Gemini skill | Detailed LLD; actual skill is a stub | TODO sections | No synthetic extraction test | Red |
| Deterministic generator | Detailed but templates/TBDs and result bugs | Docstrings only | No golden/determinism tests | Red |
| Local review CLI | Detailed but private-interface mismatch | CLI/commands absent | Command fails | Red |
| Packaging | Basic setuptools metadata | Missing runtime deps/MCP entry | Install path not validated | Red |
| Tests/CI | Directory scaffold only | No tests | `pytest`: 0 collected | Red |

## 6. Repository Structure Assessment

The planned package split is understandable and maps closely to the six LLD documents. The main structural problem is that directory boundaries do not yet correspond to stable module interfaces.

Recommended target structure:

```text
src/
├── r210_core/
│   ├── operations.py        # Public R210Operations interface
│   ├── models.py            # Domain/result types
│   ├── validation/          # Internal validation implementation
│   └── persistence/         # Internal SQLite implementation and migrations
├── r210_mcp/                # MCP adapter; binds extraction authority
├── r210_review_cli/         # CLI adapter; binds reviewer authority
├── r210_generator/          # Deep generate(...) module + internal renderer/report
├── r210_db_init/            # Thin administrative adapter to migrations
└── gemini_skill/            # Packaged skill/template assets
```

The important change is the seam, not the directory name:

- `R210Operations` should expose the smallest public interface that both adapters need.
- Transactions and invariants remain inside that module for locality.
- MCP and CLI are adapters; neither calls private methods of the other.
- Authority is fixed when an adapter is constructed, not passed in operation data.
- SQLite remains an internal implementation. With only one storage adapter, a speculative repository interface adds no value.
- Tests exercise the same public interface as callers. Protocol/CLI contract tests then verify adapter mapping separately.

## 7. Recommended Remediation Sequence

### Phase 0 — Establish an approved baseline

1. Resolve SRS-015 before any real-data testing.
2. Define a local pre-Gemini security gate and trusted execution-role model.
3. Reconcile SRS-092a with SRS-104a.
4. Resolve or formally defer SRS-019(a-d), SRS-036a, SRS-046/053, SRS-064, SRS-071, and SRS-072.
5. Update SRS-020 for the Local Review CLI.
6. Correct HLD/LLD source versions, statuses, trace matrices, numbering, and allowlists.
7. Replace “Design complete” with an accurate maturity statement until approval criteria are met.

### Phase 1 — Build the database vertical slice

1. Implement V001 schema from one authoritative SQL/migration source.
2. Correct index naming and implement full schema introspection.
3. Reject databases newer than the application migration target.
4. Add temporary-SQLite integration tests for fresh init, repeat init, failed migration rollback, FK enforcement, CHECK/UNIQUE constraints, and preservation of data.

### Phase 2 — Build the shared operations module

1. Implement public result/error models.
2. Implement create/query/update/status operations with trusted authority.
3. Put transaction ownership, status transitions, parent demotion, duplicate warnings, and connection validation inside the module.
4. Add contract tests for every operation and negative path.

### Phase 3 — Add adapters

1. Implement MCP stdio entry point and declare the exact SDK dependency.
2. Implement Local Review CLI against the same public operations interface.
3. Package the Gemini skill and configuration.
4. Test that Gemini projections never expose a field outside the allowlist.
5. Test that extraction authority cannot approve even with hostile tool input.

### Phase 4 — Deliver deterministic outputs incrementally

1. Implement report-only generation first because it is independent of final R210 templates.
2. Add golden-file tests for ordering, UTF-8/LF output, status buckets, decision log, validation warnings, and FK errors.
3. Resolve template/naming/AUTOSAR mapping TBDs.
4. Implement R210 generation and byte-for-byte repeatability tests.

### Phase 5 — End-to-end acceptance

Create synthetic acceptance scenarios covering every supported artifact type, ambiguity/incomplete/out-of-scope cases, unresolved references, manual approval/rejection, rejected-child export, generation, and the authoritative report. Map each test to SRS IDs.

## 8. Verification Results

Commands run against the current repository:

| Check | Result |
|---|---|
| `python -m compileall -q src` | Pass; syntax only |
| `python -m pytest -q` | Fail: no tests ran |
| `PYTHONPATH=src python -m r210_db_init --help` | Fail: cannot import `main` |
| `PYTHONPATH=src python -m r210_review_cli --help` | Fail: cannot import `main` |
| `PYTHONPATH=src python -m r210_mcp --help` | Fail: no `r210_mcp.__main__` |
| Ruff | Not available in the current environment |
| mypy | Not available in the current environment |

Compilation is not evidence of implementation because docstring-only modules are syntactically valid.

## 9. Acceptance Criteria for Leaving “Red” Status

The project should not be called an operational prototype until all of the following are true:

- Security/stakeholder approval and the pre-Gemini enforcement mechanism are documented and tested.
- SRS/HLD/LLD versions form one approved, internally consistent baseline.
- All advertised entry points run after a documented install.
- Database initialization is atomic, idempotent, and schema-verified.
- MCP and review CLI share a public operations module rather than private handlers.
- Extraction cannot approve records through any input manipulation.
- The field allowlist is enforced by tests.
- At least one end-to-end synthetic workflow passes.
- Deterministic report output has golden tests.
- Final R210 templates/naming are resolved before R210 generation is accepted.

## 10. Final Conclusion

The repository has a strong amount of design thought and a mostly sensible top-level workflow, but document volume currently masks the absence of executable behavior and several important cross-layer contradictions. The next productive step is not broad implementation of all scaffold files. It is to secure and approve the baseline, establish one deep operations module with two trustworthy adapters, and deliver a tested database-to-report vertical slice. That sequence will turn the current design archive into an implementation that can be reviewed, verified, and safely extended.
