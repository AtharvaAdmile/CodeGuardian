"""
CodeGuardian MCP Server - Context Engine for GitHub Copilot.

This module implements an MCP (Model Context Protocol) server that exposes
CodeGuardian's code analysis capabilities as tools for AI assistants like
GitHub Copilot. The server runs locally and requires no external API keys.

Tools provided:
- query_codebase: Semantic search over indexed codebase
- analyze_structure: Project structure and complexity analysis
- find_dependencies: Import and call-graph analysis
- analyze_testability: Identify testable code elements with context
- run_tests: Execute pytest and return results
- detect_documentation_gaps: Find undocumented code elements
- get_file_history: Git history and blame for specific lines
- get_file_expert: Find code owners with expertise scores
- check_compliance: Scan code for PII/secrets violations
- get_file_health: Tech debt score using complexity + churn
- get_runtime_stats: Production telemetry for a file
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from mcp.server.fastmcp import FastMCP

# Local imports
from src.embedding_generator import EmbeddingGenerator
from src.vector_store import VectorStore
from src.query_engine import QueryEngine, CodeChunk
from src.structure_analyzer import StructureAnalyzer
from src.code_parser import CodeParser
from src.documentation.dependency_analyzer import DependencyAnalyzer
from src.documentation.gap_detector import GapDetector
from src.testing.test_analyzer import TestAnalyzer
from src.testing.test_runner import TestRunner
from src.models.documentation_models import CodeElement

# Advanced Context Analyzers
from src.analysis.git_context import GitContextAnalyzer
from src.analysis.expertise import ExpertiseTracker
from src.analysis.compliance import ComplianceScanner
from src.analysis.runtime import RuntimeLoader

logger = logging.getLogger(__name__)

# Initialize the MCP server
mcp = FastMCP(
    name="CodeGuardian",
    instructions="Local-first code analysis and context retrieval for AI assistants. Use these tools to search code, analyze dependencies, and understand project structure."
)

# Lazy-loaded singleton instances
_embedding_generator: Optional[EmbeddingGenerator] = None
_vector_store: Optional[VectorStore] = None
_query_engine: Optional[QueryEngine] = None


def _get_project_root() -> Path:
    """Get the project root from .codeguardian file or current directory."""
    cwd = Path.cwd()
    
    # Look for .codeguardian marker file
    codeguardian_file = cwd / ".codeguardian"
    if codeguardian_file.exists():
        try:
            with open(codeguardian_file, 'r') as f:
                config = json.load(f) if codeguardian_file.suffix == '.json' else {}
                if 'project_root' in config:
                    return Path(config['project_root'])
        except Exception:
            pass
    
    return cwd


def _get_chroma_path() -> str:
    """Get the ChromaDB storage path."""
    project_root = _get_project_root()
    return str(project_root / "chroma_data")


def _get_embedding_generator() -> EmbeddingGenerator:
    """Get or create the embedding generator singleton."""
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = EmbeddingGenerator()
    return _embedding_generator


def _get_vector_store() -> VectorStore:
    """Get or create the vector store singleton."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStore(persist_directory=_get_chroma_path())
    return _vector_store


def _get_query_engine() -> QueryEngine:
    """Get or create the query engine singleton."""
    global _query_engine
    if _query_engine is None:
        _query_engine = QueryEngine(
            embedding_generator=_get_embedding_generator(),
            vector_store=_get_vector_store(),
            collection_name="codeguardian"
        )
    return _query_engine


def _chunk_to_dict(chunk: CodeChunk) -> Dict[str, Any]:
    """Convert a CodeChunk to a serializable dictionary."""
    return {
        "id": chunk.id,
        "content": chunk.content,
        "file_path": chunk.file_path,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "chunk_type": chunk.chunk_type,
        "language": chunk.language,
        "distance": chunk.distance,
        "metadata": chunk.metadata
    }


# =============================================================================
# MCP TOOLS
# =============================================================================

