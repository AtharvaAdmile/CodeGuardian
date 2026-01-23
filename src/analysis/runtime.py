"""
Runtime Loader - Bridge to Production Telemetry.

Loads runtime statistics (error rates, latency, etc.) from a local
JSON file that can be populated by CI/CD pipelines from observability tools.
"""

import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)


class RuntimeLoader:
    """
    Loads and provides runtime statistics for code files.
    
    This reads from a local runtime_stats.json file which should be
    populated by your observability pipeline (e.g., from Datadog, New Relic).
    """
    
    DEFAULT_STATS_PATH = Path(__file__).parent.parent.parent / "runtime_stats.json"
    
    def __init__(self, stats_path: Optional[str] = None):
        """
        Initialize the runtime loader.
        
        Args:
            stats_path: Path to runtime_stats.json file. If None, uses default.
        """
        self.stats_path = Path(stats_path) if stats_path else self.DEFAULT_STATS_PATH
        self._stats_cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl_seconds = 300  # 5 minute cache
        
    def _load_stats(self) -> Dict[str, Any]:
        """Load or return cached statistics."""
        now = datetime.now()
        
        # Return cached if still valid
        if (self._stats_cache is not None and 
            self._cache_time is not None and
            (now - self._cache_time).seconds < self._cache_ttl_seconds):
            return self._stats_cache
        
        # Load from file
        try:
            if self.stats_path.exists():
                with open(self.stats_path) as f:
                    self._stats_cache = json.load(f)
                    self._cache_time = now
                    return self._stats_cache
            else:
                logger.debug(f"Runtime stats file not found: {self.stats_path}")
                return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in runtime stats: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error loading runtime stats: {e}")
            return {}
    
    def get_stats(self, file_path: str) -> Dict[str, Any]:
        """
        Get runtime statistics for a specific file.
        
        Args:
            file_path: Path to the file to look up
            
        Returns:
            Dictionary containing:
            - file_path: The queried file
            - available: Whether runtime data exists
            - error_rate: Error rate percentage
            - avg_latency_ms: Average latency in milliseconds
            - p99_latency_ms: 99th percentile latency
            - last_error: Most recent error message
            - alert_level: none, warning, critical
        """
        stats = self._load_stats()
        
        # Normalize path for lookup
        normalized_path = self._normalize_path(file_path)
        
        # Look for matching entry
        file_stats = None
        
        # Try exact match first
        if normalized_path in stats:
            file_stats = stats[normalized_path]
        else:
            # Try partial path match
            for key in stats:
                if normalized_path.endswith(key) or key.endswith(normalized_path):
                    file_stats = stats[key]
                    break
        
        if file_stats is None:
            return {
                "file_path": file_path,
                "available": False,
                "message": "No runtime data available for this file"
            }
        
        # Calculate alert level
        alert_level = self._calculate_alert_level(file_stats)
        
        return {
            "file_path": file_path,
            "available": True,
            "error_rate": file_stats.get("error_rate", 0),
            "avg_latency_ms": file_stats.get("avg_latency_ms", 0),
            "p99_latency_ms": file_stats.get("p99_latency_ms", 0),
            "request_count": file_stats.get("request_count", 0),
            "last_error": file_stats.get("last_error"),
            "last_error_time": file_stats.get("last_error_time"),
            "alert_level": alert_level,
            "summary": self._generate_summary(file_stats, alert_level)
        }
    
    def _normalize_path(self, path: str) -> str:
        """Normalize a file path for lookup."""
        # Remove leading slashes and common prefixes
        path = path.lstrip("/")
        
        # Remove common root prefixes
        prefixes = ["src/", "lib/", "app/"]
        for prefix in prefixes:
            if path.startswith(prefix):
                path = path[len(prefix):]
                break
                
        return path
    
    def _calculate_alert_level(self, stats: Dict[str, Any]) -> str:
        """Determine alert level based on metrics."""
        error_rate = stats.get("error_rate", 0)
        p99_latency = stats.get("p99_latency_ms", 0)
        
        if error_rate > 5 or p99_latency > 5000:
            return "critical"
        elif error_rate > 1 or p99_latency > 2000:
            return "warning"
        else:
            return "none"
    
    def _generate_summary(self, stats: Dict[str, Any], alert_level: str) -> str:
        """Generate a human-readable summary."""
        parts = []
        
        error_rate = stats.get("error_rate", 0)
        avg_latency = stats.get("avg_latency_ms", 0)
        
        if alert_level == "critical":
            parts.append("🔴 CRITICAL:")
        elif alert_level == "warning":
            parts.append("⚠️ WARNING:")
        else:
            parts.append("✅ Healthy:")
        
        if error_rate > 0:
            parts.append(f"Error rate: {error_rate:.2f}%")
        else:
            parts.append("No errors")
            
        parts.append(f"Avg latency: {avg_latency:.0f}ms")
        
        last_error = stats.get("last_error")
        if last_error:
            parts.append(f"Last error: {last_error[:50]}...")
            
        return " | ".join(parts)
    
    def get_all_unhealthy(self) -> Dict[str, Any]:
        """
        Get all files with runtime issues.
        
        Returns:
            Dictionary containing files with warnings or critical alerts.
        """
        stats = self._load_stats()
        unhealthy = {}
        
        for file_path, file_stats in stats.items():
            alert_level = self._calculate_alert_level(file_stats)
            if alert_level != "none":
                unhealthy[file_path] = {
                    "alert_level": alert_level,
                    "error_rate": file_stats.get("error_rate", 0),
                    "avg_latency_ms": file_stats.get("avg_latency_ms", 0)
                }
                
        return {
            "unhealthy_files": unhealthy,
            "total_unhealthy": len(unhealthy),
            "critical_count": sum(1 for v in unhealthy.values() if v["alert_level"] == "critical"),
            "warning_count": sum(1 for v in unhealthy.values() if v["alert_level"] == "warning")
        }
