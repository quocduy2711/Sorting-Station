"""
TBHttpClient — shared HTTP client for ThingsBoard REST API.

Features:
    - Shared aiohttp.ClientSession with connection pooling
    - Circuit breaker (open after N consecutive failures, reset after T seconds)
    - Request timeout (configurable, default 5s)
    - Never raises — all errors return False with structured logging
    - Session pool: reuses TCP connections to TB server

Endpoints:
    POST /api/v1/{token}/telemetry      → telemetry upload
    POST /api/v1/{token}/attributes     → client attributes
    GET  /api/v1/{token}/attributes     → request shared attributes

Docs: https://thingsboard.io/docs/reference/http-api/
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

try:
    import aiohttp
    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

logger = logging.getLogger(__name__)


class TBHttpClient:
    """
    Low-level HTTP client for ThingsBoard REST API.

    Shared by all HTTP adapters (telemetry, attributes, health).
    Implements circuit breaker to avoid hammering a dead server.

    Circuit breaker states:
        CLOSED     — normal operation, requests go through
        OPEN       — too many failures, reject immediately for reset_s seconds
        HALF_OPEN  — after reset_s, allow ONE probe request
    """

    def __init__(
        self,
        base_url: str,
        access_token: str,
        timeout_s: float = 5.0,
        cb_threshold: int = 5,
        cb_reset_s: float = 30.0,
        pool_size: int = 10,
    ) -> None:
        if not _AIOHTTP_AVAILABLE:
            raise RuntimeError(
                "aiohttp is required for HTTP transport. "
                "Install: pip install aiohttp"
            )

        self._api_base = f"{base_url}/api/v1/{access_token}"
        self._timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._pool_size = pool_size

        # Circuit breaker state
        self._cb_threshold = cb_threshold
        self._cb_reset_s = cb_reset_s
        self._consecutive_failures: int = 0
        self._cb_open_since: float = 0.0
        self._cb_state: str = "closed"  # closed | open | half_open

        # Session (lazy init)
        self._session: Optional[aiohttp.ClientSession] = None
        self._healthy: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> bool:
        """Create session and verify connectivity."""
        connector = aiohttp.TCPConnector(
            limit=self._pool_size,
            enable_cleanup_closed=True,
        )
        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            connector=connector,
        )

        # Warm-up probe
        ok = await self.post_telemetry({"_http_probe": "startup"})
        self._healthy = ok
        if ok:
            logger.info(f"TBHttpClient connected → {self._api_base}")
        else:
            logger.warning(
                f"TBHttpClient: startup probe failed → {self._api_base} "
                f"(will retry on next publish)"
            )
        return ok

    async def stop(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        logger.info("TBHttpClient stopped")

    # ── Public API ────────────────────────────────────────────────────────

    async def post_telemetry(
        self, payload: Dict[str, Any]
    ) -> bool:
        """POST single telemetry payload."""
        return await self._post(f"{self._api_base}/telemetry", payload)

    async def post_telemetry_batch(
        self, payloads: List[Dict[str, Any]]
    ) -> bool:
        """
        POST batch of telemetry payloads.

        ThingsBoard accepts array of objects for batch telemetry.
        """
        if not payloads:
            return True
        if len(payloads) == 1:
            return await self._post(f"{self._api_base}/telemetry", payloads[0])
        # TB accepts array for batch
        return await self._post(f"{self._api_base}/telemetry", payloads)

    async def post_attributes(self, attrs: Dict[str, Any]) -> bool:
        """POST client attributes."""
        return await self._post(f"{self._api_base}/attributes", attrs)

    async def get_attributes(self, keys: str) -> Optional[Dict[str, Any]]:
        """GET shared attributes. keys = comma-separated string."""
        return await self._get(
            f"{self._api_base}/attributes?sharedKeys={keys}"
        )

    # ── Internal HTTP ─────────────────────────────────────────────────────

    async def _post(self, url: str, payload: Any) -> bool:
        """Execute HTTP POST with circuit breaker + exponential backoff retry.

        Retry strategy: max 3 attempts, delay 1s → 2s → 4s.
        Only retries on transient failures (timeout, connection error).
        HTTP 4xx errors are NOT retried.
        """
        max_retries = 3
        base_delay = 1.0  # seconds

        for attempt in range(max_retries):
            # Circuit breaker check
            if not self._check_circuit_breaker():
                return False

            if self._session is None or self._session.closed:
                await self._ensure_session()

            try:
                async with self._session.post(url, json=payload) as resp:
                    if resp.status in (200, 201):
                        self._on_success()
                        return True
                    elif 400 <= resp.status < 500:
                        # Client error — do NOT retry
                        body = await resp.text()
                        self._on_failure(f"HTTP {resp.status}: {body[:200]}")
                        logger.error(
                            f"TB HTTP POST [{resp.status}] {url} → {body[:200]}"
                        )
                        return False
                    else:
                        # Server error — retry
                        body = await resp.text()
                        logger.warning(
                            f"TB HTTP POST [{resp.status}] {url} → {body[:200]} "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )

            except asyncio.TimeoutError:
                logger.warning(
                    f"TB HTTP timeout: {url} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
            except aiohttp.ClientConnectorError as exc:
                logger.warning(
                    f"TB HTTP connection error: {exc} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )
            except Exception as exc:
                logger.error(
                    f"TB HTTP error: {exc} "
                    f"(attempt {attempt + 1}/{max_retries})"
                )

            # Wait before retry (exponential backoff: 1s, 2s, 4s)
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        # All retries exhausted
        self._on_failure(f"All {max_retries} attempts failed for {url}")
        logger.error(f"TB HTTP POST failed after {max_retries} retries: {url}")
        return False

    async def _get(self, url: str) -> Optional[Dict[str, Any]]:
        """Execute HTTP GET with circuit breaker protection."""
        if not self._check_circuit_breaker():
            return None

        if self._session is None or self._session.closed:
            await self._ensure_session()

        try:
            async with self._session.get(url) as resp:
                if resp.status == 200:
                    self._on_success()
                    return await resp.json()
                else:
                    self._on_failure(f"HTTP {resp.status}")
                    return None
        except Exception as exc:
            self._on_failure(str(exc))
            return None

    async def _ensure_session(self) -> None:
        """Lazily create session if needed."""
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                limit=self._pool_size,
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                connector=connector,
            )

    # ── Circuit breaker ───────────────────────────────────────────────────

    def _check_circuit_breaker(self) -> bool:
        """Returns True if request is allowed, False if circuit is open."""
        if self._cb_state == "closed":
            return True

        if self._cb_state == "open":
            elapsed = time.monotonic() - self._cb_open_since
            if elapsed >= self._cb_reset_s:
                self._cb_state = "half_open"
                logger.info("Circuit breaker → HALF_OPEN (allowing probe)")
                return True
            return False

        # half_open — allow the probe
        return True

    def _on_success(self) -> None:
        """Reset circuit breaker on success."""
        if self._cb_state != "closed":
            logger.info("Circuit breaker → CLOSED (success)")
        self._consecutive_failures = 0
        self._cb_state = "closed"
        self._healthy = True

    def _on_failure(self, error: str) -> None:
        """Track failure and potentially open circuit breaker."""
        self._consecutive_failures += 1
        self._healthy = False

        if self._cb_state == "half_open":
            # Probe failed — back to open
            self._cb_state = "open"
            self._cb_open_since = time.monotonic()
            logger.warning(
                f"Circuit breaker → OPEN (probe failed: {error})"
            )
            return

        if self._consecutive_failures >= self._cb_threshold:
            if self._cb_state != "open":
                self._cb_state = "open"
                self._cb_open_since = time.monotonic()
                logger.error(
                    f"Circuit breaker → OPEN "
                    f"({self._consecutive_failures} consecutive failures)"
                )

    # ── Status ────────────────────────────────────────────────────────────

    def is_healthy(self) -> bool:
        return self._healthy and self._cb_state != "open"

    @property
    def circuit_breaker_state(self) -> str:
        return self._cb_state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
