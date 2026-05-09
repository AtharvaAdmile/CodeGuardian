"""
Commit review routes.

The previous code-snippet review endpoint has been replaced with a git-backed
workflow for reviewing recent commits and deciding whether the current working
tree should be committed.
"""

from __future__ import annotations

import logging
from pathlib import Path

import git
from fastapi import APIRouter, HTTPException
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from server.models.route_schemas import (
    CommitActionResponse,
    CommitFileChangeSchema,
    CommitHistoryEntrySchema,
    CommitRecommendationSchema,
    CommitRequest,
    CommitReviewRequest,
    CommitReviewResponse,
)

logger = logging.getLogger("codeguardian.routes.review")

router = APIRouter(prefix="/api/review", tags=["commit-review"])

_DIFF_LIMIT = 12000
_HISTORY_DIFF_LIMIT = 18000
_SENSITIVE_NAMES = {".env", ".env.local", ".env.production", "id_rsa", "id_ed25519"}
_SENSITIVE_TOKENS = ("secret", "password", "private_key", "apikey", "api_key", "token")


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + f"\n\n... truncated {len(value) - limit} characters ..."


def _open_repo(project_path: str) -> git.Repo:
    path = Path(project_path).expanduser()
    if not path.exists() or not path.is_dir():
        raise HTTPException(404, f"Project path not found: {project_path}")

    try:
        repo = git.Repo(path, search_parent_directories=True)
    except (InvalidGitRepositoryError, NoSuchPathError) as exc:
        raise HTTPException(400, f"Not a git repository: {project_path}") from exc

    if repo.bare or repo.working_tree_dir is None:
        raise HTTPException(400, f"Repository has no working tree: {project_path}")
    return repo


def _head_sha(repo: git.Repo) -> str:
    try:
        return repo.head.commit.hexsha
    except Exception:
        return ""


def _branch_name(repo: git.Repo) -> str:
    try:
        return repo.active_branch.name
    except TypeError:
        sha = _head_sha(repo)
        return f"detached:{sha[:7]}" if sha else "unborn"


def _parse_name_status(output: str) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        status = parts[0]
        file_path = parts[-1]
        statuses[file_path] = status
    return statuses


def _parse_numstat(output: str) -> dict[str, tuple[int, int]]:
    stats: dict[str, tuple[int, int]] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        raw_additions, raw_deletions, file_path = parts[0], parts[1], parts[-1]
        additions = int(raw_additions) if raw_additions.isdigit() else 0
        deletions = int(raw_deletions) if raw_deletions.isdigit() else 0
        stats[file_path] = (additions, deletions)
    return stats


def _file_diff(repo: git.Repo, file_path: str, staged: bool, untracked: bool) -> str:
    if untracked:
        return "Untracked file. Stage it to include the full file in a git diff."
    try:
        args = ["--", file_path]
        if staged:
            diff = repo.git.diff("--cached", *args)
        else:
            diff = repo.git.diff(*args)
        return _truncate(diff, _DIFF_LIMIT)
    except GitCommandError as exc:
        logger.debug("Could not generate diff for %s: %s", file_path, exc)
        return ""


def _collect_working_tree(repo: git.Repo) -> list[CommitFileChangeSchema]:
    changes: dict[str, CommitFileChangeSchema] = {}

    try:
        staged_statuses = _parse_name_status(repo.git.diff("--cached", "--name-status"))
        staged_stats = _parse_numstat(repo.git.diff("--cached", "--numstat"))
    except GitCommandError:
        staged_statuses = {}
        staged_stats = {}

    try:
        unstaged_statuses = _parse_name_status(repo.git.diff("--name-status"))
        unstaged_stats = _parse_numstat(repo.git.diff("--numstat"))
    except GitCommandError:
        unstaged_statuses = {}
        unstaged_stats = {}

    for file_path, status in staged_statuses.items():
        additions, deletions = staged_stats.get(file_path, (0, 0))
        changes[file_path] = CommitFileChangeSchema(
            file_path=file_path,
            status=status,
            additions=additions,
            deletions=deletions,
            staged=True,
            diff=_file_diff(repo, file_path, staged=True, untracked=False),
        )

    for file_path, status in unstaged_statuses.items():
        additions, deletions = unstaged_stats.get(file_path, (0, 0))
        existing = changes.get(file_path)
        if existing:
            existing.unstaged = True
            existing.status = f"{existing.status}/{status}"
            existing.additions += additions
            existing.deletions += deletions
            if not existing.diff:
                existing.diff = _file_diff(repo, file_path, staged=False, untracked=False)
        else:
            changes[file_path] = CommitFileChangeSchema(
                file_path=file_path,
                status=status,
                additions=additions,
                deletions=deletions,
                unstaged=True,
                diff=_file_diff(repo, file_path, staged=False, untracked=False),
            )

    for file_path in repo.untracked_files:
        changes[file_path] = CommitFileChangeSchema(
            file_path=file_path,
            status="??",
            untracked=True,
            diff=_file_diff(repo, file_path, staged=False, untracked=True),
        )

    return sorted(changes.values(), key=lambda item: item.file_path)


