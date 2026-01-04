"""
Analysis Agent for identifying documentation gaps in code.

This module provides the AnalysisAgent class that analyzes Python and
JavaScript/TypeScript files to identify code elements that need documentation.
"""

import ast
import re
import uuid
from typing import List, Optional, Callable, Dict, Tuple
from pathlib import Path

from src.code_parser import CodeParser, ParsedCode, CodeBlock
from src.documentation.gap_detector import GapDetector
from src.models.documentation_models import (
    CodeElement,
    Parameter,
    FileAnalysis,
    GapReport
)


class AnalysisAgent:
    """
    Analyzes code files to identify documentation gaps.
    
    The AnalysisAgent uses the CodeParser to extract code structure and the
    GapDetector to evaluate documentation quality, generating comprehensive
    gap reports for documentation generation.
    """
    
    def __init__(
        self,
        code_parser: CodeParser,
        gap_detector: GapDetector
    ):
        """
        Initialize the Analysis Agent.
        
        Args:
            code_parser: CodeParser instance for parsing source files
            gap_detector: GapDetector instance for evaluating documentation quality
        """
        self.code_parser = code_parser
        self.gap_detector = gap_detector
    
    def analyze_files(
        self,
        file_paths: List[str],
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> GapReport:
        """
        Analyze multiple files and generate a documentation gap report.
        
        Processes each file to extract code elements, evaluate existing
        documentation, and identify gaps based on quality scores.
        
        Args:
            file_paths: List of file paths to analyze
            progress_callback: Optional callback function called with
                             (current_index, total_files, current_file_path)
                             
        Returns:
            GapReport containing all analyzed elements and gap statistics
        """
        file_analyses = []
        total_files = len(file_paths)
        
        for idx, file_path in enumerate(file_paths):
            # Call progress callback if provided
            if progress_callback:
                progress_callback(idx + 1, total_files, file_path)
            
            try:
                # Read file content
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Analyze the file
                file_analysis = self.analyze_single_file(file_path, content)
                file_analyses.append(file_analysis)
                
            except Exception as e:
                # Log error but continue with other files
                print(f"Error analyzing {file_path}: {str(e)}")
                continue
        
        # Generate gap report from all file analyses
        return self._generate_gap_report(file_analyses)
    
    def analyze_single_file(
        self,
        file_path: str,
        content: str
    ) -> FileAnalysis:
        """
        Analyze a single file and return analysis results.
        
        Parses the file, extracts code elements, evaluates documentation
        quality, and identifies gaps.
        
        Args:
            file_path: Path to the file being analyzed
            content: Content of the file as a string
            
        Returns:
            FileAnalysis object containing all code elements and metadata
        """
        # Parse the file using CodeParser
        parsed = self.code_parser.parse_file(file_path, content)
        
        # Extract code elements from parsed result
        code_elements = []
        
        # Process functions
        for func_block in parsed.functions:
            element = self._create_code_element_from_block(
                func_block,
                file_path,
                parsed.language,
                content
            )
            code_elements.append(element)
        
        # Process classes
        for class_block in parsed.classes:
            element = self._create_code_element_from_block(
                class_block,
                file_path,
                parsed.language,
                content
            )
            code_elements.append(element)
        
        return FileAnalysis(
            file_path=file_path,
            language=parsed.language,
            code_elements=code_elements,
            total_lines=parsed.total_lines
        )
    
    def _create_code_element_from_block(
        self,
        block: CodeBlock,
        file_path: str,
        language: str,
        full_content: str
    ) -> CodeElement:
        """
        Create a CodeElement from a CodeBlock with enhanced metadata.
        
        Extracts parameters, return types, and existing documentation,
        then calculates quality score and gap status.
        
        Args:
            block: CodeBlock from parser
            file_path: Path to the source file
            language: Programming language
            full_content: Full file content for context
            
        Returns:
            CodeElement with complete metadata
        """
        # Generate unique element ID
        element_id = str(uuid.uuid4())
        
        # Extract existing documentation
        existing_doc = self._extract_existing_documentation(
            block.content,
            language,
            block.block_type
        )
        
        # Extract parameters and return type
        parameters, return_type = self._extract_signature_info(
            block.content,
            language,
            block.block_type
        )
        
        # Create CodeElement
        element = CodeElement(
            element_id=element_id,
            name=block.name,
            element_type=block.block_type,
            file_path=file_path,
            start_line=block.start_line,
            end_line=block.end_line,
            language=language,
            code_content=block.content,
            existing_doc=existing_doc,
            parent_class=block.parent_class,
            parameters=parameters,
            return_type=return_type
        )
        
        # Calculate quality score
        element.quality_score = self.gap_detector.calculate_quality_score(element)
        
        # Determine if there's a gap
        element.has_gap = self.gap_detector.has_documentation_gap(element.quality_score)
        
        return element
    
    def _extract_existing_documentation(
        self,
        code_content: str,
        language: str,
        element_type: str
    ) -> Optional[str]:
        """
        Extract existing documentation from code content.
        
        For Python: Extracts docstrings
        For JavaScript/TypeScript: Extracts JSDoc comments
        
        Args:
            code_content: The code content to search
            language: Programming language
            element_type: Type of code element
            
        Returns:
            Existing documentation string or None
        """
        if language.lower() == "python":
            return self._extract_python_docstring(code_content)
        elif language.lower() in ["javascript", "typescript"]:
            return self._extract_jsdoc(code_content)
        return None
    
    def _extract_python_docstring(self, code_content: str) -> Optional[str]:
        """
        Extract docstring from Python code.
        
        Handles triple-quoted strings that appear immediately
        after function/class definition.
        
        Args:
            code_content: Python code content
            
        Returns:
            Docstring text or None
        """
        try:
            tree = ast.parse(code_content)
            
            # Get the first node (should be function or class)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                    docstring = ast.get_docstring(node)
                    return docstring
                    
        except SyntaxError:
            # Fallback to regex if AST parsing fails
            pass
        
        # Regex fallback for docstrings
        docstring_pattern = r'(?:def|class)\s+\w+[^:]*:\s*(?:"""(.*?)"""|\'\'\'(.*?)\'\'\')'
        match = re.search(docstring_pattern, code_content, re.DOTALL)
        if match:
            return match.group(1) or match.group(2)
        
        return None
    
    def _extract_jsdoc(self, code_content: str) -> Optional[str]:
        """
        Extract JSDoc comment from JavaScript/TypeScript code.
        
        Looks for /** ... */ comments before function/class declarations.
        
        Args:
            code_content: JavaScript/TypeScript code content
            
        Returns:
            JSDoc comment text or None
        """
        # Pattern for JSDoc comments
        jsdoc_pattern = r'/\*\*(.*?)\*/'
        match = re.search(jsdoc_pattern, code_content, re.DOTALL)
        if match:
            return match.group(0)  # Return full comment including markers
        return None
    
    def _extract_signature_info(
        self,
        code_content: str,
        language: str,
        element_type: str
    ) -> Tuple[List[Parameter], Optional[str]]:
        """
        Extract parameters and return type from code signature.
        
        Args:
            code_content: Code content to analyze
            language: Programming language
            element_type: Type of code element
            
        Returns:
            Tuple of (parameters list, return_type string)
        """
        if language.lower() == "python":
            return self._extract_python_signature(code_content, element_type)
        elif language.lower() in ["javascript", "typescript"]:
            return self._extract_javascript_signature(code_content, element_type)
        return [], None
    
    def _extract_python_signature(
        self,
        code_content: str,
        element_type: str
    ) -> Tuple[List[Parameter], Optional[str]]:
        """
        Extract parameters and return type from Python function/method using AST.
        
        Args:
            code_content: Python code content
            element_type: Type of element ('function', 'method', 'class')
            
        Returns:
            Tuple of (parameters list, return_type string)
        """
        parameters = []
        return_type = None
        
        try:
            # Remove leading indentation to help AST parser
            import textwrap
            dedented_code = textwrap.dedent(code_content)
            tree = ast.parse(dedented_code)
            
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Extract parameters
                    for arg in node.args.args:
                        param_name = arg.arg
                        
                        # Skip 'self' and 'cls' for methods
                        if element_type == 'method' and param_name in ['self', 'cls']:
                            continue
                        
                        # Extract type hint if present
                        type_hint = None
                        if arg.annotation:
                            type_hint = ast.unparse(arg.annotation)
                        
                        # Extract default value if present
                        default_value = None
                        defaults = node.args.defaults
                        num_defaults = len(defaults)
                        num_args = len(node.args.args)
                        arg_index = node.args.args.index(arg)
                        
                        if arg_index >= num_args - num_defaults:
                            default_index = arg_index - (num_args - num_defaults)
                            default_value = ast.unparse(defaults[default_index])
                        
                        parameters.append(Parameter(
                            name=param_name,
                            type_hint=type_hint,
                            default_value=default_value
                        ))
                    
                    # Extract return type
                    if node.returns:
                        return_type = ast.unparse(node.returns)
                    
                    break  # Only process first function/method
                
                elif isinstance(node, ast.ClassDef) and element_type == 'class':
                    # For classes, we don't extract parameters from __init__
                    # but we could in the future
                    break
                    
        except SyntaxError:
            # Fallback to regex if AST parsing fails
            pass
        
        return parameters, return_type
    
    def _extract_javascript_signature(
        self,
        code_content: str,
        element_type: str
    ) -> Tuple[List[Parameter], Optional[str]]:
        """
        Extract parameters and return type from JavaScript/TypeScript using regex.
        
        Args:
            code_content: JavaScript/TypeScript code content
            element_type: Type of element ('function', 'method', 'class')
            
        Returns:
            Tuple of (parameters list, return_type string)
        """
        parameters = []
        return_type = None
        
        if element_type == 'class':
            # For classes, we don't extract constructor parameters yet
            return parameters, return_type
        
        # Pattern to match function signatures
        # Matches: function name(params), name(params), (params) =>, etc.
        patterns = [
            r'function\s+\w+\s*\(([^)]*)\)(?:\s*:\s*([^{]+))?',  # function name(params): type
            r'(?:const|let|var)\s+\w+\s*=\s*function\s*\(([^)]*)\)(?:\s*:\s*([^{]+))?',  # const name = function(params)
            r'(?:const|let|var)\s+\w+\s*=\s*\(([^)]*)\)\s*(?::\s*([^=]+))?\s*=>',  # const name = (params): type =>
            r'(\w+)\s*\(([^)]*)\)(?:\s*:\s*([^{]+))?\s*\{',  # name(params): type {
        ]
        
        for pattern in patterns:
            match = re.search(pattern, code_content)
            if match:
                # Extract parameters from the matched group
                params_str = match.group(1) if '(' in pattern else match.group(2)
                
                if params_str and params_str.strip():
                    # Split parameters
                    param_parts = params_str.split(',')
                    
                    for param_part in param_parts:
                        param_part = param_part.strip()
                        if not param_part:
                            continue
                        
                        # Parse parameter with optional type and default
                        # Format: name: type = default
                        param_name = param_part
                        type_hint = None
                        default_value = None
                        
                        # Check for default value
                        if '=' in param_part:
                            param_name, default_value = param_part.split('=', 1)
                            param_name = param_name.strip()
                            default_value = default_value.strip()
                        
                        # Check for type annotation
                        if ':' in param_name:
                            param_name, type_hint = param_name.split(':', 1)
                            param_name = param_name.strip()
                            type_hint = type_hint.strip()
                        
                        # Remove destructuring and rest operators
                        param_name = re.sub(r'^\.\.\.', '', param_name)  # Rest operator
                        param_name = re.sub(r'[{}\[\]]', '', param_name)  # Destructuring
                        param_name = param_name.strip()
                        
                        if param_name:
                            parameters.append(Parameter(
                                name=param_name,
                                type_hint=type_hint,
                                default_value=default_value
                            ))
                
                # Extract return type if present
                # Return type is typically the last captured group
                groups = match.groups()
                for group in reversed(groups):
                    if group and ':' not in group and '=' not in group:
                        return_type = group.strip()
                        break
                
                break  # Found a match, stop searching
        
        return parameters, return_type
    
    def _generate_gap_report(
        self,
        file_analyses: List[FileAnalysis]
    ) -> GapReport:
        """
        Generate a comprehensive gap report from file analyses.
        
        Aggregates statistics across all analyzed files.
        
        Args:
            file_analyses: List of FileAnalysis objects
            
        Returns:
            GapReport with aggregated statistics
        """
        total_elements = 0
        elements_with_gaps = 0
        elements_by_type: Dict[str, int] = {}
        elements_by_language: Dict[str, int] = {}
        total_quality_score = 0.0
        
        for file_analysis in file_analyses:
            for element in file_analysis.code_elements:
                total_elements += 1
                
                if element.has_gap:
                    elements_with_gaps += 1
                
                # Count by type
                element_type = element.element_type
                elements_by_type[element_type] = elements_by_type.get(element_type, 0) + 1
                
                # Count by language
                language = element.language
                elements_by_language[language] = elements_by_language.get(language, 0) + 1
                
                # Sum quality scores
                total_quality_score += element.quality_score
        
        # Calculate average quality score
        average_quality_score = (
            total_quality_score / total_elements if total_elements > 0 else 0.0
        )
        
        return GapReport(
            total_elements=total_elements,
            elements_with_gaps=elements_with_gaps,
            elements_by_type=elements_by_type,
            elements_by_language=elements_by_language,
            file_analyses=file_analyses,
            average_quality_score=average_quality_score
        )
