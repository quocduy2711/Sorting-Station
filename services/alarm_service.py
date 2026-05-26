"""
AlarmService — bridges AlarmManager to cloud transport.

Responsibilities:
- Subscribe to ALARM_TRIGGERED event
- Format and publish alarm payload via TelemetryPublisher port
- Log alarms to alarms.log (via WARNING level)
- Track alarm count in SystemState

RULE: Does NOT know HTTP, MQTT, topics, or transport details.
RULE: Uses TelemetryPublisher.publish_alarm() — port abstraction.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from alarms.alarm_manager import AlarmManager, AlarmType
from control.event_manager import Event, SystemEvent

if TYPE_CHECKING:
    from config.runtime_context import ApplicationContext

logger = logging.getLogger(__name__)


class AlarmService:
    """
    Bridges internal alarm events to cloud transport via port.
    """

    def __init__(self, ctx: "ApplicationContext") -> None:
        self._ctx = ctx
        self._alarm_manager: AlarmManager = ctx.alarm_manager

    def register_handlers(self) -> None:
        """Subscribe to alarm events."""
        self._ctx.event_manager.subscribe(
            SystemEvent.ALARM_TRIGGERED, self._on_alarm
        )
        self._ctx.event_manager.subscribe(
            SystemEvent.WATCHDOG_TIMEOUT, self._on_watchdog_timeout
        )
        self._ctx.event_manager.subscribe(
            SystemEvent.MODBUS_DISCONNECTED, self._on_modbus_disconnected
        )
        self._ctx.event_manager.subscribe(
            SystemEvent.MQTT_DISCONNECTED, self._on_mqtt_disconnected
        )
        logger.info("AlarmService handlers registered")

    async def _on_alarm(self, event: Event) -> None:
        """Handle generic ALARM_TRIGGERED event."""
        alarm_type_str: str = event.data.get("alarm_type", "UNKNOWN")
        message: str = event.data.get("message", "")
        severity: str = event.data.get("severity", "WARNING")
        source: str = event.source

        # Resolve AlarmType enum
        try:
            alarm_type = AlarmType(alarm_type_str)
        except ValueError:
            alarm_type = AlarmType.UNKNOWN

        # Register in alarm manager
        alarm = self._alarm_manager.trigger_alarm(
            alarm_type=alarm_type,
            message=message,
            source=source,
        )

        # Update system state alarm counter
        if self._ctx.state.system_state:
            self._ctx.state.system_state.alarm_count += 1

        # Publish via transport port
        await self._publish_alarm(alarm_type_str, message, severity, source)

    async def _on_watchdog_timeout(self, event: Event) -> None:
        """Handle watchdog timeout alarm."""
        check_name = event.data.get("check_name", "unknown")
        message = f"Watchdog timeout: {check_name}"
        logger.critical(message)
        self._alarm_manager.trigger_alarm(
            AlarmType.WATCHDOG_FAILURE, message=message, source="Watchdog"
        )
        await self._publish_alarm("WATCHDOG_FAILURE", message, "CRITICAL", "Watchdog")

        # Mark health monitor
        if self._ctx.state.health_monitor:
            self._ctx.state.health_monitor.set_watchdog_ok(False)
        if self._ctx.state.metrics:
            self._ctx.state.metrics.increment_watchdog_trips()

    async def _on_modbus_disconnected(self, event: Event) -> None:
        """Handle Modbus disconnect alarm."""
        message = "Modbus TCP connection lost — entering degraded mode"
        logger.warning(message)
        self._alarm_manager.trigger_alarm(
            AlarmType.MODBUS_DISCONNECT, message=message, source="ModbusClient"
        )
        if self._ctx.state.system_state:
            self._ctx.state.system_state.modbus_connected = False
        if self._ctx.state.health_monitor:
            self._ctx.state.health_monitor.set_modbus_connected(False)
        if self._ctx.state.metrics:
            self._ctx.state.metrics.increment_modbus_reconnect()
        await self._publish_alarm("MODBUS_DISCONNECT", message, "WARNING", "ModbusClient")

    async def _on_mqtt_disconnected(self, event: Event) -> None:
        """Handle MQTT disconnect (log only — MQTT is RPC-only now)."""
        message = "MQTT RPC connection lost — RPC commands unavailable"
        logger.warning(message)
        if self._ctx.state.health_monitor:
            self._ctx.state.health_monitor.set_mqtt_rpc_available(False)
        if self._ctx.state.metrics:
            self._ctx.state.metrics.increment_mqtt_reconnect()

    async def _publish_alarm(
        self, alarm_type: str, message: str, severity: str, source: str
    ) -> None:
        """Publish alarm via TelemetryPublisher port."""
        telemetry_pub = self._ctx.infrastructure.telemetry
        if not telemetry_pub:
            return

        payload = {
            "alarm_active": True,
            "alarm_type": alarm_type,
            "alarm_message": message,
            "alarm_severity": severity,
            "alarm_source": source,
        }
        await telemetry_pub.publish_alarm(payload)
