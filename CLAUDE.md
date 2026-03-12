# CodeGuardian — Project Memory

## What This Project Is
CodeGuardian is an AI-powered institutional memory system for codebases. It preserves and surfaces engineering context (the "why" behind code decisions) so developers — whether they joined yesterday or five years ago — can make confident decisions.

## Core Mission (Never Deviate)
Every feature must serve ONE goal: reduce the 40-60% of developer time lost to context reconstruction, knowledge silos, and impact blindness.

## Tech Stack (Canonical)
- **API Server:** FastAPI + Uvicorn (server/ directory, port 8742)
- **LLM:** NVIDIA NIM API exclusively — model: `qwen/qwen3-coder-480b-a35b-instruct`
- **Embeddings:** NVIDIA NIM — model: `nvidia/nv-embedqa-e5-v5` (1024 dimensions)
- **Vector Store:** ChromaDB (local) + Supabase pgvector (team sharing), dual-write
- **Knowledge Graph:** NetworkX (in-memory) + JSON persistence. NO Neo4j.
- **Agent Framework:** LangGraph (from langgraph package)
- **Desktop App:** Electron + React + Vite + D3.js (desktop-app/ directory)
- **CLI:** Typer + Rich (cgctl/ directory)
- **MCP Server:** Python MCP SDK (server/mcp_server.py)
- **AST Parsing:** tree-sitter (Python), regex fallback (JS/TS)
- **Git Analysis:** GitPython
- **DB:** Supabase PostgreSQL 16 with pgvector extension

## Hard Rules
- ALL LLM calls go through NIM API via server/services/llm_client.py. No local models. No Ollama. No OpenAI SDK.
- ALL embeddings are 1024-dimensional from NIM. No sentence-transformers. No torch for inference.
- Vector IDs are deterministic: SHA256(project_id + file_path + chunk_index). Same ID in ChromaDB AND Supabase.
- Knowledge graph is rebuilt from scratch on every index (never incremental patch — causes ghost edges).
- Supabase is always OPTIONAL. Every feature must work with ChromaDB-only (offline mode).
- No Jira integration. Task input is always plain text.
- When Qwen3-Coder returns `<think>...</think>` tags, strip them unless thinking_mode=True was explicitly set.
- NIM rate limits: retry 429 with exponential backoff (2s, 4s, 8s). Max 3 retries.

## Directory Structure
server/                    # FastAPI backend (THE hub — all clients talk to this)
  app.py                   # App factory + lifespan
  config.py                # Pydantic Settings from .env
  routes/                  # REST endpoints
  services/                # Business logic (llm_client, vector_service, embedding_service, etc.)
  agents/                  # LangGraph agents (review, onboarding, impact, context)
  models/                  # Pydantic schemas
cgctl/                     # CLI (Typer + Rich)
desktop-app/               # Electron + React
  electron/                # Main process + preload
  src/                     # React renderer
docs/                      # Reference docs (skills.md, architecture, etc.)
tests/                     # pytest test suite
.codeguardian/             # Per-project config + cached data
