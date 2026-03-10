"""
Database module for CodeGuardian.

Provides Supabase client and query helpers.
"""

from src.db.supabase_client import get_supabase_client, SupabaseClient
from src.db.queries import (
    create_project,
    get_project,
    insert_file,
    insert_embedding,
    match_embeddings,
    calculate_blast_radius,
)

__all__ = [
    "get_supabase_client",
    "SupabaseClient",
    "create_project",
    "get_project",
    "insert_file",
    "insert_embedding",
    "match_embeddings",
    "calculate_blast_radius",
]
