# Phase 5 — Implemented Requirements (Partial)

## R210 AUTOSAR Requirements Automation Prototype

| Field | Value |
|---|---|
| **Document ID** | R210-IMP-05 |
| **Phase** | Phase 5 — R210 file generation |
| **Date** | 2026-08-15 |
| **Branch** | `feature/phase4-5-generator-and-review-cli` |
| **Source Documents** | R210-SRS-001 v5.4, R210-LLD-04 v1.3 §6 |
| **Scope** | `docs/PHASE5_SCOPE.md` |
| **Status** | **Partial — framework complete, template content outstanding** |

---

## 1. What This Document Records

`docs/PHASE5_SCOPE.md` treats Phase 5 as one blocked unit. It is not: LLD-04 §6
divides into structural rules that need no work configuration, and template
content that cannot be written without it.

This phase delivered the first half. The second half is **not** delivered and
this document does not claim otherwise. See DEV-39.

| LLD-04 § | Content | Needs work config? | Delivered |
|---|---|---|---|
| §6.1 | Template *interface* | No | **Yes** |
| §6.2 | Rendering pipeline, dispatch | No | **Yes** |
| §6.3 | Artifact ordering | No | **Yes** |
| §6.4 | Child record ordering | No | **Yes** |
| §6.5 | Rejected-child exclusion | No | **Yes** |
| §6.6 | Port connection rendering *body* | Yes — SRS-019(c) | **No** — plug-point |
| §6.7 | AUTOSAR metamodel mapping | Yes — SRS-064 | **No** — plug-point |

---

## 2. Requirements Status

| SRS | Requirement | Status | Note |
|---|---|---|---|
| SRS-103 | Generate R210 files for supported artifact types | **Open** | Pipeline complete; template bodies absent |
| SRS-101 | Byte-identical R210 output | **Partial** | Verified with an injected synthetic `TemplateSet`. Real-template verification belongs to the work computer |
| SRS-064 | `access_point` / `trigger` metamodel mapping | **Open** | `trigger` → `ExternalTriggeringPoint` is fixed and encoded; `access_point` needs the selection rule |
| SRS-073 | Port connection rendering | **Partial** | Structure enforced — one global multi-port render call, no pairwise expansion, asserted by test. Content absent |
| SRS-090 | All three generation modes operative | **Partial** | All three run. `report_only` produces output; `r210_only` and `both` report unmet entry criteria |
| SRS-116 | Single output format per SRS-019 | **Open** | Depends on SRS-019 |
| SRS-092a, SRS-108 | Exclusion and ordering applied to R210 output | **Met** | Structural; verified with synthetic templates |

---

## 3. What Was Built

### 3.1 The plug-point contract

`src/r210_generator/r210/templates/__init__.py` declares three frozen policies,
each defaulting to an unconfigured form that raises `TemplateNotConfigured`
naming the SRS it needs:

| Policy | Supplies | Criterion |
|---|---|---|
| `TemplateSet` | Eight render callables | SRS-019(c) |
| `NamingPolicy` | Output file path per artifact | SRS-019(d) |
| `AccessPointPolicy` | `access_point` → AUTOSAR element | SRS-064 |

The four template modules stay where LLD-04 §2 puts them, keep §6.1's function
names and signatures, and document exactly what the work computer must supply.

### 3.2 The rendering pipeline

`r210/renderer.py` implements §6.2–§6.5 in full:

- **§6.3** the eight-row artifact sort table, secondary sort on the sort *field*
  (`name`, or `description` for `PortConnections`, which has no `name` column),
  tertiary on `id`. A null sort field does not crash it (LLD-04 v1.2's H-06).
- **§6.4** child ordering by `(position, id)`.
- **§6.5** rejected children never reach a template.
- **§6.6 structure** a connection renders in one call with all members — no
  pairwise provider/requester expansion (SRS-073).

Templates receive children already sorted and already filtered, so no template
can get §6.4 or §6.5 wrong.

### 3.3 Generation modes

All three modes run the pipeline. `r210_only` and `both` check the entry
criteria before rendering and return them by SRS number when unmet — an empty
database calls no template, so catching a raise would have let an unconfigured
run report success (DEV-47).

---

## 4. What Remains — the Work-Computer Task

Phase 5 completion is now one module plus verification.

### 4.1 Write the configuration module

```python
from r210_generator.r210.templates import (
    AccessPointPolicy, NamingPolicy, TemplateSet,
)

WORK_TEMPLATES = TemplateSet(
    simple_typedef=render_simple_typedef,   # SRS-019(c)
    array_type=render_array_type,
    struct_type=render_struct_type,
    enum_type=render_enum_type,
    sender_receiver=render_sender_receiver,
    client_server=render_client_server,
    port_prototype=render_port_prototype,
    port_connection=render_port_connection,
)
WORK_NAMING = NamingPolicy(file_path=...)               # SRS-019(d)
WORK_ACCESS_POINTS = AccessPointPolicy(
    access_point_element=...,                            # SRS-064
)
```

Then pass them to `GeneratorConfig`. **No framework code changes.** If any are
required, `docs/PHASE5_SCOPE.md` §5 says to record it as a deviation — the seam
was drawn in the wrong place.

Each render callable is invoked as
`template(record, children, snapshot, config) -> str`, where `children` is a
list of `(child_table, record)` pairs, ordered and filtered.

### 4.2 Entry criteria still open

From `docs/PHASE5_SCOPE.md` §2, unchanged:

| # | Criterion | SRS | Owner |
|---|---|---|---|
| 1 | R210 output templates installed and approved | SRS-019(c) | Work computer |
| 2 | Naming conventions and output paths defined | SRS-019(d) | Work computer |
| 3 | AUTOSAR package paths and version identifiers | SRS-019 | Work computer |
| 4 | `access_point` selection rule documented | SRS-064 | Development team |
| 5 | Phase 4 complete | — | **Met** — `docs/PHASE4_IMPLEMENTED_REQUIREMENTS.md` |

### 4.3 Verification still required

- Generated files match the approved work templates byte-for-byte.
- Two runs over an unchanged database produce byte-identical R210 output with
  **real** templates. The framework's determinism is already asserted with
  synthetic ones, so a failure here points at a template, not at the pipeline.
- Golden files in committed tests must contain synthetic data only
  (`docs/WORK_MACHINE_CONFIGURATION.md`).

---

## 5. Statement for Stakeholders

`docs/PHASE5_SCOPE.md` §9 asks that this be said plainly rather than reported as
an incomplete prototype:

> After Phase 4 and this framework, extraction, review, the review report and
> the entire generation pipeline all work on synthetic data. What is missing is
> four template bodies and one mapping table. The blockage is a configuration
> decision, not an engineering one — and the engineering that surrounds it is
> now finished and tested rather than waiting behind it.

---

## Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-15 | Initial partial record. Framework half of Phase 5 delivered under DEV-39; template content remains open, with the four entry criteria unchanged. |
