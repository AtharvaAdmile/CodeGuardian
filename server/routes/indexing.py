"""
Indexing routes — background codebase indexing with progress polling.

3-phase pipeline:
  Phase 1 (fast):       Code files → embeddings → vector store
  Phase 2 (background): Git blame → expertise mapping
  Phase 3 (background): Recent commits → decision extraction

POST  /api/index              → queue a background indexing job
GET   /api/index/status/{id}  → poll job progress
"""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from server.models.embedding_models import VectorDocument
from server.models.route_schemas import (
    IndexRequest,
    IndexResponse,
    IndexStatus,
    JobStatus,
)
from server.services.embedding_service import NIMEmbeddingService

logger = logging.getLogger("codeguardian.routes.indexing")

router = APIRouter(prefix="/api", tags=["indexing"])

# ── Constants ───────────────────────────────────────────────────────────
_SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx"}
_SKIP_DIRS = {"node_modules", "__pycache__", ".git", "venv", "dist", "build"}
_EMBED_BATCH_SIZE = 32
_CONTEXT_OVERLAP_LINES = 2
_DECISION_COMMIT_LIMIT = 50  # Recent commits to process for decisions


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


def _chunk_file(content: str, file_path: str) -> list[dict]:
    """Dispatch to the correct language chunker."""
    ext = Path(file_path).suffix.lower()
    if ext == ".py":
        return _chunk_python(content, file_path)

    language = "typescript" if ext in {".ts", ".tsx"} else "javascript"
    return _chunk_js_ts(content, file_path, language)


# ═════════════════════════════════════════════════════════════════════════
# Phase 1: Code → Embeddings → Vector Store (fast)
# ═════════════════════════════════════════════════════════════════════════


async def _phase1_index_code(
    project_id: str,
    project_path: str,
    embedding_service: NIMEmbeddingService,
    vector_service,
    status: IndexStatus,
) -> list[str]:
    """
    Walk the project, chunk files, embed, and upsert to the vector store.

    Returns the list of relative file paths that were indexed (used by
    Phase 2 for expertise mapping).
    """
    file_paths: list[Path] = []
    root = Path(project_path)

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            fp = Path(dirpath) / fname
            if fp.suffix.lower() in _SUPPORTED_EXTENSIONS:
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

            # Flush when batch is full
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

    # Flush remaining
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

    logger.info(
        "Phase 1 complete: %d files, %d chunks indexed",
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
# Phase 2: Git Blame → Expertise Mapping (background)
# ═════════════════════════════════════════════════════════════════════════


async def _phase2_expertise_map(
    project_path: str,
    indexed_files: list[str],
    status: IndexStatus,
    supabase_client=None,
) -> None:
    """
    Build expertise map from git blame for all indexed files.

    Runs in a thread pool since GitService is synchronous.
    """
    status.expertise_status = "running"

    try:
        from server.services.git_service import GitService, GitServiceError

        try:
            git_svc = GitService(
                project_path,
                supabase_client=supabase_client,
            )
        except GitServiceError as exc:
            logger.warning("Phase 2 skipped — not a git repo: %s", exc)
            status.expertise_status = "skipped"
            return

        # Run blame (blocking I/O) in a thread
        expertise = await asyncio.to_thread(
            git_svc.build_expertise_map, indexed_files
        )

        status.expertise_files_mapped = len(expertise)
        status.expertise_status = "completed"
        logger.info(
            "Phase 2 complete: expertise mapped for %d files",
            len(expertise),
        )

    except Exception as exc:
        logger.error("Phase 2 failed: %s", exc)
        status.expertise_status = "failed"
        status.errors.append(f"expertise mapping error: {exc}")


# ═════════════════════════════════════════════════════════════════════════
# Phase 3: Recent Commits → Decision Extraction (background)
# ═════════════════════════════════════════════════════════════════════════


async def _phase3_decision_extraction(
    project_path: str,
    status: IndexStatus,
    decision_extractor=None,
    decision_service=None,
    embedding_service=None,
) -> None:
    """
    Process recent commits through the decision extractor.

    Stores found decisions via the DecisionService.
    """
    if decision_extractor is None:
        logger.info("Phase 3 skipped — no DecisionExtractor available")
        status.decision_status = "skipped"
        return

    status.decision_status = "running"

    try:
        from server.services.git_service import GitService, GitServiceError

        try:
            git_svc = GitService(project_path)
        except GitServiceError as exc:
            logger.warning("Phase 3 skipped — not a git repo: %s", exc)
            status.decision_status = "skipped"
            return

        # Fetch recent commits (blocking I/O in thread)
        commits = await asyncio.to_thread(
            git_svc.get_recent_commits, _DECISION_COMMIT_LIMIT
        )

        if not commits:
            logger.info("Phase 3 skipped — no commits found")
            status.decision_status = "completed"
            return

        # Process commits through the extractor (rate-limited)
        extraction_stats = await decision_extractor.process_commits_batch(
            commits, git_svc
        )

        status.decisions_commits_processed = extraction_stats.total_processed
        status.decisions_found = extraction_stats.decisions_found

        # Store discovered decisions
        if decision_service and extraction_stats.decisions:
            project_id = Path(project_path).name  # Use dir name as project ID

            for decision in extraction_stats.decisions:
                try:
                    # Optionally embed the decision for semantic search
                    embedding = None
                    if embedding_service:
                        try:
                            decision_text = (
                                f"{decision.title}: {decision.context} "
                                f"{decision.decision} {decision.reasoning}"
                            )
                            embeddings = await embedding_service.embed_documents(
                                [decision_text]
                            )
                            embedding = embeddings[0]
                        except Exception:
                            pass  # Embedding failure is non-fatal

                    await decision_service.store_decision(
                        project_id=project_id,
                        title=decision.title,
                        context=decision.context,
                        decision=decision.decision,
                        reasoning=decision.reasoning,
                        source_type=decision.source_type,
                        source_ref=decision.source_ref,
                        embedding=embedding,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to store decision '%s': %s",
                        decision.title,
                        exc,
                    )

        status.decision_status = "completed"
        logger.info(
            "Phase 3 complete: %d commits processed, %d decisions found",
            extraction_stats.total_processed,
            extraction_stats.decisions_found,
        )

    except Exception as exc:
        logger.error("Phase 3 failed: %s", exc)
        status.decision_status = "failed"
        status.errors.append(f"decision extraction error: {exc}")


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
    supabase_client=None,
    decision_extractor=None,
    decision_service=None,
) -> None:
    """
    Run the 3-phase indexing pipeline.

    Phase 1 (fast):       Code → embeddings → vector store
    Phase 2 (background): Git blame → expertise mapping
    Phase 3 (background): Recent commits → decision extraction

    Progress is written to ``jobs[job_id]`` for polling.
    """
    status = jobs[job_id]
    status.status = JobStatus.RUNNING

    try:
        # ── Phase 1: Code indexing (user sees results within seconds) ──
        indexed_files = await _phase1_index_code(
            project_id=project_id,
            project_path=project_path,
            embedding_service=embedding_service,
            vector_service=vector_service,
            status=status,
        )

        # Mark as completed — code is now searchable
        status.status = JobStatus.COMPLETED

        # ── Phase 2 & 3: Background git analysis ──────────────────────
        # These run concurrently in the background AFTER Phase 1 completes.
        # The user can already query the codebase while these are running.

        await asyncio.gather(
            _phase2_expertise_map(
                project_path=project_path,
                indexed_files=indexed_files,
                status=status,
                supabase_client=supabase_client,
            ),
            _phase3_decision_extraction(
                project_path=project_path,
                status=status,
                decision_extractor=decision_extractor,
                decision_service=decision_service,
                embedding_service=embedding_service,
            ),
            return_exceptions=True,
        )

        logger.info(
            "Indexing job %s fully completed: %d files, %d chunks, "
            "expertise=%s, decisions=%s (%d found)",
            job_id,
            status.files_processed,
            status.chunks_created,
            status.expertise_status,
            status.decision_status,
            status.decisions_found,
        )

    except Exception as exc:
        logger.exception("Indexing job %s failed", job_id)
        status.status = JobStatus.FAILED
        status.error_message = str(exc)


