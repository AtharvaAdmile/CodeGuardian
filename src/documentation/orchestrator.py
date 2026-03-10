"""
Documentation Orchestrator for coordinating documentation analysis workflow.

Note: Documentation generation has been moved to Copilot/AI assistants via MCP tools.
This orchestrator now focuses on analysis and context building only.
"""

import uuid
from datetime import datetime
from typing import List, Optional, Callable, Dict, Any

from src.models.documentation_models import (
    DocumentationSession,
    SessionStatusInfo,
    ErrorInfo,
    GapReport,
    ContextMap,
)
from src.documentation.analysis_agent import AnalysisAgent
from src.documentation.context_agent import ContextAgent
from src.documentation.review_manager import ReviewManager
from src.documentation.error_handler import ErrorHandler


class DocumentationOrchestrator:
    """
    Coordinates documentation analysis workflow.
    
    The orchestrator manages the execution of analysis agents:
    1. Analysis Agent - Identifies documentation gaps
    2. Context Agent - Builds context map with dependencies
    
    Documentation generation is now handled externally by AI assistants
    (e.g., GitHub Copilot) using context provided by MCP tools.
    """
    
    def __init__(
        self,
        analysis_agent: AnalysisAgent,
        context_agent: ContextAgent,
        review_manager: Optional[ReviewManager] = None,
        error_handler: Optional[ErrorHandler] = None
    ):
        """
        Initialize the Documentation Orchestrator.
        
        Args:
            analysis_agent: Agent for analyzing code and identifying gaps
            context_agent: Agent for building context maps
            review_manager: Optional manager for review workflow
            error_handler: Optional error handler for robust error management
        """
        self.analysis_agent = analysis_agent
        self.context_agent = context_agent
        self.review_manager = review_manager or ReviewManager()
        self.error_handler = error_handler or ErrorHandler()
        
        # Storage for active sessions
        self._sessions: Dict[str, DocumentationSession] = {}
    
    def analyze_documentation_gaps(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]] = None
    ) -> DocumentationSession:
        """
        Analyze files to identify documentation gaps and build context.
        
        This method orchestrates analysis agents to:
        1. Analyze files and generate gap report
        2. Build context map with dependencies
        
        The results can be used by AI assistants to generate documentation.
        
        Args:
            file_paths: List of file paths to process
            progress_callback: Optional callback function(stage, progress_percent, current_item)
        
        Returns:
            DocumentationSession containing analysis results
        """
        # Create unique session ID
        session_id = str(uuid.uuid4())
        
        # Initialize session
        session = DocumentationSession(
            session_id=session_id,
            file_paths=file_paths,
            status=SessionStatusInfo(
                stage="analysis",
                progress_percent=0.0
            ),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Store session
        self._sessions[session_id] = session
        
        try:
            # Stage 1: Analysis
            self._update_progress(session, "analysis", 0.0, None, progress_callback)
            gap_report = self._execute_analysis_stage(
                session,
                file_paths,
                progress_callback
            )
            session.gap_report = gap_report
            
            # Stage 2: Context Building
            self._update_progress(session, "context", 50.0, None, progress_callback)
            context_map = self._execute_context_stage(
                session,
                gap_report,
                progress_callback
            )
            session.context_map = context_map
            
            # Mark as complete
            self._update_progress(session, "complete", 100.0, None, progress_callback)
            
        except Exception as e:
            # Handle unexpected errors
            error_info = self.error_handler.handle_error(
                error=e,
                stage=session.status.stage,
                context={
                    "session_id": session_id,
                    "file_paths": file_paths
                }
            )
            session.errors.append(error_info)
            session.status.stage = "error"
            raise
        
        finally:
            session.updated_at = datetime.now()
        
        return session
    
    def get_session_status(self, session_id: str) -> Optional[SessionStatusInfo]:
        """
        Query the current workflow state for a session.
        
        Args:
            session_id: Unique identifier for the documentation session
        
        Returns:
            SessionStatusInfo with current status, or None if session not found
        """
        if session_id not in self._sessions:
            return None
        
        session = self._sessions[session_id]
        return session.status
    
    def get_session(self, session_id: str) -> Optional[DocumentationSession]:
        """
        Get the complete session object.
        
        Args:
            session_id: Unique identifier for the documentation session
        
        Returns:
            DocumentationSession object, or None if not found
        """
        return self._sessions.get(session_id)
    
    def get_all_sessions(self) -> List[str]:
        """Get list of all session IDs."""
        return list(self._sessions.keys())
    
    def clear_session(self, session_id: str) -> None:
        """Clear a session from memory."""
        if session_id in self._sessions:
            del self._sessions[session_id]
        
        if self.review_manager:
            self.review_manager.clear_session(session_id)
    
    def _execute_analysis_stage(
        self,
        session: DocumentationSession,
        file_paths: List[str],
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]]
    ) -> GapReport:
        """Execute the analysis stage to identify documentation gaps."""
        try:
            def analysis_progress(current: int, total: int, file_path: str):
                stage_progress = (current / total) * 50.0 if total > 0 else 0.0
                self._update_progress(
                    session,
                    "analysis",
                    stage_progress,
                    file_path,
                    progress_callback
                )
            
            gap_report = self.analysis_agent.analyze_files(
                file_paths,
                progress_callback=analysis_progress
            )
            
            return gap_report
            
        except Exception as e:
            error_info = self.error_handler.handle_error(
                error=e,
                stage="analysis",
                context={
                    "session_id": session.session_id,
                    "file_paths": file_paths
                }
            )
            session.errors.append(error_info)
            raise
    
    def _execute_context_stage(
        self,
        session: DocumentationSession,
        gap_report: GapReport,
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]]
    ) -> ContextMap:
        """Execute the context building stage."""
        try:
            def context_progress(current: int, total: int, element_name: str):
                stage_progress = 50.0 + ((current / total) * 50.0 if total > 0 else 0.0)
                self._update_progress(
                    session,
                    "context",
                    stage_progress,
                    element_name,
                    progress_callback
                )
            
            context_map = self.context_agent.build_context_map(
                gap_report,
                progress_callback=context_progress
            )
            
            return context_map
            
        except Exception as e:
            error_info = self.error_handler.handle_error(
                error=e,
                stage="context",
                context={
                    "session_id": session.session_id,
                    "total_elements": gap_report.total_elements
                }
            )
            session.errors.append(error_info)
            raise
    
    def _update_progress(
        self,
        session: DocumentationSession,
        stage: str,
        progress_percent: float,
        current_item: Optional[str],
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]]
    ) -> None:
        """Update session progress and call progress callback."""
        session.status.stage = stage
        session.status.progress_percent = progress_percent
        session.status.current_file = current_item
        session.updated_at = datetime.now()
        
        if progress_callback:
            try:
                progress_callback(stage, progress_percent, current_item)
            except Exception as e:
                print(f"Warning: Progress callback error: {str(e)}")
