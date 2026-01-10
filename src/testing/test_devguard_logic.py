import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.getcwd())

# Mock google.generativeai before importing modules that use it
mock_genai = MagicMock()
sys.modules["google.generativeai"] = mock_genai

from src.testing.test_analyzer import TestAnalyzer
from src.testing.test_generator import TestGenerator
from src.testing.test_orchestrator import TestOrchestrator
from src.models.testing_models import TestType

class TestDevGuardLogic(unittest.TestCase):
    def setUp(self):
        self.analyzer = TestAnalyzer()
        self.orchestrator = TestOrchestrator()
        
    def test_analyzer_logic(self):
        code = "def foo():\n    return 1"
        elements = self.analyzer.analyze_file("dummy_test_file.py", code)
        self.assertTrue(len(elements) >= 1) 
        found = any(e.name == "foo" for e in elements)
        self.assertTrue(found)
        
    @patch('src.testing.test_generator.genai')
    def test_generator_mock(self, mock_genai):
        # Mock Gemini response
        mock_model = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "```python\ndef test_foo(): assert foo() == 1\n```"
        mock_model.generate_content.return_value = mock_response
        
        mock_genai.GenerativeModel.return_value = mock_model
        
        generator = TestGenerator(api_key="fake_key")
        generator.model = mock_model
        
        from src.models.testing_models import TestableElement
        element = TestableElement(
            element_id="1", name="foo", element_type="function",
            file_path="test.py", start_line=1, end_line=2, content="def foo(): pass"
        )
        
        result = generator.generate_tests(element, TestType.UNIT)
        self.assertIn("def test_foo", result.test_code)
        
    def test_orchestrator_session(self):
        session = self.orchestrator.start_session(["/tmp/test.py"])
        self.assertIsNotNone(session.session_id)
        self.assertEqual(session.selected_files, ["/tmp/test.py"])

if __name__ == '__main__':
    unittest.main()
