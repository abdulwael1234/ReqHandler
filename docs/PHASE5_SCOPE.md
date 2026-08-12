# Phase 5 — Scope

## R210 AUTOSAR Requirements Automation Prototype

| Field                | Value                                                        |
|----------------------|--------------------------------------------------------------|
| **Document ID**      | R210-SCOPE-05                                                |
| **Phase**            | Phase 5 — R210 file generation on the work computer          |
| **Date**             | 2026-08-13                                                   |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-04 v1.3 §6                       |
| **Predecessor**      | `docs/PHASE4_SCOPE.md`                                       |
| **Companion**        | `docs/WORK_MACHINE_CONFIGURATION.md`                         |
| **Status**           | **Blocked** — cannot start until the entry criteria in §2 are met |

---

## 1. Purpose

Phase 5 delivers R210 AUTOSAR requirement file generation (SRS-103): the one
part of the system that cannot be written without work-specific configuration.

It is a small phase by module count and a large one by verification effort.
Almost all of it is rendering against templates that do not exist in this
repository copy, verified byte-for-byte against approved examples.

---

## 2. Entry Criteria

Phase 5 **cannot begin** until all of the following are true. Each is a
decision or a value, not development work.

| # | Criterion | SRS | Owner |
|---|-----------|-----|-------|
| 1 | R210 output templates installed and approved | SRS-019(c) | Work computer |
| 2 | File and artifact naming conventions, output paths defined | SRS-019(d) | Work computer |
| 3 | AUTOSAR package paths and metamodel/version identifiers defined | SRS-019 | Work computer |
| 4 | `access_point` selection rule documented — which input picks `DataReadAccess`, `DataWriteAccess` or `ServerCallPoint` | SRS-064 | Development team |
| 5 | Phase 4 complete | — | Development |

Criteria 1–4 are recorded in `docs/WORK_MACHINE_CONFIGURATION.md` and must be
completed **on the work computer**, after the repository is transferred.

**SRS-071 (interface compatibility) is not an entry criterion.** It affects
validation, not rendering. Until it closes, the SRS-125 fallback delivered in
Phase 3 stands: connections are accepted and an `incomplete` ReviewIssue
records that compatibility was not verified.

---

## 3. Deliverables

### 3.1 R210 rendering subpackage

**Package:** `src/r210_generator/r210/` — the only part of the generator Phase 4
leaves untouched, apart from `file_writer.py`.

| LLD-04 § | Module | Responsibility | SRS |
|----------|--------|----------------|-----|
| §6.1–6.2 | `renderer.py` | Template dispatch and rendering pipeline | SRS-103 |
| §6.3 | `renderer.py` | Artifact ordering for determinism | SRS-101 |
| §6.4 | `renderer.py` | Child record ordering | SRS-108 |
| §6.5 | `renderer.py` | Rejected-child exclusion | SRS-092a |
| §6.6 | `templates/port_connection.py` | Port connection rendering | SRS-073 |
| §6.7 | `templates/*` | AUTOSAR metamodel mapping | SRS-064 |
| §6.1 | `templates/type_definition.py` | Type definition template | SRS-103 |
| §6.1 | `templates/port_interface.py` | Port interface template | SRS-103 |
| §6.1 | `templates/port_prototype.py` | Port prototype template | SRS-103 |

### 3.2 Generation modes

Phase 4 makes `report_only` operative. Phase 5 completes the other two
(LLD-04 §3.2):

| Mode | Precondition |
|------|-------------|
| `r210_only` | ≥ 1 fully-approved artifact tree |
| `both` | ≥ 1 fully-approved artifact tree for the R210 portion |

`trigger_generation` then delegates all three modes and stops reporting
unavailability (DEV-31 closes).

### 3.3 Determinism verification

SRS-101 requires byte-identical output for the same database content,
generator version and work configuration. For R210 files the relevant input is
the set of **fully-approved artifact trees**.

This is the bulk of the phase's effort: golden-file tests over real approved
templates, covering ordering, UTF-8/LF encoding, rejected-child exclusion, and
repeatability across runs.

---

## 4. Requirements Covered

