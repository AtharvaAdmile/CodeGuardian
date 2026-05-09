# 🛡️ CodeGuardian

> **AI-powered institutional memory for codebases.** A CLI-first tool with an Electron desktop GUI that surfaces engineering context, detects compliance risks, identifies code experts, and generates onboarding paths — all backed by NVIDIA NIM and an MCP server for AI assistant integration.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [CLI Usage (cgctl)](#cli-usage-cgctl)
- [Desktop App](#desktop-app)
- [MCP Server](#mcp-server)
- [Server Services](#server-services)
- [LangGraph Agents](#langgraph-agents)
- [Running Tests](#running-tests)
- [License](#license)

---

## Overview

CodeGuardian preserves and surfaces the institutional knowledge behind a codebase — the **why** behind architectural decisions, who owns what, and the blast radius of any change. It indexes your code once and lets developers query that context through a CLI, a desktop app, or directly from their AI assistant via MCP.

Everything runs through a central **FastAPI hub on port 8742**. The CLI, the Electron desktop app, and the MCP server are all thin HTTP clients — no LLM or embedding work is done client-side.

---

## Features

- **Semantic Q&A** — Ask natural-language questions; get answers grounded in code chunks, architectural decisions, and author expertise
- **Knowledge Graph** — NetworkX `DiGraph` linking files, functions, decisions, authors, and modules; rebuilt on every index
- **Impact Analysis** — File Explorer sidebar action that persists LLM-synthesized blast-radius reports per file
- **Decision Extraction** — LLM parses the last 50 commits to extract and store architectural decisions
- **Commit Review** — Git history and working-tree review: changed files, diffs, commit readiness, and one-click commit flow
- **Onboarding Paths** — LangGraph agent converts a plain-text task description into an ordered learning path
- **Expertise Map** — `git blame` + commit analysis to identify who knows each file best
- **MCP Integration** — Exposes 9 tools to any MCP-compatible AI assistant (Claude Code, etc.)
- **Offline-capable CLI** — `--offline` flag bypasses the HTTP layer and imports Python services directly

---

## Architecture

All three clients talk exclusively to the FastAPI backend over HTTP. No client touches the database or LLM directly.

```
cgctl CLI ──────────────┐
Desktop Electron App ───┼──→  FastAPI server (:8742) ──→ NVIDIA NIM API
MCP Server (stdio/SSE) ─┘         │
                                   ├──→ ChromaDB (local, always)
                                   ├──→ Supabase pgvector (optional)
                                   └──→ .codeguardian/ (JSON persistence)
```

### Indexing Pipeline (4 phases)

`POST /api/index` starts a background job. Phase 1 completes fast (code is immediately searchable); Phases 2–4 run concurrently in the background:

| Phase | Work |
|-------|------|
| 1 | Walk files → AST chunk (Python) or regex chunk (JS/TS) → NIM embeddings (batches of 32) → upsert to ChromaDB + Supabase |
| 2 | `git blame` → expertise map (author → files) |
| 3 | Last 50 commits → LLM decision extraction → stored in DecisionService |
| 4 | Rebuild NetworkX knowledge graph from scratch → persist to `.codeguardian/knowledge_graph.json` |

Poll progress at `GET /api/index/status/{job_id}`.

---

## Project Structure

```
CG_2/
├── server/                        # FastAPI backend (the hub)
│   ├── app.py                     # Application factory + lifespan
│   ├── config.py                  # Pydantic-settings config
│   ├── mcp_server.py              # Standalone MCP server (stdio / SSE)
│   ├── agents/
│   │   ├── review_agent.py        # LangGraph: security + complexity review
│   │   └── onboarding_agent.py    # LangGraph: task → learning path
│   ├── routes/
│   │   ├── health.py
│   │   ├── indexing.py
│   │   ├── query.py
│   │   ├── analysis.py
│   │   ├── analysis_extended.py
│   │   ├── impact.py
│   │   ├── review.py
│   │   └── onboarding.py
│   └── services/
│       ├── llm_client.py          # NIMClient — sole LLM interface
│       ├── embedding_service.py   # NIMEmbeddingService (1024-dim)
│       ├── vector_service.py      # ChromaDB + optional Supabase
│       ├── knowledge_graph.py     # NetworkX DiGraph builder
│       ├── decision_service.py    # Store / retrieve architectural decisions
│       ├── decision_extractor.py  # LLM extracts decisions from git log
│       ├── git_service.py         # git blame, log, diff helpers
│       └── impact_engine.py       # Blast-radius calculator
│
├── cgctl/                         # CLI (thin HTTP client)
│   ├── main.py                    # Typer entry point
│   ├── client.py                  # CGClient (synchronous httpx)
│   ├── state.py                   # Global --offline / --api-url state
│   └── commands/
│       ├── init.py
│       ├── index.py
│       ├── ask.py
│       ├── context.py
│       ├── impact.py
│       ├── review.py
│       ├── onboard.py
│       ├── health.py
│       ├── serve.py
│       ├── config.py
│       └── audit.py
│
├── desktop-app/                   # Electron + React + Vite
│   ├── electron/main.ts           # Electron main process
│   └── src/
│       ├── App.tsx                # Router + ProjectContext
│       ├── pages/                 # Full-page views
│       │   ├── Dashboard.tsx
│       │   ├── QnA.tsx
│       │   ├── KnowledgeGraph.tsx
│       │   ├── Onboarding.tsx
│       │   ├── CommitReview.tsx
│       │   ├── FileExplorer.tsx
│       │   ├── Indexing.tsx
│       │   └── Settings.tsx
│       ├── components/
│       │   ├── layout/            # Sidebar, TopBar, CommandPalette
│       │   └── shared/            # LoadingSpinner, etc.
│       └── hooks/                 # useProject, API hooks
│
├── tests/                         # pytest test suite
├── .env.example                   # Environment variable template
├── requirements.txt
└── CLAUDE.md                      # AI assistant guidance
```

---

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm (desktop app only)
- **NVIDIA NIM API Key** — get one at [build.nvidia.com](https://build.nvidia.com)
- Git (required for expertise mapping and decision extraction)

---

## Installation

### 1. Python backend + CLI

```bash
git clone https://github.com/your-org/codeguardian.git
cd codeguardian

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Electron desktop app

```bash
cd desktop-app
npm install
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# NVIDIA NIM (required — all LLM and embedding calls)
NVIDIA_NIM_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_LLM_MODEL=qwen/qwen3-coder-480b-a35b-instruct
NVIDIA_EMBED_MODEL=nvidia/nv-embedqa-e5-v5

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8742

# ChromaDB (local vector store — always required)
CHROMADB_PERSIST_DIR=./chroma_data

# Supabase (optional — enables persistent pgvector storage)
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Logging
LOG_LEVEL=INFO
```

All features work with ChromaDB only. Supabase adds persistent cloud storage.

---

## CLI Usage (cgctl)

Start the server first (required for all commands except `--offline` mode):

```bash
# Start the server
python -m cgctl.main serve

# Or with uvicorn directly
uvicorn server.app:app --host 0.0.0.0 --port 8742

# Dev mode with auto-reload
python -m cgctl.main serve --reload
```

Global flags available on every command:

```
--offline       Run in offline mode (direct Python imports, no HTTP)
--api-url URL   API server URL (default: http://localhost:8742)
```

### Commands

#### `cgctl init`
Initialize a new CodeGuardian project in the current directory.

```bash
python -m cgctl.main init
```

#### `cgctl index`
Index a codebase into the vector store. Walks `.py`, `.js`, `.ts`, `.jsx`, `.tsx` files. Skips `node_modules`, `__pycache__`, `.git`, `venv`, `dist`, `build`.

```bash
python -m cgctl.main index /path/to/project
```

#### `cgctl ask`
Ask a natural-language question about the indexed codebase.

```bash
python -m cgctl.main ask "Why is authentication handled in middleware?"
python -m cgctl.main ask "Who owns the payment module?"
```

#### `cgctl context`
Get full context for a specific file: purpose, owners, architectural decisions, and dependents.

```bash
python -m cgctl.main context server/routes/query.py
```

#### `cgctl impact`
Show the blast radius for a changed file — which files transitively depend on it and their risk scores.

```bash
python -m cgctl.main impact server/services/vector_service.py
```

#### `cgctl review`
Run a multi-stage code review on a file or diff. Checks security patterns, complexity, and blast radius.

```bash
python -m cgctl.main review server/routes/indexing.py
python -m cgctl.main review --diff path/to/changes.diff
```

#### `cgctl onboard`
Generate an ordered learning path for a developer picking up a new task.

```bash
python -m cgctl.main onboard "Add rate limiting to the API"
```

#### `cgctl health`
Check server health and report which services are active.

```bash
python -m cgctl.main health
```

#### `cgctl serve`
Start the FastAPI server. Optionally run as an MCP server instead.

```bash
python -m cgctl.main serve               # REST API on :8742
python -m cgctl.main serve --reload      # Dev mode with auto-reload
python -m cgctl.main serve --mcp         # MCP server (stdio)
python -m cgctl.main serve --mcp-sse     # MCP server (SSE on :8743)
```

#### `cgctl config`
Manage project configuration settings.

```bash
python -m cgctl.main config show
python -m cgctl.main config set KEY VALUE
```

#### `cgctl audit`
Run a code audit across the indexed project.

```bash
python -m cgctl.main audit
```

---

## Desktop App

The desktop app is an Electron + React + Vite application. It communicates with the FastAPI server over HTTP — no direct Python or database access from the renderer.

### Running

```bash
# Requires server running on :8742
cd desktop-app
npm run dev          # Vite + Electron in development mode
npm run build        # Production build
npm run typecheck    # TypeScript type check
```

### Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | Project overview, health status, recent activity |
| `/ask` | Q&A | Natural-language query interface with source citations |
| `/graph` | Knowledge Graph | D3.js interactive graph of files, functions, decisions, authors |
| `/impact` | Redirect | Opens File Explorer, where impact analysis lives in the file context sidebar |
| `/onboard` | Onboarding | Learning path generator for new tasks |
| `/review` | Commit Review | Git history, current changes, commit summary, and commit action |
| `/files` | File Explorer | Browse indexed files, file context, and persisted impact analysis |
| `/indexing` | Indexing | Kick off and monitor index jobs |
| `/settings` | Settings | Server URL, project configuration |

### Architecture

```
Electron main process (electron/main.ts)
    └── exposes window.cgctl IPC bridge (selectDirectory, etc.)

React renderer (src/)
    ├── BrowserRouter with 9 page routes
    ├── ProjectContext — tracks active project, health, index status
    └── HTTP calls → FastAPI :8742 (no direct DB or LLM access)
```

---

## MCP Server

The MCP server exposes CodeGuardian's capabilities as tools to any MCP-compatible AI assistant. It is a thin HTTP proxy — all tools delegate to the FastAPI server on `:8742`.

### Setup

Add to your Claude Code MCP config (`~/.claude/mcp_servers.json`):

```json
{
  "mcpServers": {
    "codeguardian": {
      "command": "python",
      "args": ["-m", "server.mcp_server"],
      "cwd": "/path/to/codeguardian"
    }
  }
}
```

### Transport modes

```bash
python -m server.mcp_server              # stdio (default, for Claude Code)
python -m server.mcp_server --sse        # SSE on :8743
python -m server.mcp_server --sse --port 9000   # custom port
```

### Available Tools

| Tool | Description |
|------|-------------|
| `query_codebase` | Ask any natural-language question; returns answer with sources, decisions, and experts |
| `get_context_for_file` | Full context for a file: purpose, owners, decisions, dependents |
| `get_decision_history` | All architectural decisions affecting a file, plus git commit timeline |
| `get_expertise` | Who knows a file best: ranked contributors with commit counts and ownership % |
| `analyze_impact` | Blast-radius report: transitive dependents, risk scores, suggested reviewers |
| `review_code` | Multi-stage review: security, complexity, patterns, impact |
| `check_compliance` | Security and compliance scan only (secrets, SQL injection, PII logging) |
| `generate_onboarding_path` | Ordered learning path for a developer picking up a new task |
| `check_breaking_changes` | AST-based detection of removed functions, added required params, changed signatures |

---

## Server Services

All services are initialized on `app.state` during startup and are `None` if their prerequisites are missing. Every feature degrades gracefully.

| Service | File | Role |
|---------|------|------|
| `NIMClient` | `services/llm_client.py` | Sole LLM interface — raw `httpx` against NVIDIA NIM's OpenAI-compatible endpoint. Retry: 429 → exponential backoff, 5xx → 1 retry, timeout → 1 retry |
| `NIMEmbeddingService` | `services/embedding_service.py` | 1024-dimensional embeddings from `nvidia/nv-embedqa-e5-v5` |
| `VectorService` | `services/vector_service.py` | ChromaDB (always) + optional Supabase pgvector. Vector IDs are deterministic `SHA256(project_id + file_path + chunk_index)` |
| `KnowledgeGraph` | `services/knowledge_graph.py` | NetworkX `DiGraph` with node types: `file`, `function`, `decision`, `author`, `module`. Always rebuilt from scratch on index. Persisted to `.codeguardian/knowledge_graph.json` |
| `DecisionService` | `services/decision_service.py` | Store and retrieve architectural decisions extracted from git history |
| `DecisionExtractor` | `services/decision_extractor.py` | LLM parses the last 50 commits to extract structured decisions |
| `GitService` | `services/git_service.py` | `git blame`, `git log`, `git diff` helpers; initialized per-project when an index job runs |
| `ImpactEngine` | `services/impact_engine.py` | Traverses the knowledge graph to compute blast-radius reports |

---

## LangGraph Agents

Two agents are built with LangGraph and live in `server/agents/`.

### ReviewAgent (`agents/review_agent.py`)

Linear pipeline: `parse_input → pattern_check → impact_analysis → security_scan → synthesize`

- **pattern_check** — checks naming, error handling, and logging consistency vs similar functions in the codebase
- **security_scan** — detects hardcoded secrets, SQL injection, path traversal, PII in logs
- **impact_analysis** — uses `ImpactEngine` to attach blast-radius data to the report
- **synthesize** — LLM combines all findings into a ranked `ReviewReport`

### OnboardingAgent (`agents/onboarding_agent.py`)

Linear pipeline: `parse_task → find_relevant_code → gather_context → generate_path`

Converts a plain-text task description into an ordered, numbered learning path enriched with architectural decisions and expert contacts from the knowledge graph.

---

## Running Tests

```bash
# All tests
pytest

# Single file
pytest tests/test_decision_service.py

# Filter by name
pytest tests/ -k "test_embedding"

# Async tests
pytest --asyncio-mode=auto
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.
