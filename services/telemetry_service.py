"""
TelemetryService — periodic MQTT telemetry publisher.

Responsibilities:
- Run periodic publish loop at TELEMETRY_MS interval
- Build payload from SystemState + RuntimeMetrics + ProductTracker
- Heartbeat the health monitor on each publish
- Subscribe to FSM state changes for immediate attribute publish

RULE: Does NOT own MQTT connection — uses MQTTClient.
RULE: Offline buffering handled by MQTTClient layer.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Optional

from control.event_manager import Event, SystemEvent

if TYPE_CHECKING:
    from config.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)

TELEMETRY_TOPIC = "v1/devices/me/telemetry"
ATTRIBUTES_TOPIC = "v1/devices/me/attributes"


class TelemetryService:
    """
    Runs a periodic coroutine to publish telemetry to ThingsBoard.
    """

    def __init__(self, ctx: "RuntimeContext") -> None:
        self._ctx = ctx
        self._interval_s: float = ctx.config.timing.telemetry_ms / 1000.0
        self._publish_count: int = 0
        self._running: bool = False

    def register_handlers(self) -> None:
        """Subscribe to relevant events."""
        self._ctx.event_manager.subscribe(
            SystemEvent.FSM_STATE_CHANGED, self._on_state_changed
        )
        self._ctx.event_manager.subscribe(
            SystemEvent.MQTT_RECONNECTED, self._on_mqtt_reconnected
        )
        logger.info("TelemetryService handlers registered")

    async def run(self) -> None:
        """
        Main telemetry publish loop.

        Runs indefinitely until cancelled.
        """
        self._running = True
        logger.info(
            f"TelemetryService started — interval={self._interval_s*1000:.0f}ms"
        )
        try:
            while self._running:
                start = time.monotonic()
                await self._publish_telemetry()
                elapsed = time.monotonic() - start

                # Precise sleep: subtract execution time
                sleep_s = max(0.0, self._interval_s - elapsed)
                await asyncio.sleep(sleep_s)
        except asyncio.CancelledError:
            logger.info("TelemetryService stopped")
            self._running = False

    async def _publish_telemetry(self) -> None:
        """Build and publish current telemetry payload."""
        ctx = self._ctx
        mqtt = ctx.mqtt
        system_state = ctx.system_state
        tracker = ctx.product_tracker
        runtime_metrics = ctx.runtime_metrics
        health = ctx.health_monitor

        if not mqtt:
            return

        # Collect metrics snapshot
        metrics = runtime_metrics.snapshot() if runtime_metrics else None

        # Current product info
        product = tracker.get_current_product() if tracker else None

        # Build payload
        payload: dict = {
            "system_state": system_state.state.value if system_state else "UNKNOWN",
            "modbus_connected": system_state.modbus_connected if system_state else False,
            "mqtt_connected": True,  # If we're publishing, we're connected
            "total_products": system_state.total_products if system_state else 0,
            "successful_sorts": system_state.successful_sorts if system_state else 0,
            "failed_sorts": system_state.failed_sorts if system_state else 0,
            "alarm_count": system_state.alarm_count if system_state else 0,
            "uptime_seconds": round(system_state.get_uptime_seconds(), 1) if system_state else 0,
        }

        if product:
            payload.update({
                "current_product_id": product.vision_id,
                "current_product_shape": product.shape.value,
                "current_product_color": product.color.value,
                "current_product_sorter": product.target_sorter,
            })
        else:
            payload.update({
                "current_product_id": 0,
                "current_product_shape": "",
                "current_product_color": "",
                "current_product_sorter": 0,
            })

        if metrics:
            payload.update({
                "scan_cycle_ms": round(metrics.scan_cycle_ms, 2),
                "avg_scan_cycle_ms": round(metrics.avg_scan_cycle_ms, 2),
                "max_scan_cycle_ms": round(metrics.max_scan_cycle_ms, 2),
                "mqtt_reconnect_count": metrics.mqtt_reconnect_count,
                "modbus_reconnect_count": metrics.modbus_reconnect_count,
                "modbus_dropped_reads": metrics.modbus_dropped_reads,
                "watchdog_trips": metrics.watchdog_trips,
                "mqtt_offline_buffer": metrics.mqtt_offline_buffer_size,
            })

        # Publish with latency tracking
        t0 = time.monotonic()
        ok = await mqtt.publish(TELEMETRY_TOPIC, payload)
        latency_ms = (time.monotonic() - t0) * 1000.0

        if ok:
            self._publish_count += 1
            if runtime_metrics:
                runtime_metrics.record_mqtt_latency(latency_ms)
            if health:
                health.heartbeat_telemetry()
            logger.debug(
                f"TelemetryService: published #{self._publish_count} "
                f"(latency={latency_ms:.1f}ms)"
            )
        else:
            logger.debug("TelemetryService: buffered offline (MQTT disconnected)")

    async def _on_state_changed(self, event: Event) -> None:
        """Publish immediate attribute update on FSM state change."""
        ctx = self._ctx
        if ctx.mqtt and ctx.system_state:
            await ctx.mqtt.publish(
                ATTRIBUTES_TOPIC,
                {"system_state": event.data.get("new_state", "")},
            )

    async def _on_mqtt_reconnected(self, event: Event) -> None:
        """Publish device attributes immediately after MQTT reconnect."""
        ctx = self._ctx
        if ctx.mqtt and ctx.system_state:
            await ctx.mqtt.publish(
                ATTRIBUTES_TOPIC,
                {
                    "firmware_version": "2.0.0",
                    "station_id": "sorting_station_01",
                    "system_state": ctx.system_state.state.value,
                },
            )

    def stop(self) -> None:
        self._running = False
