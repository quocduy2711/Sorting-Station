"""
Debounce filter for sensor inputs.

RULE: Vision sensor debounce to prevent duplicate reads.
RẤT QUAN TRỌNG: Factory I/O vision sensor holds value for multiple cycles.
"""
import logging
import time
from typing import Optional


logger = logging.getLogger(__name__)


class DebounceFilter:
    """
    Debounces sensor inputs to prevent spurious edge detection.
    
    Particularly important for vision sensor which holds value for ~100ms.
    """

    def __init__(self, debounce_time_ms: float = 50):
        """
        Initialize debounce filter.
        
        Args:
            debounce_time_ms: Minimum time between valid state changes
        """
        self.debounce_time_ms = debounce_time_ms
        self.last_change_time = 0.0
        self.last_value: Optional[int] = None
        self.debounce_count = 0

    def filter(self, value: int) -> Optional[int]:
        """
        Filter input value with debounce.
        
        Returns:
            Value if state changed (after debounce), None otherwise.
        """
        current_time = time.monotonic()
        time_since_change = (current_time - self.last_change_time) * 1000

        # Value didn't change
        if value == self.last_value:
            return None

        # Value changed but still in debounce window
        if time_since_change < self.debounce_time_ms:
            self.debounce_count += 1
            return None

        # Valid state change (debounced)
        self.last_value = value
        self.last_change_time = current_time
        return value

    def reset(self) -> None:
        """Reset debounce filter."""
        self.last_value = None
        self.last_change_time = time.monotonic()

    def get_debounce_count(self) -> int:
        """Get number of debounced events."""
        return self.debounce_count
