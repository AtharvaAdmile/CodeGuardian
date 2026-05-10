# CodeGuardian — Comprehensive Project Context

## Overview

**CodeGuardian** is an AI-powered institutional memory system for codebases. It indexes code and lets developers query contextual information (purpose, ownership, architectural decisions, impact analysis) through a CLI (`cgctl`), an Electron desktop app, or an MCP server for AI assistant integration (Claude Code, etc.).

All clients talk to a central **FastAPI hub on port 8742**. No client touches the database or LLM directly.

---

## Architecture

```
cgctl CLI ─────────────────────┐
Desktop Electron App ──────────┼──→ FastAPI server (:8742) ──→ NVIDIA NIM API
MCP Server (stdio/SSE) ───────┘         │
                                          ├──→ ChromaDB (local storage)
                                          └──→ .codeguardian/ (JSON persistence)
```

### Key Design Decisions

- **Single LLM Provider**: Everything routes through NVIDIA NIM's OpenAI-compatible API. No OpenAI, no Ollama, no local models.
- **Offline Mode**: The CLI can bypass HTTP and import Python services directly via `--offline`.
- **Graceful Degradation**: Every service is optional. If the NIM API key is missing, LLM-dependent features are disabled but the server still starts.
- **Vector Store**: ChromaDB for local persistent vector storage.
- **Context-YAML**: A new system (being phased in) that generates `.context.yaml` files per directory via LLM analysis, complementing/replacing vector-based retrieval.

---

## Project Structure

