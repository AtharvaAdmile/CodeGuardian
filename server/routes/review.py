"""
Code Review routes.

POST /api/review
    Run the multi-node LangGraph review pipeline against a code snippet
    or a file + unified diff (PR mode).

POST /api/review/webhook
    GitHub PR webhook receiver.  Parses the event payload and logs it;
    full automation (auto-posting review comments) is deferred.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from server.models.route_schemas import ReviewRequest, ReviewResponse

logger = logging.getLogger("codeguardian.routes.review")

router = APIRouter(prefix="/api/review", tags=["review"])


# ── POST /api/review ──────────────────────────────────────────────────────


@router.post("", response_model=ReviewResponse)
async def review_code(body: ReviewRequest, request: Request) -> ReviewResponse:
    """
    Run the LangGraph code-review pipeline.

    Requires llm_client (503 if absent).
    embedding_service and vector_service are optional (pattern_check is
    skipped gracefully when absent).
    """
    llm_client = getattr(request.app.state, "llm_client", None)
    if llm_client is None:
        raise HTTPException(503, "LLM client is not initialised.")

    if not body.code and not body.diff:
        raise HTTPException(422, "Either 'code' or 'diff' must be provided.")

    embedding_service = getattr(request.app.state, "embedding_service", None)
    vector_service = getattr(request.app.state, "vector_service", None)
    knowledge_graph = getattr(request.app.state, "knowledge_graph", None)

    from server.agents.review_agent import ReviewAgent

    agent = ReviewAgent(
        llm_client=llm_client,
        embedding_service=embedding_service,
        vector_service=vector_service,
        knowledge_graph=knowledge_graph,
    )

    try:
        result = await agent.run(
            project_id=body.project_id,
            project_path=body.project_path,
            input_code=body.code or "",
            file_path=body.file_path,
            diff=body.diff,
        )

        return ReviewResponse(
            summary=result.get("summary", ""),
            findings=result.get("findings", []),
            severity_counts=result.get("severity_counts", {}),
            impact_report=result.get("impact_report", {}),
        )

    except asyncio.TimeoutError:
        logger.warning("Review agent timed out for project %r", body.project_id)
        raise HTTPException(504, "Review agent timed out after 180 seconds.")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error in /api/review")
        raise HTTPException(500, f"Review failed: {exc}") from exc


# ── POST /api/review/webhook ──────────────────────────────────────────────


@router.post("/webhook", status_code=202)
async def github_webhook(request: Request) -> dict:
    """
    Receive GitHub PR webhook events.

    Validates the HMAC-SHA256 signature when ``GITHUB_WEBHOOK_SECRET`` is
    configured in app settings; otherwise accepts all events (dev mode).

    Parses the event and logs the PR details.  Full automation
    (auto-posting review comments back to GitHub) is not yet wired up.
    """
    settings = getattr(request.app.state, "settings", None)
    webhook_secret: str = getattr(settings, "github_webhook_secret", "") or ""

    raw_body = await request.body()

    # ── Signature verification ──────────────────────────────────────────
    if webhook_secret:
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        if not sig_header.startswith("sha256="):
            raise HTTPException(401, "Missing or malformed X-Hub-Signature-256 header.")
        expected = "sha256=" + hmac.new(
            webhook_secret.encode(), raw_body, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected, sig_header):
            raise HTTPException(401, "Webhook signature mismatch.")

    # ── Parse payload ───────────────────────────────────────────────────
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"Invalid JSON payload: {exc}") from exc

    event_type = request.headers.get("X-GitHub-Event", "unknown")
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})

    if event_type == "pull_request" and pr:
        pr_number = pr.get("number")
        pr_title = pr.get("title", "")
        pr_url = pr.get("html_url", "")
        repo = payload.get("repository", {}).get("full_name", "unknown/repo")
        author = pr.get("user", {}).get("login", "unknown")
        base_branch = pr.get("base", {}).get("ref", "")
        head_branch = pr.get("head", {}).get("ref", "")
        additions = pr.get("additions", 0)
        deletions = pr.get("deletions", 0)
        changed_files = pr.get("changed_files", 0)

        logger.info(
            "GitHub PR webhook: [%s] #%s '%s' by @%s (%s → %s) "
            "+%d/-%d lines across %d file(s) | %s",
            action.upper(),
            pr_number,
            pr_title,
            author,
            head_branch,
            base_branch,
            additions,
            deletions,
            changed_files,
            pr_url,
        )

        return {
            "received": True,
            "event": event_type,
            "action": action,
            "pr_number": pr_number,
            "repository": repo,
            "note": (
                "Event logged. Automated review posting is not yet enabled; "
                "trigger /api/review manually with the diff."
            ),
        }

    # Other event types (push, ping, etc.)
    logger.info("GitHub webhook: event=%s action=%s (no PR — ignored)", event_type, action)
    return {"received": True, "event": event_type, "action": action}
