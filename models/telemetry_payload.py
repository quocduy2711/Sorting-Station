"""
TelemetryPayload — typed telemetry schema for ThingsBoard.

RULE: All telemetry published to TB MUST go through this dataclass.
RULE: TelemetryService BUILDS this. ThingsBoardService PUBLISHES this.
RULE: Field names are stable — TB Dashboard keys must match.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict


@dataclass(slots=True)
class TelemetryPayload:
    """
    Slim telemetry schema — only fields needed for TB dashboard.

    Internal metrics (total_products, failed_sorts, scan_cycle_ms, etc.)
    are kept in SystemState for business logic but NOT published.
    """

    # --- Core machine state ---
    machine_state: str          # SystemStateEnum.value (RUNNING/STOPPED/EMERGENCY_STOP/ERROR)
    is_running: bool            # True if conveyor is running

    # --- Per-remover counters (3 removers) ---
    remover1_count: int         # Products dropped into Remover 1
    remover2_count: int
    remover3_count: int

    # --- Vision sensor ---
    vision_product_id: int      # ID from vision sensor (0 = none)
    vision_product_shape: str   # "Flat" / "Circle" / "Complex" / "Unknown"
    vision_product_color: str   # "Blue" / "Green" / "Unknown"
    vision_ok: bool             # Vision sensor operating normally

    # --- Connectivity ---
    modbus_connected: bool
    mqtt_rpc_available: bool    # (renamed from mqtt_connected)

    # --- Health ---
    temperature_c: float        # Temperature from sensor (°C), default 0.0
    uptime_seconds: float
    heartbeat: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to TB-compatible flat dict. Floats rounded for bandwidth."""
        return {
            "machine_state":        self.machine_state,
            "is_running":           self.is_running,
            "remover1_count":       self.remover1_count,
            "remover2_count":       self.remover2_count,
            "remover3_count":       self.remover3_count,
            "vision_product_id":    self.vision_product_id,
            "vision_product_shape": self.vision_product_shape,
            "vision_product_color": self.vision_product_color,
            "vision_ok":            self.vision_ok,
            "modbus_connected":     self.modbus_connected,
            "mqtt_rpc_available":   self.mqtt_rpc_available,
            "temperature_c":        round(self.temperature_c, 1),
            "uptime_seconds":       round(self.uptime_seconds, 1),
            "heartbeat":            self.heartbeat,
        }


@dataclass(slots=True)
class ErrorTelemetryPayload:
    """
    Error telemetry — sent immediately on error detection, not queued.

    RULE: Bypasses normal telemetry cycle for instant error reporting.
    """
    error_code: str         # ErrorCode constant
    error_message: str      # Detailed description
    machine_state: str      # State at time of error
    emergency_active: bool  # True = emergency stop activated
    timestamp_ms: int       # epoch ms

    def to_dict(self) -> Dict[str, Any]:
        """Convert to TB-compatible flat dict."""
        return {
            "error_code":       self.error_code,
            "error_message":    self.error_message,
            "machine_state":    self.machine_state,
            "emergency_active": self.emergency_active,
            "error_timestamp":  self.timestamp_ms,
        }

    @classmethod
    def create_now(
        cls,
        error_code: str,
        error_message: str,
        machine_state: str,
        emergency_active: bool = True,
    ) -> "ErrorTelemetryPayload":
        """Factory method with auto-timestamp."""
        return cls(
            error_code=error_code,
            error_message=error_message,
            machine_state=machine_state,
            emergency_active=emergency_active,
            timestamp_ms=int(time.time() * 1000),
        )
