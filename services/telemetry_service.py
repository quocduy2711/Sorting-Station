"""
TelemetryService — business telemetry builder.

Responsibilities:
- Run periodic build loop at TELEMETRY_MS interval
- Build TelemetryPayload from SystemState + ProductTracker
- Enqueue payload to TelemetryPublisher (NON-BLOCKING)
- Publish attributes on FSM state change

RULE: Does NOT know HTTP, MQTT, QoS, topics, or reconnect logic.
RULE: Only interacts with TelemetryPublisher port (ABC).
RULE: enqueue_nowait() MUST be the ONLY publish method used from the loop.
RULE: NEVER calls await for any transport operation in the build loop.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from control.event_manager import Event, SystemEvent
from models.system_state import SystemStateEnum
from models.telemetry_payload import TelemetryPayload

if TYPE_CHECKING:
    from config.runtime_context import ApplicationContext

logger = logging.getLogger(__name__)


class TelemetryService:
    """
    Builds telemetry payloads and enqueues them non-blocking.

    Pipeline:
        TelemetryService._build_payload() → pure, no I/O
            ↓
        ctx.infrastructure.telemetry.enqueue_nowait(payload) → non-blocking
            ↓
        [TelemetryPipeline handles batching, HTTP upload, retry]
    """

    def __init__(self, ctx: "ApplicationContext") -> None:
        self._ctx = ctx
        self._interval_s: float = ctx.config.timing.telemetry_ms / 1000.0
        self._publish_count: int = 0
        self._running: bool = False

    def register_handlers(self) -> None:
        """Subscribe to relevant events."""
        self._ctx.event_manager.subscribe(
            SystemEvent.FSM_STATE_CHANGED, self._on_state_changed
        )
        logger.info("TelemetryService handlers registered")

    async def run(self) -> None:
        """Main telemetry loop — builds payload and enqueues non-blocking."""
        self._running = True
        logger.info(
            f"TelemetryService started — interval={self._interval_s*1000:.0f}ms"
        )
        try:
            while self._running:
                start = time.monotonic()
                self._build_and_enqueue()  # SYNC — no await!
                elapsed = time.monotonic() - start

                # Precise sleep
                sleep_s = max(0.0, self._interval_s - elapsed)
                await asyncio.sleep(sleep_s)
        except asyncio.CancelledError:
            logger.info("TelemetryService stopped")
            self._running = False

    def _build_and_enqueue(self) -> None:
        """
        Build telemetry payload and enqueue NON-BLOCKING.

        This method is intentionally SYNCHRONOUS.
        It MUST NOT await any I/O or transport operation.
        Total execution time budget: < 1ms.
        """
        ctx = self._ctx
        telemetry_pub = ctx.infrastructure.telemetry

        if not telemetry_pub:
            return

        system_state = ctx.state.system_state
        tracker = ctx.product_tracker
        health = ctx.state.health_monitor

        # Current product info for vision fields
        product = tracker.get_current_product() if tracker else None

        # Vision sensor fields
        vision_id = 0
        vision_shape = "Unknown"
        vision_color = "Unknown"
        vision_ok = True
        if system_state and system_state.last_error and "VISION" in system_state.last_error:
            vision_ok = False

        if product:
            vision_id = product.vision_id if hasattr(product, 'vision_id') else 0
            vision_shape = product.shape.value if hasattr(product, 'shape') else "Unknown"
            vision_color = product.color.value if hasattr(product, 'color') else "Unknown"

        # Determine is_running
        is_running = (
            system_state.state in (
                SystemStateEnum.RUNNING,
                SystemStateEnum.WAITING_PRODUCT,
                SystemStateEnum.WAITING_CLEAR_ZONE,
                SystemStateEnum.READING_ID,
                SystemStateEnum.MOVING_TO_SORTER,
                SystemStateEnum.SORTING,
            )
            if system_state
            else False
        )

        # RPC connection status
        rpc_available = False
        if ctx.infrastructure.rpc:
            rpc_available = ctx.infrastructure.rpc.is_connected()

        # Temperature from serial bridge (if available)
        temperature_c = 0.0
        serial_bridge = getattr(ctx, 'serial_bridge', None)
        if serial_bridge and hasattr(serial_bridge, 'last_temperature'):
            temperature_c = serial_bridge.last_temperature

        # Build typed payload
        payload = TelemetryPayload(
            machine_state=system_state.state.value if system_state else "UNKNOWN",
            is_running=is_running,

            remover1_count=system_state.remover_counts.get(1, 0) if system_state else 0,
            remover2_count=system_state.remover_counts.get(2, 0) if system_state else 0,
            remover3_count=system_state.remover_counts.get(3, 0) if system_state else 0,

            vision_product_id=vision_id,
            vision_product_shape=vision_shape,
            vision_product_color=vision_color,
            vision_ok=vision_ok,

            modbus_connected=system_state.modbus_connected if system_state else False,
            mqtt_rpc_available=rpc_available,

            temperature_c=temperature_c,
            uptime_seconds=system_state.get_uptime_seconds() if system_state else 0.0,

            heartbeat=True,
        )

        # NON-BLOCKING enqueue — returns immediately
        ok = telemetry_pub.enqueue_nowait(payload.to_dict())
        if ok:
            self._publish_count += 1
            if health:
                health.heartbeat_telemetry()

    async def _on_state_changed(self, event: Event) -> None:
        """Publish immediate attribute update on FSM state change."""
        ctx = self._ctx
        attr_pub = ctx.infrastructure.attributes
        if attr_pub and ctx.state.system_state:
            await attr_pub.publish_client_attributes(
                {"system_state": event.data.get("new_state", "")}
            )

    def stop(self) -> None:
        """Stop the telemetry loop."""
        self._running = False
