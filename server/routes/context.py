"""
Context routes — manage .context.yaml files for directory context.

POST /api/context/analyze    → Analyze a directory and generate context
GET  /api/context/{dir}     → Get context for a directory
POST /api/context/update     → Update context with changes
DELETE /api/context/{dir}   → Delete context file
GET  /api/context/search     → Search for relevant contexts
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger("codeguardian.routes.context")

router = APIRouter(prefix="/api/context", tags=["context"])


class AnalyzeRequest(BaseModel):
    repo_path: str
    directory: str
    force_refresh: bool = False


class UpdateRequest(BaseModel):
    repo_path: str
    directory: str
    change_type: str = "committed"


class SearchRequest(BaseModel):
    repo_path: str
    query: str
    max_results: int = 5


class ContextResponse(BaseModel):
    directory: str
    description: str
    version: str
    generated_at: str
    files: list[dict]
    subdirectories: list[dict]
    changes: dict


def _get_context_service(request: Request):
    """Get or create context service from app state."""
    from server.services.context_service import ContextService

    if not hasattr(request.app.state, "_context_service"):
        llm_client = getattr(request.app.state, "llm_client", None)
        git_service = getattr(request.app.state, "git_service", None)

        if llm_client is None:
            raise HTTPException(
                status_code=503,
                detail="LLM client not available. Set NVIDIA_NIM_API_KEY.",
            )

        request.app.state._context_service = ContextService(
            llm_client=llm_client,
            git_service=git_service,
        )

    return request.app.state._context_service


def _get_retrieval_service(request: Request):
    """Get or create retrieval service from app state."""
    from server.services.retrieval_service import RetrievalService

    if not hasattr(request.app.state, "_retrieval_service"):
        context_service = _get_context_service(request)
        request.app.state._retrieval_service = RetrievalService(
            context_service=context_service,
        )

    return request.app.state._retrieval_service


@router.post("/analyze")
async def analyze_directory(request: Request, body: AnalyzeRequest):
    """
    Analyze a directory and generate its .context.yaml file.

    This will:
    1. List files and subdirectories
    2. Get git history for the directory
    3. Call LLM to generate description
    4. Write .context.yaml file
    """
    context_service = _get_context_service(request)

    dir_path = Path(body.repo_path) / body.directory
    if not dir_path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {body.directory}")

    if not dir_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {body.directory}")

    try:
        context = await context_service.analyze_directory(
            dir_path=str(dir_path),
            repo_path=body.repo_path,
            force_refresh=body.force_refresh,
        )

        return {
            "status": "success",
            "directory": context.directory,
            "description": context.description,
            "file_count": len(context.files),
            "subdirectory_count": len(context.subdirectories),
        }

    except Exception as exc:
        logger.error("Directory analysis failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{directory:path}")
async def get_context(request: Request, directory: str, repo_path: str):
    """
    Get context for a specific directory.

    Query params:
    - repo_path: Required. Path to the repository root.
    - include_related: Optional. Include parent directory context.
    """
    include_related = request.query_params.get("include_related", "false").lower() == "true"
    retrieval_service = _get_retrieval_service(request)

    dir_path = str(Path(repo_path) / directory)
    context = await retrieval_service.get_directory_context(
        dir_path,
        include_related=include_related,
    )

    if not context:
        raise HTTPException(
            status_code=404,
            detail=f"No context found for: {directory}",
        )

    return context


@router.post("/update")
async def update_context(request: Request, body: UpdateRequest):
    """
    Update context file with new changes.

    change_type can be: staged, unstaged, or committed
    """
    context_service = _get_context_service(request)

    dir_path = Path(body.repo_path) / body.directory
    if not dir_path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {body.directory}")

    if body.change_type not in ("staged", "unstaged", "committed"):
        raise HTTPException(
            status_code=400,
            detail="change_type must be one of: staged, unstaged, committed",
        )

    try:
        updated = await context_service.update_on_changes(
            dir_path=str(dir_path),
            repo_path=body.repo_path,
            change_type=body.change_type,
        )

        return {
            "status": "success",
            "directory": updated.directory,
            "description": updated.description,
        }

    except Exception as exc:
        logger.error("Context update failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.delete("/{directory:path}")
async def delete_context(request: Request, directory: str, repo_path: str):
    """
    Delete context file for a directory.
    """
    context_service = _get_context_service(request)

    dir_path = str(Path(repo_path) / directory)
    deleted = await context_service.delete_context(dir_path)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No context file found for: {directory}",
        )

    return {"status": "success", "directory": directory}


@router.post("/search")
async def search_contexts(request: Request, body: SearchRequest):
    """
    Search for relevant context files matching a query.

    Returns a list of context files sorted by relevance.
    """
    retrieval_service = _get_retrieval_service(request)

    results = retrieval_service.search_contexts(
        query=body.query,
        repo_path=body.repo_path,
        max_results=body.max_results,
    )

    return {
        "query": body.query,
        "results": [
            {
                "directory": r.directory,
                "file_path": r.file_path,
                "relevance_score": r.relevance_score,
                "matched_field": r.matched_field,
                "matched_content": r.matched_content,
            }
            for r in results
        ],
    }


@router.get("/validate/all")
async def validate_all_contexts(request: Request, repo_path: str):
    """
    Validate all context files in a repository.

    Returns counts of valid/invalid files and any errors.
    """
    retrieval_service = _get_retrieval_service(request)

    results = await retrieval_service.validate_context_files(repo_path)
    return results


@router.get("/files/list")
async def list_context_files(request: Request, repo_path: str):
    """
    List all .context.yaml files in a repository.
    """
    retrieval_service = _get_retrieval_service(request)

    files = retrieval_service.get_all_context_files(repo_path)
    return {
        "repo_path": repo_path,
        "count": len(files),
        "files": files,
    }