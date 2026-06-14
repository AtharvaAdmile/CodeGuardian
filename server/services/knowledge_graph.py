"""
Knowledge Graph Service — NetworkX DiGraph with JSON persistence.

Represents a codebase as a directed graph where nodes are files, functions,
decisions, authors, and modules, and edges encode their relationships.

Node types (stored as node attribute "type"):
  "file"     — a source code file      {path, language, line_count}
  "function" — a function/class/method {name, file_path, start_line, end_line}
  "decision" — architectural decision  {title, decision_id}
  "author"   — a developer             {name, email}
  "module"   — a logical directory     {name}

Edge types (stored as edge attribute "type"):
  "imports"    (file → file)       — static import dependency
  "contains"   (file → function)   — file defines this symbol
  "decided_by" (decision → author) — who made this decision
  "affects"    (decision → file)   — which files this decision constrains
  "owns"       (author → file)     — primary maintainer (from expertise map)
  "belongs_to" (file → module)     — derived from directory structure

Design rules:
  - NEVER incrementally patch. Always rebuild from scratch (avoids ghost edges).
  - Graph is rebuilt in < 5 s for most projects (1 000 files).
  - Persisted to .codeguardian/knowledge_graph.json after every build.
  - Supabase storage is optional (best-effort JSONB write).
"""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import networkx as nx

logger = logging.getLogger("codeguardian.knowledge_graph")

# ── Constants ────────────────────────────────────────────────────────────

_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".js", ".ts", ".jsx", ".tsx"}
)
_SKIP_DIRS: frozenset[str] = frozenset(
    {"node_modules", "__pycache__", ".git", "venv", ".venv", "dist", "build",
     "chroma_data", "generated_test_cases", ".codeguardian", "coverage"}
)

# JS/TS import patterns — ordered most-to-least specific
_JS_IMPORT_PATTERNS: list[re.Pattern] = [
    re.compile(r'import\s+[^"\']*?\s+from\s+["\'](.+?)["\']'),   # import X from '…'
    re.compile(r'import\s+["\'](.+?)["\']'),                      # import '…'  (side-effect)
    re.compile(r'export\s+[^"\']*?\s+from\s+["\'](.+?)["\']'),   # export … from '…'
    re.compile(r'require\(\s*["\'](.+?)["\']\s*\)'),              # require('…')
]

# JS/TS symbol patterns
_JS_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(",
    re.MULTILINE,
)
_JS_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
    re.MULTILINE,
)
_JS_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:default\s+)?class\s+(\w+)",
    re.MULTILINE,
)


# ═════════════════════════════════════════════════════════════════════════
# KnowledgeGraph
# ═════════════════════════════════════════════════════════════════════════


