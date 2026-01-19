"""
Supabase client wrapper for CodeGuardian.

Provides connection management and basic operations.
"""

from typing import Optional, Any, Dict, List
import logging

from supabase import create_client, Client
from src.config.settings import get_settings

logger = logging.getLogger(__name__)

# Global client instance (lazy initialized)
_client: Optional[Client] = None


class SupabaseClient:
    """
    Wrapper around Supabase client with CodeGuardian-specific operations.
    """
    
    def __init__(self, client: Client):
        """
        Initialize with an existing Supabase client.
        
        Args:
            client: Supabase Client instance
        """
        self._client = client
    
    @property
    def client(self) -> Client:
        """Get the underlying Supabase client."""
        return self._client
    
    def insert(self, table: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Insert a row into a table.
        
        Args:
            table: Table name
            data: Row data as dictionary
            
        Returns:
            Inserted row data
        """
        response = self._client.table(table).insert(data).execute()
        if response.data:
            return response.data[0]
        raise Exception(f"Insert failed for table {table}")
    
    def insert_many(self, table: str, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Insert multiple rows into a table.
        
        Args:
            table: Table name
            data: List of row data dictionaries
            
        Returns:
            List of inserted rows
        """
        response = self._client.table(table).insert(data).execute()
        return response.data or []
    
    def select(
        self,
        table: str,
        columns: str = "*",
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Select rows from a table.
        
        Args:
            table: Table name
            columns: Comma-separated column names or "*"
            filters: Dictionary of column=value filters
            limit: Maximum number of rows
            
        Returns:
            List of matching rows
        """
        query = self._client.table(table).select(columns)
        
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        
        if limit:
            query = query.limit(limit)
        
        response = query.execute()
        return response.data or []
    
    def select_one(
        self,
        table: str,
        columns: str = "*",
        filters: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Select a single row from a table.
        
        Args:
            table: Table name
            columns: Comma-separated column names or "*"
            filters: Dictionary of column=value filters
            
        Returns:
            Matching row or None
        """
        rows = self.select(table, columns, filters, limit=1)
        return rows[0] if rows else None
    
    def update(
        self,
        table: str,
        data: Dict[str, Any],
        filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Update rows in a table.
        
        Args:
            table: Table name
            data: Update data
            filters: Dictionary of column=value filters
            
        Returns:
            List of updated rows
        """
        query = self._client.table(table).update(data)
        
        for key, value in filters.items():
            query = query.eq(key, value)
        
        response = query.execute()
        return response.data or []
    
    def delete(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Delete rows from a table.
        
        Args:
            table: Table name
            filters: Dictionary of column=value filters
            
        Returns:
            List of deleted rows
        """
        query = self._client.table(table).delete()
        
        for key, value in filters.items():
            query = query.eq(key, value)
        
        response = query.execute()
        return response.data or []
    
    def rpc(self, function_name: str, params: Dict[str, Any]) -> Any:
        """
        Call a PostgreSQL function via RPC.
        
        Args:
            function_name: Name of the PostgreSQL function
            params: Function parameters
            
        Returns:
            Function result
        """
        response = self._client.rpc(function_name, params).execute()
        return response.data


def get_supabase_client() -> SupabaseClient:
    """
    Get the global Supabase client instance.
    
    Returns:
        SupabaseClient wrapper instance
        
    Raises:
        ValueError: If Supabase credentials are not configured
    """
    global _client
    
    if _client is None:
        settings = get_settings()
        
        if not settings.database.url or not settings.database.key:
            raise ValueError(
                "Supabase credentials not found. "
                "Please set SUPABASE_URL and SUPABASE_KEY in your .env file."
            )
        
        _client = create_client(settings.database.url, settings.database.key)
        logger.info("Supabase client initialized")
    
    return SupabaseClient(_client)


def reset_client() -> None:
    """Reset the global client instance (useful for testing)."""
    global _client
    _client = None
