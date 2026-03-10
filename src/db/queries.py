"""
SQL query helpers for CodeGuardian.

Provides high-level database operations for projects, files, embeddings, etc.
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
import logging

from src.db.supabase_client import get_supabase_client

logger = logging.getLogger(__name__)


def create_project(
    name: str,
    root_path: str,
    total_files: int = 0,
    total_lines: int = 0
) -> Dict[str, Any]:
    """
    Create a new project record.
    
    Args:
        name: Project name
        root_path: Absolute path to project root
        total_files: Total number of files
        total_lines: Total lines of code
        
    Returns:
        Created project record
    """
    client = get_supabase_client()
    
    return client.insert("projects", {
        "name": name,
        "root_path": root_path,
        "total_files": total_files,
        "total_lines": total_lines,
    })


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a project by ID.
    
    Args:
        project_id: UUID of the project
        
    Returns:
        Project record or None
    """
    client = get_supabase_client()
    return client.select_one("projects", filters={"id": project_id})


def get_project_by_path(root_path: str) -> Optional[Dict[str, Any]]:
    """
    Get a project by its root path.
    
    Args:
        root_path: Absolute path to project root
        
    Returns:
        Project record or None
    """
    client = get_supabase_client()
    return client.select_one("projects", filters={"root_path": root_path})


def update_project_indexed(
    project_id: str,
    total_files: int,
    total_lines: int
) -> Dict[str, Any]:
    """
    Update project after indexing.
    
    Args:
        project_id: UUID of the project
        total_files: Total indexed files
        total_lines: Total lines of code
        
    Returns:
        Updated project record
    """
    client = get_supabase_client()
    
    rows = client.update("projects", {
        "total_files": total_files,
        "total_lines": total_lines,
        "indexed_at": datetime.now().isoformat(),
    }, filters={"id": project_id})
    
    return rows[0] if rows else {}


def insert_file(
    project_id: str,
    path: str,
    language: str,
    content: Optional[str] = None,
    line_count: int = 0,
    git_commit_hash: Optional[str] = None
) -> Dict[str, Any]:
    """
    Insert or update a code file record.
    
    Args:
        project_id: UUID of the project
        path: Relative path within project
        language: Programming language
        content: File content
        line_count: Number of lines
        git_commit_hash: Current git commit
        
    Returns:
        File record
    """
    client = get_supabase_client()
    
    # Check if file exists
    existing = client.select_one("code_files", filters={
        "project_id": project_id,
        "path": path,
    })
    
    data = {
        "project_id": project_id,
        "path": path,
        "language": language,
        "content": content,
        "line_count": line_count,
        "last_modified": datetime.now().isoformat(),
        "git_commit_hash": git_commit_hash,
    }
    
    if existing:
        # Update existing
        rows = client.update("code_files", data, filters={"id": existing["id"]})
        return rows[0] if rows else existing
    else:
        # Insert new
        return client.insert("code_files", data)


