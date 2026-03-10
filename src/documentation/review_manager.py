"""
Review Manager for documentation approval workflow.

This module provides the ReviewManager class that handles storage, retrieval,
and status management of generated documentation items during the review process.
"""

from typing import List, Dict, Optional, Any
from datetime import datetime
from src.models.documentation_models import DocumentationItem, ApprovalStatus


class ReviewManager:
    """
    Manages the review and approval workflow for generated documentation.
    
    Provides in-memory storage for documentation sessions and items,
    with filtering, status tracking, and approval management capabilities.
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
    """
    
    def __init__(self):
        """Initialize review manager with in-memory storage."""
        # Storage structure: session_id -> list of DocumentationItem
        self._sessions: Dict[str, List[DocumentationItem]] = {}
        
        # Track status transitions for audit trail
        self._status_history: Dict[str, List[Dict[str, Any]]] = {}
    
    def store_documentation_items(
        self,
        session_id: str,
        items: List[DocumentationItem]
    ) -> None:
        """
        Store generated documentation items for review.
        
        Args:
            session_id: Unique identifier for the documentation session
            items: List of DocumentationItem objects to store
            
        Requirements: 5.1
        """
        if session_id not in self._sessions:
            self._sessions[session_id] = []
            self._status_history[session_id] = []
        
        # Add items to session storage
        self._sessions[session_id].extend(items)
        
        # Record initial storage event
        for item in items:
            self._record_status_change(
                session_id=session_id,
                element_id=item.element_id,
                old_status=None,
                new_status=item.approval_status,
                timestamp=datetime.now()
            )
    
    def get_items_for_review(
        self,
        session_id: str,
        filter_by: Optional[Dict[str, Any]] = None
    ) -> List[DocumentationItem]:
        """
        Get documentation items for review with optional filtering.
        
        Supports filtering by:
        - approval_status: Filter by approval status (pending, approved, rejected, edited)
        - language: Filter by programming language (python, javascript, typescript)
        - element_type: Filter by element type (function, class, method)
        - file_path: Filter by file path (exact match or substring)
        
        Args:
            session_id: Unique identifier for the documentation session
            filter_by: Optional dictionary of filter criteria
            
        Returns:
            List of DocumentationItem objects matching the filter criteria
            
        Requirements: 5.2
        """
        if session_id not in self._sessions:
            return []
        
        items = self._sessions[session_id]
        
        # If no filters, return all items
        if not filter_by:
            return items.copy()
        
        # Apply filters
        filtered_items = items
        
        if "approval_status" in filter_by:
            status = filter_by["approval_status"]
            filtered_items = [
                item for item in filtered_items
                if item.approval_status == status
            ]
        
        if "language" in filter_by:
            language = filter_by["language"]
            filtered_items = [
                item for item in filtered_items
                if item.language.lower() == language.lower()
            ]
        
        if "element_type" in filter_by:
            element_type = filter_by["element_type"]
            filtered_items = [
                item for item in filtered_items
                if item.element_type == element_type
            ]
        
        if "file_path" in filter_by:
            file_path = filter_by["file_path"]
            filtered_items = [
                item for item in filtered_items
                if file_path in item.file_path
            ]
        
        return filtered_items
    
    def update_approval_status(
        self,
        session_id: str,
        element_id: str,
        status: str,
        edited_doc: Optional[str] = None
    ) -> None:
        """
        Update approval status and optionally store edited version.
        
        Handles approve, reject, and edit actions. Tracks status transitions
        from pending to approved/rejected/edited.
        
        Args:
            session_id: Unique identifier for the documentation session
            element_id: Unique identifier for the code element
            status: New approval status (approved, rejected, edited)
            edited_doc: Optional edited documentation content (required for 'edited' status)
            
        Raises:
            ValueError: If session or element not found, or if edited_doc is missing for 'edited' status
            
        Requirements: 5.3, 5.4
        """
        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")
        
        # Find the item to update
        item = None
        for doc_item in self._sessions[session_id]:
            if doc_item.element_id == element_id:
                item = doc_item
                break
        
        if item is None:
            raise ValueError(f"Element not found: {element_id} in session {session_id}")
        
        # Validate edited status requires edited_doc
        if status == "edited" and edited_doc is None:
            raise ValueError("edited_doc is required when status is 'edited'")
        
        # Record old status for history
        old_status = item.approval_status
        
        # Update the item
        item.approval_status = status
        if edited_doc is not None:
            item.edited_doc = edited_doc
        
        # Record status transition
        self._record_status_change(
            session_id=session_id,
            element_id=element_id,
            old_status=old_status,
            new_status=status,
            timestamp=datetime.now(),
            edited=edited_doc is not None
        )
    
    def get_approved_items(
        self,
        session_id: str
    ) -> List[DocumentationItem]:
        """
        Get all approved documentation items ready for export.
        
        Returns items with approval_status of 'approved' or 'edited'.
        Items with 'edited' status will use the edited_doc content.
        
        Args:
            session_id: Unique identifier for the documentation session
            
        Returns:
            List of approved DocumentationItem objects
            
        Requirements: 5.5
        """
        if session_id not in self._sessions:
            return []
        
        approved_items = [
            item for item in self._sessions[session_id]
            if item.approval_status in ["approved", "edited"]
        ]
        
        return approved_items
    
    def get_session_statistics(
        self,
        session_id: str
    ) -> Dict[str, Any]:
        """
        Get statistics for a documentation session.
        
        Args:
            session_id: Unique identifier for the documentation session
            
        Returns:
            Dictionary containing session statistics
        """
        if session_id not in self._sessions:
            return {
                "total_items": 0,
                "by_status": {},
                "by_language": {},
                "by_type": {},
                "review_progress": 0.0
            }
        
        items = self._sessions[session_id]
        total = len(items)
        
        # Count by status
        by_status = {}
        for item in items:
            status = item.approval_status
            by_status[status] = by_status.get(status, 0) + 1
        
        # Count by language
        by_language = {}
        for item in items:
            lang = item.language
            by_language[lang] = by_language.get(lang, 0) + 1
        
        # Count by type
        by_type = {}
        for item in items:
            elem_type = item.element_type
            by_type[elem_type] = by_type.get(elem_type, 0) + 1
        
        # Calculate review progress (items that are not pending)
        reviewed = sum(1 for item in items if item.approval_status != "pending")
        review_progress = (reviewed / total * 100) if total > 0 else 0.0
        
        return {
            "total_items": total,
            "by_status": by_status,
            "by_language": by_language,
            "by_type": by_type,
            "review_progress": review_progress
        }
    
    def get_status_history(
        self,
        session_id: str,
        element_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get status change history for a session or specific element.
        
        Args:
            session_id: Unique identifier for the documentation session
            element_id: Optional element ID to filter history
            
        Returns:
            List of status change records
        """
        if session_id not in self._status_history:
            return []
        
        history = self._status_history[session_id]
        
        if element_id:
            return [
                record for record in history
                if record["element_id"] == element_id
            ]
        
        return history.copy()
    
    def clear_session(self, session_id: str) -> None:
        """
        Clear all data for a session.
        
        Args:
            session_id: Unique identifier for the documentation session
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
        if session_id in self._status_history:
            del self._status_history[session_id]
    
    def get_all_sessions(self) -> List[str]:
        """
        Get list of all session IDs.
        
        Returns:
            List of session IDs
        """
        return list(self._sessions.keys())
    
    def _record_status_change(
        self,
        session_id: str,
        element_id: str,
        old_status: Optional[str],
        new_status: str,
        timestamp: datetime,
        edited: bool = False
    ) -> None:
        """
        Record a status change in the history.
        
        Args:
            session_id: Session identifier
            element_id: Element identifier
            old_status: Previous status (None for initial storage)
            new_status: New status
            timestamp: Time of change
            edited: Whether documentation was edited
        """
        if session_id not in self._status_history:
            self._status_history[session_id] = []
        
        record = {
            "element_id": element_id,
            "old_status": old_status,
            "new_status": new_status,
            "timestamp": timestamp,
            "edited": edited
        }
        
        self._status_history[session_id].append(record)
