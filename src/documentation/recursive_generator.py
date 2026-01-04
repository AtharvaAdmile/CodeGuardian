import os
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
import logging
import google.generativeai as genai

# Attempt to import gitingest, handle if not present (though added to requirements)
try:
    from gitingest import ingest
except ImportError:
    ingest = None

class RecursiveDocumentationGenerator:
    """
    Generates documentation recursively for a directory structure using a bottom-up approach.
    """

    def __init__(self, api_key: str = None, vector_store: Any = None):
        """
        Initialize the RecursiveDocumentationGenerator with Gemini.

        Args:
            api_key: API key for Google Gemini
            vector_store: The vector store instance (stubbed for now).
        """
        self.vector_store = vector_store
        self.logger = logging.getLogger(__name__)
        
        # Use provided api_key or look for GOOGLE_API_KEY env var
        api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY required for Gemini documentation generation")
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-3-flash-preview')

    def generate_docs_recursively(self, directory_path: str | Path) -> str:
        """
        Recursively generates documentation for the given directory using Post-Order Traversal.

        Args:
            directory_path: The path to the directory to document.

        Returns:
            The generated SUMMARY.md content for the directory.
        """
        path = Path(directory_path).resolve()
        
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Invalid directory path: {path}")

        self.logger.info(f"Processing directory: {path}")

        # 1. Identify sub-directories and files
        sub_directories = []
        for item in path.iterdir():
            if item.is_dir() and not self._is_ignored(item):
                sub_directories.append(item)

        # 2. Recursively process sub-directories (Post-Order Traversal)
        child_summaries = {}
        for sub_dir in sub_directories:
            try:
                summary = self.generate_docs_recursively(sub_dir)
                child_summaries[sub_dir.name] = summary
            except Exception as e:
                self.logger.error(f"Error processing subdirectory {sub_dir}: {e}")
                child_summaries[sub_dir.name] = f"Error generating summary: {e}"

        # 3. Context Aggregation
        # 3a. Get local file content using gitingest
        local_code_context = self._get_local_context(path)

        # 3b. Combine with child summaries
        combined_context = self._construct_prompt(path.name, local_code_context, child_summaries)

        # 4. Generate SUMMARY.md
        summary_md = self._generate_summary_llm(path.name, combined_context)

        # 5. Store in Vector Store (Stub)
        self._store_in_vector_store(summary_md, path)

        return summary_md

    def _get_local_context(self, path: Path) -> str:
        """
        Extracts text content of local files using gitingest.
        Excludes sub-directories to ensure we only get 'leaf nodes' relative to this folder.
        """
        if ingest is None:
            return "Error: gitingest module not found."
        
        try:
            # We want to exclude subdirectories from gitingest's recursion
            # because we are handling them manually.
            exclude_patterns = [str(p.name) for p in path.iterdir() if p.is_dir()]
            
            # Add standard ignores
            exclude_patterns.extend(['.git', '__pycache__', 'node_modules', '*.pyc'])

            summary, tree, content = ingest(str(path), exclude_patterns=exclude_patterns)
            
            return content
        except Exception as e:
            self.logger.error(f"Error using gitingest on {path}: {e}")
            # Fallback: Manual read if gitingest fails or API is different
            return self._manual_read_files(path)

    def _manual_read_files(self, path: Path) -> str:
        """Fallback to read files manually if gitingest fails."""
        content = []
        for item in path.iterdir():
            if item.is_file() and not self._is_ignored(item):
                try:
                    text = item.read_text(encoding='utf-8', errors='ignore')
                    content.append(f"File: {item.name}\n```\n{text}\n```\n")
                except Exception:
                    pass
        return "\n".join(content)

    def _construct_prompt(self, folder_name: str, local_code: str, child_summaries: Dict[str, str]) -> str:
        """Constructs the prompt for the LLM."""
        prompt = f"# Documentation Generation for Folder: {folder_name}\n\n"
        
        prompt += "## Local File Contents\n"
        prompt += local_code + "\n\n"
        
        prompt += "## Sub-module Summaries\n"
        for name, summary in child_summaries.items():
            prompt += f"### Sub-module: {name}\n{summary}\n\n"
            
        prompt += "\n---\n"
        prompt += "Analyze the local code and the provided summaries of sub-modules. "
        prompt += "Write a high-level technical documentation (SUMMARY.md) for this specific folder "
        prompt += "that abstracts implementation details but preserves architectural relationships.\n"
        
        return prompt

    def _generate_summary_llm(self, folder_name: str, prompt: str) -> str:
        """Generates the summary using Gemini."""
        try:
            # Prepend system instruction for Gemini
            full_prompt = "You are an expert software architect. Create concise, high-level technical documentation.\n\n" + prompt
            response = self.model.generate_content(full_prompt)
            return response.text
                 
        except Exception as e:
            self.logger.error(f"LLM generation failed for {folder_name}: {e}")
            return f"Error generating documentation for {folder_name}."

    def _store_in_vector_store(self, summary: str, path: Path):
        """Stub for storing in vector store."""
        # In a real implementation, this would chunk and embed the summary
        # and store it with metadata={'path': str(path), 'type': 'summary'}
        if self.vector_store:
            # self.vector_store.add_document(summary, metadata={"path": str(path)})
            pass
        # For now, we might just save it to a file for verification
        summary_path = path / "SUMMARY.md"
        try:
            summary_path.write_text(summary, encoding='utf-8')
        except Exception as e:
             self.logger.error(f"Failed to write SUMMARY.md to {path}: {e}")

    def _is_ignored(self, path: Path) -> bool:
        """Check if a path should be ignored."""
        ignored_names = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.env', '.DS_Store'}
        return path.name in ignored_names or path.name.startswith('.')


