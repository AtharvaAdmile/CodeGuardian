"""
AnswerGenerator module for generating natural language answers using LLM.
"""

import os
import time
from typing import List, Optional, Iterator
from dataclasses import dataclass
import google.generativeai as genai
from src.query_engine import CodeChunk, Message

@dataclass
class CodeSnippet:
    """Represents a formatted code snippet with metadata."""
    code: str
    file_path: str
    start_line: int
    end_line: int
    language: str


@dataclass
class Source:
    """Represents a source reference."""
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str


@dataclass
class Answer:
    """Represents a generated answer with metadata."""
    text: str
    code_snippets: List[CodeSnippet]
    sources: List[Source]
    confidence: float
    generation_time_ms: float


class AnswerGenerator:
    """
    Generates natural language answers using Google Gemini.
    
    Takes retrieved code chunks and conversation history to synthesize
    detailed, contextual answers with proper code formatting and citations.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3-flash-preview", max_retries: int = 2, retry_delay: float = 1.0):
        """
        Initialize the AnswerGenerator with Gemini API.
        
        Args:
            api_key: Gemini API key (defaults to GOOGLE_API_KEY environment variable)
            model: Model name to use (default: gemini-1.5-flash)
            max_retries: Maximum number of retry attempts for API failures
            retry_delay: Initial delay between retries in seconds (exponential backoff)
            
        Raises:
            ValueError: If API key is not provided
        """
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_API_KEY must be provided or set in environment")
        
        self.model_name = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction="You are a code expert helping developers understand their codebase."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Gemini client: {str(e)}")
    
    def generate_answer(
        self,
        question: str,
        context_chunks: List[CodeChunk],
        conversation_history: Optional[List[Message]] = None,
        stream: bool = False
    ) -> Answer:
        """
        Generate a natural language answer based on retrieved code chunks.
        
        Args:
            question: User's question
            context_chunks: Retrieved code chunks providing context
            conversation_history: Previous conversation messages
            stream: Whether to stream the response (default: False)
            
        Returns:
            Answer object containing the generated response and metadata
        """
        # Create the prompt with context and history
        prompt = self.create_prompt(question, context_chunks, conversation_history)
        
        # Generate answer using Gemini API
        if stream:
            return self._generate_streaming_answer(
                prompt, context_chunks, conversation_history
            )
        else:
            return self._generate_complete_answer(
                prompt, context_chunks, conversation_history
            )
    
    def generate_answer_stream(
        self,
        question: str,
        context_chunks: List[CodeChunk],
        conversation_history: Optional[List[Message]] = None
    ) -> Iterator[str]:
        """
        Generate a streaming answer for real-time display with retry logic.
        
        Args:
            question: User's question
            context_chunks: Retrieved code chunks providing context
            conversation_history: Previous conversation messages
            
        Yields:
            Chunks of the generated answer text
        """
        prompt = self.create_prompt(question, context_chunks, conversation_history)
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Create streaming generation
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=2048,
                    ),
                    stream=True
                )
                
                for chunk in response:
                    if chunk.text:
                        yield chunk.text
                
                # If we successfully streamed, return
                return
                        
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    yield f"\n\n⚠️ Connection error, retrying in {delay}s...\n\n"
                    time.sleep(delay)
                else:
                    yield f"\n\n**Error generating answer after {self.max_retries} attempts:** {str(last_error)}"
    
    def create_prompt(
        self,
        question: str,
        chunks: List[CodeChunk],
        conversation_history: Optional[List[Message]] = None
    ) -> str:
        """
        Create a structured prompt for the LLM with context and instructions.
        
        Args:
            question: User's question
            chunks: Code chunks providing context
            conversation_history: Previous conversation messages
            
        Returns:
            Formatted prompt string
        """
        # Format code chunks
        formatted_chunks = self._format_context_chunks(chunks)
        
        # Format conversation history
        history_text = ""
        if conversation_history and len(conversation_history) > 0:
            history_text = "\n\nPrevious conversation:\n"
            for msg in conversation_history[-6:]:  # Last 6 messages (3 turns)
                role = "User" if msg.role == "user" else "Assistant"
                history_text += f"{role}: {msg.content}\n"
        
        # Create the prompt
        prompt = f"""Context from codebase:
{formatted_chunks}
{history_text}

Question: {question}

Instructions:
- Provide a detailed, accurate answer based on the code context above
- Include relevant code snippets with file paths and line numbers
- Use markdown formatting for code blocks with appropriate language tags
- If the context doesn't contain enough information, clearly state what's missing
- Reference specific files and functions in your answer
- Be concise but thorough
- Format code snippets like: `file_path:start_line-end_line`

