"""
TextChunker module for semantic code chunking.
"""

from typing import List, Dict, Any
from dataclasses import dataclass
from src.code_parser import ParsedCode, CodeBlock


@dataclass
class ChunkMetadata:
    """Metadata for a code chunk."""
    file_path: str
    start_line: int
    end_line: int
    chunk_type: str  # 'function', 'class', 'method', 'block'
    language: str
    function_name: str = ""
    class_name: str = ""


@dataclass
class CodeChunk:
    """Represents a chunk of code with metadata."""
    content: str
    metadata: ChunkMetadata
    token_count: int


class TextChunker:
    """
    Chunks code into semantic pieces suitable for embedding.
    
    Prioritizes function and class boundaries for semantic chunking.
    Falls back to line-based chunking for large blocks.
    Maintains chunk sizes between 100-500 tokens with 50 token overlap.
    """
    
    MIN_CHUNK_TOKENS = 100
    MAX_CHUNK_TOKENS = 500
    OVERLAP_TOKENS = 50
    
    def chunk_code(self, parsed: ParsedCode) -> List[CodeChunk]:
        """
        Chunk parsed code into semantic pieces.
        
        Args:
            parsed: ParsedCode object from CodeParser
            
        Returns:
            List of CodeChunk objects
        """
        chunks = []
        
        # First, try to chunk by functions and classes
        for func in parsed.functions:
            chunk = self._create_chunk_from_block(func, parsed)
            
            # If chunk is too large, split it
            if chunk.token_count > self.MAX_CHUNK_TOKENS:
                sub_chunks = self._split_large_chunk(chunk)
                chunks.extend(sub_chunks)
            else:
                chunks.append(chunk)
        
        for cls in parsed.classes:
            chunk = self._create_chunk_from_block(cls, parsed)
            
            # If chunk is too large, split it
            if chunk.token_count > self.MAX_CHUNK_TOKENS:
                sub_chunks = self._split_large_chunk(chunk)
                chunks.extend(sub_chunks)
            else:
                chunks.append(chunk)
        
        # If no functions or classes found, do line-based chunking
        if not chunks:
            chunks = self._line_based_chunking(parsed)
        
        return chunks
    
    def create_chunk(self, content: str, metadata: ChunkMetadata) -> CodeChunk:
        """
        Create a code chunk with metadata.
        
        Args:
            content: Code content
            metadata: ChunkMetadata object
            
        Returns:
            CodeChunk object
        """
        token_count = self.estimate_tokens(content)
        
        return CodeChunk(
            content=content,
            metadata=metadata,
            token_count=token_count
        )
    
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count using simple tokenization.
        
        Uses whitespace and punctuation splitting as approximation.
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        if not text:
            return 0
        
        # Simple tokenization: split by whitespace and count
        # This is an approximation; actual tokenization may differ
        tokens = text.split()
        
        # Add extra tokens for punctuation and special characters
        # Rough estimate: 1.3x multiplier for code
        estimated = int(len(tokens) * 1.3)
        
        return estimated
    
    def _create_chunk_from_block(self, block: CodeBlock, parsed: ParsedCode) -> CodeChunk:
        """Create a chunk from a code block."""
        metadata = ChunkMetadata(
            file_path=parsed.file_path,
            start_line=block.start_line,
            end_line=block.end_line,
            chunk_type=block.block_type,
            language=parsed.language,
            function_name=block.name if block.block_type in ['function', 'method'] else "",
            class_name=block.parent_class or (block.name if block.block_type == 'class' else "")
        )
        
        return self.create_chunk(block.content, metadata)
    
    def _split_large_chunk(self, chunk: CodeChunk) -> List[CodeChunk]:
        """
        Split a large chunk into smaller chunks with overlap.
        
        Args:
            chunk: CodeChunk that exceeds MAX_CHUNK_TOKENS
            
        Returns:
            List of smaller CodeChunk objects
        """
        lines = chunk.content.splitlines()
        sub_chunks = []
        
        # Calculate lines per chunk based on token estimate
        avg_tokens_per_line = chunk.token_count / len(lines) if lines else 1
        lines_per_chunk = int(self.MAX_CHUNK_TOKENS / avg_tokens_per_line)
        overlap_lines = int(self.OVERLAP_TOKENS / avg_tokens_per_line)
        
        # Ensure minimum chunk size
        if lines_per_chunk < 10:
            lines_per_chunk = 10
        if overlap_lines < 2:
            overlap_lines = 2
        
        i = 0
        while i < len(lines):
            end_idx = min(i + lines_per_chunk, len(lines))
            chunk_lines = lines[i:end_idx]
            chunk_content = '\n'.join(chunk_lines)
            
            # Create metadata for sub-chunk
            metadata = ChunkMetadata(
                file_path=chunk.metadata.file_path,
                start_line=chunk.metadata.start_line + i,
                end_line=chunk.metadata.start_line + end_idx - 1,
                chunk_type='block',
                language=chunk.metadata.language,
                function_name=chunk.metadata.function_name,
                class_name=chunk.metadata.class_name
            )
            
            sub_chunk = self.create_chunk(chunk_content, metadata)
            sub_chunks.append(sub_chunk)
            
            # Move forward with overlap
            i += lines_per_chunk - overlap_lines
            
            # Prevent infinite loop
            if i >= len(lines) - overlap_lines:
                break
        
        return sub_chunks

    def _line_based_chunking(self, parsed: ParsedCode) -> List[CodeChunk]:
        """
        Fallback line-based chunking when no functions/classes found.
        
        Args:
            parsed: ParsedCode object
            
        Returns:
            List of CodeChunk objects
        """
        chunks = []
        lines = parsed.content.splitlines()
        
        if not lines:
            return chunks
        
        # Estimate tokens per line
        total_tokens = self.estimate_tokens(parsed.content)
        avg_tokens_per_line = total_tokens / len(lines) if lines else 1
        
        # Calculate lines per chunk
        lines_per_chunk = int(self.MAX_CHUNK_TOKENS / avg_tokens_per_line)
        overlap_lines = int(self.OVERLAP_TOKENS / avg_tokens_per_line)
        
        # Ensure minimum values
        if lines_per_chunk < 10:
            lines_per_chunk = 10
        if overlap_lines < 2:
            overlap_lines = 2
        
        i = 0
        while i < len(lines):
            end_idx = min(i + lines_per_chunk, len(lines))
            chunk_lines = lines[i:end_idx]
            chunk_content = '\n'.join(chunk_lines)
            
            # Skip empty chunks
            if not chunk_content.strip():
                i += lines_per_chunk - overlap_lines
                continue
            
            metadata = ChunkMetadata(
                file_path=parsed.file_path,
                start_line=i + 1,
                end_line=end_idx,
                chunk_type='block',
                language=parsed.language
            )
            
            chunk = self.create_chunk(chunk_content, metadata)
            
            # Only add chunks that meet minimum token requirement
            if chunk.token_count >= self.MIN_CHUNK_TOKENS or end_idx == len(lines):
                chunks.append(chunk)
            
            # Move forward with overlap
            i += lines_per_chunk - overlap_lines
            
            # Prevent infinite loop
            if i >= len(lines) - overlap_lines:
                break
        
        return chunks
