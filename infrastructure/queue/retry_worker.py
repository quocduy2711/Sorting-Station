"""
RetryWorker — dedicated background task for retrying failed telemetry batches.

CRITICAL RULE: This worker MUST NOT block the drain pipeline.
It runs as a SEPARATE asyncio Task with its own retry loop.

Architecture:
    TelemetryPipeline (drain worker)
        ↓ on_batch_failed(batch, error)
    RetryWorker._retry_queue (asyncio.Queue)
        ↓
    RetryWorker._retry_loop() (background task)
        ↓ exponential backoff (async sleep, non-blocking)
    SQLiteSpoolQueue → HTTP upload
        ↓ on max retries exceeded
    Dead-letter (stays in spool with status='dead')
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, List, Optional

from infrastructure.observability.metrics import PipelineMetrics
from infrastructure.persistence.sqlite_spool import SQLiteSpoolQueue

logger = logging.getLogger(__name__)


class RetryWorker:
    """
    Dedicated retry worker — runs in its own asyncio Task.

    Two sources of retry items:
    1. Failed batches from TelemetryPipeline (via on_batch_failed callback)
    2. Failed items recovered from SQLite spool on startup

    Retry strategy:
        - Exponential backoff: 2^n seconds (2, 4, 8, 16, 32, 60 max)
        - Max retries configurable (default 5)
        - After max retries: dead-letter (stays in spool for forensics)
        - Uses asyncio.sleep() — non-blocking, cancellable

    The retry loop also periodically checks the spool for retryable items.
    """

    def __init__(
        self,
        upload_fn: Callable[[List[Dict[str, Any]]], Coroutine[Any, Any, bool]],
        spool: SQLiteSpoolQueue,
        metrics: PipelineMetrics,
        max_retries: int = 5,
        retry_check_interval_s: float = 5.0,
        max_retry_batch: int = 10,
    ) -> None:
        self._upload_fn = upload_fn
        self._spool = spool
        self._metrics = metrics
        self._max_retries = max_retries
        self._retry_check_interval_s = retry_check_interval_s
        self._max_retry_batch = max_retry_batch

        self._retry_task: Optional[asyncio.Task] = None
        self._running = False

    # ── Callback for TelemetryPipeline ────────────────────────────────────

    async def on_batch_failed(
        self, batch: List[Dict[str, Any]], error: str
    ) -> None:
        """
        Called by TelemetryPipeline when a batch upload fails.

        Persists failed items to SQLite spool for retry.
        This method is async-safe and non-blocking.
        """
        for payload in batch:
            await self._spool.enqueue(payload, priority=0)
        logger.debug(
            f"RetryWorker: {len(batch)} items spooled for retry (error={error})"
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the retry loop background task."""
        if self._running:
            return
        self._running = True
        self._retry_task = asyncio.create_task(
            self._retry_loop(), name="telemetry_retry"
        )
        logger.info(
            f"RetryWorker started "
            f"(check_interval={self._retry_check_interval_s}s, "
            f"max_retries={self._max_retries})"
        )

    async def stop(self) -> None:
        """Stop retry loop. Does NOT flush — items remain in spool for next restart."""
        self._running = False
        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
        logger.info("RetryWorker stopped")

    # ── Retry loop ────────────────────────────────────────────────────────

    async def _retry_loop(self) -> None:
        """
        Periodically check spool for retryable items and attempt re-upload.

        This is the ONLY place retries happen.
        The drain worker NEVER retries — it delegates to us.
        """
        logger.debug("Retry loop started")
        try:
            while self._running:
                await asyncio.sleep(self._retry_check_interval_s)

                # Fetch retryable items from spool
                items = await self._spool.get_retryable(
                    limit=self._max_retry_batch
                )
                if not items:
                    # Also update metrics gauge
                    depth = await self._spool.depth()
                    self._metrics.set_spool_depth(depth)
                    continue

                logger.debug(
                    f"RetryWorker: retrying {len(items)} items "
                    f"(retry_counts={[i.retry_count for i in items]})"
                )

                # Group payloads for batch upload
                payloads = [item.payload for item in items]
                ids = [item.id for item in items]

                try:
                    ok = await self._upload_fn(payloads)
                    if ok:
                        # Success — remove from spool
                        await self._spool.mark_done(ids)
                        self._metrics.inc_published(count=len(items))
                        self._metrics.inc_retried(count=len(items))
                        logger.info(
                            f"RetryWorker: {len(items)} items retried successfully"
                        )
                    else:
                        # Failed again — mark_failed handles backoff + dead-letter
                        await self._spool.mark_failed(ids, error="upload returned False")
                        self._metrics.inc_failed(count=len(items))

                except Exception as exc:
                    await self._spool.mark_failed(ids, error=str(exc))
                    self._metrics.inc_failed(count=len(items))
                    logger.warning(f"RetryWorker: retry failed: {exc}")

                # Update spool depth metric
                depth = await self._spool.depth()
                self._metrics.set_spool_depth(depth)

                # Dead letter cleanup (every cycle, lightweight)
                dead_count = await self._spool.dead_letter_count()
                if dead_count > 0:
                    self._metrics.set_retry_queue_depth(dead_count)
                    if dead_count > 100:
                        cleaned = await self._spool.cleanup_dead_letters(
                            max_age_s=86400.0
                        )
                        if cleaned:
                            logger.info(
                                f"RetryWorker: cleaned {cleaned} old dead-letters"
                            )

        except asyncio.CancelledError:
            logger.debug("Retry loop cancelled")
