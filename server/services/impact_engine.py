"""
Static dependency analysis engine for CodeGuardian.

DependencyAnalyzer
    Extracts import records from Python (tree-sitter >= 0.23, ast fallback)
    and JS/TS (regex). Each record carries the raw specifier, a preliminary
    import_type, and the line number of the import statement.

build_dependency_graph(project_path) → nx.DiGraph
    Walks all supported files, extracts imports, resolves specifiers to
    project-relative paths, and returns a DiGraph whose edges carry:
        import_type : "relative" | "direct" | "external"
        line_number : int

calculate_centrality(graph) → dict[str, float]
    PageRank over the dependency graph. High-score files have the largest
    potential blast radius when changed.

merge_into_knowledge_graph(dep_graph, knowledge_graph)
    Enriches existing "imports" edges in the KnowledgeGraph with import_type
    and line_number metadata; inserts edges that are missing entirely.

BlastRadiusCalculator
    BFS on the reversed dependency graph to find all files that transitively
    import `changed_file`.  Scores each by risk = (1/distance) * normalised
    centrality * normalised churn.  Returns a BlastRadiusReport grouped into
    high / medium / low risk buckets with suggested reviewers.

detect_breaking_changes(old_content, new_content, language)
    AST-based (Python) / regex-based (JS/TS) comparison of two versions of a
    file.  Identifies removed functions, added required parameters, removed
    parameters, and changed return-type annotations.  Deterministic — no LLM.
"""

from __future__ import annotations

import ast as stdlib_ast
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import networkx as nx

logger = logging.getLogger("codeguardian.impact_engine")

# ── Constants ─────────────────────────────────────────────────────────────────

_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {".py", ".js", ".ts", ".jsx", ".tsx"}
)
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "__pycache__",
        ".git",
        "venv",
        ".venv",
        "dist",
        "build",
        "chroma_data",
        "generated_test_cases",
        ".codeguardian",
        "coverage",
    }
)

# JS/TS patterns — ordered most-to-least specific, compiled with DOTALL so
# multi-line imports (braced named imports) are matched correctly.
_JS_IMPORT_PATTERNS: list[re.Pattern] = [
    re.compile(r'import\s+[^"\']*?\s+from\s+["\'](.+?)["\']', re.DOTALL),
    re.compile(r'import\s+["\'](.+?)["\']'),
    re.compile(r'export\s+[^"\']*?\s+from\s+["\'](.+?)["\']', re.DOTALL),
    re.compile(r'require\(\s*["\'](.+?)["\']\s*\)'),
]


# ── Data Types ────────────────────────────────────────────────────────────────


@dataclass
class ImportRecord:
    """A single import statement extracted from a source file."""

    raw_specifier: str
    # Preliminary classification set during extraction:
    #   "relative"  → starts with "." (Python or JS relative)
    #   "absolute"  → Python absolute (dotted module name)
    #   "external"  → JS non-relative (node_modules)
    import_type: str
    line_number: int
    resolved_path: str | None = None


# ── DependencyAnalyzer ────────────────────────────────────────────────────────


