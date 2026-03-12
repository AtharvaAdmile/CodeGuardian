Current Build Status
<!-- UPDATE THIS SECTION after each build completion -->

 Build 1: FastAPI Server Skeleton
 Build 2: LLM Client (NIM API)
 Build 3: Embedding Service + Vector Store
 Build 4: Supabase Schema
 Build 5: Port MCP Tools to FastAPI Routes
 Build 6: Electron Migration (spawn → HTTP)
 Build 7: Git History + Decision Extraction
 Build 8: Knowledge Graph (NetworkX)
 Build 9: Context-Enriched Query Engine
 Build 10: MCP Server Tools
 Build 11: Dependency Graph (tree-sitter)
 Build 12: Blast Radius Calculator + API
 Build 13: Onboarding Agent
 Build 14: Multi-Agent Review Pipeline
 Build 15: CLI Upgrade (cgctl v3)
 Build 16: End-to-End Testing

Active Decisions Log
<!-- When architectural decisions are made during builds, log them here briefly -->
<!-- Format: [DATE] DECISION: reason -->
Known Issues
<!-- Track bugs/issues discovered during builds -->
Key File Locations (Quick Reference)

LLM Client: server/services/llm_client.py
Embedding Service: server/services/embedding_service.py
Vector Service: server/services/vector_service.py
Knowledge Graph: server/services/knowledge_graph.py
Impact Engine: server/services/impact_engine.py
Config: server/config.py → reads .env
Build prompts: @docs/build_prompts.md (reference when building features)
Skills reference: @docs/skills.md (reference for implementation patterns)
