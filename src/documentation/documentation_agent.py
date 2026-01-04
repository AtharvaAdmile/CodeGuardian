"""
Documentation Agent for generating code documentation using LLM.

This module provides the DocumentationAgent class that interfaces with the LLM
to generate high-quality documentation for code elements based on analysis and context.
"""

import time
import logging
from typing import List, Dict, Optional, Callable, Any

import google.generativeai as genai
from src.models.documentation_models import (
    ContextMap,
    GapReport,
    DocumentationItem,
    CodeElement,
    ElementContext,
    DocumentationConfig
)
from src.documentation.template_engine import TemplateEngine


class DocumentationAgent:
    """
    Agent responsible for generating documentation using LLM.
    
    Uses context maps and gap reports to generate context-aware documentation
    for code elements.
    """
    
    def __init__(
        self,
        llm_client: Any,
        template_engine: TemplateEngine,
        config: Optional[DocumentationConfig] = None
    ):
        """
        Initialize the Documentation Agent.
        
        Args:
            llm_client: Client for interacting with Gemini API (genai.GenerativeModel)
            template_engine: Engine for prompt generation and formatting
            config: Configuration for documentation generation
        """
        self.llm_client = llm_client
        self.template_engine = template_engine
        self.config = config or DocumentationConfig()
        
        # Cache for generated documentation (element_id -> doc_string)
        # Used to provide context for dependent elements
        self._generated_docs_cache: Dict[str, str] = {}
    
    def generate_documentation(
        self,
        context_map: ContextMap,
        gap_report: GapReport,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> List[DocumentationItem]:
        """
        Generate documentation for all elements in the context map.
        
        Args:
            context_map: Map containing element contexts and processing order
            gap_report: Report containing code elements and gaps
            progress_callback: Optional callback(current, total, element_name)
            
        Returns:
            List of generated DocumentationItem objects
        """
        documentation_items: List[DocumentationItem] = []
        self._generated_docs_cache = {}
        
        # Create a lookup for code elements
        elements_lookup: Dict[str, CodeElement] = {}
        for file_analysis in gap_report.file_analyses:
            for element in file_analysis.code_elements:
                elements_lookup[element.element_id] = element
        
        # Determine processing order
        # Use topological order from context map if available, otherwise linear
        processing_ids = context_map.processing_order
        
        # If processing order is empty/incomplete, fallback to all elements in gap report
        if not processing_ids:
            processing_ids = list(elements_lookup.keys())
            
        total_elements = len(processing_ids)
        
        for i, element_id in enumerate(processing_ids):
            if element_id not in elements_lookup:
                continue
                
            element = elements_lookup[element_id]
            context = context_map.element_contexts.get(element_id)
            
            # Skip if context is missing (shouldn't happen if flow is correct)
            if not context:
                context = ElementContext(element_id=element_id)
            
            # Update progress
            if progress_callback:
                progress_callback(i, total_elements, element.name)
            
            # Generate documentation for this element
            try:
                doc_item = self._generate_single_item(element, context)
                documentation_items.append(doc_item)
                
                # Cache the generated doc for dependent elements
                self._generated_docs_cache[element_id] = doc_item.generated_doc
                
            except Exception as e:
                print(f"Error generating documentation for {element.name}: {str(e)}")
                # Continue to next element even if one fails
                continue
                
        return documentation_items
    
    def _generate_single_item(
        self,
        element: CodeElement,
        context: ElementContext
    ) -> DocumentationItem:
        """
        Generate documentation for a single code element.
        
        Args:
            element: Code element to document
            context: Contextual information for the element
            
        Returns:
            DocumentationItem with generated content
        """
        start_time = time.time()
        
        # Prepare previously documented dependencies
        # Find which dependencies of this element have already been documented
        previously_documented = {}
        for dep in context.dependencies:
            if dep.target_element_id in self._generated_docs_cache:
                previously_documented[dep.target_element_id] = self._generated_docs_cache[dep.target_element_id]
        
        # specific logic for class methods to get parent class context
        if element.parent_class and element.parent_class in self._generated_docs_cache:
             previously_documented[element.parent_class] = self._generated_docs_cache[element.parent_class]

        # Create prompt
        prompt = self.template_engine.create_documentation_prompt(
            element,
            context,
            previously_documented
        )
        
        # Call LLM
        generated_content = self._call_llm(prompt)
        
        # Format output
        formatted_doc = self.template_engine.format_documentation(
            generated_content,
            element.language,
            element.element_type
        )
        
        generation_time = (time.time() - start_time) * 1000  # ms
        
        # Determine format type
        format_type = "google_docstring" if element.language.lower() == "python" else "jsdoc"
        
        return DocumentationItem(
            element_id=element.element_id,
            element_name=element.name,
            element_type=element.element_type,
            file_path=element.file_path,
            language=element.language,
            generated_doc=formatted_doc,
            format_type=format_type,
            confidence_score=self._calculate_confidence(formatted_doc, context),
            generation_time_ms=generation_time
        )
    
    def _call_llm(self, prompt: str) -> str:
        """
        Call the LLM API to generate content.
        
        Args:
            prompt: The prompt string
            
        Returns:
            Generated text content
        """
        try:
            # We assume self.llm_client is already a genai.GenerativeModel instance
            # or we can reconstruct it if it's not.
            # In main.py we will update the constructor call.
            
            response = self.llm_client.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=self.config.llm_temperature,
                    max_output_tokens=self.config.llm_max_tokens,
                )
            )
            
            return response.text
            
        except Exception as e:
            # In a real implementation, we might implement retry logic here
            raise Exception(f"LLM API call failed: {str(e)}")
    
    def _calculate_confidence(self, doc_string: str, context: ElementContext) -> float:
        """
        Calculate a heuristic confidence score for the generated documentation.
        
        Args:
            doc_string: Generated documentation
            context: Element context
            
        Returns:
            Confidence score (0.0 - 1.0)
        """
        # Simple heuristic scoring
        score = 0.8  # Base score
        
        # Bonus for having context
        if context.purpose_inference:
            score += 0.05
        if context.dependencies:
            score += 0.05
        if context.similar_code:
            score += 0.05
            
        # Penalty for very short documentation
        if len(doc_string) < 20:
            score -= 0.3
            
        return min(0.99, max(0.1, score))
