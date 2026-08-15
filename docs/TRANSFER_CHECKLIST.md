# Transfer Checklist — External Development Machine → Work Computer

## R210 AUTOSAR Requirements Automation Prototype

| Field | Value |
|---|---|
| **Document ID** | R210-XFER-01 |
| **Date** | 2026-08-15 |
| **Companion** | `docs/WORK_MACHINE_CONFIGURATION.md` (what to do *after* transfer) |
| **Status** | Prepared on the external machine; §3 is executed on the work computer |

---

## 1. Purpose

`docs/WORK_MACHINE_CONFIGURATION.md` lists what must be **completed on the work
computer**. This document covers the step before it: what must be true of the
repository **before** it leaves this machine, and what will be hard to obtain
once it has.

The two constraints that shape it:

- **This copy contains no real work data**, and must not acquire any. The flow
  is one-way — nothing generated on the work computer comes back.
- **The work computer's network access is unknown.** Anything requiring a
  package index should be resolved here, where the index is reachable.

---

## 2. Before Transfer — on this machine

### 2.1 Verified state

Recorded 2026-08-15 on `master` at the Phase 4 merge (`6386cab`):

| Check | Result |
|---|---|
| `python -m pytest tests/ -q -p no:cacheprovider` | 871 passing |
| `python -m ruff check src tests` | clean |
| `python -m mypy src` | clean (strict) |
| `r210-review` end to end on synthetic data | verified — `PHASE4_IMPLEMENTED_REQUIREMENTS.md` §4 |
| `python -m r210_mcp` over stdio with a real client | verified — `PHASE4_IMPLEMENTED_REQUIREMENTS.md` §5 |

**The transfer itself was rehearsed**, because a checklist that has never been
executed is a guess:

| Rehearsal | Result |
|---|---|
| `git clone` into a clean directory, then run the suite and both gates | full suite passing, gates clean — nothing depends on untracked local state |
| A virtualenv with **no `mcp` SDK** | 863 passing, 1 skipped — only the stdio-adapter module |
| `r210-review stats` and `report` with no SDK | exit 0, report written |
| `python -m r210_mcp` with no SDK | exits 1 with an actionable message, not a traceback (DEV-51) |

That last row was a defect found by the rehearsal: the server used to die with
a bare `ModuleNotFoundError: No module named 'anyio'`, which names a transitive
dependency and tells the operator neither what to install nor that the review
CLI and generator work regardless.

### 2.2 Confinement: generated output cannot be committed

`.gitignore` covers the review CLI's `DEFAULT_OUTPUT_DIR` (`r210_output/`),
`GeneratorConfig.report_filename` (`review_report.md`), `*.arxml`, and every
SQLite extension. `tests/test_confinement.py` ties those patterns to the code
constants, so they cannot drift apart silently.

**This was a real gap.** `.gitignore` listed `output/` while the CLI wrote to
`r210_output/`; on the work computer a plain `git add -A` after a default
`r210-review report` would have staged a review report containing real
requirement text.

### 2.3 Dependency versions, pinned here

`pyproject.toml` declares floors, not pins. The versions below are the ones the
846-test suite and the stdio verification actually ran against, on **Python
3.13.2**. Use them if the work computer's resolver produces something different
and something misbehaves.

```
# Runtime
mcp==2.0.0
mcp-types==2.0.0
anyio==4.14.2
pydantic==2.13.4
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
referencing==0.37.0
rpds-py==2026.6.3
starlette==1.6.0
sse-starlette==3.4.8
uvicorn==0.52.3
h11==0.16.0
click==8.4.2
idna==3.18
attrs==25.4.0
certifi==2025.1.31
python-multipart==0.0.32
PyJWT==2.13.0
cryptography==50.0.0
cffi==2.1.1
pycparser==3.0
truststore==0.10.4
opentelemetry-api==1.44.0
typing-inspection==0.4.4

# Development
pytest==9.0.2
ruff==0.16.2
mypy==2.3.0
iniconfig==2.3.0
packaging==24.2
pathspec==1.1.1
pluggy==1.6.0
```

**If the work computer has no package index**, download wheels here first:

```bash
python -m pip download "mcp==2.0.0" pytest ruff mypy -d wheelhouse/
# transfer wheelhouse/ alongside the repository, then on the work computer:
python -m pip install --no-index --find-links wheelhouse/ mcp pytest ruff mypy
```

Do **not** commit `wheelhouse/` — transfer it as a separate directory.

### 2.4 The `mcp` version question

`pyproject.toml` requires `mcp>=2.0`. This is deliberate and it is a constraint,
not a preference: LLD-02 §9's registration call
(`server.call_tool(name)(handler)`) does not exist in `mcp` 2.x, and the
rewritten `run()` calls an API that does not exist in 1.x (DEV-50). The two are
not interchangeable.

**Check what the work computer can install before relying on the MCP server.**
If only 1.x is available there, `R210McpServer.build_server()` needs a
compatibility branch. Everything else — the review CLI, the generator, the whole
tool surface via `handle_tool` — works with no SDK at all.

### 2.5 Housekeeping

- 33 `.pytest_tmp_*` directories exist in the repository root from earlier runs.
  They are untracked and unreadable by git (permission denied). A `git clone`
  will not carry them; a folder copy will. Prefer cloning, or delete them first.
- Confirm `git status` is clean and the branch is pushed before copying.

---

## 3. After Transfer — on the work computer

Work through `docs/WORK_MACHINE_CONFIGURATION.md`. In dependency order:

1. **Re-run the gates** to confirm the environment: `pytest`, `ruff`, `mypy`.
   All three should pass before any work-specific value is added. If they do
   not, the problem is the environment, not the code.
2. **Close the four Phase 5 entry criteria** (`docs/PHASE5_SCOPE.md` §2):
   templates (SRS-019c), naming and paths (SRS-019d), AUTOSAR package paths
   (SRS-019), the `access_point` rule (SRS-064).
3. **Write one configuration module** returning a populated `TemplateSet`,
   `NamingPolicy` and `AccessPointPolicy` — signatures in
   `docs/PHASE5_IMPLEMENTED_REQUIREMENTS.md` §4.1. No framework change should be
   needed; if one is, record it as a deviation.
4. **Verify byte-identity** against the approved templates, and across two runs
   over an unchanged database (SRS-101).
5. **Obtain the SRS-015 decision** before any real requirement text reaches
   Gemini. Until then the system stays synthetic-data-only *even on the work
   computer*, and the launcher's `approved_for_real_data` preflight enforces it.
6. **Confirm nothing goes back.** Re-read `WORK_MACHINE_CONFIGURATION.md`'s last
   verification item before any push, and note that `git push` from the work
   computer to this repository's origin is exactly the action the constraint
   forbids.

---

## 4. What Cannot Be Prepared Here

Stated so nobody looks for it:

| Item | Why |
|---|---|
| R210 output templates | SRS-019(c) — work-specific, deliberately absent |
| Naming conventions, output paths | SRS-019(d) |
| AUTOSAR package paths, version identifiers | SRS-019 |
| `access_point` selection rule | SRS-064 — needs validation against real configurations |
| Interface compatibility rules | SRS-071 — TBD since SRS v3.0; SRS-125 fallback stands |
| Golden files from real templates | Would breach the confinement constraint |

---

## Revision History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-15 | Written after Phase 4 completion, in preparation for transfer. Records the `.gitignore` confinement gap found and fixed, the pinned dependency set the suite was verified against, and the `mcp` 2.x constraint. |