class DependencyAnalyzer:
    """
    Extracts ImportRecord objects from Python and JavaScript/TypeScript source.

    Python files are parsed with tree-sitter-python for accurate line numbers
    and relative-import detection.  Falls back to stdlib ``ast`` if the
    tree-sitter package is not installed.

    JS/TS files are parsed with regex; node_modules imports are tagged
    "external" and never resolved.
    """

    def __init__(self) -> None:
        self._ts_parser: Any = None
        self._ts_available: bool = False
        self._init_tree_sitter()

    # ── Initialisation ────────────────────────────────────────────────────────

    def _init_tree_sitter(self) -> None:
        try:
            import tree_sitter_python as tspython  # type: ignore[import]
            from tree_sitter import Language, Parser  # type: ignore[import]

            py_lang = Language(tspython.language())
            self._ts_parser = Parser(py_lang)
            self._ts_available = True
            logger.debug("tree-sitter-python loaded")
        except Exception as exc:
            logger.warning(
                "tree-sitter-python unavailable (%s); using stdlib ast fallback",
                exc,
            )

    # ── Public extraction API ─────────────────────────────────────────────────

    def extract_imports(self, content: str, file_rel: str) -> list[ImportRecord]:
        """Return all import records found in *content* (source file at *file_rel*)."""
        ext = Path(file_rel).suffix.lower()
        if ext == ".py":
            return (
                self._ts_extract_python(content)
                if self._ts_available
                else self._ast_extract_python(content)
            )
        return self._regex_extract_js(content)

    # ── Python — tree-sitter ──────────────────────────────────────────────────

    def _ts_extract_python(self, content: str) -> list[ImportRecord]:
        try:
            tree = self._ts_parser.parse(content.encode("utf-8", errors="replace"))
            records: list[ImportRecord] = []
            _ts_walk_imports(tree.root_node, records)
            return records
        except Exception as exc:
            logger.debug("tree-sitter parse failed (%s); falling back to ast", exc)
            return self._ast_extract_python(content)

    # ── Python — stdlib ast fallback ──────────────────────────────────────────

    def _ast_extract_python(self, content: str) -> list[ImportRecord]:
        records: list[ImportRecord] = []
        try:
            tree = stdlib_ast.parse(content)
        except SyntaxError:
            return records

        for node in stdlib_ast.walk(tree):
            if isinstance(node, stdlib_ast.Import):
                for alias in node.names:
                    records.append(
                        ImportRecord(
                            raw_specifier=alias.name,
                            import_type="absolute",
                            line_number=node.lineno,
                        )
                    )
            elif isinstance(node, stdlib_ast.ImportFrom):
                prefix = "." * (node.level or 0)
                raw = prefix + (node.module or "")
                records.append(
                    ImportRecord(
                        raw_specifier=raw,
                        import_type="relative" if node.level else "absolute",
                        line_number=node.lineno,
                    )
                )

        return records

    # ── JS / TS — regex ───────────────────────────────────────────────────────

    def _regex_extract_js(self, content: str) -> list[ImportRecord]:
        records: list[ImportRecord] = []
        seen: set[str] = set()

        for pattern in _JS_IMPORT_PATTERNS:
            for m in pattern.finditer(content):
                spec = m.group(1)
                if spec in seen:
                    continue
                seen.add(spec)
                line_num = content[: m.start()].count("\n") + 1
                records.append(
                    ImportRecord(
                        raw_specifier=spec,
                        import_type="relative" if spec.startswith(".") else "external",
                        line_number=line_num,
                    )
                )

        return records


# ── Public API ────────────────────────────────────────────────────────────────


def build_dependency_graph(project_path: str) -> nx.DiGraph:
    """
    Walk *project_path*, extract imports from every supported file, resolve
    specifiers to project-relative paths, and return a dependency DiGraph.

    Node keys  : project-relative file path strings.
    Edge data  :
        ``type``        — always "imports"
        ``import_type`` — "relative" | "direct" | "external"
        ``line_number`` — int (source line of the import statement)

    Unresolved and node_modules imports are excluded from the graph.
    """
    analyzer = DependencyAnalyzer()
    graph: nx.DiGraph = nx.DiGraph()

    root = Path(project_path).resolve()
    all_files = _collect_files(root)
    rel_to_abs: dict[str, Path] = {
        str(fp.relative_to(root)): fp for fp in all_files
    }

    # ── File nodes ────────────────────────────────────────────────────────────
    for rel, fp in rel_to_abs.items():
        graph.add_node(rel, path=rel, language=_detect_language(fp))

    # ── Import edges ──────────────────────────────────────────────────────────
    for rel, fp in rel_to_abs.items():
        try:
            content = fp.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", fp, exc)
            continue

        for rec in analyzer.extract_imports(content, rel):
            # Skip node_modules / JS external specifiers immediately.
            if rec.import_type == "external":
                continue

            resolved = _resolve_import(rec.raw_specifier, rel, rel_to_abs)
            if resolved is None or resolved == rel:
                continue

            # Final edge type:
            #   "relative" — ./ or ../ import (Python or JS)
            #   "direct"   — Python absolute import resolved within the project
            edge_type = "relative" if rec.import_type == "relative" else "direct"

            graph.add_edge(
                rel,
                resolved,
                type="imports",
                import_type=edge_type,
                line_number=rec.line_number,
            )

    logger.info(
        "Dependency graph built for %s: %d file nodes, %d import edges",
        project_path,
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )
    return graph


