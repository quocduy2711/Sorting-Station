"""
MachineCommand — typed RPC command model.

Flow: TB RPC → TBRpcHandler → MachineCommand → EventManager.emit() → FSM

RULE: RPC handler creates MachineCommand.
RULE: FSM/services receive this via EventManager — never from RPC directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict


class CommandType(Enum):
    """All supported RPC methods."""
    START_MACHINE   = "start_machine"
    STOP_MACHINE    = "stop_machine"
    RESET_ALARM     = "reset_alarm"
    EMERGENCY_STOP  = "emergency_stop"
    SET_SPEED       = "set_speed"
    SET_MODE        = "set_mode"
    PING            = "ping"
    UNKNOWN         = "unknown"

    @classmethod
    def from_str(cls, method: str) -> "CommandType":
        """Parse method string, returns UNKNOWN for unrecognized values."""
        for member in cls:
            if member.value == method:
                return member
        return cls.UNKNOWN


@dataclass
class MachineCommand:
    """
    Typed RPC command.

    Attributes:
        command_type: Parsed command type enum
        request_id:   TB RPC request ID (for response routing)
        params:       Raw params dict from RPC payload
        source:       Origin — "rpc" | "api" | "schedule"
    """
    command_type: CommandType
    request_id: str
    params: Dict[str, Any] = field(default_factory=dict)
    source: str = "rpc"