```
CG_2/
├── server/                     # FastAPI backend (the central hub)
│   ├── app.py                  # Application factory + lifespan (services init)
│   ├── config.py               # Pydantic-settings config (env-based)
│   ├── mcp_server.py           # MCP server (stdio / SSE) — thin HTTP proxy to FastAPI
│   ├── agents/
│   │   ├── review_agent.py     # LangGraph: security + complexity review pipeline
│   │   └── onboarding_agent.py # LangGraph: task → learning path pipeline
│   ├── routes/                 # FastAPI route modules
│   │   ├── health.py           # GET /api/health — server + service status
│   │   ├── query.py            # POST /api/ask, /api/ask/stream — RAG Q&A
│   │   ├── indexing.py         # POST /api/index — 2-phase indexing pipeline
│   │   ├── analysis.py         # File analysis (expert, history, overview)
│   │   ├── analysis_extended.py# Extended analysis endpoints
│   │   ├── impact.py           # Blast-radius analysis, breaking changes
│   │   ├── review.py           # Commit review, webhook
│   │   ├── onboarding.py       # Learning path generation
│   │   ├── context.py          # .context.yaml CRUD + search (NEW)
│   │   ├── cg_pilot.py         # CG-pilot agent endpoint (OpenAI SDK over NIM)
│   │   └── dashboard.py        # Dashboard data aggregation
│   ├── services/
│   │   ├── llm_client.py       # NIMClient — sole LLM interface (httpx)
│   │   ├── embedding_service.py# NIMEmbeddingService (1024-dim, nv-embedqa-e5-v5)
│   │   ├── vector_service.py   # ChromaDB (local only)
│   │   ├── knowledge_graph.py  # NetworkX DiGraph builder + JSON persistence
│   │   ├── decision_service.py # Store/retrieve architectural decisions
│   │   ├── decision_extractor.py# LLM extracts decisions from git log (last 50 commits)
│   │   ├── git_service.py      # git blame, log, diff, expertise mapping
│   │   ├── impact_engine.py    # Blast-radius calculator (KG traversal)
│   │   ├── context_service.py  # .context.yaml management (NEW)
│   │   ├── retrieval_service.py# Context-YAML retrieval for QnA (NEW)
│   │   ├── chat_history_service.py # CG-pilot chat session persistence (NEW)
│   │   └── cg_pilot_service.py # CG-pilot agent service (OpenAI SDK over NIM)
│   ├── models/                 # Pydantic + dataclass models
│   │   ├── context_models.py   # DirectoryContext, FileEntry, etc.
│   │   ├── embedding_models.py # VectorDocument, SearchResult
│   │   ├── git_models.py       # BlameEntry, CommitInfo, ExpertiseEntry
│   │   ├── llm_models.py       # NIMRequest, NIMResponse, NIMStreamChunk
│   │   ├── route_schemas.py    # Pydantic request/response schemas
│   │   └── schemas.py          # Generic schemas
│   └── middleware/
│       └── __init__.py
│
├── cgctl/                     # CLI (Typer-based thin HTTP client)
│   ├── main.py                # Entry point: Typer app with 11 subcommands
│   ├── client.py              # CGClient — synchronous httpx wrapper
│   ├── state.py               # Global CliState (offline, api_url)
│   └── commands/
│       ├── init.py            # Initialize CodeGuardian project
│       ├── index.py           # Index codebase into vector store
│       ├── ask.py             # Natural-language Q&A
│       ├── context.py         # File context (owners, decisions, dependents)
│       ├── impact.py          # Blast-radius analysis
│       ├── review.py          # Code review
│       ├── onboard.py         # Learning path generation
│       ├── health.py          # Server health check
│       ├── serve.py           # Start server (REST or MCP)
│       ├── config.py          # Manage config settings
│       ├── audit.py           # Run code audit
│       └── hooks.py           # Install/uninstall git hooks
│   └── utils/
│       ├── output.py          # Rich console helpers
│       └── validators.py      # Input validation
│
├── desktop-app/               # Electron + React + Vite + Tailwind
│   ├── electron/main.ts       # Electron main process (IPC bridge)
│   └── src/
│       ├── App.tsx            # Router + ProjectContext
│       ├── pages/             # 9 page views
│       │   ├── Dashboard.tsx
│       │   ├── QnA.tsx
│       │   ├── KnowledgeGraph.tsx (D3.js interactive graph)
│       │   ├── Onboarding.tsx
│       │   ├── CommitReview.tsx
│       │   ├── FileExplorer.tsx (with impact analysis sidebar)
│       │   ├── Indexing.tsx
│       │   └── Settings.tsx
│       ├── components/
│       │   ├── layout/        # Sidebar, TopBar, CommandPalette
│       │   ├── shared/        # LoadingSpinner, etc.
│       │   └── CGPilot.tsx    # In-app AI assistant chat
│       ├── hooks/             # useProject, API hooks
│       └── lib/               # Types, API client
│
├── src/                       # Legacy Python modules (being replaced by server/)
│   ├── code_parser.py         # AST/regex chunker
│   ├── codebase_indexer.py    # Full codebase indexing
│   ├── embedding_generator.py # Client-side embeddings (legacy)
│   ├── vector_store.py        # Client-side vector store (legacy)
│   ├── text_chunker.py        # Text chunking (legacy)
│   ├── query_engine.py        # Local query engine
│   ├── mcp_server.py          # Legacy MCP server
│   └── ...                    # Various legacy modules
│
├── tests/                     # Pytest suite
│   ├── test_context_models.py
│   ├── test_context_service.py
│   ├── test_decision_extractor.py
│   ├── test_decision_service.py
│   ├── test_embedding_vector.py
│   ├── test_git_service.py
│   └── verify_dep_graph.py
│
├── rules/
│   └── compliance.yaml        # Compliance rules for code scanning
├── docs/                      # Documentation
│   ├── INDEX.md
│   ├── skills.md
│   └── screenshots/
├── config.toml                # Legacy TOML config
├── .env.example               # Environment variable template
├── requirements.txt           # Python dependencies
├── run.py                     # Entry-point script: uvicorn server.app:create_app
├── setup.py                   # pip-installable package (entry: cgctl)
└── PLAN.md                    # Context-YAML implementation plan
```

---

## Indexing Pipeline (2 Phases)

`POST /api/index` starts a background job:

| Phase | Work |
|-------|------|
| 1 | Walk files → chunk → NIM embeddings (batches of 32) → upsert to ChromaDB |
| 2 | Rebuild NetworkX knowledge graph from scratch → persist to `.codeguardian/knowledge_graph.json` |

