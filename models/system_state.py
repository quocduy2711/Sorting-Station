"""
System-level state and operation tracking.
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import time


class SystemStateEnum(Enum):
    """System finite state machine states."""
    IDLE = "IDLE"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    WAITING_PRODUCT = "WAITING_PRODUCT"
    WAITING_CLEAR_ZONE = "WAITING_CLEAR_ZONE"
    READING_ID = "READING_ID"
    MOVING_TO_SORTER = "MOVING_TO_SORTER"
    SORTING = "SORTING"
    COMPLETE = "COMPLETE"
    STOPPED = "STOPPED"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    ERROR = "ERROR"
    RESETTING = "RESETTING"


@dataclass
class SystemState:
    """
    Tracks overall system state and cycle metrics.
    
    RULE: Protected by asyncio.Lock()
    """
    state: SystemStateEnum = SystemStateEnum.IDLE
    state_changed_at: float = field(default_factory=time.monotonic)
    
    # Metrics
    total_products: int = 0
    successful_sorts: int = 0
    failed_sorts: int = 0
    alarm_count: int = 0
    
    # Timing
    scan_cycle_ms: float = 0.0
    last_scan_duration_ms: float = 0.0
    
    # Connectivity
    modbus_connected: bool = False
    mqtt_connected: bool = False
    
    # Error tracking
    last_error: Optional[str] = None
    last_error_time: Optional[float] = None
    
    # Operational time
    startup_time: float = field(default_factory=time.monotonic)

    def get_state_duration_ms(self) -> float:
        """Get how long we've been in current state."""
        return (time.monotonic() - self.state_changed_at) * 1000

    def set_state(self, new_state: SystemStateEnum) -> None:
        """Transition to new state."""
        self.state = new_state
        self.state_changed_at = time.monotonic()

    def record_error(self, error_message: str) -> None:
        """Record error occurrence."""
        self.last_error = error_message
        self.last_error_time = time.monotonic()
        self.alarm_count += 1

    def get_uptime_seconds(self) -> float:
        """Get system uptime since startup."""
        return time.monotonic() - self.startup_time

    def get_success_rate(self) -> float:
        """Get successful sort rate."""
        total = self.successful_sorts + self.failed_sorts
        if total == 0:
            return 0.0
        return (self.successful_sorts / total) * 100

    def __repr__(self) -> str:
        return (f"SystemState({self.state.value}, "
                f"products={self.total_products}, "
                f"success={self.successful_sorts}/{self.failed_sorts}, "
                f"alarms={self.alarm_count})")