def calculate_centrality(graph: nx.DiGraph) -> dict[str, float]:
    """
    Compute PageRank over the dependency graph.

    Files with a high PageRank score are imported by many other files and
    therefore have the largest potential blast radius when changed.

    Returns a dict mapping ``file_path → PageRank score`` (values sum to 1).
    If the graph has no edges every file gets an equal weight.  An empty graph
    returns ``{}``.
    """
    if graph.number_of_nodes() == 0:
        return {}

    # Work only on file-path nodes; exclude fn:/mod:/dec:/author: nodes that
    # may be present if this graph was produced by or merged into a KG.
    file_nodes: list[str] = [
        n
        for n in graph.nodes
        if not str(n).startswith(("fn:", "mod:", "dec:", "author:"))
    ]
    if not file_nodes:
        return {}

    sub = graph.subgraph(file_nodes)

    if sub.number_of_edges() == 0:
        weight = 1.0 / len(file_nodes)
        return {n: weight for n in file_nodes}

    try:
        return nx.pagerank(sub, alpha=0.85, max_iter=200)
    except nx.PowerIterationFailedConvergence:
        logger.warning("PageRank did not converge; returning uniform scores")
        weight = 1.0 / len(file_nodes)
        return {n: weight for n in file_nodes}


def merge_into_knowledge_graph(
    dep_graph: nx.DiGraph,
    knowledge_graph: Any,  # server.services.knowledge_graph.KnowledgeGraph
) -> None:
    """
    Merge import edges from *dep_graph* into *knowledge_graph*.

    For edges already present as "imports" in the knowledge graph the
    ``import_type`` and ``line_number`` metadata are added or updated.
    For file pairs not yet connected, new "imports" edges are inserted.

    Both graphs must use project-relative path strings as file node IDs.
    This function accesses ``knowledge_graph._graph`` directly; the
    KnowledgeGraph must not be rebuilt concurrently.
    """
    kg: nx.DiGraph = knowledge_graph._graph

    updates = inserts = 0

    for src, dst, data in dep_graph.edges(data=True):
        # Ensure both endpoints exist as file nodes in the KG.
        for node_id in (src, dst):
            if node_id not in kg:
                kg.add_node(node_id, type="file", path=node_id)

        imp_type = data.get("import_type", "direct")
        line_num = data.get("line_number", 0)

        if kg.has_edge(src, dst):
            kg[src][dst].update(
                type="imports",
                import_type=imp_type,
                line_number=line_num,
            )
            updates += 1
        else:
            kg.add_edge(
                src,
                dst,
                type="imports",
                import_type=imp_type,
                line_number=line_num,
            )
            inserts += 1

    logger.info(
        "Merged dependency graph into KnowledgeGraph: %d updated, %d inserted import edges",
        updates,
        inserts,
    )


# ── Private helpers ───────────────────────────────────────────────────────────


def _collect_files(root: Path) -> list[Path]:
    """Walk *root* and return all supported source files, skipping noise dirs."""
    results: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")
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


def _resolve_import(
    raw: str,
    current_rel: str,
    known_files: dict[str, Path],
) -> str | None:
    """Resolve *raw* import specifier to a project-relative path, or None."""
    if raw.startswith("."):
        return _resolve_relative(raw, current_rel, known_files)
    return _resolve_python_absolute(raw, known_files)


def _resolve_relative(
    raw: str,
    current_rel: str,
    known_files: dict[str, Path],
) -> str | None:
    """Resolve a relative specifier (leading dots) against the current file's dir."""
    current_dir = Path(current_rel).parent

    stripped = raw.lstrip(".")
    level = len(raw) - len(stripped)

    if level > 0 and not stripped.startswith("/"):
        # Climb up (level - 1) directories from the file's parent.
        base = current_dir
        for _ in range(level - 1):
            base = base.parent
        candidate_base = base / stripped.replace(".", "/") if stripped else base
    else:
        candidate_base = current_dir / raw

    candidate_str = str(candidate_base)

    # Try exact match + common extensions.
    for ext in ("", ".py", ".ts", ".tsx", ".js", ".jsx"):
        probe = (candidate_str + ext).replace("\\", "/").lstrip("/")
        if probe in known_files:
            return probe

    # Try package/directory index files.
    for index in ("index.ts", "index.tsx", "index.js", "__init__.py"):
        probe = str(candidate_base / index).replace("\\", "/").lstrip("/")
        if probe in known_files:
            return probe

    return None


