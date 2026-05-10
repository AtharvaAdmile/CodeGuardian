"""
Indexing routes — background codebase indexing with progress polling.

2-phase pipeline:
  Phase 1 (fast): Code files → embeddings → vector store
  Phase 2:        Knowledge graph rebuild

POST  /api/index                  → queue a background indexing job
GET   /api/index/status/{id}      → poll job progress
GET   /api/index/estimate/{pid}   → pre-index file estimate
GET   /api/index/history/{pid}    → per-project index history
DELETE /api/index/history/{pid}   → clear per-project history
"""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import math
import os
import re
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from server.models.embedding_models import VectorDocument
from server.models.route_schemas import (
    IndexRequest,
    IndexResponse,
    IndexStatus,
    JobStatus,
    IndexEstimateResponse,
    ExtensionEstimate,
    DirectoryEstimate,
    IndexHistoryEntry,
    GitCleanlinessResponse,
    IndexWorkingTreeRequest,
    IndexDiffRequest,
    IndexDiffResponse,
)
from server.services.embedding_service import NIMEmbeddingService
from server.services.git_service import GitService

logger = logging.getLogger("codeguardian.routes.indexing")

router = APIRouter(prefix="/api", tags=["indexing"])

# ── Constants ───────────────────────────────────────────────────────────
_SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx"}
_SKIP_DIRS = {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build",
              "chroma_data", "generated_test_cases", ".codeguardian", "coverage"}
_EMBED_BATCH_SIZE = 32
_CONTEXT_OVERLAP_LINES = 2
_MAX_CHUNK_LINES = 40         # Max lines per chunk — keeps well under the 512-token NIM limit
_OVERLAP_LINES = 5            # Overlap between sub-chunks for continuity


# ═════════════════════════════════════════════════════════════════════════
# Chunking helpers
# ═════════════════════════════════════════════════════════════════════════


def _add_context(
    lines: list[str], start: int, end: int
) -> tuple[str, int, int]:
    """
    Return chunk text with 2 lines of leading/trailing context.

    Args:
        lines: All lines of the source file.
        start: 0-indexed start line of the core chunk.
        end:   0-indexed end line (exclusive) of the core chunk.

    Returns:
        (text, adjusted_start_1indexed, adjusted_end_1indexed)
    """
    ctx_start = max(0, start - _CONTEXT_OVERLAP_LINES)
    ctx_end = min(len(lines), end + _CONTEXT_OVERLAP_LINES)
    text = "\n".join(lines[ctx_start:ctx_end])
    return text, ctx_start + 1, ctx_end


def _chunk_python(content: str, file_path: str) -> list[dict]:
    """
    Parse Python with AST and extract functions, classes, and module-level
    code as separate chunks.
    """
    chunks: list[dict] = []
    lines = content.splitlines()

    try:
        tree = ast.parse(content)
    except SyntaxError:
        # Fallback: treat the whole file as one chunk
        text, s, e = _add_context(lines, 0, len(lines))
        chunks.append(
            {
                "text": text,
                "start_line": s,
                "end_line": e,
                "chunk_type": "module",
                "language": "python",
            }
        )
        return chunks

    # Collect top-level node ranges to identify module-level gaps
    top_level_ranges: list[tuple[int, int, str, str]] = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = node.lineno - 1  # 0-indexed
            end = (node.end_lineno or node.lineno)  # 1-indexed → exclusive
            top_level_ranges.append((start, end, "function", node.name))
        elif isinstance(node, ast.ClassDef):
            start = node.lineno - 1
            end = (node.end_lineno or node.lineno)
            top_level_ranges.append((start, end, "class", node.name))

    # Sort by start line
    top_level_ranges.sort(key=lambda r: r[0])

    # Extract module-level code (lines between top-level definitions)
    prev_end = 0
    for start, end, _, _ in top_level_ranges:
        if start > prev_end:
            module_text = "\n".join(lines[prev_end:start]).strip()
            if module_text:
                text, s, e = _add_context(lines, prev_end, start)
                chunks.append(
                    {
                        "text": text,
                        "start_line": s,
                        "end_line": e,
                        "chunk_type": "module",
                        "language": "python",
                    }
                )
        prev_end = end

    # Trailing module-level code
    if prev_end < len(lines):
        trailing = "\n".join(lines[prev_end:]).strip()
        if trailing:
            text, s, e = _add_context(lines, prev_end, len(lines))
            chunks.append(
                {
                    "text": text,
                    "start_line": s,
                    "end_line": e,
                    "chunk_type": "module",
                    "language": "python",
                }
            )

    # Add function/class chunks
    for start, end, chunk_type, name in top_level_ranges:
        text, s, e = _add_context(lines, start, end)
        chunks.append(
            {
                "text": text,
                "start_line": s,
                "end_line": e,
                "chunk_type": chunk_type,
                "language": "python",
            }
        )

    return chunks


