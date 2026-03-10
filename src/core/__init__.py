"""
CodeGuardian core module.
"""

from src.core.error_handler import (
    ErrorSeverity,
    CodeGuardianError,
    APIError,
    DatabaseError,
    FileOperationError,
    ConfigurationError,
    handle_error,
    retry_on_failure,
)

__all__ = [
    "ErrorSeverity",
    "CodeGuardianError",
    "APIError",
    "DatabaseError",
    "FileOperationError",
    "ConfigurationError",
    "handle_error",
    "retry_on_failure",
]