@mcp.tool()
def query_codebase(query: str, n_results: int = 5) -> Dict[str, Any]:
    """
    Search the indexed codebase using semantic similarity (RAG).
    
    Use this tool to find relevant code snippets based on a natural language query.
    Returns the most similar code chunks from the vector store.
    
    Args:
        query: Natural language search query (e.g., "authentication logic", "database connection")
        n_results: Number of results to return (default: 5, max: 20)
    
    Returns:
        Dictionary containing:
        - chunks: List of relevant code snippets with file paths and line numbers
        - query_time_ms: Time taken to execute the query
        - total_results: Number of results returned
    """
    if not query or not query.strip():
        return {"error": "Query cannot be empty", "chunks": [], "total_results": 0}
    
    n_results = min(max(1, n_results), 20)  # Clamp between 1 and 20
    
    try:
        query_engine = _get_query_engine()
        
        # Generate embedding for the query
        query_embedding = _get_embedding_generator().generate_embedding(query)
        
        # Retrieve similar chunks
        chunks = query_engine.retrieve_chunks(query_embedding, n_results=n_results)
        
        # Rerank for better relevance
        if chunks:
            chunks = query_engine.rerank_results(chunks, query)
        
        return {
            "chunks": [_chunk_to_dict(c) for c in chunks],
            "total_results": len(chunks),
            "query": query
        }
    except Exception as e:
        logger.error(f"Error querying codebase: {e}")
        return {"error": str(e), "chunks": [], "total_results": 0}


