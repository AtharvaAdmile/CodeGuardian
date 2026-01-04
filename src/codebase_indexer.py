"""
CodebaseIndexer module for coordinating the full indexing pipeline.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import uuid

from src.file_validator import FileValidator, ValidationResult
from src.code_parser import CodeParser
from src.text_chunker import TextChunker, CodeChunk
from src.embedding_generator import EmbeddingGenerator
from src.vector_store import VectorStore


@dataclass
class IndexingResult:
    """Result of indexing operation."""
    success: bool
    files_processed: int
    chunks_created: int
    errors: List[Dict[str, str]]
    collection_name: str


@dataclass
class FileToIndex:
    """Represents a file to be indexed."""
    file_path: str
    content: str
    file_size: int


class CodebaseIndexer:
    """
    Coordinates the full indexing pipeline for code files.
    
    Integrates FileValidator, CodeParser, TextChunker, EmbeddingGenerator,
    and VectorStore to process files and store embeddings.
    """
    
    def __init__(
        self,
        vector_store: Optional[VectorStore] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None,
        batch_size: int = 100
    ):
        """
        Initialize the CodebaseIndexer with required components.
        
        Args:
            vector_store: VectorStore instance (creates new if None)
            embedding_generator: EmbeddingGenerator instance (creates new if None)
            batch_size: Number of chunks to process in each batch
        """
        self.file_validator = FileValidator()
        self.code_parser = CodeParser()
        self.text_chunker = TextChunker()
        self.embedding_generator = embedding_generator or EmbeddingGenerator()
        self.vector_store = vector_store or VectorStore()
        self.batch_size = batch_size
    
    def index_files(
        self,
        files: List[FileToIndex],
        collection_name: str,
        progress_callback: Optional[callable] = None
    ) -> IndexingResult:
        """
        Index multiple files through the full pipeline.
        
        Args:
            files: List of FileToIndex objects to process
            collection_name: Name of the collection to store embeddings
            progress_callback: Optional callback function(current_file, processed_count, total_count)
            
        Returns:
            IndexingResult with processing statistics and errors
        """
        errors = []
        total_chunks = 0
        files_processed = 0
        
        # Create or get collection
        self.vector_store.create_collection(collection_name)
        
        # Process files in batches
        all_chunks = []
        
        for idx, file in enumerate(files):
            try:
                # Notify progress
                if progress_callback:
                    progress_callback(file.file_path, idx, len(files))
                
                # Validate file
                validation_result = self.file_validator.validate_file(
                    file.file_path,
                    file.file_size
                )
                
                if not validation_result.is_valid:
                    errors.append({
                        'file': file.file_path,
                        'error': validation_result.error_message,
                        'stage': 'validation'
                    })
                    continue
                
                # Parse file
                parsed_code = self.code_parser.parse_file(file.file_path, file.content)
                
                # Chunk code
                chunks = self.text_chunker.chunk_code(parsed_code)
                
                if not chunks:
                    errors.append({
                        'file': file.file_path,
                        'error': 'No chunks created from file',
                        'stage': 'chunking'
                    })
                    continue
                
                all_chunks.extend(chunks)
                files_processed += 1
                
                # Process in batches to avoid memory issues
                if len(all_chunks) >= self.batch_size:
                    batch_chunks = all_chunks[:self.batch_size]
                    all_chunks = all_chunks[self.batch_size:]
                    
                    success, error = self._process_chunk_batch(batch_chunks, collection_name)
                    if success:
                        total_chunks += len(batch_chunks)
                    else:
                        errors.append({
                            'file': 'batch_processing',
                            'error': error,
                            'stage': 'embedding'
                        })
                
            except Exception as e:
                errors.append({
                    'file': file.file_path,
                    'error': str(e),
                    'stage': 'processing'
                })
                continue
        
        # Process remaining chunks
        if all_chunks:
            success, error = self._process_chunk_batch(all_chunks, collection_name)
            if success:
                total_chunks += len(all_chunks)
            else:
                errors.append({
                    'file': 'final_batch',
                    'error': error,
                    'stage': 'embedding'
                })
        
        # Final progress notification
        if progress_callback:
            progress_callback(None, len(files), len(files))
        
        return IndexingResult(
            success=len(errors) == 0,
            files_processed=files_processed,
            chunks_created=total_chunks,
            errors=errors,
            collection_name=collection_name
        )
    
    def _process_chunk_batch(
        self,
        chunks: List[CodeChunk],
        collection_name: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Process a batch of chunks: generate embeddings and store in vector store.
        
        Args:
            chunks: List of CodeChunk objects to process
            collection_name: Name of the collection to store in
            
        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        try:
            # Extract text content for embedding
            texts = [chunk.content for chunk in chunks]
            
            # Generate embeddings in batch
            embeddings = self.embedding_generator.generate_batch_embeddings(texts)
            
            # Prepare metadata for storage
            metadatas = []
            for chunk in chunks:
                metadata = {
                    'file_path': chunk.metadata.file_path,
                    'start_line': chunk.metadata.start_line,
                    'end_line': chunk.metadata.end_line,
                    'chunk_type': chunk.metadata.chunk_type,
                    'language': chunk.metadata.language,
                }
                
                # Add optional fields if present
                if chunk.metadata.function_name:
                    metadata['function_name'] = chunk.metadata.function_name
                if chunk.metadata.class_name:
                    metadata['class_name'] = chunk.metadata.class_name
                
                metadatas.append(metadata)
            
            # Generate unique IDs for each chunk
            ids = [str(uuid.uuid4()) for _ in range(len(chunks))]
            
            # Store in vector store
            self.vector_store.add_embeddings(
                collection_name=collection_name,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids
            )
            
            return True, None
            
        except Exception as e:
            return False, str(e)
