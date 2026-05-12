"""
Central output buffer for all Modbus coil writes.

RULE: NO module writes Modbus directly.
RULE: All modules modify this buffer only.
RULE: Only output_writer.flush() writes to Modbus.
RULE: Only state machine owns outputs.
"""
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class OutputState:
    """
    Central shadow buffer for all output coils.
    
    This is the ONLY place where outputs are modified.
    output_writer.flush() is the ONLY function that writes to Modbus.
    """
    # Conveyors
    emitter: bool = False
    entry_conveyor: bool = False
    exit_conveyor: bool = False
    
    # Stop blade
    stop_blade: bool = True  # Initial state: UP
    
    # Sorter 1
    sorter1_belt: bool = False
    sorter1_turn: bool = False
    
    # Sorter 2
    sorter2_belt: bool = False
    sorter2_turn: bool = False
    
    # Sorter 3
    sorter3_belt: bool = False
    sorter3_turn: bool = False
    
    # Removers
    remover1: bool = False
    remover2: bool = False
    remover3: bool = False
    
    # Indicator lights
    start_light: bool = False
    stop_light: bool = False
    reset_light: bool = False
    
    # Previous state for shadow comparison
    _previous_state: Dict[str, bool] = field(default_factory=dict)

    def get_coil_dict(self) -> Dict[str, bool]:
        """Get all coils as dictionary for Modbus writes."""
        return {
            "emitter": self.emitter,
            "entry_conveyor": self.entry_conveyor,
            "exit_conveyor": self.exit_conveyor,
            "stop_blade": self.stop_blade,
            "sorter1_belt": self.sorter1_belt,
            "sorter1_turn": self.sorter1_turn,
            "sorter2_belt": self.sorter2_belt,
            "sorter2_turn": self.sorter2_turn,
            "sorter3_belt": self.sorter3_belt,
            "sorter3_turn": self.sorter3_turn,
            "remover1": self.remover1,
            "remover2": self.remover2,
            "remover3": self.remover3,
            "start_light": self.start_light,
            "stop_light": self.stop_light,
            "reset_light": self.reset_light,
        }

    def get_changed_coils(self) -> Dict[str, bool]:
        """
        Get only the coils that changed since last call.
        
        Used for shadow state comparison to reduce Modbus traffic.
        """
        current = self.get_coil_dict()
        changed = {}
        
        for key, value in current.items():
            if self._previous_state.get(key) != value:
                changed[key] = value
                self._previous_state[key] = value
        
        return changed

    def reset_all(self) -> None:
        """Failsafe: Turn off all outputs except stop blade."""
        self.emitter = False
        self.entry_conveyor = False
        self.exit_conveyor = False
        self.stop_blade = True  # Blade UP for safety
        self.sorter1_belt = False
        self.sorter1_turn = False
        self.sorter2_belt = False
        self.sorter2_turn = False
        self.sorter3_belt = False
        self.sorter3_turn = False
        self.remover1 = False
        self.remover2 = False
        self.remover3 = False

    def __repr__(self) -> str:
        coils = self.get_coil_dict()
        active = [k for k, v in coils.items() if v]
        return f"OutputState(active={active})"
