"""
Test Generator - AI-powered unit test generation using Google Gemini.

This module provides functionality to generate unit tests for source code files
using the Google Gemini API. It supports Python (pytest) and JavaScript/TypeScript (jest).
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Language detection and framework mapping
LANGUAGE_MAP = {
    '.py': ('python', 'pytest'),
    '.js': ('javascript', 'jest'),
    '.ts': ('typescript', 'jest'),
    '.tsx': ('typescript', 'jest'),
    '.jsx': ('javascript', 'jest'),
}


class TestGenerator:
    """
    Generates unit tests for source code using Google Gemini API.
    """
    
    def __init__(self):
        """Initialize the test generator with Gemini API."""
        self.api_key = os.getenv('GOOGLE_API_KEY')
        self.model_name = os.getenv('LLM_MODEL', 'gemini-2.5-flash')
        self._client = None
        
    def _get_client(self):
        """Lazy-load the Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.model_name)
                logger.info(f"Initialized Gemini client with model: {self.model_name}")
            except ImportError:
                raise ImportError("google-generativeai package is required. Install with: pip install google-generativeai")
            except Exception as e:
                raise RuntimeError(f"Failed to initialize Gemini client: {e}")
        return self._client
    
    def detect_language(self, file_path: str) -> tuple[str, str]:
        """
        Detect the programming language and appropriate test framework.
        
        Args:
            file_path: Path to the source file
            
        Returns:
            Tuple of (language, framework)
        """
        ext = Path(file_path).suffix.lower()
        if ext in LANGUAGE_MAP:
            return LANGUAGE_MAP[ext]
        return ('unknown', 'unknown')
    
    def _build_prompt(self, filename: str, language: str, framework: str, code_content: str) -> str:
        """
        Build the prompt for test generation.
        
        Args:
            filename: Name of the source file
            language: Detected programming language
            framework: Test framework to use (pytest/jest)
            code_content: Content of the source file
            
        Returns:
            Formatted prompt string
        """
        # Calculate relative import path
        file_stem = Path(filename).stem
        
        prompt = f"""You are a QA automation expert. Generate a complete, executable unit test for the following code.

Generate an executable unit test for this file: {filename}
Language: {language}
Framework: {framework}

Code Content:
```{language}
{code_content}
```

Requirements:
1. Use relative imports to import the functions/classes from the source file.
   - For Python: Use `from .{file_stem} import ...` or adjust based on actual module structure
   - For JS/TS: Use relative path like `import {{ ... }} from './{file_stem}'`
2. Cover positive cases (expected behavior)
3. Cover negative cases (error handling, edge cases)
4. Cover edge cases (empty inputs, boundary values)
5. Include descriptive test names that explain what is being tested
6. Add comments explaining the purpose of each test

IMPORTANT: Output ONLY the raw code for the test file. No markdown formatting, no explanations, no code fences. Just the pure test code that can be saved directly to a file and executed."""

        return prompt
    
    def generate_test(self, file_path: str, file_content: str) -> Dict[str, Any]:
        """
        Generate a unit test for the given source file.
        
        Args:
            file_path: Path to the source file (used for language detection)
            file_content: Content of the source file
            
        Returns:
            Dictionary containing:
            - test_code: Generated test code string
            - language: Detected language
            - framework: Selected test framework
            - source_file: Original source file path
            - suggested_test_path: Suggested path for the test file
        """
        if not file_content or not file_content.strip():
            return {
                "error": "File content cannot be empty",
                "test_code": None,
                "source_file": file_path
            }
        
        # Detect language and framework
        language, framework = self.detect_language(file_path)
        
        if language == 'unknown':
            return {
                "error": f"Unsupported file type. Supported: .py, .js, .ts, .tsx, .jsx",
                "test_code": None,
                "source_file": file_path
            }
        
        # Check for API key
        if not self.api_key:
            return {
                "error": "GOOGLE_API_KEY not configured. Please set it in your .env file.",
                "test_code": None,
                "source_file": file_path
            }
        
        try:
            # Build prompt
            filename = Path(file_path).name
            prompt = self._build_prompt(filename, language, framework, file_content)
            
            # Call Gemini API
            client = self._get_client()
            response = client.generate_content(prompt)
            
            # Extract the generated test code
            test_code = response.text.strip()
            
            # Remove any markdown code fences if present (LLM sometimes ignores instructions)
            if test_code.startswith('```'):
                lines = test_code.split('\n')
                # Remove first line (```python or similar)
                lines = lines[1:]
                # Remove last line if it's ```
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                test_code = '\n'.join(lines)
            
            # Generate suggested test file path
            source_path = Path(file_path)
            if language == 'python':
                test_filename = f"test_{source_path.stem}.py"
            else:
                test_filename = f"{source_path.stem}.test{source_path.suffix}"
            
            suggested_test_path = f"generated_test_cases/{source_path.parent}/{test_filename}"
            
            return {
                "test_code": test_code,
                "language": language,
                "framework": framework,
                "source_file": file_path,
                "suggested_test_path": suggested_test_path,
                "success": True
            }
            
        except Exception as e:
            logger.error(f"Error generating test: {e}")
            return {
                "error": str(e),
                "test_code": None,
                "source_file": file_path,
                "success": False
            }


# Singleton instance for convenience
_generator: Optional[TestGenerator] = None


def get_generator() -> TestGenerator:
    """Get or create the singleton TestGenerator instance."""
    global _generator
    if _generator is None:
        _generator = TestGenerator()
    return _generator


def generate_unit_test(file_path: str, file_content: str) -> Dict[str, Any]:
    """
    Convenience function to generate a unit test.
    
    Args:
        file_path: Path to the source file
        file_content: Content of the source file
        
    Returns:
        Dictionary with test generation results
    """
    generator = get_generator()
    return generator.generate_test(file_path, file_content)
