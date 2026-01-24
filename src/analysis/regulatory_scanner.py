"""
Regulatory Compliance Scanner - AI-powered compliance evaluation for Medical and Security standards.

This module evaluates code against regulatory frameworks such as:
- FDA 21 CFR Part 11
- IEC 62304
- ISO 13485
- ISO 27001 / HIPAA
"""

import os
import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

REGULATORY_RULES = [
    "FDA 21 CFR Part 11 (Electronic Records)",
    "IEC 62304 (Medical Device Software Lifecycle)",
    "ISO 13485 (Quality Management Systems)",
    "ISO 27001 / HIPAA (Information Security)",
    "Data Integrity & Security (FDA / HIPAA / ISO 27001)",
    "Accountability (FDA 21 CFR Part 11)",
    "Traceability & Safety (IEC 62304)",
    "Quality Process (ISO 13485)"
]

class RegulatoryScanner:
    """
    Evaluates source code against medical and security regulatory standards using Google Gemini.
    """
    
    def __init__(self):
        """Initialize the scanner with Gemini API."""
        self.api_key = os.getenv('GOOGLE_API_KEY')
        self.model_name = os.getenv('LLM_MODEL', 'gemini-2.5-flash')
        self._client = None
        
    def _get_client(self):
        """Lazy-load the Gemini client."""
        if self._client is None:
            try:
                import google.generativeai as genai
                if not self.api_key:
                    raise ValueError("GOOGLE_API_KEY not found in environment")
                genai.configure(api_key=self.api_key)
                self._client = genai.GenerativeModel(self.model_name)
                logger.info(f"Initialized Gemini client for regulatory scanning with model: {self.model_name}")
            except ImportError:
                raise ImportError("google-generativeai package is required. Install with: pip install google-generativeai")
            except Exception as e:
                raise RuntimeError(f"Failed to initialize Gemini client: {e}")
        return self._client
    
    def _build_prompt(self, filename: str, code_content: str) -> str:
        """Build the prompt for regulatory evaluation."""
        rules_list = "\n".join([f"- {rule}" for rule in REGULATORY_RULES])
        
        prompt = f"""You are a specialist in Medical Device Software Regulatory Compliance and Cybersecurity. 
Evaluate the following source code for compliance with these specific standards and rules:

{rules_list}

Source File: {filename}

Code Content:
```
{code_content}
```

Instructions:
1. Analyze the code for potential violations, gaps, or risks related to each standard.
2. If a standard is not applicable to the specific code (e.g., UI code vs Data storage), note it briefly.
3. Provide a list of "Violations" or "Gaps" found.
4. Provide a "Compliance Score" (0-100) for this file.
5. Provide a brief "Summary" of the overall regulatory posture.
6. For each violation, specify:
   - Rule/Standard violated
   - Severity (Critical, High, Medium, Low)
   - Description of the gap
   - Recommendation for remediation

IMPORTANT: Return your response in JSON format only with the following structure:
{{
    "passed": boolean,
    "score": number,
    "summary": "string",
    "violations": [
        {{
            "rule": "string",
            "severity": "string",
            "message": "string",
            "recommendation": "string"
        }}
    ]
}}
"""
        return prompt

    def scan_file(self, file_path: str, file_content: str) -> Dict[str, Any]:
        """
        Scan a file for regulatory compliance.
        
        Args:
            file_path: Path to the source file
            file_content: Content of the source file
            
        Returns:
            Dictionary with scan results
        """
        if not file_content or not file_content.strip():
            return {"error": "File content is empty", "passed": True, "score": 100}
            
        if not self.api_key:
            return {"error": "GOOGLE_API_KEY not configured", "passed": False, "score": 0}
            
        try:
            filename = Path(file_path).name
            prompt = self._build_prompt(filename, file_content)
            
            client = self._get_client()
            response = client.generate_content(prompt)
            
            # Extract JSON from response
            text = response.text.strip()
            
            # Find JSON boundaries if LLM included extra text
            start = text.find('{')
            end = text.rfind('}') + 1
            if start != -1 and end != 0:
                json_data = text[start:end]
                result = json.loads(json_data)
                return result
            else:
                return {
                    "error": "Failed to parse regulatory evaluation results.",
                    "raw_output": text,
                    "passed": False
                }
                
        except Exception as e:
            logger.error(f"Error in regulatory scan: {e}")
            return {
                "error": str(e),
                "passed": False,
                "score": 0,
                "violations": [],
                "summary": "Evaluation failed due to an internal error."
            }

# Singleton
_scanner: Optional[RegulatoryScanner] = None

def get_regulatory_scanner() -> RegulatoryScanner:
    """Get the regulatory scanner singleton."""
    global _scanner
    if _scanner is None:
        _scanner = RegulatoryScanner()
    return _scanner
