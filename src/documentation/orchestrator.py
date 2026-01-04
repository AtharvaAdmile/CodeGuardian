"""
Documentation Orchestrator for coordinating the documentation generation workflow.

This module provides the DocumentationOrchestrator class that manages the complete
workflow of documentation generation, from analysis through context building to
documentation generation and review preparation.
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
    DocumentationItem
)
from src.documentation.analysis_agent import AnalysisAgent
from src.documentation.context_agent import ContextAgent
from src.documentation.documentation_agent import DocumentationAgent
from src.documentation.review_manager import ReviewManager
from src.documentation.error_handler import ErrorHandler


class DocumentationOrchestrator:
    """
    Coordinates the complete documentation generation workflow.
    
    The orchestrator manages the execution of all agents in the proper sequence:
    1. Analysis Agent - Identifies documentation gaps
    2. Context Agent - Builds context map with dependencies
    3. Documentation Agent - Generates documentation
    4. Review Manager - Stores results for review
    
    It handles progress tracking, error management, and session state throughout
    the workflow.
    
    Requirements: 7.1, 7.2, 7.3, 7.4
    """
    
    def __init__(
        self,
        analysis_agent: AnalysisAgent,
        context_agent: ContextAgent,
        documentation_agent: DocumentationAgent,
        review_manager: ReviewManager,
        error_handler: Optional[ErrorHandler] = None
    ):
        """
        Initialize the Documentation Orchestrator.
        
        Args:
            analysis_agent: Agent for analyzing code and identifying gaps
            context_agent: Agent for building context maps
            documentation_agent: Agent for generating documentation
            review_manager: Manager for review workflow
            error_handler: Optional error handler for robust error management
        """
        self.analysis_agent = analysis_agent
        self.context_agent = context_agent
        self.documentation_agent = documentation_agent
        self.review_manager = review_manager
        self.error_handler = error_handler or ErrorHandler()
        
        # Storage for active sessions
        self._sessions: Dict[str, DocumentationSession] = {}
    
    def generate_documentation(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]] = None
    ) -> DocumentationSession:
        """
        Execute the full documentation generation workflow.
        
        This method orchestrates all agents to:
        1. Analyze files and generate gap report
        2. Build context map with dependencies
        3. Generate documentation for all elements with gaps
        4. Store results in review manager
        
        Progress is tracked throughout and errors are collected for reporting.
        
        Args:
            file_paths: List of file paths to process
            progress_callback: Optional callback function(stage, progress_percent, current_item)
                             called to report progress updates
        
        Returns:
            DocumentationSession containing all results and metadata
            
        Requirements: 7.1, 7.2, 7.3, 7.4
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
            self._update_progress(session, "context", 33.0, None, progress_callback)
            context_map = self._execute_context_stage(
                session,
                gap_report,
                progress_callback
            )
            session.context_map = context_map
            
            # Stage 3: Documentation Generation
            self._update_progress(session, "generation", 66.0, None, progress_callback)
            documentation_items = self._execute_generation_stage(
                session,
                context_map,
                gap_report,
                progress_callback
            )
            session.documentation_items = documentation_items
            
            # Stage 4: Store in Review Manager
            self._update_progress(session, "review", 90.0, None, progress_callback)
            self.review_manager.store_documentation_items(
                session_id,
                documentation_items
            )
            
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
            
            # Re-raise to let caller handle
            raise
        
        finally:
            # Update session timestamp
            session.updated_at = datetime.now()
        
        return session
    
    def get_session_status(self, session_id: str) -> Optional[SessionStatusInfo]:
        """
        Query the current workflow state for a session.
        
        Args:
            session_id: Unique identifier for the documentation session
        
        Returns:
            SessionStatusInfo with current status, or None if session not found
            
        Requirements: 7.4
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
        """
        Get list of all session IDs.
        
        Returns:
            List of session IDs
        """
        return list(self._sessions.keys())
    
    def clear_session(self, session_id: str) -> None:
        """
        Clear a session from memory.
        
        Args:
            session_id: Unique identifier for the documentation session
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
        
        # Also clear from review manager
        self.review_manager.clear_session(session_id)
    
    def _execute_analysis_stage(
        self,
        session: DocumentationSession,
        file_paths: List[str],
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]]
    ) -> GapReport:
        """
        Execute the analysis stage to identify documentation gaps.
        
        Args:
            session: Current documentation session
            file_paths: List of files to analyze
            progress_callback: Progress callback function
        
        Returns:
            GapReport with identified documentation gaps
        
        Raises:
            Exception: If analysis fails critically
        """
        try:
            # Create progress wrapper for analysis agent
            def analysis_progress(current: int, total: int, file_path: str):
                # Calculate progress within analysis stage (0-33%)
                stage_progress = (current / total) * 33.0 if total > 0 else 0.0
                self._update_progress(
                    session,
                    "analysis",
                    stage_progress,
                    file_path,
                    progress_callback
                )
            
            # Execute analysis
            gap_report = self.analysis_agent.analyze_files(
                file_paths,
                progress_callback=analysis_progress
            )
            
            return gap_report
            
        except Exception as e:
            # Log error and re-raise
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
        """
        Execute the context building stage.
        
        Args:
            session: Current documentation session
            gap_report: Gap report from analysis stage
            progress_callback: Progress callback function
        
        Returns:
            ContextMap with dependency graph and processing order
        
        Raises:
            Exception: If context building fails critically
        """
        try:
            # Create progress wrapper for context agent
            def context_progress(current: int, total: int, element_name: str):
                # Calculate progress within context stage (33-66%)
                stage_progress = 33.0 + ((current / total) * 33.0 if total > 0 else 0.0)
                self._update_progress(
                    session,
                    "context",
                    stage_progress,
                    element_name,
                    progress_callback
                )
            
            # Execute context building
            context_map = self.context_agent.build_context_map(
                gap_report,
                progress_callback=context_progress
            )
            
            return context_map
            
        except Exception as e:
            # Log error and re-raise
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
    
    def _execute_generation_stage(
        self,
        session: DocumentationSession,
        context_map: ContextMap,
        gap_report: GapReport,
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]]
    ) -> List[DocumentationItem]:
        """
        Execute the documentation generation stage.
        
        Args:
            session: Current documentation session
            context_map: Context map from context stage
            gap_report: Gap report from analysis stage
            progress_callback: Progress callback function
        
        Returns:
            List of DocumentationItem objects with generated documentation
        """
        documentation_items = []
        
        try:
            # Create progress wrapper for documentation agent
            def generation_progress(current: int, total: int, element_name: str):
                # Calculate progress within generation stage (66-90%)
                stage_progress = 66.0 + ((current / total) * 24.0 if total > 0 else 0.0)
                self._update_progress(
                    session,
                    "generation",
                    stage_progress,
                    element_name,
                    progress_callback
                )
            
            # Execute documentation generation
            documentation_items = self.documentation_agent.generate_documentation(
                context_map,
                gap_report,
                progress_callback=generation_progress
            )
            
        except Exception as e:
            # For generation errors, we want to continue with partial results
            # Log the error but don't re-raise
            error_info = self.error_handler.handle_error(
                error=e,
                stage="generation",
                context={
                    "session_id": session.session_id,
                    "elements_processed": len(documentation_items)
                }
            )
            session.errors.append(error_info)
        
        return documentation_items
    
    def _update_progress(
        self,
        session: DocumentationSession,
        stage: str,
        progress_percent: float,
        current_item: Optional[str],
        progress_callback: Optional[Callable[[str, float, Optional[str]], None]]
    ) -> None:
        """
        Update session progress and call progress callback.
        
        Args:
            session: Current documentation session
            stage: Current workflow stage
            progress_percent: Progress percentage (0-100)
            current_item: Current file or element being processed
            progress_callback: Optional callback to notify of progress
        """
        # Update session status
        session.status.stage = stage
        session.status.progress_percent = progress_percent
        session.status.current_file = current_item
        session.updated_at = datetime.now()
        
        # Call progress callback if provided
        if progress_callback:
            try:
                progress_callback(stage, progress_percent, current_item)
            except Exception as e:
                # Don't let callback errors break the workflow
                print(f"Warning: Progress callback error: {str(e)}")
