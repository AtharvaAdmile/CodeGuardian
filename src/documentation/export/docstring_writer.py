"""
Docstring Writer for inline documentation export.

This module provides functionality to insert generated documentation
directly into source code files as inline docstrings (Python) or
JSDoc comments (JavaScript/TypeScript).
"""

import os
import re
import shutil
from typing import List, Dict, Optional
from pathlib import Path

from src.models.documentation_models import DocumentationItem


class DocstringWriter:
    """
    Writes inline documentation to source code files.
    
    Handles insertion of docstrings for Python and JSDoc comments for
    JavaScript/TypeScript while preserving original file structure and formatting.
    """
    
    def __init__(self, create_backups: bool = True):
        """
        Initialize the DocstringWriter.
        
        Args:
            create_backups: Whether to create backup copies of original files
        """
        self.create_backups = create_backups
    
    def write_inline_documentation(
        self,
        items: List[DocumentationItem],
        output_dir: str
    ) -> List[str]:
        """
        Generate source files with inline documentation.
        
        Groups documentation items by file and inserts documentation
        at appropriate locations while preserving file structure.
        
        Args:
            items: List of documentation items to export
            output_dir: Directory where documented files will be written
            
        Returns:
            List of generated file paths
        """
        # Group items by file path
        items_by_file = self._group_by_file(items)
        
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        output_files = []
        
        # Process each file
        for file_path, file_items in items_by_file.items():
            try:
                # Read original file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                
                # Create backup if requested
                if self.create_backups:
                    self._create_backup(file_path)
                
                # Determine language
                language = file_items[0].language if file_items else 'python'
                
                # Insert documentation based on language
                if language == 'python':
                    documented_content = self._insert_python_docstrings(
                        original_content, file_items
                    )
                else:  # javascript or typescript
                    documented_content = self._insert_jsdoc_comments(
                        original_content, file_items
                    )
                
                # Write to output directory
                output_path = self._get_output_path(file_path, output_dir)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(documented_content)
                
                output_files.append(output_path)
                
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                continue
        
        return output_files
    
    def _group_by_file(
        self,
        items: List[DocumentationItem]
    ) -> Dict[str, List[DocumentationItem]]:
        """Group documentation items by file path."""
        grouped = {}
        for item in items:
            if item.file_path not in grouped:
                grouped[item.file_path] = []
            grouped[item.file_path].append(item)
        
        # Sort items by start line (descending) to insert from bottom to top
        for file_path in grouped:
            grouped[file_path].sort(
                key=lambda x: self._extract_start_line(x.element_id),
                reverse=True
            )
        
        return grouped
    
    def _extract_start_line(self, element_id: str) -> int:
        """Extract start line number from element_id."""
        # element_id format: "file_path:start_line-end_line:element_name"
        try:
            parts = element_id.split(':')
            if len(parts) >= 2:
                line_range = parts[1]
                start_line = int(line_range.split('-')[0])
                return start_line
        except (ValueError, IndexError):
            pass
        return 0
    
    def _create_backup(self, file_path: str) -> None:
        """Create a backup copy of the original file."""
        backup_path = f"{file_path}.backup"
        try:
            shutil.copy2(file_path, backup_path)
        except Exception as e:
            print(f"Warning: Could not create backup for {file_path}: {e}")
    
    def _get_output_path(self, original_path: str, output_dir: str) -> str:
        """Generate output file path maintaining relative structure."""
        # Get just the filename
        filename = os.path.basename(original_path)
        return os.path.join(output_dir, filename)
    
    def _insert_python_docstrings(
        self,
        content: str,
        items: List[DocumentationItem]
    ) -> str:
        """
        Insert docstrings into Python code.
        
        Handles:
        - Functions and methods
        - Classes
        - Existing docstrings (replacement)
        - Decorators
        - Async functions
        """
        lines = content.split('\n')
        
        for item in items:
            # Get the documentation to insert (prefer edited over generated)
            doc = item.edited_doc if item.edited_doc else item.generated_doc
            
            # Extract start line from element_id
            start_line = self._extract_start_line(item.element_id) - 1  # 0-indexed
            
            if start_line < 0 or start_line >= len(lines):
                continue
            
            # Find the actual definition line (skip decorators)
            def_line_idx = self._find_python_definition_line(lines, start_line)
            
            if def_line_idx is None:
                continue
            
            # Get indentation from the definition line
            def_line = lines[def_line_idx]
            indent = self._get_indentation(def_line)
            
            # Check if there's an existing docstring to replace
            existing_doc_range = self._find_existing_python_docstring(
                lines, def_line_idx
            )
            
            # Format the docstring with proper indentation
            docstring_lines = self._format_python_docstring(doc, indent)
            
            # Insert or replace the docstring
            if existing_doc_range:
                # Replace existing docstring
                start_idx, end_idx = existing_doc_range
                lines[start_idx:end_idx + 1] = docstring_lines
            else:
                # Insert new docstring after definition line
                insert_idx = def_line_idx + 1
                for i, docstring_line in enumerate(docstring_lines):
                    lines.insert(insert_idx + i, docstring_line)
        
        return '\n'.join(lines)
    
    def _find_python_definition_line(
        self,
        lines: List[str],
        start_line: int
    ) -> Optional[int]:
        """
        Find the actual function/class definition line, skipping decorators.
        
        Args:
            lines: List of code lines
            start_line: Starting line to search from
            
        Returns:
            Index of the definition line, or None if not found
        """
        # Look for 'def' or 'class' keyword
        for i in range(start_line, min(start_line + 10, len(lines))):
            line = lines[i].strip()
            if line.startswith('def ') or line.startswith('async def ') or \
               line.startswith('class '):
                return i
        return None
    
    def _get_indentation(self, line: str) -> str:
        """Extract indentation from a line."""
        return line[:len(line) - len(line.lstrip())]
    
    def _find_existing_python_docstring(
        self,
        lines: List[str],
        def_line_idx: int
    ) -> Optional[tuple]:
        """
        Find existing docstring after a definition line.
        
        Returns:
            Tuple of (start_idx, end_idx) if docstring found, None otherwise
        """
        # Check the line after the definition
        if def_line_idx + 1 >= len(lines):
            return None
        
        next_line_idx = def_line_idx + 1
        next_line = lines[next_line_idx].strip()
        
        # Check for triple-quoted strings
        if next_line.startswith('"""') or next_line.startswith("'''"):
            quote = '"""' if next_line.startswith('"""') else "'''"
            
            # Check if it's a single-line docstring
            if next_line.count(quote) >= 2:
                return (next_line_idx, next_line_idx)
            
            # Multi-line docstring - find the end
            for i in range(next_line_idx + 1, len(lines)):
                if quote in lines[i]:
                    return (next_line_idx, i)
        
        return None
    
    def _format_python_docstring(self, doc: str, base_indent: str) -> List[str]:
        """
        Format a docstring with proper indentation.
        
        Args:
            doc: The docstring content
            base_indent: Base indentation to apply
            
        Returns:
            List of formatted docstring lines
        """
        # Add one level of indentation for docstring content
        doc_indent = base_indent + '    '
        
        # Remove existing quotes if present
        doc = doc.strip()
        if doc.startswith('"""') or doc.startswith("'''"):
            # Extract content between quotes
            if doc.startswith('"""'):
                doc = doc[3:]
                if doc.endswith('"""'):
                    doc = doc[:-3]
            else:
                doc = doc[3:]
                if doc.endswith("'''"):
                    doc = doc[:-3]
        
        doc = doc.strip()
        
        # Split into lines and apply indentation
        doc_lines = doc.split('\n')
        formatted_lines = [doc_indent + '"""']
        
        for line in doc_lines:
            if line.strip():
                formatted_lines.append(doc_indent + line)
            else:
                formatted_lines.append('')
        
        formatted_lines.append(doc_indent + '"""')
        
        return formatted_lines
    
    def _insert_jsdoc_comments(
        self,
        content: str,
        items: List[DocumentationItem]
    ) -> str:
        """
        Insert JSDoc comments into JavaScript/TypeScript code.
        
        Handles:
        - Functions
        - Classes
        - Methods
        - Existing JSDoc (replacement)
        """
        lines = content.split('\n')
        
        for item in items:
            # Get the documentation to insert (prefer edited over generated)
            doc = item.edited_doc if item.edited_doc else item.generated_doc
            
            # Extract start line from element_id
            start_line = self._extract_start_line(item.element_id) - 1  # 0-indexed
            
            if start_line < 0 or start_line >= len(lines):
                continue
            
            # Find the actual definition line
            def_line_idx = self._find_js_definition_line(lines, start_line)
            
            if def_line_idx is None:
                continue
            
            # Get indentation from the definition line
            def_line = lines[def_line_idx]
            indent = self._get_indentation(def_line)
            
            # Check if there's an existing JSDoc to replace
            existing_doc_range = self._find_existing_jsdoc(lines, def_line_idx)
            
            # Format the JSDoc with proper indentation
            jsdoc_lines = self._format_jsdoc(doc, indent)
            
            # Insert or replace the JSDoc
            if existing_doc_range:
                # Replace existing JSDoc
                start_idx, end_idx = existing_doc_range
                lines[start_idx:end_idx + 1] = jsdoc_lines
            else:
                # Insert new JSDoc before definition line
                for i, jsdoc_line in enumerate(jsdoc_lines):
                    lines.insert(def_line_idx + i, jsdoc_line)
        
        return '\n'.join(lines)
    
    def _find_js_definition_line(
        self,
        lines: List[str],
        start_line: int
    ) -> Optional[int]:
        """
        Find the function/class definition line in JavaScript/TypeScript.
        
        Args:
            lines: List of code lines
            start_line: Starting line to search from
            
        Returns:
            Index of the definition line, or None if not found
        """
        # Look for function or class keyword
        for i in range(start_line, min(start_line + 10, len(lines))):
            line = lines[i].strip()
            if 'function ' in line or 'class ' in line or \
               ('=>' in line and '(' in line):
                return i
        return start_line  # Fallback to start_line
    
    def _find_existing_jsdoc(
        self,
        lines: List[str],
        def_line_idx: int
    ) -> Optional[tuple]:
        """
        Find existing JSDoc comment before a definition line.
        
        Returns:
            Tuple of (start_idx, end_idx) if JSDoc found, None otherwise
        """
        # Look backwards for JSDoc comment
        for i in range(def_line_idx - 1, max(def_line_idx - 20, -1), -1):
            line = lines[i].strip()
            
            # Found end of JSDoc
            if line.endswith('*/'):
                # Find start of JSDoc
                for j in range(i, max(i - 50, -1), -1):
                    if lines[j].strip().startswith('/**'):
                        return (j, i)
            
            # Stop if we hit non-comment, non-empty line
            if line and not line.startswith('*') and not line.startswith('//'):
                break
        
        return None
    
    def _format_jsdoc(self, doc: str, indent: str) -> List[str]:
        """
        Format a JSDoc comment with proper indentation.
        
        Args:
            doc: The JSDoc content
            indent: Indentation to apply
            
        Returns:
            List of formatted JSDoc lines
        """
        # Remove existing /** */ if present
        doc = doc.strip()
        if doc.startswith('/**'):
            doc = doc[3:]
        if doc.endswith('*/'):
            doc = doc[:-2]
        doc = doc.strip()
        
        # Split into lines
        doc_lines = doc.split('\n')
        
        # Format with proper indentation
        formatted_lines = [indent + '/**']
        
        for line in doc_lines:
            line = line.strip()
            if line.startswith('*'):
                line = line[1:].strip()
            if line:
                formatted_lines.append(indent + ' * ' + line)
            else:
                formatted_lines.append(indent + ' *')
        
        formatted_lines.append(indent + ' */')
        
        return formatted_lines
