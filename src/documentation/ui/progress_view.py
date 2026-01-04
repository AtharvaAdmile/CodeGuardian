"""
Progress View UI Component for Documentation Generator.

This module provides a Streamlit interface for displaying real-time progress
during the documentation generation workflow. It shows the current stage,
progress percentage, current file/element being processed, and stage completion
checkmarks.

Requirements: 7.1, 7.2, 7.3
"""

import streamlit as st
from typing import Optional, Dict, Any
from datetime import datetime

from src.models.documentation_models import (
    DocumentationSession,
    SessionStatusInfo
)


class ProgressView:
    """
    Streamlit UI component for progress tracking.
    
    Displays real-time progress information during documentation generation,
    including current workflow stage, progress bar, current item being processed,
    element counts, and stage completion indicators.
    
    Requirements: 7.1, 7.2, 7.3
    """
    
    # Stage display configuration
    STAGES = {
        'analysis': {
            'name': 'Analysis',
            'icon': '🔍',
            'description': 'Analyzing code structure and identifying documentation gaps',
            'order': 1
        },
        'context': {
            'name': 'Context Building',
            'icon': '🔗',
            'description': 'Building context map with dependencies and relationships',
            'order': 2
        },
        'generation': {
            'name': 'Documentation Generation',
            'icon': '✍️',
            'description': 'Generating documentation using AI',
            'order': 3
        },
        'review': {
            'name': 'Review Preparation',
            'icon': '📋',
            'description': 'Preparing documentation for review',
            'order': 4
        },
        'complete': {
            'name': 'Complete',
            'icon': '✅',
            'description': 'Documentation generation completed successfully',
            'order': 5
        },
        'error': {
            'name': 'Error',
            'icon': '❌',
            'description': 'An error occurred during processing',
            'order': 6
        }
    }
    
    def __init__(self):
        """Initialize the Progress View."""
        # Initialize session state for progress tracking
        if 'progress_session' not in st.session_state:
            st.session_state.progress_session = None
        
        if 'progress_last_update' not in st.session_state:
            st.session_state.progress_last_update = None
    
    def render(self, session: Optional[DocumentationSession] = None) -> None:
        """
        Render the progress tracking interface.
        
        Displays current workflow stage, progress bar, current item being processed,
        element counts, and stage completion checkmarks.
        
        Args:
            session: Current DocumentationSession object with progress information
            
        Requirements: 7.1, 7.2, 7.3
        """
        if session is None:
            self._render_no_session()
            return
        
        # Update session state
        st.session_state.progress_session = session
        st.session_state.progress_last_update = datetime.now()
        
        # Render progress UI
        self._render_header(session)
        self._render_progress_bar(session.status)
        self._render_current_status(session.status)
        self._render_stage_checklist(session.status)
        
        # Show errors if any
        if session.errors:
            self._render_errors(session.errors)
    
    def _render_no_session(self) -> None:
        """Render placeholder when no session is active."""
        st.info("👋 No documentation generation in progress. Select files to begin.")
    
    def _render_header(self, session: DocumentationSession) -> None:
        """
        Render the progress view header.
        
        Args:
            session: Current documentation session
        """
        st.subheader("📊 Documentation Generation Progress")
        
        # Show session info
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Files", len(session.file_paths))
        
        with col2:
            if session.gap_report:
                st.metric("Elements with Gaps", session.gap_report.elements_with_gaps)
            else:
                st.metric("Elements with Gaps", "—")
        
        with col3:
            if session.documentation_items:
                st.metric("Documentation Generated", len(session.documentation_items))
            else:
                st.metric("Documentation Generated", "—")
        
        st.divider()
    
    def _render_progress_bar(self, status: SessionStatusInfo) -> None:
        """
        Render the main progress bar with percentage.
        
        Args:
            status: Current session status information
            
        Requirements: 7.1, 7.2
        """
        # Get stage info
        stage_info = self.STAGES.get(status.stage, self.STAGES['analysis'])
        
        # Display current stage
        st.markdown(f"### {stage_info['icon']} {stage_info['name']}")
        st.caption(stage_info['description'])
        
        # Progress bar
        progress_value = status.progress_percent / 100.0
        st.progress(progress_value, text=f"{status.progress_percent:.1f}% Complete")
    
    def _render_current_status(self, status: SessionStatusInfo) -> None:
        """
        Render current processing status details.
        
        Args:
            status: Current session status information
            
        Requirements: 7.2, 7.3
        """
        st.divider()
        
        # Current item being processed
        if status.current_file:
            st.markdown("**Currently Processing:**")
            st.code(status.current_file, language=None)
        
        # Element counts
        if status.total_elements > 0:
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric(
                    "Elements Processed",
                    f"{status.elements_processed} / {status.total_elements}"
                )
            
            with col2:
                if status.total_elements > 0:
                    element_progress = (status.elements_processed / status.total_elements) * 100
                    st.metric("Element Progress", f"{element_progress:.1f}%")
    
    def _render_stage_checklist(self, status: SessionStatusInfo) -> None:
        """
        Render stage completion checklist with checkmarks.
        
        Args:
            status: Current session status information
            
        Requirements: 7.1, 7.3
        """
        st.divider()
        st.markdown("**Workflow Stages:**")
        
        # Get current stage order
        current_stage_order = self.STAGES.get(status.stage, {}).get('order', 0)
        
        # Render each stage
        stages_to_show = ['analysis', 'context', 'generation', 'review', 'complete']
        
        for stage_key in stages_to_show:
            stage_info = self.STAGES[stage_key]
            stage_order = stage_info['order']
            
            # Determine status
            if stage_order < current_stage_order:
                # Completed stage
                icon = "✅"
                status_text = "Complete"
                color = "green"
            elif stage_order == current_stage_order:
                # Current stage
                icon = "⟳"
                status_text = "In Progress"
                color = "blue"
            else:
                # Pending stage
                icon = "⋯"
                status_text = "Pending"
                color = "gray"
            
            # Render stage row
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.markdown(f"{icon} **{stage_info['name']}**")
            
            with col2:
                if color == "green":
                    st.success(status_text, icon="✅")
                elif color == "blue":
                    st.info(status_text, icon="⟳")
                else:
                    st.caption(status_text)
    
    def _render_errors(self, errors: list) -> None:
        """
        Render error information if errors occurred.
        
        Args:
            errors: List of ErrorInfo objects
        """
        st.divider()
        st.error(f"⚠️ {len(errors)} error(s) occurred during processing")
        
        with st.expander("View Error Details", expanded=False):
            for i, error in enumerate(errors, 1):
                st.markdown(f"**Error {i}:**")
                st.markdown(f"- **Type:** {error.error_type}")
                st.markdown(f"- **Stage:** {error.stage}")
                
                if error.file_path:
                    st.markdown(f"- **File:** `{error.file_path}`")
                
                if error.element_id:
                    st.markdown(f"- **Element:** `{error.element_id}`")
                
                st.markdown(f"- **Message:** {error.error_message}")
                st.markdown(f"- **Time:** {error.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
                st.markdown(f"- **Recoverable:** {'Yes' if error.recoverable else 'No'}")
                
                if i < len(errors):
                    st.divider()
    
    def render_compact(self, status: SessionStatusInfo) -> None:
        """
        Render a compact version of progress information.
        
        Useful for displaying progress in a sidebar or smaller space.
        
        Args:
            status: Current session status information
        """
        stage_info = self.STAGES.get(status.stage, self.STAGES['analysis'])
        
        st.markdown(f"**{stage_info['icon']} {stage_info['name']}**")
        st.progress(status.progress_percent / 100.0)
        st.caption(f"{status.progress_percent:.1f}% complete")
        
        if status.current_file:
            st.caption(f"📄 {status.current_file}")
        
        if status.total_elements > 0:
            st.caption(f"🔢 {status.elements_processed}/{status.total_elements} elements")
    
    def render_summary(self, session: DocumentationSession) -> None:
        """
        Render a summary view after completion.
        
        Args:
            session: Completed documentation session
        """
        st.success("✅ Documentation generation completed!")
        
        # Summary metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Files Processed", len(session.file_paths))
        
        with col2:
            if session.gap_report:
                st.metric("Gaps Identified", session.gap_report.elements_with_gaps)
            else:
                st.metric("Gaps Identified", "—")
        
        with col3:
            st.metric("Documentation Generated", len(session.documentation_items))
        
        # Time information
        if session.created_at and session.updated_at:
            duration = session.updated_at - session.created_at
            duration_minutes = duration.total_seconds() / 60.0
            st.info(f"⏱️ Total time: {duration_minutes:.1f} minutes")
        
        # Show breakdown by language if available
        if session.gap_report and session.gap_report.elements_by_language:
            st.divider()
            st.markdown("**Elements by Language:**")
            
            for language, count in session.gap_report.elements_by_language.items():
                st.markdown(f"- **{language}:** {count} elements")
        
        # Show errors if any
        if session.errors:
            st.divider()
            st.warning(f"⚠️ {len(session.errors)} error(s) occurred during processing")
            
            with st.expander("View Error Details"):
                for i, error in enumerate(session.errors, 1):
                    st.markdown(f"**Error {i}:** {error.error_message}")
                    if error.file_path:
                        st.caption(f"File: {error.file_path}")
    
    @staticmethod
    def create_progress_callback():
        """
        Create a progress callback function for use with the orchestrator.
        
        This callback updates Streamlit session state when called by the
        orchestrator during processing.
        
        Returns:
            Callable that can be passed to orchestrator.generate_documentation()
        """
        def progress_callback(stage: str, progress_percent: float, current_item: Optional[str]):
            """
            Progress callback for orchestrator.
            
            Args:
                stage: Current workflow stage
                progress_percent: Progress percentage (0-100)
                current_item: Current file or element being processed
            """
            # Update session state
            if 'progress_status' not in st.session_state:
                st.session_state.progress_status = {}
            
            st.session_state.progress_status = {
                'stage': stage,
                'progress_percent': progress_percent,
                'current_item': current_item,
                'last_update': datetime.now()
            }
        
        return progress_callback
    
    def clear_progress(self) -> None:
        """Clear progress tracking state."""
        if 'progress_session' in st.session_state:
            st.session_state.progress_session = None
        
        if 'progress_last_update' in st.session_state:
            st.session_state.progress_last_update = None
        
        if 'progress_status' in st.session_state:
            del st.session_state.progress_status
