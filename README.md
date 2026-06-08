<div align="center">

# CodeGuardian

**AI-powered institutional memory for your codebase**

*Stop reconstructing context. Start shipping with confidence.*

<br/>

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Node.js](https://img.shields.io/badge/Node.js-18+-339933?style=flat-square&logo=node.js&logoColor=white)](https://nodejs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Electron](https://img.shields.io/badge/Electron-28+-47848F?style=flat-square&logo=electron&logoColor=white)](https://electronjs.org)
[![React](https://img.shields.io/badge/React-18+-61DAFB?style=flat-square&logo=react&logoColor=black)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.0+-3178C6?style=flat-square&logo=typescript&logoColor=white)](https://typescriptlang.org)

[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA_NIM-Powered-76b900?style=flat-square&logo=nvidia&logoColor=white)](https://build.nvidia.com)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agents-FF6B35?style=flat-square)](https://langchain-ai.github.io/langgraph/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-8B5CF6?style=flat-square)](https://modelcontextprotocol.io)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-Vector_Store-E76F51?style=flat-square)](https://www.trychroma.com)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

[![Stars](https://img.shields.io/github/stars/AtharvaAdmile/CodeGuardian?style=flat-square&color=gold)](https://github.com/AtharvaAdmile/CodeGuardian/stargazers)
[![Issues](https://img.shields.io/github/issues/AtharvaAdmile/CodeGuardian?style=flat-square)](https://github.com/AtharvaAdmile/CodeGuardian/issues)
[![Last Commit](https://img.shields.io/github/last-commit/AtharvaAdmile/CodeGuardian?style=flat-square)](https://github.com/AtharvaAdmile/CodeGuardian/commits)

</div>

---

## What is CodeGuardian?

Every codebase accumulates invisible knowledge — why that authentication middleware exists, who truly owns the payment module, what breaks if you touch `vector_service.py`. This knowledge lives in developers' heads and Slack threads, not in the code itself.

**CodeGuardian captures and surfaces that institutional memory.** Index your codebase once and get:

- Natural-language answers grounded in actual code, commits, and architecture decisions
- A knowledge graph of who owns what and how files depend on each other  
- Compliance scans, blast-radius analysis, and agentic code review — all via a CLI, desktop app, or directly from your AI assistant

Everything routes through a single **FastAPI hub on port 8742**. The CLI, the Electron desktop app, and the MCP server are all thin HTTP clients — no LLM or embedding work happens client-side.

---

## Feature Highlights

| Feature | Description |
|---------|-------------|
| **CG-Pilot Chat** | In-app AI assistant with multi-turn conversations, tool use, and context-aware codebase Q&A |
| **Knowledge Graph** | NetworkX `DiGraph` linking files, functions, decisions, authors, and modules — rebuilt on every index |
| **Decision Extraction** | LLM parses the last 50 commits to extract and store architectural decisions |
| **Blast-Radius Analysis** | Identifies which files transitively depend on a changed file and their risk scores |
| **Expertise Mapping** | `git blame` + commit analysis to rank who knows each file best |
| **Compliance Scans** | Agentic security scan: secrets, SQL injection, PII, GDPR, HIPAA, dangerous functions |
| **Code Review Agent** | LangGraph pipeline: security patterns → complexity → blast radius → synthesized report |
| **Onboarding Paths** | Converts a plain-text task description into an ordered learning path |
| **Commit Review** | Git history, working-tree diff, commit readiness score, and one-click commit flow |
| **MCP Integration** | 9 tools exposed to Claude Code, Claude Desktop, or any MCP-compatible assistant |
| **Offline CLI** | `--offline` flag bypasses HTTP and imports Python services directly |

---

## Architecture

```
cgctl CLI ──────────────┐
Desktop Electron App ───┼──→  FastAPI server (:8742) ──→ NVIDIA NIM API
MCP Server (stdio/SSE) ─┘         │                        (LLM + Embeddings)
                                   │
                                   ├──→ ChromaDB          (local vector store)
                                   ├──→ NetworkX Graph     (in-memory + JSON)
                                   └──→ .codeguardian/     (decisions, chat, impact)
```

### Indexing Pipeline

`POST /api/index` launches a background job. Phase 1 completes fast (code is immediately searchable); Phases 2–4 run concurrently:

| Phase | What runs |
|-------|-----------|
| **1** | Walk files → AST/regex chunk → NIM embeddings (batches of 32) → upsert ChromaDB |
| **2** | `git blame` → build author expertise map |
| **3** | Last 50 commits → LLM extracts architectural decisions → stored in DecisionService |
| **4** | Rebuild NetworkX knowledge graph → persist to `.codeguardian/knowledge_graph.json` |

Poll progress: `GET /api/index/status/{job_id}`

---

## Project Structure

```
CodeGuardian/
├── server/                         # FastAPI backend (the hub)
│   ├── app.py                      # Application factory + lifespan
│   ├── config.py                   # Pydantic-settings config
│   ├── mcp_server.py               # Standalone MCP server (stdio / SSE)
│   ├── agents/
│   │   ├── review_agent.py         # LangGraph: security + complexity review
│   │   └── onboarding_agent.py     # LangGraph: task → learning path
│   ├── routes/
│   │   ├── health.py
│   │   ├── indexing.py
│   │   ├── query.py
│   │   ├── analysis.py
│   │   ├── analysis_extended.py
│   │   ├── impact.py
│   │   ├── review.py
│   │   ├── compliance.py
│   │   └── onboarding.py
│   └── services/
│       ├── llm_client.py           # NIMClient — sole LLM interface
│       ├── embedding_service.py    # NIMEmbeddingService (1024-dim)
│       ├── vector_service.py       # ChromaDB local vector store
│       ├── knowledge_graph.py      # NetworkX DiGraph builder
│       ├── decision_service.py     # Store / retrieve architectural decisions
│       ├── decision_extractor.py   # LLM extracts decisions from git log
│       ├── git_service.py          # git blame, log, diff helpers
│       ├── impact_engine.py        # Blast-radius calculator
│       └── chat_history_service.py # CG-pilot chat persistence
│
├── cgctl/                          # CLI (thin HTTP client + offline fallback)
│   ├── main.py                     # Typer entry point
│   ├── client.py                   # CGClient (synchronous httpx)
│   ├── state.py                    # Global --offline / --api-url flags
│   └── commands/                   # index, ask, context, impact, review, onboard…
│
├── desktop-app/                    # Electron + React 18 + Vite + TypeScript
│   ├── electron/main.ts            # Electron main process + IPC bridge
│   └── src/
│       ├── App.tsx                 # Router + ProjectContext
│       ├── pages/                  # Dashboard, FileExplorer, KnowledgeGraph,
│       │                           #   Indexing, Compliance, CommitReview, Settings
│       ├── components/
│       │   ├── CGPilot.tsx         # Floating AI chat panel
│       │   ├── layout/             # Sidebar, TopBar, StatusBar, CommandPalette
│       │   └── shared/             # FileTree, LoadingSpinner, …
│       └── lib/
│           ├── api.ts              # All HTTP calls to :8742
│           └── types.ts            # Shared TypeScript interfaces
│
└── tests/                          # pytest suite
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/AtharvaAdmile/CodeGuardian.git
cd CodeGuardian

python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Open `.env` and set at minimum:

```env
# Required — all LLM and embedding calls
NVIDIA_NIM_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optional overrides
NVIDIA_NIM_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_LLM_MODEL=qwen/qwen3-coder-480b-a35b-instruct
NVIDIA_EMBED_MODEL=nvidia/nv-embedqa-e5-v5

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8742

# ChromaDB (local vector store)
CHROMADB_PERSIST_DIR=./chroma_data
```

Get a free NVIDIA NIM API key at [build.nvidia.com](https://build.nvidia.com).

### 3. Start the server

```bash
python -m cgctl.main serve
# or
uvicorn server.app:app --host 0.0.0.0 --port 8742
```

### 4. Index a codebase

```bash
python -m cgctl.main index /path/to/your/project
```

### 5. Ask questions

```bash
python -m cgctl.main ask "Why is authentication handled in middleware?"
python -m cgctl.main ask "Who owns the payment module?"
python -m cgctl.main context server/routes/query.py
python -m cgctl.main impact server/services/vector_service.py
```

---

## CLI Reference

All commands support `--offline` (direct Python imports, no HTTP) and `--api-url` (custom server URL).

### `cgctl serve`

```bash
python -m cgctl.main serve               # REST API on :8742
python -m cgctl.main serve --reload      # Dev mode with auto-reload
python -m cgctl.main serve --mcp         # MCP server (stdio)
python -m cgctl.main serve --mcp-sse     # MCP server (SSE on :8743)
```

### `cgctl index`

```bash
python -m cgctl.main index /path/to/project
```

Walks `.py`, `.js`, `.ts`, `.jsx`, `.tsx` files. Skips `node_modules`, `__pycache__`, `.git`, `venv`, `dist`, `build`.

### `cgctl ask`

```bash
python -m cgctl.main ask "How does the indexing pipeline work?"
python -m cgctl.main ask "What changed in the last sprint?"
```

### `cgctl context`

```bash
python -m cgctl.main context server/routes/query.py
```

Returns: file purpose, owners, architectural decisions, and dependent files.

### `cgctl impact`

```bash
python -m cgctl.main impact server/services/vector_service.py
```

Returns: transitive dependents, risk scores, and suggested reviewers.

### `cgctl review`

```bash
python -m cgctl.main review server/routes/indexing.py
python -m cgctl.main review --diff path/to/changes.diff
```

### `cgctl onboard`

```bash
python -m cgctl.main onboard "Add rate limiting to the API"
```

### `cgctl health`

```bash
python -m cgctl.main health
```

### `cgctl config`

```bash
python -m cgctl.main config show
python -m cgctl.main config set KEY VALUE
```

### `cgctl audit`

```bash
python -m cgctl.main audit
```

---

## Desktop App

A Material-TUI dark-theme Electron app with a full IDE-style layout.

### Running

```bash
# Server must be running on :8742 first
cd desktop-app
npm install
npm run dev          # Vite + Electron (development)
npm run build        # Production build
npm run typecheck    # TypeScript check
```

### Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Dashboard | Project overview, recent CG-Pilot queries, git activity log |
| `/graph` | Knowledge Graph | D3.js interactive graph of files, functions, decisions, authors |
| `/files` | File Explorer | Browse files with context sidebar and persisted impact analysis |
| `/indexing` | Indexing | Configure, launch, and monitor index jobs with live log stream |
| `/compliance` | Compliance | Agentic compliance scanner with real-time reasoning timeline |
| `/review` | Commit Review | Working-tree diff, commit history, and one-click commit action |
| `/settings` | Settings | Server URL, project path, preferences |

**CG-Pilot** is available on every page via the `>_ CG-PILOT` button in the bottom-right corner.

---

## MCP Integration

CodeGuardian exposes a full MCP server so AI assistants can query your codebase directly.

### Setup for Claude Code

Add to `~/.claude/mcp_servers.json`:

```json
{
  "mcpServers": {
    "codeguardian": {
      "command": "python",
      "args": ["-m", "server.mcp_server"],
      "cwd": "/path/to/CodeGuardian"
    }
  }
}
```

### Transport options

```bash
python -m server.mcp_server                    # stdio (default)
python -m server.mcp_server --sse              # SSE on :8743
python -m server.mcp_server --sse --port 9000  # custom port
```

### Available Tools

| Tool | Description |
|------|-------------|
| `query_codebase` | Natural-language Q&A with source citations, decisions, and expert contacts |
| `get_context_for_file` | Purpose, owners, architectural decisions, and dependents for any file |
| `get_decision_history` | All architectural decisions affecting a file + git timeline |
| `get_expertise` | Ranked contributors with commit counts and ownership percentage |
| `analyze_impact` | Blast-radius report: transitive dependents, risk scores, suggested reviewers |
| `review_code` | Full review: security patterns, complexity, blast radius, synthesized findings |
| `check_compliance` | Security scan: secrets, SQL injection, PII, GDPR, HIPAA, dangerous functions |
| `generate_onboarding_path` | Ordered learning path for a developer picking up a new task |
| `check_breaking_changes` | AST-based detection of removed functions, added required params, changed signatures |

---

## LangGraph Agents

### ReviewAgent

Pipeline: `parse_input → pattern_check → impact_analysis → security_scan → synthesize`

- Checks naming, error handling, and logging consistency vs similar functions in the codebase
- Detects hardcoded secrets, SQL injection, path traversal, PII logging
- Attaches blast-radius data from the knowledge graph
- LLM synthesizes all findings into a ranked `ReviewReport`

### OnboardingAgent

Pipeline: `parse_task → find_relevant_code → gather_context → generate_path`

Converts a plain-text task description into an ordered, numbered learning path enriched with architectural decisions and expert contacts from the knowledge graph.

---

## Server Services

All services live on `app.state`. They are `None` if prerequisites (e.g., `NVIDIA_NIM_API_KEY`) are absent — every feature degrades gracefully.

| Service | Role |
|---------|------|
| `NIMClient` | Sole LLM interface — raw `httpx` against NVIDIA NIM. Retry: 429 → exponential backoff (1s × 2ⁿ + jitter, max 3); 5xx → 1 retry after 2s; timeout → 1 retry at 90s |
| `NIMEmbeddingService` | 1024-dimensional embeddings from `nvidia/nv-embedqa-e5-v5` |
| `VectorService` | ChromaDB local store. IDs are deterministic `SHA256(project_id + file_path + chunk_index)` |
| `KnowledgeGraph` | NetworkX `DiGraph` — node types: `file`, `function`, `decision`, `author`, `module`. Always rebuilt from scratch on index |
| `DecisionService` | Store and retrieve architectural decisions. Limits to 1000 most recent to prevent memory issues |
| `DecisionExtractor` | LLM parses the last 50 commits to extract structured `ArchitecturalDecision` objects |
| `GitService` | `git blame`, `git log`, `git diff` helpers |
| `ImpactEngine` | Traverses the knowledge graph to compute transitive blast-radius reports |
| `ChatHistoryService` | Persists CG-Pilot sessions to `.codeguardian/chat_history/` |

---

## Running Tests

```bash
pytest                                    # All tests
pytest tests/test_decision_service.py    # Single file
pytest tests/ -k "test_embedding"        # Filter by name
pytest --asyncio-mode=auto               # Async tests
```

---

## Hard Rules

A few invariants the codebase enforces strictly:

- All LLM calls go through `server/services/llm_client.py` — no OpenAI SDK, no Ollama
- All embeddings are 1024-dimensional from NIM — no sentence-transformers, no torch
- Vector IDs are deterministic SHA256 — same ID in ChromaDB every time
- Knowledge graph is always rebuilt from scratch on index — never incrementally patched
- Supabase (pgvector) is always optional — every feature works ChromaDB-only

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit your changes following the existing commit style
4. Open a pull request with a clear description

Please open an issue before starting work on large changes.

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

Built with [NVIDIA NIM](https://build.nvidia.com) · [FastAPI](https://fastapi.tiangolo.com) · [LangGraph](https://langchain-ai.github.io/langgraph/) · [Electron](https://electronjs.org)

</div>
