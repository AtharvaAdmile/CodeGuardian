"""
Error Handler for robust error management in documentation generation.

This module provides centralized error handling, categorization, and recovery
mechanisms for the documentation generation workflow. It distinguishes between
recoverable and non-recoverable errors and provides detailed context for debugging.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from src.models.documentation_models import (
    ErrorInfo,
    CodeElement,
    ElementContext,
    DocumentationItem
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categories of errors for classification."""
    PARSING_ERROR = "parsing"
    CONTEXT_ANALYSIS_ERROR = "context_analysis"
    LLM_GENERATION_ERROR = "llm_generation"
    EXPORT_ERROR = "export"
    CONFIGURATION_ERROR = "configuration"
    RESOURCE_ERROR = "resource"
    UNKNOWN_ERROR = "unknown"


class ErrorSeverity(Enum):
    """Severity levels for errors."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorHandler:
    """
    Centralized error handler for documentation generation workflow.
    
    This class provides methods to handle, categorize, log, and recover from
    errors that occur during different stages of the documentation generation
    process. It maintains error history and provides recovery recommendations.
    
    Attributes:
        error_history: List of all errors encountered
        recoverable_errors: Set of error types that can be retried
        retry_callbacks: Dict mapping stage to retry callback functions
    """
    
    def __init__(self):
        """Initialize the error handler."""
        self.error_history: List[ErrorInfo] = []
        
        # Define which error types are recoverable
        self.recoverable_errors = {
            ErrorCategory.LLM_GENERATION_ERROR,
            ErrorCategory.CONTEXT_ANALYSIS_ERROR,
            ErrorCategory.EXPORT_ERROR
        }
        
        # Callbacks for retrying failed operations
        self.retry_callbacks: Dict[str, Callable] = {}
    
    def handle_error(
        self,
        error: Exception,
        stage: str,
        context: Dict[str, Any],
        element_id: Optional[str] = None,
        file_path: Optional[str] = None
    ) -> ErrorInfo:
        """
        Handle an error by categorizing it and creating an ErrorInfo object.
        
        This method analyzes the error, determines its type and severity,
        decides if it's recoverable, and logs it with full context for debugging.
        
        Args:
            error: The exception that was raised
            stage: Current stage of processing ('analysis', 'context', 'generation', 'export')
            context: Additional context information about the error
            element_id: Optional ID of the code element being processed
            file_path: Optional path to the file being processed
        
        Returns:
            ErrorInfo object with categorized error information and recovery recommendations
        """
        # Categorize the error
        error_type = self._categorize_error(error, stage)
        
        # Determine severity
        severity = self._determine_severity(error_type, stage)
        
        # Check if recoverable
        recoverable = self._is_recoverable(error_type, error)
        
        # Create error message with context
        error_message = self._format_error_message(error, context)
        
        # Create ErrorInfo object
        error_info = ErrorInfo(
            error_type=error_type.value,
            stage=stage,
            element_id=element_id,
            file_path=file_path,
            error_message=error_message,
            timestamp=datetime.now(),
            recoverable=recoverable
        )
        
        # Log the error
        self._log_error(error_info, severity, error)
        
        # Store in history
        self.error_history.append(error_info)
        
        return error_info
    
    def retry_failed_elements(
        self,
        session_id: str,
        element_ids: List[str],
        retry_callback: Callable[[str], Optional[DocumentationItem]]
    ) -> Dict[str, bool]:
        """
        Re-attempt documentation generation for failed elements.
        
        This method attempts to regenerate documentation for elements that
        previously failed, using the provided retry callback function.
        
        Args:
            session_id: ID of the documentation session
            element_ids: List of element IDs to retry
            retry_callback: Function that takes an element_id and returns
                          a DocumentationItem if successful, None if failed
        
        Returns:
            Dict mapping element_id to success status (True if retry succeeded)
        """
        results: Dict[str, bool] = {}
        
        logger.info(f"Retrying {len(element_ids)} failed elements for session {session_id}")
        
        for element_id in element_ids:
            try:
                # Attempt to regenerate documentation
                result = retry_callback(element_id)
                
                if result is not None:
                    results[element_id] = True
                    logger.info(f"Successfully retried element {element_id}")
                else:
                    results[element_id] = False
                    logger.warning(f"Retry failed for element {element_id}")
                    
            except Exception as e:
                results[element_id] = False
                logger.error(f"Exception during retry for element {element_id}: {str(e)}")
                
                # Create error info for the retry failure
                error_info = self.handle_error(
                    error=e,
                    stage="retry",
                    context={"session_id": session_id, "element_id": element_id},
                    element_id=element_id
                )
        
        success_count = sum(1 for success in results.values() if success)
        logger.info(f"Retry complete: {success_count}/{len(element_ids)} succeeded")
        
        return results
    
    def get_errors_by_stage(self, stage: str) -> List[ErrorInfo]:
        """
        Get all errors for a specific stage.
        
        Args:
            stage: Stage name to filter by
        
        Returns:
            List of ErrorInfo objects for the specified stage
        """
        return [error for error in self.error_history if error.stage == stage]
    
    def get_recoverable_errors(self) -> List[ErrorInfo]:
        """
        Get all recoverable errors from history.
        
        Returns:
            List of ErrorInfo objects that are marked as recoverable
        """
        return [error for error in self.error_history if error.recoverable]
    
    def get_errors_by_file(self, file_path: str) -> List[ErrorInfo]:
        """
        Get all errors for a specific file.
        
        Args:
            file_path: File path to filter by
        
        Returns:
            List of ErrorInfo objects for the specified file
        """
        return [error for error in self.error_history if error.file_path == file_path]
    
    def get_error_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all errors.
        
        Returns:
            Dict with error statistics and categorization
        """
        total_errors = len(self.error_history)
        
        if total_errors == 0:
            return {
                "total_errors": 0,
                "by_stage": {},
                "by_type": {},
                "recoverable_count": 0,
                "non_recoverable_count": 0
            }
        
        # Count by stage
        by_stage: Dict[str, int] = {}
        for error in self.error_history:
            by_stage[error.stage] = by_stage.get(error.stage, 0) + 1
        
        # Count by type
        by_type: Dict[str, int] = {}
        for error in self.error_history:
            by_type[error.error_type] = by_type.get(error.error_type, 0) + 1
        
        # Count recoverable vs non-recoverable
        recoverable_count = sum(1 for error in self.error_history if error.recoverable)
        non_recoverable_count = total_errors - recoverable_count
        
        return {
            "total_errors": total_errors,
            "by_stage": by_stage,
            "by_type": by_type,
            "recoverable_count": recoverable_count,
            "non_recoverable_count": non_recoverable_count
        }
    
    def clear_history(self) -> None:
        """Clear the error history."""
        self.error_history.clear()
        logger.info("Error history cleared")
    
    def _categorize_error(self, error: Exception, stage: str) -> ErrorCategory:
        """
        Categorize an error based on its type and stage.
        
        Args:
            error: The exception to categorize
            stage: Current processing stage
        
        Returns:
            ErrorCategory enum value
        """
        error_type_name = type(error).__name__
        error_message = str(error).lower()
        
        # Check for specific error patterns
        if stage == "analysis":
            if "parse" in error_message or "syntax" in error_message:
                return ErrorCategory.PARSING_ERROR
            return ErrorCategory.PARSING_ERROR
        
        elif stage == "context":
            return ErrorCategory.CONTEXT_ANALYSIS_ERROR
        
        elif stage == "generation":
            if "api" in error_message or "rate limit" in error_message or "timeout" in error_message:
                return ErrorCategory.LLM_GENERATION_ERROR
            return ErrorCategory.LLM_GENERATION_ERROR
        
        elif stage == "export":
            if "permission" in error_message or "file" in error_message or "directory" in error_message:
                return ErrorCategory.EXPORT_ERROR
            return ErrorCategory.EXPORT_ERROR
        
        # Check for resource errors
        if "memory" in error_message or "resource" in error_message:
            return ErrorCategory.RESOURCE_ERROR
        
        # Check for configuration errors
        if "config" in error_message or "setting" in error_message:
            return ErrorCategory.CONFIGURATION_ERROR
        
        return ErrorCategory.UNKNOWN_ERROR
    
    def _determine_severity(self, error_type: ErrorCategory, stage: str) -> ErrorSeverity:
        """
        Determine the severity of an error.
        
        Args:
            error_type: Categorized error type
            stage: Current processing stage
        
        Returns:
            ErrorSeverity enum value
        """
        # Critical errors that stop the entire workflow
        if error_type == ErrorCategory.CONFIGURATION_ERROR:
            return ErrorSeverity.CRITICAL
        
        if error_type == ErrorCategory.RESOURCE_ERROR:
            return ErrorSeverity.HIGH
        
        # High severity for analysis stage (affects everything downstream)
        if stage == "analysis" and error_type == ErrorCategory.PARSING_ERROR:
            return ErrorSeverity.HIGH
        
        # Medium severity for context and generation (affects single elements)
        if error_type in [ErrorCategory.CONTEXT_ANALYSIS_ERROR, ErrorCategory.LLM_GENERATION_ERROR]:
            return ErrorSeverity.MEDIUM
        
        # Low severity for export (can be retried easily)
        if error_type == ErrorCategory.EXPORT_ERROR:
            return ErrorSeverity.LOW
        
        return ErrorSeverity.MEDIUM
    
    def _is_recoverable(self, error_type: ErrorCategory, error: Exception) -> bool:
        """
        Determine if an error is recoverable.
        
        Args:
            error_type: Categorized error type
            error: The original exception
        
        Returns:
            True if the error can be recovered from via retry
        """
        # Check if error type is in recoverable set
        if error_type not in self.recoverable_errors:
            return False
        
        # Check for specific non-recoverable conditions
        error_message = str(error).lower()
        
        # Non-recoverable API errors
        if "authentication" in error_message or "invalid api key" in error_message:
            return False
        
        # Non-recoverable file system errors
        if "permission denied" in error_message and error_type == ErrorCategory.EXPORT_ERROR:
            return False
        
        # Non-recoverable parsing errors (syntax errors in source code)
        if error_type == ErrorCategory.PARSING_ERROR:
            return False
        
        return True
    
    def _format_error_message(self, error: Exception, context: Dict[str, Any]) -> str:
        """
        Format a detailed error message with context.
        
        Args:
            error: The exception
            context: Additional context information
        
        Returns:
            Formatted error message string
        """
        error_type = type(error).__name__
        error_msg = str(error)
        
        # Build context string
        context_parts = []
        for key, value in context.items():
            if value is not None:
                context_parts.append(f"{key}={value}")
        
        context_str = ", ".join(context_parts) if context_parts else "No additional context"
        
        return f"{error_type}: {error_msg} | Context: {context_str}"
    
    def _log_error(
        self,
        error_info: ErrorInfo,
        severity: ErrorSeverity,
        original_error: Exception
    ) -> None:
        """
        Log an error with appropriate severity level.
        
        Args:
            error_info: ErrorInfo object with error details
            severity: Severity level of the error
            original_error: The original exception
        """
        log_message = (
            f"[{error_info.stage.upper()}] {error_info.error_type} - "
            f"{error_info.error_message}"
        )
        
        if error_info.file_path:
            log_message += f" | File: {error_info.file_path}"
        
        if error_info.element_id:
            log_message += f" | Element: {error_info.element_id}"
        
        log_message += f" | Recoverable: {error_info.recoverable}"
        
        # Log with appropriate level based on severity
        if severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message, exc_info=original_error)
        elif severity == ErrorSeverity.HIGH:
            logger.error(log_message, exc_info=original_error)
        elif severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)
    
    def get_recovery_recommendations(self, error_info: ErrorInfo) -> List[str]:
        """
        Get recovery recommendations for a specific error.
        
        Args:
            error_info: ErrorInfo object to analyze
        
        Returns:
            List of recommended recovery actions
        """
        recommendations = []
        
        if error_info.error_type == ErrorCategory.PARSING_ERROR.value:
            recommendations.append("Check the source file for syntax errors")
            recommendations.append("Ensure the file is valid Python/JavaScript/TypeScript")
            recommendations.append("Consider excluding this file from documentation generation")
        
        elif error_info.error_type == ErrorCategory.CONTEXT_ANALYSIS_ERROR.value:
            recommendations.append("Verify that all imported modules are accessible")
            recommendations.append("Check for circular dependencies")
            if error_info.recoverable:
                recommendations.append("Retry the context analysis for this element")
        
        elif error_info.error_type == ErrorCategory.LLM_GENERATION_ERROR.value:
            if "rate limit" in error_info.error_message.lower():
                recommendations.append("Wait before retrying to avoid rate limits")
                recommendations.append("Consider reducing batch size")
            elif "timeout" in error_info.error_message.lower():
                recommendations.append("Check network connectivity")
                recommendations.append("Retry the generation")
            elif "api key" in error_info.error_message.lower():
                recommendations.append("Verify your Gemini API key is valid")
                recommendations.append("Check API key environment variable")
            else:
                recommendations.append("Retry documentation generation for this element")
                recommendations.append("Check LLM API status")
        
        elif error_info.error_type == ErrorCategory.EXPORT_ERROR.value:
            recommendations.append("Check write permissions for output directory")
            recommendations.append("Ensure sufficient disk space")
            recommendations.append("Verify output path is valid")
            if error_info.recoverable:
                recommendations.append("Retry the export operation")
        
        elif error_info.error_type == ErrorCategory.CONFIGURATION_ERROR.value:
            recommendations.append("Review configuration settings")
            recommendations.append("Check environment variables")
            recommendations.append("Verify all required dependencies are installed")
        
        elif error_info.error_type == ErrorCategory.RESOURCE_ERROR.value:
            recommendations.append("Reduce batch size to lower memory usage")
            recommendations.append("Process fewer files at once")
            recommendations.append("Close other applications to free resources")
        
        if not recommendations:
            recommendations.append("Review error details and context")
            recommendations.append("Check application logs for more information")
        
        return recommendations
