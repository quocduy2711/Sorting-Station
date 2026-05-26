"""
HealthReporter — port for periodic health/heartbeat reporting.

Runs as a background task, publishes system health status
at configurable intervals (default 30s).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class HealthReporter(ABC):
    """Port for periodic health reporting to cloud platform."""

    @abstractmethod
    async def report_health(self, status: Dict[str, Any]) -> bool:
        """Publish a health status snapshot. Returns True on success."""

    @abstractmethod
    async def start(self, interval_s: float = 30.0) -> None:
        """Start periodic heartbeat loop as background task."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop heartbeat loop and clean up."""
