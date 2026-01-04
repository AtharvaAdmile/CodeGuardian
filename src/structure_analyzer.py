import os
from pathlib import Path
from typing import Dict, Any, Set

class StructureAnalyzer:
    """
    Analyzes the structure of a codebase to determine its organization score.
    """
    
    EXCLUDED_DIRS = {
        '__pycache__', 'node_modules', '.git', '.venv', 'venv',
        'env', '.env', 'dist', 'build', '.next', '.nuxt',
        'coverage', '.pytest_cache', '.mypy_cache', '.tox',
        '.idea', '.vscode'
    }
    
    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()
        
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
                
                # Only count code/relevant files? 
                # The prompt implies general file organization, so we'll count all 
                # except maybe hidden system files if we wanted to be strict, 
                # but os.walk usually handles standard files.
                
                current_files_count = 0
                for file in files:
                    if file.startswith('.'): # Skip hidden files like .gitignore
                        continue
                        
                    total_files += 1
                    current_files_count += 1
                    if is_root:
                        root_files += 1
                
                if current_files_count > 0:
                    folders_with_files.add(root)

        except Exception as e:
            # In case of permission error or bad path
            return {
                "score": 0.0,
                "has_git": has_git,
                "total_files": 0,
                "root_files": 0,
                "folders_count": 0,
                "error": str(e)
            }

        score = 0.0
        
        # Heuristic: Git tracking (Bonus 2 points)
        if has_git:
            score += 2.0
            
        # Heuristic: File organization (Max 8 points)
        # Score based on ratio of files in subdirectories vs root
        if total_files > 0:
            non_root_files = total_files - root_files
            organization_ratio = non_root_files / total_files
            
            # If only a few files (e.g. < 5) exist, the structure matters less, 
            # but we will stick to the requested logic.
            
            score += organization_ratio * 8.0
            
        # Cap score at 10
        score = min(10.0, score)

        return {
            "score": round(score, 1),
            "has_git": has_git,
            "total_files": total_files,
            "root_files": root_files,
            "folders_count": len(folders_with_files)
        }
