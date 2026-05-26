"""
MqttRpcListener — implements RpcListener port via MQTT.

Owns:
    - TBMqttClient (MQTT connection lifecycle)
    - Command handler registry (method → handler mapping)
    - RPC message parsing and dispatch
    - Response routing back to ThingsBoard

Flow:
    TB dashboard → MQTT → on_rpc_message(topic, payload_str)
                       → parse request_id + method + params
                       → lookup handler in registry
                       → call handler(request_id, params) → response dict
                       → publish_rpc_response(request_id, response)

The handler registry replaces the monolithic dispatch pattern.
Each command is registered individually, making it extensible.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, Optional

from domain.ports.rpc_listener import RpcListener
from infrastructure.mqtt.tb_mqtt_client import TBMqttClient
from infrastructure.observability.metrics import PipelineMetrics

logger = logging.getLogger(__name__)


class MqttRpcListener(RpcListener):
    """
    MQTT-based RPC listener with pluggable command handlers.

    Usage:
        listener = MqttRpcListener(mqtt_client, metrics)
        listener.register_command_handler("start_machine", handle_start)
        listener.register_command_handler("stop_machine", handle_stop)
        listener.register_command_handler("ping", handle_ping)
        await listener.start()
    """

    def __init__(
        self,
        mqtt_client: TBMqttClient,
        metrics: PipelineMetrics,
        on_connect: Optional[Callable[[], None]] = None,
        on_disconnect: Optional[Callable[[], None]] = None,
    ) -> None:
        self._mqtt = mqtt_client
        self._metrics = metrics

        # Handler registry: method_name → callable
        self._handlers: Dict[str, Callable] = {}

        # Wire MQTT message callback
        self._mqtt.set_rpc_message_callback(self._on_rpc_message)

        # Wire connect/disconnect callbacks
        if on_connect:
            self._mqtt.set_on_connect(on_connect)
        if on_disconnect:
            self._mqtt.set_on_disconnect(on_disconnect)

    # ── RpcListener interface ─────────────────────────────────────────────

    async def start(self) -> bool:
        """Connect to MQTT and begin listening for RPC."""
        logger.info(
            f"MqttRpcListener starting with {len(self._handlers)} handlers: "
            f"{list(self._handlers.keys())}"
        )
        connected = await self._mqtt.connect()
        if not connected:
            logger.warning(
                "MQTT RPC: initial connect failed — "
                "reconnect loop will retry in background"
            )
            self._mqtt.ensure_reconnect_loop()
        return connected

    async def stop(self) -> None:
        """Disconnect MQTT."""
        await self._mqtt.disconnect()
        logger.info("MqttRpcListener stopped")

    def register_command_handler(
        self, method: str, handler: Callable[..., Any]
    ) -> None:
        """
        Register a handler for a specific RPC method.

        Handler signature:
            def handler(request_id: str, params: dict) -> dict:
                return {"success": True, "data": ...}

        OR async:
            async def handler(request_id: str, params: dict) -> dict:
                return {"success": True}
        """
        self._handlers[method] = handler
        logger.debug(f"RPC handler registered: {method}")

    async def send_response(
        self, request_id: str, response: Dict[str, Any]
    ) -> bool:
        """Send RPC response for a specific request_id."""
        return await self._mqtt.publish_rpc_response(request_id, response)

    def is_connected(self) -> bool:
        """True if MQTT is connected."""
        connected = self._mqtt.is_connected()
        self._metrics.set_mqtt_rpc_available(connected)
        return connected

    # ── Message handling (sync — called from paho thread) ─────────────────

    def _on_rpc_message(self, topic: str, payload_str: str) -> None:
        """
        Parse incoming RPC message and dispatch to handler.

        Called from paho thread — schedules async work on event loop.
        """
        try:
            request_id = self._parse_request_id(topic)
            data = json.loads(payload_str) if payload_str else {}
            method = data.get("method", "")
            params = data.get("params", {})

            logger.info(
                f"RPC received: method={method!r} "
                f"request_id={request_id} params={params}"
            )

            # Dispatch on event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(
                        self._dispatch(request_id, method, params),
                        name=f"rpc_{method}_{request_id}",
                    )
            except RuntimeError:
                logger.error("No running event loop for RPC dispatch")

        except json.JSONDecodeError as exc:
            logger.error(f"RPC JSON error: {exc} — payload={payload_str!r}")
        except Exception as exc:
            logger.error(f"RPC handler error: {exc}")

    async def _dispatch(
        self, request_id: str, method: str, params: Dict[str, Any]
    ) -> None:
        """Dispatch to registered handler and send response."""
        handler = self._handlers.get(method)

        if handler is None:
            logger.warning(f"RPC: unknown method {method!r}")
            await self.send_response(request_id, {
                "success": False,
                "error": f"unknown_method: {method}",
            })
            return

        try:
            # Call handler (sync or async)
            if asyncio.iscoroutinefunction(handler):
                response = await handler(request_id, params)
            else:
                response = handler(request_id, params)

            # Ensure response is a dict
            if not isinstance(response, dict):
                response = {"success": True, "data": response}

            await self.send_response(request_id, response)

        except Exception as exc:
            logger.error(f"RPC handler '{method}' error: {exc}")
            await self.send_response(request_id, {
                "success": False,
                "error": str(exc),
            })

    @staticmethod
    def _parse_request_id(topic: str) -> str:
        """Extract request ID from: v1/devices/me/rpc/request/<id>"""
        parts = topic.split("/")
        return parts[-1] if parts else "0"
