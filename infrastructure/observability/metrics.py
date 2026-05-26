"""
PipelineMetrics — thread-safe, Prometheus-friendly telemetry pipeline metrics.

All counters are monotonic (only increment).
Gauges (queue_depth, etc.) are point-in-time snapshots.

Usage:
    metrics = PipelineMetrics()
    metrics.inc_enqueued()
    metrics.inc_published(count=5)
    metrics.record_http_latency(12.3)
    snapshot = metrics.snapshot()
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque


@dataclass
class MetricsSnapshot:
    """Point-in-time snapshot of pipeline metrics."""
    # Counters (monotonic)
    total_enqueued: int = 0
    total_published: int = 0
    total_failed: int = 0
    total_dropped: int = 0
    total_retried: int = 0
    total_dead_lettered: int = 0
    total_alarms_published: int = 0
    total_batches_sent: int = 0

    # Gauges (point-in-time)
    queue_depth: int = 0
    spool_depth: int = 0
    retry_queue_depth: int = 0

    # Latency (ms)
    http_latency_avg_ms: float = 0.0
    http_latency_p99_ms: float = 0.0

    # MQTT
    mqtt_reconnect_count: int = 0
    mqtt_rpc_available: bool = False

    # Circuit breaker
    circuit_breaker_state: str = "closed"  # closed, open, half-open
    consecutive_failures: int = 0

    # Uptime
    uptime_seconds: float = 0.0


class PipelineMetrics:
    """
    Thread-safe pipeline metrics collector.

    Designed for zero-allocation fast path — counters are simple ints
    protected by a lightweight lock. Latency uses a bounded deque.
    """

    def __init__(self, latency_window: int = 100) -> None:
        self._lock = threading.Lock()
        self._start_time = time.monotonic()

        # Counters
        self._enqueued: int = 0
        self._published: int = 0
        self._failed: int = 0
        self._dropped: int = 0
        self._retried: int = 0
        self._dead_lettered: int = 0
        self._alarms_published: int = 0
        self._batches_sent: int = 0

        # Gauges (set externally)
        self._queue_depth: int = 0
        self._spool_depth: int = 0
        self._retry_queue_depth: int = 0

        # Latency ring buffer
        self._http_latencies: Deque[float] = deque(maxlen=latency_window)

        # MQTT
        self._mqtt_reconnect_count: int = 0
        self._mqtt_rpc_available: bool = False

        # Circuit breaker
        self._cb_state: str = "closed"
        self._consecutive_failures: int = 0

    # ── Counter increments ────────────────────────────────────────────────

    def inc_enqueued(self, count: int = 1) -> None:
        with self._lock:
            self._enqueued += count

    def inc_published(self, count: int = 1) -> None:
        with self._lock:
            self._published += count

    def inc_failed(self, count: int = 1) -> None:
        with self._lock:
            self._failed += count

    def inc_dropped(self, count: int = 1) -> None:
        with self._lock:
            self._dropped += count

    def inc_retried(self, count: int = 1) -> None:
        with self._lock:
            self._retried += count

    def inc_dead_lettered(self, count: int = 1) -> None:
        with self._lock:
            self._dead_lettered += count

    def inc_alarms_published(self, count: int = 1) -> None:
        with self._lock:
            self._alarms_published += count

    def inc_batches_sent(self, count: int = 1) -> None:
        with self._lock:
            self._batches_sent += count

    def inc_mqtt_reconnect(self) -> None:
        with self._lock:
            self._mqtt_reconnect_count += 1

    # ── Gauge setters ─────────────────────────────────────────────────────

    def set_queue_depth(self, depth: int) -> None:
        with self._lock:
            self._queue_depth = depth

    def set_spool_depth(self, depth: int) -> None:
        with self._lock:
            self._spool_depth = depth

    def set_retry_queue_depth(self, depth: int) -> None:
        with self._lock:
            self._retry_queue_depth = depth

    def set_mqtt_rpc_available(self, connected: bool) -> None:
        """Set MQTT RPC connection status."""
        with self._lock:
            self._mqtt_rpc_available = connected

    def set_circuit_breaker(self, state: str, consecutive: int) -> None:
        with self._lock:
            self._cb_state = state
            self._consecutive_failures = consecutive

    # ── Latency recording ─────────────────────────────────────────────────

    def record_http_latency(self, latency_ms: float) -> None:
        with self._lock:
            self._http_latencies.append(latency_ms)

    # ── Snapshot ──────────────────────────────────────────────────────────

    def snapshot(self) -> MetricsSnapshot:
        """Thread-safe point-in-time snapshot."""
        with self._lock:
            latencies = list(self._http_latencies)

            avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
            p99_lat = sorted(latencies)[int(len(latencies) * 0.99)] if latencies else 0.0

            return MetricsSnapshot(
                total_enqueued=self._enqueued,
                total_published=self._published,
                total_failed=self._failed,
                total_dropped=self._dropped,
                total_retried=self._retried,
                total_dead_lettered=self._dead_lettered,
                total_alarms_published=self._alarms_published,
                total_batches_sent=self._batches_sent,
                queue_depth=self._queue_depth,
                spool_depth=self._spool_depth,
                retry_queue_depth=self._retry_queue_depth,
                http_latency_avg_ms=round(avg_lat, 2),
                http_latency_p99_ms=round(p99_lat, 2),
                mqtt_reconnect_count=self._mqtt_reconnect_count,
                mqtt_rpc_available=self._mqtt_rpc_available,
                circuit_breaker_state=self._cb_state,
                consecutive_failures=self._consecutive_failures,
                uptime_seconds=round(time.monotonic() - self._start_time, 1),
            )
