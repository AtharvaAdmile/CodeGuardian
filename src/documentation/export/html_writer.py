"""
HTML Writer for HTML documentation export.

This module provides functionality to export generated documentation
as static HTML files with syntax highlighting, navigation, and
responsive design suitable for static site hosting.
"""

import os
from typing import List, Dict
from pathlib import Path
from collections import defaultdict
from datetime import datetime

from jinja2 import Environment, BaseLoader, Template
from pygments import highlight
from pygments.lexers import get_lexer_by_name, PythonLexer, JavascriptLexer
from pygments.formatters import HtmlFormatter

from src.models.documentation_models import DocumentationItem


class HTMLWriter:
    """
    Writes documentation to HTML files.
    
    Generates static HTML documentation with syntax highlighting,
    navigation menu, and responsive design compatible with static
    site hosting.
    """
    
    def __init__(self):
        """Initialize the HTMLWriter with Jinja2 environment."""
        self.env = Environment(loader=BaseLoader())
        self.formatter = HtmlFormatter(style='monokai', cssclass='highlight')
        
        # Register custom filters
        self.env.filters['basename'] = lambda path: os.path.basename(path)
    
    def write_html_documentation(
        self,
        items: List[DocumentationItem],
        output_dir: str
    ) -> List[str]:
        """
        Generate HTML documentation files.
        
        Creates navigable HTML pages with syntax highlighting,
        file tree navigation, and an index page with statistics.
        
        Args:
            items: List of documentation items to export
            output_dir: Directory where HTML files will be written
            
        Returns:
            List of generated HTML file paths
        """
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        # Group items by file path
        items_by_file = self._group_by_file(items)
        
        output_files = []
        
        # Generate CSS file
        css_path = self._generate_css(output_dir)
        output_files.append(css_path)
        
        # Generate index page
        index_path = self._generate_index_page(items_by_file, output_dir)
        output_files.append(index_path)
        
        # Generate a page for each source file
        for file_path, file_items in items_by_file.items():
            try:
                html_path = self._generate_file_page(
                    file_path, file_items, items_by_file, output_dir
                )
                output_files.append(html_path)
            except Exception as e:
                print(f"Error generating HTML for {file_path}: {e}")
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
        
        # Sort items within each file
        for file_path in grouped:
            grouped[file_path].sort(key=lambda x: (
                self._element_type_order(x.element_type),
                x.element_name
            ))
        
        return dict(grouped)
    
    def _element_type_order(self, element_type: str) -> int:
        """Get sort order for element types."""
        order = {
            'class': 0,
            'function': 1,
            'method': 2,
            'module': 3
        }
        return order.get(element_type.lower(), 99)

    def _generate_css(self, output_dir: str) -> str:
        """
        Generate CSS file for HTML documentation.
        
        Args:
            output_dir: Output directory
            
        Returns:
            Path to generated CSS file
        """
        css_path = os.path.join(output_dir, 'styles.css')
        
        # Get Pygments CSS
        pygments_css = self.formatter.get_style_defs('.highlight')
        
        # Custom CSS for documentation
        custom_css = """
/* Base Styles */
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
}

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    line-height: 1.6;
    color: #333;
    background-color: #f5f5f5;
}

/* Layout */
.container {
    display: flex;
    min-height: 100vh;
}

/* Sidebar Navigation */
.sidebar {
    width: 280px;
    background-color: #2c3e50;
    color: #ecf0f1;
    padding: 20px;
    overflow-y: auto;
    position: fixed;
    height: 100vh;
}

.sidebar h1 {
    font-size: 1.5rem;
    margin-bottom: 20px;
    color: #3498db;
}

.sidebar nav ul {
    list-style: none;
}

.sidebar nav li {
    margin: 8px 0;
}

.sidebar nav a {
    color: #ecf0f1;
    text-decoration: none;
    display: block;
    padding: 8px 12px;
    border-radius: 4px;
    transition: background-color 0.2s;
}

.sidebar nav a:hover {
    background-color: #34495e;
}

.sidebar nav a.active {
    background-color: #3498db;
    font-weight: bold;
}

/* Main Content */
.main-content {
    flex: 1;
    margin-left: 280px;
    padding: 40px;
    max-width: 1200px;
}

/* Header */
.page-header {
    background-color: white;
    padding: 30px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 30px;
}

.page-header h1 {
    color: #2c3e50;
    font-size: 2.5rem;
    margin-bottom: 10px;
}

.page-header .metadata {
    color: #7f8c8d;
    font-size: 0.9rem;
}

.page-header .metadata span {
    margin-right: 20px;
}

/* Statistics Cards */
.stats-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 20px;
    margin-bottom: 30px;
}

.stat-card {
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    text-align: center;
}

.stat-card .stat-value {
    font-size: 2rem;
    font-weight: bold;
    color: #3498db;
    margin-bottom: 5px;
}

.stat-card .stat-label {
    color: #7f8c8d;
    font-size: 0.9rem;
}

/* File Tree */
.file-tree {
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 30px;
}

.file-tree h2 {
    color: #2c3e50;
    margin-bottom: 15px;
}

.file-tree ul {
    list-style: none;
}

.file-tree li {
    margin: 8px 0;
    padding-left: 20px;
}

.file-tree a {
    color: #3498db;
    text-decoration: none;
}

.file-tree a:hover {
    text-decoration: underline;
}

/* Table of Contents */
.toc {
    background-color: white;
    padding: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 30px;
}

.toc h2 {
    color: #2c3e50;
    margin-bottom: 15px;
}

.toc ul {
    list-style: none;
}

.toc li {
    margin: 8px 0;
}

.toc a {
    color: #3498db;
    text-decoration: none;
}

.toc a:hover {
    text-decoration: underline;
}

/* Element Sections */
.element {
    background-color: white;
    padding: 30px;
    border-radius: 8px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    margin-bottom: 30px;
}

.element-header {
    border-bottom: 2px solid #3498db;
    padding-bottom: 15px;
    margin-bottom: 20px;
}

.element-header h2 {
    color: #2c3e50;
    font-size: 1.8rem;
    display: inline-block;
}

.element-badge {
    display: inline-block;
    background-color: #3498db;
    color: white;
    padding: 4px 12px;
    border-radius: 4px;
    font-size: 0.8rem;
    margin-left: 10px;
    vertical-align: middle;
}

.element-badge.class {
    background-color: #9b59b6;
}

.element-badge.function {
    background-color: #3498db;
}

.element-badge.method {
    background-color: #1abc9c;
}

.element-metadata {
    color: #7f8c8d;
    font-size: 0.9rem;
    margin-top: 10px;
}

.element-metadata span {
    margin-right: 15px;
}

/* Documentation Content */
.documentation {
    margin: 20px 0;
}

.documentation h3 {
    color: #2c3e50;
    margin-bottom: 10px;
    font-size: 1.2rem;
}

.documentation pre {
    background-color: #272822;
    padding: 20px;
    border-radius: 4px;
    overflow-x: auto;
    margin: 15px 0;
}

.documentation code {
    font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
    font-size: 0.9rem;
}

/* Related Elements */
.related-elements {
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid #ecf0f1;
}

.related-elements h3 {
    color: #2c3e50;
    margin-bottom: 10px;
}

.related-elements ul {
    list-style: none;
}

.related-elements li {
    margin: 8px 0;
}

.related-elements a {
    color: #3498db;
    text-decoration: none;
}

.related-elements a:hover {
    text-decoration: underline;
}

/* Footer */
.footer {
    text-align: center;
    padding: 20px;
    color: #7f8c8d;
    font-size: 0.9rem;
    margin-top: 40px;
}

/* Responsive Design */
@media (max-width: 768px) {
    .sidebar {
        width: 100%;
        height: auto;
        position: relative;
    }
    
    .main-content {
        margin-left: 0;
        padding: 20px;
    }
    
    .container {
        flex-direction: column;
    }
}

/* Pygments Syntax Highlighting */
""" + pygments_css
        
        with open(css_path, 'w', encoding='utf-8') as f:
            f.write(custom_css)
        
        return css_path

    def _generate_index_page(
        self,
        items_by_file: Dict[str, List[DocumentationItem]],
        output_dir: str
    ) -> str:
        """
        Generate index.html page with overview and statistics.
        
        Args:
            items_by_file: Documentation items grouped by file
            output_dir: Output directory
            
        Returns:
            Path to generated index file
        """
        index_path = os.path.join(output_dir, 'index.html')
        
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
        
        # Build file tree data
        file_tree = []
        for file_path in sorted(items_by_file.keys()):
            items = items_by_file[file_path]
            html_filename = self._get_html_filename(file_path)
            
            # Count elements by type for this file
            file_type_counts = defaultdict(int)
            for item in items:
                file_type_counts[item.element_type] += 1
            
            type_summary = ", ".join(
                f"{count} {elem_type}{'s' if count > 1 else ''}"
                for elem_type, count in sorted(file_type_counts.items())
            )
            
            file_tree.append({
                'path': file_path,
                'link': html_filename,
                'summary': type_summary,
                'count': len(items)
            })
        
        # Generate HTML
        template = self._get_index_template()
        html_content = template.render(
            title="Documentation Index",
            total_elements=total_elements,
            total_files=total_files,
            lang_counts=sorted(lang_counts.items()),
            type_counts=sorted(type_counts.items()),
            file_tree=file_tree,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            all_files=sorted(items_by_file.keys())
        )
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return index_path
    
    def _generate_file_page(
        self,
        file_path: str,
        items: List[DocumentationItem],
        all_items_by_file: Dict[str, List[DocumentationItem]],
        output_dir: str
    ) -> str:
        """
        Generate HTML page for a single source file.
        
        Args:
            file_path: Path to the source file
            items: Documentation items for this file
            all_items_by_file: All items grouped by file (for navigation)
            output_dir: Output directory
            
        Returns:
            Path to generated HTML file
        """
        html_filename = self._get_html_filename(file_path)
        html_path = os.path.join(output_dir, html_filename)
        
        # Prepare element data
        elements_data = []
        for item in items:
            # Get the final documentation
            doc_content = item.edited_doc if item.edited_doc else item.generated_doc
            
            # Format documentation with syntax highlighting
            if item.language == 'python':
                formatted_doc = self._highlight_python_doc(doc_content)
            else:
                formatted_doc = self._highlight_jsdoc(doc_content)
            
            elements_data.append({
                'id': self._create_anchor(item.element_name),
                'name': item.element_name,
                'type': item.element_type,
                'language': item.language,
                'format_type': item.format_type,
                'documentation': formatted_doc,
                'confidence_score': item.confidence_score
            })
        
        # Generate HTML
        template = self._get_file_template()
        html_content = template.render(
            title=self._get_module_name(file_path),
            file_path=file_path,
            language=items[0].language.capitalize() if items else 'Unknown',
            element_count=len(items),
            elements=elements_data,
            all_files=sorted(all_items_by_file.keys()),
            current_file=file_path,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return html_path
    
    def _highlight_python_doc(self, doc: str) -> str:
        """
        Apply syntax highlighting to Python docstring.
        
        Args:
            doc: Python docstring content
            
        Returns:
            HTML with syntax highlighting
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
        
        # Wrap in triple quotes for highlighting
        code = f'"""\n{doc}\n"""'
        
        try:
            lexer = PythonLexer()
            return highlight(code, lexer, self.formatter)
        except Exception:
            return f'<pre><code>{code}</code></pre>'
    
    def _highlight_jsdoc(self, doc: str) -> str:
        """
        Apply syntax highlighting to JSDoc comment.
        
        Args:
            doc: JSDoc comment content
            
        Returns:
            HTML with syntax highlighting
        """
        # Remove /** */ if present
        doc = doc.strip()
        if doc.startswith('/**'):
            doc = doc[3:]
        if doc.endswith('*/'):
            doc = doc[:-2]
        doc = doc.strip()
        
        # Reconstruct JSDoc
        lines = ['/**']
        for line in doc.split('\n'):
            line = line.strip()
            if line.startswith('*'):
                lines.append(' ' + line)
            else:
                lines.append(' * ' + line)
        lines.append(' */')
        
        code = '\n'.join(lines)
        
        try:
            lexer = JavascriptLexer()
            return highlight(code, lexer, self.formatter)
        except Exception:
            return f'<pre><code>{code}</code></pre>'

    def _get_index_template(self) -> Template:
        """
        Get Jinja2 template for index page.
        
        Returns:
            Jinja2 Template object
        """
        template_str = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div class="container">
        <aside class="sidebar">
            <h1>📚 Documentation</h1>
            <nav>
                <ul>
                    <li><a href="index.html" class="active">Home</a></li>
                    {% for file_path in all_files %}
                    <li><a href="{{ file_path | replace('/', '_') | replace('\\\\', '_') | replace('.py', '.html') | replace('.js', '.html') | replace('.ts', '.html') | replace('.jsx', '.html') | replace('.tsx', '.html') }}">{{ file_path | basename }}</a></li>
                    {% endfor %}
                </ul>
            </nav>
        </aside>
        
        <main class="main-content">
            <div class="page-header">
                <h1>{{ title }}</h1>
                <div class="metadata">
                    <span>📅 Generated: {{ generated_at }}</span>
                </div>
            </div>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{{ total_elements }}</div>
                    <div class="stat-label">Total Elements</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{{ total_files }}</div>
                    <div class="stat-label">Files Documented</div>
                </div>
                {% for lang, count in lang_counts %}
                <div class="stat-card">
                    <div class="stat-value">{{ count }}</div>
                    <div class="stat-label">{{ lang | capitalize }} Elements</div>
                </div>
                {% endfor %}
            </div>
            
            <div class="file-tree">
                <h2>📁 Documented Files</h2>
                <ul>
                    {% for file in file_tree %}
                    <li>
                        <a href="{{ file.link }}">{{ file.path }}</a>
                        <span style="color: #7f8c8d; font-size: 0.9rem;"> - {{ file.summary }} ({{ file.count }} total)</span>
                    </li>
                    {% endfor %}
                </ul>
            </div>
            
            <div class="toc">
                <h2>📊 Statistics by Type</h2>
                <ul>
                    {% for elem_type, count in type_counts %}
                    <li>{{ elem_type | capitalize }}: <strong>{{ count }}</strong> elements</li>
                    {% endfor %}
                </ul>
            </div>
            
            <div class="footer">
                Generated by Smart Code Documentation Generator
            </div>
        </main>
    </div>
</body>
</html>"""
        
        template = self.env.from_string(template_str)
        return template
    
    def _get_file_template(self) -> Template:
        """
        Get Jinja2 template for file documentation page.
        
        Returns:
            Jinja2 Template object
        """
        template_str = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <div class="container">
        <aside class="sidebar">
            <h1>📚 Documentation</h1>
            <nav>
                <ul>
                    <li><a href="index.html">Home</a></li>
                    {% for file_path in all_files %}
                    <li><a href="{{ file_path | replace('/', '_') | replace('\\\\', '_') | replace('.py', '.html') | replace('.js', '.html') | replace('.ts', '.html') | replace('.jsx', '.html') | replace('.tsx', '.html') }}" {% if file_path == current_file %}class="active"{% endif %}>{{ file_path | basename }}</a></li>
                    {% endfor %}
                </ul>
            </nav>
        </aside>
        
        <main class="main-content">
            <div class="page-header">
                <h1>{{ title }}</h1>
                <div class="metadata">
                    <span>📄 File: <code>{{ file_path }}</code></span>
                    <span>💬 Language: {{ language }}</span>
                    <span>📦 Elements: {{ element_count }}</span>
                    <span>📅 Generated: {{ generated_at }}</span>
                </div>
            </div>
            
            <div class="toc">
                <h2>📑 Table of Contents</h2>
                <ul>
                    {% for element in elements %}
                    <li>
                        <a href="#{{ element.id }}">{{ element.name }}</a>
                        <span class="element-badge {{ element.type }}">{{ element.type }}</span>
                    </li>
                    {% endfor %}
                </ul>
            </div>
            
            {% for element in elements %}
            <div class="element" id="{{ element.id }}">
                <div class="element-header">
                    <h2>{{ element.name }}</h2>
                    <span class="element-badge {{ element.type }}">{{ element.type }}</span>
                    <div class="element-metadata">
                        <span>Type: {{ element.type | capitalize }}</span>
                        <span>Language: {{ element.language | capitalize }}</span>
                        <span>Format: {{ element.format_type }}</span>
                        <span>Confidence: {{ "%.1f" | format(element.confidence_score * 100) }}%</span>
                    </div>
                </div>
                
                <div class="documentation">
                    <h3>📝 Documentation</h3>
                    {{ element.documentation | safe }}
                </div>
            </div>
            {% endfor %}
            
            <div class="footer">
                Generated by Smart Code Documentation Generator
            </div>
        </main>
    </div>
</body>
</html>"""
        
        template = self.env.from_string(template_str)
        return template
    
    def _get_module_name(self, file_path: str) -> str:
        """
        Get a readable module name from file path.
        
        Args:
            file_path: Path to source file
            
        Returns:
            Module name
        """
        path = Path(file_path)
        name = path.stem
        
        # Include parent directory if meaningful
        if path.parent.name and path.parent.name not in ['.', 'src', 'lib']:
            name = f"{path.parent.name}.{name}"
        
        return name
    
    def _get_html_filename(self, file_path: str) -> str:
        """
        Generate HTML filename from source file path.
        
        Args:
            file_path: Path to source file
            
        Returns:
            HTML filename
        """
        # Convert file path to HTML filename
        path = Path(file_path)
        
        # Replace path separators with underscores
        safe_name = str(path).replace('/', '_').replace('\\', '_')
        
        # Remove extension and add .html
        safe_name = safe_name.rsplit('.', 1)[0] + '.html'
        
        return safe_name
    
    def _create_anchor(self, element_name: str) -> str:
        """
        Create URL-safe anchor for element.
        
        Args:
            element_name: Name of the element
            
        Returns:
            URL-safe anchor string
        """
        # Convert to lowercase and replace special characters
        anchor = element_name.lower()
        anchor = anchor.replace('_', '-')
        anchor = ''.join(c if c.isalnum() or c == '-' else '' for c in anchor)
        
        return anchor
