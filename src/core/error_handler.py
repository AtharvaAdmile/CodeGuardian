"""
Error handler module for CodeGuardian.

Provides central error handling with severity levels and retry logic.
"""

from enum import Enum
from typing import Optional, Callable, TypeVar, Any
import logging
import time
from functools import wraps

logger = logging.getLogger(__name__)

T = TypeVar('T')


class ErrorSeverity(Enum):
    """Error severity levels."""
    WARNING = "warning"      # Log but continue
    RECOVERABLE = "recoverable"  # Retry or fallback
    FATAL = "fatal"          # Stop execution


class CodeGuardianError(Exception):
    """Base exception for all CodeGuardian errors."""
    
    def __init__(self, message: str, severity: ErrorSeverity = ErrorSeverity.RECOVERABLE):
        self.message = message
        self.severity = severity
        super().__init__(message)


class APIError(CodeGuardianError):
    """LLM API failures (Gemini, etc.)."""
    
    def __init__(self, message: str):
        super().__init__(message, ErrorSeverity.RECOVERABLE)


class DatabaseError(CodeGuardianError):
    """Supabase connection/query failures."""
    
    def __init__(self, message: str):
        super().__init__(message, ErrorSeverity.RECOVERABLE)


class FileOperationError(CodeGuardianError):
    """File read/write failures."""
    
    def __init__(self, message: str):
        super().__init__(message, ErrorSeverity.FATAL)


class ConfigurationError(CodeGuardianError):
    """Configuration/environment errors."""
    
    def __init__(self, message: str):
        super().__init__(message, ErrorSeverity.FATAL)


def handle_error(error: Exception, context: str) -> Optional[str]:
    """
    Central error handler.
    
    Args:
        error: The exception that occurred
        context: Description of where the error occurred
        
    Returns:
        User-friendly error message if recoverable, None if handled
        
    Raises:
        Exception if fatal
    """
    if isinstance(error, APIError):
        logger.error(f"API Error in {context}: {error.message}")
        return "LLM API unavailable. Check your API key and internet connection."
    
    elif isinstance(error, DatabaseError):
        logger.error(f"Database Error in {context}: {error.message}")
        return "Supabase connection failed. Check your credentials in .env file."
    
    elif isinstance(error, FileOperationError):
        logger.error(f"File Error in {context}: {error.message}")
        raise error  # Fatal, stop execution
    
    elif isinstance(error, ConfigurationError):
        logger.error(f"Config Error in {context}: {error.message}")
        raise error  # Fatal, stop execution
    
    else:
        logger.exception(f"Unexpected error in {context}")
        return f"Unexpected error: {str(error)}"


def retry_on_failure(
    max_retries: int = 3,
    delay_seconds: float = 2.0,
    exceptions: tuple = (APIError, DatabaseError)
):
    """
    Decorator for retrying failed operations with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay_seconds: Initial delay between retries (doubles each retry)
        exceptions: Tuple of exception types to catch and retry
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error: Optional[Exception] = None
            
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        delay = delay_seconds * (2 ** attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{max_retries} after error: {e}. "
                            f"Waiting {delay}s..."
                        )
                        time.sleep(delay)
                    continue
            
            # All retries exhausted
            if last_error:
                raise last_error
            raise RuntimeError("Retry failed with no error captured")
        
        return wrapper
    return decorator
