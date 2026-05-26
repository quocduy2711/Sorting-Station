"""
HttpAttributePublisher — implements AttributePublisher port via HTTP.

Low-frequency, high-reliability operations:
    - POST /api/v1/{token}/attributes   → client attributes
    - GET  /api/v1/{token}/attributes   → shared attributes
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, List, Optional

from domain.ports.attribute_publisher import AttributePublisher
from infrastructure.http.tb_http_client import TBHttpClient

logger = logging.getLogger(__name__)


class HttpAttributePublisher(AttributePublisher):
    """
    HTTP-based attribute publisher for ThingsBoard.

    Client attributes: published on connect and FSM state change.
    Shared attributes: requested on connect, polled periodically.
    """

    def __init__(
        self,
        http_client: TBHttpClient,
        station_id: str = "",
        device_name: str = "",
        firmware_version: str = "2.0.0",
        shared_poll_interval_s: float = 60.0,
    ) -> None:
        self._http = http_client
        self._station_id = station_id
        self._device_name = device_name
        self._firmware = firmware_version
        self._poll_interval_s = shared_poll_interval_s

        self._shared_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._shared_keys: List[str] = []
        self._running = False

    # ── AttributePublisher interface ──────────────────────────────────────

    async def publish_client_attributes(self, attrs: Dict[str, Any]) -> bool:
        """Publish client attributes via HTTP POST."""
        # Merge default device info
        payload = {
            "station_id": self._station_id,
            "device_name": self._device_name,
            "firmware_version": self._firmware,
            **attrs,
        }
        ok = await self._http.post_attributes(payload)
        if ok:
            logger.info(f"Client attributes published: {list(payload.keys())}")
        else:
            logger.warning("Client attributes publish failed")
        return ok

    async def request_shared_attributes(self, keys: List[str]) -> None:
        """Request shared attributes via HTTP GET."""
        self._shared_keys = keys
        keys_str = ",".join(keys)
        result = await self._http.get_attributes(keys_str)
        if result and self._shared_callback:
            shared = result.get("shared", result)
            self._shared_callback(shared)
            logger.info(f"Shared attributes received: {list(shared.keys())}")

    def set_shared_attribute_callback(
        self, callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Register callback for shared attribute updates."""
        self._shared_callback = callback

    async def start(self) -> bool:
        """Start periodic shared attribute polling."""
        self._running = True

        # Publish initial client attributes
        await self.publish_client_attributes({})

        # Start polling loop for shared attributes
        if self._shared_keys:
            self._poll_task = asyncio.create_task(
                self._poll_loop(), name="attr_poll"
            )

        return True

    async def stop(self) -> None:
        """Stop polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

    # ── Internal ──────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        """Periodically poll shared attributes."""
        try:
            while self._running:
                await asyncio.sleep(self._poll_interval_s)
                if self._shared_keys:
                    await self.request_shared_attributes(self._shared_keys)
        except asyncio.CancelledError:
            pass