Answer:"""
        
        return prompt
    
    def format_code_snippet(self, chunk: CodeChunk) -> str:
        """
        Format a code chunk as a markdown code snippet with metadata.
        
        Args:
            chunk: CodeChunk to format
            
        Returns:
            Formatted markdown string with code and metadata
        """
        # Determine language for syntax highlighting
        lang_map = {
            "python": "python",
            "javascript": "javascript",
            "typescript": "typescript",
            "jsx": "jsx",
            "tsx": "tsx"
        }
        lang = lang_map.get(chunk.language.lower(), chunk.language.lower())
        
        # Format the snippet
        snippet = f"**File:** `{chunk.file_path}` (lines {chunk.start_line}-{chunk.end_line})\n\n"
        snippet += f"```{lang}\n{chunk.content}\n```"
        
        return snippet
    
    def _format_context_chunks(self, chunks: List[CodeChunk]) -> str:
        """
        Format all context chunks for inclusion in the prompt.
        
        Args:
            chunks: List of CodeChunk objects
            
        Returns:
            Formatted string with all chunks
        """
        if not chunks:
            return "No relevant code found in the codebase."
        
        formatted = []
        for i, chunk in enumerate(chunks, 1):
            formatted.append(f"\n--- Code Chunk {i} ---")
            formatted.append(f"File: {chunk.file_path}")
            formatted.append(f"Lines: {chunk.start_line}-{chunk.end_line}")
            formatted.append(f"Type: {chunk.chunk_type}")
            formatted.append(f"\n{chunk.content}\n")
        
        return "\n".join(formatted)
    
    def _generate_complete_answer(
        self,
        prompt: str,
        context_chunks: List[CodeChunk],
        conversation_history: Optional[List[Message]]
    ) -> Answer:
        """
        Generate a complete answer (non-streaming) with retry logic.
        
        Args:
            prompt: Formatted prompt
            context_chunks: Code chunks used for context
            conversation_history: Previous messages
            
        Returns:
            Complete Answer object
        """
        start_time = time.time()
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Generate answer
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.3,
                        max_output_tokens=2048,
                    )
                )
                
                answer_text = response.text
                generation_time = (time.time() - start_time) * 1000
                
                # Extract code snippets and sources
                code_snippets = [
                    CodeSnippet(
                        code=chunk.content,
                        file_path=chunk.file_path,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        language=chunk.language
                    )
                    for chunk in context_chunks
                ]
                
                sources = [
                    Source(
                        file_path=chunk.file_path,
                        start_line=chunk.start_line,
                        end_line=chunk.end_line,
                        chunk_type=chunk.chunk_type
                    )
                    for chunk in context_chunks
                ]
                
                # Calculate confidence based on chunk relevance
                confidence = self._calculate_confidence(context_chunks)
                
                return Answer(
                    text=answer_text,
                    code_snippets=code_snippets,
                    sources=sources,
                    confidence=confidence,
                    generation_time_ms=generation_time
                )
                
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    print(f"Answer generation failed (attempt {attempt + 1}/{self.max_retries}), retrying in {delay}s: {str(e)}")
                    time.sleep(delay)
                else:
                    # Return error answer after all retries exhausted
                    return Answer(
                        text=f"Error generating answer after {self.max_retries} attempts: {str(last_error)}",
                        code_snippets=[],
                        sources=[],
                        confidence=0.0,
                        generation_time_ms=(time.time() - start_time) * 1000
                    )
    
    def _generate_streaming_answer(
        self,
        prompt: str,
        context_chunks: List[CodeChunk],
        conversation_history: Optional[List[Message]]
    ) -> Answer:
        """
        Generate a streaming answer (collects all chunks).
        
        Args:
            prompt: Formatted prompt
            context_chunks: Code chunks used for context
            conversation_history: Previous messages
            
        Returns:
            Complete Answer object after streaming
        """
        start_time = time.time()
        
        answer_text = ""
        
        try:
            # Create streaming generation
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=2048,
                ),
                stream=True
            )
            
            for chunk in response:
                if chunk.text:
                    answer_text += chunk.text
            
            generation_time = (time.time() - start_time) * 1000
            
            # Extract code snippets and sources
            code_snippets = [
                CodeSnippet(
                    code=chunk.content,
                    file_path=chunk.file_path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    language=chunk.language
                )
                for chunk in context_chunks
            ]
            
            sources = [
                Source(
                    file_path=chunk.file_path,
                    start_line=chunk.start_line,
                    end_line=chunk.end_line,
                    chunk_type=chunk.chunk_type
                )
                for chunk in context_chunks
            ]
            
            confidence = self._calculate_confidence(context_chunks)
            
            return Answer(
                text=answer_text,
                code_snippets=code_snippets,
                sources=sources,
                confidence=confidence,
                generation_time_ms=generation_time
            )
            
        except Exception as e:
            return Answer(
                text=f"Error generating answer: {str(e)}",
                code_snippets=[],
                sources=[],
                confidence=0.0,
                generation_time_ms=(time.time() - start_time) * 1000
            )
    
    def _calculate_confidence(self, chunks: List[CodeChunk]) -> float:
        """
        Calculate confidence score based on retrieved chunks.
        
        Args:
            chunks: Retrieved code chunks
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        if not chunks:
            return 0.0
        
        # Base confidence on average distance (lower distance = higher confidence)
        avg_distance = sum(chunk.distance for chunk in chunks) / len(chunks) if chunks else 0
        
        # Normalize distance to confidence (assuming distance range 0-2)
        confidence = max(0.0, min(1.0, 1.0 - (avg_distance / 2.0)))
        
        # Boost confidence if we have multiple relevant chunks
        if len(chunks) >= 3:
            confidence = min(1.0, confidence * 1.1)
        
        return round(confidence, 2)
