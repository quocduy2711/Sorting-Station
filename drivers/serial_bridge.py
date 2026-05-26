"""
SerialBridge — giao tiếp giữa Python và ESP32 qua USB Serial.

RULE: Python là master, ESP32 là gateway.
RULE: Telemetry gửi qua ESP32 khi ESP32 available; fallback trực tiếp HTTP nếu không có.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict, Optional

try:
    import serial_asyncio
    _SERIAL_AVAILABLE = True
except ImportError:
    _SERIAL_AVAILABLE = False

logger = logging.getLogger(__name__)


class SerialBridge:
    """Async serial bridge to ESP32 gateway."""

    def __init__(self, port: str, baud: int = 115200) -> None:
        """Initialize serial bridge.

        Args:
            port: Serial port (e.g. 'COM3' on Windows, '/dev/ttyUSB0' on Linux).
            baud: Baud rate, default 115200.
        """
        if not _SERIAL_AVAILABLE:
            raise RuntimeError(
                "pyserial-asyncio is required for SerialBridge. "
                "Install: pip install pyserial-asyncio"
            )
        self.port = port
        self.baud = baud
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._rpc_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
        self._read_task: Optional[asyncio.Task] = None
        self.connected: bool = False
        self.last_temperature: float = 0.0

    async def connect(self) -> bool:
        """Open serial connection to ESP32.

        Returns:
            True if connection successful.
        """
        try:
            self._reader, self._writer = await serial_asyncio.open_serial_connection(
                url=self.port,
                baudrate=self.baud,
            )
            self.connected = True
            self._read_task = asyncio.create_task(
                self._read_loop(), name="serial_read"
            )
            logger.info(f"SerialBridge connected: {self.port} @ {self.baud}")
            return True
        except Exception as exc:
            logger.error(f"SerialBridge connect failed: {exc}")
            self.connected = False
            return False

    async def disconnect(self) -> None:
        """Close serial connection."""
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass

        if self._writer:
            self._writer.close()
            self._writer = None
            self._reader = None

        self.connected = False
        logger.info("SerialBridge disconnected")

    async def send_telemetry(self, payload: Dict[str, Any]) -> bool:
        """Send telemetry JSON to ESP32 for forwarding to ThingsBoard.

        Args:
            payload: Telemetry dict to send.

        Returns:
            True if sent successfully.
        """
        if not self.connected or not self._writer:
            return False

        try:
            message = json.dumps({"type": "telemetry", "data": payload})
            self._writer.write((message + "\n").encode("utf-8"))
            await self._writer.drain()
            return True
        except Exception as exc:
            logger.error(f"SerialBridge send error: {exc}")
            self.connected = False
            return False

    def on_rpc(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """Register callback for RPC commands received from TB via ESP32.

        Args:
            callback: Called with (method: str, params: dict).
        """
        self._rpc_callback = callback

    async def _read_loop(self) -> None:
        """Read JSON lines from ESP32 and dispatch RPC callbacks."""
        try:
            while self.connected and self._reader:
                line = await self._reader.readline()
                if not line:
                    continue

                try:
                    data = json.loads(line.decode("utf-8").strip())
                    msg_type = data.get("type", "")

                    if msg_type == "rpc" and self._rpc_callback:
                        method = data.get("method", "unknown")
                        params = data.get("params", {})
                        try:
                            self._rpc_callback(method, params)
                        except Exception as exc:
                            logger.error(f"SerialBridge RPC callback error: {exc}")

                    elif msg_type == "status":
                        wifi = data.get("wifi", False)
                        ip = data.get("ip", "")
                        logger.info(f"ESP32 status: wifi={wifi}, ip={ip}")

                except json.JSONDecodeError as exc:
                    logger.warning(f"SerialBridge invalid JSON: {exc}")
                except Exception as exc:
                    logger.error(f"SerialBridge read parse error: {exc}")

        except asyncio.CancelledError:
            logger.debug("SerialBridge read loop cancelled")
        except Exception as exc:
            logger.error(f"SerialBridge read loop error: {exc}")
            self.connected = False
