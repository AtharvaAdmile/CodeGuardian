"""
Chat History Service — persists CG-pilot chat sessions to local JSON.

Sessions are stored in ``.codeguardian/chat_history/{project_id}/{session_id}.json``,
one JSON file per session. Each file holds the full message list plus metadata.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("codeguardian.chat_history")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class ChatHistoryService:
    """Persist and retrieve CG-pilot chat sessions."""

    def __init__(self, base_dir: str = ".codeguardian/chat_history") -> None:
        self._base_dir = base_dir
        logger.info("ChatHistoryService initialised — dir: %s", base_dir)

    # ── Path helpers ───────────────────────────────────────────────────────

    def _project_dir(self, project_id: str) -> str:
        return os.path.join(self._base_dir, project_id)

    def _session_path(self, project_id: str, session_id: str) -> str:
        return os.path.join(self._project_dir(project_id), f"{session_id}.json")

    # ── CRUD ───────────────────────────────────────────────────────────────

    def create_session(self, project_id: str, title: str) -> str:
        session_id = uuid.uuid4().hex[:12]
        now = datetime.now(timezone.utc).isoformat()
        session: dict[str, Any] = {
            "session_id": session_id,
            "project_id": project_id,
            "title": title,
            "messages": [],
            "created_at": now,
            "updated_at": now,
        }
        _ensure_dir(self._project_dir(project_id))
        with open(self._session_path(project_id, session_id), "w") as f:
            json.dump(session, f, indent=2)
        logger.info("Created chat session %s for project %s", session_id, project_id)
        return session_id

    def append_message(
        self,
        project_id: str,
        session_id: str,
        role: str,
        content: str,
        sources: list[dict] | None = None,
        tools_used: list[dict] | None = None,
        steps: list[dict] | None = None,
    ) -> None:
        path = self._session_path(project_id, session_id)
        if not os.path.isfile(path):
            logger.warning("Session %s not found, creating new", session_id)
            self.create_session(project_id, content[:80])
        with open(path) as f:
            session = json.load(f)
        message: dict[str, Any] = {"role": role, "content": content}
        if sources:
            message["sources"] = sources
        if tools_used:
            message["tools_used"] = tools_used
        if steps:
            message["steps"] = steps
        session["messages"].append(message)
        session["updated_at"] = datetime.now(timezone.utc).isoformat()
        with open(path, "w") as f:
            json.dump(session, f, indent=2)

    def get_sessions(self, project_id: str, limit: int = 50) -> list[dict]:
        pdir = self._project_dir(project_id)
        if not os.path.isdir(pdir):
            return []
        sessions: list[dict] = []
        for fname in sorted(os.listdir(pdir), reverse=True):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(pdir, fname)
            try:
                with open(path) as f:
                    session = json.load(f)
                sessions.append({
                    "session_id": session.get("session_id", fname.replace(".json", "")),
                    "project_id": session.get("project_id", project_id),
                    "title": session.get("title", ""),
                    "message_count": len(session.get("messages", [])),
                    "created_at": session.get("created_at", ""),
                    "updated_at": session.get("updated_at", ""),
                })
            except Exception as e:
                logger.warning("Failed to read session %s: %s", fname, e)
            if len(sessions) >= limit:
                break
        return sessions

    def get_session(self, project_id: str, session_id: str) -> dict | None:
        path = self._session_path(project_id, session_id)
        if not os.path.isfile(path):
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to read session %s: %s", session_id, e)
            return None

    def delete_session(self, project_id: str, session_id: str) -> bool:
        path = self._session_path(project_id, session_id)
        if not os.path.isfile(path):
            return False
        os.remove(path)
        logger.info("Deleted chat session %s", session_id)
        return True

    def get_recent(self, project_id: str, limit: int = 5) -> list[dict]:
        sessions = self.get_sessions(project_id, limit=limit)
        result = []
        for s in sessions:
            session = self.get_session(project_id, s["session_id"])
            if session and session.get("messages"):
                first_user = next(
                    (m for m in session["messages"] if m.get("role") == "user"),
                    None,
                )
                result.append({
                    "session_id": s["session_id"],
                    "title": s["title"] or (first_user["content"][:100] if first_user else ""),
                    "preview": first_user["content"][:120] if first_user else "",
                    "created_at": s["created_at"],
                    "updated_at": s["updated_at"],
                    "message_count": s["message_count"],
                })
        return result
