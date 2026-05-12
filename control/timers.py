"""
Timer/timeout management system.

RULE: Every operation MUST have timeout protection.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Callable
from enum import Enum


logger = logging.getLogger(__name__)


class TimerState(Enum):
    """States of a timer."""
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


@dataclass
class Timer:
    """
    Represents a single timeout/timer.
    """
    name: str
    timeout_sec: float
    state: TimerState = TimerState.IDLE
    start_time: float = field(default_factory=time.monotonic)
    on_timeout: Optional[Callable] = None
    tag: str = ""  # For tracking

    def start(self) -> None:
        """Start the timer."""
        self.start_time = time.monotonic()
        self.state = TimerState.RUNNING

    def check_expired(self) -> bool:
        """Check if timer has expired."""
        if self.state != TimerState.RUNNING:
            return False
        
        elapsed = time.monotonic() - self.start_time
        if elapsed >= self.timeout_sec:
            self.state = TimerState.EXPIRED
            logger.warning(f"Timer expired: {self.name} ({self.tag})")
            return True
        
        return False

    def cancel(self) -> None:
        """Cancel the timer."""
        self.state = TimerState.CANCELLED

    def get_remaining_sec(self) -> float:
        """Get remaining time in seconds."""
        if self.state != TimerState.RUNNING:
            return 0.0
        
        elapsed = time.monotonic() - self.start_time
        return max(0.0, self.timeout_sec - elapsed)

    def is_running(self) -> bool:
        """Check if timer is running."""
        return self.state == TimerState.RUNNING


class TimerManager:
    """
    Manages multiple timers for various operations.
    
    RULE: Every critical operation has a timeout.
    """

    def __init__(self):
        """Initialize timer manager."""
        self.timers: Dict[str, Timer] = {}

    def create_timer(self, name: str, timeout_sec: float, tag: str = "") -> Timer:
        """
        Create and start a timer.
        
        Args:
            name: Unique timer name
            timeout_sec: Timeout duration in seconds
            tag: Optional tag for logging
            
        Returns:
            Timer object
        """
        timer = Timer(name=name, timeout_sec=timeout_sec, tag=tag)
        timer.start()
        self.timers[name] = timer
        logger.debug(f"Timer created: {name} ({timeout_sec}s, tag={tag})")
        return timer

    def check_all_timers(self) -> Dict[str, Timer]:
        """
        Check all running timers for expiration.
        
        Returns:
            Dict of expired timers.
        """
        expired = {}
        
        for name, timer in list(self.timers.items()):
            if timer.check_expired():
                expired[name] = timer
                
                # Call timeout handler if set
                if timer.on_timeout:
                    try:
                        timer.on_timeout(timer)
                    except Exception as e:
                        logger.error(f"Error in timeout handler for {name}: {e}")
        
        return expired

    def cancel_timer(self, name: str) -> bool:
        """
        Cancel a timer.
        
        Returns:
            True if timer was running and cancelled.
        """
        if name in self.timers:
            timer = self.timers[name]
            if timer.is_running():
                timer.cancel()
                logger.debug(f"Timer cancelled: {name}")
                return True
        
        return False

    def reset_timer(self, name: str) -> bool:
        """Reset a timer (restart it)."""
        if name in self.timers:
            self.timers[name].start()
            return True
        return False

    def get_timer(self, name: str) -> Optional[Timer]:
        """Get a timer by name."""
        return self.timers.get(name)

    def clear_timers(self) -> None:
        """Clear all timers."""
        self.timers.clear()

    def get_running_timers(self) -> Dict[str, Timer]:
        """Get all running timers."""
        return {
            name: timer 
            for name, timer in self.timers.items() 
            if timer.is_running()
        }
