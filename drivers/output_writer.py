"""
Output writer for Modbus coil writes and holding register writes.

RULE: Only modifies OutputState buffer, never writes directly.
RULE: Shadow state comparison to reduce Modbus traffic.
RULE: output_writer.flush() is the ONLY place that writes coils.
RULE: Counter registers are written immediately on update.
"""
import logging
from typing import Dict
from models.output_state import OutputState
from .modbus_client import ModbusClient


logger = logging.getLogger(__name__)


class OutputWriter:
    """
    Manages all Modbus coil writes through OutputState buffer.
    Also handles holding register writes for counter values.
    
    Features:
    - Shadow state comparison (only write if changed)
    - Centralized output control
    - Reduced Modbus traffic
    - Counter register writes
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

    # Modbus holding register addresses for counters
    # Adjust these addresses based on your Factory IO configuration
    REGISTER_MAP: Dict[str, int] = {
        "remover1_count": 100,  # Holding register 100
        "remover2_count": 101,  # Holding register 101
        "remover3_count": 102,  # Holding register 102
    }

    def __init__(self, modbus: ModbusClient, output_state: OutputState):
        """Initialize output writer."""
        self.modbus = modbus
        self.output_state = output_state
        self.write_count = 0
        self.skip_count = 0  # Coils skipped due to shadow match
        self._last_counter_values: Dict[str, int] = {
            "remover1_count": -1,
            "remover2_count": -1,
            "remover3_count": -1,
        }

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

    async def write_counter(self, remover_id: int, count: int) -> bool:
        """
        Write a single remover counter to Modbus holding register.

        Args:
            remover_id: Remover ID (1, 2, or 3)
            count: Counter value to write

        Returns:
            True if successful.
        """
        if remover_id not in (1, 2, 3):
            logger.error(f"Invalid remover_id: {remover_id}")
            return False

        reg_name = f"remover{remover_id}_count"
        
        if reg_name not in self.REGISTER_MAP:
            logger.warning(f"No register mapping for {reg_name}")
            return False

        address = self.REGISTER_MAP[reg_name]
        
        # Only write if value changed (shadow comparison)
        if self._last_counter_values.get(reg_name) == count:
            return True  # Skip write, value unchanged

        success = await self.modbus.write_register(address, count, retries=1)

        if success:
            logger.debug(f"Wrote counter register {reg_name} (addr {address}) = {count}")
            self._last_counter_values[reg_name] = count
            self.write_count += 1
        else:
            logger.error(f"Failed to write counter register {reg_name}")

        return success

    async def write_all_counters(self, counter_dict: Dict[int, int]) -> bool:
        """
        Write all remover counters to Modbus holding registers.

        Args:
            counter_dict: Dictionary mapping remover_id (1,2,3) to counts

        Returns:
            True if all writes successful.
        """
        all_success = True

        for remover_id in (1, 2, 3):
            count = counter_dict.get(remover_id, 0)
            success = await self.write_counter(remover_id, count)
            if not success:
                all_success = False

        return all_success

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
