"""
HttpTelemetryPublisher — implements TelemetryPublisher port via HTTP.

This is the primary adapter for telemetry in the hybrid architecture.
It owns:
    - TelemetryPipeline (non-blocking queue + dual-trigger batch drain)
    - RetryWorker (separate task for failed batch retries)
    - SQLiteSpoolQueue (persistent storage for crash recovery)
    - PipelineMetrics (observability)

CRITICAL: enqueue_nowait() is the ONLY method called from the control loop.
It MUST be non-blocking and return in < 1µs.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from domain.ports.telemetry_publisher import TelemetryPublisher
from infrastructure.http.tb_http_client import TBHttpClient
from infrastructure.persistence.sqlite_spool import SQLiteSpoolQueue
from infrastructure.queue.telemetry_pipeline import TelemetryPipeline
from infrastructure.queue.retry_worker import RetryWorker
from infrastructure.observability.metrics import PipelineMetrics

logger = logging.getLogger(__name__)


class HttpTelemetryPublisher(TelemetryPublisher):
    """
    Production-grade telemetry publisher over HTTP.

    Lifecycle:
        __init__()  → constructs all sub-components
        start()     → initializes spool, starts pipeline + retry worker
        stop()      → graceful shutdown: flush → cancel → close

    Pipeline:
        enqueue_nowait(payload)
            → TelemetryPipeline (async queue)
            → BatchDrainWorker (dual-trigger)
            → TBHttpClient.post_telemetry_batch()
            → on failure: RetryWorker → SQLiteSpoolQueue → retry
    """

    def __init__(
        self,
        http_client: TBHttpClient,
        metrics: PipelineMetrics,
        spool_db_path: str = "data/telemetry_spool.db",
        max_queue_size: int = 1000,
        max_batch_size: int = 20,
        batch_window_s: float = 1.0,
        max_spool_size: int = 10000,
        max_retries: int = 5,
        retry_check_interval_s: float = 5.0,
    ) -> None:
        self._http = http_client
        self._metrics = metrics

        # SQLite spool for persistence
        self._spool = SQLiteSpoolQueue(
            db_path=spool_db_path,
            max_size=max_spool_size,
            max_retries=max_retries,
        )

        # Telemetry pipeline (non-blocking queue + drain worker)
        self._pipeline = TelemetryPipeline(
            upload_fn=self._upload_batch,
            metrics=metrics,
            max_queue_size=max_queue_size,
            max_batch_size=max_batch_size,
            batch_window_s=batch_window_s,
        )

        # Retry worker (separate background task)
        self._retry_worker = RetryWorker(
            upload_fn=self._upload_batch,
            spool=self._spool,
            metrics=metrics,
            max_retries=max_retries,
            retry_check_interval_s=retry_check_interval_s,
        )

        # Wire pipeline failure → retry worker
        self._pipeline.set_on_batch_failed(self._retry_worker.on_batch_failed)

    # ── TelemetryPublisher interface ──────────────────────────────────────

    def enqueue_nowait(self, payload: Dict[str, Any]) -> bool:
        """
        NON-BLOCKING telemetry enqueue.

        This method is called from the control loop (50ms cycle).
        It MUST complete in < 1µs and MUST NEVER await.
        """
        return self._pipeline.enqueue_nowait(payload)

    async def publish_alarm(self, payload: Dict[str, Any]) -> bool:
        """
        Priority publish for alarms — bypasses batching.

        Uses direct HTTP POST with 5s timeout.
        On failure, spools to SQLite for retry.
        """
        try:
            t0 = time.monotonic()
            ok = await self._http.post_telemetry(payload)
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._metrics.record_http_latency(latency_ms)

            if ok:
                self._metrics.inc_alarms_published()
                logger.info(f"Alarm published via HTTP ({latency_ms:.1f}ms)")
                return True
            else:
                # Spool alarm for retry (priority=1)
                await self._spool.enqueue(payload, priority=1)
                logger.warning("Alarm HTTP failed — spooled for retry")
                return False

        except Exception as exc:
            await self._spool.enqueue(payload, priority=1)
            logger.error(f"Alarm publish error: {exc} — spooled for retry")
            return False

    async def start(self) -> bool:
        """Initialize spool, start pipeline and retry worker."""
        logger.info("HttpTelemetryPublisher starting...")

        # 1. Initialize SQLite spool (recover pending items)
        await self._spool.initialize()

        # 2. Start HTTP client
        http_ok = await self._http.start()

        # 3. Start pipeline drain worker
        await self._pipeline.start()

        # 4. Start retry worker
        await self._retry_worker.start()

        logger.info(
            f"HttpTelemetryPublisher started "
            f"(http={'OK' if http_ok else 'DEGRADED'})"
        )
        return True  # Always return True — pipeline works even without HTTP

    async def stop(self) -> None:
        """Graceful shutdown: stop workers → flush → close spool → close HTTP."""
        logger.info("HttpTelemetryPublisher stopping...")

        # Stop pipeline first (flushes remaining items)
        await self._pipeline.stop()

        # Stop retry worker (items remain in spool)
        await self._retry_worker.stop()

        # Close spool
        await self._spool.close()

        # Close HTTP
        await self._http.stop()

        logger.info("HttpTelemetryPublisher stopped")

    def is_healthy(self) -> bool:
        """True if HTTP is reachable and circuit breaker is closed."""
        return self._http.is_healthy()

    def get_stats(self) -> Dict[str, Any]:
        """Pipeline statistics for observability."""
        snap = self._metrics.snapshot()
        return {
            "total_enqueued": snap.total_enqueued,
            "total_published": snap.total_published,
            "total_failed": snap.total_failed,
            "total_dropped": snap.total_dropped,
            "total_retried": snap.total_retried,
            "total_dead_lettered": snap.total_dead_lettered,
            "total_alarms": snap.total_alarms_published,
            "total_batches": snap.total_batches_sent,
            "queue_depth": snap.queue_depth,
            "spool_depth": snap.spool_depth,
            "http_latency_avg_ms": snap.http_latency_avg_ms,
            "circuit_breaker": snap.circuit_breaker_state,
        }

    # ── Internal ──────────────────────────────────────────────────────────

    async def _upload_batch(self, payloads: List[Dict[str, Any]]) -> bool:
        """Upload a batch of telemetry payloads via HTTP."""
        return await self._http.post_telemetry_batch(payloads)
