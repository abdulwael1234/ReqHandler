# Low-Level Design — Local Review CLI

## R210 AUTOSAR Requirements Automation Prototype

| Field              | Value                                                    |
|--------------------|----------------------------------------------------------|
| **Document ID**    | R210-LLD-06                                              |
| **Version**        | 1.2                                                      |
| **Date**           | 2026-08-11                                               |
| **Component**      | Local Review CLI                                         |
| **Source Documents**| R210-SRS-001 v5.2, R210-HLD-001 v3.1                   |
| **Status**         | Draft                                                    |

---

## 1. Purpose

This document specifies the internal design of the Local Review CLI — a Python command-line program that allows manual review of extracted artifacts and review issues without connecting to the Gemini API. It invokes the same MCP tool logic as the Gemini CLI skill, ensuring all validation rules are enforced during review, while guaranteeing that review decisions never leave the work computer.

---

## 2. Design Rationale (SRS-123)

The Gemini CLI skill connects to the Gemini API for LLM-driven extraction. During the review phase, no LLM processing is needed — the reviewer is making human decisions about extracted artifacts. The Local Review CLI provides:

1. **No API connection** — review decisions and database queries never leave the work computer.
2. **Same validation** — all MCP tool validation (status transitions, parent-child rules, connection revalidation) is enforced.
3. **Local operation** — runs as a local Python program, not a network-facing service.
4. **Direct tool invocation** — calls the same Python functions that back the MCP tools, without MCP protocol overhead.

---

## 3. Module Structure

```
r210_review_cli/
├── __init__.py
├── cli.py                     # CLI entry point and argument parsing
├── commands/
│   ├── __init__.py
│   ├── query.py               # Query commands (list, show, search)
│   ├── status.py              # Status change commands
│   ├── issues.py              # Review issue management commands
│   └── generate.py            # Trigger generation commands
└── display.py                 # Output formatting for terminal display
```

---

## 4. CLI Entry Point (`cli.py`)

### 4.1 Command Structure

```
r210-review <command> [subcommand] [arguments] [options]

Commands:
  list    <entity_type>                     List artifacts/issues by type
  show    <unique_key>                      Show detailed record
  search  <entity_type> --name <pattern>    Search by name
  approve <unique_key> [--note <text>]      Set status to approved
  reject  <unique_key> [--note <text>]      Set status to rejected
  mark    <unique_key> <status> [--note]    Set any valid status
  resolve <issue_key> --resolution <text>   Resolve a review issue
  dismiss <issue_key>                       Reject a review issue
  reopen  <issue_key>                       Reopen a resolved/rejected issue
  report  [--output <path>]                 Generate review report
  generate [--mode <mode>] [--output <dir>] Trigger R210 generation
  stats                                     Show database statistics
```

### 4.2 Entity Types for `list` and `search`

| Entity Type | Alias | Maps To |
|------------|-------|---------|
| `sources` | `src` | SourceRequirements |
| `types` | `td` | TypeDefinitions (with subtypes) |
| `interfaces` | `pi` | PortInterfaces (with children) |
| `prototypes` | `pp` | PortPrototypes (with functions) |
| `connections` | `pc` | PortConnections (with members) |
| `issues` | `ri` | ReviewIssues |

### 4.3 Entry Point Implementation

