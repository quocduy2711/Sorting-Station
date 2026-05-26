"""
Main entry point for Industrial Control Runtime.

COMPOSITION ROOT — this is the ONLY file that imports infrastructure.
All dependency wiring happens here via ApplicationContext.

Usage:
    python main.py
"""

import asyncio
import logging
import signal
import sys

from config import load_config, ApplicationContext, RuntimeState, InfrastructureContext
from utils import setup_logging_from_config
from utils.runtime_metrics import RuntimeMetrics
from utils.health_monitor import HealthMonitor
from models.system_state import SystemState
from models.output_state import OutputState
from drivers.modbus_client import ModbusClient
from drivers.input_reader import InputReader
from drivers.output_writer import OutputWriter
from control.event_manager import EventManager, SystemEvent
from control.state_machine import StateMachine
from control.product_tracking import ProductTracker
from control.sorting_logic import SortingLogic
from control.watchdog import Watchdog
from control.timers import TimerManager
from control.conveyor_error_detector import ConveyorErrorDetector
from alarms.alarm_manager import AlarmManager
from alarms.fault_handler import FaultHandler
from services.sorting_service import SortingService
from services.telemetry_service import TelemetryService
from services.alarm_service import AlarmService
from services.runtime_service import RuntimeEngine

# ── Infrastructure imports (ONLY in this file) ────────────────────────────
from infrastructure.observability.metrics import PipelineMetrics
from infrastructure.http.tb_http_client import TBHttpClient
from infrastructure.http.http_telemetry import HttpTelemetryPublisher
from infrastructure.http.http_attributes import HttpAttributePublisher
from infrastructure.http.http_health import HttpHealthReporter
from infrastructure.mqtt.tb_mqtt_client import TBMqttClient
from infrastructure.mqtt.mqtt_rpc_listener import MqttRpcListener

logger = logging.getLogger(__name__)


