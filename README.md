# R210 AUTOSAR Requirements Automation Prototype

Extracts AUTOSAR artifacts from input requirements using Gemini LLM, stores them
in a validated SQLite database via MCP tools, and generates deterministic R210
requirement files and review reports.

## Components

| Component | Package | LLD | Description |
|-----------|---------|-----|-------------|
| Database Schema | — | LLD-01 | 16-table SQLite schema with FK, CHECK, UNIQUE constraints |
| MCP Server | `r210_mcp` | LLD-02 | 35 MCP tools for CRUD, validation, and status management |
| Gemini CLI Skill | `gemini_skill` | LLD-03 | Markdown skill file instructing Gemini for extraction |
| Deterministic Generator | `r210_generator` | LLD-04 | R210 file and review report generation |
| Database Initializer | `r210_db_init` | LLD-05 | Schema migration framework with version tracking |
| Local Review CLI | `r210_review_cli` | LLD-06 | Offline review tool calling MCP handlers directly |

## Repository Layout

```
R210_Req/
├── Sytem_description/          # Informal system description
├── Srs/                        # Software Requirements Specification (v5.1)
├── archi/                      # High-Level Design (v3.1)
├── lld/                        # Low-Level Design documents (v1.1)
├── src/
│   ├── r210_mcp/               # MCP Server (LLD-02)
│   │   ├── server.py           #   Entry point and tool registration
│   │   ├── db/                 #   Connection, DAL, record models
│   │   ├── validation/         #   Input validation and status rules
│   │   ├── tools/              #   Tool handler modules
│   │   ├── duplicate_detection.py
│   │   └── errors.py
│   ├── r210_generator/         # Deterministic Generator (LLD-04)
│   │   ├── generator.py        #   Main orchestrator
│   │   ├── loader.py           #   Database snapshot loader
│   │   ├── validator.py        #   Tree evaluation and FK validation
│   │   ├── r210/               #   R210 rendering and templates
│   │   ├── report/             #   Review report builder
│   │   └── models.py
│   ├── r210_db_init/           # Database Initializer (LLD-05)
│   │   ├── cli.py              #   init / reset CLI
│   │   ├── initializer.py      #   Migration orchestrator
│   │   └── migrations/         #   Versioned schema migrations
│   ├── r210_review_cli/        # Local Review CLI (LLD-06)
│   │   ├── cli.py              #   Command-line entry point
│   │   ├── commands/           #   Command modules
│   │   └── display.py          #   Terminal output formatting
│   └── gemini_skill/           # Gemini CLI Skill (LLD-03)
│       └── r210_extraction.md  #   Skill file
├── tests/                      # Test suites mirroring src/
├── docs/                       # Additional documentation
├── pyproject.toml              # Project configuration
└── README.md
```

## Quick Start

```bash
# Install in development mode
pip install -e ".[dev]"

# Initialize a new database
r210-init-db init r210.db

# Run extraction (requires Gemini CLI with MCP)
gemini --skill src/gemini_skill/r210_extraction.md

# Review extracted artifacts
r210-review list TypeDefinitions --db r210.db
r210-review show <unique_key> --db r210.db
r210-review approve <unique_key> --note "Verified" --db r210.db

# Run tests
pytest
```

## Design Documents

| Document | Version | Path |
|----------|---------|------|
| System Description | — | `Sytem_description/system_Description.md` |
| SRS | 5.1 | `Srs/SRS_Requirements.md` |
| HLD | 3.1 | `archi/HLD_High_Level_Design.md` |
| LLD-01 Database Schema | 1.0 | `lld/LLD_01_Database_Schema.md` |
| LLD-02 MCP Server | 1.1 | `lld/LLD_02_MCP_Server.md` |
| LLD-03 Gemini CLI Skill | 1.1 | `lld/LLD_03_Gemini_CLI_Skill.md` |
| LLD-04 Deterministic Generator | 1.1 | `lld/LLD_04_Deterministic_Generator.md` |
| LLD-05 Database Initializer | 1.1 | `lld/LLD_05_Database_Initializer.md` |
| LLD-06 Local Review CLI | 1.1 | `lld/LLD_06_Local_Review_CLI.md` |

## Status

**Phase:** Design complete, implementation scaffolding in place.  
**Blocking decision:** SRS-015 — external data transfer to Gemini API requires stakeholder security approval. System operates on synthetic data until resolved.
