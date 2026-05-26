"""
SQLiteSpoolQueue — persistent telemetry spool for crash recovery.

Design:
    - WAL mode for concurrent reads/writes
    - Non-blocking async wrapper over synchronous sqlite3
    - Runs all DB ops in executor (thread pool) to avoid blocking event loop
    - Recovers pending telemetry after restart/crash/power loss

Schema:
    telemetry_spool(
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        payload       TEXT NOT NULL,        -- JSON-serialized
        priority      INTEGER DEFAULT 0,    -- 0=normal, 1=alarm
        retry_count   INTEGER DEFAULT 0,
        status        TEXT DEFAULT 'pending',  -- pending | processing | failed | dead
        created_at    REAL NOT NULL,
        next_retry_at REAL,
        error_message TEXT
    )

Status lifecycle:
    pending → processing → (deleted on success)
    pending → processing → failed → (retry) → processing → ...
    failed (retry_count >= max) → dead
"""
from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS telemetry_spool (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    payload       TEXT    NOT NULL,
    priority      INTEGER DEFAULT 0,
    retry_count   INTEGER DEFAULT 0,
    status        TEXT    DEFAULT 'pending',
    created_at    REAL    NOT NULL,
    next_retry_at REAL,
    error_message TEXT
);
"""

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_spool_status
    ON telemetry_spool(status, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_spool_retry
    ON telemetry_spool(status, next_retry_at)
    WHERE status = 'failed';
"""


@dataclass(slots=True)
class SpoolItem:
    """A single spooled telemetry record."""
    id: int
    payload: Dict[str, Any]
    priority: int
    retry_count: int
    status: str
    created_at: float