def build_context() -> ApplicationContext:
    """
    Build and wire the dependency injection container.

    COMPOSITION ROOT — all infrastructure wiring happens here.
    This is the ONLY place that knows about concrete implementations.
    """
    # 1. Config & Logging
    cfg = load_config()
    setup_logging_from_config(cfg.logging)

    ctx = ApplicationContext(config=cfg)

    # 2. Runtime State (observable data)
    ctx.state = RuntimeState(
        system_state=SystemState(),
        output_state=OutputState(),
        metrics=RuntimeMetrics(window_size=120),
        pipeline_metrics=PipelineMetrics(latency_window=100),
    )
    ctx.state.health_monitor = HealthMonitor(
        runtime_metrics=ctx.state.metrics,
        scan_interval_ms=cfg.timing.io_scan_ms,
    )

    # 3. Event Bus
    ctx.event_manager = EventManager(queue_maxsize=1024)

    # 4. Modbus Driver
    def on_modbus_reconnect():
        if ctx.event_manager:
            ctx.event_manager.emit(SystemEvent.MODBUS_RECONNECTED, source="Modbus")

    def on_modbus_disconnect():
        if ctx.event_manager:
            ctx.event_manager.emit(SystemEvent.MODBUS_DISCONNECTED, source="Modbus")

    ctx.modbus = ModbusClient(
        modbus_cfg=cfg.modbus,
        reconnect_cfg=cfg.reconnect,
        on_reconnect=on_modbus_reconnect,
        on_disconnect=on_modbus_disconnect,
    )
    ctx.input_reader = InputReader(ctx.modbus)
    ctx.output_writer = OutputWriter(ctx.modbus, ctx.state.output_state)

    # 5. Infrastructure — HTTP Transport (telemetry, attributes, health)
    tb = cfg.thingsboard
    ht = cfg.http_transport
    base_url = f"http://{tb.host}:{tb.http_port}"

    http_client = TBHttpClient(
        base_url=base_url,
        access_token=tb.access_token,
        timeout_s=ht.timeout_s,
        cb_threshold=ht.circuit_breaker_threshold,
        cb_reset_s=ht.circuit_breaker_reset_s,
    )

    ctx.infrastructure = InfrastructureContext(
        telemetry=HttpTelemetryPublisher(
            http_client=http_client,
            metrics=ctx.state.pipeline_metrics,
            spool_db_path=ht.spool_db_path,
            max_queue_size=ht.max_queue_size,
            max_batch_size=ht.max_batch_size,
            batch_window_s=ht.batch_window_s,
            max_spool_size=ht.max_spool_size,
            max_retries=ht.max_retries,
            retry_check_interval_s=ht.retry_check_interval_s,
        ),
        attributes=HttpAttributePublisher(
            http_client=http_client,
            station_id=tb.station_id,
            device_name=tb.device_name,
            shared_poll_interval_s=ht.shared_attr_poll_interval_s,
        ),
        health=HttpHealthReporter(
            http_client=http_client,
            station_id=tb.station_id,
            get_health_data=lambda: _build_health_data(ctx),
        ),
    )

    # 6. Infrastructure — MQTT RPC (isolated from HTTP)
    def on_mqtt_reconnect():
        ctx.event_manager.emit(SystemEvent.MQTT_RECONNECTED, source="MQTT_RPC")

    def on_mqtt_disconnect():
        ctx.event_manager.emit(SystemEvent.MQTT_DISCONNECTED, source="MQTT_RPC")

    mqtt_client = TBMqttClient(
        host=cfg.mqtt.host,
        port=cfg.mqtt.port,
        access_token=cfg.mqtt.access_token or tb.access_token,
        station_id=tb.station_id,
        reconnect_base_s=cfg.reconnect.mqtt_base_s,
        reconnect_max_s=cfg.reconnect.mqtt_max_s,
        ca_certs=cfg.mqtt.ca_certs,
    )

    rpc_listener = MqttRpcListener(
        mqtt_client=mqtt_client,
        metrics=ctx.state.pipeline_metrics,
        on_connect=on_mqtt_reconnect,
        on_disconnect=on_mqtt_disconnect,
    )

    # Register RPC command handlers
    _register_rpc_handlers(rpc_listener, ctx)

    ctx.infrastructure.rpc = rpc_listener

    # 7. Core Control & Logic
    ctx.state_machine = StateMachine(ctx.state.system_state, ctx.state.output_state)
    ctx.product_tracker = ProductTracker(
        system_state=ctx.state.system_state,
        event_manager=ctx.event_manager,
    )
    ctx.sorting_logic = SortingLogic()
    ctx.timer_manager = TimerManager()

    ctx.watchdog = Watchdog(on_failure=lambda name, chk: ctx.event_manager.emit(
        SystemEvent.WATCHDOG_TIMEOUT, source="Watchdog", data={"check_name": name}
    ))
    ctx.watchdog.register("scan_loop", timeout_sec=cfg.timeout.watchdog_scan_timeout_ms / 1000.0)

    # 8. Alarms
    ctx.alarm_manager = AlarmManager()
    ctx.fault_handler = FaultHandler(
        output_state=ctx.state.output_state,
        system_state=ctx.state.system_state,
        output_writer=ctx.output_writer,
        alarm_manager=ctx.alarm_manager,
        http_client=http_client,
    )

    # 8b. Conveyor Error Detector
    from config.constants import (
        CONVEYOR_JAM_TIMEOUT_MS,
        CONVEYOR_VISION_STALL_TIMEOUT_MS,
        CONVEYOR_SUDDEN_STOP_DEBOUNCE_MS,
    )
    ctx.error_detector = ConveyorErrorDetector(
        system_state=ctx.state.system_state,
        event_manager=ctx.event_manager,
        http_client=http_client,
        jam_timeout_ms=CONVEYOR_JAM_TIMEOUT_MS,
        vision_stall_timeout_ms=CONVEYOR_VISION_STALL_TIMEOUT_MS,
        sudden_stop_debounce_ms=CONVEYOR_SUDDEN_STOP_DEBOUNCE_MS,
    )

    # 9. Services (wired with ports, not infrastructure)
    ctx._sorting_service = SortingService(ctx)
    ctx._telemetry_service = TelemetryService(ctx)
    ctx._alarm_service = AlarmService(ctx)

    return ctx