Poll progress at `GET /api/index/status/{job_id}`. Phase 1 completes fast (code is immediately searchable); Phase 2 (knowledge graph) runs after.

---

## Core Services

### NIMClient (`server/services/llm_client.py`)
- Sole LLM interface. Raw `httpx` against NVIDIA NIM's OpenAI-compatible `/chat/completions` endpoint.
- Retry: 429 → exponential backoff (3 retries), 5xx → 1 retry, timeout → 1 retry with extended timeout.
- Supports streaming, thinking mode (`<think>` tag parsing), and warm-up pings.

### NIMEmbeddingService (`server/services/embedding_service.py`)
- 1024-dimensional embeddings from `nvidia/nv-embedqa-e5-v5`.
- Batches of 50, input_type="passage" (documents) or "query" (search).
- Deterministic IDs: `SHA256(project_id + file_path + chunk_index)`.

### VectorService (`server/services/vector_service.py`)
- ChromaDB PersistentClient (local only). No cloud dependency.
- Collections namespaced as `cg_{project_id}`.
- CRUD: `upsert()`, `search()`, `delete_project()`, `has_project_index()`, `get_project_index_count()`.

### KnowledgeGraph (`server/services/knowledge_graph.py`)
- NetworkX `DiGraph` with node types: `file`, `function`, `decision`, `author`, `module`.
- Edge types: `imports`, `contains`, `decided_by`, `affects`, `owns`, `belongs_to`.
- Always rebuilt from scratch (never patched incrementally).
- Persisted to `.codeguardian/knowledge_graph.json`.
- AST-based Python import resolution; regex-based JS/TS import resolution.

### GitService (`server/services/git_service.py`)
- Wraps GitPython for `git blame`, `git log`, `git diff`.
- Builds expertise maps: aggregates blame entries per author, sorted by commit count.
- Persisted to local `.codeguardian/expertise/` JSON.

### DecisionExtractor (`server/services/decision_extractor.py`)
- LLM parses the last 50 commits to extract structured architectural decisions.
- Each decision has: title, decision, context, reasoning, author, source_ref.

### ImpactEngine (`server/services/impact_engine.py`)
- Traverses the knowledge graph to compute blast-radius reports.
- Uses BFS on reversed import graph with risk scoring.

### ContextService (`server/services/context_service.py` — NEW)
- Manages `.context.yaml` files per directory.
- `analyze_directory()`: lists files/subdirs, gets git history, calls LLM for description.
- `update_on_changes()`: reads existing context, appends staged/unstaged/committed changes.
- `search_contexts()`: hybrid path + keyword search over YAML files.
- In-memory LRU cache of parsed contexts.

### RetrievalService (`server/services/retrieval_service.py` — NEW)
- Complements vector-based retrieval with context-YAML retrieval.
- `retrieve_for_query()`: finds relevant `.context.yaml` files, extracts matching sections.
- `build_context_prompt()`: formats context for QnA LLM consumption.
- Keyword extraction with stopword filtering.

### ChatHistoryService (`server/services/chat_history_service.py` — NEW)
- Persists CG-pilot chat sessions to `.codeguardian/chat_history/{project_id}/{session_id}.json`.
- `create_session()` / `append_message()` / `get_sessions()` / `get_session()` / `delete_session()` / `get_recent()`.
- Sessions auto-created on first `/api/cg-pilot/chat` call; subsequent calls pass `session_id` to continue.
- `get_recent()` feeds the Dashboard "Recent Questions" widget.

---

## LangGraph Agents

### ReviewAgent (`server/agents/review_agent.py`)
**Pipeline:** `parse_input → pattern_check → impact_analysis → security_scan → synthesize`
- **pattern_check**: Compares naming, error handling, logging against similar functions.
- **security_scan**: Detects hardcoded secrets, SQL injection, path traversal, PII in logs.
- **impact_analysis**: Uses ImpactEngine for blast-radius data.
- **synthesize**: LLM combines findings into a ranked `ReviewReport`.

