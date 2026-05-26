"""
ConveyorErrorDetector — detects 3 types of conveyor errors.

RULE: When error detected → emit EMERGENCY event → FaultHandler handles shutdown.
RULE: Each error sends dedicated telemetry to ThingsBoard with error_code and error_msg.

Error types:
    ERR_SUDDEN_STOP   — Conveyor stops unexpectedly while RUNNING
    ERR_JAM           — Product stuck at same position too long
    ERR_VISION_STALL  — Vision reads product but it doesn't move
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

from control.event_manager import SystemEvent
from models.system_state import SystemStateEnum
from models.telemetry_payload import ErrorTelemetryPayload

if TYPE_CHECKING:
    from config.app_config import AppConfig
    from control.event_manager import EventManager
    from infrastructure.http.tb_http_client import TBHttpClient
    from models.system_state import SystemState

logger = logging.getLogger(__name__)


# ── Error codes ───────────────────────────────────────────────────────────────

class ErrorCode:
    """Conveyor error code constants."""
    SUDDEN_STOP  = "ERR_SUDDEN_STOP"   # Conveyor stopped unexpectedly while RUNNING
    JAM_DETECTED = "ERR_JAM"           # Product stuck at same position too long
    VISION_STALL = "ERR_VISION_STALL"  # Vision read but product doesn't move


# ── Detector ──────────────────────────────────────────────────────────────────

class ConveyorErrorDetector:
    """
    Detects conveyor error conditions and triggers emergency stops.

    Run check methods each scan cycle. When an error is detected:
    1. Set system_state.last_error
    2. Emit EMERGENCY_STOP_DETECTED event
    3. Publish error telemetry immediately via HTTP (bypass queue)
    """

    def __init__(
        self,
        system_state: "SystemState",
        event_manager: "EventManager",
        http_client: Optional["TBHttpClient"],
        jam_timeout_ms: float = 5000.0,
        vision_stall_timeout_ms: float = 3000.0,
        sudden_stop_debounce_ms: float = 500.0,
    ) -> None:
        """Initialize error detector.

        Args:
            system_state: Shared system state.
            event_manager: Event bus for emitting emergency events.
            http_client: HTTP client for immediate error telemetry.
            jam_timeout_ms: Max time product can stay at same position.
            vision_stall_timeout_ms: Max time after vision read with no movement.
            sudden_stop_debounce_ms: Debounce for sudden stop detection.
        """
        self._state = system_state
        self._em = event_manager
        self._http = http_client

        self._jam_timeout_ms = jam_timeout_ms
        self._vision_stall_timeout_ms = vision_stall_timeout_ms
        self._sudden_stop_debounce_ms = sudden_stop_debounce_ms

        # Internal tracking state
        self._prev_state: Optional[SystemStateEnum] = None
        self._motor_off_since: Optional[float] = None

    async def check_sudden_stop(self, motor_running: bool) -> bool:
        """Detect conveyor stopping unexpectedly.

        Condition: System state is RUNNING but Modbus reports motor OFF
        for longer than sudden_stop_debounce_ms.

        Args:
            motor_running: Current motor status from Modbus.

        Returns:
            True if sudden stop detected.
        """
        current_state = self._state.state
        now_ms = time.monotonic() * 1000

        if current_state == SystemStateEnum.RUNNING and not motor_running:
            if self._motor_off_since is None:
                self._motor_off_since = now_ms
            elif (now_ms - self._motor_off_since) > self._sudden_stop_debounce_ms:
                await self.trigger_emergency(
                    ErrorCode.SUDDEN_STOP,
                    f"Conveyor motor OFF while state={current_state.value} "
                    f"for {now_ms - self._motor_off_since:.0f}ms",
                )
                self._motor_off_since = None
                return True
        else:
            self._motor_off_since = None

        return False

    async def check_jam(self, product_position_unchanged_ms: float) -> bool:
        """Detect product jam on conveyor.

        Condition: A product has been at the same position for longer
        than jam_timeout_ms (read from proximity sensor / encoder).

        Args:
            product_position_unchanged_ms: Time in ms product has been stationary.

        Returns:
            True if jam detected.
        """
        if product_position_unchanged_ms > self._jam_timeout_ms:
            await self.trigger_emergency(
                ErrorCode.JAM_DETECTED,
                f"Product stationary for {product_position_unchanged_ms:.0f}ms "
                f"(threshold: {self._jam_timeout_ms:.0f}ms)",
            )
            return True
        return False

    async def check_vision_stall(
        self,
        vision_product_id: int,
        time_since_vision_read_ms: float,
        product_moved: bool,
    ) -> bool:
        """Detect vision sensor stall.

        Condition: Vision sensor read product_id != 0 but after
        vision_stall_timeout_ms the product still hasn't moved
        past the vision position.

        Args:
            vision_product_id: ID from vision sensor (0 = no product).
            time_since_vision_read_ms: Time since vision read in ms.
            product_moved: Whether downstream sensor confirms movement.

        Returns:
            True if vision stall detected.
        """
        if (
            vision_product_id != 0
            and not product_moved
            and time_since_vision_read_ms > self._vision_stall_timeout_ms
        ):
            await self.trigger_emergency(
                ErrorCode.VISION_STALL,
                f"Vision read product_id={vision_product_id} but no movement "
                f"after {time_since_vision_read_ms:.0f}ms "
                f"(threshold: {self._vision_stall_timeout_ms:.0f}ms)",
            )
            return True
        return False

    async def trigger_emergency(self, error_code: str, detail: str) -> None:
        """Handle detected error: set state, emit event, publish telemetry.

        RULE: Error telemetry is published immediately via HTTP, not queued.

        Args:
            error_code: ErrorCode constant.
            detail: Human-readable error description.
        """
        logger.critical(f"CONVEYOR ERROR [{error_code}]: {detail}")

        # 1. Record in system state
        self._state.last_error = f"{error_code}: {detail}"
        self._state.last_error_time = time.monotonic()

        # 2. Emit event for FaultHandler to pick up
        self._em.emit(
            SystemEvent.EMERGENCY_STOP_DETECTED,
            source="ConveyorErrorDetector",
            data={"error_code": error_code, "detail": detail},
        )

        # 3. Publish error telemetry immediately via HTTP (bypass queue)
        if self._http:
            error_payload = ErrorTelemetryPayload.create_now(
                error_code=error_code,
                error_message=detail,
                machine_state=self._state.state.value,
                emergency_active=True,
            )
            try:
                await self._http.post_telemetry(error_payload.to_dict())
            except Exception as exc:
                logger.error(f"Failed to publish error telemetry: {exc}")
