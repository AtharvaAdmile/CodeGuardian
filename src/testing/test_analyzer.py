import os
import ast
from typing import List, Dict, Optional, Any
import logging

from src.code_parser import CodeParser, CodeBlock
from src.documentation.dependency_analyzer import DependencyAnalyzer
from src.models.testing_models import TestableElement
from src.models.documentation_models import CodeElement

logger = logging.getLogger(__name__)

class TestAnalyzer:
    """
    Analyzes code to identify testable elements and their characteristics.
    """
    
    def __init__(self, code_parser: Optional[CodeParser] = None, dependency_analyzer: Optional[DependencyAnalyzer] = None):
        self.code_parser = code_parser or CodeParser()
        self.dependency_analyzer = dependency_analyzer or DependencyAnalyzer()
        
    def analyze_file(self, file_path: str, content: str) -> List[TestableElement]:
        """
        Analyze a file to find all testable elements (functions, classes).
        """
        if not self._is_testable_file(file_path):
            return []
            
        try:
            # Parse code structure
            parsed_code = self.code_parser.parse_file(file_path, content)
            testable_elements = []
            
            # Analyze functions (standalone)
            for func in parsed_code.functions:
                # Skip private/magic methods if configured to do so
                # For now, we include everything but maybe de-prioritize private ones
                
                element = self._create_testable_element(
                    block=func,
                    file_path=file_path,
                    element_type="function",
                    content=content
                )
                testable_elements.append(element)
                
            # Analyze classes and their methods
            for cls in parsed_code.classes:
                # Add the class itself? Maybe for integration tests. 
                # Usually we test methods, but sometimes class-level behavior.
                # structure_analyzer returns methods as children if it parses them?
                # CodeParser.extract_classes returns blocks. Does it return methods inside?
                # Looking at CodeParser, it returns functions and classes separately. 
                # Methods might be in 'functions' with parent_class set?
                # Let's check CodeParser behavior or just re-parse if needed.
                # Assuming CodeParser flattens methods into functions list or we check logic.
                pass
                
            # Re-scan for methods if CodeParser logic separates them
            # CodeParser extraction logic: 
            # extract_functions returns all functions. _find_parent_class sets parent_class.
            # So parsed_code.functions includes methods.
            
            return testable_elements
            
        except Exception as e:
            logger.error(f"Error analyzing file {file_path}: {str(e)}")
            return []
            
    def _is_testable_file(self, file_path: str) -> bool:
        """Check if file is a valid target for testing."""
        return file_path.endswith('.py') # Focus on Python for now
        
    def _create_testable_element(
        self, 
        block: CodeBlock, 
        file_path: str, 
        element_type: str,
        content: str
    ) -> TestableElement:
        """Convert a CodeBlock into a TestableElement with metrics."""
        
        # Calculate complexity (simplified for now)
        complexity = self._calculate_complexity(block.content)
        
        # unique ID
        element_id = f"{file_path}:{block.name}:{block.start_line}"
        
        return TestableElement(
            element_id=element_id,
            name=block.name,
            element_type="method" if block.parent_class else "function",
            file_path=file_path,
            start_line=block.start_line,
            end_line=block.end_line,
            content=block.content,
            complexity_score=complexity,
            has_existing_tests=False, # To be implemented via verification_agent
            dependencies=[], # Populated via dependency analyzer if needed
            docstring=None # Could extract
        )
        
    def _calculate_complexity(self, code: str) -> float:
        """Estimate code complexity."""
        # Simple heuristic: length + indentation + branches
        score = 1.0
        lines = code.splitlines()
        score += len(lines) * 0.1
        
        # Count control structures
        for line in lines:
            if any(keyword in line for keyword in ['if ', 'for ', 'while ', 'except ', 'with ']):
                score += 1.0
                
        return round(score, 2)
