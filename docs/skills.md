# CodeGuardian — Implementation Skills Reference

> This file contains reusable patterns and implementation skills for building CodeGuardian features.
> Reference with: @docs/skills.md when you need a pattern.
> This is NOT loaded every session — only when explicitly referenced.

---

## Skill: NVIDIA NIM API Call Pattern

Use this pattern for ALL LLM calls in the project.
```python
# Canonical NIM API call via httpx (never use openai SDK)
import httpx
import time

async def call_nim(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    thinking_mode: bool = False,
    nim_base_url: str = "https://integrate.api.nvidia.com/v1",
    api_key: str = "",
    model: str = "qwen/qwen3-coder-480b-a35b-instruct"
) -> dict:
    """Standard NIM API call. All LLM calls in the project use this pattern."""
    
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    if not thinking_mode:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(3):
            try:
                start = time.monotonic()
                resp = await client.post(
                    f"{nim_base_url}/chat/completions",
                    json=body,
                    headers=headers
                )
                latency = (time.monotonic() - start) * 1000
                
                if resp.status_code == 429:
                    wait = (2 ** attempt) + (random.random() * 0.5)
                    await asyncio.sleep(wait)
                    continue
                    
                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                
                # Strip thinking tags if present and thinking_mode is off
                if not thinking_mode and "<think>" in content:
                    import re
                    content = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL)
                
                return {"content": content, "latency_ms": latency, "model": model}
                
            except httpx.TimeoutException:
                if attempt < 2:
                    continue
                raise
```

---

## Skill: NIM Embedding Pattern
```python
async def embed_texts(
    texts: list[str],
    input_type: str = "passage",  # "passage" for documents, "query" for search queries
    nim_base_url: str = "https://integrate.api.nvidia.com/v1",
    api_key: str = "",
    model: str = "nvidia/nv-embedqa-e5-v5",
    batch_size: int = 50
) -> list[list[float]]:
    """Embed texts via NIM. Returns 1024-dim vectors. Batches automatically."""
    all_embeddings = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = await client.post(
                f"{nim_base_url}/embeddings",
                json={"model": model, "input": batch, "input_type": input_type},
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            )
            resp.raise_for_status()
            data = resp.json()
            all_embeddings.extend([item["embedding"] for item in data["data"]])
    
    return all_embeddings  # Each is 1024-dim float list
```

---

## Skill: Deterministic Vector ID Generation
```python
import hashlib

def generate_vector_id(project_id: str, file_path: str, chunk_index: int) -> str:
    """Deterministic ID used in BOTH ChromaDB and Supabase. Never changes for same input."""
    raw = f"{project_id}:{file_path}:{chunk_index}"
    return hashlib.sha256(raw.encode()).hexdigest()
```

---

## Skill: FastAPI Route with Service Access
```python
from fastapi import APIRouter, Request

router = APIRouter(prefix="/api")

@router.post("/ask")
async def ask_question(request: Request, body: AskRequest):
    """All routes access services via request.app.state — set during lifespan."""
    llm_client = request.app.state.llm_client
    vector_service = request.app.state.vector_service
    embedding_service = request.app.state.embedding_service
    knowledge_graph = request.app.state.knowledge_graph
    # ... use services
```

---

## Skill: SSE Streaming Response (FastAPI)
```python
from starlette.responses import StreamingResponse
import json

async def stream_answer(request: Request, body: AskRequest):
    async def event_generator():
        async for chunk in llm_client.complete(messages=messages, stream=True):
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
        
        yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## Skill: LangGraph Agent Pattern
```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional

class AgentState(TypedDict):
    project_id: str
    trigger: dict
    context: dict
    analysis: Optional[dict]
    output: Optional[dict]
    trace: list[str]  # Step log for explainability

def build_review_agent():
    graph = StateGraph(AgentState)
    
    graph.add_node("fetch_context", fetch_context_node)
    graph.add_node("analyze_patterns", analyze_patterns_node)
    graph.add_node("check_security", check_security_node)
    graph.add_node("synthesize", synthesize_node)
    
    graph.add_edge("fetch_context", "analyze_patterns")
    graph.add_edge("analyze_patterns", "check_security")
    graph.add_edge("check_security", "synthesize")
    graph.add_edge("synthesize", END)
    
    graph.set_entry_point("fetch_context")
    return graph.compile()
