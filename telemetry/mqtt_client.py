"""
MQTT client for ThingsBoard communication.

Features:
- Exponential backoff reconnect
- Offline message buffer (in-memory deque, max configurable)
- Flush offline buffer on reconnect
- Reconnect counter for runtime metrics
- Callbacks for connect/disconnect events (for event bus)
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional, Tuple

import paho.mqtt.client as mqtt

from config.app_config import MQTTConfig, ReconnectConfig

logger = logging.getLogger(__name__)

# Offline message: (topic, payload_dict, qos)
_OfflineMsg = Tuple[str, Dict[str, Any], int]


class MQTTClient:
    """
    Async-compatible MQTT client with auto-reconnect and offline buffering.

    RULE: publish() never raises — silently buffers when disconnected.
    RULE: Reconnect loop runs as a background asyncio Task.
    """

    def __init__(
        self,
        mqtt_cfg: MQTTConfig,
        reconnect_cfg: ReconnectConfig,
        on_reconnect: Optional[Callable] = None,
        on_disconnect: Optional[Callable] = None,
    ) -> None:
        self._cfg = mqtt_cfg
        self._rcfg = reconnect_cfg

        self._connected: bool = False
        self._last_error: Optional[str] = None
        self._reconnect_count: int = 0

        # Offline buffer
        self._offline_buffer: Deque[_OfflineMsg] = deque(
            maxlen=reconnect_cfg.mqtt_offline_buffer_size
        )

        # External callbacks (for event bus integration)
        self._on_reconnect: Optional[Callable] = on_reconnect
        self._on_disconnect: Optional[Callable] = on_disconnect

        # User-provided message callback
        self._on_message_cb: Optional[Callable] = None

        self._reconnect_task: Optional[asyncio.Task] = None

        # Build paho client
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION1,
            clean_session=mqtt_cfg.clean_session,
        )
        self._client.on_connect = self._paho_on_connect
        self._client.on_disconnect = self._paho_on_disconnect
        self._client.on_message = self._paho_on_message

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(self) -> bool:
        """
        Connect to MQTT broker.

        Returns:
            True if connection initiated successfully.
        """
        try:
            if self._cfg.ca_certs:
                import ssl
                self._client.tls_set(
                    ca_certs=self._cfg.ca_certs,
                    cert_reqs=ssl.CERT_REQUIRED,
                    tls_version=ssl.PROTOCOL_TLS_CLIENT,
                )

            # ThingsBoard: access_token as username, empty password
            token = self._cfg.access_token or self._cfg.username
            password = self._cfg.password if self._cfg.password else None
            self._client.username_pw_set(token, password=password)

            self._client.connect(
                self._cfg.host, self._cfg.port, keepalive=60
            )
            self._client.loop_start()

            # Wait briefly for on_connect callback
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                if self._connected:
                    return True
                await asyncio.sleep(0.05)

            if not self._connected:
                logger.warning(
                    f"MQTT connect timeout to {self._cfg.host}:{self._cfg.port}"
                )
            return self._connected

        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"MQTT connect error: {exc}")
            return False

    async def disconnect(self) -> None:
        """Gracefully disconnect and stop reconnect loop."""
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
            logger.info("MQTT disconnected")
        except Exception as exc:
            logger.error(f"MQTT disconnect error: {exc}")

    # ── Reconnect loop ────────────────────────────────────────────────────────

    async def start_reconnect_loop(self) -> None:
        """
        Background task: reconnect with exponential backoff.
        Flushes offline buffer after successful reconnect.
        """
        delay = self._rcfg.mqtt_base_s
        while True:
            await asyncio.sleep(delay)
            logger.info(f"MQTT reconnect attempt #{self._reconnect_count + 1} …")

            success = await self.connect()
            if success:
                self._reconnect_count += 1
                logger.info(f"MQTT reconnected (#{self._reconnect_count})")

                if self._on_reconnect:
                    await self._safe_call(self._on_reconnect)

                # Flush offline buffer
                await self._flush_offline_buffer()
                return  # Exit reconnect loop

            delay = min(delay * 2.0, self._rcfg.mqtt_max_s)
            logger.warning(f"MQTT reconnect failed — retry in {delay:.1f}s")

    def ensure_reconnect_loop(self) -> None:
        """Start reconnect loop if not already running (idempotent)."""
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(
                self.start_reconnect_loop(),
                name="mqtt_reconnect",
            )

    async def _flush_offline_buffer(self) -> None:
        """Publish all buffered offline messages after reconnect."""
        flushed = 0
        failed = 0
        while self._offline_buffer:
            topic, payload, qos = self._offline_buffer.popleft()
            ok = await self._do_publish(topic, payload, qos)
            if ok:
                flushed += 1
            else:
                failed += 1
                break  # Re-buffer remaining on failure

        if flushed:
            logger.info(f"MQTT offline buffer flushed: {flushed} messages")
        if failed:
            logger.warning(f"MQTT buffer flush failed: {failed} messages lost")

    # ── Publish ───────────────────────────────────────────────────────────────

    async def publish(
        self, topic: str, payload: Dict[str, Any], qos: int = 1
    ) -> bool:
        """
        Publish a message. Buffers offline if not connected.

        Args:
            topic:   MQTT topic string
            payload: Dict to serialize as JSON
            qos:     MQTT QoS level (default 1)

        Returns:
            True if published immediately, False if buffered or failed.
        """
        if not self._connected:
            self._offline_buffer.append((topic, payload, qos))
            logger.debug(
                f"MQTT offline — buffered ({len(self._offline_buffer)} queued)"
            )
            return False

        return await self._do_publish(topic, payload, qos)

    async def _do_publish(
        self, topic: str, payload: Dict[str, Any], qos: int
    ) -> bool:
        """Execute actual MQTT publish."""
        try:
            message = json.dumps(payload)
            result = self._client.publish(topic, message, qos=qos)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                self._last_error = f"Publish failed: {mqtt.error_string(result.rc)}"
                logger.error(self._last_error)
                return False
            return True
        except Exception as exc:
            self._last_error = str(exc)
            logger.error(f"MQTT publish error: {exc}")
            return False

    # ── Subscribe ─────────────────────────────────────────────────────────────

    async def subscribe(self, topic: str, qos: int = 1) -> bool:
        """Subscribe to an MQTT topic."""
        if not self._connected:
            return False
        try:
            result = self._client.subscribe(topic, qos=qos)
            success = result[0] == mqtt.MQTT_ERR_SUCCESS
            if success:
                logger.debug(f"MQTT subscribed: {topic}")
            else:
                logger.error(f"MQTT subscribe failed: {topic}")
            return success
        except Exception as exc:
            logger.error(f"MQTT subscribe error: {exc}")
            return False

    # ── Paho callbacks ────────────────────────────────────────────────────────

    def _paho_on_connect(self, client, userdata, flags, rc) -> None:
        if rc == 0:
            logger.info(f"MQTT connected to {self._cfg.host}:{self._cfg.port}")
            self._connected = True
        else:
            logger.error(f"MQTT connect failed (rc={rc}): {mqtt.connack_string(rc)}")
            self._connected = False
            self._last_error = mqtt.connack_string(rc)

    def _paho_on_disconnect(self, client, userdata, rc) -> None:
        if rc != 0:
            logger.warning(f"MQTT unexpected disconnect (rc={rc})")
            self._connected = False
            if self._on_disconnect:
                asyncio.create_task(self._safe_call(self._on_disconnect))
            self.ensure_reconnect_loop()
        else:
            self._connected = False

    def _paho_on_message(self, client, userdata, msg) -> None:
        if self._on_message_cb:
            try:
                payload = msg.payload.decode("utf-8")
                self._on_message_cb(msg.topic, payload)
            except Exception as exc:
                logger.error(f"MQTT message callback error: {exc}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    async def _safe_call(fn: Callable) -> None:
        try:
            if asyncio.iscoroutinefunction(fn):
                await fn()
            else:
                fn()
        except Exception as exc:
            logger.error(f"MQTT callback error: {exc}")

    # ── Status ────────────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self._connected

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    def set_message_callback(self, callback: Callable) -> None:
        self._on_message_cb = callback

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def offline_buffer_size(self) -> int:
        return len(self._offline_buffer)
