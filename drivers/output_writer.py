"""
Output writer for Modbus coil writes.

RULE: Only modifies OutputState buffer, never writes directly.
RULE: Shadow state comparison to reduce Modbus traffic.
RULE: output_writer.flush() is the ONLY place that writes coils.
"""
import logging
from typing import Dict
from models.output_state import OutputState
from .modbus_client import ModbusClient


logger = logging.getLogger(__name__)


class OutputWriter:
    """
    Manages all Modbus coil writes through OutputState buffer.
    
    Features:
    - Shadow state comparison (only write if changed)
    - Centralized output control
    - Reduced Modbus traffic
    """

    # Modbus coil addresses (example mapping)
    COIL_MAP: Dict[str, int] = {
        "emitter": 0,
        "entry_conveyor": 1,
        "exit_conveyor": 2,
        "stop_blade": 3,
        "sorter1_belt": 4,
        "sorter1_turn": 5,
        "sorter2_belt": 6,
        "sorter2_turn": 7,
        "sorter3_belt": 8,
        "sorter3_turn": 9,
        "remover1": 10,
        "remover2": 11,
        "remover3": 12,
        "start_light": 13,
        "stop_light": 14,
        "reset_light": 15,
    }

    def __init__(self, modbus: ModbusClient, output_state: OutputState):
        """Initialize output writer."""
        self.modbus = modbus
        self.output_state = output_state
        self.write_count = 0
        self.skip_count = 0  # Coils skipped due to shadow match

    async def flush(self) -> bool:
        """
        Write changed coils to Modbus.
        
        RULE: This is the ONLY place where Modbus coils are written.
        
        Uses shadow state comparison to only write changed coils.
        
        Returns:
            True if all writes successful.
        """
        # Get only changed coils
        changed_coils = self.output_state.get_changed_coils()

        if not changed_coils:
            self.skip_count += 1
            return True

        all_success = True

        # Write each changed coil
        for coil_name, value in changed_coils.items():
            if coil_name not in self.COIL_MAP:
                logger.warning(f"Unknown coil name: {coil_name}")
                continue

            address = self.COIL_MAP[coil_name]
            success = await self.modbus.write_coil(address, value, retries=1)

            if success:
                logger.debug(f"Wrote coil {coil_name} (addr {address}) = {value}")
                self.write_count += 1
            else:
                logger.error(f"Failed to write coil {coil_name} (addr {address})")
                all_success = False

        return all_success

    async def write_all_coils(self) -> bool:
        """
        Force write ALL coils regardless of shadow state.
        
        Used for initialization or resync after errors.
        
        Returns:
            True if successful.
        """
        coil_dict = self.output_state.get_coil_dict()
        all_success = True

        for coil_name, value in coil_dict.items():
            if coil_name not in self.COIL_MAP:
                continue

            address = self.COIL_MAP[coil_name]
            success = await self.modbus.write_coil(address, value, retries=1)

            if not success:
                logger.error(f"Failed to write coil {coil_name}")
                all_success = False

        return all_success

    async def failsafe_shutdown(self) -> None:
        """
        Emergency shutdown: turn off all outputs except stop blade.
        
        RULE: Called on critical error.
        """
        logger.critical("FAILSAFE SHUTDOWN ACTIVATED")
        
        self.output_state.reset_all()
        
        # Force write
        await self.write_all_coils()

    def get_write_count(self) -> int:
        """Get total coils written."""
        return self.write_count

    def get_skip_count(self) -> int:
        """Get coils skipped due to shadow match."""
        return self.skip_count

    def reset_counters(self) -> None:
        """Reset write/skip counters."""
        self.write_count = 0
        self.skip_count = 0