def _resolve_python_absolute(
    raw: str,
    known_files: dict[str, Path],
) -> str | None:
    """Try to resolve a Python absolute import (dotted path) to a project file."""
    # Direct module file: foo.bar → foo/bar.py
    as_path = raw.replace(".", "/") + ".py"
    if as_path in known_files:
        return as_path

    # Package __init__: foo.bar → foo/bar/__init__.py
    pkg_path = raw.replace(".", "/") + "/__init__.py"
    if pkg_path in known_files:
        return pkg_path

    # Fuzzy suffix match: any file whose stem-parts end with the import parts.
    parts = raw.split(".")
    for rel in known_files:
        rel_parts = list(Path(rel).with_suffix("").parts)
        if rel_parts[-len(parts) :] == parts:
            return rel

    return None


def _ts_walk_imports(node: Any, results: list[ImportRecord]) -> None:
    """
    Recursively walk a tree-sitter AST node, appending ImportRecord objects
    for every ``import_statement`` and ``import_from_statement`` encountered.

    Recursion stops at import nodes themselves (we don't need their children
    beyond what we explicitly read).
    """
    ntype: str = node.type

    if ntype == "import_statement":
        # Handles: import foo.bar  /  import foo.bar as baz  /  import a, b
        line = node.start_point[0] + 1
        for child in node.children:
            if child.type == "dotted_name":
                results.append(
                    ImportRecord(
                        raw_specifier=child.text.decode("utf-8", errors="replace"),
                        import_type="absolute",
                        line_number=line,
                    )
                )
            elif child.type == "aliased_import":
                # import foo.bar as baz — extract the original dotted_name
                for sub in child.children:
                    if sub.type == "dotted_name":
                        results.append(
                            ImportRecord(
                                raw_specifier=sub.text.decode(
                                    "utf-8", errors="replace"
                                ),
                                import_type="absolute",
                                line_number=line,
                            )
                        )
                        break
        return  # Don't recurse into import_statement children

    if ntype == "import_from_statement":
        # Handles: from foo.bar import x  /  from . import y  /  from ..pkg import z
        line = node.start_point[0] + 1
        module_node = node.child_by_field_name("module_name")
        if module_node is not None:
            raw = module_node.text.decode("utf-8", errors="replace").strip()
            if raw:
                imp_type = "relative" if raw.startswith(".") else "absolute"
                results.append(
                    ImportRecord(
                        raw_specifier=raw,
                        import_type=imp_type,
                        line_number=line,
                    )
                )
        return  # Don't recurse into import_from_statement children

    # For all other node types, recurse into children.
    for child in node.children:
        _ts_walk_imports(child, results)


# ═════════════════════════════════════════════════════════════════════════════
# Blast Radius Calculator
# ═════════════════════════════════════════════════════════════════════════════

_HIGH_RISK: float = 0.7
_MEDIUM_RISK: float = 0.3
_MAX_CHURN_COMMITS: float = 20.0  # commits/30 days that represents "maximum" churn


@dataclass
class AffectedFile:
    """A single file in the blast radius of a change."""

    file_path: str
    risk_score: float
    distance: int
    reason: str


@dataclass
class BlastRadiusReport:
    """Full blast-radius report for a changed file."""

    changed_file: str
    total_affected: int
    high_risk: list[AffectedFile]    # risk_score ≥ 0.7
    medium_risk: list[AffectedFile]  # 0.3 ≤ risk_score < 0.7
    low_risk: list[AffectedFile]     # risk_score < 0.3
    affected_modules: list[str]
    suggested_reviewers: list[str]


