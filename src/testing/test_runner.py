import subprocess
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional
from src.models.testing_models import TestResult

logger = logging.getLogger(__name__)

# Allowed test execution directory for security
GENERATED_TESTS_DIR = "generated_test_cases"


class TestRunner:
    """
    Executes tests using pytest (Python) or jest (JS/TS) and captures results.
    Enhanced with multi-language support and security validation.
    """
    
    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize the test runner.
        
        Args:
            project_root: Root directory of the project (for security validation)
        """
        self.project_root = project_root or os.getcwd()
    
    def _detect_language(self, file_path: str) -> str:
        """Detect the language of the test file."""
        ext = Path(file_path).suffix.lower()
        if ext == '.py':
            return 'python'
        elif ext in {'.js', '.ts', '.tsx', '.jsx'}:
            return 'javascript'
        return 'unknown'
    
    def _is_safe_path(self, file_path: str) -> bool:
        """
        Validate that the file is within the allowed generated_test_cases directory.
        Security measure to prevent arbitrary code execution.
        """
        try:
            abs_path = Path(file_path).resolve()
            safe_dir = (Path(self.project_root) / GENERATED_TESTS_DIR).resolve()
            return str(abs_path).startswith(str(safe_dir))
        except Exception:
            return False
    
    def run_file(self, file_path: str, allow_unsafe: bool = False) -> TestResult:
        """
        Run a single test file using the appropriate test runner.
        
        Args:
            file_path: Path to the test file
            allow_unsafe: If True, skip security check (only for internal use)
        """
        if not os.path.exists(file_path):
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output="File not found",
                error_message="Test file does not exist on disk"
            )
        
        # Security check: only allow execution from generated_test_cases/
        if not allow_unsafe and not self._is_safe_path(file_path):
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output="",
                error_message=f"Security: Tests can only be executed from {GENERATED_TESTS_DIR}/ directory"
            )
        
        language = self._detect_language(file_path)
        
        if language == 'python':
            return self._run_pytest(file_path)
        elif language == 'javascript':
            return self._run_jest(file_path)
        else:
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output="",
                error_message=f"Unsupported test file type: {Path(file_path).suffix}"
            )
    
    def _run_pytest(self, file_path: str) -> TestResult:
        """Run a Python test file using pytest."""
        try:
            result = subprocess.run(
                ["pytest", file_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.project_root
            )
            
            passed = result.returncode == 0
            output = result.stdout
            if result.stderr:
                output += "\n--- STDERR ---\n" + result.stderr
            
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=passed,
                output=output,
                error_message=None if passed else "Tests failed (see output)"
            )
            
        except subprocess.TimeoutExpired:
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output="Timeout expired after 60 seconds",
                error_message="Execution timed out"
            )
        except FileNotFoundError:
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output="",
                error_message="pytest not found. Install with: pip install pytest"
            )
        except Exception as e:
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output=str(e),
                error_message=f"Execution error: {str(e)}"
            )
    
    def _run_jest(self, file_path: str) -> TestResult:
        """Run a JavaScript/TypeScript test file using jest."""
        try:
            # Try npx jest first (most common), fallback to npm test
            result = subprocess.run(
                ["npx", "jest", file_path, "--no-coverage", "--colors"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.project_root,
                shell=True  # Required for npx on some systems
            )
            
            passed = result.returncode == 0
            output = result.stdout
            if result.stderr:
                output += "\n--- STDERR ---\n" + result.stderr
            
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=passed,
                output=output,
                error_message=None if passed else "Tests failed (see output)"
            )
            
        except subprocess.TimeoutExpired:
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output="Timeout expired after 60 seconds",
                error_message="Execution timed out"
            )
        except FileNotFoundError:
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output="",
                error_message="jest not found. Install with: npm install -D jest"
            )
        except Exception as e:
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output=str(e),
                error_message=f"Execution error: {str(e)}"
            )

    def run_all(self, test_dir: str = "tests") -> Dict[str, TestResult]:
        """Run all tests in a directory."""
        results = {}
        if not os.path.exists(test_dir):
            return results
        
        # Determine if we need to bypass security (for legacy tests/ directory)
        allow_unsafe = not test_dir.startswith(GENERATED_TESTS_DIR)
            
        for root, _, files in os.walk(test_dir):
            for file in files:
                # Python tests
                if file.endswith("_test.py") or file.startswith("test_"):
                    path = os.path.join(root, file)
                    results[path] = self.run_file(path, allow_unsafe=allow_unsafe)
                # JS/TS tests
                elif file.endswith(('.test.js', '.test.ts', '.test.tsx', '.spec.js', '.spec.ts')):
                    path = os.path.join(root, file)
                    results[path] = self.run_file(path, allow_unsafe=allow_unsafe)
        return results
    
    def run_generated_test(self, test_file_path: str) -> TestResult:
        """
        Run a generated test file with full security validation.
        This is the preferred method for running AI-generated tests.
        
        Args:
            test_file_path: Path to the test file (must be in generated_test_cases/)
        """
        return self.run_file(test_file_path, allow_unsafe=False)
