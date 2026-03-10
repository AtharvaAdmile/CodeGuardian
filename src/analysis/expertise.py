"""
Expertise Tracker - The "Intelligent Routing System" for code ownership.

Identifies who truly understands a codebase based on recency and frequency
of contributions, not just raw line counts.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

try:
    from git import Repo, InvalidGitRepositoryError
except ImportError:
    Repo = None
    InvalidGitRepositoryError = Exception

logger = logging.getLogger(__name__)


class ExpertiseTracker:
    """
    Tracks code ownership using a recency-weighted scoring algorithm.
    
    Score Formula: (LinesOwned * 1) + (CommitsLast3Months * 5)
    
    This weights recent activity heavily, so an active contributor
    is ranked higher than someone who wrote code years ago.
    """
    
    # Weights for scoring
    LINES_WEIGHT = 1.0
    RECENT_COMMIT_WEIGHT = 5.0
    RECENCY_MONTHS = 3
    
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
    
    def find_owners(self, file_path: str) -> Dict[str, Any]:
        """
        Find the primary experts for a file based on contribution patterns.
        
        Uses git blame to count lines owned and git log to count recent commits.
        
        Args:
            file_path: Path to the file or directory to analyze
            
        Returns:
            Dictionary containing:
            - primary_expert: The top contributor
            - backup: Second-highest contributor
            - experts: Full list with scores
            - last_active: When the file was last modified
        """
        if self.repo is None:
            return {
                "file_path": file_path,
                "error": "Not a git repository",
                "primary_expert": None,
                "backup": None
            }
            
        try:
            # Normalize file path
            abs_file_path = Path(file_path)
            if not abs_file_path.is_absolute():
                abs_file_path = self.repo_path / file_path
                
            rel_path = abs_file_path.relative_to(self.repo.working_dir)
            
            # Get line ownership from blame
            line_counts = self._get_line_ownership(str(rel_path))
            
            # Get recent commit counts
            recent_commits = self._get_recent_commits(str(rel_path))
            
            # Calculate scores
            scores = self._calculate_expert_scores(line_counts, recent_commits)
            
            # Sort by score
            sorted_experts = sorted(
                scores.items(),
                key=lambda x: x[1]['score'],
                reverse=True
            )
            
            # Build response
            experts_list = [
                {
                    "name": name,
                    "score": data['score'],
                    "lines_owned": data['lines'],
                    "recent_commits": data['commits']
                }
                for name, data in sorted_experts[:5]  # Top 5
            ]
            
            primary = sorted_experts[0] if sorted_experts else (None, {})
            backup = sorted_experts[1] if len(sorted_experts) > 1 else (None, {})
            
            # Get last modification date
            last_active = self._get_last_modification(str(rel_path))
            
            return {
                "file_path": str(rel_path),
                "primary_expert": primary[0],
                "primary_score": primary[1].get('score', 0),
                "backup": backup[0],
                "backup_score": backup[1].get('score', 0),
                "experts": experts_list,
                "last_active": last_active,
                "analysis_period_months": self.RECENCY_MONTHS
            }
            
        except Exception as e:
            logger.error(f"Error finding owners for {file_path}: {e}")
            return {
                "file_path": file_path,
                "error": str(e),
                "primary_expert": None,
                "backup": None
            }
    
    def _get_line_ownership(self, file_path: str) -> Dict[str, int]:
        """Get line count per author using git blame."""
        line_counts: Dict[str, int] = defaultdict(int)
        
        if self.repo is None:
            return dict(line_counts)
            
        try:
            blame_output = self.repo.git.blame(
                "--line-porcelain",
                file_path
            )
            
            for line in blame_output.split('\n'):
                if line.startswith('author '):
                    author = line[7:]
                    line_counts[author] += 1
                    
        except Exception as e:
            logger.debug(f"Error running git blame: {e}")
            
        return dict(line_counts)
    
    def _get_recent_commits(self, file_path: str) -> Dict[str, int]:
        """Get commit count per author in the recency period."""
        commit_counts: Dict[str, int] = defaultdict(int)
        
        if self.repo is None:
            return dict(commit_counts)
            
        try:
            since_date = datetime.now() - timedelta(days=self.RECENCY_MONTHS * 30)
            since_str = since_date.strftime("%Y-%m-%d")
            
            log_output = self.repo.git.log(
                f"--since={since_str}",
                "--pretty=format:%an",
                "--",
                file_path
            )
            
            for author in log_output.split('\n'):
                if author.strip():
                    commit_counts[author.strip()] += 1
                    
        except Exception as e:
            logger.debug(f"Error getting recent commits: {e}")
            
        return dict(commit_counts)
    
    def _calculate_expert_scores(
        self,
        line_counts: Dict[str, int],
        commit_counts: Dict[str, int]
    ) -> Dict[str, Dict[str, Any]]:
        """Calculate expertise scores for all contributors."""
        # Combine all authors
        all_authors = set(line_counts.keys()) | set(commit_counts.keys())
        
        scores = {}
        for author in all_authors:
            lines = line_counts.get(author, 0)
            commits = commit_counts.get(author, 0)
            
            score = (lines * self.LINES_WEIGHT) + (commits * self.RECENT_COMMIT_WEIGHT)
            
            scores[author] = {
                'score': round(score, 1),
                'lines': lines,
                'commits': commits
            }
            
        return scores
    
    def _get_last_modification(self, file_path: str) -> Optional[str]:
        """Get the date of the last modification to the file."""
        if self.repo is None:
            return None
            
        try:
            log_output = self.repo.git.log(
                "-1",
                "--pretty=format:%ci",
                "--",
                file_path
            )
            
            if log_output.strip():
                # Parse and format the date
                date_str = log_output.strip()
                # Git format: "2024-01-15 10:30:45 -0500"
                parts = date_str.split()
                if parts:
                    # Return relative time description
                    date_part = parts[0]
                    commit_date = datetime.strptime(date_part, "%Y-%m-%d")
                    days_ago = (datetime.now() - commit_date).days
                    
                    if days_ago == 0:
                        return "today"
                    elif days_ago == 1:
                        return "yesterday"
                    elif days_ago < 7:
                        return f"{days_ago} days ago"
                    elif days_ago < 30:
                        weeks = days_ago // 7
                        return f"{weeks} week{'s' if weeks > 1 else ''} ago"
                    elif days_ago < 365:
                        months = days_ago // 30
                        return f"{months} month{'s' if months > 1 else ''} ago"
                    else:
                        years = days_ago // 365
                        return f"{years} year{'s' if years > 1 else ''} ago"
                        
        except Exception as e:
            logger.debug(f"Error getting last modification: {e}")
            
        return None
