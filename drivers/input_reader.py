"""
Input reader for Modbus discrete inputs and registers.

RULE: Only bulk reads per cycle.
RULE: Returns immutable InputSnapshot.
RULE: Edge-triggered for vision sensor (debounce).
"""
import logging
import time
from typing import Optional
from models.input_snapshot import InputSnapshot
from .modbus_client import ModbusClient


logger = logging.getLogger(__name__)


class InputReader:
    """
    Reads all input signals in bulk once per IO scan cycle.
    
    Produces immutable InputSnapshot for consumption by control logic.
    """

    # Modbus addresses (example mapping)
    ADDR_VISION_ID = 0  # Input register
    ADDR_DISCRETE_START = 0  # Discrete inputs start

    # Discrete input bit mapping
    IDX_AT_EXIT = 0
    IDX_START_BUTTON = 1
    IDX_STOP_BUTTON = 2
    IDX_ESTOP = 3
    IDX_AUTO_MODE = 4
    IDX_MANUAL_MODE = 5

    def __init__(self, modbus: ModbusClient):
        """Initialize input reader."""
        self.modbus = modbus
        self.previous_vision_id = 0
        self.vision_read_count = 0

    async def read_all_inputs(self) -> Optional[InputSnapshot]:
        """
        Read all inputs in bulk (single Modbus read cycle).
        
        Returns:
            InputSnapshot or None on error.
            
        RULE: NO per-input reads, only bulk.
        """
        scan_start = time.monotonic()

        # Read input registers (vision ID)
        registers = await self.modbus.read_input_registers(
            address=self.ADDR_VISION_ID,
            count=1
        )
        
        if registers is None:
            logger.warning("Failed to read input registers")
            return None

        vision_id = registers[0] if registers else 0

        # Read discrete inputs
        discrete = await self.modbus.read_discrete_inputs(
            address=self.ADDR_DISCRETE_START,
            count=6
        )
        
        if discrete is None:
            logger.warning("Failed to read discrete inputs")
            return None

        # Clamp vision_id to valid range
        vision_id = max(0, min(6, vision_id))

        # Build snapshot
        snapshot = InputSnapshot(
            vision_id=vision_id,
            at_exit=discrete[self.IDX_AT_EXIT] if len(discrete) > self.IDX_AT_EXIT else False,
            start_button=discrete[self.IDX_START_BUTTON] if len(discrete) > self.IDX_START_BUTTON else False,
            stop_button=discrete[self.IDX_STOP_BUTTON] if len(discrete) > self.IDX_STOP_BUTTON else False,
            estop=discrete[self.IDX_ESTOP] if len(discrete) > self.IDX_ESTOP else False,
            auto_mode=discrete[self.IDX_AUTO_MODE] if len(discrete) > self.IDX_AUTO_MODE else False,
            manual_mode=discrete[self.IDX_MANUAL_MODE] if len(discrete) > self.IDX_MANUAL_MODE else False,
            scan_timestamp=scan_start
        )

        # Track vision reads
        if vision_id > 0 and self.previous_vision_id == 0:
            # Edge trigger: vision just appeared
            self.vision_read_count += 1
        
        self.previous_vision_id = vision_id

        return snapshot

    def get_vision_edge_triggered(self, current_snapshot: InputSnapshot) -> bool:
        """
        Detect edge-triggered vision sensor reading.
        
        RULE: Only react to 0->X transition, not continuous high.
        
        Returns:
            True if new vision reading detected (0->X edge).
        """
        return (current_snapshot.vision_id > 0 and 
                self.previous_vision_id == 0)

    def reset_vision_edge(self) -> None:
        """Reset vision edge detection."""
        self.previous_vision_id = 0
