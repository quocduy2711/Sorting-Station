"""
RuntimeContext — lightweight dependency injection container.

Holds references to all shared services and components.
Pass this object instead of importing globals.

RULE: Create ONE RuntimeContext per process.
RULE: All services receive the context via __init__.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from config.app_config import AppConfig
    from drivers.modbus_client import ModbusClient
    from drivers.input_reader import InputReader
    from drivers.output_writer import OutputWriter
    from telemetry.mqtt_client import MQTTClient
    from telemetry.publisher import TelemetryPublisher
    from telemetry.metrics import MetricsCollector
    from control.event_manager import EventManager
    from control.state_machine import StateMachine
    from control.product_tracking import ProductTracker
    from control.sorting_logic import SortingLogic
    from control.watchdog import Watchdog
    from control.timers import TimerManager
    from alarms.alarm_manager import AlarmManager
    from alarms.fault_handler import FaultHandler
    from models.system_state import SystemState
    from models.output_state import OutputState
    from utils.runtime_metrics import RuntimeMetrics
    from utils.health_monitor import HealthMonitor


@dataclass
class RuntimeContext:
    """
    Dependency injection container.

    All fields are optional to allow incremental construction
    during the startup sequence.
    """
    # Config (always present)
    config: Optional["AppConfig"] = None

    # Models
    system_state: Optional["SystemState"] = None
    output_state: Optional["OutputState"] = None

    # Drivers
    modbus: Optional["ModbusClient"] = None
    input_reader: Optional["InputReader"] = None
    output_writer: Optional["OutputWriter"] = None

    # Telemetry
    mqtt: Optional["MQTTClient"] = None
    telemetry_publisher: Optional["TelemetryPublisher"] = None
    metrics_collector: Optional["MetricsCollector"] = None

    # Control
    event_manager: Optional["EventManager"] = None
    state_machine: Optional["StateMachine"] = None
    product_tracker: Optional["ProductTracker"] = None
    sorting_logic: Optional["SortingLogic"] = None
    watchdog: Optional["Watchdog"] = None
    timer_manager: Optional["TimerManager"] = None

    # Alarms
    alarm_manager: Optional["AlarmManager"] = None
    fault_handler: Optional["FaultHandler"] = None

    # Monitoring
    runtime_metrics: Optional["RuntimeMetrics"] = None
    health_monitor: Optional["HealthMonitor"] = None

    def validate(self) -> list[str]:
        """
        Validate that all required components are wired.

        Returns:
            List of missing component names (empty = OK).
        """
        required = [
            "config", "system_state", "output_state",
            "modbus", "input_reader", "output_writer",
            "mqtt", "telemetry_publisher", "metrics_collector",
            "event_manager", "state_machine", "product_tracker",
            "sorting_logic", "watchdog", "timer_manager",
            "alarm_manager", "fault_handler",
            "runtime_metrics", "health_monitor",
        ]
        return [name for name in required if getattr(self, name) is None]
