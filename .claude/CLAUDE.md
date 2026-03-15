# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is
CodeGuardian is an AI-powered institutional memory system for codebases. It preserves and surfaces engineering context (the "why" behind code decisions) so developers can make confident decisions without reconstructing context from scratch.

## Development Commands

### Backend (FastAPI server)
```bash
# Start the server (required before using CLI commands)
uvicorn server.app:app --host 0.0.0.0 --port 8742

# Or via CLI
python -m cgctl.main serve

# Dev mode with auto-reload
python -m cgctl.main serve --reload
```

### CLI (cgctl)
```bash
python -m cgctl.main <command>

# Key commands:
python -m cgctl.main index /path/to/project   # Index a codebase
python -m cgctl.main ask "your question"       # Query the codebase
python -m cgctl.main context <file>            # Get file context
python -m cgctl.main impact <file>             # Blast radius analysis
python -m cgctl.main review <file>             # Code review
python -m cgctl.main onboard "task description" # Learning path
python -m cgctl.main health                    # Server health check

# MCP server modes
python -m cgctl.main serve --mcp               # stdio mode
python -m cgctl.main serve --mcp-sse           # SSE mode (port 8743)
```

### Desktop App
```bash
cd desktop-app
npm install
npm run dev          # Vite + Electron (requires server on :8742)
npm run build        # Production build
npm run typecheck    # TypeScript check
```

### Tests
```bash
pytest                                          # All tests
pytest tests/test_decision_service.py          # Single test file
pytest tests/ -k "test_embedding"              # Filter by name
pytest --asyncio-mode=auto                     # For async tests
```

### Environment Setup
Copy `.env.example` to `.env` and set:
```
NVIDIA_NIM_API_KEY=nvapi-...
SUPABASE_URL=https://...          # Optional
SUPABASE_KEY=...                   # Optional
CHROMADB_PERSIST_DIR=./chroma_data
```

## Architecture Overview

### Client-Server Hub Pattern
All three clients (CLI, Desktop App, MCP Server) are thin HTTP clients that talk exclusively to the FastAPI backend on port 8742. No client does any LLM or embedding work directly — everything routes through `server/`.

```
cgctl CLI ──────────────┐
Desktop Electron App ───┼──→  FastAPI server (:8742) ──→ NVIDIA NIM API
MCP Server (stdio/SSE) ─┘         │
                                   ├──→ ChromaDB (local)
                                   ├──→ Supabase pgvector (optional)
                                   └──→ .codeguardian/ (JSON persistence)
```

### Indexing Pipeline (4-Phase)
`POST /api/index` starts a background job. Phase 1 completes fast (code is immediately searchable); Phases 2–4 run concurrently in the background:

1. **Phase 1** — Walk files → AST chunk (Python) or regex chunk (JS/TS) → NIM embeddings (batches of 32) → upsert to ChromaDB + Supabase
2. **Phase 2** — `git blame` → expertise map (author → files)
3. **Phase 3** — Last 50 commits → LLM decision extraction → stored in DecisionService
4. **Phase 4** — Rebuild NetworkX knowledge graph from scratch → persist to `.codeguardian/knowledge_graph.json`

Poll progress at `GET /api/index/status/{job_id}`.

### LLM Layer (`server/services/llm_client.py`)
`NIMClient` is the sole LLM interface. It uses raw `httpx` (no openai SDK) against NVIDIA NIM's OpenAI-compatible endpoint. Retry policy: 429 → exponential backoff (1s × 2^n + jitter, max 3 retries); 5xx → 1 retry after 2s; timeout → 1 retry at 90s. Always strip `<think>…</think>` tags from responses unless `thinking_mode=True`.

### Vector IDs
Vector chunk IDs are deterministic: `SHA256(project_id + file_path + chunk_index)`. The same ID is used in both ChromaDB and Supabase — enabling safe upserts without duplicates.

### Knowledge Graph (`server/services/knowledge_graph.py`)
NetworkX `DiGraph` with node types: `file`, `function`, `decision`, `author`, `module`. Edge types encode relationships (`imports`, `contains`, `owns`, `affects`, `decided_by`, `belongs_to`). Always rebuilt from scratch on index — never incrementally patched. Persisted to `.codeguardian/knowledge_graph.json`; loaded at server startup.

### LangGraph Agents (`server/agents/`)
Two agents built with LangGraph:
- **ReviewAgent** (`review_agent.py`) — linear pipeline: `parse_input → pattern_check → impact_analysis → security_scan → synthesize`. Checks security patterns, complexity via `radon`, blast radius via the knowledge graph, and synthesizes findings via LLM.
- **OnboardingAgent** (`onboarding_agent.py`) — linear pipeline: `parse_task → find_relevant_code → gather_context → generate_path`. Converts a plain-text task description into an ordered learning path.

### App State (`server/app.py` lifespan)
All shared services are stored on `app.state` during startup: `llm_client`, `embedding_service`, `vector_service`, `decision_service`, `decision_extractor`, `knowledge_graph`, `index_jobs`. Routes access them via `request.app.state`. Services are `None` if their prerequisites (e.g., `NVIDIA_NIM_API_KEY`) are absent — all features must degrade gracefully.

### CLI Architecture (`cgctl/`)
`cgctl/main.py` is the Typer entry point. Global `--offline` and `--api-url` flags are stored in `cgctl/state.py` singleton. Commands in `cgctl/commands/` call `cgctl/client.py` (`CGClient`, synchronous httpx) in connected mode, or fall back to direct Python imports in `--offline` mode. All output uses `cgctl/utils/output.py` (Rich console helpers).

### Desktop App (`desktop-app/`)
Electron + React + Vite. Electron main process in `electron/main.ts`. React renderer in `src/`. Uses `react-router-dom` for routing, D3.js for graph visualisation, Tailwind CSS + Framer Motion for UI.

## Hard Rules
- ALL LLM calls go through `server/services/llm_client.py`. No local models, no Ollama, no OpenAI SDK.
- ALL embeddings are 1024-dimensional from NIM (`nvidia/nv-embedqa-e5-v5`). No sentence-transformers, no torch.
- Vector IDs are deterministic SHA256. Same ID in ChromaDB AND Supabase.
- Knowledge graph is always rebuilt from scratch on index — never incrementally patched.
- Supabase is always OPTIONAL. Every feature must work ChromaDB-only (offline mode).
- Strip `<think>…</think>` from LLM output unless `thinking_mode=True` was explicitly requested.
- `project_id` convention: `Path(project_path).name` (directory name) unless overridden.
- Indexed file types: `.py`, `.js`, `.ts`, `.jsx`, `.tsx`. Skipped dirs: `node_modules`, `__pycache__`, `.git`, `venv`, `dist`, `build`.

## MCP Server Setup

Add to Claude Code MCP config (`~/.claude/mcp_servers.json`):
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

Available tools: `query_codebase`, `get_context_for_file`, `get_decision_history`, `get_expertise`.
