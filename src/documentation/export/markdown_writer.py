"""
Markdown Writer for markdown documentation export.

This module provides functionality to export generated documentation
as markdown files organized by module with proper formatting, table
of contents, and cross-references.
"""

import os
from typing import List, Dict, Set
from pathlib import Path
from collections import defaultdict

from src.models.documentation_models import DocumentationItem


class MarkdownWriter:
    """
    Writes documentation to markdown files.
    
    Organizes documentation by module with file-based structure,
    generates table of contents, and includes cross-references
    between related elements.
    """
    
    def __init__(self):
        """Initialize the MarkdownWriter."""
        pass
    
    def write_markdown_documentation(
        self,
        items: List[DocumentationItem],
        output_dir: str
    ) -> List[str]:
        """
        Generate markdown documentation files.
        
        Organizes documentation by module (file) with sections for each
        code element. Includes table of contents and cross-references.
        
        Args:
            items: List of documentation items to export
            output_dir: Directory where markdown files will be written
            
        Returns:
            List of generated markdown file paths
        """
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Group items by file path
        items_by_file = self._group_by_file(items)
        
        output_files = []
        
        # Generate index file
        index_path = self._generate_index(items_by_file, output_dir)
        output_files.append(index_path)
        
        # Generate a markdown file for each source file
        for file_path, file_items in items_by_file.items():
            try:
                markdown_path = self._generate_file_documentation(
                    file_path, file_items, output_dir, items
                )
                output_files.append(markdown_path)
            except Exception as e:
                print(f"Error generating markdown for {file_path}: {e}")
                continue
        
        return output_files

    def _group_by_file(
        self,
        items: List[DocumentationItem]
    ) -> Dict[str, List[DocumentationItem]]:
        """
        Group documentation items by file path.
        
        Args:
            items: List of documentation items
            
        Returns:
            Dictionary mapping file paths to lists of items
        """
        grouped = defaultdict(list)
        for item in items:
            grouped[item.file_path].append(item)
        
        # Sort items within each file by element name
        for file_path in grouped:
            grouped[file_path].sort(key=lambda x: (
                self._element_type_order(x.element_type),
                x.element_name
            ))
        
        return dict(grouped)
    
    def _element_type_order(self, element_type: str) -> int:
        """
        Get sort order for element types.
        
        Classes first, then functions, then methods.
        """
        order = {
            'class': 0,
            'function': 1,
            'method': 2,
            'module': 3
        }
        return order.get(element_type.lower(), 99)
    
    def _generate_index(
        self,
        items_by_file: Dict[str, List[DocumentationItem]],
        output_dir: str
    ) -> str:
        """
        Generate index.md file with overview and links to all modules.
        
        Args:
            items_by_file: Documentation items grouped by file
            output_dir: Output directory
            
        Returns:
            Path to generated index file
        """
        index_path = os.path.join(output_dir, 'index.md')
        
        # Calculate statistics
        total_elements = sum(len(items) for items in items_by_file.values())
        total_files = len(items_by_file)
        
        # Count by language and type
        lang_counts = defaultdict(int)
        type_counts = defaultdict(int)
        
        for items in items_by_file.values():
            for item in items:
                lang_counts[item.language] += 1
                type_counts[item.element_type] += 1
        
        # Build index content
        lines = [
            "# Documentation Index",
            "",
            "## Overview",
            "",
            f"This documentation covers **{total_elements}** code elements across **{total_files}** files.",
            "",
            "### Statistics",
            "",
            "**By Language:**",
            ""
        ]
        
        for lang, count in sorted(lang_counts.items()):
            lines.append(f"- {lang.capitalize()}: {count} elements")
        
        lines.extend([
            "",
            "**By Type:**",
            ""
        ])
        
        for elem_type, count in sorted(type_counts.items()):
            lines.append(f"- {elem_type.capitalize()}: {count} elements")
        
        lines.extend([
            "",
            "## Modules",
            "",
            "Click on a module to view its documentation:",
            ""
        ])
        
        # Add links to each module
        for file_path in sorted(items_by_file.keys()):
            items = items_by_file[file_path]
            module_name = self._get_module_name(file_path)
            markdown_filename = self._get_markdown_filename(file_path)
            
            # Count elements by type for this file
            file_type_counts = defaultdict(int)
            for item in items:
                file_type_counts[item.element_type] += 1
            
            type_summary = ", ".join(
                f"{count} {elem_type}{'s' if count > 1 else ''}"
                for elem_type, count in sorted(file_type_counts.items())
            )
            
            lines.append(f"- [{module_name}]({markdown_filename}) - {type_summary}")
        
        lines.append("")
        
        # Write index file
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return index_path
    
    def _generate_file_documentation(
        self,
        file_path: str,
        items: List[DocumentationItem],
        output_dir: str,
        all_items: List[DocumentationItem]
    ) -> str:
        """
        Generate markdown documentation for a single source file.
        
        Args:
            file_path: Path to the source file
            items: Documentation items for this file
            output_dir: Output directory
            all_items: All documentation items (for cross-references)
            
        Returns:
            Path to generated markdown file
        """
        markdown_filename = self._get_markdown_filename(file_path)
        markdown_path = os.path.join(output_dir, markdown_filename)
        
        module_name = self._get_module_name(file_path)
        
        lines = [
            f"# {module_name}",
            "",
            "## Metadata",
            "",
            f"- **File Path:** `{file_path}`",
            f"- **Language:** {items[0].language.capitalize() if items else 'Unknown'}",
            f"- **Elements:** {len(items)}",
            "",
            "## Table of Contents",
            ""
        ]
        
        # Generate table of contents
        for item in items:
            anchor = self._create_anchor(item.element_name, item.element_type)
            type_badge = self._get_type_badge(item.element_type)
            lines.append(f"- [{item.element_name}](#{anchor}) {type_badge}")
        
        lines.extend(["", "---", ""])
        
        # Generate documentation for each element
        for item in items:
            element_section = self._generate_element_section(item, all_items)
            lines.extend(element_section)
            lines.extend(["", "---", ""])
        
        # Write markdown file
        with open(markdown_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        return markdown_path
    
    def _generate_element_section(
        self,
        item: DocumentationItem,
        all_items: List[DocumentationItem]
    ) -> List[str]:
        """
        Generate markdown section for a single code element.
        
        Args:
            item: Documentation item
            all_items: All documentation items (for cross-references)
            
        Returns:
            List of markdown lines
        """
        anchor = self._create_anchor(item.element_name, item.element_type)
        type_badge = self._get_type_badge(item.element_type)
        
        lines = [
            f"## {item.element_name} {type_badge}",
            "",
            f"<a id=\"{anchor}\"></a>",
            "",
            "### Metadata",
            "",
            f"- **Type:** {item.element_type.capitalize()}",
            f"- **Language:** {item.language.capitalize()}",
            f"- **Format:** {item.format_type}",
            ""
        ]
        
        # Add documentation content
        lines.extend([
            "### Documentation",
            ""
        ])
        
        # Get the final documentation (prefer edited over generated)
        doc_content = item.edited_doc if item.edited_doc else item.generated_doc
        
        # Format the documentation based on language
        if item.language == 'python':
            lines.extend(self._format_python_doc_for_markdown(doc_content))
        else:  # javascript or typescript
            lines.extend(self._format_jsdoc_for_markdown(doc_content))
        
        # Add cross-references if any
        cross_refs = self._find_cross_references(item, all_items)
        if cross_refs:
            lines.extend([
                "",
                "### Related Elements",
                ""
            ])
            for ref in cross_refs:
                lines.append(f"- [{ref['name']}]({ref['link']}) - {ref['file']}")
        
        return lines
    
    def _format_python_doc_for_markdown(self, doc: str) -> List[str]:
        """
        Format Python docstring for markdown display.
        
        Args:
            doc: Python docstring content
            
        Returns:
            List of formatted markdown lines
        """
        # Remove triple quotes if present
        doc = doc.strip()
        if doc.startswith('"""') or doc.startswith("'''"):
            if doc.startswith('"""'):
                doc = doc[3:]
                if doc.endswith('"""'):
                    doc = doc[:-3]
            else:
                doc = doc[3:]
                if doc.endswith("'''"):
                    doc = doc[:-3]
        
        doc = doc.strip()
        
        # Split into lines and format
        lines = ["```python"]
        lines.append('"""')
        lines.extend(doc.split('\n'))
        lines.append('"""')
        lines.append("```")
        
        return lines
    
    def _format_jsdoc_for_markdown(self, doc: str) -> List[str]:
        """
        Format JSDoc comment for markdown display.
        
        Args:
            doc: JSDoc comment content
            
        Returns:
            List of formatted markdown lines
        """
        # Remove /** */ if present
        doc = doc.strip()
        if doc.startswith('/**'):
            doc = doc[3:]
        if doc.endswith('*/'):
            doc = doc[:-2]
        doc = doc.strip()
        
        # Split into lines and format
        lines = ["```javascript"]
        lines.append('/**')
        for line in doc.split('\n'):
            line = line.strip()
            if line.startswith('*'):
                lines.append(' ' + line)
            else:
                lines.append(' * ' + line)
        lines.append(' */')
        lines.append("```")
        
        return lines
    
    def _find_cross_references(
        self,
        item: DocumentationItem,
        all_items: List[DocumentationItem]
    ) -> List[Dict[str, str]]:
        """
        Find cross-references to other documented elements.
        
        Looks for mentions of other element names in the documentation.
        
        Args:
            item: Current documentation item
            all_items: All documentation items
            
        Returns:
            List of cross-reference dictionaries
        """
        cross_refs = []
        
        # Get the documentation content
        doc_content = item.edited_doc if item.edited_doc else item.generated_doc
        doc_lower = doc_content.lower()
        
        # Look for mentions of other elements
        for other_item in all_items:
            # Skip self
            if other_item.element_id == item.element_id:
                continue
            
            # Check if the other element is mentioned
            if other_item.element_name.lower() in doc_lower:
                markdown_filename = self._get_markdown_filename(other_item.file_path)
                anchor = self._create_anchor(other_item.element_name, other_item.element_type)
                
                cross_refs.append({
                    'name': other_item.element_name,
                    'link': f"{markdown_filename}#{anchor}",
                    'file': self._get_module_name(other_item.file_path)
                })
        
        return cross_refs
    
    def _get_module_name(self, file_path: str) -> str:
        """
        Get a readable module name from file path.
        
        Args:
            file_path: Path to source file
            
        Returns:
            Module name
        """
        # Convert path to module-like name
        path = Path(file_path)
        
        # Remove extension
        name = path.stem
        
        # Include parent directory if it's meaningful
        if path.parent.name and path.parent.name not in ['.', 'src', 'lib']:
            name = f"{path.parent.name}.{name}"
        
        return name
    
    def _get_markdown_filename(self, file_path: str) -> str:
        """
        Generate markdown filename from source file path.
        
        Args:
            file_path: Path to source file
            
        Returns:
            Markdown filename
        """
        # Convert file path to markdown filename
        path = Path(file_path)
        
        # Replace path separators with underscores
        safe_name = str(path).replace('/', '_').replace('\\', '_')
        
        # Remove extension and add .md
        safe_name = safe_name.rsplit('.', 1)[0] + '.md'
        
        return safe_name
    
    def _create_anchor(self, element_name: str, element_type: str) -> str:
        """
        Create URL-safe anchor for element.
        
        Args:
            element_name: Name of the element
            element_type: Type of the element
            
        Returns:
            URL-safe anchor string
        """
        # Convert to lowercase and replace special characters
        anchor = element_name.lower()
        anchor = anchor.replace('_', '-')
        anchor = ''.join(c if c.isalnum() or c == '-' else '' for c in anchor)
        
        return anchor
    
    def _get_type_badge(self, element_type: str) -> str:
        """
        Get a badge/emoji for element type.
        
        Args:
            element_type: Type of the element
            
        Returns:
            Badge string
        """
        badges = {
            'function': '`function`',
            'class': '`class`',
            'method': '`method`',
            'module': '`module`'
        }
        return badges.get(element_type.lower(), '`element`')
