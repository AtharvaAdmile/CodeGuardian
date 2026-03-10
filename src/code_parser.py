"""
CodeParser module for parsing Python and JavaScript/TypeScript code.
"""

import ast
import re
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class CodeBlock:
    """Represents a code block (function, class, or method)."""
    content: str
    start_line: int
    end_line: int
    block_type: str  # 'function', 'class', 'method'
    name: str
    parent_class: Optional[str] = None


@dataclass
class ParsedCode:
    """Result of parsing a code file."""
    file_path: str
    language: str
    content: str
    functions: List[CodeBlock]
    classes: List[CodeBlock]
    total_lines: int


class CodeParser:
    """
    Parses source code files to extract structural information.
    
    Supports Python (using AST) and JavaScript/TypeScript (using regex).
    Falls back to line-based parsing if AST parsing fails.
    """
    
    def parse_file(self, file_path: str, content: str) -> ParsedCode:
        """
        Parse a source code file and extract structural information.
        
        Args:
            file_path: Path to the file being parsed
            content: Content of the file as a string
            
        Returns:
            ParsedCode object containing parsed information
        """
        # Determine language from file extension
        language = self._detect_language(file_path)
        total_lines = len(content.splitlines())
        
        # Parse based on language
        if language == 'python':
            try:
                functions, classes = self._parse_python(content)
            except Exception:
                # Fallback to line-based parsing
                functions, classes = self._fallback_parse(content, language)
        elif language in ['javascript', 'typescript']:
            functions, classes = self._parse_javascript(content)
        else:
            functions, classes = [], []
        
        return ParsedCode(
            file_path=file_path,
            language=language,
            content=content,
            functions=functions,
            classes=classes,
            total_lines=total_lines
        )
    
    def extract_functions(self, parsed: ParsedCode) -> List[CodeBlock]:
        """
        Extract all function blocks from parsed code.
        
        Args:
            parsed: ParsedCode object
            
        Returns:
            List of CodeBlock objects representing functions
        """
        return parsed.functions
    
    def extract_classes(self, parsed: ParsedCode) -> List[CodeBlock]:
        """
        Extract all class blocks from parsed code.
        
        Args:
            parsed: ParsedCode object
            
        Returns:
            List of CodeBlock objects representing classes
        """
        return parsed.classes
    
    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        extension = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''
        
        if extension == 'py':
            return 'python'
        elif extension in ['js', 'jsx']:
            return 'javascript'
        elif extension in ['ts', 'tsx']:
            return 'typescript'
        else:
            return 'unknown'
    
    def _parse_python(self, content: str) -> tuple[List[CodeBlock], List[CodeBlock]]:
        """
        Parse Python code using AST.
        
        Args:
            content: Python source code
            
        Returns:
            Tuple of (functions, classes)
        """
        functions = []
        classes = []
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            # If parsing fails, return empty lists
            return functions, classes
        
        lines = content.splitlines()
        
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Check if it's a method (inside a class)
                parent_class = self._find_parent_class(node, tree)
                
                start_line = node.lineno
                end_line = node.end_lineno if node.end_lineno else start_line
                
                # Extract function content
                func_content = '\n'.join(lines[start_line - 1:end_line])
                
                block = CodeBlock(
                    content=func_content,
                    start_line=start_line,
                    end_line=end_line,
                    block_type='method' if parent_class else 'function',
                    name=node.name,
                    parent_class=parent_class
                )
                
                functions.append(block)
            
            elif isinstance(node, ast.ClassDef):
                start_line = node.lineno
                end_line = node.end_lineno if node.end_lineno else start_line
                
                # Extract class content
                class_content = '\n'.join(lines[start_line - 1:end_line])
                
                block = CodeBlock(
                    content=class_content,
                    start_line=start_line,
                    end_line=end_line,
                    block_type='class',
                    name=node.name,
                    parent_class=None
                )
                
                classes.append(block)
        
        return functions, classes
    
    def _find_parent_class(self, func_node: ast.FunctionDef, tree: ast.AST) -> Optional[str]:
        """Find the parent class of a function node, if any."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if item == func_node:
                        return node.name
        return None

    def _parse_javascript(self, content: str) -> tuple[List[CodeBlock], List[CodeBlock]]:
        """
        Parse JavaScript/TypeScript code using regex patterns.
        
        Args:
            content: JavaScript/TypeScript source code
            
        Returns:
            Tuple of (functions, classes)
        """
        functions = []
        classes = []
        lines = content.splitlines()
        
        # Pattern for function declarations and expressions
        # Matches: function name(), const name = function(), const name = () =>
        func_patterns = [
            r'^\s*function\s+(\w+)\s*\(',  # function name()
            r'^\s*const\s+(\w+)\s*=\s*function\s*\(',  # const name = function()
            r'^\s*const\s+(\w+)\s*=\s*\([^)]*\)\s*=>',  # const name = () =>
            r'^\s*let\s+(\w+)\s*=\s*function\s*\(',  # let name = function()
            r'^\s*let\s+(\w+)\s*=\s*\([^)]*\)\s*=>',  # let name = () =>
            r'^\s*var\s+(\w+)\s*=\s*function\s*\(',  # var name = function()
            r'^\s*async\s+function\s+(\w+)\s*\(',  # async function name()
        ]
        
        # Pattern for class declarations
        class_pattern = r'^\s*class\s+(\w+)'
        
        # Pattern for method declarations inside classes
        method_pattern = r'^\s*(\w+)\s*\([^)]*\)\s*\{'
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Check for class declaration
            class_match = re.match(class_pattern, line)
            if class_match:
                class_name = class_match.group(1)
                start_line = i + 1
                end_line = self._find_closing_brace(lines, i)
                
                if end_line > start_line:
                    class_content = '\n'.join(lines[i:end_line])
                    classes.append(CodeBlock(
                        content=class_content,
                        start_line=start_line,
                        end_line=end_line,
                        block_type='class',
                        name=class_name,
                        parent_class=None
                    ))
                    i = end_line
                    continue
            
            # Check for function declarations
            for pattern in func_patterns:
                func_match = re.match(pattern, line)
                if func_match:
                    func_name = func_match.group(1)
                    start_line = i + 1
                    end_line = self._find_closing_brace(lines, i)
                    
                    if end_line > start_line:
                        func_content = '\n'.join(lines[i:end_line])
                        functions.append(CodeBlock(
                            content=func_content,
                            start_line=start_line,
                            end_line=end_line,
                            block_type='function',
                            name=func_name,
                            parent_class=None
                        ))
                        i = end_line
                        break
            
            i += 1
        
        return functions, classes
    
    def _find_closing_brace(self, lines: List[str], start_idx: int) -> int:
        """
        Find the closing brace for a code block starting at start_idx.
        
        Args:
            lines: List of code lines
            start_idx: Index of the line where the block starts
            
        Returns:
            Index of the line with the closing brace
        """
        brace_count = 0
        found_opening = False
        
        for i in range(start_idx, len(lines)):
            line = lines[i]
            
            # Count braces
            for char in line:
                if char == '{':
                    brace_count += 1
                    found_opening = True
                elif char == '}':
                    brace_count -= 1
                    
                    # Found matching closing brace
                    if found_opening and brace_count == 0:
                        return i + 1
        
        # If no closing brace found, return end of file
        return len(lines)
    
    def _fallback_parse(self, content: str, language: str) -> tuple[List[CodeBlock], List[CodeBlock]]:
        """
        Fallback line-based parsing when AST parsing fails.
        
        Creates simple blocks based on line ranges.
        
        Args:
            content: Source code content
            language: Programming language
            
        Returns:
            Tuple of (functions, classes) - both empty for fallback
        """
        # For fallback, we don't extract specific functions/classes
        # The chunker will handle line-based chunking
        return [], []