# Regex patterns for JS/TS function and class declarations
_JS_FUNC_PATTERNS = [
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\("),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function\s*\("),
]
_JS_CLASS_PATTERN = re.compile(r"^\s*(?:export\s+)?class\s+(\w+)")


def _find_brace_end(lines: list[str], start_idx: int) -> int:
    """Find the line index (exclusive) of the closing brace for a block."""
    depth = 0
    found = False
    for i in range(start_idx, len(lines)):
        for ch in lines[i]:
            if ch == "{":
                depth += 1
                found = True
            elif ch == "}":
                depth -= 1
                if found and depth == 0:
                    return i + 1
    return len(lines)


def _chunk_js_ts(content: str, file_path: str, language: str) -> list[dict]:
    """Regex-based chunking for JavaScript / TypeScript."""
    chunks: list[dict] = []
    lines = content.splitlines()
    used_lines: set[int] = set()

    i = 0
    while i < len(lines):
        line = lines[i]

        # Check class
        m = _JS_CLASS_PATTERN.match(line)
        if m:
            end = _find_brace_end(lines, i)
            text, s, e = _add_context(lines, i, end)
            chunks.append(
                {
                    "text": text,
                    "start_line": s,
                    "end_line": e,
                    "chunk_type": "class",
                    "language": language,
                }
            )
            used_lines.update(range(i, end))
            i = end
            continue

        # Check functions
        matched = False
        for pat in _JS_FUNC_PATTERNS:
            fm = pat.match(line)
            if fm:
                end = _find_brace_end(lines, i)
                text, s, e = _add_context(lines, i, end)
                chunks.append(
                    {
                        "text": text,
                        "start_line": s,
                        "end_line": e,
                        "chunk_type": "function",
                        "language": language,
                    }
                )
                used_lines.update(range(i, end))
                i = end
                matched = True
                break

        if not matched:
            i += 1

    # Collect remaining module-level code in blocks of 50 lines
    remaining_lines: list[int] = [
        idx for idx in range(len(lines)) if idx not in used_lines
    ]
    if remaining_lines:
        block_start = remaining_lines[0]
        prev = remaining_lines[0]
        for idx in remaining_lines[1:]:
            if idx - prev > 1 or idx - block_start >= 50:
                block_text = "\n".join(lines[block_start : prev + 1]).strip()
                if block_text:
                    text, s, e = _add_context(lines, block_start, prev + 1)
                    chunks.append(
                        {
                            "text": text,
                            "start_line": s,
                            "end_line": e,
                            "chunk_type": "module",
                            "language": language,
                        }
                    )
                block_start = idx
            prev = idx
        # Final remaining block
        block_text = "\n".join(lines[block_start : prev + 1]).strip()
        if block_text:
            text, s, e = _add_context(lines, block_start, prev + 1)
            chunks.append(
                {
                    "text": text,
                    "start_line": s,
                    "end_line": e,
                    "chunk_type": "module",
                    "language": language,
                }
            )

    # Fallback: if nothing extracted, treat whole file as one chunk
    if not chunks:
        text, s, e = _add_context(lines, 0, len(lines))
        chunks.append(
            {
                "text": text,
                "start_line": s,
                "end_line": e,
                "chunk_type": "module",
                "language": language,
            }
        )

    return chunks


