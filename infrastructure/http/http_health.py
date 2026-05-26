"""
HttpHealthReporter — implements HealthReporter port via HTTP.

Sends periodic heartbeat telemetry to ThingsBoard.
Replaces MQTT heartbeat with HTTP POST.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from domain.ports.health_reporter import HealthReporter
from infrastructure.http.tb_http_client import TBHttpClient

logger = logging.getLogger(__name__)


class HttpHealthReporter(HealthReporter):
    """
    HTTP-based health reporter for ThingsBoard.

    Publishes system health status at configurable intervals.
    Replaces MQTT LWT with periodic HTTP heartbeat.
    """

    def __init__(
        self,
        http_client: TBHttpClient,
        station_id: str = "",
        get_health_data: Optional[callable] = None,
    ) -> None:
        self._http = http_client
        self._station_id = station_id
        self._get_health_data = get_health_data

        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self._start_time = time.monotonic()

    # ── HealthReporter interface ──────────────────────────────────────────

    async def report_health(self, status: Dict[str, Any]) -> bool:
        """Publish a health status snapshot via HTTP."""
        payload = {
            "heartbeat": True,
            "station_id": self._station_id,
            "uptime_seconds": round(time.monotonic() - self._start_time, 1),
            **status,
        }
        ok = await self._http.post_telemetry(payload)
        if ok:
            logger.debug("Health heartbeat published")
        return ok

    async def start(self, interval_s: float = 30.0) -> None:
        """Start periodic heartbeat loop."""
        self._running = True
        self._start_time = time.monotonic()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(interval_s), name="health_heartbeat"
        )
        logger.info(f"HttpHealthReporter started (interval={interval_s}s)")

        # Publish online status immediately
        await self.report_health({"status": "online"})

    async def stop(self) -> None:
        """Stop heartbeat, publish offline status."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Best-effort offline status
        try:
            await self._http.post_telemetry({
                "status": "offline",
                "station_id": self._station_id,
                "heartbeat": False,
            })
        except Exception:
            pass

        logger.info("HttpHealthReporter stopped")

    # ── Internal ──────────────────────────────────────────────────────────

    async def _heartbeat_loop(self, interval_s: float) -> None:
        """Periodic heartbeat — confirms device alive to TB."""
        try:
            while self._running:
                await asyncio.sleep(interval_s)

                status = {}
                if self._get_health_data:
                    try:
                        status = self._get_health_data()
                    except Exception as exc:
                        logger.error(f"Health data callback error: {exc}")

                await self.report_health(status)

        except asyncio.CancelledError:
            logger.debug("Heartbeat loop cancelled")
