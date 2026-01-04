"""
Context Agent for analyzing code relationships and building context maps.

This module provides the ContextAgent class that analyzes code elements to
understand their purpose, dependencies, and relationships. It integrates with
the DependencyAnalyzer and vector store to build comprehensive context maps
that inform documentation generation.
"""

import re
from typing import List, Dict, Optional, Callable

from src.models.documentation_models import (
    CodeElement,
    ElementContext,
    ContextMap,
    GapReport,
    SimilarCode,
    InheritanceInfo
)
from src.documentation.dependency_analyzer import DependencyAnalyzer
from src.vector_store import VectorStore
from src.embedding_generator import EmbeddingGenerator


class ContextAgent:
    """
    Analyzes code context and relationships to inform documentation generation.
    
    The Context Agent:
    - Analyzes dependencies and relationships between code elements
    - Queries vector store for semantically similar code
    - Infers purpose from element names, parameters, and context
    - Calculates complexity scores
    - Builds dependency graphs and determines processing order
    """
    
    def __init__(
        self,
        dependency_analyzer: DependencyAnalyzer,
        vector_store: VectorStore,
        embedding_generator: EmbeddingGenerator,
        collection_name: str
    ):
        """
        Initialize the Context Agent.
        
        Args:
            dependency_analyzer: Analyzer for extracting dependencies
            vector_store: Vector store for similarity searches
            embedding_generator: Generator for creating embeddings
            collection_name: Name of the vector store collection to query
        """
        self.dependency_analyzer = dependency_analyzer
        self.vector_store = vector_store
        self.embedding_generator = embedding_generator
        self.collection_name = collection_name
    
    def build_context_map(
        self,
        gap_report: GapReport,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> ContextMap:
        """
        Build a complete context map for all code elements in the gap report.
        
        Processes each element to extract:
        - Dependencies and relationships
        - Similar code from vector store
        - Purpose inference
        - Complexity metrics
        
        Then builds a dependency graph and determines processing order.
        
        Args:
            gap_report: Gap report containing code elements to analyze
            progress_callback: Optional callback(current, total, element_name)
            
        Returns:
            ContextMap with element contexts, dependency graph, and processing order
        """
        # Collect all code elements from the gap report
        all_elements = []
        for file_analysis in gap_report.file_analyses:
            all_elements.extend(file_analysis.code_elements)
        
        # Build context for each element
        element_contexts = {}
        dependencies_map = {}
        
        total_elements = len(all_elements)
        for idx, element in enumerate(all_elements):
            if progress_callback:
                progress_callback(idx + 1, total_elements, element.name)
            
            # Analyze context for this element
            context = self.analyze_element_context(element, all_elements)
            element_contexts[element.element_id] = context
            
            # Store dependencies for graph building
            dependencies_map[element.element_id] = context.dependencies
        
        # Build dependency graph
        dependency_graph = self.dependency_analyzer.build_dependency_graph(
            all_elements,
            dependencies_map
        )
        
        # Determine processing order using topological sort
        processing_order = self.dependency_analyzer.topological_sort(dependency_graph)
        
        return ContextMap(
            element_contexts=element_contexts,
            dependency_graph=dependency_graph,
            processing_order=processing_order
        )
    
    def analyze_element_context(
        self,
        element: CodeElement,
        all_elements: List[CodeElement]
    ) -> ElementContext:
        """
        Analyze context for a single code element.
        
        Extracts:
        - Imports from the file
        - Dependencies (function calls, inheritance)
        - Similar code from vector store
        - Purpose inference
        - Complexity score
        
        Args:
            element: Code element to analyze
            all_elements: All code elements for dependency resolution
            
        Returns:
            ElementContext with comprehensive context information
        """
        # Extract dependencies
        dependencies = self.dependency_analyzer.analyze_dependencies(
            element,
            all_elements
        )
        
        # Extract imports
        imports = self._extract_imports_for_element(element)
        
        # Extract called functions and accessed variables
        called_functions = self._extract_called_functions(element, dependencies)
        accessed_variables = self._extract_accessed_variables(element)
        
        # Get inheritance information for classes
        inheritance = None
        if element.element_type == 'class':
            dependencies_map = {element.element_id: dependencies}
            inheritance = self.dependency_analyzer.get_inheritance_info(
                element,
                all_elements,
                dependencies_map
            )
        
        # Query vector store for similar code
        similar_code = self._find_similar_code(element)
        
        # Infer purpose from element characteristics
        purpose_inference = self._infer_purpose(
            element,
            similar_code,
            inheritance
        )
        
        # Calculate complexity score
        complexity_score = self._calculate_complexity(element)
        
        return ElementContext(
            element_id=element.element_id,
            imports=imports,
            dependencies=dependencies,
            called_functions=called_functions,
            accessed_variables=accessed_variables,
            inheritance=inheritance,
            similar_code=similar_code,
            purpose_inference=purpose_inference,
            complexity_score=complexity_score
        )
    
    def _extract_imports_for_element(self, element: CodeElement) -> List[str]:
        """
        Extract import statements relevant to the code element.
        
        Args:
            element: Code element to analyze
            
        Returns:
            List of imported module/function names
        """
        return self.dependency_analyzer._extract_imports(element)
    
    def _extract_called_functions(
        self,
        element: CodeElement,
        dependencies: List
    ) -> List[str]:
        """
        Extract function names called within the element implementation.
        
        Args:
            element: Code element to analyze
            dependencies: List of dependencies for the element
            
        Returns:
            List of called function names
        """
        called_functions = []
        
        for dep in dependencies:
            if dep.dependency_type == 'function_call':
                called_functions.append(dep.name)
        
        return called_functions
    
    def _extract_accessed_variables(self, element: CodeElement) -> List[str]:
        """
        Extract variable names accessed within the element implementation.
        
        Uses simple pattern matching to identify variable accesses.
        
        Args:
            element: Code element to analyze
            
        Returns:
            List of accessed variable names
        """
        variables = set()
        
        # Pattern to match variable assignments and accesses
        # Matches: variable_name = or self.variable_name or this.variable_name
        if element.language == 'python':
            # Match self.variable_name
            self_pattern = r'\bself\.(\w+)'
            for match in re.finditer(self_pattern, element.code_content):
                variables.add(match.group(1))
            
            # Match variable assignments
            assign_pattern = r'^\s*(\w+)\s*='
            for line in element.code_content.splitlines():
                match = re.match(assign_pattern, line)
                if match:
                    var_name = match.group(1)
                    # Filter out common keywords
                    if var_name not in ['if', 'for', 'while', 'def', 'class', 'return']:
                        variables.add(var_name)
        
        elif element.language in ['javascript', 'typescript']:
            # Match this.variable_name
            this_pattern = r'\bthis\.(\w+)'
            for match in re.finditer(this_pattern, element.code_content):
                variables.add(match.group(1))
            
            # Match variable declarations
            decl_pattern = r'^\s*(?:const|let|var)\s+(\w+)\s*='
            for line in element.code_content.splitlines():
                match = re.match(decl_pattern, line)
                if match:
                    variables.add(match.group(1))
        
        return list(variables)
    
    def _find_similar_code(
        self,
        element: CodeElement,
        n_results: int = 3
    ) -> List[SimilarCode]:
        """
        Find semantically similar code elements using vector store.
        
        Args:
            element: Code element to find similar code for
            n_results: Number of similar results to return
            
        Returns:
            List of SimilarCode objects with similarity scores
        """
        similar_code = []
        
        try:
            # Generate embedding for the code element
            # Use a combination of name, parameters, and code snippet
            query_text = self._create_query_text(element)
            query_embedding = self.embedding_generator.generate_embedding(query_text)
            
            # Query vector store
            results = self.vector_store.query(
                collection_name=self.collection_name,
                query_embedding=query_embedding,
                n_results=n_results + 1  # +1 to account for self-match
            )
            
            # Process results
            for idx, (doc_id, document, metadata, distance) in enumerate(
                zip(results.ids, results.documents, results.metadatas, results.distances)
            ):
                # Skip if this is the same element (self-match)
                if metadata.get('file_path') == element.file_path and \
                   metadata.get('start_line') == element.start_line:
                    continue
                
                # Convert distance to similarity score (0-1)
                # Cosine distance is 0-2, where 0 is identical
                similarity_score = 1.0 - (distance / 2.0)
                
                similar_code.append(SimilarCode(
                    element_id=doc_id,
                    file_path=metadata.get('file_path', 'unknown'),
                    similarity_score=similarity_score,
                    code_snippet=document[:200]  # Truncate to 200 chars
                ))
                
                if len(similar_code) >= n_results:
                    break
        
        except Exception as e:
            # If vector store query fails, return empty list
            print(f"Warning: Failed to find similar code for {element.name}: {str(e)}")
        
        return similar_code
    
    def _create_query_text(self, element: CodeElement) -> str:
        """
        Create query text for vector similarity search.
        
        Combines element name, type, parameters, and a code snippet.
        
        Args:
            element: Code element to create query for
            
        Returns:
            Query text string
        """
        parts = [
            f"{element.element_type}: {element.name}",
        ]
        
        # Add parameters if available
        if element.parameters:
            param_names = [p.name for p in element.parameters]
            parts.append(f"Parameters: {', '.join(param_names)}")
        
        # Add return type if available
        if element.return_type:
            parts.append(f"Returns: {element.return_type}")
        
        # Add code snippet (first 300 characters)
        code_snippet = element.code_content[:300]
        parts.append(code_snippet)
        
        return " | ".join(parts)
    
    def _infer_purpose(
        self,
        element: CodeElement,
        similar_code: List[SimilarCode],
        inheritance: Optional[InheritanceInfo]
    ) -> str:
        """
        Infer the purpose of a code element from its characteristics.
        
        Analyzes:
        - Element name (camelCase, snake_case patterns)
        - Parameters and return type
        - Similar code patterns
        - Inheritance relationships
        
        Args:
            element: Code element to analyze
            similar_code: List of similar code elements
            inheritance: Inheritance information if element is a class
            
        Returns:
            Purpose inference string
        """
        purpose_parts = []
        
        # Analyze element name
        name_purpose = self._analyze_name_pattern(element.name, element.element_type)
        if name_purpose:
            purpose_parts.append(name_purpose)
        
        # Analyze parameters and return type
        if element.element_type in ['function', 'method']:
            if element.parameters:
                param_count = len(element.parameters)
                purpose_parts.append(f"Takes {param_count} parameter{'s' if param_count != 1 else ''}")
            
            if element.return_type and element.return_type != 'None':
                purpose_parts.append(f"Returns {element.return_type}")
        
        # Analyze inheritance for classes
        if inheritance and inheritance.parent_classes:
            parent_list = ', '.join(inheritance.parent_classes)
            purpose_parts.append(f"Extends {parent_list}")
        
        # Analyze similar code patterns
        if similar_code and len(similar_code) > 0:
            avg_similarity = sum(sc.similarity_score for sc in similar_code) / len(similar_code)
            if avg_similarity > 0.7:
                purpose_parts.append("Similar patterns found in codebase")
        
        # Combine all parts
        if purpose_parts:
            return ". ".join(purpose_parts) + "."
        else:
            return f"A {element.element_type} named {element.name}."
    
    def _analyze_name_pattern(self, name: str, element_type: str) -> Optional[str]:
        """
        Analyze naming patterns to infer purpose.
        
        Recognizes common patterns like:
        - get_*, set_* (getters/setters)
        - is_*, has_* (boolean checks)
        - calculate_*, compute_* (calculations)
        - create_*, build_* (constructors)
        - validate_*, check_* (validation)
        
        Args:
            name: Element name
            element_type: Type of element (function, class, method)
            
        Returns:
            Purpose inference or None
        """
        name_lower = name.lower()
        
        # Getter patterns
        if name_lower.startswith('get') or name_lower.startswith('fetch') or name_lower.startswith('retrieve'):
            return "Retrieves or fetches data"
        
        # Setter patterns
        if name_lower.startswith('set') or name_lower.startswith('update'):
            return "Sets or updates data"
        
        # Boolean check patterns
        if name_lower.startswith('is') or name_lower.startswith('has') or name_lower.startswith('can'):
            return "Performs a boolean check"
        
        # Calculation patterns
        if name_lower.startswith('calculate') or name_lower.startswith('compute'):
            return "Performs calculations"
        
        # Creation patterns
        if name_lower.startswith('create') or name_lower.startswith('build') or name_lower.startswith('make'):
            return "Creates or constructs objects"
        
        # Validation patterns
        if name_lower.startswith('validate') or name_lower.startswith('check') or name_lower.startswith('verify'):
            return "Validates or checks conditions"
        
        # Processing patterns
        if name_lower.startswith('process') or name_lower.startswith('handle'):
            return "Processes or handles data"
        
        # Initialization patterns
        if name_lower.startswith('init') or name_lower == '__init__':
            return "Initializes the object"
        
        return None
    
    def _calculate_complexity(self, element: CodeElement) -> float:
        """
        Calculate complexity score for a code element.
        
        Based on:
        - Lines of code (LOC)
        - Cyclomatic complexity estimate (control flow statements)
        - Nesting depth
        
        Returns a score from 0-100 where higher means more complex.
        
        Args:
            element: Code element to analyze
            
        Returns:
            Complexity score (0-100)
        """
        code = element.code_content
        lines = code.splitlines()
        
        # Count lines of code (excluding empty lines and comments)
        loc = 0
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and not stripped.startswith('//'):
                loc += 1
        
        # Estimate cyclomatic complexity by counting control flow statements
        control_flow_keywords = [
            'if', 'elif', 'else', 'for', 'while', 'try', 'except', 'catch',
            'switch', 'case', 'break', 'continue', 'return'
        ]
        
        cyclomatic = 1  # Base complexity
        for keyword in control_flow_keywords:
            # Count occurrences of control flow keywords
            pattern = r'\b' + keyword + r'\b'
            cyclomatic += len(re.findall(pattern, code))
        
        # Estimate nesting depth by counting indentation levels
        max_indent = 0
        for line in lines:
            if line.strip():
                # Count leading spaces/tabs
                indent = len(line) - len(line.lstrip())
                max_indent = max(max_indent, indent)
        
        # Normalize to typical indentation (4 spaces or 1 tab)
        nesting_depth = max_indent // 4
        
        # Calculate complexity score
        # LOC contributes up to 40 points (capped at 100 lines)
        loc_score = min(40, (loc / 100) * 40)
        
        # Cyclomatic complexity contributes up to 40 points (capped at 20)
        cyclomatic_score = min(40, (cyclomatic / 20) * 40)
        
        # Nesting depth contributes up to 20 points (capped at 5 levels)
        nesting_score = min(20, (nesting_depth / 5) * 20)
        
        complexity_score = loc_score + cyclomatic_score + nesting_score
        
        return round(complexity_score, 2)