@mcp.tool()
def analyze_structure(project_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyze the project structure, complexity, and git status.
    
    Use this tool to understand the overall organization of a codebase,
    including file distribution, directory structure, and version control status.
    
    Args:
        project_path: Path to the project root (defaults to current directory)
    
    Returns:
        Dictionary containing:
        - score: Organization score (0-10)
        - has_git: Whether the project is under git version control
        - total_files: Total number of files
        - root_files: Number of files in root directory
        - folders_count: Number of folders with files
    """
    path = project_path or str(_get_project_root())
    
    try:
        analyzer = StructureAnalyzer(path)
        result = analyzer.analyze_structure()
        result["project_path"] = path
        return result
    except Exception as e:
        logger.error(f"Error analyzing structure: {e}")
        return {"error": str(e), "project_path": path}


@mcp.tool()
def find_dependencies(file_path: str) -> Dict[str, Any]:
    """
    Analyze dependencies and relationships for a specific file.
    
    Use this tool to understand what a file imports, what functions it calls,
    and its inheritance relationships. Useful for creating dependency graphs.
    
    Args:
        file_path: Absolute or relative path to the file to analyze
    
    Returns:
        Dictionary containing:
        - imports: List of imported modules/functions
        - function_calls: List of functions called within the file
        - inheritance: Class inheritance relationships (for class files)
        - file_path: The analyzed file path
    """
    # Resolve path
    path = Path(file_path)
    if not path.is_absolute():
        path = _get_project_root() / path
    
    if not path.exists():
        return {"error": f"File not found: {file_path}", "file_path": str(path)}
    
    if not path.is_file():
        return {"error": f"Path is not a file: {file_path}", "file_path": str(path)}
    
    try:
        # Read file content
        content = path.read_text(encoding='utf-8')
        
        # Determine language from extension
        ext = path.suffix.lower()
        language = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.jsx': 'javascript',
            '.tsx': 'typescript'
        }.get(ext, 'unknown')
        
        # Create a CodeElement for analysis
        element = CodeElement(
            element_id=str(path),
            element_type="file",
            name=path.name,
            file_path=str(path),
            start_line=1,
            end_line=len(content.splitlines()),
            language=language,
            code_content=content,
            existing_doc=None
        )
        
        analyzer = DependencyAnalyzer()
        dependencies = analyzer.analyze_dependencies(element, [])
        
        # Group dependencies by type (dependency_type is already a string, not an enum)
        imports = [d.name for d in dependencies if d.dependency_type == "import"]
        function_calls = [d.name for d in dependencies if d.dependency_type == "function_call"]
        inheritance = [d.name for d in dependencies if d.dependency_type == "inheritance"]
        
        return {
            "file_path": str(path),
            "language": language,
            "imports": imports,
            "function_calls": function_calls,
            "inheritance": inheritance,
            "total_dependencies": len(dependencies)
        }
    except Exception as e:
        logger.error(f"Error analyzing dependencies: {e}")
        return {"error": str(e), "file_path": str(path)}


@mcp.tool()
def analyze_project_dependencies(project_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyze dependencies for the entire project to build a dependency graph.
    
    Use this tool to get a full graph of all files and their relationships.
    More efficient than calling find_dependencies on every file.
    
    Args:
        project_path: Path to the project root (defaults to current directory)
    
    Returns:
        Dictionary containing:
        - nodes: List of files (id, name, type, language)
        - links: List of dependencies (source, target, type)
    """
    root_path = Path(project_path) if project_path else _get_project_root()
    
    if not root_path.exists():
        return {"error": f"Path not found: {root_path}", "nodes": [], "links": []}
    
    nodes = []
    links = []
    node_ids = set()  # Track node IDs for link validation
    
    try:
        # 1. Collect all valid files
        analyzer = DependencyAnalyzer()
        valid_extensions = {'.py', '.js', '.ts', '.jsx', '.tsx'}
        
        # Walk through directory
        for root, dirs, files in os.walk(root_path):
            # Skip hidden and ignored dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in {'node_modules', 'venv', '__pycache__', 'dist', 'build', 'chroma_data'}]
            
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() not in valid_extensions:
                    continue
                    
                # Use relative path as ID (much shorter)
                rel_path = str(file_path.relative_to(root_path))
                
                nodes.append({
                    "id": rel_path,
                    "name": file,
                    "group": file_path.suffix.lower().replace('.', '')
                })
                
                node_ids.add(rel_path)
        
        # 2. Analyze dependencies for each file (simplified - only imports)
        for node in nodes:
            file_path = root_path / node["id"]
            try:
                content = file_path.read_text(encoding='utf-8')
                language = {
                    '.py': 'python',
                    '.js': 'javascript',
                    '.ts': 'typescript',
                    '.jsx': 'javascript',
                    '.tsx': 'typescript'
                }.get(file_path.suffix.lower(), 'unknown')
                
                element = CodeElement(
                    element_id=node["id"],
                    element_type="file",
                    name=node["name"],
                    file_path=str(file_path),
                    start_line=1,
                    end_line=100,
                    language=language,
                    code_content=content,
                    existing_doc=None
                )
                
                deps = analyzer.analyze_dependencies(element, [])
                
                for dep in deps:
                    if dep.dependency_type == "import":
                        target_name = dep.name
                        
                        # Find potential matches in our nodes
                        for potential_node in nodes:
                            potential_id = potential_node["id"]
                            potential_name = potential_node["name"].split('.')[0]
                            
                            # Match import name to file
                            if target_name == potential_name or target_name.replace('.', '/') in potential_id:
                                # Avoid self-links and duplicates
                                if node["id"] != potential_id:
                                    link_key = f"{node['id']}:{potential_id}"
                                    links.append({
                                        "source": node["id"],
                                        "target": potential_id
                                    })
                                break  # Only one match per import
            except Exception as e:
                logger.warning(f"Failed to analyze file {file_path}: {e}")
                continue
        
        # Deduplicate links
        seen_links = set()
        unique_links = []
        for link in links:
            key = f"{link['source']}:{link['target']}"
            if key not in seen_links:
                seen_links.add(key)
                unique_links.append(link)
                
        return {
            "nodes": nodes,
            "links": unique_links,
            "total_files": len(nodes),
            "total_links": len(unique_links)
        }
            
    except Exception as e:
        logger.error(f"Error analyzing project dependencies: {e}")
        return {"error": str(e), "nodes": [], "links": []}


@mcp.tool()
def analyze_testability(file_path: str) -> Dict[str, Any]:
    """
    Analyze a file to identify testable elements and their context.
    
    Use this tool to find functions and classes that can be tested,
    along with their complexity scores and relevant context from the codebase.
    This provides the information needed for an AI to generate test cases.
    
    Args:
        file_path: Path to the file to analyze
    
    Returns:
        Dictionary containing:
        - testable_elements: List of functions/classes that can be tested
        - context_chunks: Related code from the codebase for test generation
        - file_path: The analyzed file path
    """
    # Resolve path
    path = Path(file_path)
    if not path.is_absolute():
        path = _get_project_root() / path
    
    if not path.exists():
        return {"error": f"File not found: {file_path}", "file_path": str(path)}
    
    try:
        content = path.read_text(encoding='utf-8')
        
        # Analyze testable elements
        test_analyzer = TestAnalyzer()
        testable_elements = test_analyzer.analyze_file(str(path), content)
        
        # Get context for each testable element from RAG
        elements_with_context = []
        query_engine = _get_query_engine()
        embedding_generator = _get_embedding_generator()
        
        for element in testable_elements:
            # Query for related code (usages, dependencies)
            query_text = f"usage of {element.name} function in {path.name}"
            try:
                embedding = embedding_generator.generate_embedding(query_text)
                context_chunks = query_engine.retrieve_chunks(embedding, n_results=3)
                context = [_chunk_to_dict(c) for c in context_chunks]
            except Exception:
                context = []
            
            elements_with_context.append({
                "element_id": element.element_id,
                "name": element.name,
                "element_type": element.element_type,
                "file_path": element.file_path,
                "start_line": element.start_line,
                "end_line": element.end_line,
                "content": element.content,
                "complexity_score": element.complexity_score,
                "context_chunks": context
            })
        
        return {
            "file_path": str(path),
            "testable_elements": elements_with_context,
            "total_elements": len(elements_with_context)
        }
    except Exception as e:
        logger.error(f"Error analyzing testability: {e}")
        return {"error": str(e), "file_path": str(path)}


@mcp.tool()
def run_tests(file_path: Optional[str] = None, test_dir: str = "tests") -> Dict[str, Any]:
    """
    Execute pytest and return the results.
    
    Use this tool to run tests and get detailed output about pass/fail status.
    Can run a specific test file or all tests in a directory.
    
    Args:
        file_path: Specific test file to run (optional)
        test_dir: Directory containing tests (default: "tests")
    
    Returns:
        Dictionary containing:
        - passed: Overall pass/fail status
        - results: Detailed test results per file
        - output: Raw pytest output
    """
    runner = TestRunner()
    
    try:
        if file_path:
            # Resolve path
            path = Path(file_path)
            if not path.is_absolute():
                path = _get_project_root() / path
            
            result = runner.run_file(str(path))
            return {
                "passed": result.passed,
                "file_path": result.file_path,
                "output": result.output,
                "error_message": result.error_message,
                "results": {str(path): {
                    "passed": result.passed,
                    "output": result.output
                }}
            }
        else:
            # Run all tests in directory
            test_path = _get_project_root() / test_dir
            results = runner.run_all(str(test_path))
            
            all_passed = all(r.passed for r in results.values()) if results else True
            
            return {
                "passed": all_passed,
                "test_dir": str(test_path),
                "total_files": len(results),
                "passed_files": sum(1 for r in results.values() if r.passed),
                "failed_files": sum(1 for r in results.values() if not r.passed),
                "results": {
                    path: {
                        "passed": r.passed,
                        "output": r.output[:500] if r.output else "",  # Truncate long output
                        "error": r.error_message
                    }
                    for path, r in results.items()
                }
            }
    except Exception as e:
        logger.error(f"Error running tests: {e}")
        return {"error": str(e), "passed": False}


@mcp.tool()
def detect_documentation_gaps(file_path: str) -> Dict[str, Any]:
    """
    Analyze a file to find undocumented or poorly documented code elements.
    
    Use this tool to identify functions, classes, and methods that lack
    proper documentation. Returns quality scores and specific gaps.
    
    Args:
        file_path: Path to the file to analyze
    
    Returns:
        Dictionary containing:
        - elements: List of code elements with documentation quality scores
        - gaps: Elements with quality below threshold (need documentation)
        - average_score: Average documentation quality score
    """
    # Resolve path
    path = Path(file_path)
    if not path.is_absolute():
        path = _get_project_root() / path
    
    if not path.exists():
        return {"error": f"File not found: {file_path}", "file_path": str(path)}
    
    try:
        content = path.read_text(encoding='utf-8')
        
        # Parse the file
        parser = CodeParser()
        parsed = parser.parse_file(str(path), content)
        
        # Determine language
        ext = path.suffix.lower()
        language = {'.py': 'python', '.js': 'javascript', '.ts': 'typescript'}.get(ext, 'unknown')
        
        gap_detector = GapDetector(quality_threshold=70.0)
        
        elements = []
        gaps = []
        total_score = 0
        
        # Analyze functions
        for func in parsed.functions:
            element = CodeElement(
                element_id=f"{path}:{func.name}:{func.start_line}",
                element_type="function",
                name=func.name,
                file_path=str(path),
                start_line=func.start_line,
                end_line=func.end_line,
                language=language,
                code_content=func.content,
                existing_doc=func.docstring
            )
            
            score = gap_detector.calculate_quality_score(element)
            has_gap = gap_detector.has_documentation_gap(score)
            
            element_info = {
                "name": func.name,
                "type": "function",
                "start_line": func.start_line,
                "end_line": func.end_line,
                "quality_score": score,
                "has_gap": has_gap,
                "has_docstring": bool(func.docstring)
            }
            
            elements.append(element_info)
            total_score += score
            
            if has_gap:
                gaps.append(element_info)
        
        # Analyze classes
        for cls in parsed.classes:
            element = CodeElement(
                element_id=f"{path}:{cls.name}:{cls.start_line}",
                element_type="class",
                name=cls.name,
                file_path=str(path),
                start_line=cls.start_line,
                end_line=cls.end_line,
                language=language,
                code_content=cls.content,
                existing_doc=cls.docstring
            )
            
            score = gap_detector.calculate_quality_score(element)
            has_gap = gap_detector.has_documentation_gap(score)
            
            element_info = {
                "name": cls.name,
                "type": "class",
                "start_line": cls.start_line,
                "end_line": cls.end_line,
                "quality_score": score,
                "has_gap": has_gap,
                "has_docstring": bool(cls.docstring)
            }
            
            elements.append(element_info)
            total_score += score
            
            if has_gap:
                gaps.append(element_info)
        
        avg_score = total_score / len(elements) if elements else 100.0
        
        return {
            "file_path": str(path),
            "elements": elements,
            "gaps": gaps,
            "total_elements": len(elements),
            "elements_with_gaps": len(gaps),
            "average_score": round(avg_score, 1),
            "quality_threshold": 70.0
        }
    except Exception as e:
        logger.error(f"Error detecting documentation gaps: {e}")
        return {"error": str(e), "file_path": str(path)}


# =============================================================================
# ADVANCED CONTEXT ANALYZER TOOLS
# =============================================================================

@mcp.tool()
def get_file_history(
    file_path: str,
    line_start: Optional[int] = None,
    line_end: Optional[int] = None
) -> Dict[str, Any]:
    """
    Retrieve git commit history for specific lines in a file.
    
    Use this tool to understand WHY certain code exists by looking at
    the commit history. Especially useful for understanding "weird" code
    that might have been added for a specific bug fix.
    
    Args:
        file_path: Path to the file to analyze
        line_start: Starting line number (1-indexed, optional)
        line_end: Ending line number (1-indexed, optional)
    
    Returns:
        Dictionary containing:
        - history: List of commits affecting those lines
        - summary: Human-readable explanation
        - file_path: The analyzed file
    """
    path = Path(file_path)
    if not path.is_absolute():
        path = _get_project_root() / path
    
    if not path.exists():
        return {"error": f"File not found: {file_path}", "file_path": str(path)}
    
    try:
        analyzer = GitContextAnalyzer(str(_get_project_root()))
        result = analyzer.get_history(str(path), line_start, line_end)
        
        # Also get churn info for context
        churn = analyzer.get_churn(str(path))
        result["churn"] = {
            "count": churn.get("churn_count", 0),
            "risk_level": churn.get("risk_level", "unknown")
        }
        
        return result
    except Exception as e:
        logger.error(f"Error getting file history: {e}")
        return {"error": str(e), "file_path": str(path)}


@mcp.tool()
def get_file_expert(file_path: str) -> Dict[str, Any]:
    """
    Find the code experts/owners for a specific file.
    
    Use this tool to identify who understands a piece of code best,
    useful for PR reviews or getting help with unfamiliar code.
    Uses a recency-weighted scoring: recent contributors rank higher.
    
    Args:
        file_path: Path to the file to analyze
    
    Returns:
        Dictionary containing:
        - primary_expert: Top contributor name
        - backup: Second contributor name
        - experts: Full list with scores
        - last_active: When file was last modified
    """
    path = Path(file_path)
    if not path.is_absolute():
        path = _get_project_root() / path
    
    if not path.exists():
        return {"error": f"File not found: {file_path}", "file_path": str(path)}
    
    try:
        tracker = ExpertiseTracker(str(_get_project_root()))
        return tracker.find_owners(str(path))
    except Exception as e:
        logger.error(f"Error finding file expert: {e}")
        return {"error": str(e), "file_path": str(path)}


@mcp.tool()
def check_compliance(code_snippet: str) -> Dict[str, Any]:
    """
    Scan code for potential compliance and security violations.
    
    Use this tool to check code for PII exposure, hardcoded secrets,
    or dangerous function usage before committing. Works on any
    Python code snippet.
    
    Args:
        code_snippet: Python source code to analyze
    
    Returns:
        Dictionary containing:
        - passed: True if no violations found
        - violations: List of issues with line numbers and severity
        - summary: Human-readable summary
    """
    if not code_snippet or not code_snippet.strip():
        return {"error": "Code snippet cannot be empty", "passed": True}
    
    try:
        scanner = ComplianceScanner()
        return scanner.scan_code(code_snippet)
    except Exception as e:
        logger.error(f"Error checking compliance: {e}")
        return {"error": str(e), "passed": False}


@mcp.tool()
def get_file_health(file_path: str) -> Dict[str, Any]:
    """
    Calculate tech debt health score for a file.
    
    Combines cyclomatic complexity (radon) with git churn to identify
    "hotspot" files that are both complex AND frequently edited - 
    prime candidates for refactoring.
    
    Health Score = 100 - (Complexity + Churn)
    
    Args:
        file_path: Path to the file to analyze
    
    Returns:
        Dictionary containing:
        - health_score: 0-100 (higher is better)
        - complexity: Score and rank (A-F)
        - churn: Edit frequency and rank
        - recommendation: Refactoring priority
        - is_hotspot: True if needs immediate attention
    """
    path = Path(file_path)
    if not path.is_absolute():
        path = _get_project_root() / path
    
    if not path.exists():
        return {"error": f"File not found: {file_path}", "file_path": str(path)}
    
    try:
        analyzer = StructureAnalyzer(str(_get_project_root()))
        return analyzer.get_file_health(str(path))
    except Exception as e:
        logger.error(f"Error calculating file health: {e}")
        return {"error": str(e), "file_path": str(path)}


@mcp.tool()
def get_runtime_stats(file_path: str) -> Dict[str, Any]:
    """
    Get production runtime statistics for a file.
    
    Use this tool to check if a file has runtime issues (high error rate,
    high latency) before making changes. Prioritize fixing files with
    production problems.
    
    Note: Requires runtime_stats.json to be populated by your CI/CD pipeline.
    
    Args:
        file_path: Path to the file to check
    
    Returns:
        Dictionary containing:
        - available: Whether runtime data exists
        - error_rate: Error percentage
        - avg_latency_ms: Average response time
        - alert_level: none/warning/critical
        - last_error: Most recent error message
    """
    try:
        loader = RuntimeLoader()
        return loader.get_stats(file_path)
    except Exception as e:
        logger.error(f"Error getting runtime stats: {e}")
        return {"error": str(e), "file_path": file_path, "available": False}


# =============================================================================
# SERVER ENTRY POINT
# =============================================================================

def run_server():
    """
    Start the CodeGuardian MCP server using Stdio transport.
    
    This function is called by the CLI command `cgctl serve`.
    The server communicates over standard input/output for VS Code integration.
    """
    logger.info("Starting CodeGuardian MCP Server...")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    # Allow running directly for testing
    logging.basicConfig(level=logging.INFO)
    run_server()