class SQLiteSpoolQueue:
    """
    Persistent telemetry spool backed by SQLite.

    All operations run in asyncio executor to avoid blocking the event loop.
    The DB file is created in data/telemetry_spool.db by default.

    Usage:
        spool = SQLiteSpoolQueue(db_path="data/telemetry_spool.db")
        await spool.initialize()
        await spool.enqueue({"temp": 42.5})
        items = await spool.dequeue_batch(limit=20)
        await spool.mark_done([item.id for item in items])
        await spool.close()
    """

    def __init__(
        self,
        db_path: str = "data/telemetry_spool.db",
        max_size: int = 10000,
        max_retries: int = 5,
    ) -> None:
        self._db_path = db_path
        self._max_size = max_size
        self._max_retries = max_retries
        self._conn: Optional[sqlite3.Connection] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def initialize(self) -> None:
        """Create DB, tables, indexes. Recover any 'processing' rows from crash."""
        self._loop = asyncio.get_running_loop()
        await self._run_sync(self._init_db)
        recovered = await self._run_sync(self._recover_processing)
        if recovered > 0:
            logger.info(f"SQLiteSpool: recovered {recovered} pending items from previous crash")
        depth = await self.depth()
        logger.info(f"SQLiteSpool initialized: {self._db_path} (depth={depth})")

    def _init_db(self) -> None:
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            self._db_path, timeout=5.0, check_same_thread=False
        )
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=3000")
        self._conn.executescript(_CREATE_TABLE + _CREATE_INDEXES)
        self._conn.commit()

    def _recover_processing(self) -> int:
        """Reset 'processing' status back to 'pending' (crash recovery)."""
        cursor = self._conn.execute(
            "UPDATE telemetry_spool SET status='pending' WHERE status='processing'"
        )
        self._conn.commit()
        return cursor.rowcount

    # ── Enqueue ───────────────────────────────────────────────────────────

    async def enqueue(
        self, payload: Dict[str, Any], priority: int = 0
    ) -> bool:
        """
        Insert a telemetry payload into the spool.

        Drops oldest normal-priority items if spool exceeds max_size.
        Returns True if inserted, False on error.
        """
        return await self._run_sync(self._enqueue_sync, payload, priority)

    def _enqueue_sync(self, payload: Dict[str, Any], priority: int) -> bool:
        try:
            # Enforce max size — drop oldest normal items
            current = self._conn.execute(
                "SELECT COUNT(*) FROM telemetry_spool WHERE status != 'dead'"
            ).fetchone()[0]

            if current >= self._max_size:
                drop_count = current - self._max_size + 1
                self._conn.execute(
                    "DELETE FROM telemetry_spool WHERE id IN ("
                    "  SELECT id FROM telemetry_spool"
                    "  WHERE status='pending' AND priority=0"
                    "  ORDER BY created_at ASC LIMIT ?"
                    ")",
                    (drop_count,),
                )

            self._conn.execute(
                "INSERT INTO telemetry_spool (payload, priority, created_at) VALUES (?, ?, ?)",
                (json.dumps(payload), priority, time.time()),
            )
            self._conn.commit()
            return True
        except Exception as exc:
            logger.error(f"SQLiteSpool enqueue error: {exc}")
            return False

    async def enqueue_batch(
        self, payloads: List[Dict[str, Any]], priority: int = 0
    ) -> int:
        """Insert multiple payloads. Returns count inserted."""
        return await self._run_sync(self._enqueue_batch_sync, payloads, priority)

    def _enqueue_batch_sync(
        self, payloads: List[Dict[str, Any]], priority: int
    ) -> int:
        try:
            now = time.time()
            rows = [(json.dumps(p), priority, now) for p in payloads]
            self._conn.executemany(
                "INSERT INTO telemetry_spool (payload, priority, created_at) VALUES (?, ?, ?)",
                rows,
            )
            self._conn.commit()
            return len(rows)
        except Exception as exc:
            logger.error(f"SQLiteSpool batch enqueue error: {exc}")
            return 0

    # ── Dequeue ───────────────────────────────────────────────────────────

    async def dequeue_batch(self, limit: int = 20) -> List[SpoolItem]:
        """
        Fetch and lock up to `limit` pending items (highest priority first).

        Sets status='processing' atomically.
        """
        return await self._run_sync(self._dequeue_batch_sync, limit)

    def _dequeue_batch_sync(self, limit: int) -> List[SpoolItem]:
        try:
            rows = self._conn.execute(
                "SELECT id, payload, priority, retry_count, status, created_at "
                "FROM telemetry_spool "
                "WHERE status='pending' "
                "ORDER BY priority DESC, created_at ASC "
                "LIMIT ?",
                (limit,),
            ).fetchall()

            if not rows:
                return []

            ids = [r[0] for r in rows]
            placeholders = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE telemetry_spool SET status='processing' WHERE id IN ({placeholders})",
                ids,
            )
            self._conn.commit()

            return [
                SpoolItem(
                    id=r[0],
                    payload=json.loads(r[1]),
                    priority=r[2],
                    retry_count=r[3],
                    status="processing",
                    created_at=r[5],
                )
                for r in rows
            ]
        except Exception as exc:
            logger.error(f"SQLiteSpool dequeue error: {exc}")
            return []

    # ── Mark results ──────────────────────────────────────────────────────

    async def mark_done(self, ids: List[int]) -> None:
        """Delete successfully published items."""
        if not ids:
            return
        await self._run_sync(self._mark_done_sync, ids)

    def _mark_done_sync(self, ids: List[int]) -> None:
        placeholders = ",".join("?" * len(ids))
        self._conn.execute(
            f"DELETE FROM telemetry_spool WHERE id IN ({placeholders})", ids
        )
        self._conn.commit()

    async def mark_failed(
        self, ids: List[int], error: str = ""
    ) -> None:
        """Mark items as failed and schedule retry or dead-letter."""
        if not ids:
            return
        await self._run_sync(self._mark_failed_sync, ids, error)

    def _mark_failed_sync(self, ids: List[int], error: str) -> None:
        for item_id in ids:
            row = self._conn.execute(
                "SELECT retry_count FROM telemetry_spool WHERE id=?", (item_id,)
            ).fetchone()
            if not row:
                continue

            retry_count = row[0] + 1
            if retry_count >= self._max_retries:
                # Dead-letter
                self._conn.execute(
                    "UPDATE telemetry_spool SET status='dead', retry_count=?, error_message=? WHERE id=?",
                    (retry_count, error, item_id),
                )
            else:
                # Schedule retry with exponential backoff
                backoff = min(2 ** retry_count, 60)  # 2, 4, 8, 16, 32, 60
                next_retry = time.time() + backoff
                self._conn.execute(
                    "UPDATE telemetry_spool SET status='failed', retry_count=?, "
                    "next_retry_at=?, error_message=? WHERE id=?",
                    (retry_count, next_retry, error, item_id),
                )
        self._conn.commit()

    # ── Retry query ───────────────────────────────────────────────────────

    async def get_retryable(self, limit: int = 10) -> List[SpoolItem]:
        """Fetch failed items whose next_retry_at has passed."""
        return await self._run_sync(self._get_retryable_sync, limit)

    def _get_retryable_sync(self, limit: int) -> List[SpoolItem]:
        try:
            now = time.time()
            rows = self._conn.execute(
                "SELECT id, payload, priority, retry_count, status, created_at "
                "FROM telemetry_spool "
                "WHERE status='failed' AND next_retry_at <= ? "
                "ORDER BY priority DESC, next_retry_at ASC "
                "LIMIT ?",
                (now, limit),
            ).fetchall()

            if not rows:
                return []

            ids = [r[0] for r in rows]
            placeholders = ",".join("?" * len(ids))
            self._conn.execute(
                f"UPDATE telemetry_spool SET status='processing' WHERE id IN ({placeholders})",
                ids,
            )
            self._conn.commit()

            return [
                SpoolItem(
                    id=r[0],
                    payload=json.loads(r[1]),
                    priority=r[2],
                    retry_count=r[3],
                    status="processing",
                    created_at=r[5],
                )
                for r in rows
            ]
        except Exception as exc:
            logger.error(f"SQLiteSpool retry query error: {exc}")
            return []

    # ── Stats ─────────────────────────────────────────────────────────────

    async def depth(self) -> int:
        """Count of pending + processing + failed items."""
        return await self._run_sync(self._depth_sync)

    def _depth_sync(self) -> int:
        try:
            return self._conn.execute(
                "SELECT COUNT(*) FROM telemetry_spool WHERE status IN ('pending', 'processing', 'failed')"
            ).fetchone()[0]
        except Exception:
            return 0

    async def dead_letter_count(self) -> int:
        """Count of dead-lettered items."""
        return await self._run_sync(self._dead_letter_count_sync)

    def _dead_letter_count_sync(self) -> int:
        try:
            return self._conn.execute(
                "SELECT COUNT(*) FROM telemetry_spool WHERE status='dead'"
            ).fetchone()[0]
        except Exception:
            return 0

    async def cleanup_dead_letters(self, max_age_s: float = 86400.0) -> int:
        """Delete dead-letter items older than max_age_s. Default 24h."""
        return await self._run_sync(self._cleanup_sync, max_age_s)

    def _cleanup_sync(self, max_age_s: float) -> int:
        try:
            cutoff = time.time() - max_age_s
            cursor = self._conn.execute(
                "DELETE FROM telemetry_spool WHERE status='dead' AND created_at < ?",
                (cutoff,),
            )
            self._conn.commit()
            return cursor.rowcount
        except Exception:
            return 0

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Close DB connection."""
        if self._conn:
            await self._run_sync(self._close_sync)

    def _close_sync(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Executor helper ───────────────────────────────────────────────────

    async def _run_sync(self, fn, *args):
        """Run a synchronous function in the default executor."""
        loop = self._loop or asyncio.get_running_loop()
        return await loop.run_in_executor(None, fn, *args)
