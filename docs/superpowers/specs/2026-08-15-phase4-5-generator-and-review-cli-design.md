# Phases 4 and 5 — Review CLI, Generator, R210 Framework (Design)

| Field | Value |
|---|---|
| **Document ID** | R210-SPEC-P45 |
| **Phase** | Phase 4 (complete) + Phase 5 (structural half only) |
| **Date** | 2026-08-15 |
| **Branch** | `feature/phase4-5-generator-and-review-cli` |
| **Source Documents** | R210-LLD-03 v1.3, R210-LLD-04 v1.3, R210-LLD-06 v1.2, R210-SRS-001 v5.4 |
| **Predecessor** | Phase 3 — MCP Tool Surface (`docs/superpowers/specs/2026-08-12-phase3-mcp-tool-surface-design.md`) |
| **Governing scope** | `docs/PHASE4_SCOPE.md`, `docs/PHASE5_SCOPE.md` |

---

## 1. Scope

This phase builds the last two components of the prototype — the Local Review
CLI (LLD-06) and the Deterministic Generator (LLD-04) — plus the Gemini CLI
skill (LLD-03), on a single branch.

It covers **all of Phase 4** and the **structural half of Phase 5**.

### 1.1 Why Phase 5 splits, and where

Phase 5 as scoped cannot be built in this repository copy. Its entry criteria
(`docs/PHASE5_SCOPE.md` §2) are four work-computer values —  R210 output
templates (SRS-019c), naming conventions and output paths (SRS-019d), AUTOSAR
package paths and metamodel identifiers (SRS-019), and the `access_point`
selection rule (SRS-064). `docs/WORK_MACHINE_CONFIGURATION.md` records that
these are *deliberately* absent, and CLAUDE.md's standing constraint forbids
inventing them. `src/r210_generator/r210/templates/type_definition.py` says so
in its own docstring: `TBD: Template content (SRS-019c)`.

The blockage is narrower than the phase, however. LLD-04 §11 states that the
TBDs "do not block the design of the generator's architecture — template
implementations are pluggable," and LLD-04 §6 divides cleanly:

| LLD-04 § | Content | Needs work config? | This phase |
|---|---|---|---|
| §6.1 | Template *interface* | No | **Yes** |
| §6.2 | Rendering pipeline, dispatch | No | **Yes** |
| §6.3 | Artifact ordering | No | **Yes** |
| §6.4 | Child record ordering | No | **Yes** |
| §6.5 | Rejected-child exclusion | No | **Yes** |
| §6.6 | Port connection rendering *body* | Yes (SRS-019c) | Plug-point only |
| §6.7 | AUTOSAR metamodel mapping | Yes (SRS-064) | Plug-point only |

So this phase delivers the renderer framework, fully tested through injected
synthetic templates, and leaves four template bodies plus one mapping table as
declared plug-points. On the work computer, Phase 5 becomes "write one module
and pass it to `GeneratorConfig`", not "build a subsystem".

**This is a scope change to two agreed scope documents and is recorded as a
deviation (DEV-39), not made silently.**

### 1.2 Sub-projects

Six units, ordered so each one's output is human-inspectable before the next
depends on it. The order follows `docs/PHASE4_SCOPE.md` §8.

| # | Sub-project | Package | Depends on |
|---|---|---|---|
| SP1 | Review CLI | `r210_review_cli/` | Phase 3 registry seam |
| SP2 | Loader + validator | `r210_generator/{models,loader,validator}.py` | — |
| SP3 | Report + file writer + `report_only` | `r210_generator/report/`, `r210/file_writer.py` | SP2 |
| SP4 | R210 renderer framework | `r210_generator/r210/` | SP2, SP3 |
| SP5 | Gemini CLI skill | `src/gemini_skill/r210_extraction.md` | SP1–SP4 |
| SP6 | Verify `R210McpServer.run()` | `r210_mcp/server.py` | Independent |

SP1 is first because it makes everything downstream inspectable by a human
rather than by tool calls. SP5 is last so it documents a surface that has
stopped moving — `PHASE4_SCOPE.md` §9's stated mitigation against skill drift.

---

## 2. Architecture

Both new packages sit *above* the finished stack. Nothing in `r210_mcp/` imports
either of them, so the existing layering holds unchanged:

```
r210_mcp/db/{connection,dal}  ←── r210_generator/loader.py
r210_mcp/tools/{registry,context}  ←── r210_review_cli/bridge.py
r210_generator/  ←── r210_review_cli/commands/generate.py
                 ←── r210_mcp/tools/generation.py
```

`r210_mcp` gains exactly two additions and no behaviour change:

| Addition | Module | For | Rationale |
|---|---|---|---|
| `DAL.search_by_name_pattern()` | `db/dal.py` | SP1 `search` | §3.3 |
| `DatabaseConnection.read_snapshot()` | `db/connection.py` | SP2 loader | §4.2 |

### 2.1 The bridge does not import `R210McpServer` (DEV-40)

LLD-06 §5.1 specifies `from r210_mcp.server import R210McpServer`, and §5.2
constructs one. Following that literally imports `server.py` — the only module
in the repository that imports the `mcp` SDK. That has two consequences:

1. It would fail outright in this environment, where the SDK is not installed.
2. It violates **LLD-06 §7 item 2**, the network-isolation guarantee the same
   document states: the CLI must contain "no MCP protocol" and no import of
   "any MCP transport module".

LLD-06 contradicts itself. §7 carries the requirement (SRS-123); §5.1 is a code
sketch written before Phase 3 existed. Phase 3 then created the seam that
resolves it deliberately — handlers are functions over a `ToolContext`
(DEV-26), and `tools/registry.py` exposes `dispatch`, `query_by_table`,
`get_children_for_display` and `get_stats` without touching the SDK.

**The bridge therefore constructs `build_context(db_path, adapter_mode="review")`
and calls `registry.dispatch`.** Every guarantee LLD-06 §5.2 asks for is
preserved: identical validation, identical transactions, identical errors,
approval permitted by `adapter_mode` (SRS-082a), full unprojected records
(SRS-015a does not apply in review mode).

Classified **Correction**.

### 2.2 `ReviewToolBridge` gets its own module (DEV-41)

LLD-06 §3's module list omits `bridge.py` while §5.2 specifies the class. It
goes in `r210_review_cli/bridge.py` rather than inside `cli.py`, so that
argument parsing and tool invocation stay separately testable. Classified
**Gap-fill**.

---

## 3. SP1 — Local Review CLI (LLD-06, SRS-123, SRS-118)

### 3.1 Commands

All **twelve** commands from LLD-06 §4.1. The `cli.py` stub docstring lists
nine; it predates LLD-06 v1.2 and is stale (`PHASE4_SCOPE.md` §5.2). The
docstring is corrected, not treated as specification.

| Command | Bridge call | Validation enforced |
|---|---|---|
| `list <entity_type>` | `query` | read-only |
| `show <unique_key>` | `show` | read-only |
| `search <entity_type> --name` | `search` | read-only |
| `approve <unique_key>` | `set_review_status` | SRS-035b, SRS-046, SRS-053, SRS-092a |
| `reject <unique_key>` | `set_review_status` | SRS-035b, SRS-035c |
| `mark <unique_key> <status>` | `set_review_status` | SRS-035b + both of the above |
| `resolve <issue_key> --resolution` | `update_review_issue` | SRS-035b (issues) |
| `dismiss <issue_key>` | `update_review_issue` | SRS-035b (issues) |
| `reopen <issue_key>` | `update_review_issue` | SRS-035b (issues) |
| `report [--output]` | `generate("report_only")` | SRS-104 |
| `generate [--mode] [--output]` | `generate(mode)` | SRS-090 |
| `stats` | `stats` | read-only |

Entity aliases per LLD-06 §4.2: `sources`/`src`, `types`/`td`, `interfaces`/`pi`,
`prototypes`/`pp`, `connections`/`pc`, `issues`/`ri`. The alias map is a single
dict in `commands/query.py`; it does not restate table names that
`models.ARTIFACT_TABLES` already owns.

`--db` defaults to `r210.db`, per LLD-06 §4.3.

### 3.2 Exit codes

Not specified by LLD-06. Defined here (DEV-42, Gap-fill):

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Tool returned an error, or generation reported failure |
| 2 | Usage error (argparse default) |

### 3.3 `search --name` adds a DAL method (DEV-43)