```python
"""
Local Review CLI — manual review without Gemini API connection.

Usage:
    python -m r210_review_cli <command> [args]

This CLI invokes the same validation logic as the MCP server
but runs locally without any network connection (SRS-123).
"""

import argparse
import sys
from .commands import query, status, issues, generate

def main():
    parser = argparse.ArgumentParser(
        description="R210 Local Review CLI — review artifacts without Gemini API"
    )
    parser.add_argument("--db", default="r210.db",
                        help="Path to SQLite database file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── List command ───────────────────────────────────────
    list_parser = subparsers.add_parser("list", help="List artifacts by type")
    list_parser.add_argument("entity_type", choices=[
        "sources", "src", "types", "td", "interfaces", "pi",
        "prototypes", "pp", "connections", "pc", "issues", "ri",
    ])
    list_parser.add_argument("--status", help="Filter by status")
    list_parser.add_argument("--kind", help="Filter by kind (types only)")
    list_parser.add_argument("--issue-type", help="Filter by issue_type (issues only)")

    # ── Show command ───────────────────────────────────────
    show_parser = subparsers.add_parser("show", help="Show record details")
    show_parser.add_argument("unique_key", help="UUID of the record")

    # ── Search command ─────────────────────────────────────
    search_parser = subparsers.add_parser("search", help="Search by name")
    search_parser.add_argument("entity_type")
    search_parser.add_argument("--name", required=True, help="Name pattern to search")

    # ── Approve command ────────────────────────────────────
    approve_parser = subparsers.add_parser("approve", help="Approve an artifact")
    approve_parser.add_argument("unique_key")
    approve_parser.add_argument("--note", help="Review note")

    # ── Reject command ─────────────────────────────────────
    reject_parser = subparsers.add_parser("reject", help="Reject an artifact")
    reject_parser.add_argument("unique_key")
    reject_parser.add_argument("--note", help="Review note")

    # ── Mark command ───────────────────────────────────────
    mark_parser = subparsers.add_parser("mark", help="Set artifact status")
    mark_parser.add_argument("unique_key")
    mark_parser.add_argument("status", choices=[
        "pending_review", "approved", "rejected", "ambiguous", "out_of_scope"
    ])
    mark_parser.add_argument("--note", help="Review note")

    # ── Resolve command ────────────────────────────────────
    resolve_parser = subparsers.add_parser("resolve", help="Resolve a review issue")
    resolve_parser.add_argument("unique_key")
    resolve_parser.add_argument("--resolution", required=True, help="Resolution text")

    # ── Dismiss command ────────────────────────────────────
    dismiss_parser = subparsers.add_parser("dismiss", help="Reject a review issue")
    dismiss_parser.add_argument("unique_key")

    # ── Reopen command ─────────────────────────────────────
    reopen_parser = subparsers.add_parser("reopen", help="Reopen an issue")
    reopen_parser.add_argument("unique_key")

    # ── Report command ─────────────────────────────────────
    report_parser = subparsers.add_parser("report", help="Generate review report")
    report_parser.add_argument("--output", help="Output file path")

    # ── Generate command ───────────────────────────────────
    gen_parser = subparsers.add_parser("generate", help="Trigger R210 generation")
    gen_parser.add_argument("--mode", choices=["r210_only", "report_only", "both"],
                            default="both")
    gen_parser.add_argument("--output", help="Output directory")

    # ── Stats command ──────────────────────────────────────
    subparsers.add_parser("stats", help="Show database statistics")

    args = parser.parse_args()
    # Dispatch to command handler...
```

---

## 5. Tool Invocation Layer

**SRS-123 requirement:** "This CLI shall invoke the **same MCP tools** as the Gemini CLI skill."

The review CLI calls the MCP tool handler functions directly — the same Python functions that the MCP server dispatches to when it receives a tool call over stdio. This guarantees identical validation, transaction management, and error behavior. The CLI bypasses only the MCP protocol transport layer (serialization, stdio I/O), not the tool logic.

### 5.1 Shared Code Reuse

```python
# The review CLI imports the MCP server's tool handler class directly:
from r210_mcp.server import R210McpServer

# It also imports the DB connection for read-only queries:
from r210_mcp.db.connection import DatabaseConnection
```

### 5.2 Review Tool Bridge