def _split_oversized(chunks: list[dict]) -> list[dict]:
    """
    Split any chunk exceeding _MAX_CHUNK_LINES into smaller sub-chunks
    with _OVERLAP_LINES of overlap for continuity.

    This is the PROPER fix for the 512-token NIM limit — split at line
    boundaries so each sub-chunk is semantically coherent, instead of
    silently truncating mid-line.
    """
    result: list[dict] = []
    for chunk in chunks:
        text = chunk["text"]
        if not text or not text.strip():
            continue  # Drop empty/whitespace-only chunks at the source

        lines = text.splitlines()
        if len(lines) <= _MAX_CHUNK_LINES:
            result.append(chunk)
            continue

        # Split into sub-chunks with overlap
        start = 0
        while start < len(lines):
            end = min(start + _MAX_CHUNK_LINES, len(lines))
            sub_text = "\n".join(lines[start:end])

            if sub_text.strip():  # Only keep non-empty sub-chunks
                result.append({
                    "text": sub_text,
                    "start_line": chunk["start_line"] + start,
                    "end_line": chunk["start_line"] + end - 1,
                    "chunk_type": chunk["chunk_type"],
                    "language": chunk["language"],
                })

            if end >= len(lines):
                break
            start = end - _OVERLAP_LINES  # Overlap for continuity

    return result


def _chunk_file(content: str, file_path: str) -> list[dict]:
    """Dispatch to the correct language chunker, then split oversized chunks."""
    ext = Path(file_path).suffix.lower()
    if ext == ".py":
        raw_chunks = _chunk_python(content, file_path)
    else:
        language = "typescript" if ext in {".ts", ".tsx"} else "javascript"
        raw_chunks = _chunk_js_ts(content, file_path, language)

    return _split_oversized(raw_chunks)


# ═════════════════════════════════════════════════════════════════════════
# Phase 1: Code → Embeddings → Vector Store (fast)
# ═════════════════════════════════════════════════════════════════════════


async def _phase1_index_code(
    project_id: str,
    project_path: str,
    embedding_service: NIMEmbeddingService,
    vector_service,
    status: IndexStatus,
    include_extensions: set[str] | None = None,
    include_directories: list[str] | None = None,
) -> list[str]:
    """
    Walk the project, chunk files, embed, and upsert to the vector store.

    Returns the list of relative file paths that were indexed.

    If *include_extensions* is provided, only files whose extension is in
    the set are indexed (intersected with _SUPPORTED_EXTENSIONS).
    If *include_directories* is provided, only files whose relative path
    starts with one of the listed directory prefixes are indexed.
    """
    file_paths: list[Path] = []
    root = Path(project_path)

    extensions = _SUPPORTED_EXTENSIONS
    if include_extensions is not None:
        extensions = _SUPPORTED_EXTENSIONS & include_extensions

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            fp = Path(dirpath) / fname
            ext = fp.suffix.lower()
            if ext not in extensions:
                continue
            if include_directories:
                rel = str(fp.relative_to(root))
                if not any(rel.startswith(d) for d in include_directories):
                    continue
            file_paths.append(fp)

    status.files_total = len(file_paths)
    rel_paths: list[str] = []

    pending_texts: list[str] = []
    pending_meta: list[dict] = []
    pending_ids: list[str] = []
    chunk_index = 0

    for fp in file_paths:
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            status.errors.append(f"{fp}: read error — {exc}")
            status.files_processed += 1
            continue

        rel_path = str(fp.relative_to(root))
        rel_paths.append(rel_path)

        status.current_file = rel_path

        file_chunks = _chunk_file(content, str(fp))

        for fc in file_chunks:
            doc_id = NIMEmbeddingService.generate_id(
                project_id, rel_path, chunk_index
            )
            pending_ids.append(doc_id)
            pending_texts.append(fc["text"])
            pending_meta.append(
                {
                    "file_path": rel_path,
                    "start_line": fc["start_line"],
                    "end_line": fc["end_line"],
                    "chunk_type": fc["chunk_type"],
                    "language": fc["language"],
                }
            )
            chunk_index += 1

            if len(pending_texts) >= _EMBED_BATCH_SIZE:
                await _flush_batch(
                    embedding_service,
                    vector_service,
                    project_id,
                    pending_ids,
                    pending_texts,
                    pending_meta,
                    status,
                )
                pending_ids.clear()
                pending_texts.clear()
                pending_meta.clear()

        status.files_processed += 1

    if pending_texts:
        await _flush_batch(
            embedding_service,
            vector_service,
            project_id,
            pending_ids,
            pending_texts,
            pending_meta,
            status,
        )

    status.current_file = None

    logger.info(
        "Code indexing complete: %d files, %d chunks indexed",
        status.files_processed,
        status.chunks_created,
    )
    return rel_paths


