"""
TelemetryPipeline — non-blocking telemetry drain with dual-trigger batching.

Architecture:
    enqueue_nowait(payload)         ← called from control loop (NEVER blocks)
        ↓
    asyncio.Queue (bounded)         ← in-memory, fast
        ↓
    _drain_worker() (background)    ← dual-trigger: batch_size >= N OR window >= T
        ↓
    SQLiteSpoolQueue.enqueue_batch  ← persist before HTTP
        ↓
    _upload_batch()                 ← HTTP POST to ThingsBoard
        ↓ on failure
    RetryWorker                     ← separate task handles retries

CRITICAL INVARIANT:
    enqueue_nowait() MUST complete in < 1µs.
    It MUST NEVER await, MUST NEVER call I/O, MUST NEVER raise.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

from infrastructure.observability.metrics import PipelineMetrics

logger = logging.getLogger(__name__)


class TelemetryPipeline:
    """
    Non-blocking telemetry pipeline with dual-trigger batch drain.

    Dual-trigger flush:
        Flush when EITHER condition is met:
        1. Batch size >= max_batch_size (e.g. 20 items)
        2. Oldest item age >= batch_window_s (e.g. 1.0 second)

    Config:
        max_queue_size:  bounded asyncio.Queue capacity (default 1000)
        max_batch_size:  max items per flush batch (default 20)
        batch_window_s:  max age before forced flush (default 1.0s)
    """

    def __init__(
        self,
        upload_fn: Callable[[List[Dict[str, Any]]], Coroutine[Any, Any, bool]],
        metrics: PipelineMetrics,
        spool_enqueue_fn: Optional[Callable] = None,
        max_queue_size: int = 1000,
        max_batch_size: int = 20,
        batch_window_s: float = 1.0,
    ) -> None:
        self._upload_fn = upload_fn
        self._metrics = metrics
        self._spool_enqueue_fn = spool_enqueue_fn

        self._queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._max_batch_size = max_batch_size
        self._batch_window_s = batch_window_s

        self._drain_task: Optional[asyncio.Task] = None
        self._running = False

        # Failed batch callback — wired to RetryWorker
        self._on_batch_failed: Optional[
            Callable[[List[Dict[str, Any]], str], Coroutine]
        ] = None

    # ── Non-blocking enqueue ──────────────────────────────────────────────

    def enqueue_nowait(self, payload: Dict[str, Any]) -> bool:
        """
        Non-blocking enqueue. MUST NEVER block the caller.

        Returns True if enqueued, False if dropped (queue full).
        On drop: logs warning, increments dropped counter.
        """
        try:
            self._queue.put_nowait(payload)
            self._metrics.inc_enqueued()
            return True
        except asyncio.QueueFull:
            # Drop oldest by draining one and adding new
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(payload)
                self._metrics.inc_dropped()
                logger.warning(
                    f"Telemetry queue full ({self._queue.maxsize}) — "
                    f"dropped oldest item"
                )
                return True
            except Exception:
                self._metrics.inc_dropped()
                return False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background drain worker."""
        if self._running:
            return
        self._running = True
        self._drain_task = asyncio.create_task(
            self._drain_worker(), name="telemetry_drain"
        )
        logger.info(
            f"TelemetryPipeline started "
            f"(batch_size={self._max_batch_size}, "
            f"window={self._batch_window_s}s, "
            f"queue_max={self._queue.maxsize})"
        )

    async def stop(self) -> None:
        """Graceful shutdown: flush remaining items, cancel worker."""
        self._running = False
        if self._drain_task:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass

        # Final flush — best effort
        remaining = self._drain_queue()
        if remaining:
            logger.info(
                f"TelemetryPipeline: flushing {len(remaining)} items on shutdown"
            )
            await self._upload_batch(remaining)

        logger.info("TelemetryPipeline stopped")

    def set_on_batch_failed(
        self,
        callback: Callable[[List[Dict[str, Any]], str], Coroutine],
    ) -> None:
        """Wire the retry worker callback for failed batches."""
        self._on_batch_failed = callback

    # ── Drain worker ──────────────────────────────────────────────────────

    async def _drain_worker(self) -> None:
        """
        Background task: dual-trigger batch drain.

        Flushes when:
            batch_size >= max_batch_size  (size trigger)
            OR
            oldest item age >= batch_window_s  (time trigger)
        """
        logger.debug("Drain worker started")
        batch: List[Dict[str, Any]] = []
        batch_start: float = time.monotonic()

        try:
            while self._running:
                # Calculate time until window expires
                age = time.monotonic() - batch_start
                remaining_window = max(0.01, self._batch_window_s - age)

                try:
                    # Wait for next item with timeout = remaining window
                    item = await asyncio.wait_for(
                        self._queue.get(), timeout=remaining_window
                    )
                    batch.append(item)
                    self._metrics.set_queue_depth(self._queue.qsize())
                except asyncio.TimeoutError:
                    pass  # Window expired — flush below

                # Dual-trigger check
                should_flush = (
                    len(batch) >= self._max_batch_size  # Size trigger
                    or (
                        batch
                        and (time.monotonic() - batch_start) >= self._batch_window_s
                    )  # Time trigger
                )

                if should_flush and batch:
                    await self._upload_batch(batch)
                    batch = []
                    batch_start = time.monotonic()

        except asyncio.CancelledError:
            # Flush remaining on cancellation
            batch.extend(self._drain_queue())
            if batch:
                await self._upload_batch(batch)
            logger.debug("Drain worker cancelled")

    def _drain_queue(self) -> List[Dict[str, Any]]:
        """Drain all remaining items from the queue (non-blocking)."""
        items = []
        while not self._queue.empty():
            try:
                items.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        return items

    async def _upload_batch(self, batch: List[Dict[str, Any]]) -> None:
        """
        Attempt to upload a batch. On failure, delegate to retry worker.

        If spool_enqueue_fn is set, persists to SQLite before upload
        for crash recovery.
        """
        if not batch:
            return

        # Persist to spool first (crash recovery)
        if self._spool_enqueue_fn:
            try:
                await self._spool_enqueue_fn(batch, priority=0)
            except Exception as exc:
                logger.warning(f"Spool persist failed (non-fatal): {exc}")

        # Attempt HTTP upload
        try:
            t0 = time.monotonic()
            ok = await self._upload_fn(batch)
            latency_ms = (time.monotonic() - t0) * 1000.0
            self._metrics.record_http_latency(latency_ms)

            if ok:
                self._metrics.inc_published(count=len(batch))
                self._metrics.inc_batches_sent()
                logger.debug(
                    f"Batch uploaded: {len(batch)} items ({latency_ms:.1f}ms)"
                )
            else:
                await self._handle_batch_failure(batch, "HTTP upload returned False")

        except Exception as exc:
            await self._handle_batch_failure(batch, str(exc))

    async def _handle_batch_failure(
        self, batch: List[Dict[str, Any]], error: str
    ) -> None:
        """Route failed batch to retry worker or log."""
        self._metrics.inc_failed(count=len(batch))
        logger.warning(f"Batch upload failed ({len(batch)} items): {error}")

        if self._on_batch_failed:
            try:
                await self._on_batch_failed(batch, error)
            except Exception as exc:
                logger.error(f"Retry callback error: {exc}")

    # ── Stats ─────────────────────────────────────────────────────────────

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize()
