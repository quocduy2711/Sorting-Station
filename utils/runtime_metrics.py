"""
Runtime metrics — thread-safe rolling window metrics collection.

Tracks:
- Scan cycle time (current, avg, max)
- MQTT publish latency
- Reconnect counters (Modbus + MQTT)
- Dropped read / packet counters
- Offline buffer depth
- Watchdog trip counter
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Deque, Dict


# ── Snapshot (immutable) ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class MetricsSnapshot:
    """Point-in-time snapshot of runtime metrics."""
    # Scan cycle
    scan_cycle_ms: float
    avg_scan_cycle_ms: float
    max_scan_cycle_ms: float
    min_scan_cycle_ms: float

    # MQTT
    mqtt_publish_latency_ms: float
    avg_mqtt_latency_ms: float
    mqtt_reconnect_count: int
    mqtt_offline_buffer_size: int

    # Modbus
    modbus_reconnect_count: int
    modbus_dropped_reads: int

    # Watchdog
    watchdog_trips: int

    # Uptime
    uptime_seconds: float

    def to_dict(self) -> Dict:
        return {
            "scan_cycle_ms": round(self.scan_cycle_ms, 2),
            "avg_scan_cycle_ms": round(self.avg_scan_cycle_ms, 2),
            "max_scan_cycle_ms": round(self.max_scan_cycle_ms, 2),
            "min_scan_cycle_ms": round(self.min_scan_cycle_ms, 2),
            "mqtt_publish_latency_ms": round(self.mqtt_publish_latency_ms, 2),
            "avg_mqtt_latency_ms": round(self.avg_mqtt_latency_ms, 2),
            "mqtt_reconnect_count": self.mqtt_reconnect_count,
            "mqtt_offline_buffer_size": self.mqtt_offline_buffer_size,
            "modbus_reconnect_count": self.modbus_reconnect_count,
            "modbus_dropped_reads": self.modbus_dropped_reads,
            "watchdog_trips": self.watchdog_trips,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }


# ── Mutable collector ─────────────────────────────────────────────────────────

class RuntimeMetrics:
    """
    Thread-safe runtime metrics collector.

    Uses rolling windows for cycle/latency averages.
    All public methods are safe to call from async or sync code.
    """

    def __init__(self, window_size: int = 120) -> None:
        """
        Args:
            window_size: Number of samples for rolling averages.
        """
        self._lock = Lock()
        self._window = window_size

        self._scan_times: Deque[float] = deque(maxlen=window_size)
        self._mqtt_latencies: Deque[float] = deque(maxlen=window_size)

        self._last_scan_ms: float = 0.0
        self._last_mqtt_latency_ms: float = 0.0

        self._mqtt_reconnect_count: int = 0
        self._mqtt_offline_buffer: int = 0
        self._modbus_reconnect_count: int = 0
        self._modbus_dropped_reads: int = 0
        self._watchdog_trips: int = 0

        self._startup_time: float = time.monotonic()

    # ── Writers ───────────────────────────────────────────────────────────────

    def record_scan_cycle(self, ms: float) -> None:
        """Record one scan cycle duration."""
        with self._lock:
            self._last_scan_ms = ms
            self._scan_times.append(ms)

    def record_mqtt_latency(self, ms: float) -> None:
        """Record one MQTT publish round-trip latency."""
        with self._lock:
            self._last_mqtt_latency_ms = ms
            self._mqtt_latencies.append(ms)

    def increment_mqtt_reconnect(self) -> None:
        with self._lock:
            self._mqtt_reconnect_count += 1

    def set_mqtt_offline_buffer(self, size: int) -> None:
        with self._lock:
            self._mqtt_offline_buffer = size

    def increment_modbus_reconnect(self) -> None:
        with self._lock:
            self._modbus_reconnect_count += 1

    def increment_modbus_dropped_reads(self) -> None:
        with self._lock:
            self._modbus_dropped_reads += 1

    def increment_watchdog_trips(self) -> None:
        with self._lock:
            self._watchdog_trips += 1

    # ── Readers ───────────────────────────────────────────────────────────────

    def snapshot(self) -> MetricsSnapshot:
        """Return an immutable snapshot of current metrics."""
        with self._lock:
            scan_times = list(self._scan_times)
            mqtt_latencies = list(self._mqtt_latencies)

            avg_scan = sum(scan_times) / len(scan_times) if scan_times else 0.0
            max_scan = max(scan_times) if scan_times else 0.0
            min_scan = min(scan_times) if scan_times else 0.0
            avg_mqtt = (
                sum(mqtt_latencies) / len(mqtt_latencies)
                if mqtt_latencies else 0.0
            )

            return MetricsSnapshot(
                scan_cycle_ms=self._last_scan_ms,
                avg_scan_cycle_ms=avg_scan,
                max_scan_cycle_ms=max_scan,
                min_scan_cycle_ms=min_scan,
                mqtt_publish_latency_ms=self._last_mqtt_latency_ms,
                avg_mqtt_latency_ms=avg_mqtt,
                mqtt_reconnect_count=self._mqtt_reconnect_count,
                mqtt_offline_buffer_size=self._mqtt_offline_buffer,
                modbus_reconnect_count=self._modbus_reconnect_count,
                modbus_dropped_reads=self._modbus_dropped_reads,
                watchdog_trips=self._watchdog_trips,
                uptime_seconds=time.monotonic() - self._startup_time,
            )

    @property
    def last_scan_ms(self) -> float:
        return self._last_scan_ms

    @property
    def uptime_seconds(self) -> float:
        return time.monotonic() - self._startup_time