async def _flush_batch(
    embedding_service: NIMEmbeddingService,
    vector_service,
    project_id: str,
    ids: list[str],
    texts: list[str],
    metas: list[dict],
    status: IndexStatus,
) -> None:
    """Embed a batch of texts and upsert to the vector store."""
    # Safety net: drop any empty texts that slipped through the chunker
    filtered = [
        (i, t, m) for i, t, m in zip(ids, texts, metas)
        if t and t.strip()
    ]
    if not filtered:
        return
    if filtered:
        ids, texts, metas = [item[0] for item in filtered], [item[1] for item in filtered], [item[2] for item in filtered]
    else:
        ids, texts, metas = [], [], []

    try:
        embeddings = await embedding_service.embed_documents(texts)

        documents = [
            VectorDocument(id=did, text=text, embedding=emb, metadata=meta)
            for did, text, emb, meta in zip(ids, texts, embeddings, metas)
        ]

        await vector_service.upsert(project_id, documents)
        status.chunks_created += len(documents)

    except Exception as exc:
        logger.warning("Batch embed/upsert failed: %s", exc)
        status.errors.append(f"batch error: {exc}")


# ═════════════════════════════════════════════════════════════════════════
# Phase 2: Knowledge Graph Build
# ═════════════════════════════════════════════════════════════════════════


async def _phase2_knowledge_graph(
    project_path: str,
    status: IndexStatus,
    knowledge_graph=None,
) -> None:
    """
    Rebuild the knowledge graph from code structure.

    Runs in a thread pool since graph construction is CPU-bound.
    Persists to .codeguardian/knowledge_graph.json.
    """
    if knowledge_graph is None:
        logger.info("Knowledge graph skipped — no KnowledgeGraph available")
        status.graph_status = "skipped"
        return

    status.graph_status = "running"

    try:
        await asyncio.to_thread(
            knowledge_graph.rebuild,
            project_path,
        )

        # Persist to disk
        persist_path = Path(project_path) / ".codeguardian" / "knowledge_graph.json"
        await asyncio.to_thread(
            knowledge_graph.save_to_json, str(persist_path)
        )

        stats = knowledge_graph.get_stats()
        status.graph_nodes = stats.get("total_nodes", 0)
        status.graph_edges = stats.get("total_edges", 0)
        status.graph_status = "completed"

        logger.info(
            "Knowledge graph built: %d nodes, %d edges",
            status.graph_nodes,
            status.graph_edges,
        )

    except Exception as exc:
        logger.error("Knowledge graph failed: %s", exc)
        status.graph_status = "failed"
        status.errors.append(f"knowledge graph error: {exc}")


# ═════════════════════════════════════════════════════════════════════════
# Main indexing orchestrator
# ═════════════════════════════════════════════════════════════════════════


async def _index_project(
    job_id: str,
    project_id: str,
    project_path: str,
    force: bool,
    embedding_service: NIMEmbeddingService,
    vector_service,
    jobs: dict[str, IndexStatus],
    knowledge_graph=None,
    include_extensions: set[str] | None = None,
    include_directories: list[str] | None = None,
    *,
    incremental: bool = False,
    diff_info: dict | None = None,
    git_service: GitService | None = None,
    last_indexed_commit: str = "",
) -> None:
    """
    Run the 2-phase indexing pipeline.

    Phase 1 (fast): Code → embeddings → vector store
    Phase 2:        Rebuild knowledge graph

    When *incremental* is True and *diff_info* is provided, Phase 1 only
    processes files changed since the last indexed commit.

    Progress is written to ``jobs[job_id]`` for polling.
    """
    status = jobs[job_id]
    status.status = JobStatus.RUNNING
    start_ts = time.time()

    try:
        # ── Phase 1: Code indexing ─────────────────────────────────────
        if incremental and diff_info and git_service:
            status.incremental = True
            await _phase1_index_incremental(
                project_id=project_id,
                project_path=project_path,
                diff_info=diff_info,
                git_service=git_service,
                embedding_service=embedding_service,
                vector_service=vector_service,
                status=status,
                last_indexed_commit=last_indexed_commit,
            )
        else:
            if force:
                await vector_service.delete_project(project_id)

            await _phase1_index_code(
                project_id=project_id,
                project_path=project_path,
                embedding_service=embedding_service,
                vector_service=vector_service,
                status=status,
                include_extensions=include_extensions,
                include_directories=include_directories,
            )

        # ── Phase 2: Knowledge Graph ────────────────────────────────────
        await _phase2_knowledge_graph(
            project_path=project_path,
            status=status,
            knowledge_graph=knowledge_graph,
        )

        # Store commit SHA
        if git_service:
            status.commit_sha = git_service.get_head_sha()

        status.status = JobStatus.COMPLETED

        # ── Persist history entry ──────────────────────────────────────
        elapsed = int(time.time() - start_ts)
        minutes, seconds = divmod(elapsed, 60)
        duration_str = f"{minutes}:{seconds:02d}"

        history_entry = IndexHistoryEntry(
            id=job_id,
            date=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            files=status.files_processed,
            chunks=status.chunks_created,
            nodes=status.graph_nodes,
            edges=status.graph_edges,
            status=status.status.value if hasattr(status.status, 'value') else str(status.status),
            duration=duration_str,
            project_path=project_path,
            commit_sha=status.commit_sha,
            incremental=status.incremental,
        )
        _append_history(project_id, history_entry)

        logger.info(
            "Indexing job %s fully completed: %d files, %d chunks, graph=%s (%d nodes) incremental=%s",
            job_id,
            status.files_processed,
            status.chunks_created,
            status.graph_status,
            status.graph_nodes,
            status.incremental,
        )

    except Exception as exc:
        logger.exception("Indexing job %s failed", job_id)
        status.status = JobStatus.FAILED
        status.error_message = str(exc)


