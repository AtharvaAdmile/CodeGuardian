"""
Gap Detector for analyzing documentation quality and identifying gaps.

This module provides functionality to evaluate existing documentation quality
and identify code elements that need documentation.
"""

import re
from typing import Optional, Dict, List, Tuple
from src.models.documentation_models import CodeElement


class GapDetector:
    """
    Analyzes code elements to detect documentation gaps and calculate quality scores.
    
    The GapDetector evaluates existing documentation (docstrings for Python,
    JSDoc for JavaScript/TypeScript) and assigns quality scores based on
    completeness criteria.
    """
    
    def __init__(self, quality_threshold: float = 70.0):
        """
        Initialize the GapDetector.
        
        Args:
            quality_threshold: Minimum quality score (0-100) to consider
                             documentation adequate. Default is 70.0.
        """
        self.quality_threshold = quality_threshold
    
    def calculate_quality_score(self, element: CodeElement) -> float:
        """
        Calculate documentation quality score (0-100) for a code element.
        
        Scoring criteria:
        - Presence of docstring/JSDoc: 40 points
        - Description completeness: 20 points
        - Parameter documentation: 20 points
        - Return value documentation: 10 points
        - Usage examples: 10 points
        
        Args:
            element: The code element to evaluate
            
        Returns:
            Quality score between 0 and 100
        """
        if not element.existing_doc or not element.existing_doc.strip():
            return 0.0
        
        score = 0.0
        doc = element.existing_doc.strip()
        
        # Determine language and extract documentation
        if element.language.lower() == "python":
            doc_info = self._parse_python_docstring(doc)
        elif element.language.lower() in ["javascript", "typescript"]:
            doc_info = self._parse_jsdoc(doc)
        else:
            # Unsupported language, just check for presence
            return 40.0 if doc else 0.0
        
        # 40 points: Presence of docstring/JSDoc
        score += 40.0
        
        # 20 points: Description completeness
        # Consider complete if description has at least 20 characters
        if doc_info["description"] and len(doc_info["description"]) >= 20:
            score += 20.0
        elif doc_info["description"] and len(doc_info["description"]) >= 10:
            score += 10.0  # Partial credit for short description
        
        # 20 points: Parameter documentation
        if element.parameters:
            documented_params = len(doc_info["params"])
            total_params = len(element.parameters)
            param_score = (documented_params / total_params) * 20.0
            score += param_score
        else:
            # No parameters to document, give full credit
            score += 20.0
        
        # 10 points: Return value documentation
        if element.element_type in ["function", "method"]:
            if doc_info["returns"]:
                score += 10.0
            elif element.return_type and element.return_type.lower() in ["none", "void", "null"]:
                # No return value to document, give full credit
                score += 10.0
        else:
            # Classes don't need return documentation
            score += 10.0
        
        # 10 points: Usage examples
        if doc_info["examples"]:
            score += 10.0
        
        return min(score, 100.0)
    
    def has_documentation_gap(self, quality_score: float) -> bool:
        """
        Determine if a code element has a documentation gap.
        
        Args:
            quality_score: The quality score (0-100) of the element's documentation
            
        Returns:
            True if quality_score is below the threshold, False otherwise
        """
        return quality_score < self.quality_threshold
    
    def _parse_python_docstring(self, docstring: str) -> Dict[str, any]:
        """
        Parse Python docstring (Google-style, NumPy-style, or basic).
        
        Args:
            docstring: The docstring text to parse
            
        Returns:
            Dictionary with keys: description, params, returns, examples
        """
        result = {
            "description": "",
            "params": [],
            "returns": None,
            "examples": []
        }
        
        if not docstring:
            return result
        
        # Try Google-style first
        google_result = self._parse_google_docstring(docstring)
        if google_result["params"] or google_result["returns"]:
            return google_result
        
        # Try NumPy-style
        numpy_result = self._parse_numpy_docstring(docstring)
        if numpy_result["params"] or numpy_result["returns"]:
            return numpy_result
        
        # Fall back to basic docstring (just description)
        result["description"] = docstring.strip()
        return result
    
    def _parse_google_docstring(self, docstring: str) -> Dict[str, any]:
        """
        Parse Google-style Python docstring.
        
        Format:
            Brief description.
            
            Longer description.
            
            Args:
                param1: Description
                param2: Description
            
            Returns:
                Description of return value
            
            Examples:
                >>> example code
        """
        result = {
            "description": "",
            "params": [],
            "returns": None,
            "examples": []
        }
        
        lines = docstring.split('\n')
        current_section = "description"
        description_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Check for section headers
            if line.lower() in ["args:", "arguments:", "parameters:"]:
                current_section = "args"
                i += 1
                continue
            elif line.lower() in ["returns:", "return:"]:
                current_section = "returns"
                i += 1
                continue
            elif line.lower() in ["examples:", "example:"]:
                current_section = "examples"
                i += 1
                continue
            elif line.lower() in ["raises:", "yields:", "note:", "notes:", "warning:", "warnings:"]:
                # Other sections we don't score
                current_section = "other"
                i += 1
                continue
            
            # Process content based on current section
            if current_section == "description":
                if line:
                    description_lines.append(line)
            elif current_section == "args":
                # Look for parameter lines (indented, format: "param: description")
                if line and ':' in line:
                    param_match = re.match(r'^(\w+)(?:\s*\([^)]+\))?\s*:\s*(.+)', line)
                    if param_match:
                        result["params"].append(param_match.group(1))
            elif current_section == "returns":
                if line:
                    result["returns"] = line
                    current_section = "other"  # Only capture first line
            elif current_section == "examples":
                if line:
                    result["examples"].append(line)
            
            i += 1
        
        result["description"] = " ".join(description_lines)
        return result
    
    def _parse_numpy_docstring(self, docstring: str) -> Dict[str, any]:
        """
        Parse NumPy-style Python docstring.
        
        Format:
            Brief description.
            
            Longer description.
            
            Parameters
            ----------
            param1 : type
                Description
            param2 : type
                Description
            
            Returns
            -------
            type
                Description
            
            Examples
            --------
            >>> example code
        """
        result = {
            "description": "",
            "params": [],
            "returns": None,
            "examples": []
        }
        
        lines = docstring.split('\n')
        current_section = "description"
        description_lines = []
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Check for section headers (followed by dashes)
            if i + 1 < len(lines) and re.match(r'^-+$', lines[i + 1].strip()):
                section_name = line.lower()
                if section_name in ["parameters", "params", "arguments"]:
                    current_section = "params"
                elif section_name in ["returns", "return"]:
                    current_section = "returns"
                elif section_name in ["examples", "example"]:
                    current_section = "examples"
                else:
                    current_section = "other"
                i += 2  # Skip header and dashes
                continue
            
            # Process content based on current section
            if current_section == "description":
                if line:
                    description_lines.append(line)
            elif current_section == "params":
                # Look for parameter lines (format: "param : type")
                # Parameters can be at the start of line or slightly indented
                if line and ':' in line:
                    param_match = re.match(r'^(\w+)\s*:', line)
                    if param_match:
                        result["params"].append(param_match.group(1))
            elif current_section == "returns":
                if line and not line.startswith(' '):
                    result["returns"] = line
                    current_section = "other"  # Only capture type line
            elif current_section == "examples":
                if line:
                    result["examples"].append(line)
            
            i += 1
        
        result["description"] = " ".join(description_lines)
        return result
    
    def _parse_jsdoc(self, jsdoc: str) -> Dict[str, any]:
        """
        Parse JSDoc comment for JavaScript/TypeScript.
        
        Format:
            /**
             * Description
             * 
             * @param {type} name - Description
             * @returns {type} Description
             * @example
             * example code
             */
        
        Args:
            jsdoc: The JSDoc comment text to parse
            
        Returns:
            Dictionary with keys: description, params, returns, examples
        """
        result = {
            "description": "",
            "params": [],
            "returns": None,
            "examples": []
        }
        
        if not jsdoc:
            return result
        
        # Remove comment markers
        cleaned = jsdoc.strip()
        cleaned = re.sub(r'^/\*\*\s*', '', cleaned)
        cleaned = re.sub(r'\s*\*/$', '', cleaned)
        cleaned = re.sub(r'^\s*\*\s?', '', cleaned, flags=re.MULTILINE)
        
        lines = cleaned.split('\n')
        description_lines = []
        in_example = False
        
        for line in lines:
            line = line.strip()
            
            # Check for @tags
            if line.startswith('@param'):
                # Extract parameter name
                param_match = re.match(r'@param(?:eter)?\s+(?:\{[^}]+\})?\s+(\w+)', line)
                if param_match:
                    result["params"].append(param_match.group(1))
                in_example = False
            elif line.startswith('@return'):
                # @returns or @return
                returns_match = re.match(r'@returns?\s+(?:\{[^}]+\})?\s*(.+)', line)
                if returns_match:
                    result["returns"] = returns_match.group(1)
                else:
                    result["returns"] = "return value"
                in_example = False
            elif line.startswith('@example'):
                in_example = True
                # Capture example content on same line if present
                example_match = re.match(r'@example\s+(.+)', line)
                if example_match:
                    result["examples"].append(example_match.group(1))
            elif in_example:
                if line and not line.startswith('@'):
                    result["examples"].append(line)
            elif not line.startswith('@'):
                # Part of description
                if line:
                    description_lines.append(line)
        
        result["description"] = " ".join(description_lines)
        return result
