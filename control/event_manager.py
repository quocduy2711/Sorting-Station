"""
Event system for industrial control.

RULE: Event-driven architecture, not polling.
"""
import logging
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, List, Dict, Any
from datetime import datetime


logger = logging.getLogger(__name__)


class SystemEvent(Enum):
    """
    System-wide events that drive control logic.
    """
    PRODUCT_CREATED = "PRODUCT_CREATED"
    PRODUCT_PASSED_BLADE = "PRODUCT_PASSED_BLADE"
    VISION_ID_READ = "VISION_ID_READ"
    SORTER_ACTIVATED = "SORTER_ACTIVATED"
    PRODUCT_REMOVED = "PRODUCT_REMOVED"
    ALARM_TRIGGERED = "ALARM_TRIGGERED"
    SYSTEM_RESET = "SYSTEM_RESET"
    START_BUTTON_PRESSED = "START_BUTTON_PRESSED"
    STOP_BUTTON_PRESSED = "STOP_BUTTON_PRESSED"
    ESTOP_ACTIVATED = "ESTOP_ACTIVATED"
    ESTOP_CLEARED = "ESTOP_CLEARED"
    MODE_CHANGED = "MODE_CHANGED"
    TIMEOUT_OCCURRED = "TIMEOUT_OCCURRED"


@dataclass
class Event:
    """
    Represents a single event with metadata.
    """
    event_type: SystemEvent
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    source: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    
    def __repr__(self) -> str:
        return f"Event({self.event_type.value}, source={self.source}, data={self.data})"


class EventManager:
    """
    Central event bus for system.
    
    Handlers are called synchronously in order of registration.
    """

    def __init__(self):
        """Initialize event manager."""
        self._handlers: Dict[SystemEvent, List[Callable]] = {}
        self._event_log: List[Event] = []
        self.event_count = 0

    def subscribe(self, event_type: SystemEvent, handler: Callable) -> None:
        """
        Subscribe to an event type.
        
        Args:
            event_type: Type of event to listen for
            handler: Callable that takes Event as argument
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        
        self._handlers[event_type].append(handler)
        logger.debug(f"Subscribed {handler.__name__} to {event_type.value}")

    async def emit(self, event_type: SystemEvent, source: str = "", data: Dict = None) -> None:
        """
        Emit an event to all subscribers.
        
        Args:
            event_type: Type of event
            source: Source of event (for logging)
            data: Event data
        """
        event = Event(
            event_type=event_type,
            source=source,
            data=data or {}
        )

        logger.debug(f"Event emitted: {event}")
        self._event_log.append(event)
        self.event_count += 1

        # Call all handlers synchronously
        if event_type in self._handlers:
            for handler in self._handlers[event_type]:
                try:
                    if hasattr(handler, '__await__'):
                        # Async handler
                        await handler(event)
                    else:
                        # Sync handler
                        handler(event)
                except Exception as e:
                    logger.error(f"Error in event handler {handler.__name__}: {e}")

    def get_event_log(self, limit: int = 100) -> List[Event]:
        """Get recent events."""
        return self._event_log[-limit:]

    def clear_event_log(self) -> None:
        """Clear event log."""
        self._event_log.clear()

    def get_handler_count(self, event_type: SystemEvent) -> int:
        """Get number of handlers for an event type."""
        return len(self._handlers.get(event_type, []))