### OnboardingAgent (`server/agents/onboarding_agent.py`)
**Pipeline:** `parse_task → find_relevant_code → gather_context → generate_path`
- Converts a plain-text task description into an ordered learning path.
- Enriched with architectural decisions and expert contacts from the KG.

---

## MCP Server (`server/mcp_server.py`)

**9 Tools** exposed to MCP-compatible AI assistants:

| Tool | Description |
|------|-------------|
| `query_codebase` | Natural-language Q&A with sources, decisions, experts |
| `get_context_for_file` | Full context: purpose, owners, decisions, dependents |
| `get_decision_history` | Architectural decisions + git commit timeline |
| `get_expertise` | Ranked contributors with commit counts and ownership % |
| `analyze_impact` | Blast-radius report with risk scores, reviewers |
| `review_code` | Git working tree review (staged/unstaged/untracked) |
| `check_compliance` | Deprecated — migrated to review_code |
| `generate_onboarding_path` | Ordered learning path for new tasks |
| `check_breaking_changes` | AST-based API breaking change detection |

All tools are thin HTTP proxies to the FastAPI server — no direct DB/LLM access.

---

## API Routes Summary

| Method | Route | Description |
|--------|-------|-------------|
| GET | `/api/health` | Server + service health status |
| POST | `/api/ask` | RAG Q&A with sources, decisions, experts |
| POST | `/api/ask/stream` | SSE streaming Q&A |
| POST | `/api/index` | Start 2-phase indexing job |
| GET | `/api/index/status/{job_id}` | Index job progress |
| GET | `/api/index/projects` | List indexed projects |
| GET | `/api/analyze/expert` | File expert analysis |
| GET | `/api/analyze/history` | File git history |
| GET | `/api/analyze/overview` | File overview |
| POST | `/api/impact/analyze` | Blast-radius analysis |
| POST | `/api/impact/breaking-changes` | AST breaking change detection |
| POST | `/api/review/status` | Git working tree review |
| POST | `/api/review/webhook` | GitHub webhook handler |
| POST | `/api/onboard/generate` | Learning path generation |
| POST | `/api/context/analyze` | Generate .context.yaml for a directory |
| GET | `/api/context/{dir}` | Get directory context |
| POST | `/api/context/update` | Update context with changes |
| DELETE | `/api/context/{dir}` | Delete context file |
| POST | `/api/context/search` | Search context files |
| GET | `/api/context/validate/all` | Validate all context files |
| GET | `/api/context/files/list` | List all context files |
| POST | `/api/cg-pilot/chat` | CG-pilot agent chat (auto-creates sessions) |
| GET | `/api/cg-pilot/status/{project_id}` | CG-pilot readiness check |
| GET | `/api/cg-pilot/history/{project_id}` | List chat sessions for a project |
| GET | `/api/cg-pilot/history/{project_id}/{session_id}` | Get full session with messages |
| DELETE | `/api/cg-pilot/history/{project_id}/{session_id}` | Delete a chat session |
| GET | `/api/dashboard/{project_path}` | Dashboard aggregated data |

---

## CLI Commands (`cgctl`)

| Command | Description |
|---------|-------------|
| `cgctl init` | Initialize CodeGuardian project |
| `cgctl index` | Index codebase into vector store |
| `cgctl ask` | Natural-language Q&A |
| `cgctl context` | Get file context (owners, decisions, dependents) |
| `cgctl impact` | Show blast radius for a changed file |
| `cgctl review` | Multi-stage code review |
| `cgctl onboard` | Generate learning path for a task |
| `cgctl health` | Check server health |
| `cgctl serve` | Start FastAPI server (optionally MCP mode) |
| `cgctl config` | Manage project configuration |
| `cgctl audit` | Run code audit |
| `cgctl hooks` | Install/uninstall git hooks |

