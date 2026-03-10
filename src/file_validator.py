"""
FileValidator module for validating uploaded code files.
"""

from typing import Set, Tuple
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of file validation."""
    is_valid: bool
    error_message: str = ""


class FileValidator:
    """
    Validates code files before processing.
    
    Checks file extensions and sizes to ensure only supported
    file types are processed and files don't exceed size limits.
    """
    
    SUPPORTED_EXTENSIONS: Set[str] = {'.py', '.js', '.jsx', '.ts', '.tsx'}
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10MB in bytes
    
    def validate_file(self, filename: str, file_size: int) -> ValidationResult:
        """
        Validate a file based on extension and size.
        
        Args:
            filename: Name of the file to validate
            file_size: Size of the file in bytes
            
        Returns:
            ValidationResult indicating if file is valid and any error message
        """
        # Check if file type is supported
        if not self.is_supported_type(filename):
            supported = ', '.join(sorted(self.SUPPORTED_EXTENSIONS))
            return ValidationResult(
                is_valid=False,
                error_message=f"Unsupported file type. Supported types: {supported}"
            )
        
        # Check file size
        if file_size > self.MAX_FILE_SIZE:
            max_size_mb = self.MAX_FILE_SIZE / (1024 * 1024)
            actual_size_mb = file_size / (1024 * 1024)
            return ValidationResult(
                is_valid=False,
                error_message=f"File size ({actual_size_mb:.2f}MB) exceeds maximum allowed size ({max_size_mb:.0f}MB)"
            )
        
        return ValidationResult(is_valid=True)
    
    def is_supported_type(self, filename: str) -> bool:
        """
        Check if a file type is supported based on its extension.
        
        Args:
            filename: Name of the file to check
            
        Returns:
            True if file type is supported, False otherwise
        """
        if not filename:
            return False
        
        # Extract extension (including the dot)
        extension = ''
        if '.' in filename:
            extension = '.' + filename.rsplit('.', 1)[1].lower()
        
        return extension in self.SUPPORTED_EXTENSIONS