def _commit_files(repo: git.Repo, commit: git.Commit) -> list[CommitFileChangeSchema]:
    stats_by_file = commit.stats.files
    if commit.parents:
        diffs = commit.parents[0].diff(commit)
    else:
        diffs = commit.diff(git.NULL_TREE)

    files: list[CommitFileChangeSchema] = []
    seen: set[str] = set()
    for diff in diffs:
        file_path = diff.b_path or diff.a_path or ""
        if not file_path:
            continue
        seen.add(file_path)
        stat = stats_by_file.get(file_path, {})
        files.append(
            CommitFileChangeSchema(
                file_path=file_path,
                status=diff.change_type or "",
                additions=int(stat.get("insertions", 0)),
                deletions=int(stat.get("deletions", 0)),
            )
        )

    for file_path, stat in stats_by_file.items():
        if file_path in seen:
            continue
        files.append(
            CommitFileChangeSchema(
                file_path=file_path,
                status="M",
                additions=int(stat.get("insertions", 0)),
                deletions=int(stat.get("deletions", 0)),
            )
        )

    return sorted(files, key=lambda item: item.file_path)


def _recent_commits(repo: git.Repo, limit: int) -> list[CommitHistoryEntrySchema]:
    try:
        commits = list(repo.iter_commits(max_count=limit))
    except (ValueError, GitCommandError):
        return []

    history: list[CommitHistoryEntrySchema] = []
    for commit in commits:
        files = _commit_files(repo, commit)
        try:
            diff = repo.git.show("--format=", "--find-renames", "--stat", "--patch", commit.hexsha)
        except GitCommandError:
            diff = ""

        history.append(
            CommitHistoryEntrySchema(
                sha=commit.hexsha,
                short_sha=commit.hexsha[:7],
                message=commit.summary,
                author=str(commit.author),
                email=str(commit.author.email or ""),
                date=commit.committed_datetime.isoformat(),
                files=files,
                insertions=sum(item.additions for item in files),
                deletions=sum(item.deletions for item in files),
                diff=_truncate(diff, _HISTORY_DIFF_LIMIT),
            )
        )
    return history


def _has_conflicts(repo: git.Repo) -> bool:
    try:
        return bool(repo.index.unmerged_blobs())
    except GitCommandError:
        return False


def _looks_sensitive(file_path: str) -> bool:
    path = file_path.lower()
    name = Path(path).name
    return name in _SENSITIVE_NAMES or any(token in path for token in _SENSITIVE_TOKENS)


def _summary(changes: list[CommitFileChangeSchema]) -> str:
    if not changes:
        return "The working tree is clean. There are no staged, unstaged, or untracked changes to commit."

    files = len(changes)
    additions = sum(item.additions for item in changes)
    deletions = sum(item.deletions for item in changes)
    staged = sum(1 for item in changes if item.staged)
    unstaged = sum(1 for item in changes if item.unstaged)
    untracked = sum(1 for item in changes if item.untracked)
    affected = ", ".join(item.file_path for item in changes[:6])
    if files > 6:
        affected += f", and {files - 6} more"
    return (
        f"{files} file(s) have uncommitted changes (+{additions}/-{deletions}). "
        f"{staged} staged, {unstaged} unstaged, {untracked} untracked. "
        f"Affected files: {affected}."
    )