# ═════════════════════════════════════════════════════════════════════════
# Index History (per-project JSON persistence)
# ═════════════════════════════════════════════════════════════════════════

_HISTORY_DIR = ".codeguardian/index_history"


def _history_path(project_id: str) -> Path:
    return Path(_HISTORY_DIR) / f"{project_id}.json"


def _load_history(project_id: str) -> list[dict]:
    path = _history_path(project_id)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Corrupt history file for '%s', starting fresh", project_id)
        return []


def _append_history(project_id: str, entry: IndexHistoryEntry) -> None:
    path = _history_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = _load_history(project_id)
    entries.append(entry.model_dump())
    # Keep last 20
    entries = entries[-20:]
    path.write_text(json.dumps(entries, indent=2, default=str), encoding="utf-8")


def _clear_history(project_id: str) -> None:
    path = _history_path(project_id)
    if path.exists():
        path.unlink()


def _get_last_indexed_commit(project_id: str) -> str | None:
    """Return the commit SHA from the most recent index history entry, or None."""
    entries = _load_history(project_id)
    for entry in reversed(entries):
        sha = entry.get("commit_sha", "")
        if sha:
            return sha
    return None


# ═════════════════════════════════════════════════════════════════════════
# Phase 1 — Incremental indexing (git diff-based)
# ═════════════════════════════════════════════════════════════════════════


async def _index_single_file(
    project_id: str,
    project_path: str,
    rel_path: str,
    content: str,
    pending_ids: list[str],
    pending_texts: list[str],
    pending_meta: list[dict],
    chunk_index_start: int,
) -> int:
    """Chunk a single file, populate pending lists, return number of chunks added."""
    file_chunks = _chunk_file(content, str(Path(project_path) / rel_path))
    for i, fc in enumerate(file_chunks):
        doc_id = NIMEmbeddingService.generate_id(
            project_id, rel_path, chunk_index_start + i
        )
        pending_ids.append(doc_id)
        pending_texts.append(fc["text"])
        pending_meta.append({
            "file_path": rel_path,
            "start_line": fc["start_line"],
            "end_line": fc["end_line"],
            "chunk_type": fc["chunk_type"],
            "language": fc["language"],
        })
    return len(file_chunks)