class KnowledgeGraph:
    """NetworkX DiGraph-backed knowledge graph for a CodeGuardian project."""

    # ── Construction ─────────────────────────────────────────────────────

    def __init__(self) -> None:
        self._graph: nx.DiGraph = nx.DiGraph()

    # ── Build ────────────────────────────────────────────────────────────

    def build_from_project(
        self,
        project_path: str,
        git_service: Any | None = None,
        expertise_data: dict[str, list] | None = None,
        decisions: list[dict] | None = None,
    ) -> None:
        """
        Build the graph for *project_path*.

        Args:
            project_path:   Absolute path to the project root.
            git_service:    Optional GitService instance (used only for
                            any supplemental data not in expertise_data).
            expertise_data: Dict mapping file_path → list of ExpertiseEntry
                            (or plain dicts with keys author/email/commit_count).
            decisions:      List of decision dicts with keys title, decision_id,
                            context, reasoning, source_ref.
        """
        root = Path(project_path).resolve()
        all_files = _collect_files(root)
        rel_to_abs: dict[str, Path] = {
            str(fp.relative_to(root)): fp for fp in all_files
        }

        # ── a) File nodes ───────────────────────────────────────────────
        for rel, fp in rel_to_abs.items():
            try:
                line_count = _count_lines(fp)
            except OSError:
                line_count = 0
            self._graph.add_node(
                rel,
                type="file",
                path=rel,
                language=_detect_language(fp),
                line_count=line_count,
                health_score=_compute_file_health(line_count),
            )

        # ── b) Import edges (file → file) ───────────────────────────────
        for rel, fp in rel_to_abs.items():
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            raw_imports = _extract_raw_imports(content, fp)
            for raw in raw_imports:
                target = _resolve_import(raw, rel, rel_to_abs)
                if target and target != rel:
                    self._graph.add_edge(rel, target, type="imports")

        # ── c) Function/class nodes + "contains" edges ──────────────────
        for rel, fp in rel_to_abs.items():
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            symbols = _extract_symbols(content, fp)
            for sym in symbols:
                node_id = f"fn:{rel}:{sym['name']}:{sym['start_line']}"
                self._graph.add_node(
                    node_id,
                    type="function",
                    name=sym["name"],
                    file_path=rel,
                    start_line=sym["start_line"],
                    end_line=sym["end_line"],
                )
                self._graph.add_edge(rel, node_id, type="contains")

        # ── d) Module nodes + "belongs_to" edges ────────────────────────
        dirs_seen: set[str] = set()
        for rel in rel_to_abs:
            parent = str(Path(rel).parent)
            if parent in (".", ""):
                parent = "<root>"
            if parent not in dirs_seen:
                dirs_seen.add(parent)
                mod_id = f"mod:{parent}"
                if mod_id not in self._graph:
                    self._graph.add_node(
                        mod_id,
                        type="module",
                        name=parent,
                    )
            mod_id = f"mod:{parent}"
            self._graph.add_edge(rel, mod_id, type="belongs_to")

        # ── e) Author nodes + "owns" edges ──────────────────────────────
        if expertise_data:
            for file_rel, entries in expertise_data.items():
                if file_rel not in self._graph:
                    continue
                if not entries:
                    continue
                # Only the top expert gets "owns"; others are just author nodes
                for entry in entries:
                    author = _get_attr(entry, "author")
                    email = _get_attr(entry, "email", "")
                    if not author:
                        continue
                    author_id = f"author:{_stable_id(author)}"
                    if author_id not in self._graph:
                        self._graph.add_node(
                            author_id,
                            type="author",
                            name=author,
                            email=email,
                        )

                # Primary owner = entry with highest commit_count
                top = max(
                    entries,
                    key=lambda e: _get_attr(e, "commit_count", 0),
                    default=None,
                )
                if top:
                    author = _get_attr(top, "author")
                    if author:
                        author_id = f"author:{_stable_id(author)}"
                        self._graph.add_edge(author_id, file_rel, type="owns")

        # ── f) Decision nodes + "affects" / "decided_by" edges ──────────
        if decisions:
            for dec in decisions:
                title = dec.get("title", "untitled")
                dec_id_raw = dec.get("decision_id") or dec.get("id") or _stable_id(title)
                dec_node = f"dec:{dec_id_raw}"
                if dec_node not in self._graph:
                    self._graph.add_node(
                        dec_node,
                        type="decision",
                        title=title,
                        decision_id=str(dec_id_raw),
                        context=dec.get("context", ""),
                        reasoning=dec.get("reasoning", ""),
                        source_ref=dec.get("source_ref", ""),
                    )

                # Link to author if known
                author_name = dec.get("author") or dec.get("created_by")
                author_email = dec.get("author_email", "")
                if author_name:
                    author_id = f"author:{_stable_id(author_name)}"
                    if author_id not in self._graph:
                        self._graph.add_node(
                            author_id,
                            type="author",
                            name=author_name,
                            email=author_email,
                        )
                    self._graph.add_edge(dec_node, author_id, type="decided_by")

                # Heuristic: the decision "affects" any file whose path or name
                # appears in the decision text.
                dec_text = " ".join([
                    dec.get("context", ""),
                    dec.get("decision", ""),
                    dec.get("reasoning", ""),
                    dec.get("title", ""),
                ])
                for file_rel in rel_to_abs:
                    fname = Path(file_rel).name
                    if fname in dec_text or file_rel in dec_text:
                        self._graph.add_edge(dec_node, file_rel, type="affects")

        logger.info(
            "Knowledge graph built: %d nodes, %d edges  (project=%s)",
            self._graph.number_of_nodes(),
            self._graph.number_of_edges(),
            project_path,
        )

    def rebuild(
        self,
        project_path: str,
        git_service: Any | None = None,
        expertise_data: dict[str, list] | None = None,
        decisions: list[dict] | None = None,
    ) -> None:
        """
        Clear the graph entirely, then call build_from_project().

        Always use this instead of patching incrementally.
        """
        self._graph = nx.DiGraph()
        self.build_from_project(
            project_path=project_path,
            git_service=git_service,
            expertise_data=expertise_data,
            decisions=decisions,
        )

    # ── Query API ────────────────────────────────────────────────────────

    def get_file_context(self, file_path: str) -> dict[str, Any]:
        """
        Return structured context for *file_path*.

        Returns:
            {
              owners: [{"name": "...", "email": "..."}],
              decisions: [{"title": "...", "decision_id": "...", ...}],
              dependencies: ["rel/path/to/imported.py", ...],
              dependents: ["rel/path/to/importer.py", ...],
            }
        """
        if file_path not in self._graph:
            return {"owners": [], "decisions": [], "dependencies": [], "dependents": []}

        owners: list[dict] = []
        decisions: list[dict] = []
        dependencies: list[str] = []
        dependents: list[str] = []

        # Out-edges from file: imports (dependencies) + belongs_to
        for _, target, data in self._graph.out_edges(file_path, data=True):
            if data.get("type") == "imports":
                dependencies.append(target)

        # In-edges to file: owns (author → file), affects (decision → file),
        # imports (file → file)
        for source, _, data in self._graph.in_edges(file_path, data=True):
            edge_type = data.get("type")
            if edge_type == "imports":
                dependents.append(source)
            elif edge_type == "owns":
                node_data = dict(self._graph.nodes[source])
                owners.append({"name": node_data.get("name", ""), "email": node_data.get("email", "")})
            elif edge_type == "affects":
                node_data = dict(self._graph.nodes[source])
                decisions.append({
                    "title": node_data.get("title", ""),
                    "decision_id": node_data.get("decision_id", ""),
                    "context": node_data.get("context", ""),
                    "reasoning": node_data.get("reasoning", ""),
                    "source_ref": node_data.get("source_ref", ""),
                })

        return {
            "owners": owners,
            "decisions": decisions,
            "dependencies": dependencies,
            "dependents": dependents,
        }

    def get_impact_radius(
        self, file_path: str, depth: int = 3
    ) -> list[dict[str, Any]]:
        """
        Return all files that transitively import *file_path*, with distance.

        This answers "if I change file_path, which other files might break?"
        Uses BFS on the reversed import graph up to *depth* hops.

        Returns:
            [{"file": "rel/path.py", "distance": 1}, ...]
            sorted by ascending distance.
        """
        if file_path not in self._graph:
            return []

        # Build a subgraph of only "imports" edges, then reverse it
        import_edges = [
            (u, v) for u, v, d in self._graph.edges(data=True)
            if d.get("type") == "imports"
        ]
        imp_graph = nx.DiGraph()
        imp_graph.add_edges_from(import_edges)

        if file_path not in imp_graph:
            return []

        rev = imp_graph.reverse(copy=False)
        affected: list[dict] = []

        for node in nx.bfs_tree(rev, file_path, depth_limit=depth):
            if node == file_path:
                continue
            node_data = self._graph.nodes.get(node, {})
            if node_data.get("type") != "file":
                continue
            try:
                distance = nx.shortest_path_length(rev, file_path, node)
            except nx.NetworkXNoPath:
                distance = -1
            affected.append({
                "file": node,
                "distance": distance,
                "language": node_data.get("language", "unknown"),
                "line_count": node_data.get("line_count", 0),
            })

        return sorted(affected, key=lambda x: (x["distance"], x["file"]))

    def get_module_overview(self, module_name: str) -> dict[str, Any]:
        """
        Return files, function nodes, and decisions associated with a module.

        Args:
            module_name: Directory path relative to project root, e.g. "server/services".

        Returns:
            {"module": "...", "files": [...], "functions": [...], "decisions": [...]}
        """
        mod_id = f"mod:{module_name}"
        if mod_id not in self._graph:
            # Try partial match
            candidates = [
                n for n in self._graph.nodes
                if self._graph.nodes[n].get("type") == "module"
                and module_name in self._graph.nodes[n].get("name", "")
            ]
            if not candidates:
                return {"module": module_name, "files": [], "functions": [], "decisions": []}
            mod_id = candidates[0]

        # Files that belong to this module
        files: list[str] = [
            u for u, v, d in self._graph.in_edges(mod_id, data=True)
            if d.get("type") == "belongs_to"
        ]

        # Functions contained in those files
        functions: list[dict] = []
        for file_node in files:
            for _, fn_node, d in self._graph.out_edges(file_node, data=True):
                if d.get("type") == "contains":
                    fn_data = dict(self._graph.nodes[fn_node])
                    functions.append({
                        "name": fn_data.get("name", ""),
                        "file_path": fn_data.get("file_path", ""),
                        "start_line": fn_data.get("start_line"),
                        "end_line": fn_data.get("end_line"),
                    })

        # Decisions affecting any file in this module
        decisions: list[dict] = []
        seen_dec: set[str] = set()
        for file_node in files:
            for dec_node, _, d in self._graph.in_edges(file_node, data=True):
                if d.get("type") == "affects" and dec_node not in seen_dec:
                    seen_dec.add(dec_node)
                    dec_data = dict(self._graph.nodes[dec_node])
                    decisions.append({
                        "title": dec_data.get("title", ""),
                        "decision_id": dec_data.get("decision_id", ""),
                        "context": dec_data.get("context", ""),
                    })

        return {
            "module": module_name,
            "files": files,
            "functions": functions,
            "decisions": decisions,
        }

    def get_expertise_for_file(self, file_path: str) -> list[dict[str, Any]]:
        """
        Return authors ranked by expertise for *file_path*.

        Returns authors that have an "owns" edge to the file, along with
        their stored attributes. Currently returns at most one primary owner
        per file (the top committer from the expertise map).

        Returns:
            [{"name": "...", "email": "...", "rank": 1}]
        """
        if file_path not in self._graph:
            return []

        experts: list[dict] = []
        rank = 1
        for source, _, d in self._graph.in_edges(file_path, data=True):
            if d.get("type") == "owns":
                node_data = self._graph.nodes.get(source, {})
                experts.append({
                    "name": node_data.get("name", ""),
                    "email": node_data.get("email", ""),
                    "rank": rank,
                })
                rank += 1

        return experts

    def get_decisions_affecting_file(self, file_path: str) -> list[dict[str, Any]]:
        """
        Return all decision nodes that have an "affects" edge to *file_path*.

        Returns:
            [{"title": "...", "decision_id": "...", "context": "...", ...}]
        """
        if file_path not in self._graph:
            return []

        decisions: list[dict] = []
        for source, _, d in self._graph.in_edges(file_path, data=True):
            if d.get("type") == "affects":
                node_data = dict(self._graph.nodes[source])
                decisions.append({
                    "title": node_data.get("title", ""),
                    "decision_id": node_data.get("decision_id", ""),
                    "context": node_data.get("context", ""),
                    "reasoning": node_data.get("reasoning", ""),
                    "source_ref": node_data.get("source_ref", ""),
                })

        return decisions

    # ── Statistics & Node Accessors ──────────────────────────────────────

    def get_stats(self) -> dict[str, int]:
        """Return a summary of node and edge counts."""
        counts: dict[str, int] = {}
        for _, data in self._graph.nodes(data=True):
            t = data.get("type", "unknown")
            counts[t] = counts.get(t, 0) + 1

        edge_counts: dict[str, int] = {}
        for _, _, data in self._graph.edges(data=True):
            t = data.get("type", "unknown")
            edge_counts[t] = edge_counts.get(t, 0) + 1

        return {
            "total_nodes": self._graph.number_of_nodes(),
            "total_edges": self._graph.number_of_edges(),
            **{f"node_{k}": v for k, v in counts.items()},
            **{f"edge_{k}": v for k, v in edge_counts.items()},
        }

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Return data for a single node, or None if it doesn't exist."""
        if node_id not in self._graph:
            return None
        return {"id": node_id, **dict(self._graph.nodes[node_id])}

    def is_empty(self) -> bool:
        """Return True if the graph has no nodes."""
        return self._graph.number_of_nodes() == 0

    def all_file_nodes(self) -> list[dict[str, Any]]:
        """Return all file nodes as plain dicts."""
        return [
            {"id": n, **dict(d)}
            for n, d in self._graph.nodes(data=True)
            if d.get("type") == "file"
        ]

    # ── Persistence ──────────────────────────────────────────────────────

    def save_to_json(self, filepath: str) -> None:
        """
        Serialize the graph to JSON (NetworkX node-link format) and write to *filepath*.

        Creates parent directories if they don't exist.
        """
        path = Path(filepath)
        parent = path.parent
        # Clear any path component that exists as a file instead of directory
        for ancestor in reversed(parent.parents):
            if ancestor.exists() and not ancestor.is_dir():
                ancestor.unlink()
        if parent.exists() and not parent.is_dir():
            parent.unlink()
        parent.mkdir(parents=True, exist_ok=True)
        data = nx.node_link_data(self._graph)
        path.write_text(json.dumps(data, default=str), encoding="utf-8")
        logger.info("Knowledge graph saved → %s", filepath)

    def load_from_json(self, filepath: str) -> bool:
        """
        Restore the graph from a JSON file produced by save_to_json().

        Returns True on success, False if the file doesn't exist or is corrupt.
        """
        path = Path(filepath)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._graph = nx.node_link_graph(data)
            logger.info(
                "Knowledge graph loaded ← %s  (%d nodes, %d edges)",
                filepath,
                self._graph.number_of_nodes(),
                self._graph.number_of_edges(),
            )
            return True
        except Exception as exc:
            logger.warning("Failed to load knowledge graph from %s: %s", filepath, exc)
            return False

    def save_to_supabase(self, supabase_client: Any, project_id: str) -> None:
        """
        Persist the graph as a JSONB blob in the ``projects.config_json`` column.

        Best-effort — failures are logged but not re-raised.
        """
        if supabase_client is None:
            return
        try:
            data = nx.node_link_data(self._graph)
            supabase_client.table("projects").upsert(
                {"id": project_id, "config_json": json.dumps(data, default=str)}
            ).execute()
            logger.debug("Knowledge graph saved to Supabase for project %s", project_id)
        except Exception as exc:
            logger.warning("Supabase KG save failed (non-fatal): %s", exc)


