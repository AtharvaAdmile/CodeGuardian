# Project Memory

## Project Overview
**CodeGuardian** — A local-first code analysis and context retrieval system for AI assistants. Provides RAG-based code understanding, automated test generation, dependency analysis, compliance checking, and tech debt tracking via an MCP server.

## Tech Stack
- Frontend: React + TypeScript (Vite)
- Backend: Python (FastAPI / MCP Server)
- Database: ChromaDB (vector store), SQLite (metadata)
- Other: Radon (complexity analysis), Git integration, pytest

## Architecture
CodeGuardian operates as an MCP (Model Context Protocol) server that exposes code analysis tools to AI assistants. It indexes codebases into a vector store for semantic search, analyzes dependencies and complexity, generates unit tests, checks compliance, and tracks tech debt — all running locally without external API calls.

## Features Built
| Feature | Status | Notes |
|---------|--------|-------|
| MCP Server | ✅ Built | Core server exposing tools via MCP protocol |
| Codebase Indexing | ✅ Built | Semantic search via ChromaDB |
| Dependency Analysis | ✅ Built | File-level and project-level dependency graphs |
| Tech Debt Health | ✅ Built | Complexity + churn scoring |
| Compliance Checking | ✅ Built | PII, secrets, dangerous functions |
| Regulatory Compliance | ✅ Built | FDA, ISO, IEC standards |
| Unit Test Generation | ✅ Built | AI-powered pytest/jest generation |
| Documentation Gaps | ✅ Built | Detects undocumented code elements |
| File History | ✅ Built | Git blame and commit history |
| File Expert | ✅ Built | Identifies code owners via git |
| Runtime Stats | ✅ Built | Production metrics integration |
| Structure Analysis | ✅ Built | Project organization scoring |

## Implementation Log
### 2026-05-06 - Bug Fixes
- Fixed 11 code issues across the codebase
- Critical: query.py regex substitution, indexing.py type safety, git_service.py timezone
- Memory: decision_service.py now limits local search to 1000 decisions
- Added warmup task tracking for proper server shutdown

### 2026-03-12 - Project Management Setup
- Created `Memory.md` and `Skills.md` for project tracking
- Key decisions: Established living documentation workflow
- Files created: `Memory.md`, `Skills.md`

## Current State
CodeGuardian MCP server is functional with all core analysis tools operational. The system can index codebases, analyze dependencies, check compliance, generate tests, and track tech debt.

## Known Issues / TODOs
- [ ] Review and update any stale documentation
- [ ] Verify all MCP tools are properly registered
- [ ] Add integration tests for end-to-end workflows

## Environment & Config
- MCP server runs locally
- ChromaDB stores vector embeddings in local directory
- Git must be available in PATH for history/expert features
- No external API keys required for core functionality
