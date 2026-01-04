"""
Review View UI Component for Documentation Generator.

This module provides a Streamlit interface for reviewing and approving generated
documentation. Users can view original code alongside generated documentation,
filter items by various criteria, and approve, reject, or edit documentation.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

import streamlit as st
from typing import Optional, List, Dict, Any
from pathlib import Path

from src.models.documentation_models import DocumentationItem
from src.documentation.review_manager import ReviewManager


class ReviewView:
    """
    Streamlit UI component for documentation review.
    
    Provides an interface for reviewing generated documentation with filtering,
    side-by-side comparison, and approval/rejection/editing capabilities.
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
    """
    
    # Status display configuration
    STATUS_CONFIG = {
        'pending': {
            'icon': '⏳',
            'color': 'orange',
            'label': 'Pending Review'
        },
        'approved': {
            'icon': '✅',
            'color': 'green',
            'label': 'Approved'
        },
        'rejected': {
            'icon': '❌',
            'color': 'red',
            'label': 'Rejected'
        },
        'edited': {
            'icon': '✏️',
            'color': 'blue',
            'label': 'Edited & Approved'
        }
    }
    
    def __init__(self, review_manager: ReviewManager):
        """
        Initialize the Review View.
        
        Args:
            review_manager: ReviewManager instance for managing documentation items
        """
        self.review_manager = review_manager
        
        # Initialize session state for review
        if 'review_session_id' not in st.session_state:
            st.session_state.review_session_id = None
        
        if 'review_current_item_index' not in st.session_state:
            st.session_state.review_current_item_index = 0
        
        if 'review_filters' not in st.session_state:
            st.session_state.review_filters = {}
        
        if 'review_editing_item' not in st.session_state:
            st.session_state.review_editing_item = None
    
    def render(self, session_id: str) -> None:
        """
        Render the review interface.
        
        Displays list of documentation items with filtering options, side-by-side
        view of code and documentation, and action buttons for approval workflow.
        
        Args:
            session_id: Documentation session ID to review
            
        Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
        """
        # Update session ID
        st.session_state.review_session_id = session_id
        
        # Render header
        st.subheader("📋 Review Generated Documentation")
        
        # Get session statistics
        stats = self.review_manager.get_session_statistics(session_id)
        
        # Display progress summary
        self._render_progress_summary(stats)
        
        st.divider()
        
        # Render filters
        self._render_filters(session_id)
        
        st.divider()
        
        # Get filtered items
        items = self.review_manager.get_items_for_review(
            session_id,
            filter_by=st.session_state.review_filters
        )
        
        if not items:
            st.info("No documentation items match the current filters.")
            return
        
        # Render item list and detail view
        self._render_item_list(items)
        
        st.divider()
        
        # Render detail view for selected item
        if 0 <= st.session_state.review_current_item_index < len(items):
            current_item = items[st.session_state.review_current_item_index]
            self._render_item_detail(current_item, session_id)
    
    def _render_progress_summary(self, stats: Dict[str, Any]) -> None:
        """
        Render review progress summary.
        
        Args:
            stats: Session statistics dictionary
        """
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Items", stats['total_items'])
        
        with col2:
            pending = stats['by_status'].get('pending', 0)
            st.metric("Pending", pending, delta=None)
        
        with col3:
            approved = stats['by_status'].get('approved', 0) + stats['by_status'].get('edited', 0)
            st.metric("Approved", approved, delta=None)
        
        with col4:
            progress = stats['review_progress']
            st.metric("Progress", f"{progress:.1f}%")
        
        # Progress bar
        if stats['total_items'] > 0:
            st.progress(progress / 100.0, text=f"Review Progress: {progress:.1f}%")
    
    def _render_filters(self, session_id: str) -> None:
        """
        Render filter controls.
        
        Args:
            session_id: Documentation session ID
            
        Requirements: 5.2
        """
        st.markdown("**Filter Documentation Items:**")
        
        col1, col2, col3, col4 = st.columns(4)
        
        # Get all items for filter options
        all_items = self.review_manager.get_items_for_review(session_id)
        
        # Extract unique values for filters
        unique_statuses = sorted(set(item.approval_status for item in all_items))
        unique_languages = sorted(set(item.language for item in all_items))
        unique_types = sorted(set(item.element_type for item in all_items))
        unique_files = sorted(set(item.file_path for item in all_items))
        
        with col1:
            status_filter = st.selectbox(
                "Status",
                options=['All'] + unique_statuses,
                index=0,
                key='filter_status'
            )
        
        with col2:
            language_filter = st.selectbox(
                "Language",
                options=['All'] + unique_languages,
                index=0,
                key='filter_language'
            )
        
        with col3:
            type_filter = st.selectbox(
                "Element Type",
                options=['All'] + unique_types,
                index=0,
                key='filter_type'
            )
        
        with col4:
            file_filter = st.selectbox(
                "File",
                options=['All'] + [Path(f).name for f in unique_files],
                index=0,
                key='filter_file'
            )
        
        # Build filter dictionary
        filters = {}
        
        if status_filter != 'All':
            filters['approval_status'] = status_filter
        
        if language_filter != 'All':
            filters['language'] = language_filter
        
        if type_filter != 'All':
            filters['element_type'] = type_filter
        
        if file_filter != 'All':
            # Find full path for selected file name
            for file_path in unique_files:
                if Path(file_path).name == file_filter:
                    filters['file_path'] = file_path
                    break
        
        # Update session state
        st.session_state.review_filters = filters
        
        # Clear filters button
        if filters:
            if st.button("🔄 Clear Filters", use_container_width=True):
                st.session_state.review_filters = {}
                st.rerun()
    
    def _render_item_list(self, items: List[DocumentationItem]) -> None:
        """
        Render list of documentation items.
        
        Args:
            items: List of filtered documentation items
        """
        st.markdown(f"**Documentation Items ({len(items)}):**")
        
        # Create a container for the list
        for i, item in enumerate(items):
            status_config = self.STATUS_CONFIG.get(
                item.approval_status,
                self.STATUS_CONFIG['pending']
            )
            
            # Create a clickable item
            col1, col2, col3 = st.columns([3, 2, 1])
            
            with col1:
                # Element name and type
                st.markdown(f"**{item.element_name}** `({item.element_type})`")
            
            with col2:
                # File path
                st.caption(f"📄 {Path(item.file_path).name}")
            
            with col3:
                # Status badge
                if item.approval_status == 'approved':
                    st.success(status_config['label'], icon=status_config['icon'])
                elif item.approval_status == 'rejected':
                    st.error(status_config['label'], icon=status_config['icon'])
                elif item.approval_status == 'edited':
                    st.info(status_config['label'], icon=status_config['icon'])
                else:
                    st.warning(status_config['label'], icon=status_config['icon'])
            
            # Select button
            if st.button(
                "View Details",
                key=f"select_item_{i}",
                use_container_width=True,
                type="primary" if i == st.session_state.review_current_item_index else "secondary"
            ):
                st.session_state.review_current_item_index = i
                st.session_state.review_editing_item = None
                st.rerun()
            
            if i < len(items) - 1:
                st.divider()
    
    def _render_item_detail(self, item: DocumentationItem, session_id: str) -> None:
        """
        Render detailed view of a documentation item with side-by-side comparison.
        
        Args:
            item: Documentation item to display
            session_id: Documentation session ID
            
        Requirements: 5.2, 5.3, 5.4
        """
        st.markdown("### 📝 Documentation Detail")
        
        # Item header
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.markdown(f"**Element:** `{item.element_name}`")
        
        with col2:
            st.markdown(f"**Type:** `{item.element_type}`")
        
        with col3:
            st.markdown(f"**Language:** `{item.language}`")
        
        st.caption(f"📄 File: `{item.file_path}`")
        st.caption(f"🎯 Confidence: {item.confidence_score:.2f}")
        
        st.divider()
        
        # Get original code from the item
        # Note: We need to fetch the original code element to show the code
        # For now, we'll show a placeholder since we don't have direct access
        # In a real implementation, this would be passed through or fetched
        
        # Side-by-side view
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### 📄 Original Code")
            st.caption("The code element being documented")
            
            # Show code snippet (placeholder - would need actual code from CodeElement)
            st.code(
                f"# Code for {item.element_name}\n# (Full code would be displayed here)",
                language=item.language.lower()
            )
            
            # Show existing documentation if any
            st.markdown("#### 📚 Existing Documentation")
            if hasattr(item, 'existing_doc') and item.existing_doc:
                st.info(item.existing_doc)
            else:
                st.caption("_No existing documentation_")
        
        with col2:
            st.markdown("#### ✨ Generated Documentation")
            st.caption(f"Format: {item.format_type}")
            
            # Check if we're editing this item
            if st.session_state.review_editing_item == item.element_id:
                # Show edit mode
                self._render_edit_mode(item, session_id)
            else:
                # Show view mode
                doc_to_show = item.edited_doc if item.edited_doc else item.generated_doc
                st.code(doc_to_show, language=None)
                
                # Show edit indicator if edited
                if item.edited_doc:
                    st.info("✏️ This documentation has been edited")
        
        st.divider()
        
        # Action buttons
        self._render_action_buttons(item, session_id)
    
    def _render_edit_mode(self, item: DocumentationItem, session_id: str) -> None:
        """
        Render edit mode for documentation item.
        
        Args:
            item: Documentation item being edited
            session_id: Documentation session ID
            
        Requirements: 5.4
        """
        # Text area for editing
        doc_to_edit = item.edited_doc if item.edited_doc else item.generated_doc
        
        edited_text = st.text_area(
            "Edit Documentation",
            value=doc_to_edit,
            height=300,
            key=f"edit_text_{item.element_id}",
            help="Edit the generated documentation. Changes will be saved when you click 'Save Edit'."
        )
        
        # Save and cancel buttons
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("💾 Save Edit", key=f"save_edit_{item.element_id}", use_container_width=True, type="primary"):
                try:
                    # Update with edited documentation
                    self.review_manager.update_approval_status(
                        session_id=session_id,
                        element_id=item.element_id,
                        status='edited',
                        edited_doc=edited_text
                    )
                    st.session_state.review_editing_item = None
                    st.success("✅ Documentation updated successfully!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error saving edit: {str(e)}")
        
        with col2:
            if st.button("❌ Cancel", key=f"cancel_edit_{item.element_id}", use_container_width=True):
                st.session_state.review_editing_item = None
                st.rerun()
    
    def _render_action_buttons(self, item: DocumentationItem, session_id: str) -> None:
        """
        Render action buttons for approve, reject, and edit.
        
        Args:
            item: Documentation item
            session_id: Documentation session ID
            
        Requirements: 5.3, 5.4
        """
        st.markdown("**Actions:**")
        
        col1, col2, col3 = st.columns(3)
        
        # Only show action buttons if not currently editing
        if st.session_state.review_editing_item != item.element_id:
            with col1:
                if st.button(
                    "✅ Approve",
                    key=f"approve_{item.element_id}",
                    use_container_width=True,
                    type="primary",
                    disabled=item.approval_status == 'approved'
                ):
                    try:
                        self.review_manager.update_approval_status(
                            session_id=session_id,
                            element_id=item.element_id,
                            status='approved'
                        )
                        st.success("✅ Documentation approved!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error approving: {str(e)}")
            
            with col2:
                if st.button(
                    "❌ Reject",
                    key=f"reject_{item.element_id}",
                    use_container_width=True,
                    disabled=item.approval_status == 'rejected'
                ):
                    try:
                        self.review_manager.update_approval_status(
                            session_id=session_id,
                            element_id=item.element_id,
                            status='rejected'
                        )
                        st.warning("❌ Documentation rejected")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error rejecting: {str(e)}")
            
            with col3:
                if st.button(
                    "✏️ Edit",
                    key=f"edit_{item.element_id}",
                    use_container_width=True
                ):
                    st.session_state.review_editing_item = item.element_id
                    st.rerun()
        
        # Navigation buttons
        st.divider()
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        # Get current filtered items to know navigation bounds
        items = self.review_manager.get_items_for_review(
            session_id,
            filter_by=st.session_state.review_filters
        )
        
        with col1:
            if st.button(
                "⬅️ Previous",
                key="nav_previous",
                use_container_width=True,
                disabled=st.session_state.review_current_item_index == 0
            ):
                st.session_state.review_current_item_index -= 1
                st.session_state.review_editing_item = None
                st.rerun()
        
        with col2:
            st.caption(
                f"Item {st.session_state.review_current_item_index + 1} of {len(items)}"
            )
        
        with col3:
            if st.button(
                "Next ➡️",
                key="nav_next",
                use_container_width=True,
                disabled=st.session_state.review_current_item_index >= len(items) - 1
            ):
                st.session_state.review_current_item_index += 1
                st.session_state.review_editing_item = None
                st.rerun()
    
    def render_summary(self, session_id: str) -> None:
        """
        Render a summary of the review session.
        
        Args:
            session_id: Documentation session ID
        """
        st.subheader("📊 Review Summary")
        
        stats = self.review_manager.get_session_statistics(session_id)
        
        # Overall metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total Items", stats['total_items'])
        
        with col2:
            approved = stats['by_status'].get('approved', 0) + stats['by_status'].get('edited', 0)
            st.metric("Approved", approved)
        
        with col3:
            rejected = stats['by_status'].get('rejected', 0)
            st.metric("Rejected", rejected)
        
        with col4:
            pending = stats['by_status'].get('pending', 0)
            st.metric("Pending", pending)
        
        # Progress bar
        progress = stats['review_progress']
        st.progress(progress / 100.0, text=f"Review Progress: {progress:.1f}%")
        
        # Breakdown by language
        if stats['by_language']:
            st.divider()
            st.markdown("**Items by Language:**")
            
            for language, count in stats['by_language'].items():
                st.markdown(f"- **{language}:** {count} items")
        
        # Breakdown by type
        if stats['by_type']:
            st.divider()
            st.markdown("**Items by Type:**")
            
            for elem_type, count in stats['by_type'].items():
                st.markdown(f"- **{elem_type}:** {count} items")
    
    def get_export_ready_count(self, session_id: str) -> int:
        """
        Get count of items ready for export (approved or edited).
        
        Args:
            session_id: Documentation session ID
            
        Returns:
            Count of approved items
        """
        approved_items = self.review_manager.get_approved_items(session_id)
        return len(approved_items)
    
    def reset_review_state(self) -> None:
        """Reset review UI state."""
        st.session_state.review_current_item_index = 0
        st.session_state.review_filters = {}
        st.session_state.review_editing_item = None
    
    @staticmethod
    def create_quick_approve_all(review_manager: ReviewManager, session_id: str) -> None:
        """
        Render a quick action to approve all pending items.
        
        Args:
            review_manager: ReviewManager instance
            session_id: Documentation session ID
        """
        pending_items = review_manager.get_items_for_review(
            session_id,
            filter_by={'approval_status': 'pending'}
        )
        
        if pending_items:
            st.warning(f"⚠️ {len(pending_items)} items are still pending review")
            
            if st.button(
                f"✅ Approve All {len(pending_items)} Pending Items",
                key="quick_approve_all",
                help="Approve all pending documentation items at once"
            ):
                for item in pending_items:
                    try:
                        review_manager.update_approval_status(
                            session_id=session_id,
                            element_id=item.element_id,
                            status='approved'
                        )
                    except Exception as e:
                        st.error(f"Error approving {item.element_name}: {str(e)}")
                
                st.success(f"✅ Approved {len(pending_items)} items!")
                st.rerun()