| SRS | Requirement (abridged) | Deliverable |
|-----|------------------------|-------------|
| SRS-103 | Generate R210 files for the supported artifact types | §3.1 |
| SRS-101 | Byte-identical R210 output from approved trees | §3.3 |
| SRS-064 | `access_point` / `trigger` metamodel mapping | §3.1 (§6.7) |
| SRS-073 | Port connection rendering | §3.1 |
| SRS-090 | All three generation modes operative | §3.2 |
| SRS-116 | Single output format, per SRS-019 | §3.1 |
| SRS-092a, SRS-108 | Exclusion and ordering, applied to R210 output | §3.1 |

---

## 5. What Phase 4 Leaves Ready

Phase 5 inherits a complete generator framework and adds only rendering.
LLD-04 §11 states the intent directly: the TBDs "do not block the design of the
generator's architecture — template implementations are pluggable."

| Delivered in Phase 4 | Used by Phase 5 |
|----------------------|-----------------|
| `loader.py` — database snapshot | Input to rendering |
| `validator.py` — exportable-tree evaluation (SRS-104a, SRS-092a) | Decides which trees render |
| `validator.py` — FK validation (SRS-102) | Excludes invalid records |
| `file_writer.py` — UTF-8/LF, byte-identical writing (SRS-101) | Writes R210 files unchanged |
| `generator.py` — orchestrator and mode dispatch | Gains two live modes |
| `models.py` — `GenerationResult` | Return shape unchanged |

Phase 5 should not need to modify any of them. If it does, that is a signal the
Phase 4 seam was drawn in the wrong place and worth recording as a deviation.

---

## 6. Constraints

**Work-computer confinement.** `docs/WORK_MACHINE_CONFIGURATION.md` requires
that no real work data, completed configuration, generated output, or review
report is committed or transferred outside the work computer. Phase 5 is the
first phase that handles real templates, so this constraint binds it directly:

- Golden files used in tests must contain synthetic data, or must not be
  committed to a repository that leaves the work computer.
- Completed configuration values must not be copied back into the external
  development environment.

**SRS-015 remains blocking for extraction**, though not for generation.
Generation reads the database; it does not call Gemini. A database populated by
manual MCP tool calls can be generated from without SRS-015 approval.

---

## 7. Definition of Done

1. `r210/` implemented: renderer, four templates, metamodel mapping.
2. All three generation modes operative; `trigger_generation` fully delegating.
3. Generated files match the approved work templates byte-for-byte where
   determinism is required (`WORK_MACHINE_CONFIGURATION.md`).
4. Two runs over an unchanged database produce byte-identical R210 output
   (SRS-101).
5. `pytest`, `ruff check src tests`, `mypy src` all clean.
6. `docs/PHASE5_IMPLEMENTED_REQUIREMENTS.md` written; any deviations recorded.
7. Confirmed that no real work data, configuration or output left the work
   computer.

---

## 8. Risks

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Templates arrive in a form the pluggable architecture does not fit | Rework in `renderer.py`, which Phase 4 delivers | Review one real template against LLD-04 §6.1 **before** starting; treat a mismatch as a design change, not an implementation detail |
| SRS-064's selection rule turns out to depend on data the schema does not capture | Schema migration, touching Phase 1 | Validate the rule against real configurations during entry criterion 4, not during implementation |
| Byte-for-byte determinism fails on incidental differences (line endings, encoding, ordering) | SRS-101 is a hard requirement | `file_writer.py` centralises encoding and line endings in Phase 4; assert byte-identity from the first rendering commit |
| Golden files leak real work data into version control | Breaches the confinement constraint | Use synthetic fixtures for committed tests; keep any real-template comparison out of the repository |

---

## 9. If the Entry Criteria Never Close

SRS-071 and SRS-064 have been TBD since SRS v3.0. If the work-specific values
remain unavailable, the prototype still delivers value without Phase 5: after
Phase 4, extraction, review and the review report all work on synthetic data.
What is missing is only the final R210 artifact.

That is worth stating plainly to stakeholders rather than reporting the
prototype as incomplete: the blocked portion is one rendering subpackage, and
the blockage is a configuration decision, not an engineering one.

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-13 | Initial scope, agreed after the Phase 3 hand-off. |
