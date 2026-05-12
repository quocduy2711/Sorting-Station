"""
Immutable input snapshot from Modbus scan.

RULE: Only bulk reads, never individual reads.
RULE: Returns immutable snapshot per cycle.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class InputSnapshot:
    """
    Immutable snapshot of all input signals from a single Modbus scan.
    
    This is read-only and captured once per IO scan cycle (50ms).
    """
    # Input Registers
    vision_id: int  # 0-6, current vision sensor reading
    
    # Discrete Inputs
    at_exit: bool  # Product at exit sensor
    start_button: bool  # Start button pressed
    stop_button: bool  # Stop button pressed
    estop: bool  # Emergency stop activated
    auto_mode: bool  # Auto mode enabled
    manual_mode: bool  # Manual mode enabled
    
    # Metadata
    scan_timestamp: float = 0.0  # monotonic timestamp of scan
    
    def __repr__(self) -> str:
        return (f"InputSnapshot(vision_id={self.vision_id}, at_exit={self.at_exit}, "
                f"estop={self.estop}, auto_mode={self.auto_mode}, "
                f"start={self.start_button}, stop={self.stop_button})")
