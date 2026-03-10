"""
ProgressTracker module for tracking indexing progress.
"""

from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
import uuid


@dataclass
class ProgressStatus:
    """Status of an indexing operation."""
    tracking_id: str
    total_files: int
    files_processed: int
    current_file: Optional[str]
    percentage: float
    status: str  # 'in_progress', 'completed', 'error'
    errors: List[Dict[str, str]] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None


class ProgressTracker:
    """
    Tracks and reports indexing progress for the codebase indexer.
    
    Maintains progress state for multiple concurrent indexing operations.
    Designed to work with Streamlit session state for real-time updates.
    """
    
    def __init__(self):
        """Initialize the ProgressTracker with empty tracking state."""
        self._tracking_sessions: Dict[str, ProgressStatus] = {}
    
    def start_tracking(self, total_files: int) -> str:
        """
        Start tracking a new indexing operation.
        
        Args:
            total_files: Total number of files to be processed
            
        Returns:
            Unique tracking ID for this operation
        """
        tracking_id = str(uuid.uuid4())
        
        progress_status = ProgressStatus(
            tracking_id=tracking_id,
            total_files=total_files,
            files_processed=0,
            current_file=None,
            percentage=0.0,
            status='in_progress',
            errors=[],
            start_time=datetime.now(),
            end_time=None
        )
        
        self._tracking_sessions[tracking_id] = progress_status
        return tracking_id
    
    def update_progress(
        self,
        tracking_id: str,
        current_file: Optional[str],
        processed: int
    ) -> None:
        """
        Update progress for an ongoing indexing operation.
        
        Args:
            tracking_id: Unique tracking ID from start_tracking()
            current_file: Name of the file currently being processed (None if batch complete)
            processed: Number of files processed so far
        """
        if tracking_id not in self._tracking_sessions:
            raise ValueError(f"Invalid tracking ID: {tracking_id}")
        
        progress = self._tracking_sessions[tracking_id]
        progress.current_file = current_file
        progress.files_processed = processed
        
        # Calculate percentage
        if progress.total_files > 0:
            progress.percentage = (processed / progress.total_files) * 100
        else:
            progress.percentage = 0.0
    
    def complete_tracking(self, tracking_id: str) -> None:
        """
        Mark an indexing operation as completed.
        
        Args:
            tracking_id: Unique tracking ID from start_tracking()
        """
        if tracking_id not in self._tracking_sessions:
            raise ValueError(f"Invalid tracking ID: {tracking_id}")
        
        progress = self._tracking_sessions[tracking_id]
        progress.status = 'completed'
        progress.percentage = 100.0
        progress.end_time = datetime.now()
        progress.current_file = None
    
    def report_error(
        self,
        tracking_id: str,
        file: str,
        error: str
    ) -> None:
        """
        Report an error for a specific file during indexing.
        
        Args:
            tracking_id: Unique tracking ID from start_tracking()
            file: Name of the file that caused the error
            error: Error message
        """
        if tracking_id not in self._tracking_sessions:
            raise ValueError(f"Invalid tracking ID: {tracking_id}")
        
        progress = self._tracking_sessions[tracking_id]
        progress.errors.append({
            'file': file,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
    
    def get_progress(self, tracking_id: str) -> ProgressStatus:
        """
        Get current progress status for an indexing operation.
        
        Args:
            tracking_id: Unique tracking ID from start_tracking()
            
        Returns:
            ProgressStatus object with current state
        """
        if tracking_id not in self._tracking_sessions:
            raise ValueError(f"Invalid tracking ID: {tracking_id}")
        
        return self._tracking_sessions[tracking_id]
    
    def clear_tracking(self, tracking_id: str) -> None:
        """
        Clear tracking data for a completed operation.
        
        Args:
            tracking_id: Unique tracking ID from start_tracking()
        """
        if tracking_id in self._tracking_sessions:
            del self._tracking_sessions[tracking_id]
    
    def get_all_tracking_ids(self) -> List[str]:
        """
        Get all active tracking IDs.
        
        Returns:
            List of tracking IDs
        """
        return list(self._tracking_sessions.keys())
