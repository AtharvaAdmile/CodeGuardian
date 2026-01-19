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
    and its inheritance relationships. Useful for understanding code coupling
    and refactoring impact.
    
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
            signature="",
            implementation=content,
            language=language,
            docstring=None
        )
        
        analyzer = DependencyAnalyzer()
        dependencies = analyzer.analyze_dependencies(element, [])
        
        # Group dependencies by type
        imports = [d.target_name for d in dependencies if d.dependency_type.value == "import"]
        function_calls = [d.target_name for d in dependencies if d.dependency_type.value == "call"]
        inheritance = [d.target_name for d in dependencies if d.dependency_type.value == "inheritance"]
        
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
                signature=func.signature or "",
                implementation=func.content,
                language=language,
                docstring=func.docstring
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
                signature=cls.signature or "",
                implementation=cls.content,
                language=language,
                docstring=cls.docstring
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
