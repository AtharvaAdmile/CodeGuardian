"""
Input validation utilities for CodeGuardian CLI.
"""

import re
import os
from typing import Tuple, Optional


def validate_project_path(path: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a project directory path.
    
    Args:
        path: Path to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not path:
        return False, "Path cannot be empty"
    
    abs_path = os.path.abspath(os.path.expanduser(path))
    
    if not os.path.exists(abs_path):
        return False, f"Path does not exist: {abs_path}"
    
    if not os.path.isdir(abs_path):
        return False, f"Path is not a directory: {abs_path}"
    
    return True, None


def validate_collection_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a collection/project name.
    
    Args:
        name: Name to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not name:
        return False, "Name cannot be empty"
    
    if len(name) < 3:
        return False, "Name must be at least 3 characters"
    
    if len(name) > 64:
        return False, "Name must be at most 64 characters"
    
    # Allow alphanumeric, underscores, and hyphens
    if not re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', name):
        return False, "Name must start with a letter and contain only letters, numbers, underscores, and hyphens"
    
    return True, None


def validate_question(question: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a user question.
    
    Args:
        question: Question to validate
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not question:
        return False, "Question cannot be empty"
    
    if len(question) < 5:
        return False, "Question is too short"
    
    if len(question) > 2000:
        return False, "Question is too long (max 2000 characters)"
    
    return True, None


def sanitize_project_name(name: str) -> str:
    """
    Sanitize a project name for use as identifier.
    
    Args:
        name: Name to sanitize
        
    Returns:
        Sanitized name
    """
    # Replace spaces and special chars with underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    
    # Ensure starts with letter
    if sanitized and not sanitized[0].isalpha():
        sanitized = 'p_' + sanitized
    
    # Truncate if too long
    if len(sanitized) > 64:
        sanitized = sanitized[:64]
    
    return sanitized.lower()


def get_absolute_path(path: str) -> str:
    """
    Get absolute path from potentially relative path.
    
    Args:
        path: Path to resolve
        
    Returns:
        Absolute path
    """
    return os.path.abspath(os.path.expanduser(path))