class BlastRadiusCalculator:
    """
    Calculates the blast radius of a proposed change to a single file.

    Algorithm
    ---------
    1. Extract the import-only sub-graph from *graph* (only "imports" edges
       between file nodes).
    2. Reverse it — edges now point from imported → importer, so BFS from
       `changed_file` yields every file that (transitively) depends on it.
    3. For each reachable file compute:

           risk = (1 / distance) * norm_centrality * churn_factor

       where
         • norm_centrality = PageRank of the file / max PageRank in graph
                             (normalised to [0, 1])
         • churn_factor    = min(commits_in_last_30d / 20, 1.0)
                             defaults to 1.0 when git is unavailable
    4. Bucket files into high (≥0.7) / medium (0.3–0.7) / low (<0.3) risk.
    5. Pull suggested reviewers from the knowledge graph's expertise edges.
    """

    def calculate_blast_radius(
        self,
        changed_file: str,
        graph: nx.DiGraph,
        git_service: Any | None = None,
        knowledge_graph: Any | None = None,
        depth: int = 4,
    ) -> BlastRadiusReport:
        # ── Build a clean file-only import sub-graph ──────────────────────
        file_nodes: set[str] = {
            n for n in graph.nodes
            if not str(n).startswith(("fn:", "mod:", "dec:", "author:"))
        }
        imp_graph: nx.DiGraph = nx.DiGraph()
        imp_graph.add_nodes_from(file_nodes)
        for u, v, d in graph.edges(data=True):
            if d.get("type") == "imports" and u in file_nodes and v in file_nodes:
                imp_graph.add_edge(u, v)

        empty = BlastRadiusReport(
            changed_file=changed_file,
            total_affected=0,
            high_risk=[],
            medium_risk=[],
            low_risk=[],
            affected_modules=[],
            suggested_reviewers=[],
        )

        if changed_file not in imp_graph:
            return empty

        # ── Centrality over the import graph ──────────────────────────────
        centrality = calculate_centrality(imp_graph)
        max_c = max(centrality.values(), default=1.0) or 1.0

        # ── BFS on reversed graph ─────────────────────────────────────────
        rev = imp_graph.reverse(copy=False)
        affected_nodes: set[str] = set(
            nx.bfs_tree(rev, changed_file, depth_limit=depth).nodes
        )
        affected_nodes.discard(changed_file)

        if not affected_nodes:
            return empty

        # ── Churn data from git (best-effort per file) ────────────────────
        churn_map: dict[str, int] = {}
        if git_service is not None:
            cutoff = datetime.now(tz=timezone.utc) - timedelta(days=30)
            for node in affected_nodes:
                try:
                    history = git_service.get_file_history(node, limit=100)
                    churn_map[node] = sum(
                        1 for c in history
                        if _commit_date(c) >= cutoff
                    )
                except Exception:
                    churn_map[node] = 0

        # ── Score every affected file ─────────────────────────────────────
        scored: list[AffectedFile] = []
        for node in affected_nodes:
            try:
                distance = nx.shortest_path_length(rev, changed_file, node)
            except nx.NetworkXNoPath:
                distance = depth

            norm_c = centrality.get(node, 0.0) / max_c

            if git_service is not None:
                churn_factor = min(
                    churn_map.get(node, 0) / _MAX_CHURN_COMMITS, 1.0
                )
            else:
                churn_factor = 1.0  # neutral when git is unavailable

            risk = (1.0 / distance) * norm_c * churn_factor

            scored.append(
                AffectedFile(
                    file_path=node,
                    risk_score=round(risk, 4),
                    distance=distance,
                    reason=_format_reason(distance, norm_c, churn_factor, git_service),
                )
            )

        scored.sort(key=lambda x: (-x.risk_score, x.file_path))

        high_risk   = [f for f in scored if f.risk_score >= _HIGH_RISK]
        medium_risk = [f for f in scored if _MEDIUM_RISK <= f.risk_score < _HIGH_RISK]
        low_risk    = [f for f in scored if f.risk_score < _MEDIUM_RISK]

        # ── Affected modules ──────────────────────────────────────────────
        modules: set[str] = set()
        for af in scored:
            parent = str(Path(af.file_path).parent)
            if parent not in (".", ""):
                modules.add(parent)

        # ── Suggested reviewers from knowledge graph ──────────────────────
        reviewers: list[str] = []
        if knowledge_graph is not None:
            seen: set[str] = set()
            # Prioritise owners of highest-risk files
            for af in (high_risk + medium_risk + scored)[:20]:
                try:
                    for expert in knowledge_graph.get_expertise_for_file(
                        af.file_path
                    ):
                        name: str = expert.get("name", "")
                        if name and name not in seen:
                            seen.add(name)
                            reviewers.append(name)
                except Exception:
                    pass

        return BlastRadiusReport(
            changed_file=changed_file,
            total_affected=len(scored),
            high_risk=high_risk,
            medium_risk=medium_risk,
            low_risk=low_risk,
            affected_modules=sorted(modules),
            suggested_reviewers=reviewers[:10],
        )


def _commit_date(commit: Any) -> datetime:
    """Extract a timezone-aware datetime from a CommitInfo or plain dict."""
    d = commit.date if hasattr(commit, "date") else commit.get("date")
    if isinstance(d, datetime):
        if d.tzinfo is None:
            return d.replace(tzinfo=timezone.utc)
        return d
    return datetime.min.replace(tzinfo=timezone.utc)


