"""
Input validation and sanitization utilities.
"""

import re
import os
from typing import Tuple


class InputValidator:
    """
    Validates and sanitizes user inputs to prevent security issues and ensure data quality.
    """
    
    # Collection name validation
    COLLECTION_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
    MAX_COLLECTION_NAME_LENGTH = 63
    MIN_COLLECTION_NAME_LENGTH = 1
    
    # Question validation
    MAX_QUESTION_LENGTH = 2000
    MIN_QUESTION_LENGTH = 3
    
    # File path validation
    DANGEROUS_PATH_PATTERNS = [
        r'\.\.',  # Parent directory traversal
        r'^/',    # Absolute paths
        r'^\\',   # Windows absolute paths
        r'~',     # Home directory
        r'\$',    # Environment variables
    ]
    
    @staticmethod
    def validate_collection_name(name: str) -> Tuple[bool, str]:
        """
        Validate collection name for ChromaDB.
        
        Collection names must be:
        - Alphanumeric with underscores and hyphens only
        - Between 1 and 63 characters
        - Not empty or whitespace only
        
        Args:
            name: Collection name to validate
            
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        if not name:
            return False, "Collection name cannot be empty"
        
        # Remove leading/trailing whitespace
        name = name.strip()
        
        if not name:
            return False, "Collection name cannot be whitespace only"
        
        if len(name) < InputValidator.MIN_COLLECTION_NAME_LENGTH:
            return False, f"Collection name must be at least {InputValidator.MIN_COLLECTION_NAME_LENGTH} character"
        
        if len(name) > InputValidator.MAX_COLLECTION_NAME_LENGTH:
            return False, f"Collection name must be at most {InputValidator.MAX_COLLECTION_NAME_LENGTH} characters"
        
        if not InputValidator.COLLECTION_NAME_PATTERN.match(name):
            return False, "Collection name can only contain letters, numbers, underscores, and hyphens"
        
        # Check for reserved names
        reserved_names = ['con', 'prn', 'aux', 'nul', 'com1', 'com2', 'com3', 'com4', 
                         'lpt1', 'lpt2', 'lpt3']
        if name.lower() in reserved_names:
            return False, f"'{name}' is a reserved name and cannot be used"
        
        return True, ""
    
    @staticmethod
    def sanitize_collection_name(name: str) -> str:
        """
        Sanitize collection name by removing invalid characters.
        
        Args:
            name: Collection name to sanitize
            
        Returns:
            Sanitized collection name
        """
        if not name:
            return "default_collection"
        
        # Remove leading/trailing whitespace
        name = name.strip()
        
        # Replace spaces with underscores
        name = name.replace(' ', '_')
        
        # Remove invalid characters
        name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
        
        # Ensure it's not empty after sanitization
        if not name:
            return "default_collection"
        
        # Truncate if too long
        if len(name) > InputValidator.MAX_COLLECTION_NAME_LENGTH:
            name = name[:InputValidator.MAX_COLLECTION_NAME_LENGTH]
        
        return name
    
    @staticmethod
    def validate_question(question: str) -> Tuple[bool, str]:
        """
        Validate user question input.
        
        Questions must be:
        - Non-empty
        - Between 3 and 2000 characters
        - Not just whitespace
        
        Args:
            question: Question text to validate
            
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        if not question:
            return False, "Question cannot be empty"
        
        # Remove leading/trailing whitespace for validation
        question_stripped = question.strip()
        
        if not question_stripped:
            return False, "Question cannot be whitespace only"
        
        if len(question_stripped) < InputValidator.MIN_QUESTION_LENGTH:
            return False, f"Question must be at least {InputValidator.MIN_QUESTION_LENGTH} characters"
        
        if len(question_stripped) > InputValidator.MAX_QUESTION_LENGTH:
            return False, f"Question must be at most {InputValidator.MAX_QUESTION_LENGTH} characters"
        
        return True, ""
    
    @staticmethod
    def sanitize_question(question: str) -> str:
        """
        Sanitize question by trimming whitespace and limiting length.
        
        Args:
            question: Question text to sanitize
            
        Returns:
            Sanitized question text
        """
        if not question:
            return ""
        
        # Remove leading/trailing whitespace
        question = question.strip()
        
        # Normalize internal whitespace (replace multiple spaces with single space)
        question = re.sub(r'\s+', ' ', question)
        
        # Truncate if too long
        if len(question) > InputValidator.MAX_QUESTION_LENGTH:
            question = question[:InputValidator.MAX_QUESTION_LENGTH]
        
        return question
    
    @staticmethod
    def validate_file_path(file_path: str) -> Tuple[bool, str]:
        """
        Validate file path to prevent directory traversal attacks.
        
        File paths must:
        - Not contain parent directory references (..)
        - Not be absolute paths
        - Not contain dangerous characters or patterns
        
        Args:
            file_path: File path to validate
            
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        if not file_path:
            return False, "File path cannot be empty"
        
        # Check for dangerous patterns
        for pattern in InputValidator.DANGEROUS_PATH_PATTERNS:
            if re.search(pattern, file_path):
                return False, f"File path contains dangerous pattern: {pattern}"
        
        # Normalize the path and check if it tries to escape
        try:
            normalized = os.path.normpath(file_path)
            
            # Check if normalized path tries to go up directories
            if normalized.startswith('..') or '/..' in normalized or '\\..' in normalized:
                return False, "File path cannot reference parent directories"
            
            # Check if it's an absolute path
            if os.path.isabs(normalized):
                return False, "File path must be relative, not absolute"
                
        except Exception as e:
            return False, f"Invalid file path: {str(e)}"
        
        return True, ""
    
    @staticmethod
    def sanitize_file_path(file_path: str) -> str:
        """
        Sanitize file path by removing dangerous components.
        
        Args:
            file_path: File path to sanitize
            
        Returns:
            Sanitized file path (basename only for safety)
        """
        if not file_path:
            return ""
        
        # Get just the filename (basename) to prevent directory traversal
        # This is the safest approach for uploaded files
        sanitized = os.path.basename(file_path)
        
        # Remove any remaining dangerous characters
        sanitized = re.sub(r'[^\w\s\-\.]', '_', sanitized)
        
        return sanitized
    
    @staticmethod
    def validate_api_key(api_key: str) -> Tuple[bool, str]:
        """
        Validate API key format.
        
        Args:
            api_key: API key to validate
            
        Returns:
            Tuple of (is_valid: bool, error_message: str)
        """
        if not api_key:
            return False, "API key cannot be empty"
        
        api_key = api_key.strip()
        
        if not api_key:
            return False, "API key cannot be whitespace only"
        
        if len(api_key) < 10:
            return False, "API key appears to be too short"
        
        # Check for common placeholder values
        placeholder_values = ['your_api_key', 'api_key_here', 'xxx', 'test', 'placeholder']
        if api_key.lower() in placeholder_values:
            return False, "API key appears to be a placeholder value"
        
        return True, ""
