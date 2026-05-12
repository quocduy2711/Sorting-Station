"""
Alarm system for detecting and managing system faults.
"""
import logging
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


class AlarmType(Enum):
    """Types of alarms."""
    VISION_TIMEOUT = "VISION_TIMEOUT"
    INVALID_PRODUCT_ID = "INVALID_PRODUCT_ID"
    CONVEYOR_JAM = "CONVEYOR_JAM"
    SORT_TIMEOUT = "SORT_TIMEOUT"
    BLADE_TIMEOUT = "BLADE_TIMEOUT"
    MODBUS_DISCONNECT = "MODBUS_DISCONNECT"
    WATCHDOG_FAILURE = "WATCHDOG_FAILURE"
    EMERGENCY_STOP = "EMERGENCY_STOP"
    UNKNOWN = "UNKNOWN"


@dataclass
class Alarm:
    """
    Represents a single alarm event.
    """
    alarm_type: AlarmType
    timestamp: float = field(default_factory=time.monotonic)
    message: str = ""
    source: str = ""
    data: Dict = field(default_factory=dict)
    acknowledged: bool = False
    cleared: bool = False

    def acknowledge(self) -> None:
        """Mark alarm as acknowledged."""
        self.acknowledged = True

    def clear(self) -> None:
        """Mark alarm as cleared."""
        self.cleared = True

    def __repr__(self) -> str:
        return (f"Alarm({self.alarm_type.value}, {self.message}, "
                f"ack={self.acknowledged}, cleared={self.cleared})")


class AlarmManager:
    """
    Central alarm system for the industrial runtime.
    
    Tracks active alarms, history, and acknowledgment state.
    """

    def __init__(self):
        """Initialize alarm manager."""
        self.active_alarms: Dict[AlarmType, List[Alarm]] = {}
        self.alarm_history: List[Alarm] = []
        self.total_alarms = 0

    def trigger_alarm(
        self,
        alarm_type: AlarmType,
        message: str = "",
        source: str = "",
        data: Dict = None
    ) -> Alarm:
        """
        Trigger a new alarm.
        
        Args:
            alarm_type: Type of alarm
            message: Human-readable message
            source: Source of alarm
            data: Additional data
            
        Returns:
            The Alarm object
        """
        alarm = Alarm(
            alarm_type=alarm_type,
            message=message,
            source=source,
            data=data or {}
        )

        if alarm_type not in self.active_alarms:
            self.active_alarms[alarm_type] = []

        self.active_alarms[alarm_type].append(alarm)
        self.alarm_history.append(alarm)
        self.total_alarms += 1

        logger.critical(f"ALARM: {alarm_type.value} - {message} (source: {source})")

        return alarm

    def clear_alarm_type(self, alarm_type: AlarmType) -> int:
        """
        Clear all alarms of a specific type.
        
        Returns:
            Number of alarms cleared
        """
        if alarm_type not in self.active_alarms:
            return 0

        cleared = 0
        for alarm in self.active_alarms[alarm_type]:
            alarm.clear()
            cleared += 1

        del self.active_alarms[alarm_type]
        logger.info(f"Cleared {cleared} alarms of type {alarm_type.value}")

        return cleared

    def acknowledge_alarm_type(self, alarm_type: AlarmType) -> int:
        """
        Acknowledge all alarms of a specific type.
        
        Returns:
            Number of alarms acknowledged
        """
        if alarm_type not in self.active_alarms:
            return 0

        acknowledged = 0
        for alarm in self.active_alarms[alarm_type]:
            alarm.acknowledge()
            acknowledged += 1

        logger.info(f"Acknowledged {acknowledged} alarms of type {alarm_type.value}")

        return acknowledged

    def get_active_alarms(self) -> Dict[AlarmType, List[Alarm]]:
        """Get all active alarms."""
        return self.active_alarms

    def get_active_alarm_count(self) -> int:
        """Get count of active alarms."""
        return sum(len(alarms) for alarms in self.active_alarms.values())

    def get_unacknowledged_alarm_count(self) -> int:
        """Get count of unacknowledged alarms."""
        count = 0
        for alarms in self.active_alarms.values():
            count += sum(1 for a in alarms if not a.acknowledged)
        return count

    def has_active_alarms(self) -> bool:
        """Check if there are any active alarms."""
        return len(self.active_alarms) > 0

    def has_critical_alarms(self) -> bool:
        """Check if there are any critical alarms."""
        critical_types = {
            AlarmType.MODBUS_DISCONNECT,
            AlarmType.WATCHDOG_FAILURE,
            AlarmType.EMERGENCY_STOP
        }
        return any(t in self.active_alarms for t in critical_types)

    def get_alarm_history(self, limit: int = 100) -> List[Alarm]:
        """Get recent alarm history."""
        return self.alarm_history[-limit:]

    def clear_history(self) -> None:
        """Clear alarm history."""
        self.alarm_history.clear()

    def get_stats(self) -> Dict:
        """Get alarm statistics."""
        return {
            "total_alarms": self.total_alarms,
            "active_alarms": self.get_active_alarm_count(),
            "unacknowledged": self.get_unacknowledged_alarm_count(),
            "has_critical": self.has_critical_alarms(),
        }