def _register_rpc_handlers(
    rpc_listener: MqttRpcListener, ctx: ApplicationContext
) -> None:
    """Register all RPC command handlers on the listener."""

    def handle_start(request_id: str, params: dict) -> dict:
        ctx.event_manager.emit(
            SystemEvent.START_BUTTON_PRESSED,
            source="RPC",
            data={"request_id": request_id},
        )
        return {"success": True, "message": "Machine start command accepted"}

    def handle_stop(request_id: str, params: dict) -> dict:
        ctx.event_manager.emit(
            SystemEvent.STOP_BUTTON_PRESSED,
            source="RPC",
            data={"request_id": request_id},
        )
        return {"success": True, "message": "Machine stop command accepted"}

    def handle_estop(request_id: str, params: dict) -> dict:
        ctx.event_manager.emit(
            SystemEvent.ESTOP_ACTIVATED,
            source="RPC",
            data={"request_id": request_id},
        )
        return {"success": True, "message": "Emergency stop activated"}

    def handle_ping(request_id: str, params: dict) -> dict:
        return {
            "success": True,
            "message": "pong",
            "station_id": ctx.config.thingsboard.station_id,
            "state": ctx.state.system_state.state.value if ctx.state.system_state else "UNKNOWN",
        }

    def handle_get_stats(request_id: str, params: dict) -> dict:
        stats = {}
        if ctx.infrastructure.telemetry:
            stats["pipeline"] = ctx.infrastructure.telemetry.get_stats()
        if ctx.state.system_state:
            stats["machine"] = {
                "state": ctx.state.system_state.state.value,
                "total_products": ctx.state.system_state.total_products,
                "successful_sorts": ctx.state.system_state.successful_sorts,
            }
        return {"success": True, "data": stats}

    def handle_reset_emergency(request_id: str, params: dict) -> dict:
        if ctx.fault_handler:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(ctx.fault_handler.reset_emergency())
        return {"success": True, "message": "Emergency reset command accepted"}

    rpc_listener.register_command_handler("start_machine", handle_start)
    rpc_listener.register_command_handler("stop_machine", handle_stop)
    rpc_listener.register_command_handler("emergency_stop", handle_estop)
    rpc_listener.register_command_handler("ping", handle_ping)
    rpc_listener.register_command_handler("get_stats", handle_get_stats)
    rpc_listener.register_command_handler("reset_emergency", handle_reset_emergency)


def _build_health_data(ctx: ApplicationContext) -> dict:
    """Build health status payload for heartbeat."""
    status = {}
    ss = ctx.state.system_state
    if ss:
        status["machine_state"] = ss.state.value
        status["modbus_connected"] = ss.modbus_connected
    if ctx.infrastructure.rpc:
        status["rpc_connected"] = ctx.infrastructure.rpc.is_connected()
    if ctx.infrastructure.telemetry:
        stats = ctx.infrastructure.telemetry.get_stats()
        status["pipeline_queue_depth"] = stats.get("queue_depth", 0)
        status["pipeline_published"] = stats.get("total_published", 0)
    return status


class RuntimeController:
    """Controller for runtime lifecycle."""

    def __init__(self):
        """Initialize controller."""
        self.engine: RuntimeEngine = None
        self.shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start the runtime."""
        logger.info("=== Industrial Control Runtime Starting ===")

        ctx = build_context()

        # Verify wiring
        missing = ctx.validate()
        if missing:
            logger.error(f"Missing dependencies in context: {missing}")
            sys.exit(1)

        # Create engine
        self.engine = RuntimeEngine(ctx)

        # Initialize
        if not await self.engine.initialize():
            logger.error("Failed to initialize runtime")
            sys.exit(1)

        # Run main loop
        try:
            await self.engine.run()
        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception as e:
            logger.critical(f"Fatal error: {e}")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Shutdown the runtime."""
        if self.engine:
            await self.engine.shutdown()

        logger.info("=== Runtime Stopped ===")


async def main():
    """Main entry point."""
    controller = RuntimeController()

    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating shutdown")
        # Cancel all tasks
        for task in asyncio.all_tasks():
            task.cancel()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Start runtime
    await controller.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print(f"Unhandled exception: {e}")
        sys.exit(1)