def insert_embedding(
    file_id: str,
    chunk_text: str,
    embedding: List[float],
    start_line: int,
    end_line: int,
    metadata: Optional[Dict[str, Any]] = None,
    entity_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Insert an embedding record.
    
    Args:
        file_id: UUID of the code file
        chunk_text: Text content of the chunk
        embedding: Vector embedding (768 dimensions)
        start_line: Starting line number
        end_line: Ending line number
        metadata: Additional metadata
        entity_id: Optional code entity UUID
        
    Returns:
        Embedding record
    """
    client = get_supabase_client()
    
    return client.insert("embeddings", {
        "file_id": file_id,
        "entity_id": entity_id,
        "chunk_text": chunk_text,
        "embedding": embedding,
        "start_line": start_line,
        "end_line": end_line,
        "metadata": metadata or {},
    })


def insert_embeddings_batch(
    embeddings_data: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Insert multiple embeddings in batch.
    
    Args:
        embeddings_data: List of embedding records
        
    Returns:
        List of inserted records
    """
    client = get_supabase_client()
    return client.insert_many("embeddings", embeddings_data)


def match_embeddings(
    query_embedding: List[float],
    match_threshold: float = 0.7,
    match_count: int = 5
) -> List[Dict[str, Any]]:
    """
    Find similar embeddings using vector similarity search.
    
    Calls the match_embeddings PostgreSQL function.
    
    Args:
        query_embedding: Query vector (768 dimensions)
        match_threshold: Minimum similarity threshold (0.0 - 1.0)
        match_count: Maximum number of results
        
    Returns:
        List of matching chunks with similarity scores
    """
    client = get_supabase_client()
    
    return client.rpc("match_embeddings", {
        "query_embedding": query_embedding,
        "match_threshold": match_threshold,
        "match_count": match_count,
    })


def calculate_blast_radius(file_id: str) -> int:
    """
    Calculate the blast radius of changes to a file.
    
    Calls the calculate_blast_radius PostgreSQL function.
    
    Args:
        file_id: UUID of the target file
        
    Returns:
        Number of files that would be affected
    """
    client = get_supabase_client()
    
    result = client.rpc("calculate_blast_radius", {
        "target_file_id": file_id,
    })
    
    return result if isinstance(result, int) else 0


def insert_decision(
    project_id: str,
    title: str,
    description: str,
    rationale: Optional[str] = None,
    alternatives: Optional[List[Dict]] = None,
    tags: Optional[List[str]] = None,
    made_by: Optional[str] = None,
    git_commit_hash: Optional[str] = None
) -> Dict[str, Any]:
    """
    Insert an architectural decision record.
    
    Args:
        project_id: UUID of the project
        title: Decision title
        description: What was decided
        rationale: Why it was decided
        alternatives: Other options considered
        tags: Categorization tags
        made_by: Who made the decision
        git_commit_hash: Related git commit
        
    Returns:
        Decision record
    """
    client = get_supabase_client()
    
    return client.insert("decisions", {
        "project_id": project_id,
        "title": title,
        "description": description,
        "rationale": rationale,
        "alternatives": alternatives or [],
        "tags": tags or [],
        "made_by": made_by,
        "git_commit_hash": git_commit_hash,
    })


def insert_agent_task(
    project_id: str,
    task_type: str,
    description: str,
    context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Insert an agent task record.
    
    Args:
        project_id: UUID of the project
        task_type: Type of task (fix_bug, generate_tests, refactor)
        description: Task description
        context: Additional context
        
    Returns:
        Task record
    """
    client = get_supabase_client()
    
    return client.insert("agent_tasks", {
        "project_id": project_id,
        "type": task_type,
        "description": description,
        "context": context or {},
        "status": "pending",
    })


def update_task_status(
    task_id: str,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error_message: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update agent task status.
    
    Args:
        task_id: UUID of the task
        status: New status
        result: Task result data
        error_message: Error message if failed
        
    Returns:
        Updated task record
    """
    client = get_supabase_client()
    
    data = {"status": status}
    
    if result:
        data["result"] = result
    
    if error_message:
        data["error_message"] = error_message
    
    if status == "completed":
        data["completed_at"] = datetime.now().isoformat()
    elif status == "executing":
        data["started_at"] = datetime.now().isoformat()
    
    rows = client.update("agent_tasks", data, filters={"id": task_id})
    return rows[0] if rows else {}


def clear_project_embeddings(project_id: str) -> int:
    """
    Delete all embeddings for a project (for re-indexing).
    
    Args:
        project_id: UUID of the project
        
    Returns:
        Number of deleted records
    """
    client = get_supabase_client()
    
    # Get all file IDs for the project
    files = client.select("code_files", columns="id", filters={"project_id": project_id})
    
    if not files:
        return 0
    
    deleted_count = 0
    for file in files:
        deleted = client.delete("embeddings", filters={"file_id": file["id"]})
        deleted_count += len(deleted)
    
    return deleted_count
