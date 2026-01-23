"""
Compliance Scanner - PII and Security Pattern Detection.

Scans code for potential compliance violations including:
- PII exposure (GDPR, HIPAA)
- Hardcoded secrets
- Dangerous function usage
"""

import ast
import re
import logging
from typing import Dict, Any, List, Optional, Set
from pathlib import Path
from dataclasses import dataclass

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    yaml = None

logger = logging.getLogger(__name__)


@dataclass
class ComplianceViolation:
    """Represents a single compliance violation."""
    line: int
    column: int
    pattern: str
    severity: str  # critical, high, medium, low
    message: str
    code_snippet: str
    category: str  # pii, secrets, gdpr, hipaa, dangerous


class ComplianceScanner:
    """
    AST-based compliance scanner for Python code.
    
    Checks variable names, string literals, and function calls
    against configurable compliance rules.
    """
    
    DEFAULT_RULES_PATH = Path(__file__).parent.parent.parent / "rules" / "compliance.yaml"
    
    def __init__(self, rules_path: Optional[str] = None):
        """
        Initialize scanner with compliance rules.
        
        Args:
            rules_path: Path to YAML rules file. If None, uses default rules.
        """
        self.rules_path = Path(rules_path) if rules_path else self.DEFAULT_RULES_PATH
        self.rules = self._load_rules()
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}
        self._compile_patterns()
        
    def _load_rules(self) -> Dict[str, Any]:
        """Load compliance rules from YAML file."""
        if not YAML_AVAILABLE:
            logger.warning("PyYAML not available, using default rules")
            return self._get_default_rules()
            
        try:
            if self.rules_path.exists():
                with open(self.rules_path) as f:
                    return yaml.safe_load(f)
            else:
                logger.warning(f"Rules file not found: {self.rules_path}")
                return self._get_default_rules()
        except Exception as e:
            logger.error(f"Error loading rules: {e}")
            return self._get_default_rules()
    
    def _get_default_rules(self) -> Dict[str, Any]:
        """Return built-in default compliance rules."""
        return {
            "pii_patterns": [
                {"pattern": "password", "severity": "critical", "message": "Password exposure"},
                {"pattern": "ssn", "severity": "critical", "message": "SSN detected"},
                {"pattern": "api_key", "severity": "high", "message": "API key exposure"},
                {"pattern": "secret", "severity": "high", "message": "Secret detected"},
            ],
            "secret_patterns": [
                {"pattern": "private_key", "severity": "high", "message": "Private key exposure"},
                {"pattern": "access_token", "severity": "high", "message": "Access token exposure"},
            ],
            "dangerous_functions": [
                {"pattern": "eval", "severity": "critical", "message": "eval() is dangerous"},
                {"pattern": "exec", "severity": "critical", "message": "exec() is dangerous"},
            ]
        }
    
    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for performance."""
        for category, patterns in self.rules.items():
            if not isinstance(patterns, list):
                continue
                
            self._compiled_patterns[category] = []
            for rule in patterns:
                if isinstance(rule, dict) and 'pattern' in rule:
                    try:
                        regex = re.compile(rule['pattern'], re.IGNORECASE)
                        self._compiled_patterns[category].append({
                            'regex': regex,
                            'severity': rule.get('severity', 'medium'),
                            'message': rule.get('message', 'Compliance violation')
                        })
                    except re.error as e:
                        logger.warning(f"Invalid regex pattern '{rule['pattern']}': {e}")
    
    def scan_code(self, code_snippet: str) -> Dict[str, Any]:
        """
        Scan a code snippet for compliance violations.
        
        Args:
            code_snippet: Python source code to analyze
            
        Returns:
            Dictionary containing:
            - passed: bool - True if no violations found
            - violations: List of violation details
            - summary: Human-readable summary
            - severity_counts: Count by severity level
        """
        violations: List[ComplianceViolation] = []
        
        # Try AST-based analysis first
        try:
            tree = ast.parse(code_snippet)
            violations.extend(self._scan_ast(tree, code_snippet))
        except SyntaxError as e:
            logger.debug(f"AST parsing failed, falling back to regex: {e}")
            # Fall back to regex-only scanning
            violations.extend(self._scan_regex(code_snippet))
        
        # Count by severity
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for v in violations:
            if v.severity in severity_counts:
                severity_counts[v.severity] += 1
        
        return {
            "passed": len(violations) == 0,
            "violations": [
                {
                    "line": v.line,
                    "column": v.column,
                    "pattern": v.pattern,
                    "severity": v.severity,
                    "message": v.message,
                    "code_snippet": v.code_snippet,
                    "category": v.category
                }
                for v in violations
            ],
            "summary": self._generate_summary(violations),
            "severity_counts": severity_counts,
            "total_violations": len(violations)
        }
    
    def _scan_ast(self, tree: ast.AST, source: str) -> List[ComplianceViolation]:
        """Scan AST nodes for violations."""
        violations = []
        lines = source.split('\n')
        
        for node in ast.walk(tree):
            # Check variable names (Name, arg)
            if isinstance(node, ast.Name):
                violations.extend(
                    self._check_identifier(node.id, node.lineno, node.col_offset, lines)
                )
            elif isinstance(node, ast.arg):
                violations.extend(
                    self._check_identifier(node.arg, node.lineno, node.col_offset, lines)
                )
            
            # Check string literals
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                violations.extend(
                    self._check_string_literal(node.value, node.lineno, node.col_offset, lines)
                )
            
            # Check function calls
            elif isinstance(node, ast.Call):
                violations.extend(
                    self._check_function_call(node, lines)
                )
            
            # Check assignments to dangerous names
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        violations.extend(
                            self._check_identifier(target.id, target.lineno, target.col_offset, lines)
                        )
        
        return violations
    
    def _check_identifier(
        self,
        name: str,
        line: int,
        col: int,
        lines: List[str]
    ) -> List[ComplianceViolation]:
        """Check an identifier name against compliance patterns."""
        violations = []
        
        for category, patterns in self._compiled_patterns.items():
            cat_name = category.replace('_patterns', '')
            
            for rule in patterns:
                if rule['regex'].search(name):
                    code_snippet = lines[line - 1] if line <= len(lines) else ""
                    violations.append(ComplianceViolation(
                        line=line,
                        column=col,
                        pattern=name,
                        severity=rule['severity'],
                        message=f"Variable '{name}': {rule['message']}",
                        code_snippet=code_snippet.strip(),
                        category=cat_name
                    ))
                    break  # One violation per identifier per category
                    
        return violations
    
    def _check_string_literal(
        self,
        value: str,
        line: int,
        col: int,
        lines: List[str]
    ) -> List[ComplianceViolation]:
        """Check string literal for suspicious content."""
        violations = []
        
        # Only check strings that look like they might contain secrets
        # (e.g., API key patterns, passwords, etc.)
        suspicious_patterns = [
            (r'[A-Za-z0-9]{32,}', 'high', 'Potential API key or token'),
            (r'-----BEGIN.*KEY-----', 'critical', 'Private key detected'),
            (r'password\s*[=:]\s*\S+', 'critical', 'Hardcoded password'),
        ]
        
        for pattern, severity, message in suspicious_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                code_snippet = lines[line - 1] if line <= len(lines) else ""
                violations.append(ComplianceViolation(
                    line=line,
                    column=col,
                    pattern=value[:50] + "..." if len(value) > 50 else value,
                    severity=severity,
                    message=message,
                    code_snippet=code_snippet.strip(),
                    category="secrets"
                ))
                
        return violations
    
    def _check_function_call(
        self,
        node: ast.Call,
        lines: List[str]
    ) -> List[ComplianceViolation]:
        """Check for dangerous function calls."""
        violations = []
        
        # Get function name
        func_name = None
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            
        if func_name:
            if 'dangerous_functions' in self._compiled_patterns:
                for rule in self._compiled_patterns['dangerous_functions']:
                    if rule['regex'].search(func_name):
                        code_snippet = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
                        violations.append(ComplianceViolation(
                            line=node.lineno,
                            column=node.col_offset,
                            pattern=func_name,
                            severity=rule['severity'],
                            message=f"Function '{func_name}': {rule['message']}",
                            code_snippet=code_snippet.strip(),
                            category="dangerous_functions"
                        ))
                        
        return violations
    
    def _scan_regex(self, code: str) -> List[ComplianceViolation]:
        """Fallback regex-only scanning for non-parseable code."""
        violations = []
        lines = code.split('\n')
        
        for line_num, line in enumerate(lines, start=1):
            for category, patterns in self._compiled_patterns.items():
                cat_name = category.replace('_patterns', '')
                
                for rule in patterns:
                    match = rule['regex'].search(line)
                    if match:
                        violations.append(ComplianceViolation(
                            line=line_num,
                            column=match.start(),
                            pattern=match.group(),
                            severity=rule['severity'],
                            message=rule['message'],
                            code_snippet=line.strip(),
                            category=cat_name
                        ))
                        
        return violations
    
    def _generate_summary(self, violations: List[ComplianceViolation]) -> str:
        """Generate a human-readable summary."""
        if not violations:
            return "✅ No compliance violations detected."
            
        critical = sum(1 for v in violations if v.severity == 'critical')
        high = sum(1 for v in violations if v.severity == 'high')
        
        if critical > 0:
            return f"🛑 {len(violations)} violation(s) found including {critical} CRITICAL. Immediate attention required."
        elif high > 0:
            return f"⚠️ {len(violations)} violation(s) found including {high} HIGH severity. Review recommended."
        else:
            return f"ℹ️ {len(violations)} minor violation(s) found. Consider reviewing."
