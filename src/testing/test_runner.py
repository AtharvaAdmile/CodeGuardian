import subprocess
import os
import logging
from typing import Dict, List, Optional
from src.models.testing_models import TestResult

logger = logging.getLogger(__name__)

class TestRunner:
    """
    Executes tests using pytest and captures results.
    """
    
    def run_file(self, file_path: str) -> TestResult:
        """
        Run a single test file using pytest.
        """
        if not os.path.exists(file_path):
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output="File not found",
                error_message="Test file does not exist on disk"
            )
            
        try:
            # Run pytest on the file
            # -v: verbose
            # --no-header: cleaner output
            # --no-summary: cleaner output
            result = subprocess.run(
                ["pytest", file_path, "-v"],
                capture_output=True,
                text=True,
                timeout=30 # Prevent hangs
            )
            
            passed = result.returncode == 0
            
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=passed,
                output=result.stdout + "\n" + result.stderr,
                error_message=None if passed else "Tests failed (see output)"
            )
            
        except subprocess.TimeoutExpired:
            return TestResult(
                test_id=file_path,
                file_path=file_path,
                passed=False,
                output="Timeout expired",
                error_message="Execution timed out"
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
            
        for root, _, files in os.walk(test_dir):
            for file in files:
                if file.endswith("_test.py") or file.startswith("test_"):
                    path = os.path.join(root, file)
                    results[path] = self.run_file(path)
        return results
