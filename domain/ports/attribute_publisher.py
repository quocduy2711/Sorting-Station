"""
AttributePublisher — port for publishing device attributes to cloud.

Attributes are low-frequency, high-importance data:
    - Client attributes: device info, firmware version, station ID
    - Shared attributes: runtime config from dashboard (read-only on device)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List


class AttributePublisher(ABC):
    """Port for device attribute sync with cloud platform."""

    @abstractmethod
    async def publish_client_attributes(self, attrs: Dict[str, Any]) -> bool:
        """Publish static device info. Called on connect and state change."""

    @abstractmethod
    async def request_shared_attributes(self, keys: List[str]) -> None:
        """Request runtime config values from cloud server."""

    @abstractmethod
    def set_shared_attribute_callback(
        self, callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Register callback for shared attribute updates from server."""

    @abstractmethod
    async def start(self) -> bool:
        """Initialize transport. Returns success."""

    @abstractmethod
    async def stop(self) -> None:
        """Shutdown transport."""