# ═════════════════════════════════════════════════════════════════════════
# Module-level helpers
# ═════════════════════════════════════════════════════════════════════════


def _collect_files(root: Path) -> list[Path]:
    """Walk *root* and return all supported source files."""
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.startswith(".")
        ]
        for fname in filenames:
            fp = Path(dirpath) / fname
            if fp.suffix.lower() in _SUPPORTED_EXTENSIONS:
                results.append(fp)
    return results


def _detect_language(fp: Path) -> str:
    return {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
    }.get(fp.suffix.lower(), "unknown")


def _count_lines(fp: Path) -> int:
    """Count newlines in a file without loading it fully into memory."""
    count = 0
    with fp.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            count += chunk.count(b"\n")
    return count


def _compute_file_health(line_count: int) -> float:
    """
    Heuristic health score for a file based on line count.

    Rule of thumb:
      - < 50 lines:   0.95 (small — may be incomplete or a stub)
      -  50–200       1.00 (sweet spot — focused, readable)
      - 200–500       0.85 (getting long — worth watching)
      - 500–1000      0.65 (long — consider splitting)
      - > 1000        0.40 (needs refactoring)
    """
    if line_count <= 0:
        return 0.80
    if line_count < 50:
        return 0.95
    if line_count <= 200:
        return 1.00
    if line_count <= 500:
        return 0.85
    if line_count <= 1000:
        return 0.65
    return 0.40


