"""
Export Module coordinator for documentation export.

This module provides the main ExportModule class that coordinates
format-specific writers (DocstringWriter, MarkdownWriter, HTMLWriter)
and handles the export workflow with error handling and timing.
"""

import time
from typing import List, Dict
from collections import defaultdict

from src.models.documentation_models import DocumentationItem, ExportResult
from src.documentation.export.docstring_writer import DocstringWriter
from src.documentation.export.markdown_writer import MarkdownWriter
from src.documentation.export.html_writer import HTMLWriter


class ExportModule:
    """
    Coordinates documentation export across multiple formats.
    
    Routes export requests to appropriate format-specific writers
    and provides unified error handling and result reporting.
    """
    
    def __init__(
        self,
        docstring_writer: DocstringWriter = None,
        markdown_writer: MarkdownWriter = None,
        html_writer: HTMLWriter = None
    ):
        """
        Initialize the ExportModule with format writers.
        
        Args:
            docstring_writer: Writer for inline documentation (optional)
            markdown_writer: Writer for markdown documentation (optional)
            html_writer: Writer for HTML documentation (optional)
        """
        self.docstring_writer = docstring_writer or DocstringWriter()
        self.markdown_writer = markdown_writer or MarkdownWriter()
        self.html_writer = html_writer or HTMLWriter()
    
    def export_documentation(
        self,
        items: List[DocumentationItem],
        export_format: str,
        output_path: str
    ) -> ExportResult:
        """
        Export documentation in specified format.
        
        Routes to the appropriate format-specific writer based on
        the export_format parameter. Handles errors gracefully and
        collects timing and count information.
        
        Args:
            items: List of documentation items to export
            export_format: Format type ('inline', 'markdown', 'html')
            output_path: Directory where documentation will be written
            
        Returns:
            ExportResult with file paths, counts, timing, and any errors
        """
        # Validate inputs
        if not items:
            return ExportResult(
                success=False,
                format_type=export_format,
                output_files=[],
                elements_exported=0,
                elements_by_language={},
                export_time_ms=0.0,
                errors=["No documentation items provided for export"]
            )
        
        if export_format not in ['inline', 'markdown', 'html']:
            return ExportResult(
                success=False,
                format_type=export_format,
                output_files=[],
                elements_exported=0,
                elements_by_language={},
                export_time_ms=0.0,
                errors=[f"Unsupported export format: {export_format}. "
                       f"Supported formats: 'inline', 'markdown', 'html'"]
            )
        
        # Start timing
        start_time = time.time()
        
        # Initialize result tracking
        output_files = []
        errors = []
        
        try:
            # Route to appropriate writer
            if export_format == 'inline':
                output_files = self._export_inline(items, output_path, errors)
            elif export_format == 'markdown':
                output_files = self._export_markdown(items, output_path, errors)
            elif export_format == 'html':
                output_files = self._export_html(items, output_path, errors)
        
        except Exception as e:
            errors.append(f"Unexpected error during {export_format} export: {str(e)}")
        
        # Calculate timing
        end_time = time.time()
        export_time_ms = (end_time - start_time) * 1000
        
        # Count elements by language
        elements_by_language = self._count_by_language(items)
        
        # Determine success
        success = len(output_files) > 0 and len(errors) == 0
        
        return ExportResult(
            success=success,
            format_type=export_format,
            output_files=output_files,
            elements_exported=len(items),
            elements_by_language=elements_by_language,
            export_time_ms=export_time_ms,
            errors=errors
        )
    
    def _export_inline(
        self,
        items: List[DocumentationItem],
        output_path: str,
        errors: List[str]
    ) -> List[str]:
        """
        Export documentation as inline docstrings/JSDoc.
        
        Args:
            items: Documentation items to export
            output_path: Output directory
            errors: List to collect error messages
            
        Returns:
            List of generated file paths
        """
        try:
            output_files = self.docstring_writer.write_inline_documentation(
                items, output_path
            )
            return output_files
        
        except Exception as e:
            errors.append(f"Error during inline export: {str(e)}")
            return []
    
    def _export_markdown(
        self,
        items: List[DocumentationItem],
        output_path: str,
        errors: List[str]
    ) -> List[str]:
        """
        Export documentation as markdown files.
        
        Args:
            items: Documentation items to export
            output_path: Output directory
            errors: List to collect error messages
            
        Returns:
            List of generated file paths
        """
        try:
            output_files = self.markdown_writer.write_markdown_documentation(
                items, output_path
            )
            return output_files
        
        except Exception as e:
            errors.append(f"Error during markdown export: {str(e)}")
            return []
    
    def _export_html(
        self,
        items: List[DocumentationItem],
        output_path: str,
        errors: List[str]
    ) -> List[str]:
        """
        Export documentation as HTML files.
        
        Args:
            items: Documentation items to export
            output_path: Output directory
            errors: List to collect error messages
            
        Returns:
            List of generated file paths
        """
        try:
            output_files = self.html_writer.write_html_documentation(
                items, output_path
            )
            return output_files
        
        except Exception as e:
            errors.append(f"Error during HTML export: {str(e)}")
            return []
    
    def _count_by_language(
        self,
        items: List[DocumentationItem]
    ) -> Dict[str, int]:
        """
        Count documentation items by language.
        
        Args:
            items: Documentation items
            
        Returns:
            Dictionary mapping language to count
        """
        counts = defaultdict(int)
        for item in items:
            counts[item.language] += 1
        return dict(counts)
