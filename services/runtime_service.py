"""
RuntimeService — core scan cycle orchestration.

Responsibilities:
- Main control loop (scan cycle) running at IO_SCAN_MS
- Coordinates: Read Inputs → Event Bus → FSM → Write Outputs
- Watchdog heartbeat
- Graceful shutdown
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

from control.event_manager import SystemEvent
from models.system_state import SystemStateEnum

if TYPE_CHECKING:
    from config.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


class RuntimeEngine:
    """
    The main industrial control engine.
    """

    def __init__(self, ctx: "RuntimeContext") -> None:
        self._ctx = ctx
        self._interval_s: float = ctx.config.timing.io_scan_ms / 1000.0
        self._running: bool = False
        
        # Button edge tracking (Stop and E-Stop are Normally Closed, so initial state is True)
        self._last_start = False
        self._last_stop = True
        self._last_estop = True

    async def initialize(self) -> bool:
        """Initialize and connect subsystems."""
        logger.info("Initializing RuntimeEngine...")
        ctx = self._ctx

        # Modbus
        if ctx.modbus:
            connected = await ctx.modbus.connect()
            if not connected:
                logger.error("Failed initial Modbus connection. Running in degraded mode.")
                # We don't fail initialize() completely, Modbus reconnect loop handles it.
            
            # Start reconnect loop just in case
            ctx.modbus.ensure_reconnect_loop()

        # MQTT
        if ctx.mqtt:
            mqtt_connected = await ctx.mqtt.connect()
            if not mqtt_connected:
                logger.error("Failed initial MQTT connection. Running with offline buffering.")
            
            ctx.mqtt.ensure_reconnect_loop()

        # Register event handlers
        if ctx.state_machine:
            ctx.state_machine.register_handlers(ctx.event_manager)
        if ctx.sorting_service:
            ctx.sorting_service.register_handlers()
        if ctx.telemetry_service:
            ctx.telemetry_service.register_handlers()
        if ctx.alarm_service:
            ctx.alarm_service.register_handlers()

        # Start event dispatcher
        asyncio.create_task(ctx.event_manager.dispatch_loop(), name="event_dispatcher")

        # Start telemetry loop
        if ctx.telemetry_service:
            asyncio.create_task(ctx.telemetry_service.run(), name="telemetry_loop")

        return True

    async def run(self) -> None:
        """
        Main industrial scan cycle loop.
        Runs until cancelled or stopped.
        """
        self._running = True
        logger.info(f"RuntimeEngine scan loop started (interval={self._interval_s*1000:.0f}ms)")
        ctx = self._ctx

        try:
            while self._running:
                start_time = time.monotonic()

                # 1. Read Inputs
                if ctx.input_reader and not ctx.modbus.is_degraded():
                    snapshot = await ctx.input_reader.read_all_inputs()
                    if snapshot:
                        # Edge trigger for vision sensor
                        if ctx.input_reader.get_vision_edge_triggered(snapshot):
                            ctx.event_manager.emit(
                                SystemEvent.PRODUCT_DETECTED,
                                source="InputReader",
                                data={"vision_id": snapshot.vision_id}
                            )
                            
                        # Edge trigger for buttons (Start is NO, Stop and E-Stop are NC)
                        if snapshot.start_button and not self._last_start:
                            ctx.event_manager.emit(SystemEvent.START_BUTTON_PRESSED, source="Hardware")
                        if not snapshot.stop_button and self._last_stop:
                            ctx.event_manager.emit(SystemEvent.STOP_BUTTON_PRESSED, source="Hardware")
                        if not snapshot.estop and self._last_estop:
                            ctx.event_manager.emit(SystemEvent.ESTOP_ACTIVATED, source="Hardware")
                        if snapshot.estop and not self._last_estop:
                            ctx.event_manager.emit(SystemEvent.ESTOP_CLEARED, source="Hardware")
                            
                        self._last_start = snapshot.start_button
                        self._last_stop = snapshot.stop_button
                        self._last_estop = snapshot.estop
                
                # 2. Logic (Events are handled by background dispatch loop)
                # But we can tick timers or FSM if needed here
                if ctx.timer_manager:
                    ctx.timer_manager.check_all_timers()

                # 3. Write Outputs
                if ctx.output_writer and not ctx.modbus.is_degraded():
                    await ctx.output_writer.flush()

                # 4. Metrics & Health
                elapsed = time.monotonic() - start_time
                if ctx.runtime_metrics:
                    ctx.runtime_metrics.record_scan_cycle(elapsed * 1000.0)
                if ctx.health_monitor:
                    ctx.health_monitor.heartbeat_scan()
                if ctx.watchdog:
                    ctx.watchdog.heartbeat("scan_loop")

                # Precise Sleep
                sleep_s = max(0.0, self._interval_s - elapsed)
                await asyncio.sleep(sleep_s)

        except asyncio.CancelledError:
            logger.info("RuntimeEngine scan loop cancelled")
        finally:
            self._running = False
            await self.shutdown()

    async def shutdown(self) -> None:
        """Gracefully stop and disconnect everything."""
        if not self._running:
            return
            
        logger.info("Shutting down RuntimeEngine...")
        self._running = False
        ctx = self._ctx

        # Try to failsafe shutdown FSM and outputs
        if ctx.state_machine:
            try:
                await ctx.state_machine.transition_to(SystemStateEnum.STOPPED)
            except Exception as e:
                logger.error(f"Error during FSM shutdown: {e}")

        if ctx.output_writer and ctx.modbus and ctx.modbus.is_connected():
            try:
                await ctx.output_writer.flush()
            except Exception as e:
                logger.error(f"Error during output flush on shutdown: {e}")

        # Stop telemetry
        if ctx.telemetry_service:
            ctx.telemetry_service.stop()

        # Disconnect drivers
        if ctx.mqtt:
            await ctx.mqtt.disconnect()
        if ctx.modbus:
            await ctx.modbus.disconnect()

        logger.info("RuntimeEngine shutdown complete")

class RuntimeService(RuntimeEngine):
    """Alias for backwards compatibility if needed, or structured access."""
    pass