def _stable_id(value: str) -> str:
    """Short deterministic ID derived from *value* (first 16 hex chars of SHA-256)."""
    return hashlib.sha256(value.encode()).hexdigest()[:16]


def _get_attr(obj: Any, attr: str, default: Any = None) -> Any:
    """Get attribute from either a dict or an object."""
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)


# ── Import extraction ────────────────────────────────────────────────────


def _extract_raw_imports(content: str, fp: Path) -> list[str]:
    """Return raw import strings from a source file (not yet resolved to paths)."""
    ext = fp.suffix.lower()
    if ext == ".py":
        return _py_imports(content)
    return _js_imports(content)


def _py_imports(content: str) -> list[str]:
    """Extract module names from Python import statements via ast."""
    imports: list[str] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                prefix = "." * (node.level or 0)
                imports.append(prefix + node.module)
            elif node.level:
                # bare "from . import x" — just a relative marker
                imports.append("." * node.level)

    return imports


def _js_imports(content: str) -> list[str]:
    """Extract module specifiers from JS/TS via regex."""
    imports: list[str] = []
    seen: set[str] = set()
    for pattern in _JS_IMPORT_PATTERNS:
        for match in pattern.finditer(content):
            spec = match.group(1)
            if spec not in seen:
                seen.add(spec)
                imports.append(spec)
    return imports


