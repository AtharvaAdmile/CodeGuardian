"""
Dependency Analyzer for extracting and analyzing code relationships.

This module provides functionality to analyze dependencies between code elements,
including imports, function calls, and inheritance relationships. It builds
dependency graphs and provides topological sorting for processing order.
"""

import ast
import re
from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict, deque

from src.models.documentation_models import (
    CodeElement,
    Dependency,
    DependencyGraph,
    InheritanceInfo,
    DependencyType
)


class DependencyAnalyzer:
    """
    Analyzes dependencies and relationships between code elements.
    
    Supports:
    - Import extraction (Python and JavaScript/TypeScript)
    - Function call detection
    - Class inheritance detection
    - Dependency graph construction
    - Topological sorting for processing order
    """
    
    def __init__(self):
        """Initialize the dependency analyzer."""
        pass
    
    def analyze_dependencies(
        self,
        element: CodeElement,
        all_elements: List[CodeElement]
    ) -> List[Dependency]:
        """
        Analyze dependencies for a code element.
        
        Extracts:
        - Import statements
        - Function calls within the implementation
        - Class inheritance relationships
        
        Args:
            element: The code element to analyze
            all_elements: All code elements in the codebase for reference
            
        Returns:
            List of Dependency objects representing relationships
        """
        dependencies = []
        
        # Extract imports from the file
        imports = self._extract_imports(element)
        for import_name in imports:
            dependencies.append(Dependency(
                name=import_name,
                dependency_type=DependencyType.IMPORT.value,
                source_element_id=element.element_id,
                target_element_id=self._find_element_by_name(import_name, all_elements)
            ))
        
        # Extract function calls
        called_functions = self._extract_function_calls(element)
        for func_name in called_functions:
            target_id = self._find_element_by_name(func_name, all_elements)
            if target_id:  # Only add if we can resolve the target
                dependencies.append(Dependency(
                    name=func_name,
                    dependency_type=DependencyType.FUNCTION_CALL.value,
                    source_element_id=element.element_id,
                    target_element_id=target_id
                ))
        
        # Extract inheritance relationships for classes
        if element.element_type == 'class':
            parent_classes = self._extract_inheritance(element)
            for parent_name in parent_classes:
                dependencies.append(Dependency(
                    name=parent_name,
                    dependency_type=DependencyType.INHERITANCE.value,
                    source_element_id=element.element_id,
                    target_element_id=self._find_element_by_name(parent_name, all_elements)
                ))
        
        return dependencies

    def _extract_imports(self, element: CodeElement) -> List[str]:
        """
        Extract import statements from a code element's file.
        
        Args:
            element: Code element to analyze
            
        Returns:
            List of imported module/function names
        """
        if element.language == 'python':
            return self._extract_python_imports(element.code_content)
        elif element.language in ['javascript', 'typescript']:
            return self._extract_javascript_imports(element.code_content)
        return []
    
    def _extract_python_imports(self, code: str) -> List[str]:
        """
        Extract imports from Python code using AST.
        
        Args:
            code: Python source code
            
        Returns:
            List of imported names
        """
        imports = []
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
                    for alias in node.names:
                        imports.append(alias.name)
        
        except SyntaxError:
            # If parsing fails, fall back to regex
            imports = self._extract_python_imports_regex(code)
        
        return imports
    
    def _extract_python_imports_regex(self, code: str) -> List[str]:
        """
        Extract imports from Python code using regex (fallback).
        
        Args:
            code: Python source code
            
        Returns:
            List of imported names
        """
        imports = []
        
        # Match: import module
        import_pattern = r'^\s*import\s+([\w.]+)'
        # Match: from module import name
        from_pattern = r'^\s*from\s+([\w.]+)\s+import\s+([\w,\s]+)'
        
        for line in code.splitlines():
            import_match = re.match(import_pattern, line)
            if import_match:
                imports.append(import_match.group(1))
            
            from_match = re.match(from_pattern, line)
            if from_match:
                imports.append(from_match.group(1))
                # Also add individual imported names
                names = from_match.group(2).split(',')
                for name in names:
                    name = name.strip()
                    if name and name != '*':
                        imports.append(name)
        
        return imports
    
    def _extract_javascript_imports(self, code: str) -> List[str]:
        """
        Extract imports from JavaScript/TypeScript code.
        
        Args:
            code: JavaScript/TypeScript source code
            
        Returns:
            List of imported names
        """
        imports = []
        
        # Match: import { name } from 'module'
        # Match: import name from 'module'
        # Match: import * as name from 'module'
        import_pattern = r'^\s*import\s+(?:\{([^}]+)\}|(\w+)|\*\s+as\s+(\w+))\s+from\s+[\'"]([^\'"]+)[\'"]'
        
        # Match: const name = require('module')
        require_pattern = r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*require\s*\([\'"]([^\'"]+)[\'"]\)'
        
        for line in code.splitlines():
            import_match = re.match(import_pattern, line)
            if import_match:
                # Extract module name
                module = import_match.group(4)
                imports.append(module)
                
                # Extract imported names
                if import_match.group(1):  # { name1, name2 }
                    names = import_match.group(1).split(',')
                    for name in names:
                        name = name.strip().split(' as ')[0].strip()
                        if name:
                            imports.append(name)
                elif import_match.group(2):  # default import
                    imports.append(import_match.group(2))
                elif import_match.group(3):  # * as name
                    imports.append(import_match.group(3))
            
            require_match = re.match(require_pattern, line)
            if require_match:
                imports.append(require_match.group(2))
                imports.append(require_match.group(1))
        
        return imports

    def _extract_function_calls(self, element: CodeElement) -> List[str]:
        """
        Extract function calls from code element implementation.
        
        Args:
            element: Code element to analyze
            
        Returns:
            List of called function names
        """
        if element.language == 'python':
            return self._extract_python_function_calls(element.code_content)
        elif element.language in ['javascript', 'typescript']:
            return self._extract_javascript_function_calls(element.code_content)
        return []
    
    def _extract_python_function_calls(self, code: str) -> List[str]:
        """
        Extract function calls from Python code using AST.
        
        Args:
            code: Python source code
            
        Returns:
            List of called function names
        """
        function_calls = set()
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Extract function name
                    func_name = self._get_function_name_from_call(node)
                    if func_name:
                        function_calls.add(func_name)
        
        except SyntaxError:
            # If parsing fails, fall back to regex
            function_calls = set(self._extract_python_function_calls_regex(code))
        
        return list(function_calls)
    
    def _get_function_name_from_call(self, call_node: ast.Call) -> Optional[str]:
        """
        Extract function name from an AST Call node.
        
        Args:
            call_node: AST Call node
            
        Returns:
            Function name or None
        """
        func = call_node.func
        
        if isinstance(func, ast.Name):
            return func.id
        elif isinstance(func, ast.Attribute):
            # For method calls like obj.method(), return 'method'
            return func.attr
        
        return None
    
    def _extract_python_function_calls_regex(self, code: str) -> List[str]:
        """
        Extract function calls from Python code using regex (fallback).
        
        Args:
            code: Python source code
            
        Returns:
            List of called function names
        """
        function_calls = set()
        
        # Match: function_name( or obj.method_name(
        call_pattern = r'(?:^|[^\w.])(\w+)\s*\('
        
        for match in re.finditer(call_pattern, code):
            func_name = match.group(1)
            # Filter out common keywords
            if func_name not in ['if', 'for', 'while', 'def', 'class', 'return', 'print']:
                function_calls.add(func_name)
        
        return list(function_calls)
    
    def _extract_javascript_function_calls(self, code: str) -> List[str]:
        """
        Extract function calls from JavaScript/TypeScript code.
        
        Args:
            code: JavaScript/TypeScript source code
            
        Returns:
            List of called function names
        """
        function_calls = set()
        
        # Match: functionName( or obj.methodName(
        call_pattern = r'(?:^|[^\w.])(\w+)\s*\('
        
        for match in re.finditer(call_pattern, code):
            func_name = match.group(1)
            # Filter out common keywords
            if func_name not in ['if', 'for', 'while', 'function', 'class', 'return', 
                                  'console', 'const', 'let', 'var', 'new']:
                function_calls.add(func_name)
        
        return list(function_calls)

    def _extract_inheritance(self, element: CodeElement) -> List[str]:
        """
        Extract class inheritance relationships.
        
        Args:
            element: Code element (must be a class)
            
        Returns:
            List of parent class names
        """
        if element.language == 'python':
            return self._extract_python_inheritance(element.code_content)
        elif element.language in ['javascript', 'typescript']:
            return self._extract_javascript_inheritance(element.code_content)
        return []
    
    def _extract_python_inheritance(self, code: str) -> List[str]:
        """
        Extract parent classes from Python class definition using AST.
        
        Args:
            code: Python class code
            
        Returns:
            List of parent class names
        """
        parent_classes = []
        
        try:
            tree = ast.parse(code)
            
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            parent_classes.append(base.id)
                        elif isinstance(base, ast.Attribute):
                            # For cases like module.ClassName
                            parent_classes.append(base.attr)
        
        except SyntaxError:
            # Fall back to regex
            parent_classes = self._extract_python_inheritance_regex(code)
        
        return parent_classes
    
    def _extract_python_inheritance_regex(self, code: str) -> List[str]:
        """
        Extract parent classes from Python class definition using regex (fallback).
        
        Args:
            code: Python class code
            
        Returns:
            List of parent class names
        """
        parent_classes = []
        
        # Match: class ClassName(ParentClass):
        # Match: class ClassName(Parent1, Parent2):
        class_pattern = r'^\s*class\s+\w+\s*\(([^)]+)\)\s*:'
        
        for line in code.splitlines():
            match = re.match(class_pattern, line)
            if match:
                parents = match.group(1).split(',')
                for parent in parents:
                    parent = parent.strip()
                    # Extract just the class name (handle module.ClassName)
                    if '.' in parent:
                        parent = parent.split('.')[-1]
                    if parent:
                        parent_classes.append(parent)
                break  # Only process the first class definition
        
        return parent_classes
    
    def _extract_javascript_inheritance(self, code: str) -> List[str]:
        """
        Extract parent classes from JavaScript/TypeScript class definition.
        
        Args:
            code: JavaScript/TypeScript class code
            
        Returns:
            List of parent class names
        """
        parent_classes = []
        
        # Match: class ClassName extends ParentClass
        extends_pattern = r'^\s*class\s+\w+\s+extends\s+([\w.]+)'
        
        for line in code.splitlines():
            match = re.match(extends_pattern, line)
            if match:
                parent = match.group(1)
                # Extract just the class name (handle module.ClassName)
                if '.' in parent:
                    parent = parent.split('.')[-1]
                parent_classes.append(parent)
                break  # Only process the first class definition
        
        return parent_classes
    
    def _find_element_by_name(
        self,
        name: str,
        all_elements: List[CodeElement]
    ) -> Optional[str]:
        """
        Find a code element by name and return its element_id.
        
        Args:
            name: Name to search for
            all_elements: All code elements to search
            
        Returns:
            Element ID if found, None otherwise
        """
        for element in all_elements:
            if element.name == name:
                return element.element_id
        return None

    def build_dependency_graph(
        self,
        elements: List[CodeElement],
        dependencies: Dict[str, List[Dependency]]
    ) -> DependencyGraph:
        """
        Build a directed graph of element dependencies.
        
        Args:
            elements: All code elements
            dependencies: Map of element_id to list of dependencies
            
        Returns:
            DependencyGraph with nodes and edges
        """
        nodes = [element.element_id for element in elements]
        edges = []
        
        for element_id, deps in dependencies.items():
            for dep in deps:
                # Only add edges where we have a resolved target
                if dep.target_element_id:
                    # Edge from dependency to dependent (target -> source)
                    # This ensures dependencies are processed before dependents
                    edges.append((dep.target_element_id, element_id))
        
        return DependencyGraph(nodes=nodes, edges=edges)
    
    def topological_sort(self, graph: DependencyGraph) -> List[str]:
        """
        Perform topological sort on dependency graph using Kahn's algorithm.
        
        Returns element IDs in dependency order (dependencies before dependents).
        Elements with no dependencies come first.
        
        Args:
            graph: DependencyGraph to sort
            
        Returns:
            List of element_ids in topological order
        """
        # Build adjacency list and in-degree map
        adj_list = defaultdict(list)
        in_degree = {node: 0 for node in graph.nodes}
        
        for from_node, to_node in graph.edges:
            adj_list[from_node].append(to_node)
            in_degree[to_node] += 1
        
        # Initialize queue with nodes that have no dependencies (in-degree = 0)
        queue = deque([node for node in graph.nodes if in_degree[node] == 0])
        sorted_order = []
        
        # Process nodes in topological order
        while queue:
            node = queue.popleft()
            sorted_order.append(node)
            
            # Reduce in-degree for neighbors
            for neighbor in adj_list[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # Check for cycles - if we haven't processed all nodes, there's a cycle
        if len(sorted_order) != len(graph.nodes):
            # Handle cycle by adding remaining nodes in arbitrary order
            remaining = set(graph.nodes) - set(sorted_order)
            sorted_order.extend(remaining)
        
        return sorted_order
    
    def get_inheritance_info(
        self,
        element: CodeElement,
        all_elements: List[CodeElement],
        dependencies: Dict[str, List[Dependency]]
    ) -> Optional[InheritanceInfo]:
        """
        Get complete inheritance information for a class element.
        
        Args:
            element: Code element (must be a class)
            all_elements: All code elements
            dependencies: Map of element_id to dependencies
            
        Returns:
            InheritanceInfo with parent and child classes, or None if not a class
        """
        if element.element_type != 'class':
            return None
        
        parent_classes = []
        child_classes = []
        
        # Get parent classes from dependencies
        if element.element_id in dependencies:
            for dep in dependencies[element.element_id]:
                if dep.dependency_type == DependencyType.INHERITANCE.value:
                    parent_classes.append(dep.name)
        
        # Find child classes (classes that inherit from this one)
        for other_element in all_elements:
            if other_element.element_id in dependencies:
                for dep in dependencies[other_element.element_id]:
                    if (dep.dependency_type == DependencyType.INHERITANCE.value and
                        dep.target_element_id == element.element_id):
                        child_classes.append(other_element.name)
        
        return InheritanceInfo(
            parent_classes=parent_classes,
            child_classes=child_classes,
            interfaces=[]  # Can be extended for TypeScript interfaces
        )