async def _phase1_index_incremental(
    project_id: str,
    project_path: str,
    diff_info: dict,
    git_service: GitService,
    embedding_service: NIMEmbeddingService,
    vector_service,
    status: IndexStatus,
    last_indexed_commit: str,
) -> list[str]:
    """
    Index only the files changed since *last_indexed_commit*.

    *diff_info* contains:
      added (list[str]), modified (list[str]),
      deleted (list[str]), renamed (list[tuple[str,str]])

    Steps:
      1. Delete chunks for deleted and renamed-old files.
      2. For modified files: delete old chunks, chunk new content, index.
      3. For added and renamed-new files: chunk new content and index.
    """
    root = Path(project_path)
    rel_paths: list[str] = []

    added = diff_info.get("added", [])
    modified = diff_info.get("modified", [])
    deleted = diff_info.get("deleted", [])
    renamed = diff_info.get("renamed", [])

    # Collect all file paths to delete from vector store
    files_to_delete: list[str] = list(deleted)
    files_to_delete.extend(old for old, _ in renamed)
    files_to_delete.extend(modified)  # delete old chunks before re-adding

    if files_to_delete:
        await vector_service.delete_chunks_for_files(project_id, files_to_delete)
        status.deleted_files = len(deleted) + len(renamed)
        logger.info(
            "Deleted chunks for %d files (deleted + renamed + modified)",
            len(files_to_delete),
        )

    # Files to (re-)index: added + modified + renamed-new
    files_to_index: list[tuple[str, str | None]] = []
    for fp in added:
        files_to_index.append((fp, None))
    for fp in modified:
        files_to_index.append((fp, None))
    for old, new in renamed:
        files_to_index.append((new, old))

    status.files_total = len(files_to_index)
    status.incremental = True
    status.added_files = len(added)
    status.modified_files = len(modified) + len(renamed)

    pending_ids: list[str] = []
    pending_texts: list[str] = []
    pending_meta: list[dict] = []
    global_chunk_index = 0

    for rel_path, _ in files_to_index:
        fp = root / rel_path
        ext = fp.suffix.lower()
        if ext not in _SUPPORTED_EXTENSIONS:
            status.errors.append(f"{rel_path}: unsupported extension, skipped")
            status.files_processed += 1
            continue

        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            status.errors.append(f"{rel_path}: read error — {exc}")
            status.files_processed += 1
            continue

        rel_paths.append(rel_path)
        status.current_file = rel_path

        num_chunks = await _index_single_file(
            project_id, project_path, rel_path, content,
            pending_ids, pending_texts, pending_meta,
            global_chunk_index,
        )
        global_chunk_index += num_chunks

        if len(pending_texts) >= _EMBED_BATCH_SIZE:
            await _flush_batch(
                embedding_service, vector_service, project_id,
                pending_ids, pending_texts, pending_meta, status,
            )
            pending_ids.clear()
            pending_texts.clear()
            pending_meta.clear()

        status.files_processed += 1

    if pending_texts:
        await _flush_batch(
            embedding_service, vector_service, project_id,
            pending_ids, pending_texts, pending_meta, status,
        )

    status.current_file = None

    logger.info(
        "Incremental indexing complete: +%d added, ~%d modified, -%d deleted — %d chunks",
        len(added), len(modified), len(deleted), status.chunks_created,
    )
    return rel_paths


# ═════════════════════════════════════════════════════════════════════════
# Endpoints
# ═════════════════════════════════════════════════════════════════════════


@router.post("/index/check-working-tree", response_model=GitCleanlinessResponse)
async def check_working_tree(body: IndexWorkingTreeRequest) -> GitCleanlinessResponse:
    """
    Check whether the project's git working tree is clean enough for indexing.

    Returns a summary of staged, unstaged, and untracked files.
    """
    try:
        git_svc = GitService(body.project_path)
        result = git_svc.get_working_tree_status()
        return GitCleanlinessResponse(**result)
    except Exception as exc:
        logger.warning("Git status check failed (non-git repo?): %s", exc)
        return GitCleanlinessResponse(
            clean=True,
            has_changes=False,
            summary="Not a git repository or git is unavailable.",
        )