# ── Import resolution ────────────────────────────────────────────────────


def _resolve_import(
    raw: str,
    current_rel: str,
    known_files: dict[str, Path],
) -> str | None:
    """
    Attempt to resolve *raw* import specifier to a known project-relative path.

    Returns None for external (third-party) imports or when resolution fails.
    """
    # Relative JS/TS imports start with './' or '../'
    if raw.startswith("."):
        return _resolve_relative(raw, current_rel, known_files)

    # Python relative imports (level-prefix dots, e.g. ".sibling" or "..pkg")
    if raw.startswith("."):
        return _resolve_relative(raw, current_rel, known_files)

    # Python absolute imports — convert dots to path separators
    return _resolve_python_absolute(raw, known_files)


def _resolve_relative(
    raw: str,
    current_rel: str,
    known_files: dict[str, Path],
) -> str | None:
    """Resolve a relative import specifier against the current file's directory."""
    current_dir = Path(current_rel).parent

    # Strip leading dots for Python relative imports
    stripped = raw.lstrip(".")
    level = len(raw) - len(stripped)
    if level > 0 and not stripped.startswith("/"):
        # Go up `level - 1` parent directories
        base = current_dir
        for _ in range(level - 1):
            base = base.parent
        candidate_base = base / stripped.replace(".", "/") if stripped else base
    else:
        candidate_base = current_dir / raw

    candidate_str = str(candidate_base)

    # Try exact match + common extensions
    for ext in ("", ".py", ".ts", ".tsx", ".js", ".jsx"):
        probe = candidate_str + ext
        # Normalise path separators
        probe_norm = probe.replace("\\", "/").lstrip("/")
        if probe_norm in known_files:
            return probe_norm

    # Try index files (e.g. directory/index.ts)
    for index in ("index.ts", "index.tsx", "index.js", "__init__.py"):
        probe = str(candidate_base / index).replace("\\", "/").lstrip("/")
        if probe in known_files:
            return probe

    return None


