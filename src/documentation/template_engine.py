"""
Template Engine for generating documentation prompts and formatting output.

This module provides templates and formatting logic for generating LLM prompts
and parsing/formatting the generated documentation in language-specific formats.
"""

from typing import Dict, Optional
from src.models.documentation_models import CodeElement, ElementContext, Parameter


class TemplateEngine:
    """
    Generates LLM prompts for documentation and formats the output.
    
    Supports multiple languages and documentation formats:
    - Python: Google-style docstrings
    - JavaScript/TypeScript: JSDoc format
    """
    
    def __init__(self):
        """Initialize the template engine."""
        pass
    
    def create_documentation_prompt(
        self,
        element: CodeElement,
        context: ElementContext,
        previously_documented: Dict[str, str]
    ) -> str:
        """
        Create an LLM prompt for documentation generation.
        
        Args:
            element: The code element to document
            context: Contextual information about the element
            previously_documented: Dict mapping element_id to generated documentation
                                  for dependencies that have already been documented
        
        Returns:
            Formatted prompt string for the LLM
        """
        language = element.language.lower()
        element_type = element.element_type.lower()
        
        if language == "python":
            return self._create_python_prompt(element, context, previously_documented)
        elif language in ["javascript", "typescript"]:
            return self._create_javascript_prompt(element, context, previously_documented)
        else:
            raise ValueError(f"Unsupported language: {language}")
    
    def format_documentation(
        self,
        raw_doc: str,
        language: str,
        element_type: str
    ) -> str:
        """
        Format raw LLM output into proper docstring/JSDoc format.
        
        Args:
            raw_doc: Raw documentation text from LLM
            language: Programming language ('python', 'javascript', 'typescript')
            element_type: Type of element ('function', 'class', 'method')
        
        Returns:
            Properly formatted documentation string
        """
        language = language.lower()
        
        # Clean up the raw documentation
        raw_doc = raw_doc.strip()
        
        if language == "python":
            return self._format_python_docstring(raw_doc, element_type)
        elif language in ["javascript", "typescript"]:
            return self._format_jsdoc(raw_doc, element_type)
        else:
            return raw_doc
    
    # ========================================================================
    # Python Prompt Templates
    # ========================================================================
    
    def _create_python_prompt(
        self,
        element: CodeElement,
        context: ElementContext,
        previously_documented: Dict[str, str]
    ) -> str:
        """Create prompt for Python code element."""
        element_type = element.element_type.lower()
        
        if element_type in ["function", "method"]:
            return self._create_python_function_prompt(element, context, previously_documented)
        elif element_type == "class":
            return self._create_python_class_prompt(element, context, previously_documented)
        else:
            return self._create_python_function_prompt(element, context, previously_documented)
    
    def _create_python_function_prompt(
        self,
        element: CodeElement,
        context: ElementContext,
        previously_documented: Dict[str, str]
    ) -> str:
        """Create prompt for Python function/method documentation."""
        
        # Build parameter information
        params_info = self._format_parameters_info(element.parameters)
        
        # Build context information
        context_info = self._format_context_info(context, previously_documented)
        
        # Build the prompt
        prompt = f"""Generate comprehensive documentation for the following Python {element.element_type}.

Code:
```python
{element.code_content}
```

{context_info}

Requirements:
- Use Google-style docstring format
- Include a clear, concise summary description (one line)
- Include an Args section with type information for each parameter
- Include a Returns section with type and description
- Include a usage example that demonstrates typical usage
- Keep the tone professional and clear
- Focus on what the {element.element_type} does, not how it does it

Example of high-quality Google-style docstring:
```python
def calculate_similarity(embedding1: List[float], embedding2: List[float]) -> float:
    \"\"\"Calculate cosine similarity between two embedding vectors.
    
    This function computes the cosine similarity, which measures the cosine
    of the angle between two vectors in a multi-dimensional space.
    
    Args:
        embedding1: First embedding vector as a list of floats
        embedding2: Second embedding vector as a list of floats
    
    Returns:
        Cosine similarity score between -1 and 1, where 1 indicates
        identical direction, 0 indicates orthogonality, and -1 indicates
        opposite direction
    
    Example:
        >>> vec1 = [1.0, 2.0, 3.0]
        >>> vec2 = [2.0, 4.0, 6.0]
        >>> similarity = calculate_similarity(vec1, vec2)
        >>> print(f"Similarity: {{similarity:.3f}}")
        Similarity: 1.000
    \"\"\"
```

Generate only the docstring content (including the triple quotes), no additional code or explanations."""
        
        return prompt
    
    def _create_python_class_prompt(
        self,
        element: CodeElement,
        context: ElementContext,
        previously_documented: Dict[str, str]
    ) -> str:
        """Create prompt for Python class documentation."""
        
        # Build context information
        context_info = self._format_context_info(context, previously_documented)
        
        prompt = f"""Generate comprehensive documentation for the following Python class.

Code:
```python
{element.code_content}
```

{context_info}

Requirements:
- Use Google-style docstring format
- Include a clear, concise summary description
- Describe the purpose and responsibility of the class
- Include an Attributes section if the class has instance variables
- Include a usage example showing how to instantiate and use the class
- Keep the tone professional and clear

Example of high-quality class docstring:
```python
class DocumentationAgent:
    \"\"\"Generates high-quality documentation using LLM.
    
    This agent is responsible for creating comprehensive documentation for
    code elements by leveraging contextual information and previously
    generated documentation for dependencies.
    
    Attributes:
        llm_client: Gemini client for LLM API calls
        template_engine: Engine for generating prompts and formatting output
        model: Name of the LLM model to use
    
    Example:
        >>> agent = DocumentationAgent(gemini_client, template_engine)
        >>> doc_items = agent.generate_documentation(context_map, gap_report)
        >>> print(f"Generated {{len(doc_items)}} documentation items")
    \"\"\"
```

Generate only the docstring content (including the triple quotes), no additional code or explanations."""
        
        return prompt
    
    # ========================================================================
    # JavaScript/TypeScript Prompt Templates
    # ========================================================================
    
    def _create_javascript_prompt(
        self,
        element: CodeElement,
        context: ElementContext,
        previously_documented: Dict[str, str]
    ) -> str:
        """Create prompt for JavaScript/TypeScript code element."""
        element_type = element.element_type.lower()
        
        if element_type in ["function", "method"]:
            return self._create_javascript_function_prompt(element, context, previously_documented)
        elif element_type == "class":
            return self._create_javascript_class_prompt(element, context, previously_documented)
        else:
            return self._create_javascript_function_prompt(element, context, previously_documented)
    
    def _create_javascript_function_prompt(
        self,
        element: CodeElement,
        context: ElementContext,
        previously_documented: Dict[str, str]
    ) -> str:
        """Create prompt for JavaScript/TypeScript function documentation."""
        
        # Build parameter information
        params_info = self._format_parameters_info(element.parameters)
        
        # Build context information
        context_info = self._format_context_info(context, previously_documented)
        
        lang_name = "JavaScript" if element.language.lower() == "javascript" else "TypeScript"
        
        prompt = f"""Generate comprehensive JSDoc documentation for the following {lang_name} {element.element_type}.

Code:
```{element.language.lower()}
{element.code_content}
```

{context_info}

Requirements:
- Use JSDoc format with appropriate tags
- Include a clear, concise description
- Use @param tags for each parameter with type information
- Use @returns tag with type and description
- Use @example tag with a practical usage example
- Keep the tone professional and clear
- Focus on what the {element.element_type} does, not implementation details

Example of high-quality JSDoc:
```javascript
/**
 * Creates a debounced version of a function that delays execution.
 * 
 * This higher-order function returns a new function that delays invoking
 * the provided function until after the specified wait time has elapsed
 * since the last time it was invoked. Useful for rate-limiting expensive
 * operations like API calls or DOM updates.
 * 
 * @param {{Function}} func - The function to debounce
 * @param {{number}} wait - The number of milliseconds to delay
 * @returns {{Function}} A debounced version of the provided function
 * 
 * @example
 * const debouncedSearch = debounce((query) => {{
 *   console.log('Searching for:', query);
 * }}, 300);
 * 
 * // Will only execute once after 300ms of no calls
 * debouncedSearch('hello');
 * debouncedSearch('hello world');
 */
```

Generate only the JSDoc comment (including /** and */), no additional code or explanations."""
        
        return prompt
    
    def _create_javascript_class_prompt(
        self,
        element: CodeElement,
        context: ElementContext,
        previously_documented: Dict[str, str]
    ) -> str:
        """Create prompt for JavaScript/TypeScript class documentation."""
        
        # Build context information
        context_info = self._format_context_info(context, previously_documented)
        
        lang_name = "JavaScript" if element.language.lower() == "javascript" else "TypeScript"
        
        prompt = f"""Generate comprehensive JSDoc documentation for the following {lang_name} class.

Code:
```{element.language.lower()}
{element.code_content}
```

{context_info}

Requirements:
- Use JSDoc format with @class tag
- Include a clear, concise description
- Describe the purpose and responsibility of the class
- Use @property tags for important instance properties
- Include an @example tag showing instantiation and usage
- Keep the tone professional and clear

Example of high-quality class JSDoc:
```javascript
/**
 * Manages the review and approval workflow for generated documentation.
 * 
 * This class provides storage and retrieval functionality for documentation
 * items, tracks approval status, and handles user edits. It serves as the
 * central coordinator for the review phase of documentation generation.
 * 
 * @class
 * @property {{Map<string, DocumentationItem[]>}} sessions - Storage for documentation sessions
 * @property {{Map<string, string>}} approvalStatus - Tracks approval status by element ID
 * 
 * @example
 * const reviewManager = new ReviewManager();
 * reviewManager.storeDocumentationItems(sessionId, items);
 * const pendingItems = reviewManager.getItemsForReview(sessionId, {{ status: 'pending' }});
 */
```

Generate only the JSDoc comment (including /** and */), no additional code or explanations."""
        
        return prompt
    
    # ========================================================================
    # Formatting Methods
    # ========================================================================
    
    def _format_python_docstring(self, raw_doc: str, element_type: str) -> str:
        """Format raw documentation as Python docstring."""
        # Remove any markdown code blocks if present
        raw_doc = raw_doc.replace("```python", "").replace("```", "").strip()
        
        # Ensure it has triple quotes
        if not raw_doc.startswith('"""') and not raw_doc.startswith("'''"):
            raw_doc = '"""' + raw_doc
        
        if not raw_doc.endswith('"""') and not raw_doc.endswith("'''"):
            raw_doc = raw_doc + '"""'
        
        return raw_doc
    
    def _format_jsdoc(self, raw_doc: str, element_type: str) -> str:
        """Format raw documentation as JSDoc comment."""
        # Remove any markdown code blocks if present
        raw_doc = raw_doc.replace("```javascript", "").replace("```typescript", "")
        raw_doc = raw_doc.replace("```", "").strip()
        
        # Ensure it has JSDoc comment markers
        if not raw_doc.startswith("/**"):
            raw_doc = "/**\n" + raw_doc
        
        if not raw_doc.endswith("*/"):
            raw_doc = raw_doc + "\n*/"
        
        return raw_doc
    
    # ========================================================================
    # Helper Methods
    # ========================================================================
    
    def _format_parameters_info(self, parameters: list[Parameter]) -> str:
        """Format parameter information for inclusion in prompts."""
        if not parameters:
            return "No parameters"
        
        params = []
        for param in parameters:
            param_str = f"- {param.name}"
            if param.type_hint:
                param_str += f" ({param.type_hint})"
            if param.default_value:
                param_str += f" = {param.default_value}"
            params.append(param_str)
        
        return "Parameters:\n" + "\n".join(params)
    
    def _format_context_info(
        self,
        context: ElementContext,
        previously_documented: Dict[str, str]
    ) -> str:
        """Format context information for inclusion in prompts."""
        sections = []
        
        # Purpose inference
        if context.purpose_inference:
            sections.append(f"Purpose: {context.purpose_inference}")
        
        # Dependencies
        if context.dependencies:
            dep_names = [dep.name for dep in context.dependencies[:5]]  # Limit to 5
            sections.append(f"Dependencies: {', '.join(dep_names)}")
        
        # Called functions
        if context.called_functions:
            funcs = context.called_functions[:5]  # Limit to 5
            sections.append(f"Calls: {', '.join(funcs)}")
        
        # Inheritance
        if context.inheritance and context.inheritance.parent_classes:
            parents = ', '.join(context.inheritance.parent_classes)
            sections.append(f"Inherits from: {parents}")
        
        # Similar code
        if context.similar_code:
            similar = context.similar_code[0]  # Just the most similar
            sections.append(
                f"Similar code found in: {similar.file_path} "
                f"(similarity: {similar.similarity_score:.2f})"
            )
        
        # Previously documented dependencies
        if previously_documented:
            sections.append(
                f"\nRelated documentation already generated for "
                f"{len(previously_documented)} dependencies. "
                f"Use this context to maintain consistency."
            )
        
        # Complexity
        if context.complexity_score > 0:
            complexity_level = "high" if context.complexity_score > 10 else "moderate" if context.complexity_score > 5 else "low"
            sections.append(f"Complexity: {complexity_level}")
        
        if not sections:
            return "Context: No additional context available"
        
        return "Context:\n" + "\n".join(f"- {section}" for section in sections)
