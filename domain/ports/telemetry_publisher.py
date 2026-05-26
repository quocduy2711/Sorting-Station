"""
TelemetryPublisher — port for publishing telemetry to cloud platform.

CRITICAL CONTRACT:
    enqueue_nowait() MUST be non-blocking.
    It MUST NEVER raise, MUST NEVER await network I/O.
    Overflow → drop oldest, log warning.

This is the ONLY interface the application layer uses for telemetry.
The infrastructure layer handles HTTP/MQTT/buffering/retry behind it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class TelemetryPublisher(ABC):
    """
    Port for non-blocking telemetry publishing.

    Two modes:
        enqueue_nowait()   — fire-and-forget, non-blocking (for control loop)
        publish_alarm()    — priority publish, may retry internally

    Lifecycle:
        start() → ... → stop()
    """

    @abstractmethod
    def enqueue_nowait(self, payload: Dict[str, Any]) -> bool:
        """
        Non-blocking enqueue of telemetry payload.

        MUST NOT await, MUST NOT block, MUST NOT raise.
        Returns True if enqueued, False if dropped (queue full).
        """

    @abstractmethod
    async def publish_alarm(self, payload: Dict[str, Any]) -> bool:
        """
        Priority publish for alarms — bypasses batching, retries on failure.

        May await briefly for HTTP POST but MUST have a hard timeout.
        Returns True if delivered, False if queued for retry.
        """

    @abstractmethod
    async def start(self) -> bool:
        """Start background workers (drain, retry, spool). Returns success."""

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown: flush pending → cancel workers → close connections."""

    @abstractmethod
    def is_healthy(self) -> bool:
        """True if the publisher can accept and deliver telemetry."""

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        Pipeline statistics for observability.

        Expected keys:
            total_enqueued, total_published, total_failed, total_dropped,
            queue_depth, spool_depth, retry_queue_depth
        """
