"""
RpcListener — port for receiving real-time RPC commands from cloud.

Implemented by MQTT adapter. MQTT is the ONLY transport for RPC
because commands need sub-100ms push latency.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict


class RpcListener(ABC):
    """
    Port for real-time RPC command reception.

    The infrastructure adapter (MQTT) handles:
        - Connection lifecycle & auto-reconnect
        - Message parsing (JSON → dict)
        - Command routing to registered handlers
        - Response publishing back to cloud

    Lifecycle:
        start() → ... → stop()
    """

    @abstractmethod
    async def start(self) -> bool:
        """Connect and begin listening. Returns True if connected."""

    @abstractmethod
    async def stop(self) -> None:
        """Disconnect and stop listening."""

    @abstractmethod
    def register_command_handler(
        self, method: str, handler: Callable[..., Any]
    ) -> None:
        """
        Register a handler for a specific RPC method name.

        Args:
            method:  RPC method string (e.g. 'start_machine', 'ping')
            handler: Callable(request_id: str, params: dict) -> dict
                     Return value is sent as RPC response.
        """

    @abstractmethod
    async def send_response(
        self, request_id: str, response: Dict[str, Any]
    ) -> bool:
        """Send RPC response for a specific request_id."""

    @abstractmethod
    def is_connected(self) -> bool:
        """True if MQTT is connected and subscribed to RPC topic."""
