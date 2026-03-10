# 🛡️ CodeGuardian

> **AI-powered institutional memory for codebases.** A CLI-first tool with a stunning Electron desktop GUI that surfaces engineering context, audits code health, detects compliance risks, and identifies code experts — all backed by a local-first RAG pipeline and an MCP server for GitHub Copilot integration.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [Python CLI (cgctl)](#1-python-cli-cgctl)
  - [Electron Desktop App](#2-electron-desktop-app)
- [Configuration](#configuration)
- [CLI Usage (cgctl)](#cli-usage-cgctl)
  - [init](#cgctl-init)
  - [index](#cgctl-index)
  - [ask](#cgctl-ask)
  - [audit](#cgctl-audit)
  - [serve](#cgctl-serve)
  - [config](#cgctl-config)
- [Desktop App](#desktop-app)
  - [Running the App](#running-the-app)
  - [Features](#desktop-features)
  - [IPC Architecture](#ipc-architecture)
- [MCP Server](#mcp-server)
  - [Available Tools](#available-mcp-tools)
  - [VS Code / GitHub Copilot Integration](#vs-code--github-copilot-integration)
- [Core Python Modules](#core-python-modules)
- [Analysis Modules](#analysis-modules)
- [Documentation Generator](#documentation-generator)
- [Test Generator](#test-generator)
- [Database Layer (Supabase)](#database-layer-supabase)
- [Development](#development)
- [License](#license)

---

## Overview

CodeGuardian is a **developer intelligence platform** that turns your codebase into a searchable, auditable knowledge base. It combines:

- A **local RAG pipeline** (ChromaDB + sentence-transformers) for semantic code search without sending code to the cloud
- A **Google Gemini-powered LLM layer** for Q&A, documentation generation, and test generation
- An **MCP (Model Context Protocol) server** that plugs CodeGuardian's tools directly into GitHub Copilot / VS Code
- A **`cgctl` CLI** for terminal-first workflows (init, index, ask, audit, serve)
- An **Electron + React + D3.js desktop app** providing an interactive codebase graph and sidebar analysis tools

---

## Features

### 🔍 Semantic Code Search (RAG)
- Index any Python/JS/TS/JSX/TSX codebase with local `sentence-transformers` embeddings
- Query your codebase in natural language; get back ranked, source-cited code chunks
- Re-ranking for improved relevance; no data leaves your machine

### 📊 Codebase Intelligence
| Feature | Description |
|---|---|
| ❤️ **File Health Score** | Combines cyclomatic complexity (Radon) + git churn into a 0–100 score |
| 🛡️ **Compliance Scanner** | Detects PII exposure, hardcoded secrets, dangerous function calls |
| 👥 **Code Experts** | Identifies file owners with recency-weighted git scoring |
| 📜 **Git History** | Commit history + blame for files or specific line ranges |
| ⚡ **Runtime Stats** | Reads a `runtime_stats.json` fed by your CI/CD for production telemetry |
| 📐 **Structure Analyzer** | Organization score, file distribution, directory structure analysis |

### 📝 AI Documentation Generator
- Multi-agent pipeline: Analysis → Context → Documentation → Review
- Supports docstring injection, Markdown export, and HTML export
- Gap detection with quality scoring per function/class

### 🧪 AI Test Generator
- Analyzes files for testable functions/classes with complexity scores
- Generates pytest (Python) or Jest (JS/TS) unit tests via Gemini
- Saves tests to `generated_test_cases/` with mirrored directory structure
- Can run generated tests and return pass/fail results

### 🖥️ Electron Desktop App
- Interactive force-directed codebase dependency graph powered by D3.js
- Sidebar with per-file analysis actions (health, compliance, experts, history)
- Slide-in results pane with smart grouping and line-range formatting
- Dark glassmorphism theme with micro-animations

### 🔌 MCP Server (GitHub Copilot Integration)
- Exposes 13+ CodeGuardian tools as MCP-compatible functions
- Plugs directly into GitHub Copilot via VS Code settings
- Runs locally, zero external API calls for search

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     CodeGuardian Platform                        │
│                                                                  │
│  ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐  │
│  │  cgctl CLI  │    │  Electron App   │    │  MCP Server     │  │
│  │  (Typer +   │    │  (React + D3 +  │    │  (FastMCP via   │  │
│  │   Rich)     │    │   Vite + TS)    │    │   Python MCP)   │  │
│  └──────┬──────┘    └────────┬────────┘    └────────┬────────┘  │
│         │                    │ IPC (Electron)        │           │
│         └────────────────────┴──────────────────────┘           │
│                              │                                   │
│                    ┌─────────▼──────────┐                        │
│                    │   src/ Core Engine │                        │
│                    │                   │                        │
│                    │  EmbeddingGen     │  ← sentence-transformers│
│                    │  VectorStore      │  ← ChromaDB (local)    │
│                    │  QueryEngine      │  ← RAG + reranking     │
│                    │  CodeParser       │  ← AST parsing         │
│                    │  StructureAnalyzer│  ← Radon complexity    │
│                    └─────────┬─────────┘                        │
│                              │                                   │
│           ┌──────────────────┼──────────────────┐               │
│           │                  │                  │               │
│  ┌────────▼──────┐  ┌────────▼──────┐  ┌───────▼────────┐      │
│  │ src/analysis/ │  │src/documentation│  │ src/testing/  │      │
│  │  git_context  │  │  orchestrator   │  │  test_gen     │      │
│  │  expertise    │  │  analysis_agent │  │  test_runner  │      │
│  │  compliance   │  │  gap_detector   │  │  test_analyzer│      │
│  │  runtime      │  │  export/        │  └───────────────┘      │
│  └───────────────┘  └─────────────────┘                        │
│                                                                  │
│  ┌───────────────────────────────────────────────┐              │
│  │  src/db/  →  Supabase (PostgreSQL + pgvector)  │              │
│  │  (queries.py, supabase_client.py, schema.sql)  │              │
│  └───────────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────────┘
```

**LLM**: Google Gemini (`gemini-2.0-flash`) via `google-generativeai`  
**Local Embeddings**: `sentence-transformers` + `text-embedding-004` (Gemini)  
**Vector Store**: ChromaDB (local persistence in `chroma_data/`)  
**Database**: Supabase (PostgreSQL + pgvector) — optional, for the full cloud-backed variant  
**Desktop**: Electron 28 + React 18 + Vite 5 + D3.js v7 + TypeScript

---

## Project Structure

```
CG_2/
├── cgctl/                        # CLI package (pip-installable as 'cgctl')
│   ├── main.py                   # Typer app entry point
│   ├── commands/
│   │   ├── init.py               # cgctl init
│   │   ├── index.py              # cgctl index
│   │   ├── ask.py                # cgctl ask
│   │   ├── audit.py              # cgctl audit
│   │   ├── serve.py              # cgctl serve (MCP server)
│   │   └── config.py             # cgctl config
│   └── utils/
│       ├── output.py             # Rich console helpers
│       └── validators.py         # Input validation
│
├── src/                          # Core Python engine
│   ├── mcp_server.py             # FastMCP server (13+ tools)
│   ├── codebase_indexer.py       # File scanning + indexing pipeline
│   ├── embedding_generator.py    # Local sentence-transformer embeddings
│   ├── vector_store.py           # ChromaDB wrapper
│   ├── query_engine.py           # RAG retrieval + reranking
│   ├── code_parser.py            # AST-based code parsing (Python/JS/TS)
│   ├── structure_analyzer.py     # Project structure + complexity (Radon)
│   ├── text_chunker.py           # Token-aware code chunking
│   ├── conversation_manager.py   # Multi-turn conversation history
│   ├── progress_tracker.py       # Indexing progress callbacks
│   ├── input_validator.py        # Input sanitization
│   ├── file_validator.py         # File type + size validation
│   ├── analysis/                 # Advanced code intelligence
│   │   ├── git_context.py        # Git history + blame (GitPython)
│   │   ├── expertise.py          # Code owner scoring (recency-weighted)
│   │   ├── compliance.py         # PII/secrets/dangerous-function scanner
│   │   ├── regulatory_scanner.py # Regulatory compliance (HIPAA, etc.)
│   │   └── runtime.py            # Production telemetry loader
│   ├── documentation/            # AI documentation generator
│   │   ├── orchestrator.py       # Multi-agent pipeline coordinator
│   │   ├── analysis_agent.py     # Code element extraction
│   │   ├── context_agent.py      # RAG-based context enrichment
│   │   ├── gap_detector.py       # Documentation gap detection
│   │   ├── dependency_analyzer.py# Import/call-graph analysis
│   │   ├── template_engine.py    # Jinja2 doc templates
│   │   ├── review_manager.py     # Human-in-the-loop review
│   │   ├── error_handler.py      # Retry + error recovery
│   │   └── export/
│   │       ├── docstring_writer.py # Injects docstrings into source
│   │       ├── markdown_writer.py  # Exports to Markdown
│   │       └── html_writer.py      # Exports to HTML
│   ├── testing/                  # AI test generator
│   │   ├── test_analyzer.py      # Identifies testable code elements
│   │   ├── test_generator.py     # Gemini-powered test generation
│   │   ├── test_orchestrator.py  # End-to-end test gen pipeline
│   │   ├── test_runner.py        # pytest / jest runner
│   │   └── test_validator.py     # Validates generated test code
│   ├── db/                       # Supabase / PostgreSQL layer
│   │   ├── supabase_client.py    # Supabase connection + auth
│   │   ├── queries.py            # SQL query helpers
│   │   └── schema.sql            # Database schema (pgvector tables)
│   ├── config/                   # Config loader
│   ├── core/                     # Shared error handler
│   └── models/                   # Pydantic data models
│       ├── documentation_models.py
│       └── testing_models.py
│
├── desktop-app/                  # Electron + React + Vite desktop app
│   ├── electron/
│   │   ├── main.ts               # Electron main process + IPC handlers
│   │   └── preload.ts            # Secure IPC bridge (contextBridge)
│   ├── src/
│   │   ├── App.tsx               # Root React component + layout
│   │   ├── main.tsx              # React entry point
│   │   ├── index.css             # Global styles, design tokens
│   │   ├── components/
│   │   │   ├── ActionsPane.tsx   # Sidebar + slide-in results pane
│   │   │   └── SettingsPane.tsx  # Settings panel
│   │   ├── views/
│   │   │   └── GraphDashboard.tsx# D3.js force-directed codebase graph
│   │   └── context/              # React context providers
│   ├── package.json
│   ├── tsconfig.json             # TypeScript config (React)
│   ├── tsconfig.electron.json    # TypeScript config (Electron main)
│   ├── tsconfig.node.json        # TypeScript config (Node utilities)
│   └── vite.config.ts            # Vite build config
│
├── docs/                         # Project documentation
│   ├── INDEX.md
│   ├── DOCUMENTATION_GENERATOR_GUIDE.md
│   ├── configuration-examples.md
│   └── screenshots/
│
├── rules/
│   └── compliance.yaml           # Custom compliance scan rules
│
├── config.toml                   # Project-wide configuration
├── setup.py                      # pip package setup
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
├── .codeguardian                 # Project marker file (auto-created by cgctl init)
└── runtime_stats.json            # Optional CI/CD telemetry feed
```

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.9+ (3.10–3.12 recommended) |
| Node.js | 18+ |
| npm | 9+ |
| Git | Any recent version |
| Google Gemini API Key | Required for AI features |

---

## Installation

### 1. Python CLI (`cgctl`)

```bash
# Clone the repository
git clone <repo-url>
cd CG_2

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows

# Install in editable mode
pip install -e .

# Install all dependencies
pip install -r requirements.txt

# Verify installation
cgctl --version
```

### 2. Electron Desktop App

```bash
# Navigate to the desktop app directory
cd desktop-app

# Install Node.js dependencies
npm install

# Start in development mode (hot-reload Vite + Electron)
npm run dev
```

---

## Configuration

### Environment Variables

Copy the template and fill in your values:

```bash
cp .env.example .env
```

**Required:**
```bash
GOOGLE_API_KEY=your_gemini_api_key_here
```

**Optional (Supabase — for cloud DB variant):**
```bash
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_anon_key
```

### `config.toml`

The `config.toml` at the project root controls all default settings:

```toml
[llm]
provider = "gemini"
model = "gemini-2.0-flash"
temperature = 0.7
max_tokens = 2048

[embedding]
model = "models/text-embedding-004"
dimension = 768
batch_size = 32

[indexing]
exclude_dirs = [".git", "__pycache__", "node_modules", ...]
supported_extensions = [".py", ".js", ".jsx", ".ts", ".tsx"]

[chunking]
min_chunk_tokens = 100
max_chunk_tokens = 500
overlap_tokens = 50

[retrieval]
initial_count = 10
final_count = 5
similarity_threshold = 0.7

[agent]
blast_radius_threshold = 5
require_approval_above = 5
```

---

## CLI Usage (`cgctl`)

### `cgctl init`

Initialize a new CodeGuardian project in a directory. Creates the `.codeguardian` marker file.

```bash
# Initialize in the current directory
cgctl init .

# Initialize a specific path with a custom name
cgctl init /path/to/my-project --name "MyProject"
```

### `cgctl index`

Scan and index all supported source files (`*.py`, `*.js`, `*.ts`, `*.jsx`, `*.tsx`) into the local ChromaDB vector store using sentence-transformer embeddings.

```bash
# Index the current directory
cgctl index .

# Force re-index (clears existing embeddings)
cgctl index /path/to/project --force
```

> **Note:** You must run `cgctl init` before `cgctl index`.

### `cgctl ask`

Semantic search across your indexed codebase in natural language.

```bash
# Basic query
cgctl ask "What does the authentication module do?"

# Control number of results
cgctl ask "database connection pooling" --top-k 10

# JSON output for scripting
cgctl ask "error handling" --json

# Search in a specific project
cgctl ask "how is rate limiting implemented?" --path /path/to/project

# Pipe raw context to clipboard (macOS)
cgctl ask context "authentication" | pbcopy
```

### `cgctl audit`

Run a comprehensive audit on a single file: expertise, health score, compliance, runtime stats, and git history.

```bash
# Audit a file
cgctl audit src/mcp_server.py

# Disable specific sections
cgctl audit src/query_engine.py --no-git --no-runtime
cgctl audit file src/embedding_generator.py --no-compliance
```

**Output includes:**
- 👤 **Expertise**: Primary and backup code owners with expertise scores
- 📊 **Health Score**: 0–100 score combining cyclomatic complexity + git churn
- 🔒 **Compliance**: PII, secrets, and dangerous function detections with severity
- ⚡ **Runtime**: Error rate, average latency, p99 latency (from `runtime_stats.json`)
- 📜 **Git History**: Last 5 commits + churn risk level

### `cgctl serve`

Start the MCP server for GitHub Copilot / VS Code integration.

```bash
# Start with stdio transport (default, for VS Code)
cgctl serve

# Start with SSE transport on a specific port
cgctl serve --transport sse --port 8765
```

### `cgctl config`

View and manage project configuration.

```bash
# Show current config
cgctl config show

# Set a value
cgctl config set llm.model gemini-2.0-flash
```

---

## Desktop App

The Electron desktop app provides a visual, interactive interface for CodeGuardian's analysis capabilities.

### Running the App

```bash
cd desktop-app

# Development (hot-reload)
npm run dev

# Type-check the entire project
npm run typecheck

# Build for production
npm run build

# Package as distributable (macOS .dmg, Windows .exe, Linux .AppImage)
npm run build:electron
```

> **Important:** The CodeGuardian Python backend must be installed (`pip install -e .`) and the target project must be initialized (`cgctl init`) and indexed (`cgctl index`) before using the desktop app's analysis features.

### Desktop Features

#### 🗺️ Interactive Codebase Graph
- **Force-Directed Visualization**: Browse your entire codebase as an interactive dependency graph powered by D3.js
- **Zoom & Pan**: Smooth interactions for large codebases
- **Smart Node Sizing**: Folders display with labels inside; files are sized by byte count
- **Double-click to Reset**: Re-centers and rescales the view

#### 🎛️ Action Sidebar
A persistent floating sidebar with per-file analysis tools:

| Button | Action |
|---|---|
| ❤️ File Health | Tech debt score (complexity + churn) |
| 🛡️ Compliance Scanner | PII, secrets, dangerous code detection |
| 👥 Code Experts | File owner identification with scores |
| 📜 Git History | Commit history and blame for selected files |

#### 📊 Results Pane
- Slide-in panel from the left triggered by sidebar actions
- Smart grouping of compliance violations by message + severity
- Formatted line ranges (e.g., "Lines 130, 132–136, 140")
- Selected-file pill indicator always visible at bottom

#### ⚙️ Settings Pane
- Set the active project path
- Update the Google Gemini API key (written directly to the project's `.env` file)
- Trigger project initialization and indexing

### IPC Architecture

The app uses Electron's IPC (Inter-Process Communication):

```
React Renderer          Electron Main Process (Node.js)      Python Backend
     │                             │                              │
     │ window.cgctl.getFileHealth()│                              │
     │────────────────────────────►│                              │
     │                             │ spawn python3 -c             │
     │                             │ "from src.mcp_server         │
     │                             │  import get_file_health..."  │
     │                             │─────────────────────────────►│
     │                             │       JSON result            │
     │                             │◄─────────────────────────────│
     │           JSON result       │                              │
     │◄────────────────────────────│                              │
```

**IPC Channels exposed via `window.cgctl`:**

| Channel | Description |
|---|---|
| `cgctl:init` | Initialize a project |
| `cgctl:index` | Index a project |
| `cgctl:analyzeStructure` | Get structure analysis |
| `cgctl:getFileHealth` | Get a file's health score |
| `cgctl:checkCompliance` | Run standard compliance scan |
| `cgctl:checkRegulatoryCompliance` | Run regulatory compliance scan |
| `cgctl:getFileExpert` | Find code owner for a file |
| `cgctl:getFileHistory` | Get git history for a file |
| `cgctl:findDependencies` | Analyze file dependencies |
| `cgctl:analyzeProjectDependencies`| Build full project dependency graph |
| `cgctl:detectDocumentationGaps` | Find undocumented code |
| `cgctl:analyzeTestability` | Find testable elements |
| `cgctl:queryCodebase` | Semantic code search |
| `cgctl:runTests` | Execute pytest |
| `cgctl:generateTestCase` | AI-generate unit tests |
| `cgctl:runLocalTest` | Run a generated test file |
| `cgctl:updateApiKey` | Update `.env` with new API key |
| `fs:listFiles` | List project files |
| `fs:readFile` | Read file content |
| `fs:saveTestFile` | Save generated test to disk |
| `fs:testFileExists` | Check if test file already exists |

---

## MCP Server

The MCP server (`src/mcp_server.py`) exposes CodeGuardian's full analysis capabilities as tools consumable by GitHub Copilot and other MCP-compatible AI assistants.

### Available MCP Tools

| Tool | Description |
|---|---|
| `query_codebase` | Semantic RAG search over the indexed codebase |
| `analyze_structure` | Project structure score, file counts, git status |
| `find_dependencies` | Imports, function calls, and inheritance for a file |
| `analyze_project_dependencies` | Full project dependency graph (nodes + links) |
| `analyze_testability` | Find testable elements with complexity + RAG context |
| `run_tests` | Execute pytest and return pass/fail results |
| `generate_unit_test` | AI-generate unit tests for a source file |
| `run_generated_test` | Execute a previously generated test file |
| `detect_documentation_gaps` | Find undocumented functions/classes with quality scores |
| `get_file_history` | Git commit history + churn for a file or line range |
| `get_file_expert` | Code owner identification with expertise scores |
| `check_compliance` | Scan code snippet for PII, secrets, dangerous APIs |
| `check_regulatory_compliance` | Regulatory compliance scan (HIPAA-style rules) |
| `get_file_health` | Composite tech debt score (complexity + churn) |
| `get_runtime_stats` | Production telemetry for a file from `runtime_stats.json` |

### VS Code / GitHub Copilot Integration

Add to your VS Code `settings.json`:

```json
{
  "github.copilot.chat.experimental.mcpServers": {
    "codeguardian": {
      "command": "cgctl",
      "args": ["serve"],
      "cwd": "/path/to/your/project"
    }
  }
}
```

Then in GitHub Copilot Chat, you can use `@codeguardian` and reference any tool. Example prompts:
- *"Use `query_codebase` to find all authentication-related code"*
- *"Call `get_file_health` on `src/query_engine.py` and explain the results"*
- *"Run `generate_unit_test` on the `EmbeddingGenerator` class"*

---

## Core Python Modules

| Module | Purpose |
|---|---|
| `src/codebase_indexer.py` | Walks the project directory, reads files, chunks them, and stores embeddings in ChromaDB |
| `src/embedding_generator.py` | Wraps `sentence-transformers` (`all-MiniLM-L6-v2`) for local embedding generation |
| `src/vector_store.py` | ChromaDB client wrapper; handles collection creation, upsert, and vector similarity search |
| `src/query_engine.py` | Orchestrates embedding generation → vector search → reranking for RAG queries |
| `src/code_parser.py` | AST-based parser for Python and regex-based parser for JS/TS to extract functions, classes, imports |
| `src/text_chunker.py` | Token-aware chunking with configurable min/max/overlap tokens |
| `src/structure_analyzer.py` | Analyzes project structure; uses Radon for cyclomatic complexity; computes file health scores |
| `src/conversation_manager.py` | Manages multi-turn conversation history for context-aware Q&A |

---

## Analysis Modules

### `src/analysis/git_context.py` — `GitContextAnalyzer`
Uses GitPython to extract commit history, per-line blame, and churn counts for any file or line range.

### `src/analysis/expertise.py` — `ExpertiseTracker`
Calculates recency-weighted expertise scores for each contributor per file. Returns primary expert, backup expert, and last-active timestamp.

### `src/analysis/compliance.py` — `ComplianceScanner`
Pattern-based scanner that detects:
- **PII exposure** (emails, phone numbers, SSNs in code strings)
- **Hardcoded secrets** (API keys, passwords, tokens)
- **Dangerous functions** (eval, exec, pickle.loads, etc.)
- Severity levels: `critical`, `high`, `medium`, `low`

### `src/analysis/regulatory_scanner.py`
Loads custom rules from `rules/compliance.yaml` for domain-specific compliance (e.g., HIPAA logging requirements).

### `src/analysis/runtime.py` — `RuntimeLoader`
Reads `runtime_stats.json` to surface production telemetry (error rate, avg latency, p99, last error) per file.

---

## Documentation Generator

The documentation generator lives in `src/documentation/` and uses a multi-agent pipeline:

1. **`AnalysisAgent`** — Parses files, extracts code elements (functions, classes), scores documentation gaps
2. **`ContextAgent`** — Enriches each element with related code context from the RAG index
3. **`DocumentationAgent`** — Calls Gemini to generate docstrings/documentation for each gap
4. **`ReviewManager`** — Presents generated docs for human-in-the-loop review/approval
5. **`ExportModule`** — Writes approved docs as:
   - Docstring injection back into source files
   - Markdown documentation files
   - Standalone HTML documentation pages

---

## Test Generator

The test generator lives in `src/testing/`:

1. **`TestAnalyzer`** — Scans a file for testable functions and classes, scores by complexity
2. **`TestGenerator`** — Uses Gemini to generate `pytest` or `jest` test code with mocking and edge cases
3. **`TestOrchestrator`** — End-to-end pipeline: analyze → generate → validate → save
4. **`TestRunner`** — Executes `pytest` subprocess and parses pass/fail per file
5. **`TestValidator`** — Basic syntax validation of generated test code before saving

Generated tests are saved to `generated_test_cases/` (mirroring the source tree structure).

---

## Database Layer (Supabase)

`src/db/` provides an optional Supabase (PostgreSQL + pgvector) integration:

- **`supabase_client.py`** — Supabase Python client wrapper with connection management
- **`queries.py`** — Helper functions for vector similarity search, chunk storage, project metadata
- **`schema.sql`** — Full PostgreSQL schema with pgvector tables for code chunks and embeddings

> The primary local vector store is ChromaDB (zero-config). Supabase is used for the cloud-backed multi-user variant when `SUPABASE_URL` and `SUPABASE_KEY` are set.

---

## Development

### Running Tests

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_query_engine.py -v
```

### Type Checking (Desktop App)

```bash
cd desktop-app
npm run typecheck
```

### Adding a New MCP Tool

1. Add a new `@mcp.tool()` decorated function to `src/mcp_server.py`
2. Add the corresponding IPC handler to `desktop-app/electron/main.ts`
3. Expose it via `contextBridge` in `desktop-app/electron/preload.ts`
4. Call it from a React component in `desktop-app/src/`

### Feeding Runtime Stats

Populate `runtime_stats.json` from your CI/CD pipeline to enable the runtime telemetry feature:

```json
{
  "src/your_module.py": {
    "error_rate": 0.5,
    "avg_latency_ms": 120,
    "p99_latency_ms": 350,
    "request_count": 5000,
    "last_error": null,
    "last_error_time": null
  }
}
```

---

## License

MIT