def _resolve_python_absolute(
    raw: str,
    known_files: dict[str, Path],
) -> str | None:
    """Try to resolve a Python absolute import to a known relative path."""
    # Convert dots → path separators and try .py
    as_path = raw.replace(".", "/") + ".py"
    if as_path in known_files:
        return as_path

    # Try as a package: raw/path/__init__.py
    pkg_path = raw.replace(".", "/") + "/__init__.py"
    if pkg_path in known_files:
        return pkg_path

    # Fuzzy: check if any file ends with the module path
    parts = raw.split(".")
    for rel in known_files:
        rel_parts = list(Path(rel).with_suffix("").parts)
        if rel_parts[-len(parts):] == parts:
            return rel

    return None


# ── Symbol extraction ────────────────────────────────────────────────────


def _extract_symbols(content: str, fp: Path) -> list[dict]:
    """Extract top-level functions and classes from a source file."""
    ext = fp.suffix.lower()
    if ext == ".py":
        return _py_symbols(content)
    return _js_symbols(content)


def _py_symbols(content: str) -> list[dict]:
    """Use ast to extract top-level function/class definitions."""
    symbols: list[dict] = []
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return symbols

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append({
                "name": node.name,
                "start_line": node.lineno,
                "end_line": node.end_lineno or node.lineno,
            })

    return symbols


def _js_symbols(content: str) -> list[dict]:
    """Use regex to extract top-level function/class names from JS/TS."""
    symbols: list[dict] = []
    lines = content.splitlines()

    def _line_of(match: re.Match) -> int:
        return content[: match.start()].count("\n") + 1

    for pattern in (_JS_FUNCTION_RE, _JS_ARROW_RE, _JS_CLASS_RE):
        for m in pattern.finditer(content):
            name = m.group(1)
            line = _line_of(m)
            symbols.append({"name": name, "start_line": line, "end_line": line})

    return symbols
