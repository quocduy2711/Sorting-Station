"""
RuntimeService — core scan cycle orchestration.

Responsibilities:
- Main control loop (scan cycle) running at IO_SCAN_MS
- Coordinates: Read Inputs → Event Bus → FSM → Write Outputs
- Watchdog heartbeat
- Graceful shutdown with ordered teardown
- Infrastructure lifecycle (start/stop transport adapters)

RULE: Infrastructure failures MUST NOT crash the control loop.
RULE: Control loop continues even if all transports are down.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

from control.event_manager import SystemEvent
from models.system_state import SystemStateEnum

if TYPE_CHECKING:
    from config.runtime_context import ApplicationContext

logger = logging.getLogger(__name__)


class RuntimeEngine:
    """
    The main industrial control engine.

    Startup order:
        1. Modbus connect
        2. Infrastructure start (HTTP telemetry, MQTT RPC, attributes, health)
        3. Register event handlers
        4. Start event dispatcher
        5. Start telemetry loop
        6. Enter scan cycle

    Shutdown order (reverse):
        1. Stop FSM (transition to STOPPED)
        2. Flush outputs
        3. Stop telemetry service
        4. Stop infrastructure (HTTP, MQTT, spool)
        5. Disconnect Modbus
    """

    def __init__(self, ctx: "ApplicationContext") -> None:
        self._ctx = ctx
        self._interval_s: float = ctx.config.timing.io_scan_ms / 1000.0
        self._running: bool = False

        # Button edge tracking (Stop và E-Stop là Normally Closed)
        self._last_start = False
        self._last_stop = True
        self._last_estop = True
        self._last_at_exit = False  # at_exit là Normally Open

        # Error detector tracking state
        self._last_position_change_time: float = 0.0   # monotonic
        self._last_vision_read_time: float = 0.0        # monotonic
        self._last_vision_id: int = 0                    # previous vision_id
        self._last_at_exit_state: bool = False            # track position changes

    async def initialize(self) -> bool:
        """Initialize and connect subsystems."""
        logger.info("Initializing RuntimeEngine...")
        ctx = self._ctx

        # 1. Modbus
        if ctx.modbus:
            connected = await ctx.modbus.connect()
            if not connected:
                logger.error("Failed initial Modbus connection. Running in degraded mode.")
            ctx.modbus.ensure_reconnect_loop()

        # 2. Infrastructure — HTTP transport (telemetry, attributes, health)
        infra = ctx.infrastructure

        if infra.telemetry:
            try:
                await infra.telemetry.start()
                logger.info("Infrastructure: telemetry publisher started")
            except Exception as exc:
                logger.error(f"Infrastructure: telemetry start failed: {exc}")

        if infra.attributes:
            try:
                await infra.attributes.start()
                logger.info("Infrastructure: attribute publisher started")
            except Exception as exc:
                logger.error(f"Infrastructure: attributes start failed: {exc}")

        if infra.health:
            try:
                hb_interval = ctx.config.http_transport.heartbeat_interval_s
                await infra.health.start(interval_s=hb_interval)
                logger.info("Infrastructure: health reporter started")
            except Exception as exc:
                logger.error(f"Infrastructure: health start failed: {exc}")

        # 3. Infrastructure — MQTT RPC (isolated from HTTP)
        if infra.rpc:
            try:
                rpc_connected = await infra.rpc.start()
                if rpc_connected:
                    logger.info("Infrastructure: MQTT RPC listener connected")
                else:
                    logger.warning(
                        "Infrastructure: MQTT RPC not connected "
                        "(reconnect loop active)"
                    )
            except Exception as exc:
                logger.error(f"Infrastructure: MQTT RPC start failed: {exc}")

        # 4. Register event handlers
        if ctx.state_machine:
            ctx.state_machine.register_handlers(ctx.event_manager)
        if hasattr(ctx, '_telemetry_service') and ctx._telemetry_service:
            ctx._telemetry_service.register_handlers()
        if hasattr(ctx, '_alarm_service') and ctx._alarm_service:
            ctx._alarm_service.register_handlers()

        # 5. Initialize counter values in Modbus
        if ctx.output_writer and ctx.state.system_state:
            try:
                await ctx.output_writer.write_all_counters(
                    ctx.state.system_state.remover_counts
                )
                logger.info("Initialized remover counters to Modbus")
            except Exception as exc:
                logger.warning(f"Failed to initialize counters: {exc}")

        # 6. Start event dispatcher
        asyncio.create_task(ctx.event_manager.dispatch_loop(), name="event_dispatcher")

        # 7. Start telemetry loop
        if hasattr(ctx, '_telemetry_service') and ctx._telemetry_service:
            asyncio.create_task(ctx._telemetry_service.run(), name="telemetry_loop")

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

                        # Edge trigger for at_exit (NO — phát hiện rising edge)
                        if snapshot.at_exit and not self._last_at_exit:
                            ctx.event_manager.emit(
                                SystemEvent.AT_EXIT_TRIGGERED,
                                source="InputReader",
                                data={},
                            )

                        # Edge trigger cho buttons (Start = NO, Stop/E-Stop = NC)
                        if snapshot.start_button and not self._last_start:
                            ctx.event_manager.emit(SystemEvent.START_BUTTON_PRESSED, source="Hardware")
                        if not snapshot.stop_button and self._last_stop:
                            ctx.event_manager.emit(SystemEvent.STOP_BUTTON_PRESSED, source="Hardware")
                        if not snapshot.estop and self._last_estop:
                            ctx.event_manager.emit(SystemEvent.ESTOP_ACTIVATED, source="Hardware")
                        if snapshot.estop and not self._last_estop:
                            ctx.event_manager.emit(SystemEvent.ESTOP_CLEARED, source="Hardware")

                        self._last_at_exit = snapshot.at_exit
                        self._last_start = snapshot.start_button
                        self._last_stop = snapshot.stop_button
                        self._last_estop = snapshot.estop

                        # ── Error Detection ──────────────────────────
                        await self._run_error_checks(snapshot)

                # 2. Logic (Events are handled by background dispatch loop)
                if ctx.timer_manager:
                    ctx.timer_manager.check_all_timers()

                # 3. Write Outputs
                if ctx.output_writer and not ctx.modbus.is_degraded():
                    await ctx.output_writer.flush()

                # 4. Metrics & Health
                elapsed = time.monotonic() - start_time
                if ctx.state.metrics:
                    ctx.state.metrics.record_scan_cycle(elapsed * 1000.0)
                if ctx.state.health_monitor:
                    ctx.state.health_monitor.heartbeat_scan()
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
        """Gracefully stop and disconnect everything (reverse startup order)."""
        if not self._running:
            return

        logger.info("Shutting down RuntimeEngine...")
        self._running = False
        ctx = self._ctx

        # 1. Failsafe FSM shutdown
        if ctx.state_machine:
            try:
                await ctx.state_machine.transition_to(SystemStateEnum.STOPPED)
            except Exception as e:
                logger.error(f"Error during FSM shutdown: {e}")

        # 2. Flush outputs
        if ctx.output_writer and ctx.modbus and ctx.modbus.is_connected():
            try:
                await ctx.output_writer.flush()
            except Exception as e:
                logger.error(f"Error during output flush on shutdown: {e}")

        # 3. Stop telemetry service
        if hasattr(ctx, '_telemetry_service') and ctx._telemetry_service:
            ctx._telemetry_service.stop()

        # 4. Stop infrastructure (ordered: health → attributes → RPC → telemetry)
        infra = ctx.infrastructure

        if infra.health:
            try:
                await infra.health.stop()
            except Exception as e:
                logger.error(f"Health reporter shutdown error: {e}")

        if infra.attributes:
            try:
                await infra.attributes.stop()
            except Exception as e:
                logger.error(f"Attribute publisher shutdown error: {e}")

        if infra.rpc:
            try:
                await infra.rpc.stop()
            except Exception as e:
                logger.error(f"MQTT RPC shutdown error: {e}")

        if infra.telemetry:
            try:
                await infra.telemetry.stop()
            except Exception as e:
                logger.error(f"Telemetry publisher shutdown error: {e}")

        # 5. Disconnect Modbus
        if ctx.modbus:
            await ctx.modbus.disconnect()

        logger.info("RuntimeEngine shutdown complete")

    # ── Error Detection Helpers ───────────────────────────────────────────

    async def _run_error_checks(self, snapshot) -> None:
        """Run all error detection checks for current scan cycle.

        Called each scan cycle after reading inputs.
        RULE: Each check is independent — one failure doesn't skip others.
        """
        ctx = self._ctx
        detector = ctx.error_detector
        if not detector:
            return

        now = time.monotonic()

        # Track position changes (vision_id changes or at_exit transition = movement)
        position_changed = False
        if snapshot.vision_id != self._last_vision_id:
            position_changed = True
            self._last_vision_id = snapshot.vision_id
            if snapshot.vision_id != 0:
                self._last_vision_read_time = now

        if snapshot.at_exit != self._last_at_exit_state:
            position_changed = True
            self._last_at_exit_state = snapshot.at_exit

        if position_changed:
            self._last_position_change_time = now

        # Initialize tracking on first scan
        if self._last_position_change_time == 0.0:
            self._last_position_change_time = now

        # 1. Sudden stop: conveyor motor OFF while FSM says RUNNING
        #    Motor running state comes from OutputState (software intent)
        motor_running = ctx.state.output_state.entry_conveyor if ctx.state.output_state else False
        try:
            await detector.check_sudden_stop(motor_running=motor_running)
        except Exception as exc:
            logger.error(f"Error in check_sudden_stop: {exc}")

        # 2. Jam detection: product stuck at same position too long
        #    Only check when there's an active product
        if ctx.product_tracker and ctx.product_tracker.has_active_product():
            position_unchanged_ms = (now - self._last_position_change_time) * 1000
            try:
                await detector.check_jam(
                    product_position_unchanged_ms=position_unchanged_ms
                )
            except Exception as exc:
                logger.error(f"Error in check_jam: {exc}")

        # 3. Vision stall: vision read product but no downstream movement
        if self._last_vision_read_time > 0.0 and self._last_vision_id != 0:
            time_since_vision_ms = (now - self._last_vision_read_time) * 1000
            try:
                await detector.check_vision_stall(
                    vision_product_id=self._last_vision_id,
                    time_since_vision_read_ms=time_since_vision_ms,
                    product_moved=snapshot.at_exit,
                )
            except Exception as exc:
                logger.error(f"Error in check_vision_stall: {exc}")


class RuntimeService(RuntimeEngine):
    """Alias for backwards compatibility."""
    pass