```python
class ReviewToolBridge:
    """Invokes MCP tool handler functions directly without MCP protocol transport.

    This bridge calls the SAME handler functions registered in R210McpServer
    (LLD-02 §9), ensuring identical validation, transactions, and error behavior.
    The server is constructed with adapter_mode="review" (LLD-02 §9), so
    approval transitions are structurally permitted (SRS-082a) and query
    results return full records (no Gemini projection).

    It does NOT provide:
    - Create operations (extraction is done by Gemini, not the reviewer)
    - Delete operations (never exposed — SRS-091)
    """

    def __init__(self, db_path: str):
        self._server = R210McpServer(db_path, adapter_mode="review")

    def set_review_status(self, unique_key: str, new_status: str,
                           table_hint: str = None,
                           review_note: str = None) -> dict:
        """Delegate to the MCP server's set_review_status handler.

        The server's adapter_mode="review" structurally permits approval
        (SRS-082a). table_hint is passed through when the caller knows the
        table; when omitted, the server resolves by unique_key scan.
        """
        args = {
            "unique_key": unique_key,
            "new_status": new_status,
            "caller": "review",
        }
        if table_hint is not None:
            args["table_hint"] = table_hint
        if review_note is not None:
            args["review_note"] = review_note
        return self._server.handle_tool("set_review_status", args)

    def update_review_issue(self, unique_key: str,
                             status: str = None,
                             resolution: str = None) -> dict:
        """Delegate to the MCP server's update_review_issue handler."""
        args = {"unique_key": unique_key}
        if status is not None:
            args["status"] = status
        if resolution is not None:
            args["resolution"] = resolution
        return self._server.handle_tool("update_review_issue", args)

    def query(self, table: str, filters: dict = None) -> list[dict]:
        """Query records using the MCP server's public tool interface.

        Returns FULL records (no Gemini projection) because the server
        was constructed with adapter_mode="review" (SRS-123).
        """
        tool_map = {
            "SourceRequirements": "query_source_requirements",
            "TypeDefinitions": "query_type_definitions",
            "PortInterfaces": "query_port_interfaces",
            "PortPrototypes": "query_port_prototypes",
            "PortConnections": "query_port_connections",
            "ReviewIssues": "query_review_issues",
        }
        tool_name = tool_map.get(table)
        if tool_name:
            return self._server.handle_tool(tool_name, filters or {})
        # For child tables without dedicated query tools, use the
        # server's query_by_table public helper
        return self._server.query_by_table(table, filters or {})

    def show(self, unique_key: str) -> dict:
        """Delegate to the MCP server's resolve_reference tool for lookup,
        then load children for display."""
        result = self._server.handle_tool(
            "resolve_reference", {"unique_key": unique_key}
        )
        if "error" in result:
            return result
        # resolve_reference returns full record; load children for display
        table = result.get("table")
        children = self._server.get_children_for_display(
            table, result.get("record", {})
        )
        result["children"] = children
        return result

    def stats(self) -> dict:
        """Return database statistics: counts by table and status.

        Uses the MCP server's public stats() method which queries tables
        with and without status columns.
        """
        return self._server.get_stats()
```

---

## 6. Display Formatting (`display.py`)

### 6.1 Record Display

```python
class DisplayFormatter:
    """Format database records for terminal output."""

    STATUS_COLORS = {
        "pending_review": "yellow",
        "approved": "green",
        "rejected": "red",
        "ambiguous": "magenta",
        "out_of_scope": "cyan",
        "pending": "yellow",
        "resolved": "green",
    }

    def format_list(self, records: list[dict], table: str) -> str:
        """Format a list of records as a table."""
        # Table headers vary by entity type
        # Use compact columnar format with status coloring

    def format_detail(self, record: dict, children: list[dict]) -> str:
        """Format a single record with its children."""
        # Full field display with children nested underneath

    def format_stats(self, stats: dict) -> str:
        """Format database statistics as a summary table."""

    def format_result(self, result: dict) -> str:
        """Format a command result (status change, etc.)."""
```

### 6.2 Example Output Formats

**List output:**
```
Type Definitions (5 records, filtered: kind=struct)
──────────────────────────────────────────────────────────────
UUID                                   Name                Status
a1b2c3d4-...                          SensorData          ■ pending_review
e5f6a7b8-...                          MotorConfig         ■ approved
...
```

