"""
TBMqttClient — simplified MQTT client for RPC-only operation.

This client is ONLY used for:
    - Subscribe to v1/devices/me/rpc/request/+
    - Publish to v1/devices/me/rpc/response/{id}

NO telemetry, NO attributes, NO heartbeat over MQTT.

Features:
    - Auto-reconnect with exponential backoff + JITTER
    - LWT (Last Will Testament) for offline detection
    - Thread-safe: paho runs in its own thread, bridges to asyncio
    - Isolated from HTTP transport — failure here does NOT affect telemetry
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import socket
import time
from typing import Any, Callable, Dict, Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

# ThingsBoard MQTT topics for RPC
RPC_REQUEST_TOPIC = "v1/devices/me/rpc/request/+"
RPC_RESPONSE_TOPIC = "v1/devices/me/rpc/response/{request_id}"
TELEMETRY_TOPIC = "v1/devices/me/telemetry"


class TBMqttClient:
    """
    Simplified MQTT client for ThingsBoard RPC only.

    Reconnect strategy:
        delay = min(base * 2^attempt, max_delay) * uniform(0.8, 1.2)
        This prevents thundering herd / reconnect storm.
    """

    def __init__(
        self,
        host: str,
        port: int,
        access_token: str,
        station_id: str = "sorting-station-01",
        reconnect_base_s: float = 2.0,
        reconnect_max_s: float = 60.0,
        jitter_range: tuple = (0.8, 1.2),
        ca_certs: str = "",
    ) -> None:
        self._host = host
        self._port = port
        self._token = access_token
        self._station_id = station_id
        self._reconnect_base = reconnect_base_s
        self._reconnect_max = reconnect_max_s
        self._jitter_range = jitter_range
        self._ca_certs = ca_certs

        self._connected: bool = False
        self._reconnect_count: int = 0
        self._last_error: Optional[str] = None

        # Callbacks
        self._on_rpc_message: Optional[Callable[[str, str], None]] = None
        self._on_connect_cb: Optional[Callable[[], None]] = None
        self._on_disconnect_cb: Optional[Callable[[], None]] = None

        self._reconnect_task: Optional[asyncio.Task] = None

        # Build paho client
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            clean_session=True,
        )
        self._client.on_connect = self._paho_on_connect
        self._client.on_disconnect = self._paho_on_disconnect
        self._client.on_message = self._paho_on_message

        # Configure LWT before connect
        self._configure_lwt()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def connect(self) -> bool:
        """Connect to MQTT broker."""
        try:
            # Pre-flight TCP check
            if not self._check_reachable():
                return False

            # TLS
            if self._ca_certs:
                import ssl
                self._client.tls_set(
                    ca_certs=self._ca_certs,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS_CLIENT,
                )

            # Auth: ThingsBoard uses access_token as username
            self._client.username_pw_set(self._token)

            self._client.connect(self._host, self._port, keepalive=60)
            self._client.loop_start()

            # Wait for on_connect callback (max 5s)
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                if self._connected:
                    return True
                await asyncio.sleep(0.05)

            if not self._connected:
                logger.warning(
                    f"MQTT connect timeout: {self._host}:{self._port}"
                )
            return self._connected

        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"MQTT connect error: {exc}")
            return False

    async def disconnect(self) -> None:
        """Graceful disconnect — cancel reconnect loop, stop paho."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        try:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            logger.info("MQTT RPC disconnected")
        except Exception as exc:
            logger.error(f"MQTT disconnect error: {exc}")

    # ── Reconnect with jitter ─────────────────────────────────────────────

    def ensure_reconnect_loop(self) -> None:
        """Start reconnect loop if not already running."""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(
                self._reconnect_loop(), name="mqtt_rpc_reconnect"
            )

    async def _reconnect_loop(self) -> None:
        """
        Background reconnect with exponential backoff + jitter.

        Jitter prevents thundering herd when multiple devices
        reconnect simultaneously after broker restart.
        """
        attempt = 0
        while True:
            # Calculate delay with jitter
            base_delay = min(
                self._reconnect_base * (2 ** attempt),
                self._reconnect_max,
            )
            jitter = random.uniform(*self._jitter_range)
            delay = base_delay * jitter

            logger.info(
                f"MQTT RPC reconnect in {delay:.1f}s "
                f"(attempt #{attempt + 1}, base={base_delay:.1f}s)"
            )
            await asyncio.sleep(delay)

            success = await self.connect()
            if success:
                self._reconnect_count += 1
                logger.info(
                    f"MQTT RPC reconnected (#{self._reconnect_count})"
                )
                if self._on_connect_cb:
                    try:
                        self._on_connect_cb()
                    except Exception as exc:
                        logger.error(f"Reconnect callback error: {exc}")
                return

            attempt += 1
            logger.warning(f"MQTT RPC reconnect failed — attempt #{attempt}")

    # ── Publish ───────────────────────────────────────────────────────────

    async def publish_rpc_response(
        self, request_id: str, response: Dict[str, Any]
    ) -> bool:
        """Publish RPC response to ThingsBoard."""
        if not self._connected:
            logger.warning("MQTT RPC: cannot send response — disconnected")
            return False

        topic = RPC_RESPONSE_TOPIC.format(request_id=request_id)
        try:
            payload = json.dumps(response)
            result = self._client.publish(topic, payload, qos=1)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.error(
                    f"MQTT RPC response publish failed: "
                    f"{mqtt.error_string(result.rc)}"
                )
                return False
            return True
        except Exception as exc:
            logger.error(f"MQTT RPC response error: {exc}")
            return False

    # ── Subscription ──────────────────────────────────────────────────────

    def _subscribe_rpc(self) -> None:
        """Subscribe to RPC request topic. Called after connect."""
        try:
            result = self._client.subscribe(RPC_REQUEST_TOPIC, qos=1)
            if result[0] == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"MQTT RPC subscribed: {RPC_REQUEST_TOPIC}")
            else:
                logger.error(f"MQTT RPC subscribe failed: {RPC_REQUEST_TOPIC}")
        except Exception as exc:
            logger.error(f"MQTT RPC subscribe error: {exc}")

    # ── Configuration ─────────────────────────────────────────────────────

    def set_rpc_message_callback(
        self, callback: Callable[[str, str], None]
    ) -> None:
        """Set callback for incoming RPC messages."""
        self._on_rpc_message = callback

    def set_on_connect(self, callback: Callable[[], None]) -> None:
        self._on_connect_cb = callback

    def set_on_disconnect(self, callback: Callable[[], None]) -> None:
        self._on_disconnect_cb = callback

    # ── Paho callbacks (sync — called from paho thread) ───────────────────

    def _paho_on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            logger.info(f"MQTT RPC connected: {self._host}:{self._port}")
            self._connected = True
            self._subscribe_rpc()
        else:
            logger.error(
                f"MQTT RPC connect failed (rc={rc}): "
                f"{mqtt.connack_string(rc)}"
            )
            self._connected = False
            self._last_error = mqtt.connack_string(rc)

    def _paho_on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False
        if rc != 0:
            logger.warning(f"MQTT RPC unexpected disconnect (rc={rc})")
            if self._on_disconnect_cb:
                try:
                    self._on_disconnect_cb()
                except Exception:
                    pass
            # Auto-reconnect
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(self.ensure_reconnect_loop)
            except RuntimeError:
                pass

    def _paho_on_message(self, client, userdata, msg) -> None:
        """Route incoming RPC messages to the registered callback."""
        if self._on_rpc_message and "rpc/request" in msg.topic:
            try:
                payload = msg.payload.decode("utf-8")
                self._on_rpc_message(msg.topic, payload)
            except Exception as exc:
                logger.error(f"MQTT RPC message callback error: {exc}")

    # ── LWT ───────────────────────────────────────────────────────────────

    def _configure_lwt(self) -> None:
        """Configure Last Will Testament for offline detection."""
        lwt_payload = json.dumps({
            "status": "offline",
            "station_id": self._station_id,
            "rpc_connected": False,
        })
        self._client.will_set(
            topic=TELEMETRY_TOPIC,
            payload=lwt_payload,
            qos=1,
            retain=False,
        )

    # ── Helpers ───────────────────────────────────────────────────────────

    def _check_reachable(self, timeout: float = 3.0) -> bool:
        """Pre-flight TCP check."""
        try:
            with socket.create_connection(
                (self._host, self._port), timeout=timeout
            ):
                return True
        except (ConnectionRefusedError, OSError) as exc:
            logger.error(
                f"MQTT broker {self._host}:{self._port} unreachable: {exc}"
            )
            return False

    # ── Status ────────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self._connected

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error