# ═════════════════════════════════════════════════════════════════════════
# Endpoints
# ═════════════════════════════════════════════════════════════════════════


@router.post("/index", response_model=IndexResponse)
async def start_indexing(body: IndexRequest, request: Request) -> IndexResponse:
    """
    Queue a background indexing job.

    Returns a ``job_id`` immediately — poll ``/api/index/status/{job_id}``
    for progress. Code becomes searchable within seconds (Phase 1).
    Expertise mapping and decision extraction continue in the background.
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

    # Create job
    job_id = uuid.uuid4().hex[:12]
    jobs: dict[str, IndexStatus] = getattr(request.app.state, "index_jobs", {})

    initial_status = IndexStatus(job_id=job_id, status=JobStatus.QUEUED)
    jobs[job_id] = initial_status
    request.app.state.index_jobs = jobs

    # Collect optional services for Phase 2 & 3
    supabase_client = getattr(request.app.state, "supabase_client", None)
    decision_extractor = getattr(request.app.state, "decision_extractor", None)
    decision_service = getattr(request.app.state, "decision_service", None)

    # Launch background task
    asyncio.create_task(
        _index_project(
            job_id=job_id,
            project_id=body.project_id,
            project_path=body.project_path,
            force=body.force,
            embedding_service=embedding,
            vector_service=vector,
            jobs=jobs,
            supabase_client=supabase_client,
            decision_extractor=decision_extractor,
            decision_service=decision_service,
        )
    )

    return IndexResponse(job_id=job_id)


@router.get("/index/status/{job_id}", response_model=IndexStatus)
async def index_status(job_id: str, request: Request) -> IndexStatus:
    """Poll the progress of an indexing job."""
    jobs: dict[str, IndexStatus] = getattr(request.app.state, "index_jobs", {})

    if job_id not in jobs:
        raise HTTPException(404, f"Job not found: {job_id}")

    return jobs[job_id]