def _format_reason(
    distance: int,
    norm_c: float,
    churn_factor: float,
    git_service: Any | None,
) -> str:
    parts: list[str] = []
    parts.append("direct importer" if distance == 1 else f"{distance} hops away")
    if norm_c >= 0.7:
        parts.append("high centrality")
    elif norm_c >= 0.3:
        parts.append("moderate centrality")
    if git_service is not None:
        if churn_factor >= 0.7:
            parts.append("high recent churn")
        elif churn_factor >= 0.3:
            parts.append("moderate recent churn")
    return "; ".join(parts)


# ═════════════════════════════════════════════════════════════════════════════
# Breaking-Change Detector
# ═════════════════════════════════════════════════════════════════════════════


@dataclass
class BreakingChange:
    """A single detected API-level breaking change between two file versions."""

    symbol: str                   # function / method name (qualified for methods)
    change_type: str              # see _CHANGE_TYPES below
    severity: str                 # "breaking" | "non-breaking"
    old_signature: str | None
    new_signature: str | None
    description: str


_BREAKING_CHANGE_TYPES: frozenset[str] = frozenset(
    {
        "removed_function",
        "added_required_param",
        "removed_param",
        "changed_return_type",
    }
)

# JS/TS function-signature patterns used for diff comparison
_JS_FUNC_SIG_RE = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)"
    r"(?:\s*:\s*([\w<>\[\]|&., ]+))?",
    re.MULTILINE,
)
_JS_ARROW_SIG_RE = re.compile(
    r"(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?"
    r"(?:\(([^)]*)\)|(\w+))\s*=>"
    r"(?:\s*:\s*([\w<>\[\]|&., ]+))?",
    re.MULTILINE,
)


def detect_breaking_changes(
    old_content: str,
    new_content: str,
    language: str,
) -> list[BreakingChange]:
    """
    Compare two versions of a source file and return breaking / non-breaking
    API changes found at the function / method level.

    Uses AST parsing for Python and regex for JavaScript / TypeScript.
    Never calls the LLM — fully deterministic.

    Args:
        old_content: Source code of the original version.
        new_content: Source code of the modified version.
        language:    One of "python", "javascript", "typescript" (or short forms).

    Returns:
        List of BreakingChange objects, empty if none detected.
    """
    lang = language.lower().strip()
    if lang in ("python", "py"):
        return _detect_breaking_python(old_content, new_content)
    if lang in ("javascript", "js", "typescript", "ts", "jsx", "tsx"):
        return _detect_breaking_js(old_content, new_content)
    return []


# ── Python ────────────────────────────────────────────────────────────────────


@dataclass
class _PyFuncSig:
    name: str
    qualified: str           # "ClassName.method" or "function"
    required: list[str]      # param names without defaults
    all_params: list[str]    # all param names (excl. self/cls)
    has_varargs: bool
    has_kwargs: bool
    return_ann: str          # "" if absent
    sig_str: str             # human-readable signature string