@router.post("/index/diff-status", response_model=IndexDiffResponse)
async def index_diff_status(body: IndexDiffRequest) -> IndexDiffResponse:
    """
    Preview what an incremental index would change.

    Compares the last indexed commit against HEAD and returns the
    list of added, modified, and deleted files. If incremental indexing
    is not possible (no prior index, no git repo, same commit), explains why.
    """
    last_sha = _get_last_indexed_commit(body.project_id)
    if not last_sha:
        return IndexDiffResponse(
            incremental_possible=False,
            message="No prior index history found. A full index is needed.",
        )

    try:
        git_svc = GitService(body.project_path)
    except Exception as exc:
        return IndexDiffResponse(
            incremental_possible=False,
            message=f"Cannot access git repository: {exc}",
        )

    head_sha = git_svc.get_head_sha()
    if not head_sha:
        return IndexDiffResponse(
            incremental_possible=False,
            message="Repository has no commits yet.",
        )

    if head_sha == last_sha:
        return IndexDiffResponse(
            commit_sha=head_sha,
            last_indexed_commit=last_sha,
            incremental_possible=False,
            message="Index is up to date with HEAD. No new commits to index.",
        )

    diff = git_svc.get_diff_between(last_sha, head_sha)
    added = diff.get("added", [])
    modified = diff.get("modified", [])
    deleted = diff.get("deleted", [])
    renamed = diff.get("renamed", [])

    total = len(added) + len(modified) + len(deleted) + len(renamed)

    return IndexDiffResponse(
        commit_sha=head_sha,
        last_indexed_commit=last_sha,
        added=added,
        modified=modified + [new for _, new in renamed],
        deleted=deleted + [old for old, _ in renamed],
        total_changed=total,
        incremental_possible=total > 0,
        message=f"{total} file(s) changed since last index. "
                f"+{len(added)} added, ~{len(modified) + len(renamed)} modified, -{len(deleted)} deleted."
                if total > 0
                else "No changes detected since last index.",
    )


@router.get("/index/estimate/{project_id}", response_model=IndexEstimateResponse)
async def estimate_index(project_id: str, project_path: str, request: Request) -> IndexEstimateResponse:
    """
    Walk the project directory and return file counts, line counts,
    and estimated chunks grouped by extension and by directory.
    """
    root = Path(project_path)
    if not root.exists() or not root.is_dir():
        raise HTTPException(404, f"Project path not found: {project_path}")

    ext_data: dict[str, dict] = {}
    dir_data: dict[str, dict] = {}
    total_files = 0
    total_lines = 0
    total_chunks = 0

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            fp = Path(dirpath) / fname
            ext = fp.suffix.lower()
            if not ext:
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            line_count = content.count("\n") + 1
            est_chunks = max(1, math.ceil(line_count / _MAX_CHUNK_LINES))

            # Per extension
            e = ext_data.setdefault(ext, {"count": 0, "total_lines": 0, "estimated_chunks": 0})
            e["count"] += 1
            e["total_lines"] += line_count
            e["estimated_chunks"] += est_chunks

            # Per directory (top-2-level relative path)
            rel = str(fp.relative_to(root))
            parts = rel.split("/")
            dir_key = parts[0] if len(parts) <= 2 else "/".join(parts[:2])
            d = dir_data.setdefault(dir_key, {"count": 0, "total_lines": 0, "estimated_chunks": 0})
            d["count"] += 1
            d["total_lines"] += line_count
            d["estimated_chunks"] += est_chunks

            total_files += 1
            total_lines += line_count
            total_chunks += est_chunks

    return IndexEstimateResponse(
        project_id=project_id,
        project_path=project_path,
        total_files=total_files,
        total_lines=total_lines,
        estimated_total_chunks=total_chunks,
        by_extension=[ExtensionEstimate(extension=k, **v) for k, v in sorted(ext_data.items())],
        by_directory=[DirectoryEstimate(path=k, **v) for k, v in sorted(dir_data.items())],
    )


@router.get("/index/history/{project_id}")
async def get_index_history(project_id: str) -> list[IndexHistoryEntry]:
    """Return per-project index history entries."""
    entries = _load_history(project_id)
    return [IndexHistoryEntry(**e) for e in entries]


@router.delete("/index/history/{project_id}")
async def delete_index_history(project_id: str) -> dict:
    """Clear per-project index history."""
    _clear_history(project_id)
    return {"success": True, "project_id": project_id}