**Detail output:**
```
╔══════════════════════════════════════════════════════════════╗
║ Type Definition (struct)                                     ║
╠══════════════════════════════════════════════════════════════╣
  unique_key:           a1b2c3d4-e5f6-4789-abcd-ef0123456789
  name:                 SensorData
  kind:                 struct
  status:               ■ pending_review
  source_reference:     REQ-EXT-042
  description:          Sensor data structure for temperature readings

  Children (StructElements): 3 records
  ──────────────────────────────────────────────────────────
  #  Name            Type              Status
  1  temperature     Float32           ■ approved
  2  timestamp       UInt32            ■ approved
  3  quality         QualityEnum       ■ pending_review
╚══════════════════════════════════════════════════════════════╝
```

**Status change output:**
```
✓ Status changed: a1b2c3d4-... (StructElements)
  Old status: approved
  New status: pending_review
  ⚠ Parent auto-demoted: e5f6a7b8-... (TypeDefinitions) → pending_review
```

---

## 7. Network Isolation Guarantee (SRS-123)

The Local Review CLI guarantees no network communication:

1. **No imports** of Gemini SDK, API clients, or HTTP libraries.
2. **No MCP protocol** — direct Python function calls to the validation/DAL layer.
3. **SQLite only** — all data access is local file I/O.
4. **No external dependencies** at runtime beyond Python stdlib and the MCP server's internal modules.

**Verification:** A code review shall confirm that `r210_review_cli/` contains no import of `google.generativeai`, `requests`, `httpx`, `urllib`, `aiohttp`, `websockets`, or any MCP transport module.

---

## 8. Command Summary with Validation

| Command | Validation Rules Enforced | SRS Reference |
|---------|--------------------------|---------------|
| `approve` | Status transition (SRS-035b); parent-child check — all non-rejected children must be approved (SRS-046, SRS-053, SRS-092a) | SRS-089 |
| `reject` | Status transition (SRS-035b); auto-demotion of approved parent (SRS-035c) | SRS-089 |
| `mark` | Status transition (SRS-035b); parent checks for approve; auto-demotion for non-approve | SRS-089 |
| `resolve` | Issue transition (SRS-035b for issues) | SRS-119 |
| `dismiss` | Issue transition (SRS-035b for issues) | SRS-119 |
| `reopen` | Issue transition (SRS-035b for issues) | SRS-119 |
| `generate` | Delegates to Generator (LLD-04) | SRS-090 |
| `list` / `show` / `search` / `stats` | Read-only — no validation needed | SRS-118 |

---

## 9. Traceability Matrix (LLD-06 → SRS)

| LLD Section | SRS Requirements |
|-------------|-----------------|
| §2 Design Rationale | SRS-123, SRS-015 |
| §4 CLI Entry Point | SRS-118, SRS-123 |
| §5 Tool Invocation | SRS-118, SRS-035b, SRS-035c, SRS-046, SRS-053, SRS-091a, SRS-092a, SRS-122 |
| §6 Display Formatting | SRS-118 (reviewer inspects via query tools) |
| §7 Network Isolation | SRS-123, SRS-015 |
| §8 Command Validation | SRS-089, SRS-119, SRS-090, SRS-035b, SRS-035c, SRS-046, SRS-053, SRS-092a |

---

## Revision History

| Version | Date       | Changes |
|---------|------------|---------|
| 1.0     | 2026-08-10 | Initial LLD derived from SRS v5.0 and HLD v3.0. |
| 1.1     | 2026-08-10 | Post-review amendments: Rewrote §5 tool invocation layer — ReviewToolBridge now delegates to `R210McpServer._handle_*` methods directly instead of reimplementing DAL/validator orchestration (SRS-123). Fixed `stats` to exclude subtype tables without status columns. Always passes `caller="review"` to permit approval (SRS-082a). |
| 1.2     | 2026-08-11 | Review-driven fixes: Replaced all `_handle_*` / `_dal` private-method calls with public interface: `handle_tool()`, `query_by_table()`, `get_children_for_display()`, `get_stats()` (H-04). Added `table_hint` parameter to `set_review_status` (H-03). Server constructed with `adapter_mode="review"` binding authority structurally (C-04). Stats delegated to `server.get_stats()`. Updated source references to SRS v5.2, HLD v3.1. |