```

---

## Skill: Decision Extraction Prompt
```python
DECISION_EXTRACTION_SYSTEM_PROMPT = """You analyze git commit messages and PR comments to extract architectural decisions.

An architectural decision IS:
- A technology choice ("switched from REST to gRPC because...")
- A design pattern choice ("using repository pattern to isolate DB...")
- A constraint explanation ("timeout is 30s because downstream service X...")
- A tradeoff acknowledgment ("chose eventual consistency over strong because...")

An architectural decision is NOT:
- A bug fix, feature description, review nitpick, or merge commit

If NO architectural decision exists, respond: NONE

If a decision exists, respond in JSON only:
{"title": "...", "context": "...", "decision": "...", "reasoning": "..."}"""
```

Use with temperature=0.1, thinking_mode=False for speed.
Pre-filter: skip texts < 50 chars or matching /^(LGTM|looks good|\+1|nit:|fix(ed)?|merge|update|wip)/i

---

## Skill: ChromaDB + Supabase Dual Write
```python
async def dual_upsert(self, project_id, documents):
    """Write to ChromaDB always, Supabase if available. Never fail on Supabase errors."""
    # ChromaDB (must succeed)
    collection = self.chroma_client.get_or_create_collection(f"cg_{project_id}")
    collection.upsert(
        ids=[d.id for d in documents],
        documents=[d.text for d in documents],
        embeddings=[d.embedding for d in documents],
        metadatas=[d.metadata for d in documents]
    )
    
    # Supabase (best-effort)
    if self.supabase:
        try:
            rows = [{"id": d.id, "project_id": project_id, "file_path": d.metadata["file_path"],
                     "chunk_text": d.text, "embedding": d.embedding, ...} for d in documents]
            self.supabase.table("code_embeddings").upsert(rows).execute()
        except Exception as e:
            logger.warning(f"Supabase upsert failed (non-fatal): {e}")
```

---

## Skill: Supabase Vector Search via RPC
```python
async def search_supabase(self, project_id, query_embedding, top_k=10):
    """Call the match_code_embeddings Postgres function."""
    result = self.supabase.rpc("match_code_embeddings", {
        "query_embedding": query_embedding,  # list[float], 1024-dim
        "match_count": top_k,
        "filter_project_id": project_id
    }).execute()
    return result.data
```

---

## Skill: Knowledge Graph Query Patterns (NetworkX)
```python
import networkx as nx

# Get all files that depend on a changed file (reverse traversal)
def get_dependents(graph, file_path, max_depth=4):
    """Find all files that import this file, recursively."""
    dependents = []
    for node in nx.bfs_tree(graph.reverse(), file_path, depth_limit=max_depth):
        if node != file_path and graph.nodes[node].get("type") == "file":
            distance = nx.shortest_path_length(graph.reverse(), file_path, node)
            dependents.append({"file": node, "distance": distance})
    return sorted(dependents, key=lambda x: x["distance"])

# Get file context (owners, decisions, deps)
def get_file_context(graph, file_path):
    context = {"owners": [], "decisions": [], "imports": [], "imported_by": []}
    for _, target, data in graph.edges(file_path, data=True):
        if data.get("type") == "imports":
            context["imports"].append(target)
    for source, _, data in graph.in_edges(file_path, data=True):
        if data.get("type") == "imports":
            context["imported_by"].append(source)
        elif data.get("type") == "affects":
            context["decisions"].append(graph.nodes[source])
        elif data.get("type") == "owns":
            context["owners"].append(graph.nodes[source])
    return context
```

---

## Skill: Python AST Import Extraction (tree-sitter)
```python
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY_LANGUAGE = Language(tspython.language())
parser = Parser(PY_LANGUAGE)

def extract_python_imports(source_code: str) -> list[str]:
    tree = parser.parse(bytes(source_code, "utf8"))
    imports = []
    for node in tree.root_node.children:
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    imports.append(child.text.decode())
        elif node.type == "import_from_statement":
            module = node.child_by_field_name("module_name")
            if module:
                imports.append(module.text.decode())
    return imports
```

---

## Skill: JS/TS Import Extraction (Regex Fallback)
```python
import re

JS_IMPORT_PATTERNS = [
    re.compile(r'import\s+.*?\s+from\s+["\'](.+?)["\']'),      # import X from './path'
    re.compile(r'import\s+["\'](.+?)["\']'),                     # import './path'
    re.compile(r'require\(\s*["\'](.+?)["\']\s*\)'),             # require('./path')
    re.compile(r'export\s+.*?\s+from\s+["\'](.+?)["\']'),       # export { X } from './path'
]

def extract_js_imports(source_code: str) -> list[dict]:
    imports = []
    for pattern in JS_IMPORT_PATTERNS:
        for match in pattern.finditer(source_code):
            path = match.group(1)
            is_external = not path.startswith(".")
            imports.append({"path": path, "external": is_external, "line": source_code[:match.start()].count("\n") + 1})
    return imports
```

---

## Updating This File

When you discover a new reusable pattern during development, add it here using this format:
## Skill: [Name]
[Brief description of when to use it]
```[language]
[code]
```