@router.post("/index", response_model=IndexResponse)
async def start_indexing(body: IndexRequest, request: Request) -> IndexResponse:
    """
    Queue a background indexing job.

    Before queuing, validates:
      1. The project directory exists.
      2. The working tree is clean (no staged/unstaged/untracked changes).
      3. If already indexed and ``force=False``, tries incremental mode.

    Returns a ``job_id`` immediately — poll ``/api/index/status/{job_id}``
    for progress. Code becomes searchable within seconds (Phase 1).
    The knowledge graph is rebuilt in the background (Phase 2).
    """
    embedding = getattr(request.app.state, "embedding_service", None)
    vector = getattr(request.app.state, "vector_service", None)

    if embedding is None:
        raise HTTPException(503, "Embedding service is not initialised.")
    if vector is None:
        raise HTTPException(503, "Vector service is not initialised.")

    project_root = Path(body.project_path)
    if not project_root.exists() or not project_root.is_dir():
        raise HTTPException(404, f"Project path not found: {body.project_path}")

    # ── Git cleanliness gate ──────────────────────────────────────────
    git_service: GitService | None = None
    try:
        git_service = GitService(body.project_path)
        status_info = git_service.get_working_tree_status()
        if not status_info["clean"]:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Cannot index: working tree has uncommitted changes. "
                               "Commit or stash them first.",
                    "staged_files": status_info["staged_files"],
                    "unstaged_files": status_info["unstaged_files"],
                    "untracked_files": status_info["untracked_files"],
                    "summary": status_info["summary"],
                },
            )
    except HTTPException:
        raise
    except Exception:
        git_service = None

    # ── Determine incremental vs full ──────────────────────────────────
    incremental = False
    diff_info = None
    last_indexed_commit = ""
    head_sha = git_service.get_head_sha() if git_service else ""

    if not body.force and head_sha:
        last_indexed_commit = _get_last_indexed_commit(body.project_id) or ""
        if last_indexed_commit and last_indexed_commit != head_sha:
            diff_info = git_service.get_diff_between(last_indexed_commit, head_sha) if git_service else None
            total_changed = sum(len(v) for v in diff_info.values()) if diff_info else 0
            incremental = total_changed > 0

    # ── Create job ─────────────────────────────────────────────────────
    job_id = uuid.uuid4().hex[:12]
    jobs: dict[str, IndexStatus] = getattr(request.app.state, "index_jobs", {})

    initial_status = IndexStatus(job_id=job_id, status=JobStatus.QUEUED)
    jobs[job_id] = initial_status
    request.app.state.index_jobs = jobs

    knowledge_graph = getattr(request.app.state, "knowledge_graph", None)

    ext_filter = set(body.include_extensions) if body.include_extensions else None
    dir_filter = body.include_directories

    # ── Launch background task ─────────────────────────────────────────
    args = dict(
        job_id=job_id,
        project_id=body.project_id,
        project_path=body.project_path,
        force=body.force,
        embedding_service=embedding,
        vector_service=vector,
        jobs=jobs,
        knowledge_graph=knowledge_graph,
        include_extensions=ext_filter,
        include_directories=dir_filter,
        incremental=incremental,
        diff_info=diff_info,
        git_service=git_service,
        last_indexed_commit=last_indexed_commit,
    )
    asyncio.create_task(_index_project(**args))

    return IndexResponse(job_id=job_id)


@router.get("/index/status/{job_id}", response_model=IndexStatus)
async def index_status(job_id: str, request: Request) -> IndexStatus:
    """Poll the progress of an indexing job."""
    jobs: dict[str, IndexStatus] = getattr(request.app.state, "index_jobs", {})

    if job_id not in jobs:
        raise HTTPException(404, f"Job not found: {job_id}")

    return jobs[job_id]


class IndexCheckResponse(BaseModel):
    project_id: str
    is_indexed: bool
    chunks_count: int = 0


@router.delete("/index/{project_id}")
async def delete_index(project_id: str, request: Request) -> dict:
    """
    Delete all indexed chunks/embeddings for a project from ChromaDB.
    """
    vector = getattr(request.app.state, "vector_service", None)
    if vector is None:
        raise HTTPException(503, "Vector service is not initialised.")

    await vector.delete_project(project_id)
    logger.info("Deleted index for project '%s'", project_id)
    return {"success": True, "project_id": project_id}


@router.get("/index/check/{project_id}", response_model=IndexCheckResponse)
async def check_index(project_id: str, request: Request) -> IndexCheckResponse:
    """
    Check whether a project has already been indexed in ChromaDB.

    Returns:
        - is_indexed: True if chunks exist in the vector store
        - chunks_count: Number of chunks stored
    """
    vector = getattr(request.app.state, "vector_service", None)
    if vector is None:
        raise HTTPException(503, "Vector service is not initialised.")

    is_indexed = vector.has_project_index(project_id)
    chunks_count = vector.get_project_index_count(project_id) if is_indexed else 0

    return IndexCheckResponse(
        project_id=project_id,
        is_indexed=is_indexed,
        chunks_count=chunks_count,
    )