def _extract_py_signatures(content: str) -> dict[str, _PyFuncSig]:
    """
    Extract all top-level functions and class methods from Python source.

    Returns a dict keyed by qualified name ("ClassName.method" or "func").
    """
    try:
        tree = stdlib_ast.parse(content)
    except SyntaxError:
        return {}

    sigs: dict[str, _PyFuncSig] = {}

    def _process_func(
        node: stdlib_ast.FunctionDef | stdlib_ast.AsyncFunctionDef,
        class_name: str | None,
    ) -> None:
        args = node.args
        all_arg_nodes = args.args
        # Drop self / cls for methods
        if class_name and all_arg_nodes and all_arg_nodes[0].arg in ("self", "cls"):
            all_arg_nodes = all_arg_nodes[1:]

        n_defaults = len(args.defaults)
        n_total = len(all_arg_nodes)
        n_required = n_total - n_defaults

        required = [a.arg for a in all_arg_nodes[:n_required]]
        all_p = [a.arg for a in all_arg_nodes]

        # Return annotation
        ret = ""
        if node.returns:
            try:
                ret = stdlib_ast.unparse(node.returns)
            except Exception:
                ret = ""

        # Human-readable signature
        parts: list[str] = []
        for i, arg in enumerate(all_arg_nodes):
            part = arg.arg
            if arg.annotation:
                try:
                    part += f": {stdlib_ast.unparse(arg.annotation)}"
                except Exception:
                    pass
            if i >= n_required:
                part += "=…"
            parts.append(part)
        if args.vararg:
            parts.append(f"*{args.vararg.arg}")
        if args.kwarg:
            parts.append(f"**{args.kwarg.arg}")

        qualified = f"{class_name}.{node.name}" if class_name else node.name
        sig_str = f"{qualified}({', '.join(parts)})"
        if ret:
            sig_str += f" -> {ret}"

        sigs[qualified] = _PyFuncSig(
            name=node.name,
            qualified=qualified,
            required=required,
            all_params=all_p,
            has_varargs=args.vararg is not None,
            has_kwargs=args.kwarg is not None,
            return_ann=ret,
            sig_str=sig_str,
        )

    for node in stdlib_ast.iter_child_nodes(tree):
        if isinstance(node, (stdlib_ast.FunctionDef, stdlib_ast.AsyncFunctionDef)):
            _process_func(node, None)
        elif isinstance(node, stdlib_ast.ClassDef):
            for child in stdlib_ast.iter_child_nodes(node):
                if isinstance(
                    child, (stdlib_ast.FunctionDef, stdlib_ast.AsyncFunctionDef)
                ):
                    _process_func(child, node.name)

    return sigs


def _detect_breaking_python(
    old_content: str, new_content: str
) -> list[BreakingChange]:
    old_sigs = _extract_py_signatures(old_content)
    new_sigs = _extract_py_signatures(new_content)
    changes: list[BreakingChange] = []

    for qualified, old_f in old_sigs.items():
        if qualified not in new_sigs:
            changes.append(
                BreakingChange(
                    symbol=qualified,
                    change_type="removed_function",
                    severity="breaking",
                    old_signature=old_f.sig_str,
                    new_signature=None,
                    description=f"`{qualified}` was removed.",
                )
            )
            continue

        new_f = new_sigs[qualified]

        # Added required parameters
        new_required_set = set(new_f.required)
        old_required_set = set(old_f.required)
        added_required = sorted(new_required_set - old_required_set)
        if added_required and not new_f.has_varargs:
            changes.append(
                BreakingChange(
                    symbol=qualified,
                    change_type="added_required_param",
                    severity="breaking",
                    old_signature=old_f.sig_str,
                    new_signature=new_f.sig_str,
                    description=(
                        f"`{qualified}` gained required parameter(s): "
                        + ", ".join(f"`{p}`" for p in added_required)
                        + "."
                    ),
                )
            )

        # Removed parameters (positional callers break)
        old_param_set = set(old_f.all_params)
        new_param_set = set(new_f.all_params)
        removed_params = sorted(old_param_set - new_param_set)
        if removed_params and not old_f.has_varargs:
            changes.append(
                BreakingChange(
                    symbol=qualified,
                    change_type="removed_param",
                    severity="breaking",
                    old_signature=old_f.sig_str,
                    new_signature=new_f.sig_str,
                    description=(
                        f"`{qualified}` removed parameter(s): "
                        + ", ".join(f"`{p}`" for p in removed_params)
                        + "."
                    ),
                )
            )

        # Changed return type annotation (only when both sides have one)
        if (
            old_f.return_ann
            and new_f.return_ann
            and old_f.return_ann != new_f.return_ann
        ):
            changes.append(
                BreakingChange(
                    symbol=qualified,
                    change_type="changed_return_type",
                    severity="breaking",
                    old_signature=old_f.sig_str,
                    new_signature=new_f.sig_str,
                    description=(
                        f"`{qualified}` return type changed from "
                        f"`{old_f.return_ann}` to `{new_f.return_ann}`."
                    ),
                )
            )

    # Added functions — non-breaking (informational)
    for qualified, new_f in new_sigs.items():
        if qualified not in old_sigs:
            changes.append(
                BreakingChange(
                    symbol=qualified,
                    change_type="added_function",
                    severity="non-breaking",
                    old_signature=None,
                    new_signature=new_f.sig_str,
                    description=f"`{qualified}` was added.",
                )
            )

    return changes


# ── JavaScript / TypeScript ───────────────────────────────────────────────────


