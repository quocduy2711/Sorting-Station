"""
Async Modbus TCP client for Factory I/O communication.

Features:
- AsyncModbusTcpClient (non-blocking, safe in asyncio event loop)
- Exponential backoff reconnect loop
- Degraded mode flag when disconnected
- Reconnect counter for runtime metrics
- Emits MODBUS_RECONNECTED / MODBUS_DISCONNECTED events via callback

Library: pymodbus >= 3.6 (asyncio variant)
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Callable, Dict, List, Optional

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException

from config.app_config import ModbusConfig, ReconnectConfig

logger = logging.getLogger(__name__)


class ModbusClient:
    """
    Async Modbus TCP client with automatic reconnect.

    RULE: All I/O methods are awaitable and never block the event loop.
    RULE: On disconnect, enter degraded_mode and begin reconnect loop.
    RULE: Notify on_reconnect / on_disconnect callbacks for event emission.
    """

    def __init__(
        self,
        modbus_cfg: ModbusConfig,
        reconnect_cfg: ReconnectConfig,
        on_reconnect: Optional[Callable] = None,
        on_disconnect: Optional[Callable] = None,
    ) -> None:
        self._cfg = modbus_cfg
        self._rcfg = reconnect_cfg

        self._client: Optional[AsyncModbusTcpClient] = None
        self._connected: bool = False
        self._degraded_mode: bool = False
        self._last_error: Optional[str] = None

        self._reconnect_count: int = 0
        self._dropped_reads: int = 0

        # External callbacks (set by service layer)
        self._on_reconnect: Optional[Callable] = on_reconnect
        self._on_disconnect: Optional[Callable] = on_disconnect

        self._reconnect_task: Optional[asyncio.Task] = None

    # ── Connection lifecycle ──────────────────────────────────────────────────

    async def connect(self) -> bool:
        """
        Attempt initial connection to Modbus server.

        Returns:
            True if connected successfully.
        """
        self._client = AsyncModbusTcpClient(
            host=self._cfg.host,
            port=self._cfg.port,
            timeout=self._cfg.timeout,
        )
        try:
            await self._client.connect()
            if self._client.connected:
                self._connected = True
                self._degraded_mode = False
                logger.info(
                    f"Modbus connected → {self._cfg.host}:{self._cfg.port}"
                )
                return True
            else:
                self._last_error = "Connection refused"
                logger.error(f"Modbus connect failed: {self._last_error}")
                self._enter_degraded()
                return False
        except (ModbusException, ConnectionException, OSError) as exc:
            self._last_error = str(exc)
            logger.error(f"Modbus connect error: {exc}")
            self._enter_degraded()
            return False

    async def disconnect(self) -> None:
        """Gracefully close Modbus connection and cancel reconnect loop."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        if self._client:
            self._client.close()
            self._connected = False
            logger.info("Modbus disconnected")

    # ── Reconnect (exponential backoff) ──────────────────────────────────────

    def _enter_degraded(self) -> None:
        """Enter degraded mode and start reconnect loop."""
        if not self._degraded_mode:
            self._connected = False
            self._degraded_mode = True
            logger.warning("Modbus entering DEGRADED mode — reconnect loop starting")
            if self._on_disconnect:
                asyncio.create_task(self._safe_call(self._on_disconnect))

    async def start_reconnect_loop(self) -> None:
        """
        Background task: attempt reconnect with exponential backoff.

        base_s → base_s*2 → base_s*4 → ... → max_s (capped)
        """
        delay = self._rcfg.modbus_base_s
        while True:
            await asyncio.sleep(delay)
            logger.info(f"Modbus reconnect attempt #{self._reconnect_count + 1} …")

            success = await self.connect()
            if success:
                self._reconnect_count += 1
                self._degraded_mode = False
                logger.info(
                    f"Modbus reconnected (attempt #{self._reconnect_count})"
                )
                if self._on_reconnect:
                    await self._safe_call(self._on_reconnect)
                return  # Exit loop — reconnected

            # Back-off
            delay = min(delay * 2.0, self._rcfg.modbus_max_s)
            logger.warning(f"Modbus reconnect failed — retrying in {delay:.1f}s")

    def ensure_reconnect_loop(self) -> None:
        """
        Ensure a reconnect loop is running (idempotent).
        Call this after detecting a connection loss during read/write.
        """
        if self._reconnect_task is None or self._reconnect_task.done():
            self._reconnect_task = asyncio.create_task(
                self.start_reconnect_loop(),
                name="modbus_reconnect",
            )

    # ── Read operations ───────────────────────────────────────────────────────

    async def read_discrete_inputs(
        self, address: int = 0, count: int = 6
    ) -> Optional[List[bool]]:
        """
        Read discrete inputs (digital sensor signals).

        Returns:
            List[bool] or None on error / degraded mode.
        """
        if not self._connected or not self._client:
            self._dropped_reads += 1
            return None

        try:
            response = await self._client.read_discrete_inputs(
                address=address, count=count, device_id=self._cfg.unit_id
            )
            if response.isError():
                self._last_error = f"read_discrete_inputs error: {response}"
                logger.error(self._last_error)
                return None
            return list(response.bits[:count])

        except (ModbusException, ConnectionException, OSError) as exc:
            self._last_error = str(exc)
            logger.error(f"Modbus read error: {exc}")
            self._handle_comm_error()
            return None

    async def read_input_registers(
        self, address: int = 0, count: int = 1
    ) -> Optional[List[int]]:
        """
        Read input registers (vision sensor value).

        Returns:
            List[int] or None on error.
        """
        if not self._connected or not self._client:
            self._dropped_reads += 1
            return None

        try:
            response = await self._client.read_input_registers(
                address=address, count=count, device_id=self._cfg.unit_id
            )
            if response.isError():
                self._last_error = f"read_input_registers error: {response}"
                logger.error(self._last_error)
                return None
            return list(response.registers)

        except (ModbusException, ConnectionException, OSError) as exc:
            self._last_error = str(exc)
            logger.error(f"Modbus read error: {exc}")
            self._handle_comm_error()
            return None

    # ── Write operations ──────────────────────────────────────────────────────

    async def write_coil(
        self, address: int, value: bool, retries: int = 1
    ) -> bool:
        """
        Write a single coil with retry.

        Returns:
            True if successful.
        """
        if not self._connected or not self._client:
            return False

        for attempt in range(retries + 1):
            try:
                response = await self._client.write_coil(
                    address=address, value=value, device_id=self._cfg.unit_id
                )
                if not response.isError():
                    return True
                self._last_error = f"write_coil addr={address}: {response}"
                logger.warning(self._last_error)

            except (ModbusException, ConnectionException, OSError) as exc:
                self._last_error = str(exc)
                logger.error(f"Modbus write error (attempt {attempt+1}): {exc}")
                self._handle_comm_error()
                return False

        return False

    async def write_coils(
        self, address: int, values: List[bool], retries: int = 1
    ) -> bool:
        """
        Write multiple coils with retry.

        Returns:
            True if successful.
        """
        if not self._connected or not self._client:
            return False

        for attempt in range(retries + 1):
            try:
                response = await self._client.write_coils(
                    address=address, values=values, device_id=self._cfg.unit_id
                )
                if not response.isError():
                    return True
                self._last_error = f"write_coils addr={address}: {response}"
                logger.warning(self._last_error)

            except (ModbusException, ConnectionException, OSError) as exc:
                self._last_error = str(exc)
                logger.error(f"Modbus write_coils error (attempt {attempt+1}): {exc}")
                self._handle_comm_error()
                return False

        return False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _handle_comm_error(self) -> None:
        """Called on any communication failure."""
        if self._connected:
            self._enter_degraded()
            self.ensure_reconnect_loop()

    @staticmethod
    async def _safe_call(fn: Callable) -> None:
        """Call a callback safely (async or sync)."""
        try:
            if asyncio.iscoroutinefunction(fn):
                await fn()
            else:
                fn()
        except Exception as exc:
            logger.error(f"Callback error: {exc}")

    # ── Status ────────────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self._connected

    def is_degraded(self) -> bool:
        return self._degraded_mode

    def get_last_error(self) -> Optional[str]:
        return self._last_error

    @property
    def reconnect_count(self) -> int:
        return self._reconnect_count

    @property
    def dropped_reads(self) -> int:
        return self._dropped_reads
