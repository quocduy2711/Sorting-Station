"""
Health monitor — checks liveness of critical subsystems.

Produces a structured health report for:
- MQTT connection
- Modbus connection
- Scan loop alive
- Telemetry loop alive
- Watchdog status
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from utils.runtime_metrics import RuntimeMetrics

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    OK = "OK"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: HealthStatus
    message: str = ""
    last_ok_at: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "status": self.status.value,
            "message": self.message,
            "last_ok_seconds_ago": round(time.monotonic() - self.last_ok_at, 1)
            if self.last_ok_at > 0 else -1,
        }


@dataclass
class HealthReport:
    """Aggregated health report for the entire system."""
    overall: HealthStatus
    components: Dict[str, ComponentHealth]
    timestamp: float

    def to_dict(self) -> Dict:
        return {
            "overall": self.overall.value,
            "timestamp": self.timestamp,
            "components": {
                name: comp.to_dict()
                for name, comp in self.components.items()
            },
        }

    def is_healthy(self) -> bool:
        return self.overall == HealthStatus.OK

    def is_critical(self) -> bool:
        return self.overall == HealthStatus.CRITICAL


class HealthMonitor:
    """
    Monitors liveness of critical subsystems.

    Relies on external references to modbus/mqtt clients and
    runtime metrics to determine health.
    """

    # Max age for scan cycle heartbeat (seconds)
    MAX_SCAN_AGE_S: float = 2.0

    def __init__(
        self,
        runtime_metrics: "RuntimeMetrics",
        scan_interval_ms: int = 50,
    ) -> None:
        """
        Args:
            runtime_metrics:  RuntimeMetrics instance to read from.
            scan_interval_ms: Expected scan interval (for staleness check).
        """
        self._metrics = runtime_metrics
        self._scan_interval_ms = scan_interval_ms
        self._last_report: Optional[HealthReport] = None

        # External status flags (set by drivers on connect/disconnect)
        self._modbus_connected: bool = False
        self._mqtt_rpc_available: bool = False
        self._watchdog_ok: bool = True

        # Timestamps
        self._last_scan_time: float = time.monotonic()
        self._last_telemetry_time: float = time.monotonic()

    # ── Setters (called by drivers) ───────────────────────────────────────────

    def set_modbus_connected(self, connected: bool) -> None:
        self._modbus_connected = connected

    def set_mqtt_rpc_available(self, connected: bool) -> None:
        """Set MQTT RPC connection status."""
        self._mqtt_rpc_available = connected

    def set_watchdog_ok(self, ok: bool) -> None:
        self._watchdog_ok = ok

    def heartbeat_scan(self) -> None:
        """Called each scan cycle to indicate scan loop is alive."""
        self._last_scan_time = time.monotonic()

    def heartbeat_telemetry(self) -> None:
        """Called each telemetry publish to indicate telemetry loop alive."""
        self._last_telemetry_time = time.monotonic()

    # ── Health Check ─────────────────────────────────────────────────────────

    def get_health(self) -> HealthReport:
        """
        Evaluate and return a full health report.

        Returns:
            HealthReport with per-component and overall status.
        """
        now = time.monotonic()
        components: Dict[str, ComponentHealth] = {}

        # ── Modbus ───────────────────────────────────────────────────────
        modbus_status = HealthStatus.OK if self._modbus_connected else HealthStatus.CRITICAL
        components["modbus"] = ComponentHealth(
            name="modbus",
            status=modbus_status,
            message="Connected" if self._modbus_connected else "Disconnected — scan will degrade",
            last_ok_at=now if self._modbus_connected else 0.0,
        )

        # ── MQTT ─────────────────────────────────────────────────────────
        mqtt_status = HealthStatus.OK if self._mqtt_rpc_available else HealthStatus.DEGRADED
        components["mqtt"] = ComponentHealth(
            name="mqtt",
            status=mqtt_status,
            message="Connected" if self._mqtt_rpc_available else "Disconnected — buffering offline",
            last_ok_at=now if self._mqtt_rpc_available else 0.0,
        )

        # ── Scan Loop ────────────────────────────────────────────────────
        scan_age = now - self._last_scan_time
        max_age = max(self.MAX_SCAN_AGE_S, (self._scan_interval_ms / 1000.0) * 5)
        if scan_age < max_age:
            scan_status = HealthStatus.OK
            scan_msg = f"Alive (last {scan_age*1000:.0f}ms ago)"
        else:
            scan_status = HealthStatus.CRITICAL
            scan_msg = f"STALLED — no heartbeat for {scan_age:.1f}s"

        components["scan_loop"] = ComponentHealth(
            name="scan_loop",
            status=scan_status,
            message=scan_msg,
            last_ok_at=self._last_scan_time,
        )

        # ── Telemetry Loop ───────────────────────────────────────────────
        telem_age = now - self._last_telemetry_time
        telem_ok = telem_age < 10.0  # Should publish at least every 10s
        components["telemetry_loop"] = ComponentHealth(
            name="telemetry_loop",
            status=HealthStatus.OK if telem_ok else HealthStatus.DEGRADED,
            message=f"Last publish {telem_age:.1f}s ago",
            last_ok_at=self._last_telemetry_time,
        )

        # ── Watchdog ─────────────────────────────────────────────────────
        wd_status = HealthStatus.OK if self._watchdog_ok else HealthStatus.CRITICAL
        components["watchdog"] = ComponentHealth(
            name="watchdog",
            status=wd_status,
            message="OK" if self._watchdog_ok else "TRIPPED",
            last_ok_at=now if self._watchdog_ok else 0.0,
        )

        # ── Overall ──────────────────────────────────────────────────────
        statuses = [c.status for c in components.values()]
        if HealthStatus.CRITICAL in statuses:
            overall = HealthStatus.CRITICAL
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.OK

        report = HealthReport(
            overall=overall,
            components=components,
            timestamp=now,
        )
        self._last_report = report
        return report

    def get_last_report(self) -> Optional[HealthReport]:
        """Return the last generated health report (may be stale)."""
        return self._last_report
