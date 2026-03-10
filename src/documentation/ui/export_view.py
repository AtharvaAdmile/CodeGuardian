"""
Export View UI Component for Documentation Generator.

This module provides a Streamlit interface for exporting approved documentation
in various formats (inline docstrings/JSDoc, markdown, HTML). Users can select
export format, configure output options, and view export results.

Requirements: 6.1, 6.6
"""

import streamlit as st
import os
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

from src.models.documentation_models import DocumentationItem, ExportResult
from src.documentation.export.export_module import ExportModule
from src.documentation.review_manager import ReviewManager


class ExportView:
    """
    Streamlit UI component for documentation export.
    
    Provides an interface for exporting approved documentation with format
    selection, output directory configuration, export options, and result
    display with download links.
    
    Requirements: 6.1, 6.6
    """
    
    # Export format configuration
    FORMAT_CONFIG = {
        'inline': {
            'name': 'Inline Docstrings/JSDoc',
            'icon': '📝',
            'description': 'Insert documentation directly into source code files',
            'file_extension': 'Source files (.py, .js, .ts)',
            'details': [
                'Python: Google-style docstrings after function/class definitions',
                'JavaScript/TypeScript: JSDoc comments before declarations',
                'Preserves original file formatting and structure',
                'Creates backup copies of original files'
            ]
        },
        'markdown': {
            'name': 'Markdown Documentation',
            'icon': '📄',
            'description': 'Generate markdown files organized by module',
            'file_extension': 'Markdown files (.md)',
            'details': [
                'Organized by module with file-based structure',
                'Table of contents with links to each element',
                'Syntax highlighting using markdown code blocks',
                'Cross-references between related elements',
                'Metadata headers (file path, language, element type)'
            ]
        },
        'html': {
            'name': 'HTML Documentation',
            'icon': '🌐',
            'description': 'Generate HTML documentation with navigation',
            'file_extension': 'HTML files (.html)',
            'details': [
                'Syntax highlighting using Pygments',
                'Navigation menu with file tree structure',
                'Index page with overview and statistics',
                'CSS styling for readable documentation',
                'Compatible with static site hosting'
            ]
        }
    }
    
    def __init__(
        self,
        export_module: ExportModule,
        review_manager: ReviewManager
    ):
        """
        Initialize the Export View.
        
        Args:
            export_module: ExportModule instance for handling exports
            review_manager: ReviewManager instance for accessing approved items
        """
        self.export_module = export_module
        self.review_manager = review_manager
        
        # Initialize session state for export
        if 'export_format' not in st.session_state:
            st.session_state.export_format = 'inline'
        
        if 'export_output_dir' not in st.session_state:
            st.session_state.export_output_dir = './docs/generated'
        
        if 'export_options' not in st.session_state:
            st.session_state.export_options = {
                'backup_files': True,
                'generate_index': True,
                'include_snippets': False
            }
        
        if 'export_result' not in st.session_state:
            st.session_state.export_result = None
        
        if 'export_in_progress' not in st.session_state:
            st.session_state.export_in_progress = False
    
    def render(self, session_id: str) -> Optional[ExportResult]:
        """
        Render the export interface.
        
        Displays format selection, output directory input, export options,
        export button, and results summary with download links.
        
        Args:
            session_id: Documentation session ID to export
            
        Returns:
            ExportResult if export was successful, None otherwise
            
        Requirements: 6.1, 6.6
        """
        st.subheader("📦 Export Documentation")
        
        # Get approved items count
        approved_items = self.review_manager.get_approved_items(session_id)
        approved_count = len(approved_items)
        
        if approved_count == 0:
            st.warning("⚠️ No approved documentation items to export. Please review and approve items first.")
            return None
        
        # Display export readiness
        st.success(f"✅ {approved_count} approved documentation items ready for export")
        
        st.divider()
        
        # Render format selection
        self._render_format_selection()
        
        st.divider()
        
        # Render output directory configuration
        self._render_output_directory()
        
        st.divider()
        
        # Render export options
        self._render_export_options()
        
        st.divider()
        
        # Render export button
        export_result = self._render_export_button(session_id, approved_items)
        
        # Render export results if available
        if st.session_state.export_result:
            st.divider()
            self._render_export_results(st.session_state.export_result)
        
        return export_result
    
    def _render_format_selection(self) -> None:
        """
        Render format selection radio buttons with descriptions.
        
        Requirements: 6.1
        """
        st.markdown("### 📋 Select Export Format")
        
        # Create radio buttons for format selection
        format_options = list(self.FORMAT_CONFIG.keys())
        format_labels = [
            f"{self.FORMAT_CONFIG[fmt]['icon']} {self.FORMAT_CONFIG[fmt]['name']}"
            for fmt in format_options
        ]
        
        selected_index = format_options.index(st.session_state.export_format)
        
        selected_format = st.radio(
            "Choose documentation format:",
            options=format_options,
            format_func=lambda x: f"{self.FORMAT_CONFIG[x]['icon']} {self.FORMAT_CONFIG[x]['name']}",
            index=selected_index,
            key='format_radio',
            help="Select the format for exporting your documentation"
        )
        
        # Update session state
        if selected_format != st.session_state.export_format:
            st.session_state.export_format = selected_format
            st.rerun()
        
        # Display format details
        format_info = self.FORMAT_CONFIG[st.session_state.export_format]
        
        st.info(f"**{format_info['description']}**")
        
        with st.expander("📖 Format Details", expanded=False):
            st.markdown(f"**Output:** {format_info['file_extension']}")
            st.markdown("**Features:**")
            for detail in format_info['details']:
                st.markdown(f"- {detail}")
    
    def _render_output_directory(self) -> None:
        """
        Render output directory input with file browser.
        
        Requirements: 6.1
        """
        st.markdown("### 📁 Output Directory")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            output_dir = st.text_input(
                "Output directory path:",
                value=st.session_state.export_output_dir,
                key='output_dir_input',
                help="Directory where documentation files will be saved"
            )
            
            # Update session state
            if output_dir != st.session_state.export_output_dir:
                st.session_state.export_output_dir = output_dir
        
        with col2:
            st.markdown("<br>", unsafe_allow_html=True)  # Spacing
            if st.button("📂 Browse", key='browse_button', help="Browse for directory"):
                st.info("💡 Tip: Enter the path directly in the text field")
        
        # Show current directory info
        output_path = Path(st.session_state.export_output_dir)
        
        if output_path.exists():
            st.success(f"✅ Directory exists: `{output_path.resolve()}`")
        else:
            st.info(f"📁 Directory will be created: `{output_path.resolve()}`")
        
        # Show format-specific output info
        format_info = self.FORMAT_CONFIG[st.session_state.export_format]
        st.caption(f"Output files: {format_info['file_extension']}")
    
    def _render_export_options(self) -> None:
        """
        Render export options checkboxes.
        
        Requirements: 6.1
        """
        st.markdown("### ⚙️ Export Options")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            backup_files = st.checkbox(
                "🔒 Backup original files",
                value=st.session_state.export_options['backup_files'],
                key='option_backup',
                help="Create backup copies before modifying files (inline format only)"
            )
        
        with col2:
            generate_index = st.checkbox(
                "📑 Generate index/TOC",
                value=st.session_state.export_options['generate_index'],
                key='option_index',
                help="Generate table of contents or index page"
            )
        
        with col3:
            include_snippets = st.checkbox(
                "💻 Include code snippets",
                value=st.session_state.export_options['include_snippets'],
                key='option_snippets',
                help="Include code snippets in documentation (markdown/HTML formats)"
            )
        
        # Update session state
        st.session_state.export_options = {
            'backup_files': backup_files,
            'generate_index': generate_index,
            'include_snippets': include_snippets
        }
        
        # Show format-specific option notes
        if st.session_state.export_format == 'inline':
            st.caption("💡 Backup files option is recommended for inline format")
        elif st.session_state.export_format in ['markdown', 'html']:
            st.caption("💡 Index and code snippets enhance documentation readability")
    
    def _render_export_button(
        self,
        session_id: str,
        approved_items: List[DocumentationItem]
    ) -> Optional[ExportResult]:
        """
        Render export button and handle export execution.
        
        Args:
            session_id: Documentation session ID
            approved_items: List of approved documentation items
            
        Returns:
            ExportResult if export was triggered and completed, None otherwise
            
        Requirements: 6.1, 6.6
        """
        st.markdown("### 🚀 Export Documentation")
        
        # Show export summary
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Items to Export", len(approved_items))
        
        with col2:
            # Count by language
            lang_counts = {}
            for item in approved_items:
                lang_counts[item.language] = lang_counts.get(item.language, 0) + 1
            
            lang_summary = ", ".join([f"{lang}: {count}" for lang, count in lang_counts.items()])
            st.caption(f"**By Language:** {lang_summary}")
        
        # Export button
        export_button = st.button(
            f"📦 Export as {self.FORMAT_CONFIG[st.session_state.export_format]['name']}",
            key='export_button',
            type='primary',
            use_container_width=True,
            disabled=st.session_state.export_in_progress
        )
        
        if export_button:
            return self._execute_export(approved_items)
        
        return None
    
    def _execute_export(
        self,
        approved_items: List[DocumentationItem]
    ) -> Optional[ExportResult]:
        """
        Execute the export operation.
        
        Args:
            approved_items: List of approved documentation items
            
        Returns:
            ExportResult with export details
        """
        # Set export in progress
        st.session_state.export_in_progress = True
        
        # Show progress
        with st.spinner(f"Exporting documentation as {st.session_state.export_format}..."):
            try:
                # Call export module
                result = self.export_module.export_documentation(
                    items=approved_items,
                    export_format=st.session_state.export_format,
                    output_path=st.session_state.export_output_dir
                )
                
                # Store result in session state
                st.session_state.export_result = result
                
                # Reset export in progress
                st.session_state.export_in_progress = False
                
                return result
            
            except Exception as e:
                st.session_state.export_in_progress = False
                st.error(f"❌ Export failed: {str(e)}")
                return None
    
    def _render_export_results(self, result: ExportResult) -> None:
        """
        Render export results summary with file paths and download links.
        
        Args:
            result: ExportResult from export operation
            
        Requirements: 6.6
        """
        st.markdown("### 📊 Export Results")
        
        if result.success:
            st.success("✅ Export completed successfully!")
        else:
            st.error("❌ Export completed with errors")
        
        # Display metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Elements Exported", result.elements_exported)
        
        with col2:
            st.metric("Files Generated", len(result.output_files))
        
        with col3:
            export_time_sec = result.export_time_ms / 1000.0
            st.metric("Export Time", f"{export_time_sec:.2f}s")
        
        # Show breakdown by language
        if result.elements_by_language:
            st.markdown("**Elements by Language:**")
            lang_cols = st.columns(len(result.elements_by_language))
            
            for i, (language, count) in enumerate(result.elements_by_language.items()):
                with lang_cols[i]:
                    st.metric(language, count)
        
        st.divider()
        
        # Show output files with download links
        if result.output_files:
            st.markdown("**Generated Files:**")
            
            for file_path in result.output_files:
                file_path_obj = Path(file_path)
                
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.code(str(file_path), language=None)
                
                with col2:
                    # Check if file exists and provide download
                    if file_path_obj.exists():
                        try:
                            with open(file_path, 'rb') as f:
                                file_data = f.read()
                            
                            st.download_button(
                                label="⬇️ Download",
                                data=file_data,
                                file_name=file_path_obj.name,
                                key=f"download_{file_path}",
                                use_container_width=True
                            )
                        except Exception as e:
                            st.caption(f"❌ Cannot read file")
                    else:
                        st.caption("❌ File not found")
        
        # Show errors if any
        if result.errors:
            st.divider()
            st.error(f"⚠️ {len(result.errors)} error(s) occurred during export")
            
            with st.expander("View Error Details", expanded=True):
                for i, error in enumerate(result.errors, 1):
                    st.markdown(f"**Error {i}:** {error}")
        
        # Show export summary
        st.divider()
        
        st.info(
            f"📁 Documentation exported to: `{Path(st.session_state.export_output_dir).resolve()}`"
        )
        
        # Action buttons
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Export Again", key='export_again', use_container_width=True):
                st.session_state.export_result = None
                st.rerun()
        
        with col2:
            if st.button("📂 Open Output Directory", key='open_dir', use_container_width=True):
                output_path = Path(st.session_state.export_output_dir).resolve()
                st.info(f"💡 Open this directory in your file browser:\n`{output_path}`")
    
    def render_compact(self, session_id: str) -> None:
        """
        Render a compact version of export interface.
        
        Useful for displaying in a sidebar or smaller space.
        
        Args:
            session_id: Documentation session ID
        """
        st.markdown("**📦 Export Documentation**")
        
        # Get approved items count
        approved_items = self.review_manager.get_approved_items(session_id)
        approved_count = len(approved_items)
        
        if approved_count == 0:
            st.caption("⚠️ No approved items")
            return
        
        st.caption(f"✅ {approved_count} items ready")
        
        # Format selection
        format_options = list(self.FORMAT_CONFIG.keys())
        selected_format = st.selectbox(
            "Format:",
            options=format_options,
            format_func=lambda x: self.FORMAT_CONFIG[x]['icon'] + " " + x.title(),
            index=format_options.index(st.session_state.export_format),
            key='compact_format'
        )
        
        st.session_state.export_format = selected_format
        
        # Quick export button
        if st.button("📦 Export", key='compact_export', use_container_width=True):
            self._execute_export(approved_items)
    
    def get_export_status(self) -> Dict[str, Any]:
        """
        Get current export status information.
        
        Returns:
            Dictionary with export status details
        """
        return {
            'format': st.session_state.export_format,
            'output_dir': st.session_state.export_output_dir,
            'options': st.session_state.export_options,
            'in_progress': st.session_state.export_in_progress,
            'last_result': st.session_state.export_result
        }
    
    def reset_export_state(self) -> None:
        """Reset export UI state."""
        st.session_state.export_format = 'inline'
        st.session_state.export_output_dir = './docs/generated'
        st.session_state.export_options = {
            'backup_files': True,
            'generate_index': True,
            'include_snippets': False
        }
        st.session_state.export_result = None
        st.session_state.export_in_progress = False
    
    @staticmethod
    def create_quick_export_button(
        export_module: ExportModule,
        review_manager: ReviewManager,
        session_id: str,
        export_format: str = 'inline'
    ) -> None:
        """
        Create a quick export button for immediate export.
        
        Args:
            export_module: ExportModule instance
            review_manager: ReviewManager instance
            session_id: Documentation session ID
            export_format: Export format to use (default: 'inline')
        """
        approved_items = review_manager.get_approved_items(session_id)
        
        if not approved_items:
            st.warning("⚠️ No approved items to export")
            return
        
        if st.button(
            f"⚡ Quick Export ({len(approved_items)} items)",
            key=f"quick_export_{export_format}",
            help=f"Export all approved items as {export_format}"
        ):
            with st.spinner(f"Exporting as {export_format}..."):
                try:
                    result = export_module.export_documentation(
                        items=approved_items,
                        export_format=export_format,
                        output_path='./docs/generated'
                    )
                    
                    if result.success:
                        st.success(f"✅ Exported {result.elements_exported} items!")
                        st.caption(f"📁 Output: {result.output_files[0] if result.output_files else 'N/A'}")
                    else:
                        st.error(f"❌ Export failed: {result.errors[0] if result.errors else 'Unknown error'}")
                
                except Exception as e:
                    st.error(f"❌ Export error: {str(e)}")
