"""
Tests for invalid sensor inputs.
"""
import pytest
from models.input_snapshot import InputSnapshot

def test_vision_id_clamped():
    from drivers.input_reader import InputReader
    from unittest.mock import MagicMock
    
    modbus = MagicMock()
    reader = InputReader(modbus)
    
    # 0 is valid (no product)
    snap = InputSnapshot(vision_id=0, scan_timestamp=0, at_exit=False, start_button=False, stop_button=False, estop=False, auto_mode=False, manual_mode=False)
    assert not reader.get_vision_edge_triggered(snap)
    
    # Simulate valid product
    snap2 = InputSnapshot(vision_id=3, scan_timestamp=0, at_exit=False, start_button=False, stop_button=False, estop=False, auto_mode=False, manual_mode=False)
    assert reader.get_vision_edge_triggered(snap2)
    
    # Reset edge
    reader.previous_vision_id = 3
    
    # Simulate same product holding
    snap3 = InputSnapshot(vision_id=3, scan_timestamp=0, at_exit=False, start_button=False, stop_button=False, estop=False, auto_mode=False, manual_mode=False)
    assert not reader.get_vision_edge_triggered(snap3)
