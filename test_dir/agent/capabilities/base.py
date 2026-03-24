"""
Base Capability Class
All agent capabilities inherit from this abstract base class.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class BaseCapability(ABC):
    """Abstract base class for all agent capabilities"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.enabled = True
        self.last_run = None
        self.error_count = 0
        
    @property
    @abstractmethod
    def capability_id(self) -> str:
        """Unique identifier for this capability"""
        pass
    
    @property
    @abstractmethod
    def capability_name(self) -> str:
        """Human-readable name"""
        pass
    
    @abstractmethod
    def collect(self) -> Dict[str, Any]:
        """
        Execute the capability's data collection logic.
        Returns a dictionary of collected data.
        Must not raise exceptions - handle errors internally.
        """
        pass
    
    def execute(self) -> Dict[str, Any]:
        """
        Wrapper around collect() that handles errors gracefully.
        """
        try:
            result = self.collect()
            self.error_count = 0
            return {
                "capability": self.capability_id,
                "status": "success",
                "data": result
            }
        except Exception as e:
            self.error_count += 1
            logger.error(f"{self.capability_name} failed: {e}", exc_info=True)
            return {
                "capability": self.capability_id,
                "status": "error",
                "error": str(e),
                "error_count": self.error_count
            }
    
    def should_run(self, interval_seconds: int) -> bool:
        """Check if enough time has passed since last run"""
        if self.last_run is None:
            return True
        
        from datetime import datetime, timedelta
        elapsed = (datetime.now() - self.last_run).total_seconds()
        return elapsed >= interval_seconds
