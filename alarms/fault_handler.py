"""
Fault handler for emergency shutdown and error recovery.

RULE: On ANY critical error, trigger failsafe_shutdown().
RULE: Failsafe disables all outputs except stop blade UP.
RULE: On emergency, publish error telemetry immediately via HTTP.
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Callable, Optional

from models.output_state import OutputState
from models.system_state import SystemState, SystemStateEnum
from models.telemetry_payload import ErrorTelemetryPayload
from drivers.output_writer import OutputWriter
from .alarm_manager import AlarmManager, AlarmType

if TYPE_CHECKING:
    from infrastructure.http.tb_http_client import TBHttpClient

logger = logging.getLogger(__name__)


class FaultHandler:
    """Handles critical faults and triggers failsafe shutdown."""

    def __init__(
        self,
        output_state: OutputState,
        system_state: SystemState,
        output_writer: OutputWriter,
        alarm_manager: AlarmManager,
        http_client: Optional["TBHttpClient"] = None,
    ) -> None:
        """Initialize fault handler.

        Args:
            output_state: Current output state for failsafe reset.
            system_state: System state to update on fault.
            output_writer: Modbus output writer.
            alarm_manager: Alarm registry.
            http_client: Optional HTTP client for immediate error telemetry.
        """
        self.output_state = output_state
        self.system_state = system_state
        self.output_writer = output_writer
        self.alarm_manager = alarm_manager
        self._http_client = http_client
        self.failsafe_triggered = False
        self.shutdown_callback: Optional[Callable] = None

    async def failsafe_shutdown(self, reason: str = "") -> None:
        """EMERGENCY: Shutdown system and disable all outputs.

        RULE: Called on critical error.
        RULE: Failsafe state: all OFF except stop blade UP.
        RULE: Publish error telemetry immediately via HTTP (no queue).

        Args:
            reason: Reason for shutdown.
        """
        if self.failsafe_triggered:
            logger.warning("Failsafe already triggered, ignoring duplicate")
            return

        self.failsafe_triggered = True
        logger.critical(f"FAILSAFE SHUTDOWN: {reason}")

        # Set system state
        self.system_state.set_state(SystemStateEnum.EMERGENCY_STOP)
        self.system_state.record_error(f"Failsafe shutdown: {reason}")

        # Reset all outputs
        self.output_state.reset_all()

        # Force write to Modbus
        success = await self.output_writer.write_all_coils()

        if success:
            logger.critical("Failsafe outputs written successfully")
        else:
            logger.error("Failed to write failsafe outputs to Modbus")

        # Trigger alarm
        self.alarm_manager.trigger_alarm(
            AlarmType.UNKNOWN,
            message=f"Failsafe shutdown: {reason}",
            source="FaultHandler"
        )

        # Publish error telemetry immediately via HTTP (bypass queue)
        if self._http_client:
            error_payload = ErrorTelemetryPayload.create_now(
                error_code="FAILSAFE_SHUTDOWN",
                error_message=reason,
                machine_state=self.system_state.state.value,
                emergency_active=True,
            )
            try:
                await self._http_client.post_telemetry(error_payload.to_dict())
                logger.info("Error telemetry published via HTTP")
            except Exception as exc:
                logger.error(f"Failed to publish error telemetry: {exc}")

        # Call user callback if set
        if self.shutdown_callback:
            try:
                if hasattr(self.shutdown_callback, '__await__'):
                    await self.shutdown_callback(reason)
                else:
                    self.shutdown_callback(reason)
            except Exception as e:
                logger.error(f"Error in shutdown callback: {e}")

    async def handle_modbus_error(self, error_message: str) -> None:
        """Handle Modbus communication error.

        Args:
            error_message: Error description.
        """
        logger.error(f"Modbus error: {error_message}")

        self.system_state.modbus_connected = False

        self.alarm_manager.trigger_alarm(
            AlarmType.MODBUS_DISCONNECT,
            message=error_message,
            source="ModbusError"
        )

    async def handle_watchdog_failure(self, check_name: str) -> None:
        """Handle watchdog timeout.

        Args:
            check_name: Name of failed watchdog check.
        """
        logger.critical(f"Watchdog failed: {check_name}")

        self.alarm_manager.trigger_alarm(
            AlarmType.WATCHDOG_FAILURE,
            message=f"Watchdog timeout: {check_name}",
            source="Watchdog"
        )

        # Trigger failsafe immediately
        await self.failsafe_shutdown(f"Watchdog failure: {check_name}")

    async def handle_vision_timeout(self) -> None:
        """Handle vision read timeout."""
        logger.error("Vision sensor read timeout")

        self.alarm_manager.trigger_alarm(
            AlarmType.VISION_TIMEOUT,
            message="Vision sensor did not respond",
            source="VisionSensor"
        )

    async def handle_sort_timeout(self, product_id: int, sorter_id: int) -> None:
        """Handle sort operation timeout.

        Args:
            product_id: Product ID.
            sorter_id: Sorter ID.
        """
        logger.error(f"Sort timeout: product {product_id} at sorter {sorter_id}")

        self.alarm_manager.trigger_alarm(
            AlarmType.SORT_TIMEOUT,
            message=f"Product {product_id} not removed from sorter {sorter_id}",
            source="SortTimeout"
        )

    async def handle_invalid_product_id(self, product_id: int) -> None:
        """Handle invalid product ID.

        Args:
            product_id: Invalid ID read from vision.
        """
        logger.error(f"Invalid product ID: {product_id}")

        self.alarm_manager.trigger_alarm(
            AlarmType.INVALID_PRODUCT_ID,
            message=f"Unknown product ID: {product_id}",
            source="VisionSensor"
        )

    async def handle_conveyor_jam(self) -> None:
        """Handle conveyor jam detection."""
        logger.error("Conveyor jam detected")

        self.alarm_manager.trigger_alarm(
            AlarmType.CONVEYOR_JAM,
            message="Product stuck on conveyor",
            source="JamDetection"
        )

        # Trigger failsafe
        await self.failsafe_shutdown("Conveyor jam detected")

    def set_shutdown_callback(self, callback: Callable) -> None:
        """Set callback to be called when shutdown occurs."""
        self.shutdown_callback = callback

    def is_failsafe_triggered(self) -> bool:
        """Check if failsafe has been triggered."""
        return self.failsafe_triggered

    def reset_failsafe(self) -> None:
        """Reset failsafe flag (for testing/recovery)."""
        self.failsafe_triggered = False

    async def reset_emergency(self) -> None:
        """Reset emergency state — allows restart after error is resolved.

        RULE: Called via RPC from dashboard after operator clears the fault.
        RULE: Transitions from EMERGENCY_STOP → IDLE (not directly to RUNNING).
        """
        if not self.failsafe_triggered:
            logger.warning("reset_emergency called but no failsafe active")
            return

        logger.info("Emergency reset — transitioning to IDLE")
        self.failsafe_triggered = False
        self.system_state.set_state(SystemStateEnum.IDLE)
        self.system_state.last_error = None
        self.system_state.last_error_time = None
