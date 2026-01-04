"""
File Selector UI Component for Documentation Generator.

This module provides a Streamlit interface for selecting files to document.
Users can select individual files or entire directories, with filtering for
supported file extensions.

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
"""

import os
import streamlit as st
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass


@dataclass
class FileSelectionResult:
    """Result of file selection operation."""
    selected_files: List[str]
    files_by_language: Dict[str, int]
    estimated_time_minutes: float


class FileSelector:
    """
    Streamlit UI component for file selection.
    
    Provides an interface for users to select files for documentation generation,
    with support for individual file selection, directory selection, and filtering
    by supported file extensions.
    
    Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
    """
    
    # Supported file extensions by language
    SUPPORTED_EXTENSIONS = {
        'Python': ['.py'],
        'JavaScript': ['.js', '.jsx'],
        'TypeScript': ['.ts', '.tsx']
    }
    
    # Directories to exclude from file tree
    EXCLUDED_DIRS = {
        '__pycache__', 'node_modules', '.git', '.venv', 'venv',
        'env', '.env', 'dist', 'build', '.next', '.nuxt',
        'coverage', '.pytest_cache', '.mypy_cache', '.tox'
    }
    
    # Estimated processing time per file (in seconds)
    ESTIMATED_TIME_PER_FILE = 15
    
    def __init__(self, root_path: str = "."):
        """
        Initialize the File Selector.
        
        Args:
            root_path: Root directory path for file selection (default: current directory)
        """
        self.root_path = Path(root_path).resolve()
        
        # Initialize session state for file selection
        if 'selected_files' not in st.session_state:
            st.session_state.selected_files = set()
        
        if 'select_all_project' not in st.session_state:
            st.session_state.select_all_project = False
    
    def render(self) -> Optional[FileSelectionResult]:
        """
        Render the file selection interface.
        
        Displays a file tree with checkboxes for selection, "Select entire project"
        option, file count by language, and estimated processing time.
        
        Returns:
            FileSelectionResult if files are selected and confirmed, None otherwise
            
        Requirements: 1.1, 1.2, 1.3, 1.4, 1.5
        """
        st.subheader("📁 Select Files for Documentation")
        
        # Select entire project checkbox
        select_all = st.checkbox(
            "Select entire project",
            value=st.session_state.select_all_project,
            help="Select all supported files in the project directory"
        )
        
        # Update session state
        if select_all != st.session_state.select_all_project:
            st.session_state.select_all_project = select_all
            if select_all:
                # Select all supported files
                st.session_state.selected_files = self._get_all_supported_files()
            else:
                # Clear selection
                st.session_state.selected_files = set()
            st.rerun()
        
        st.divider()
        
        # Display file tree with selection
        st.markdown("**Project Files:**")
        
        # Get file tree
        file_tree = self._build_file_tree()
        
        # Render file tree
        self._render_file_tree(file_tree, self.root_path)
        
        st.divider()
        
        # Display selection summary
        selected_count = len(st.session_state.selected_files)
        
        if selected_count > 0:
            # Count files by language
            files_by_language = self._count_files_by_language(
                st.session_state.selected_files
            )
            
            # Calculate estimated time
            estimated_time = self._calculate_estimated_time(selected_count)
            
            # Display summary
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Selected Files", selected_count)
                
                # Show breakdown by language
                for language, count in files_by_language.items():
                    st.caption(f"  • {language}: {count}")
            
            with col2:
                st.metric("Estimated Time", f"~{estimated_time:.1f} min")
                st.caption("Processing time may vary based on file size and complexity")
            
            # Confirm selection button
            if st.button("✅ Confirm Selection", type="primary", use_container_width=True):
                return FileSelectionResult(
                    selected_files=sorted(list(st.session_state.selected_files)),
                    files_by_language=files_by_language,
                    estimated_time_minutes=estimated_time
                )
        else:
            st.info("👆 Select files from the tree above or use 'Select entire project'")
        
        return None
    
    def _build_file_tree(self) -> Dict:
        """
        Build a hierarchical file tree structure.
        
        Returns:
            Dictionary representing the file tree structure
        """
        tree = {}
        
        for file_path in self._get_all_supported_files():
            # Get relative path from root
            rel_path = Path(file_path).relative_to(self.root_path)
            parts = rel_path.parts
            
            # Navigate/create tree structure
            current = tree
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # Leaf node (file)
                    if '_files' not in current:
                        current['_files'] = []
                    current['_files'].append(str(file_path))
                else:
                    # Directory node
                    if part not in current:
                        current[part] = {}
                    current = current[part]
        
        return tree
    
    def _render_file_tree(
        self,
        tree: Dict,
        current_path: Path,
        level: int = 0,
        parent_key: str = ""
    ) -> None:
        """
        Recursively render the file tree with checkboxes.
        
        Args:
            tree: File tree dictionary
            current_path: Current directory path
            level: Indentation level
            parent_key: Parent key for unique widget keys
        """
        indent = "  " * level
        
        # Render directories first
        for key in sorted(tree.keys()):
            if key == '_files':
                continue
            
            # Directory
            dir_path = current_path / key if level > 0 else current_path
            unique_key = f"{parent_key}_{key}_{level}"
            
            # Use expander for directories
            with st.expander(f"📁 {key}", expanded=(level == 0)):
                self._render_file_tree(
                    tree[key],
                    dir_path / key,
                    level + 1,
                    unique_key
                )
        
        # Render files
        if '_files' in tree:
            for file_path in sorted(tree['_files']):
                file_name = Path(file_path).name
                unique_key = f"file_{file_path}"
                
                # Checkbox for file selection
                is_selected = file_path in st.session_state.selected_files
                
                # Create checkbox
                selected = st.checkbox(
                    f"📄 {file_name}",
                    value=is_selected,
                    key=unique_key,
                    disabled=st.session_state.select_all_project
                )
                
                # Update selection
                if selected and not is_selected:
                    st.session_state.selected_files.add(file_path)
                elif not selected and is_selected:
                    st.session_state.selected_files.discard(file_path)
    
    def _get_all_supported_files(self) -> Set[str]:
        """
        Get all supported files in the project directory.
        
        Returns:
            Set of file paths for all supported files
            
        Requirements: 1.2
        """
        supported_files = set()
        
        # Get all supported extensions
        all_extensions = []
        for extensions in self.SUPPORTED_EXTENSIONS.values():
            all_extensions.extend(extensions)
        
        # Walk through directory tree
        for root, dirs, files in os.walk(self.root_path):
            # Filter out excluded directories
            dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS]
            
            # Check each file
            for file in files:
                file_path = Path(root) / file
                
                # Check if file has supported extension
                if file_path.suffix in all_extensions:
                    supported_files.add(str(file_path))
        
        return supported_files
    
    def _count_files_by_language(self, file_paths: Set[str]) -> Dict[str, int]:
        """
        Count selected files by programming language.
        
        Args:
            file_paths: Set of selected file paths
        
        Returns:
            Dictionary mapping language name to file count
            
        Requirements: 1.5
        """
        counts = {}
        
        for file_path in file_paths:
            extension = Path(file_path).suffix
            
            # Find language for this extension
            for language, extensions in self.SUPPORTED_EXTENSIONS.items():
                if extension in extensions:
                    counts[language] = counts.get(language, 0) + 1
                    break
        
        return counts
    
    def _calculate_estimated_time(self, file_count: int) -> float:
        """
        Calculate estimated processing time in minutes.
        
        Args:
            file_count: Number of files to process
        
        Returns:
            Estimated time in minutes
            
        Requirements: 1.5
        """
        total_seconds = file_count * self.ESTIMATED_TIME_PER_FILE
        return total_seconds / 60.0
    
    def reset_selection(self) -> None:
        """Reset file selection state."""
        st.session_state.selected_files = set()
        st.session_state.select_all_project = False
    
    @staticmethod
    def get_language_from_extension(file_path: str) -> Optional[str]:
        """
        Get programming language from file extension.
        
        Args:
            file_path: Path to the file
        
        Returns:
            Language name or None if not supported
        """
        extension = Path(file_path).suffix
        
        for language, extensions in FileSelector.SUPPORTED_EXTENSIONS.items():
            if extension in extensions:
                return language
        
        return None
