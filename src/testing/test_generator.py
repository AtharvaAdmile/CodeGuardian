import os
import logging
from typing import List, Optional, Dict, Any
import google.generativeai as genai
from dataclasses import dataclass

from src.models.testing_models import TestableElement, GeneratedTest, TestType
from src.query_engine import QueryEngine, CodeChunk

logger = logging.getLogger(__name__)

class TestGenerator:
    """
    Generates automated tests using Gemini AI with codebase context.
    """
    
    def __init__(self, api_key: Optional[str] = None, query_engine: Optional[QueryEngine] = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            logger.warning("No Google API Key provided for TestGenerator")
            
        if self.api_key:
            genai.configure(api_key=self.api_key)
            # Use the same model as the main app
            self.model = genai.GenerativeModel("gemini-3-flash-preview")
            
        self.query_engine = query_engine
        
    def generate_tests(
        self, 
        element: TestableElement, 
        test_type: TestType = TestType.UNIT
    ) -> GeneratedTest:
        """
        Generate tests for a specific code element.
        """
        if not self.api_key:
            raise ValueError("Google API Key is required for test generation")
            
        # 1. Gather Context
        context_chunks = []
        if self.query_engine:
            # query for usages/dependencies of this function
            # matching the function name or content
            try:
                # We essentially want to find "how is this used" or "what does this call"
                # Simple approach: query the vector store with the function signature
                query_text = f"references to {element.name} {element.content[:100]}"
                # Retrieve top 5 related chunks
                # We need to access vector store directly or use query engine
                # query_engine.retrieve_chunks returns chunks based on embedding
                # We need to generate embedding for the query first, QueryEngine does that internally in retrieve_chunks if we pass text?
                # looking at QueryEngine.retrieve_chunks, it takes query_embedding.
                # query_engine.query() takes a string but returns an answer string, not chunks directly (it does retrieve internally).
                # We might want to expose a retrieve_context method on QueryEngine or use it if available.
                # QueryEngine has retrieve_chunks(query_embedding). QueryEngine also has embedding_generator.
                if hasattr(self.query_engine, 'embedding_generator'):
                     emb = self.query_engine.embedding_generator.generate_embedding(query_text)
                     context_chunks = self.query_engine.retrieve_chunks(emb, n_results=3)
            except Exception as e:
                logger.warning(f"Failed to retrieve context for test generation: {e}")
                
        # 2. Construct Prompt
        prompt = self._create_test_prompt(element, context_chunks, test_type)
        
        # 3. Call LLM
        try:
            response = self.model.generate_content(prompt)
            test_code = self._clean_llm_response(response.text)
            
            return GeneratedTest(
                test_id=f"test_{element.name}_{test_type.value}",
                target_element_id=element.element_id,
                original_code=element.content,
                test_code=test_code,
                test_type=test_type.value,
                framework="pytest",
                confidence_score=0.8, # Placeholder or heuristic from logprobs
                status="pending"
            )
            
        except Exception as e:
            logger.error(f"Error generating tests for {element.name}: {e}")
            raise

    def _create_test_prompt(
        self, 
        element: TestableElement, 
        context: List[CodeChunk], 
        test_type: TestType
    ) -> str:
        """Create the prompt for Gemini."""
        
        context_str = "\n\n".join([f"// From {c.file_path}:{c.start_line}\n{c.content}" for c in context])
        
        return f"""
You are an expert software test automation engineer.
Your task is to write high-quality {test_type.value} tests for the following Python code using 'pytest'.

TARGET CODE (File: {element.file_path}):
```python
{element.content}
```

RELEVANT CONTEXT (Dependencies/Usages):
```python
{context_str}
```

REQUIREMENTS:
1. Use 'pytest' framework.
2. Naming convention: The file should be named `{os.path.basename(element.file_path).replace('.py', '')}_test.py` (logic handled externally, but write the content for this file).
3. Include all necessary imports. Assume the target code is in a module accessible via import.
4. If the target code has dependencies (external libraries or internal modules), use `unittest.mock` or `pytest-mock` to mock them appropriately.
5. Cover:
   - Positive cases (happy path)
   - Negative cases (error handling, invalid inputs)
   - Edge cases (boundary values, empty inputs)
6. Output ONLY the raw python code for the test file. Do not include markdown formatting (like ```python) or explanations outside the code.
7. Add comments explaining complex test logic.

GENERATE TESTS NOW:
"""

    def _clean_llm_response(self, text: str) -> str:
        """Strip markdown code blocks."""
        cleaned = text.strip()
        if cleaned.startswith("```python"):
            cleaned = cleaned[9:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        return cleaned.strip()
