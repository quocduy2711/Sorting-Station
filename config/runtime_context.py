"""
Application Context — structured dependency injection replacing God Object.

Split into three focused contexts:
    RuntimeState          — observable runtime data (system state, metrics)
    InfrastructureContext — transport adapters (ports implementations)
    ApplicationContext    — top-level container for all components

Access patterns:
    ctx.infrastructure.telemetry.enqueue_nowait(payload)
    ctx.state.system_state.modbus_connected
    ctx.state.metrics.record_scan_cycle(...)

RULE: Create ONE ApplicationContext per process.
RULE: All services receive the context via __init__.
RULE: services/ MUST NOT import from infrastructure/ directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from config.app_config import AppConfig
    from drivers.modbus_client import ModbusClient
    from drivers.input_reader import InputReader
    from drivers.output_writer import OutputWriter
    from control.event_manager import EventManager
    from control.state_machine import StateMachine
    from control.product_tracking import ProductTracker
    from control.sorting_logic import SortingLogic
    from control.watchdog import Watchdog
    from control.timers import TimerManager
    from alarms.alarm_manager import AlarmManager
    from alarms.fault_handler import FaultHandler
    from control.conveyor_error_detector import ConveyorErrorDetector
    from models.system_state import SystemState
    from models.output_state import OutputState
    from utils.runtime_metrics import RuntimeMetrics
    from utils.health_monitor import HealthMonitor
    from domain.ports.telemetry_publisher import TelemetryPublisher
    from domain.ports.rpc_listener import RpcListener
    from domain.ports.attribute_publisher import AttributePublisher
    from domain.ports.health_reporter import HealthReporter
    from infrastructure.observability.metrics import PipelineMetrics
    from drivers.serial_bridge import SerialBridge


@dataclass
class RuntimeState:
    """
    Observable runtime data — shared across all layers.

    Contains state objects and metrics. No transport, no business logic.
    """
    system_state: Optional["SystemState"] = None
    output_state: Optional["OutputState"] = None
    metrics: Optional["RuntimeMetrics"] = None
    health_monitor: Optional["HealthMonitor"] = None
    pipeline_metrics: Optional["PipelineMetrics"] = None


@dataclass
class InfrastructureContext:
    """
    Transport adapters — concrete implementations of domain ports.

    Access: ctx.infrastructure.telemetry / ctx.infrastructure.rpc
    Wired ONLY in main.py (composition root).
    """
    telemetry: Optional["TelemetryPublisher"] = None
    rpc: Optional["RpcListener"] = None
    attributes: Optional["AttributePublisher"] = None
    health: Optional["HealthReporter"] = None


@dataclass
class ApplicationContext:
    """
    Top-level dependency injection container.

    Replaces the old RuntimeContext (God Object) with structured access.

    Sections:
        config          — frozen AppConfig
        state           — RuntimeState (system state, metrics)
        infrastructure  — InfrastructureContext (transport ports)
        event_manager   — async event bus
        [control]       — FSM, product tracking, sorting logic
        [drivers]       — Modbus client, I/O reader/writer
        [alarms]        — alarm manager, fault handler
        [services]      — sorting, telemetry, alarm services (set after creation)
    """
    # Config (always present)
    config: Optional["AppConfig"] = None

    # Structured sub-contexts
    state: RuntimeState = field(default_factory=RuntimeState)
    infrastructure: InfrastructureContext = field(
        default_factory=InfrastructureContext
    )

    # Event Bus
    event_manager: Optional["EventManager"] = None

    # Drivers
    modbus: Optional["ModbusClient"] = None
    input_reader: Optional["InputReader"] = None
    output_writer: Optional["OutputWriter"] = None

    # Control
    state_machine: Optional["StateMachine"] = None
    product_tracker: Optional["ProductTracker"] = None
    sorting_logic: Optional["SortingLogic"] = None
    watchdog: Optional["Watchdog"] = None
    timer_manager: Optional["TimerManager"] = None

    # Alarms
    alarm_manager: Optional["AlarmManager"] = None
    fault_handler: Optional["FaultHandler"] = None

    # Error detection
    error_detector: Optional["ConveyorErrorDetector"] = None

    # Serial bridge (ESP32 gateway, Optional)
    serial_bridge: Optional["SerialBridge"] = None

    # ── Convenience accessors (backwards-compat during migration) ─────────

    @property
    def system_state(self) -> Optional["SystemState"]:
        return self.state.system_state

    @property
    def output_state(self) -> Optional["OutputState"]:
        return self.state.output_state

    @property
    def runtime_metrics(self) -> Optional["RuntimeMetrics"]:
        return self.state.metrics

    @property
    def health_monitor(self) -> Optional["HealthMonitor"]:
        return self.state.health_monitor

    # ── Validation ────────────────────────────────────────────────────────

    def validate(self) -> list[str]:
        """
        Validate that all required components are wired.

        Returns:
            List of missing component names (empty = OK).
        """
        missing = []

        if self.config is None:
            missing.append("config")

        # State
        if self.state.system_state is None:
            missing.append("state.system_state")
        if self.state.output_state is None:
            missing.append("state.output_state")

        # Infrastructure (at least telemetry must be wired)
        if self.infrastructure.telemetry is None:
            missing.append("infrastructure.telemetry")

        # Core
        required_attrs = [
            "event_manager", "modbus", "input_reader", "output_writer",
            "state_machine", "product_tracker", "sorting_logic",
            "watchdog", "timer_manager",
            "alarm_manager", "fault_handler",
        ]
        for attr in required_attrs:
            if getattr(self, attr) is None:
                missing.append(attr)

        # Monitoring
        if self.state.metrics is None:
            missing.append("state.metrics")
        if self.state.health_monitor is None:
            missing.append("state.health_monitor")

        return missing


# ── Backwards compatibility alias ─────────────────────────────────────────
# Old code uses `RuntimeContext` — this alias allows incremental migration.
RuntimeContext = ApplicationContext
