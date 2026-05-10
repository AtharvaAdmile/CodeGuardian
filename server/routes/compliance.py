"""
Compliance check routes — tool-calling agent for codebase compliance scanning.

POST /api/compliance/scan         — start a compliance scan (polling-based)
POST /api/compliance/scan/stream  — start a compliance scan (SSE streaming)
GET  /api/compliance/status/{job_id}    — poll scan progress
GET  /api/compliance/report/{job_id}    — get final report
GET  /api/compliance/checks             — list available check types
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, Request
from starlette.responses import StreamingResponse

from server.agents.compliance_agent import ComplianceAgent, get_available_checks
from server.config import get_settings
from server.models.route_schemas import (
    ComplianceCheckType,
    ComplianceFinding,
    ComplianceReport,
    ComplianceScanRequest,
    ComplianceScanStatus,
    ComplianceStep,
)

logger = logging.getLogger("codeguardian.routes.compliance")

router = APIRouter(prefix="/api/compliance", tags=["compliance"])

_PERSIST_DIR = ".codeguardian/compliance"


def _persist_path(project_id: str) -> str:
    return os.path.join(_PERSIST_DIR, f"{project_id}.json")


def _save_report(project_id: str, report: dict) -> None:
    os.makedirs(_PERSIST_DIR, exist_ok=True)
    try:
        with open(_persist_path(project_id), "w") as f:
            json.dump(report, f, indent=2, default=str)
    except Exception as e:
        logger.warning("Failed to persist compliance report: %s", e)


def _load_report(project_id: str) -> dict | None:
    path = _persist_path(project_id)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load compliance report: %s", e)
    return None


@dataclass
class ComplianceJob:
    job_id: str
    status: str = "queued"
    project_id: str = ""
    project_path: str = ""
    selected_checks: list[str] = field(default_factory=list)
    current_check: str | None = None
    files_scanned: int = 0
    files_total: int = 0
    total_violations: int = 0
    violation_counts: dict[str, int] = field(
        default_factory=lambda: {"critical": 0, "high": 0, "medium": 0, "low": 0}
    )
    compliance_score: float | None = None
    steps: list[dict] = field(default_factory=list)
    report: dict | None = None
    error: str | None = None
    can_overwrite: bool = True


compliance_jobs: dict[str, ComplianceJob] = {}


async def _run_scan_polling(job: ComplianceJob, request: Request):
    """Background task: run the ComplianceAgent for polling-based endpoint."""
    try:
        settings = get_settings()
        agent = ComplianceAgent(
            api_key=settings.nvidia_nim_api_key,
            base_url=settings.nvidia_nim_base_url,
            model=settings.nvidia_llm_model,
            max_tool_rounds=settings.compliance_max_tool_rounds,
        )

        async def on_step(step: ComplianceStep):
            job.steps.append(step.model_dump())
            if step.findings:
                for f in step.findings:
                    sev = f.severity
                    if sev in job.violation_counts:
                        job.violation_counts[sev] += 1
                    job.total_violations += 1
            if step.check_type and step.check_type != "_overall":
                job.current_check = step.check_type

        agent._step_callback = on_step
        findings, steps, _ = await agent.run_all(
            project_id=job.project_id,
            project_path=job.project_path,
            selected_checks=job.selected_checks,
        )

        await agent.close()

        # Compute score
        score = _compute_score(findings)
        counts = _count_by_severity(findings)
        passed = score >= 70.0 and counts.get("critical", 0) == 0

        summary_lines = []
        for step in steps:
            if step.action == "check_complete":
                summary_lines.append(f"[{step.check_type}] {step.message}")
        summary = "\n".join(summary_lines) if summary_lines else f"Found {len(findings)} violation(s). Score: {score:.0f}/100."

        report = {
            "scanned_files": sum(1 for s in steps if s.action in ("tool_call", "finding")),
            "total_violations": len(findings),
            "violation_counts": counts,
            "compliance_score": round(score, 1),
            "passed": passed,
            "summary": summary,
            "violations": [f.model_dump() for f in findings],
            "check_types_ran": job.selected_checks,
            "steps": [s.model_dump() for s in steps],
            "can_overwrite": True,
        }

        job.report = report
        job.status = "completed"
        job.compliance_score = score

        _save_report(job.project_id, report)

    except asyncio.CancelledError:
        job.status = "cancelled"
        logger.info("Compliance scan %s cancelled", job.job_id)
    except Exception as exc:
        logger.exception("Compliance scan %s failed", job.job_id)
        job.status = "failed"
        job.error = str(exc)


async def _run_scan_stream(
    body: ComplianceScanRequest,
    request: Request,
) -> AsyncGenerator[str, None]:
    """Run the ComplianceAgent and stream steps via SSE using a queue."""
    settings = get_settings()

    if not settings.nvidia_nim_api_key:
        yield f"data: {json.dumps({'type': 'error', 'message': 'NVIDIA NIM API key not configured'})}\n\n"
        return

    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

    async def run_agent():
        try:
            agent = ComplianceAgent(
                api_key=settings.nvidia_nim_api_key,
                base_url=settings.nvidia_nim_base_url,
                model=settings.nvidia_llm_model,
                max_tool_rounds=settings.compliance_max_tool_rounds,
            )

            async def emit_step(step: ComplianceStep):
                await queue.put(("step", step))

            agent._step_callback = emit_step

            findings, steps, _ = await agent.run_all(
                project_id=body.project_id,
                project_path=body.project_path,
                selected_checks=body.selected_checks,
            )

            await agent.close()

            score = _compute_score(findings)
            counts = _count_by_severity(findings)
            passed = score >= 70.0 and counts.get("critical", 0) == 0

            summary_lines = []
            for step in steps:
                if step.action == "check_complete":
                    summary_lines.append(f"[{step.check_type}] {step.message}")
            summary = "\n".join(summary_lines) if summary_lines else f"Found {len(findings)} violation(s). Score: {score:.0f}/100."

            report = {
                "scanned_files": sum(1 for s in steps if s.action in ("tool_call", "finding")),
                "total_violations": len(findings),
                "violation_counts": counts,
                "compliance_score": round(score, 1),
                "passed": passed,
                "summary": summary,
                "violations": [f.model_dump() for f in findings],
                "check_types_ran": body.selected_checks,
                "steps": [s.model_dump() for s in steps],
                "can_overwrite": True,
            }

            _save_report(body.project_id, report)
            await queue.put(("complete", report))

        except Exception as exc:
            logger.exception("Compliance stream scan failed")
            await queue.put(("error", str(exc)))

    task = asyncio.create_task(run_agent())

    try:
        while True:
            msg_type, data = await queue.get()
            if msg_type == "step":
                step: ComplianceStep = data
                payload = {
                    "type": "step",
                    "step": step.model_dump(),
                    "progress": {
                        "total_violations": len(step.findings),
                        "violation_counts": _count_by_severity(step.findings),
                    },
                }
                yield f"data: {json.dumps(payload)}\n\n"
            elif msg_type == "complete":
                yield f"data: {json.dumps({'type': 'complete', 'report': data})}\n\n"
                break
            elif msg_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': str(data)})}\n\n"
                break
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _compute_score(findings: list[ComplianceFinding]) -> float:
    if not findings:
        return 100.0
    weights = {"critical": 25, "high": 10, "medium": 3, "low": 1}
    total_penalty = sum(weights.get(f.severity, 1) for f in findings)
    return max(0.0, min(100.0, 100.0 - total_penalty))


def _count_by_severity(findings: list[ComplianceFinding]) -> dict[str, int]:
    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.severity
        counts[sev] = counts.get(sev, 0) + 1
    return counts


def _findings_to_models(findings: list[dict]) -> list[ComplianceFinding]:
    return [ComplianceFinding(**f) for f in findings]


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.get("/checks", response_model=list[ComplianceCheckType])
async def list_compliance_checks():
    """Return all available compliance check types with descriptions."""
    return [ComplianceCheckType(**c) for c in get_available_checks()]


@router.get("/report/{project_id}", response_model=ComplianceReport | None)
async def get_compliance_report(project_id: str):
    """Get the latest compliance report for a project (from persistence)."""
    saved = _load_report(project_id)
    if saved:
        return ComplianceReport(**saved)
    return None


@router.post("/scan", response_model=ComplianceScanStatus)
async def start_compliance_scan(body: ComplianceScanRequest, request: Request):
    """Start a compliance scan job (polling-based). Returns immediately with job_id."""
    job_id = str(uuid.uuid4())
    job = ComplianceJob(
        job_id=job_id,
        project_id=body.project_id,
        project_path=body.project_path,
        selected_checks=body.selected_checks,
    )
    compliance_jobs[job_id] = job

    asyncio.create_task(_run_scan_polling(job, request))

    return ComplianceScanStatus(
        job_id=job_id,
        status="queued",
        can_overwrite=True,
    )


@router.get("/status/{job_id}", response_model=ComplianceScanStatus)
async def get_compliance_status(job_id: str):
    """Poll the progress of a running compliance scan."""
    job = compliance_jobs.get(job_id)
    if not job:
        raise HTTPException(404, f"Compliance job not found: {job_id}")

    return ComplianceScanStatus(
        job_id=job.job_id,
        status=job.status,
        current_check=job.current_check,
        files_scanned=len([s for s in job.steps if s.get("action") == "finding"]),
        total_violations=job.total_violations,
        violation_counts=job.violation_counts,
        compliance_score=job.compliance_score,
        steps=[ComplianceStep(**s) for s in job.steps],
        error=job.error,
        can_overwrite=True,
    )


@router.post("/scan/stream")
async def start_compliance_scan_stream(body: ComplianceScanRequest, request: Request):
    """Start a compliance scan with SSE streaming for real-time agent step visibility."""
    return StreamingResponse(
        _run_scan_stream(body, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