@dataclass
class _JsFuncSig:
    name: str
    params: list[str]    # raw parameter tokens
    required: list[str]  # params without a default value
    return_type: str     # "" if absent
    sig_str: str


def _parse_js_params(raw: str) -> tuple[list[str], list[str]]:
    """
    Parse a raw JS/TS parameter string into (all_params, required_params).

    Handles simple cases: `a, b = 5, c`, rest/spread `...rest`, typed `a: T`.
    Does NOT handle destructuring (`{a, b}`).
    """
    if not raw or not raw.strip():
        return [], []

    all_p: list[str] = []
    required: list[str] = []

    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        # Strip TypeScript type annotation: `a: Type` → `a`
        name_part = token.split(":")[0].strip()
        # Check for default value
        has_default = "=" in name_part or "=" in token
        # Normalise rest params
        name_part = name_part.lstrip(".")  # remove spread `...`
        # Extract identifier
        ident = re.split(r"\s|=", name_part)[0].strip()
        if not ident or ident == "{" or ident == "[":
            # Skip destructured params — too complex to compare
            continue
        all_p.append(ident)
        if not has_default:
            required.append(ident)

    return all_p, required


def _extract_js_signatures(content: str) -> dict[str, _JsFuncSig]:
    sigs: dict[str, _JsFuncSig] = {}

    for pattern in (_JS_FUNC_SIG_RE, _JS_ARROW_SIG_RE):
        for m in pattern.finditer(content):
            name = m.group(1)
            # group(2) = params for function/arrow, group(3) = single bare param
            raw_params = m.group(2) or m.group(3) or ""
            # Return type: last non-None group
            ret = ""
            for g in reversed(m.groups()):
                if g and g != raw_params and g != name:
                    ret = g.strip()
                    break

            all_p, required = _parse_js_params(raw_params)
            sig_str = f"{name}({raw_params.strip()})"
            if ret:
                sig_str += f": {ret}"

            sigs[name] = _JsFuncSig(
                name=name,
                params=all_p,
                required=required,
                return_type=ret,
                sig_str=sig_str,
            )

    return sigs


def _detect_breaking_js(old_content: str, new_content: str) -> list[BreakingChange]:
    old_sigs = _extract_js_signatures(old_content)
    new_sigs = _extract_js_signatures(new_content)
    changes: list[BreakingChange] = []

    for name, old_f in old_sigs.items():
        if name not in new_sigs:
            changes.append(
                BreakingChange(
                    symbol=name,
                    change_type="removed_function",
                    severity="breaking",
                    old_signature=old_f.sig_str,
                    new_signature=None,
                    description=f"`{name}` was removed.",
                )
            )
            continue

        new_f = new_sigs[name]

        added_required = sorted(set(new_f.required) - set(old_f.required))
        if added_required:
            changes.append(
                BreakingChange(
                    symbol=name,
                    change_type="added_required_param",
                    severity="breaking",
                    old_signature=old_f.sig_str,
                    new_signature=new_f.sig_str,
                    description=(
                        f"`{name}` gained required parameter(s): "
                        + ", ".join(f"`{p}`" for p in added_required)
                        + "."
                    ),
                )
            )

        removed_params = sorted(set(old_f.params) - set(new_f.params))
        if removed_params:
            changes.append(
                BreakingChange(
                    symbol=name,
                    change_type="removed_param",
                    severity="breaking",
                    old_signature=old_f.sig_str,
                    new_signature=new_f.sig_str,
                    description=(
                        f"`{name}` removed parameter(s): "
                        + ", ".join(f"`{p}`" for p in removed_params)
                        + "."
                    ),
                )
            )

        if (
            old_f.return_type
            and new_f.return_type
            and old_f.return_type != new_f.return_type
        ):
            changes.append(
                BreakingChange(
                    symbol=name,
                    change_type="changed_return_type",
                    severity="breaking",
                    old_signature=old_f.sig_str,
                    new_signature=new_f.sig_str,
                    description=(
                        f"`{name}` return type changed from "
                        f"`{old_f.return_type}` to `{new_f.return_type}`."
                    ),
                )
            )

    for name, new_f in new_sigs.items():
        if name not in old_sigs:
            changes.append(
                BreakingChange(
                    symbol=name,
                    change_type="added_function",
                    severity="non-breaking",
                    old_signature=None,
                    new_signature=new_f.sig_str,
                    description=f"`{name}` was added.",
                )
            )

    return changes
