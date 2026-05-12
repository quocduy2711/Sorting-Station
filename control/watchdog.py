"""
Watchdog system to detect runtime stalls and deadlocks.

RULE: Detect coroutine freeze, scan stall, modbus deadlock, runtime overload.
RULE: On failure, trigger failsafe_shutdown.
"""
import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable


logger = logging.getLogger(__name__)


@dataclass
class WatchdogCheck:
    """Represents a single watchdog check."""
    name: str
    last_heartbeat: float = 0.0
    timeout_sec: float = 5.0
    enabled: bool = True
    failed: bool = False
    failure_count: int = 0

    def heartbeat(self) -> None:
        """Record a heartbeat."""
        self.last_heartbeat = time.monotonic()
        self.failed = False

    def check(self) -> bool:
        """
        Check if watchdog has timed out.
        
        Returns:
            True if timed out (failed).
        """
        if not self.enabled:
            return False
        
        elapsed = time.monotonic() - self.last_heartbeat
        if elapsed > self.timeout_sec:
            self.failed = True
            self.failure_count += 1
            return True
        
        return False

    def get_age_sec(self) -> float:
        """Get time since last heartbeat."""
        return time.monotonic() - self.last_heartbeat


class Watchdog:
    """
    System watchdog to detect runtime stalls and deadlocks.
    
    Monitors critical coroutines and operations.
    """

    def __init__(self, on_failure: Optional[Callable] = None):
        """
        Initialize watchdog.
        
        Args:
            on_failure: Callback when watchdog detects failure
        """
        self.checks: dict[str, WatchdogCheck] = {}
        self.on_failure = on_failure
        self.global_failure_count = 0

    def register(self, name: str, timeout_sec: float = 5.0) -> None:
        """
        Register a watchdog check.
        
        Args:
            name: Check name
            timeout_sec: Timeout duration in seconds
        """
        self.checks[name] = WatchdogCheck(
            name=name,
            timeout_sec=timeout_sec,
            last_heartbeat=time.monotonic()
        )
        logger.debug(f"Watchdog registered: {name} ({timeout_sec}s)")

    def heartbeat(self, name: str) -> None:
        """
        Record a heartbeat for a check.
        
        Called when the monitored coroutine/operation is active.
        
        Args:
            name: Check name
        """
        if name in self.checks:
            self.checks[name].heartbeat()

    async def check_all(self) -> dict[str, WatchdogCheck]:
        """
        Check all registered watchdogs.
        
        Returns:
            Dict of failed checks.
        """
        failed = {}
        
        for name, check in self.checks.items():
            if check.check():
                failed[name] = check
                logger.critical(f"Watchdog FAILED: {name} (age: {check.get_age_sec():.2f}s)")
                self.global_failure_count += 1
                
                # Call failure callback
                if self.on_failure:
                    try:
                        if hasattr(self.on_failure, '__await__'):
                            await self.on_failure(name, check)
                        else:
                            self.on_failure(name, check)
                    except Exception as e:
                        logger.error(f"Error in watchdog failure handler: {e}")
        
        return failed

    def get_check(self, name: str) -> Optional[WatchdogCheck]:
        """Get a specific watchdog check."""
        return self.checks.get(name)

    def enable_check(self, name: str) -> None:
        """Enable a specific check."""
        if name in self.checks:
            self.checks[name].enabled = True

    def disable_check(self, name: str) -> None:
        """Disable a specific check."""
        if name in self.checks:
            self.checks[name].enabled = False

    def get_stats(self) -> dict:
        """Get watchdog statistics."""
        total_failures = sum(c.failure_count for c in self.checks.values())
        
        return {
            "total_checks": len(self.checks),
            "failed_checks": sum(1 for c in self.checks.values() if c.failed),
            "total_failures": total_failures,
            "global_failures": self.global_failure_count,
        }

    def reset(self) -> None:
        """Reset watchdog."""
        for check in self.checks.values():
            check.failed = False
            check.last_heartbeat = time.monotonic()