def _suggested_message(changes: list[CommitFileChangeSchema]) -> str:
    if not changes:
        return ""
    paths = [item.file_path for item in changes]
    if all(path.startswith(("docs/", "README")) or "/docs/" in path for path in paths):
        return "Update documentation"
    if all("/test" in path.lower() or path.lower().startswith("test") for path in paths):
        return "Update tests"
    if len(paths) == 1:
        stem = Path(paths[0]).stem.replace("_", " ").replace("-", " ")
        return f"Update {stem}"
    common_roots = {path.split("/", 1)[0] for path in paths if "/" in path}
    if len(common_roots) == 1:
        root = next(iter(common_roots)).replace("_", " ").replace("-", " ")
        return f"Update {root}"
    return "Update project changes"


def _recommendation(repo: git.Repo, changes: list[CommitFileChangeSchema]) -> CommitRecommendationSchema:
    concerns: list[str] = []
    total_delta = sum(item.additions + item.deletions for item in changes)
    sensitive_files = [item.file_path for item in changes if _looks_sensitive(item.file_path)]

    if not changes:
        return CommitRecommendationSchema(
            should_commit=False,
            title="Nothing to commit",
            reason="The working tree is clean.",
        )

    if _has_conflicts(repo):
        concerns.append("Resolve merge conflicts before committing.")

    if sensitive_files:
        visible = ", ".join(sensitive_files[:3])
        concerns.append(f"Potentially sensitive file path(s): {visible}.")

    if len(changes) > 25:
        concerns.append("This touches more than 25 files; consider splitting it into smaller commits.")

    if total_delta > 1200:
        concerns.append("This is a large diff; consider reviewing and splitting it before committing.")

    should_commit = not concerns
    title = "Ready to commit" if should_commit else "Review before committing"
    reason = (
        "The change set is small enough to commit as one unit."
        if should_commit
        else "There are concerns that should be checked before creating a commit."
    )

    return CommitRecommendationSchema(
        should_commit=should_commit,
        title=title,
        reason=reason,
        concerns=concerns,
        suggested_message=_suggested_message(changes),
    )


def _build_status(repo: git.Repo, history_limit: int) -> CommitReviewResponse:
    changes = _collect_working_tree(repo)
    return CommitReviewResponse(
        project_path=str(repo.working_tree_dir or ""),
        branch=_branch_name(repo),
        head_sha=_head_sha(repo),
        is_git_repo=True,
        has_changes=bool(changes),
        staged_files=sum(1 for item in changes if item.staged),
        unstaged_files=sum(1 for item in changes if item.unstaged),
        untracked_files=sum(1 for item in changes if item.untracked),
        uncommitted_files=changes,
        recent_commits=_recent_commits(repo, history_limit),
        summary=_summary(changes),
        recommendation=_recommendation(repo, changes),
    )


@router.post("/status", response_model=CommitReviewResponse)
async def commit_review_status(body: CommitReviewRequest) -> CommitReviewResponse:
    repo = _open_repo(body.project_path)
    try:
        return _build_status(repo, body.history_limit)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error building commit review status")
        raise HTTPException(500, f"Commit review failed: {exc}") from exc


@router.post("/commit", response_model=CommitActionResponse)
async def commit_changes(body: CommitRequest) -> CommitActionResponse:
    message = body.message.strip()
    if not message:
        raise HTTPException(422, "Commit message cannot be empty.")

    repo = _open_repo(body.project_path)
    if _has_conflicts(repo):
        raise HTTPException(409, "Resolve merge conflicts before committing.")

    before = _collect_working_tree(repo)
    if not before:
        return CommitActionResponse(
            committed=False,
            message=message,
            status=_build_status(repo, body.history_limit),
            error="No staged, unstaged, or untracked changes to commit.",
        )

    try:
        repo.git.add("--all")
        repo.git.commit("-m", message)
    except GitCommandError as exc:
        logger.warning("Commit failed: %s", exc)
        raise HTTPException(500, f"Git commit failed: {exc.stderr or exc}") from exc

    status = _build_status(repo, body.history_limit)
    return CommitActionResponse(
        committed=True,
        commit_sha=_head_sha(repo),
        message=message,
        status=status,
    )
