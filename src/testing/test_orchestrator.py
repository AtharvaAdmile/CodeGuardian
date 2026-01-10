import os
import uuid
import logging
from typing import List, Dict, Optional
import shutil

from src.models.testing_models import (
    TestGenerationSession, 
    TestableElement, 
    GeneratedTest, 
    TestResult,
    TestType
)
from src.testing.test_analyzer import TestAnalyzer
from src.testing.test_generator import TestGenerator
from src.testing.test_validator import TestValidator
from src.testing.test_runner import TestRunner

logger = logging.getLogger(__name__)

class TestOrchestrator:
    """
    Coordinates the DevGuard test generation pipeline.
    """
    
    def __init__(
        self,
        test_analyzer: Optional[TestAnalyzer] = None,
        test_generator: Optional[TestGenerator] = None,
        test_validator: Optional[TestValidator] = None,
        test_runner: Optional[TestRunner] = None
    ):
        self.analyzer = test_analyzer or TestAnalyzer()
        self.generator = test_generator or TestGenerator() # Needs QueryEngine passed typically
        self.validator = test_validator or TestValidator()
        self.runner = test_runner or TestRunner()
        
        self.current_session: Optional[TestGenerationSession] = None
        self.tests_dir = "tests" 
        
    def start_session(self, files: List[str]) -> TestGenerationSession:
        """Start a new test generation session."""
        session_id = str(uuid.uuid4())
        self.current_session = TestGenerationSession(
            session_id=session_id,
            selected_files=files
        )
        return self.current_session
        
    def analyze_selected_files(self):
        """Analyze files in the current session to find testable elements."""
        if not self.current_session:
            raise ValueError("No active session")
            
        for file_path in self.current_session.selected_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                elements = self.analyzer.analyze_file(file_path, content)
                for el in elements:
                    self.current_session.identified_elements[el.element_id] = el
                    
            except Exception as e:
                logger.error(f"Failed to analyze {file_path}: {e}")
                
    def generate_tests_for_element(self, element_id: str, test_type: TestType = TestType.UNIT) -> Optional[GeneratedTest]:
        """Generate test for a specific element."""
        if not self.current_session:
            return None
            
        element = self.current_session.identified_elements.get(element_id)
        if not element:
            return None
            
        try:
            # Generate
            test = self.generator.generate_tests(element, test_type)
            
            # Validate
            is_valid, error = self.validator.validate_syntax(test.test_code)
            if not is_valid:
                test.test_code = f"# SYNTAX ERROR in generated test: {error}\n\n{test.test_code}"
                test.confidence_score = 0.0
            
            self.current_session.generated_tests[test.test_id] = test
            return test
            
        except Exception as e:
            logger.error(f"Generation failed for {element_id}: {e}")
            return None

    def approve_test(self, test_id: str):
        """Mark a test as approved."""
        if self.current_session and test_id in self.current_session.generated_tests:
            self.current_session.generated_tests[test_id].status = "approved"

    def reject_test(self, test_id: str):
        """Mark a test as rejected."""
        if self.current_session and test_id in self.current_session.generated_tests:
            self.current_session.generated_tests[test_id].status = "rejected"

    def update_test_code(self, test_id: str, new_code: str):
        """Update test code (user edit)."""
        if self.current_session and test_id in self.current_session.generated_tests:
            self.current_session.generated_tests[test_id].test_code = new_code
            self.current_session.generated_tests[test_id].status = "edited" # Or approved? usually edited implies manual approval needed or auto-approve?
            # Let's keep it as 'edited' but treat 'edited' as actionable for approval

    def save_approved_tests(self) -> int:
        """Save all approved tests to disk."""
        if not self.current_session:
            return 0
            
        if not os.path.exists(self.tests_dir):
            os.makedirs(self.tests_dir)
            
        saved_count = 0
        for test in self.current_session.generated_tests.values():
            if test.status == "approved":
                # Determine filename: <filename>_test.py
                element = self.current_session.identified_elements[test.target_element_id]
                base_name = os.path.basename(element.file_path).replace('.py', '')
                test_filename = f"{base_name}_test.py"
                save_path = os.path.join(self.tests_dir, test_filename)
                
                # Append if file exists? Or overwrite?
                # If we generate multiple tests for same file (different functions), we should append or merge.
                # Simple approach: Append to file if it exists, but check for duplication.
                # Or read existing, parse, add new function.
                # For MVP: Append with a separator if exists.
                
                mode = 'a' if os.path.exists(save_path) else 'w'
                with open(save_path, mode, encoding='utf-8') as f:
                    if mode == 'a':
                        f.write("\n\n")
                    # Add imports if new file? generated test code might include imports. 
                    # If appending, we might duplicate imports. 
                    # TestValidator should ideally handle this or we rely on user manually fixing for now.
                    # Or Generator provides imports separately.
                    f.write(test.test_code)
                    
                saved_count += 1
                
        return saved_count
        
    def run_verification(self) -> Dict[str, TestResult]:
        """Run all tests in the tests/ directory."""
        return self.runner.run_all(self.tests_dir)