`PHASE4_SCOPE.md` §5.1 leaves this open: LLD-06 §4.2 specifies pattern search,
but the DAL only does exact equality.

**Decision: add `DAL.search_by_name_pattern(conn, table, pattern)`.** It follows
`find_duplicates_by_name` exactly — table resolved through `DAL_TABLES`, `name`
column presence checked against `TABLE_COLUMNS`, pattern bound as a `?`
parameter, `LIKE ? COLLATE NOCASE`, ordered by `_order_by(table)`. The
identifier allowlist is untouched.

Rejected alternative: filter client-side over `query_by_table`. It avoids
touching a completed layer, but loads whole tables into the CLI to discard most
rows, and puts a second, divergent notion of "matching" outside the DAL. The
`find_duplicates_by_name` precedent settles which way this project goes.

Classified **Gap-fill**. Risk noted in `PHASE4_SCOPE.md` §9 ("reopens the
completed DAL") is bounded: one additive method, no change to existing SQL.

### 3.4 Display (`display.py`)

`DisplayFormatter` with `format_list`, `format_detail`, `format_stats`,
`format_result`, producing LLD-06 §6.2's three formats verbatim. §6.2 is
treated as the specification, per `PHASE4_SCOPE.md` §9's scope-creep mitigation.

**ANSI colour is gated on `sys.stdout.isatty()` (DEV-44, Refinement).** LLD-06
§6.1 defines `STATUS_COLORS` but not when to apply them. Emitting escape
sequences into a redirected file or a pipe would corrupt it, so colour is
emitted only to a terminal; the `■` status glyph and all text are identical
either way. This also keeps CLI output testable by comparing plain strings.

### 3.5 Network isolation (SRS-123) — adversarial

LLD-06 §7 asks for a code review. `PHASE4_SCOPE.md` §7 requires this be written
adversarially instead. Two independent tests:

1. **Static.** AST-walk every `.py` under `src/r210_review_cli/`, collect every
   `Import` and `ImportFrom` target, assert none is or starts with
   `google.generativeai`, `google.genai`, `requests`, `httpx`, `urllib`,
   `aiohttp`, `websockets`, `socket`, `http`, or `mcp`.
2. **Dynamic.** In a subprocess, import `r210_review_cli.cli` and assert `mcp`
   and `socket` are absent from `sys.modules` afterwards — catching a
   transitive import the static scan would miss.

---

## 4. SP2 — Loader and validator (LLD-04 §4, §5, §9)

### 4.1 `models.py`

Per LLD-04 §9.1 and §10: `DatabaseSnapshot` (frozen, the 15 record lists),
`ExportableSet`, `ValidatedSet`, `ValidationWarning`, `ValidationError`,
`ExportedArtifact`, `R210File`, `GenerationResult`, and `GeneratorConfig`.

`GeneratorConfig` is the single carrier of everything the work computer
supplies:

```python
@dataclass(frozen=True)
class GeneratorConfig:
    output_dir: str
    templates: TemplateSet = UNCONFIGURED_TEMPLATES      # SRS-019c
    naming: NamingPolicy = UNCONFIGURED_NAMING           # SRS-019d
    access_points: AccessPointPolicy = UNCONFIGURED_ACCESS_POINTS  # SRS-064
    generated_at: str | None = None                      # §5.2
```

### 4.2 `loader.py` uses the existing layers (DEV-45)

LLD-04 §9.2 shows the loader opening a raw `sqlite3.connect`, setting pragmas
itself, and issuing `BEGIN`. That would put a fourth copy of the connection
setup in the repository and a second place that writes SQL, both against the
architecture CLAUDE.md records ("`dal.py` (all SQL)", "transaction control lives
only in `connection.py`", DEV-03).

**The loader calls `DatabaseConnection.read_snapshot()` and `DAL.query_table()`
per table. It contains no SQL.** `read_snapshot()` is added to
`connection.py` — a context manager issuing `BEGIN` (deferred, not `IMMEDIATE`:
this is a reader and must not take a write lock) and always `ROLLBACK`. Putting
the `BEGIN` there rather than in the generator is what preserves DEV-03.

Classified **Correction**.

**Ordering.** LLD-04 §9.2 wants `TypeDefinitions` ordered
`kind, name COLLATE NOCASE, id`; the DAL orders by `id`. The loader applies the
LLD's ordering in Python after loading, rather than adding a second ordering
path to a finished layer. Sorting in Python is equally deterministic and the
snapshot is already fully in memory. Recorded as part of DEV-45.

### 4.3 `validator.py`

Two pure functions over a snapshot — no I/O, no database:

- `evaluate_exportable_trees(snapshot) -> ExportableSet`, per LLD-04 §4.2,
  including §4.3's recursive `client_server` case: interface → operations →
  arguments, where a non-approved argument fails its operation and the
  operation fails the interface.
- `validate_fk_completeness(exportable, snapshot) -> ValidatedSet`, per §5.1's
  six-row table — the four SRS-036a nullable references plus
  `PortPrototypes.port_interface_id` and
  `PortConnectionMembers.port_prototype_id` — checking both non-NULL and target
  existence.

Purity is the point: both are exhaustively testable against a constructed
snapshot without a database, and Phase 5's rendering reuses them unchanged
(`PHASE5_SCOPE.md` §5).

---

## 5. SP3 — Review report and file writer (LLD-04 §7, §8)

### 5.1 Sections

`report/sections.py` builds nine section renderers; `report/builder.py`
assembles them in LLD-04 §7.1's fixed order — (a) approved & generated,
(a2) FK validation errors, (b) approved but excluded, (c) pending review,
(d) ambiguous, (e) rejected, (f) out of scope, (g) pending issues grouped by
`issue_type`, (h) decision log. Section (g)'s grouping order is §7.5's fixed
five: `incomplete`, `unresolved_reference`, `ambiguous`, `unsupported`,
`out_of_scope`; within a group, sorted by `source_reference` then `id`.

Artifact and issue rows carry the fields §7.3 and §7.4 list.

`generator.py` follows §3.3's pipeline exactly, with the consequence §3.3 calls
out explicitly: tree evaluation runs **before** the mode check, so `report_only`
still populates section (b).

### 5.2 Report determinism (SRS-101) — the timestamp (DEV-46)

`PHASE4_SCOPE.md` §5.4 requires this be decided here.

**Decision: inject it.** `GeneratorConfig.generated_at: str | None = None`. When
`None`, the report omits the generation-timestamp line entirely; when set, the
line is rendered verbatim from the injected string. The CLI passes
`datetime.now(timezone.utc).isoformat()`. Tests pass a fixed string, or `None`.

This satisfies SRS-101 as written — byte-identical output for the same database
content, generator version **and work configuration** — because the injected
timestamp is part of that configuration. Nothing else in the report varies with
wall-clock time, locale, or dict iteration order: every list is explicitly
sorted, and the file writer fixes encoding and line endings.

Rejected alternative: exclude the timestamp from the comparison. It makes the
determinism test weaker than the requirement, and leaves a live source of
nondeterminism in the product to protect the test from.

**The determinism test asserts byte-identity of the written files** — reading
both back as `bytes` — not equality of Python strings. Encoding and line-ending
bugs are exactly what a string comparison hides.

### 5.3 `file_writer.py`

Per LLD-04 §8.2: UTF-8 without BOM, `\r\n`/`\r` normalised to `\n`, exactly one
trailing newline, `newline=''` so Python adds no platform translation, parent
directories created before writing.

It stays at `r210/file_writer.py` despite being shared by both outputs, per
`PHASE4_SCOPE.md` §5.3 — moving it would churn a module Phase 5 depends on for
no functional gain.

### 5.4 `trigger_generation` (SRS-090)

`tools/generation.py` currently validates `mode` and returns a structured "not
yet implemented" error (DEV-31). It now delegates to `Generator`. See §6.3 for
what `r210_only` and `both` do.

---

## 6. SP4 — R210 renderer framework (LLD-04 §6.1–6.5)

### 6.1 `TemplateSet` (DEV-47)

The eight render functions LLD-04 §6.1 and §6.6 specify, carried as a frozen
dataclass of callables rather than resolved by module import:

```python
@dataclass(frozen=True)
class TemplateSet:
    simple_typedef:  Callable[..., str]
    array_type:      Callable[..., str]
    struct_type:     Callable[..., str]
    enum_type:       Callable[..., str]
    sender_receiver: Callable[..., str]
    client_server:   Callable[..., str]
    port_prototype:  Callable[..., str]
    port_connection: Callable[..., str]

UNCONFIGURED_TEMPLATES = TemplateSet(*[_raise_unconfigured] * 8)
```

`_raise_unconfigured` raises `TemplateNotConfigured`, whose message names the
missing criterion (SRS-019c) and points at
`docs/WORK_MACHINE_CONFIGURATION.md`.

`NamingPolicy` (SRS-019d, output paths) and `AccessPointPolicy` (SRS-064,
`access_point` → `DataReadAccess`/`DataWriteAccess`/`ServerCallPoint`) follow
the identical pattern with identical error semantics.

The four template modules under `r210/templates/` keep the names LLD-04 §2 gives
them and the signatures §6.1 specifies. Their bodies delegate to the
unconfigured raisers, and their docstrings state precisely what the work
computer must supply.

**Why injection rather than module-level stubs.** The framework must be
*testable* — §6.2's dispatch, §6.3's ordering, §6.4's child ordering, §6.5's
exclusion, and SRS-101's byte-determinism are all real logic that has nothing to
do with template content. Injecting a synthetic `TemplateSet` exercises every
one of them end to end. Module-level stubs would leave that logic reachable only
through monkeypatching, and would make installing the work templates an edit to
committed source rather than a configuration value.

Classified **Refinement** of LLD-04 §6.1, whose stated intent it serves —
"template implementations are pluggable" (§11).

### 6.2 Renderer

`renderer.py` implements §6.2's pipeline and the three ordering/exclusion rules:

- **§6.3 artifact ordering** — the eight-row sort-key table, secondary sort on
  the sort *field*, which is `name` for seven types and `description` for
  `PortConnections` (which has no `name` column). Nullable, so
  `(a.sort_field or "").lower()` per LLD-04 v1.2's H-06 fix. Tertiary `id`.
- **§6.4 child ordering** — `(position, id)`.
- **§6.5 rejected-child exclusion** — omitted from rendered output.

### 6.3 Generation modes with templates unconfigured (closes DEV-31)

`r210_only` and `both` become structurally live: the pipeline runs, trees are
evaluated, FKs validated, artifacts sorted, and rendering is attempted. With an
unconfigured `TemplateSet`, `TemplateNotConfigured` is caught at the generator
boundary and returned as a `GenerationResult` error naming **the unmet Phase 5
entry criteria** (`PHASE5_SCOPE.md` §2 rows 1–4), not a bare "not implemented".

This is a strictly better failure than DEV-31's: it tells the operator what is
missing and where it is recorded. DEV-31 is **amended, not closed** — it closes
when real templates are installed on the work computer.

---

## 7. SP5 — Gemini CLI skill (LLD-03)

`src/gemini_skill/r210_extraction.md`, currently 54 self-declared stub lines,
written out against LLD-03 §4.0–§11: the synthetic-mode gate (§4.0), seven
behavioural rules (§4.1–4.7), the classification decision tree (§5), nine
extraction procedures (§6.1–6.9), issue recording (§7), dependency-ordered
processing (§8), error handling (§9), the 35-tool quick reference (§10), and the
data-boundary statement (§11).

**Written against the implemented surface, not LLD-03's sketch.** Two Phase 3
outcomes change what the skill may rely on, and §10/§11 are cross-checked
against `TOOL_HANDLERS` rather than the document:

- `set_review_status` treats `table_hint` as optional (DEV-35).
- An extraction-mode create or update returns **only** `unique_key`, warnings
  and demoted keys — no record fields (DEV-38). A procedure that reads `name` or
  `status` back from a create response does not work.

§4.0's synthetic-mode gate is stated as binding: SRS-015 is unapproved, so the
skill may not be exercised against real requirement text regardless of what else
is finished.

---

## 8. SP6 — Verify `R210McpServer.run()` (conditional)

`run()` has never been executed; the `mcp` SDK is not installed here, and it
carries `# pragma: no cover`.

**This deliverable is conditional on `pip install mcp` succeeding in this
environment.** If it does: install, run `python -m r210_mcp <db> --mode
extraction`, confirm a client can list and call tools, and correct `run()` if
the SDK API differs from the current sketch.

If it does not — no network, or an incompatible SDK — the path stays unverified
and is **reported as unverified**. `PHASE4_SCOPE.md` §7 item 6 is then not met,
and the phase record says so rather than claiming otherwise.

---

## 9. Testing

`tests/test_r210_generator/` and `tests/test_r210_review_cli/`, mirroring `src/`
per the repository's conventions: `class Test*` groups, the verified `SRS-nnn` in
each test docstring, real migrated SQLite databases rather than mocks.

Development-level, as agreed for Phases 2 and 3, with the two exceptions
`PHASE4_SCOPE.md` §7 carries forward from the Phase 3 precedent, written
adversarially:

| Area | Standard | Why |
|---|---|---|
| CLI network isolation (SRS-123) | Adversarial — §3.5's two tests | A missed transitive import defeats the guarantee silently |
| Report determinism (SRS-101) | Adversarial — byte comparison of written files | A string comparison hides encoding and line-ending bugs |
| R210 render determinism (SRS-101) | Byte comparison, synthetic `TemplateSet` | Establishes the framework before real templates exist |
| Everything else | Development-level | Layer works, boundaries hold |

Gates unchanged and all three must be clean: `python -m pytest tests/ -q -p
no:cacheprovider`, `python -m ruff check src tests`, `python -m mypy src`
(strict).

---

## 10. Deviations Recorded

Continuing from DEV-38. Every one is entered in
`docs/DEVIATIONS_FROM_REQUIREMENTS.md` with what the documents say, what the
code does, and why.

| ID | Subject | Class | §here |
|---|---|---|---|
| DEV-39 | Phase 5 split: framework built, template bodies deferred | Refinement | §1.1 |
| DEV-40 | Bridge targets `tools/registry`, not `R210McpServer` | Correction | §2.1 |
| DEV-41 | `ReviewToolBridge` in `bridge.py` | Gap-fill | §2.2 |
| DEV-42 | CLI exit codes defined | Gap-fill | §3.2 |
| DEV-43 | `DAL.search_by_name_pattern()` added | Gap-fill | §3.3 |
| DEV-44 | ANSI colour gated on `isatty()` | Refinement | §3.4 |
| DEV-45 | Loader uses `connection.py`/`dal.py`, not raw `sqlite3`; sorts in Python | Correction | §4.2 |
| DEV-46 | Report timestamp injected via `generated_at` | Gap-fill | §5.2 |
| DEV-47 | Templates injected as `TemplateSet`, not resolved by import | Refinement | §6.1 |

`docs/DEVIATIONS_FROM_REQUIREMENTS.md` DEV-31 (`trigger_generation`
unavailability) is amended, not closed — see §6.3.

---

## 11. Definition of Done

From `PHASE4_SCOPE.md` §7, with §1.1's Phase 5 addition and §8's condition:

1. SP1–SP5 implemented. SP6 done **or** explicitly reported unverified.
2. `pytest`, `ruff check src tests`, `mypy src` (strict) all clean.
3. `r210-review` runs end to end on a synthetic database: create records through
   the MCP tools, `list`, `show`, `approve` one, `resolve` an issue, `report`.
4. Report generation byte-identical across two runs over an unchanged database.
5. R210 rendering byte-identical across two runs with an injected synthetic
   `TemplateSet`.
6. `docs/PHASE4_IMPLEMENTED_REQUIREMENTS.md` written; a partial
   `docs/PHASE5_IMPLEMENTED_REQUIREMENTS.md` written, stating plainly which
   Phase 5 rows remain open and why.
7. DEV-39…DEV-47 recorded; DEV-31 amended.
8. `docs/REMAINING_WORK.md` updated; `docs/PHASE5_SCOPE.md` §3.1 annotated to
   show what this phase already delivered.

### 11.1 What remains blocked after this phase

Stated plainly, per `PHASE5_SCOPE.md` §9. After this branch lands, the only
missing engineering is four template bodies and one mapping table. Everything
else — extraction, review, the review report, and the whole generation pipeline
— works on synthetic data. The residue is a configuration decision, not an
engineering one.

---

## Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-15 | Initial design, agreed after the Phase 3 merge. Phase 5 boundary, template plug-point mechanism, and the six-sub-project decomposition approved by the project owner; remaining decisions delegated and recorded here as DEV-39…DEV-47. |
