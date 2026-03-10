"""
Git Context Analyzer - The "Time Machine" for code history.

Provides deep insight into git history for specific files and line ranges,
enabling AI assistants to understand WHY code exists, not just WHAT it does.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path

try:
    from git import Repo, InvalidGitRepositoryError
except ImportError:
    Repo = None
    InvalidGitRepositoryError = Exception

logger = logging.getLogger(__name__)


class GitContextAnalyzer:
    """
    Analyzes git history to provide context about code changes.
    
    Features:
    - Line-level blame analysis (who, when, why)
    - File churn tracking (edit frequency)
    - Commit message retrieval
    """
    
    def __init__(self, repo_path: Optional[str] = None):
        """
        Initialize with path to git repository.
        
        Args:
            repo_path: Path to git repository root. If None, uses current directory.
        """
        self.repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._repo: Optional[Repo] = None
        
    @property
    def repo(self) -> Optional[Repo]:
        """Lazy-load the git repository."""
        if self._repo is None and Repo is not None:
            try:
                self._repo = Repo(self.repo_path, search_parent_directories=True)
            except InvalidGitRepositoryError:
                logger.warning(f"Not a git repository: {self.repo_path}")
                self._repo = None
        return self._repo
    
    def get_history(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get commit history for specific lines in a file.
        
        Uses git blame to find who modified specific lines and why.
        
        Args:
            file_path: Path to the file (relative to repo root)
            start_line: Starting line number (1-indexed). If None, analyzes entire file.
            end_line: Ending line number (1-indexed). If None, same as start_line.
            
        Returns:
            Dictionary containing:
            - file_path: The analyzed file
            - line_range: The line range analyzed
            - history: List of commit info for those lines
            - summary: Human-readable summary
        """
        if self.repo is None:
            return {
                "file_path": file_path,
                "error": "Not a git repository",
                "history": []
            }
        
        try:
            # Normalize file path relative to repo
            abs_file_path = Path(file_path)
            if not abs_file_path.is_absolute():
                abs_file_path = self.repo_path / file_path
                
            rel_path = abs_file_path.relative_to(self.repo.working_dir)
            
            # Get blame information
            blame_data = self._get_blame_for_lines(
                str(rel_path), start_line, end_line
            )
            
            return {
                "file_path": str(rel_path),
                "line_range": {
                    "start": start_line or 1,
                    "end": end_line or start_line or "EOF"
                },
                "history": blame_data,
                "summary": self._generate_history_summary(blame_data)
            }
            
        except Exception as e:
            logger.error(f"Error getting history for {file_path}: {e}")
            return {
                "file_path": file_path,
                "error": str(e),
                "history": []
            }
    
    def _get_blame_for_lines(
        self,
        file_path: str,
        start_line: Optional[int],
        end_line: Optional[int]
    ) -> List[Dict[str, Any]]:
        """Get blame information for specific lines."""
        if self.repo is None:
            return []
            
        blame_entries = []
        seen_commits = set()
        
        try:
            # Use git blame with line range if specified
            blame_args = []
            if start_line and end_line:
                blame_args = [f"-L{start_line},{end_line}"]
            elif start_line:
                blame_args = [f"-L{start_line},{start_line}"]
                
            blame_output = self.repo.git.blame(
                *blame_args,
                "--line-porcelain",
                file_path
            )
            
            # Parse porcelain output
            current_commit = {}
            for line in blame_output.split('\n'):
                if not line:
                    continue
                    
                # Commit hash line (starts with 40-char hash)
                if len(line) >= 40 and line[:40].isalnum():
                    parts = line.split()
                    commit_hash = parts[0]
                    
                    if commit_hash not in seen_commits:
                        if current_commit and 'hash' in current_commit:
                            blame_entries.append(current_commit)
                        
                        current_commit = {
                            'hash': commit_hash[:8],
                            'full_hash': commit_hash
                        }
                        seen_commits.add(commit_hash)
                        
                elif line.startswith('author '):
                    current_commit['author'] = line[7:]
                elif line.startswith('author-time '):
                    timestamp = int(line[12:])
                    current_commit['date'] = datetime.fromtimestamp(timestamp).isoformat()
                elif line.startswith('summary '):
                    current_commit['message'] = line[8:]
                    
            # Add last entry
            if current_commit and 'hash' in current_commit:
                blame_entries.append(current_commit)
                
        except Exception as e:
            logger.error(f"Error running git blame: {e}")
            
        return blame_entries
    
    def _generate_history_summary(self, blame_data: List[Dict[str, Any]]) -> str:
        """Generate a human-readable summary of the history."""
        if not blame_data:
            return "No git history available for these lines."
            
        # Get unique authors and most recent change
        authors = set(entry.get('author', 'Unknown') for entry in blame_data)
        
        # Sort by date to find most recent
        sorted_entries = sorted(
            blame_data,
            key=lambda x: x.get('date', ''),
            reverse=True
        )
        
        if sorted_entries:
            latest = sorted_entries[0]
            return (
                f"Last modified by {latest.get('author', 'Unknown')} "
                f"({latest.get('date', 'unknown date')}). "
                f"Reason: \"{latest.get('message', 'No commit message')}\". "
                f"Total contributors: {len(authors)}."
            )
        
        return "No significant history found."
    
    def get_churn(self, file_path: str, months: int = 6) -> Dict[str, Any]:
        """
        Calculate file churn (edit frequency) over a time period.
        
        High churn + high complexity = refactoring candidate.
        
        Args:
            file_path: Path to the file
            months: Number of months to analyze (default: 6)
            
        Returns:
            Dictionary containing:
            - file_path: The analyzed file
            - churn_count: Number of commits affecting this file
            - period_months: Time period analyzed
            - authors: List of unique contributors
            - commits: List of commit summaries
        """
        if self.repo is None:
            return {
                "file_path": file_path,
                "error": "Not a git repository",
                "churn_count": 0
            }
            
        try:
            # Calculate date threshold
            since_date = datetime.now() - timedelta(days=months * 30)
            since_str = since_date.strftime("%Y-%m-%d")
            
            # Normalize file path
            abs_file_path = Path(file_path)
            if not abs_file_path.is_absolute():
                abs_file_path = self.repo_path / file_path
                
            rel_path = abs_file_path.relative_to(self.repo.working_dir)
            
            # Get commits for this file
            log_output = self.repo.git.log(
                f"--since={since_str}",
                "--pretty=format:%h|%an|%s|%ci",
                "--",
                str(rel_path)
            )
            
            commits = []
            authors = set()
            
            for line in log_output.split('\n'):
                if not line.strip():
                    continue
                parts = line.split('|', 3)
                if len(parts) >= 3:
                    commits.append({
                        'hash': parts[0],
                        'author': parts[1],
                        'message': parts[2],
                        'date': parts[3] if len(parts) > 3 else ''
                    })
                    authors.add(parts[1])
            
            return {
                "file_path": str(rel_path),
                "churn_count": len(commits),
                "period_months": months,
                "authors": list(authors),
                "commits": commits[:10],  # Limit to 10 most recent
                "risk_level": self._calculate_churn_risk(len(commits), months)
            }
            
        except Exception as e:
            logger.error(f"Error calculating churn for {file_path}: {e}")
            return {
                "file_path": file_path,
                "error": str(e),
                "churn_count": 0
            }
    
    def _calculate_churn_risk(self, commit_count: int, months: int) -> str:
        """Determine risk level based on churn rate."""
        monthly_rate = commit_count / max(months, 1)
        
        if monthly_rate > 10:
            return "high"
        elif monthly_rate > 5:
            return "medium"
        else:
            return "low"
