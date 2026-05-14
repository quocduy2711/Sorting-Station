"""
Async Event Bus — internal pub/sub for industrial control.

Architecture:
- emit()    → puts event onto asyncio.Queue (non-blocking, fire-and-forget)
- dispatch_loop() → background coroutine that drains queue and calls handlers
- subscribe() → register async or sync handlers per event type

RULE: emit() never awaits handlers directly → no coupling between emitter and handler.
RULE: All inter-module communication goes through EventManager, not direct calls.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Event type registry ───────────────────────────────────────────────────────

class SystemEvent(Enum):
    """All system events. New events must be declared here."""

    # Product lifecycle
    PRODUCT_DETECTED    = "PRODUCT_DETECTED"     # Vision sensor saw a product
    PRODUCT_CLASSIFIED  = "PRODUCT_CLASSIFIED"   # Product ID confirmed + sorter assigned
    PRODUCT_SORT_DONE   = "PRODUCT_SORT_DONE"    # Product successfully removed from sorter
    PRODUCT_FAILED      = "PRODUCT_FAILED"       # Product processing failed

    # Physical sensors
    AT_EXIT_TRIGGERED   = "AT_EXIT_TRIGGERED"    # at_exit sensor: product fell into remover

    # Sorting
    SORT_COMMAND        = "SORT_COMMAND"          # Instruct FSM to activate sorter N

    # System control
    START_BUTTON_PRESSED = "START_BUTTON_PRESSED"
    STOP_BUTTON_PRESSED  = "STOP_BUTTON_PRESSED"
    ESTOP_ACTIVATED      = "ESTOP_ACTIVATED"
    ESTOP_CLEARED        = "ESTOP_CLEARED"
    MODE_CHANGED         = "MODE_CHANGED"
    SYSTEM_RESET         = "SYSTEM_RESET"

    # FSM transitions
    FSM_STATE_CHANGED    = "FSM_STATE_CHANGED"

    # Alarms & faults
    ALARM_TRIGGERED      = "ALARM_TRIGGERED"
    TIMEOUT_OCCURRED     = "TIMEOUT_OCCURRED"
    WATCHDOG_TIMEOUT     = "WATCHDOG_TIMEOUT"

    # Connectivity
    MODBUS_DISCONNECTED  = "MODBUS_DISCONNECTED"
    MODBUS_RECONNECTED   = "MODBUS_RECONNECTED"
    MQTT_DISCONNECTED    = "MQTT_DISCONNECTED"
    MQTT_RECONNECTED     = "MQTT_RECONNECTED"


# ── Event dataclass ───────────────────────────────────────────────────────────

@dataclass
class Event:
    """A single event with metadata."""
    event_type: SystemEvent
    source: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(
        default_factory=lambda: datetime.now().timestamp()
    )

    def __repr__(self) -> str:
        return (
            f"Event({self.event_type.value}, "
            f"src={self.source!r}, data={self.data})"
        )


# ── Event Manager ─────────────────────────────────────────────────────────────

class EventManager:
    """
    Async pub/sub event bus.

    Usage:
        em = EventManager()
        em.subscribe(SystemEvent.PRODUCT_DETECTED, my_handler)

        await em.emit(SystemEvent.PRODUCT_DETECTED, source="input_reader",
                      data={"vision_id": 3})

        # Run dispatch loop as background task:
        asyncio.create_task(em.dispatch_loop())
    """

    def __init__(self, queue_maxsize: int = 256) -> None:
        self._queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=queue_maxsize)
        self._handlers: Dict[SystemEvent, List[Callable]] = {}
        self._event_log: List[Event] = []
        self._max_log: int = 500
        self.event_count: int = 0
        self._running: bool = False

    # ── Subscribe ─────────────────────────────────────────────────────────────

    def subscribe(self, event_type: SystemEvent, handler: Callable) -> None:
        """
        Register a handler for an event type.

        Handler can be sync or async:
            async def on_product(event: Event): ...
            def on_product(event: Event): ...

        Args:
            event_type: Event to listen for.
            handler:    Callable accepting one Event argument.
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.debug(
            f"EventManager: {handler.__name__} → {event_type.value}"
        )

    def unsubscribe(self, event_type: SystemEvent, handler: Callable) -> None:
        """Remove a specific handler."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)

    # ── Emit (non-blocking) ───────────────────────────────────────────────────

    def emit(
        self,
        event_type: SystemEvent,
        source: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Put an event on the async queue (non-blocking, thread-safe).

        NOTE: Does NOT call handlers directly. Handlers are called by
        dispatch_loop() in the background.

        Args:
            event_type: Type of event to emit.
            source:     Identifier of emitting component.
            data:       Arbitrary key-value event payload.
        """
        event = Event(event_type=event_type, source=source, data=data or {})
        try:
            self._queue.put_nowait(event)
            self.event_count += 1
        except asyncio.QueueFull:
            logger.error(
                f"EventManager queue FULL — dropping event {event_type.value}"
            )

    async def emit_async(
        self,
        event_type: SystemEvent,
        source: str = "",
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Awaitable emit — blocks until queue has space.

        Use this when you need backpressure guarantee.
        """
        event = Event(event_type=event_type, source=source, data=data or {})
        await self._queue.put(event)
        self.event_count += 1

    # ── Dispatch loop ─────────────────────────────────────────────────────────

    async def dispatch_loop(self) -> None:
        """
        Background coroutine — drains event queue and calls handlers.

        Run as:
            asyncio.create_task(event_manager.dispatch_loop())

        Runs until cancelled.
        """
        self._running = True
        logger.info("EventManager dispatch loop started")
        try:
            while True:
                event = await self._queue.get()
                await self._dispatch(event)
                self._queue.task_done()
        except asyncio.CancelledError:
            logger.info("EventManager dispatch loop stopped")
            self._running = False

    async def _dispatch(self, event: Event) -> None:
        """Call all handlers registered for event.event_type."""
        # Log
        if len(self._event_log) >= self._max_log:
            self._event_log.pop(0)
        self._event_log.append(event)
        logger.debug(f"Dispatching: {event}")

        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as exc:
                logger.error(
                    f"EventManager: handler {handler.__name__} "
                    f"raised for {event.event_type.value}: {exc}"
                )

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def get_event_log(self, limit: int = 100) -> List[Event]:
        """Return recent event log (newest last)."""
        return self._event_log[-limit:]

    def get_queue_depth(self) -> int:
        """Return current queue depth."""
        return self._queue.qsize()

    def get_handler_count(self, event_type: SystemEvent) -> int:
        """Return number of handlers for an event type."""
        return len(self._handlers.get(event_type, []))

    def is_running(self) -> bool:
        return self._running
