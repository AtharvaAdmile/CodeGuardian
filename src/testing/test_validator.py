import ast
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)

class TestValidator:
    """
    Validates generated test code for syntax errors and basic sanity.
    """
    
    def validate_syntax(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        Check if the code matches valid Python syntax.
        """
        try:
            ast.parse(code)
            return True, None
        except SyntaxError as e:
            error_msg = f"Syntax Error at line {e.lineno}, offset {e.offset}: {e.msg}"
            logger.warning(f"Test validation failed: {error_msg}")
            return False, error_msg
        except Exception as e:
            logger.warning(f"Test validation error: {str(e)}")
            return False, str(e)

    def validate_imports(self, code: str) -> Tuple[bool, Optional[str]]:
        """
        Check for required imports (basic heuristic).
        """
        if "import pytest" not in code and "from pytest" not in code:
            return False, "Missing 'pytest' import"
        return True, None