Global flags: `--offline` (direct Python imports, no HTTP), `--api-url` (default: http://localhost:8742)

---

## Desktop App (Electron + React + Vite)

Pages:
- `/` — Dashboard (project overview, health, activity)
- `/ask` — Q&A with source citations
- `/graph` — D3.js interactive knowledge graph
- `/files` — File Explorer with impact analysis sidebar
- `/review` — Commit review and commit flow
- `/onboard` — Learning path generator
- `/indexing` — Index job kickoff and monitoring
- `/settings` — Server URL, project config

Architecture: Electron main process exposes `window.cgctl` IPC bridge (selectDirectory). React renderer makes HTTP calls to FastAPI :8742 — no direct Python access.

---

## Context-YAML System (PLAN.md)

A major architectural shift is underway to move from vector-embedding-based indexing to a self-documenting `.context.yaml` system. Key differences:

| Vector Chunking | Context YAML |
|-----------------|--------------|
| Lose file relationships | Preserves directory structure |
| Lose intent/context | LLM explains purpose |
| Fragments git history | Git-integrated by design |
| Needs full reindex | Incrementally updated |
| Bloated retrieval | Targeted, focused |
| Hard to debug | Human-readable/editable |

**Schema** (`.context.yaml`):
```yaml
directory: src/api
description: "REST API layer handling HTTP requests and responses."
files:
  - name: routes.py
    purpose: FastAPI route definitions
    type: api
    key_apis: [create_user, get_user]
subdirectories:
  - name: v1
    purpose: API version 1 (deprecated)
changes:
  recent:
    - commit: abc123
      message: "Added pagination"
      files: [routes.py]
      date: "2025-01-15T10:30:00Z"
      author: john@example.com
  staged: [...]
  unstaged: [...]
```

Implementation is planned in 6 phases: Foundation → LLM Integration → Git Integration → Triggers (hooks) → Retrieval → Cleanup (remove vector code).

---

## Configuration

**Primary**: Environment variables + `.env` file (via pydantic-settings).

Key variables:
```env
NVIDIA_NIM_API_KEY=nvapi-...        # Required for LLM + embeddings
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_LLM_MODEL=openai/gpt-oss-120b
NVIDIA_EMBED_MODEL=nvidia/nv-embedqa-e5-v5
SERVER_HOST=0.0.0.0
SERVER_PORT=8742
CHROMADB_PERSIST_DIR=./chroma_data
SUPABASE_URL=...                     # Optional
SUPABASE_KEY=...                     # Optional
LOG_LEVEL=INFO
```

**Legacy**: `config.toml` (used by old `src/` modules).

---

## Data Storage

| Data | Storage |
|------|---------|
| Vector embeddings | ChromaDB (`./chroma_data/`) |
| Knowledge graph | `.codeguardian/knowledge_graph.json` |
| Expertise maps | `.codeguardian/expertise/expertise_map.json` |
| Architectural decisions | Local `.codeguardian/decisions/` JSON |
| Chat history (CG-pilot) | `.codeguardian/chat_history/` JSON per session |
| Context-YAML files | `.context.yaml` in each directory (checked into git) |

---

## Key Dependencies

**Python**: fastapi, uvicorn, pydantic-settings, httpx, chromadb, supabase, gitpython, networkx, langgraph, typer, rich, tree-sitter, pyyaml, radon

**Node (desktop-app)**: react, react-router-dom, d3, lucide-react, react-markdown, electron, vite, tailwindcss, typescript

---

## Development Status

- Core RAG pipeline (embedding + vector search + KG enrichment + LLM answer) is functional.
- Context-YAML system (Phase 1-2 implementation) is partially complete — `ContextService`, `RetrievalService`, data models, and API routes exist.
- Git hooks (`cgctl hooks install`) are implemented.
- PLAN.md outlines the full migration from vector-based to context-YAML-based architecture.
- Tests exist for context models, context service, decision extractor/service, embedding/vector, and git service.

---

## Session Log

### Session: Indexing pipeline cleanup + Supabase removal

**Supabase removed:** `vector_service.py` stripped of all Supabase code — now ChromaDB-only with `has_project_index()`, `get_project_index_count()`, `delete_project()`. `config.py` still has unused `supabase_url`/`supabase_key` (harmless). `decision_service.py` and `knowledge_graph.py` still have benign `supabase_client=None` fallbacks.

**Indexing pipeline reduced to 2 phases:**
| Phase | Work |
|-------|------|
| 1 | Walk files → chunk → NIM embeddings (batches of 32) → upsert to ChromaDB |
| 2 | Rebuild NetworkX knowledge graph → persist to `.codeguardian/knowledge_graph.json` |

Removed Phase 2 (expertise mapping via `git blame`) and Phase 3 (LLM decision extraction from last 50 commits). `IndexStatus` schema simplified accordingly — removed `expertise_status`, `expertise_files_mapped`, `decision_status`, `decisions_commits_processed`, `decisions_found`. CLI (`cgctl/index.py`) updated to 2-phase display. Scratch file `rewrite_indexing.js` deleted.

**New endpoints:**
- `GET /api/index/estimate/{project_id}` — pre-index file count, chunk estimate by extension and directory
- `GET /api/index/history/{project_id}` / `DELETE /api/index/history/{project_id}` — per-project index history persisted to `.codeguardian/index_history/`
- `DELETE /api/index/{project_id}` — delete entire project index from ChromaDB
- `GET /api/index/check/{project_id}` — check if already indexed, return chunk count

**Frontend changes:**
- **Indexing.tsx**: 3-tab file selector (By File Type / By Extension / By Directory) with real-time selected files/chunks count. Delete Index button. History accordion loading from backend. **Bug fix**: added `setIsIndexing(false)` + `setCurrentFile(null)` on completion so the processing view transitions back to idle. Added `setCurrentFile(status.current_file)` during polling for live file progress.
- **Dashboard.tsx**: Replaced stale "Decisions Captured" → "Graph Nodes", "Experts Mapped" → "Graph Edges". Removed unused `Users` import. Label "Files Indexed" → "Total Files".
- **dashboard.py**: Updated docstrings to remove stale metric descriptions.

**Docstring cleanup**: `indexing.py` module header, `_phase1_index_code` return doc, and `start_indexing` endpoint doc all updated from "4-phase" / "expertise + decision extraction" references to the current 2-phase pipeline.

---

### Session: CG-pilot context awareness + chat history + FileTree bugfix

**Context-aware CG-pilot:** The CG-pilot chatbot now accepts an optional `file_context` parameter with a `file_path` relative to the project root. The backend reads the file content from disk and injects it into the LLM context. The desktop app's `ProjectContext` gained `selectedFilePath`/`setSelectedFilePath` state. `FileExplorer` sets this on file select; `CGPilot` reads it and shows a removable file chip above the text input. Users can dismiss the chip per-file without affecting future file selections.

**Chat history persistence:** CG-pilot conversations are now persisted to `.codeguardian/chat_history/{project_id}/{session_id}.json`. The `ChatHistoryService` (new) manages sessions. The `/api/cg-pilot/chat` endpoint auto-creates sessions (with `session_id` returned) or continues existing ones. Three new endpoints: `GET /api/cg-pilot/history/{project_id}` (list), `GET /api/cg-pilot/history/{project_id}/{session_id}` (detail), `DELETE /api/cg-pilot/history/{project_id}/{session_id}`.

**CGPilot component updated:**
- Chat History button (clock icon) toggles a panel showing all previous sessions with message counts
- Clicking a session loads its full message history
- New Chat button (`+`) starts a fresh session
- Hover-to-reveal delete button on each history entry
- Dashboard "Recent Questions" section wired up with real data from backend
- Clicking a recent question dispatches a custom event (`cg-open-session`) that opens CGPilot with that session loaded

**FileTree bugfix:** `FileExplorer.tsx` was passing a flat file list from `window.cgctl.listFiles` to `FileTree`, which expects a nested tree with `children` on directories. Fixed by building a tree via two-pass Map-based parent resolution.

**Backend schemas updated:** `CGPilotRequest` gains `session_id` and `file_context` (optional). `CGPilotResponse` gains `session_id`. New schemas: `FileContextSchema`, `ChatSessionSummary`, `ChatSessionDetail`, `ChatHistoryListResponse`, `DeleteSessionResponse`, `RecentQuestion`.
