"""
Structure Analyzer with Tech Debt Health Score.

Enhanced with radon for cyclomatic complexity and git churn analysis
to identify "hotspot" files that need refactoring.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Set, Optional

try:
    from radon.complexity import cc_visit
    from radon.metrics import h_visit
    RADON_AVAILABLE = True
except ImportError:
    RADON_AVAILABLE = False
    cc_visit = None
    h_visit = None

try:
    from git import Repo, InvalidGitRepositoryError
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    Repo = None
    InvalidGitRepositoryError = Exception

logger = logging.getLogger(__name__)


class StructureAnalyzer:
    """
    Analyzes the structure of a codebase to determine its organization score.
    
    Enhanced Features:
    - Cyclomatic complexity via radon
    - Git churn tracking
    - Health score calculation
    """
    
    EXCLUDED_DIRS = {
        '__pycache__', 'node_modules', '.git', '.venv', 'venv',
        'env', '.env', 'dist', 'build', '.next', '.nuxt',
        'coverage', '.pytest_cache', '.mypy_cache', '.tox',
        '.idea', '.vscode'
    }
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()
        self._repo: Optional[Repo] = None
        
    @property
    def repo(self) -> Optional[Repo]:
        """Lazy-load the git repository."""
        if self._repo is None and GIT_AVAILABLE and Repo is not None:
            try:
                self._repo = Repo(self.root_path, search_parent_directories=True)
            except InvalidGitRepositoryError:
                self._repo = None
        return self._repo
        
    def analyze_structure(self) -> Dict[str, Any]:
        """
        Analyze the codebase structure and return a score and details.
        
        Returns:
            Dict containing:
            - score: float (0-10)
            - has_git: bool
            - total_files: int
            - root_files: int
            - folders_count: int
        """
        total_files = 0
        root_files = 0
        folders_with_files = set()
        
        # Check for git
        has_git = (self.root_path / ".git").exists() and (self.root_path / ".git").is_dir()
        
        try:
            for root, dirs, files in os.walk(self.root_path):
                # Filter excluded dirs in-place to prevent walking them
                dirs[:] = [d for d in dirs if d not in self.EXCLUDED_DIRS]
                
                is_root = Path(root) == self.root_path
                
                current_files_count = 0
                for file in files:
                    if file.startswith('.'):
                        continue
                        
                    total_files += 1
                    current_files_count += 1
                    if is_root:
                        root_files += 1
                
                if current_files_count > 0:
                    folders_with_files.add(root)

        except Exception as e:
            return {
                "score": 0.0,
                "has_git": has_git,
                "total_files": 0,
                "root_files": 0,
                "folders_count": 0,
                "error": str(e)
            }

        score = 0.0
        
        if has_git:
            score += 2.0
            
        if total_files > 0:
            non_root_files = total_files - root_files
            organization_ratio = non_root_files / total_files
            score += organization_ratio * 8.0
            
        score = min(10.0, score)

        return {
            "score": round(score, 1),
            "has_git": has_git,
            "total_files": total_files,
            "root_files": root_files,
            "folders_count": len(folders_with_files)
        }
    
    def get_file_health(self, file_path: str) -> Dict[str, Any]:
        """
        Calculate health score for a specific file.
        
        Health Score = 100 - (Complexity Score + Churn Score)
        
        High complexity + High churn = "Hotspot" that needs refactoring.
        
        Args:
            file_path: Path to the file to analyze
            
        Returns:
            Dict containing:
            - health_score: 0-100 (higher is better)
            - complexity_score: Raw complexity value
            - complexity_rank: A-F grade
            - churn_score: Number of edits in last 6 months
            - churn_rank: low/medium/high
            - recommendation: Refactoring priority
            - details: Breakdown of complex functions
        """
        abs_path = Path(file_path)
        if not abs_path.is_absolute():
            abs_path = self.root_path / file_path
            
        if not abs_path.exists():
            return {
                "file_path": file_path,
                "error": "File not found",
                "health_score": 0
            }
        
        # Get complexity score
        complexity_result = self._calculate_complexity(abs_path)
        complexity_score = complexity_result.get('total_complexity', 0)
        
        # Get churn score
        churn_result = self._calculate_churn(abs_path)
        churn_score = churn_result.get('churn_count', 0)
        
        # Calculate health score
        # Normalize: complexity typically 1-50, churn 0-100
        normalized_complexity = min(complexity_score, 50)  # Cap at 50
        normalized_churn = min(churn_score * 2, 50)  # Scale churn, cap at 50
        
        health_score = max(0, 100 - normalized_complexity - normalized_churn)
        
        # Determine recommendation
        recommendation = self._get_recommendation(health_score, complexity_score, churn_score)
        
        return {
            "file_path": str(file_path),
            "health_score": round(health_score, 1),
            "complexity": {
                "score": complexity_score,
                "rank": complexity_result.get('rank', 'N/A'),
                "functions": complexity_result.get('functions', [])[:5]  # Top 5
            },
            "churn": {
                "score": churn_score,
                "rank": churn_result.get('rank', 'N/A'),
                "period_months": churn_result.get('period_months', 6)
            },
            "recommendation": recommendation,
            "is_hotspot": health_score < 50 and churn_score > 5
        }
    
    def _calculate_complexity(self, file_path: Path) -> Dict[str, Any]:
        """Calculate cyclomatic complexity using radon."""
        if not RADON_AVAILABLE:
            return {
                "total_complexity": 0,
                "rank": "N/A",
                "functions": [],
                "error": "radon not installed"
            }
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source = f.read()
                
            # Get complexity for all functions
            blocks = cc_visit(source)
            
            if not blocks:
                return {
                    "total_complexity": 0,
                    "rank": "A",
                    "functions": []
                }
            
            functions = []
            total_complexity = 0
            
            for block in blocks:
                total_complexity += block.complexity
                functions.append({
                    "name": block.name,
                    "complexity": block.complexity,
                    "rank": block.letter,
                    "line": block.lineno
                })
            
            # Sort by complexity (highest first)
            functions.sort(key=lambda x: x['complexity'], reverse=True)
            
            # Calculate average complexity rank
            avg_complexity = total_complexity / len(blocks) if blocks else 0
            
            if avg_complexity <= 5:
                rank = "A"
            elif avg_complexity <= 10:
                rank = "B"
            elif avg_complexity <= 20:
                rank = "C"
            elif avg_complexity <= 30:
                rank = "D"
            else:
                rank = "F"
            
            return {
                "total_complexity": total_complexity,
                "average_complexity": round(avg_complexity, 1),
                "rank": rank,
                "functions": functions
            }
            
        except Exception as e:
            logger.error(f"Error calculating complexity: {e}")
            return {
                "total_complexity": 0,
                "rank": "N/A",
                "functions": [],
                "error": str(e)
            }
    
    def _calculate_churn(self, file_path: Path, months: int = 6) -> Dict[str, Any]:
        """Calculate file churn using git log."""
        if not GIT_AVAILABLE or self.repo is None:
            return {
                "churn_count": 0,
                "rank": "N/A",
                "period_months": months,
                "error": "Git not available"
            }
            
        try:
            from datetime import datetime, timedelta
            
            since_date = datetime.now() - timedelta(days=months * 30)
            since_str = since_date.strftime("%Y-%m-%d")
            
            # Get relative path
            try:
                rel_path = file_path.relative_to(self.repo.working_dir)
            except ValueError:
                rel_path = file_path
            
            # Count commits
            log_output = self.repo.git.log(
                f"--since={since_str}",
                "--oneline",
                "--",
                str(rel_path)
            )
            
            commit_count = len([l for l in log_output.split('\n') if l.strip()])
            
            # Determine rank
            if commit_count <= 3:
                rank = "low"
            elif commit_count <= 10:
                rank = "medium"
            else:
                rank = "high"
            
            return {
                "churn_count": commit_count,
                "rank": rank,
                "period_months": months
            }
            
        except Exception as e:
            logger.debug(f"Error calculating churn: {e}")
            return {
                "churn_count": 0,
                "rank": "N/A",
                "period_months": months,
                "error": str(e)
            }
    
    def _get_recommendation(
        self,
        health_score: float,
        complexity: int,
        churn: int
    ) -> Dict[str, Any]:
        """Get refactoring recommendation based on metrics."""
        if health_score >= 80:
            return {
                "priority": "none",
                "message": "✅ This file is healthy. No immediate action needed.",
                "action": None
            }
        elif health_score >= 60:
            return {
                "priority": "low",
                "message": "ℹ️ Minor improvements possible. Monitor for increasing complexity.",
                "action": "Consider cleanup during next related change"
            }
        elif health_score >= 40:
            if churn > 10:
                return {
                    "priority": "medium",
                    "message": "⚠️ High-churn file with growing complexity. Risk of bugs.",
                    "action": "Schedule refactoring in next sprint"
                }
            else:
                return {
                    "priority": "medium",
                    "message": "⚠️ Complex file. Consider splitting into smaller modules.",
                    "action": "Review for extraction opportunities"
                }
        else:
            return {
                "priority": "high",
                "message": "🔴 HOTSPOT: High complexity + high churn. This is a bug magnet.",
                "action": "Prioritize refactoring immediately. Consider pair programming."
            }

