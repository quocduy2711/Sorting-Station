"""
Main entry point for Industrial Control Runtime.

Usage:
    python main.py
"""

import asyncio
import logging
import signal
import sys

from config import load_config, RuntimeContext
from utils import setup_logging_from_config
from utils.runtime_metrics import RuntimeMetrics
from utils.health_monitor import HealthMonitor
from models.system_state import SystemState
from models.output_state import OutputState
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
from services.sorting_service import SortingService
from services.telemetry_service import TelemetryService
from services.alarm_service import AlarmService
from services.runtime_service import RuntimeEngine

logger = logging.getLogger(__name__)


def build_context() -> RuntimeContext:
    """Build and wire the dependency injection container."""
    # 1. Config & Logging
    cfg = load_config()
    setup_logging_from_config(cfg.logging)
    
    ctx = RuntimeContext(config=cfg)

    # 2. Models
    ctx.system_state = SystemState()
    ctx.output_state = OutputState()

    # 3. Utilities & Monitoring
    ctx.runtime_metrics = RuntimeMetrics(window_size=120)
    ctx.health_monitor = HealthMonitor(
        runtime_metrics=ctx.runtime_metrics,
        scan_interval_ms=cfg.timing.io_scan_ms
    )

    # 4. Event Bus
    ctx.event_manager = EventManager(queue_maxsize=1024)

    # 5. Modbus Driver
    def on_modbus_reconnect():
        if ctx.event_manager:
            ctx.event_manager.emit(SystemEvent.MODBUS_RECONNECTED, source="Modbus")
            
    def on_modbus_disconnect():
        if ctx.event_manager:
            ctx.event_manager.emit(SystemEvent.MODBUS_DISCONNECTED, source="Modbus")

    from control.event_manager import SystemEvent
    ctx.modbus = ModbusClient(
        modbus_cfg=cfg.modbus,
        reconnect_cfg=cfg.reconnect,
        on_reconnect=on_modbus_reconnect,
        on_disconnect=on_modbus_disconnect
    )
    ctx.input_reader = InputReader(ctx.modbus)
    ctx.output_writer = OutputWriter(ctx.modbus, ctx.output_state)

    # 6. MQTT Telemetry Driver
    def on_mqtt_reconnect():
        if ctx.event_manager:
            ctx.event_manager.emit(SystemEvent.MQTT_RECONNECTED, source="MQTT")
            
    def on_mqtt_disconnect():
        if ctx.event_manager:
            ctx.event_manager.emit(SystemEvent.MQTT_DISCONNECTED, source="MQTT")

    ctx.mqtt = MQTTClient(
        mqtt_cfg=cfg.mqtt,
        reconnect_cfg=cfg.reconnect,
        on_reconnect=on_mqtt_reconnect,
        on_disconnect=on_mqtt_disconnect
    )
    ctx.metrics_collector = MetricsCollector(history_size=60)
    ctx.telemetry_publisher = TelemetryPublisher(ctx.mqtt, ctx.metrics_collector)

    # 7. Core Control & Logic
    ctx.state_machine = StateMachine(ctx.system_state, ctx.output_state)
    ctx.product_tracker = ProductTracker()
    ctx.sorting_logic = SortingLogic()
    ctx.timer_manager = TimerManager()
    
    ctx.watchdog = Watchdog(on_failure=lambda name, chk: ctx.event_manager.emit(
        SystemEvent.WATCHDOG_TIMEOUT, source="Watchdog", data={"check_name": name}
    ))
    ctx.watchdog.register("scan_loop", timeout_sec=cfg.timeout.watchdog_scan_timeout_ms / 1000.0)

    # 8. Alarms
    ctx.alarm_manager = AlarmManager()
    ctx.fault_handler = FaultHandler(
        output_state=ctx.output_state,
        system_state=ctx.system_state,
        output_writer=ctx.output_writer,
        alarm_manager=ctx.alarm_manager
    )

    # 9. Services (Wiring)
    ctx.sorting_service = SortingService(ctx)
    ctx.telemetry_service = TelemetryService(ctx)
    ctx.alarm_service = AlarmService(ctx)
    
    return ctx


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
