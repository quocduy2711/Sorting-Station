"""
Tests for state machine.
"""
import pytest
from models.system_state import SystemStateEnum
from control.state_machine import StateMachine

@pytest.mark.asyncio
async def test_idle_to_starting(system_state, output_state):
    fsm = StateMachine(system_state, output_state)
    await fsm.transition_to(SystemStateEnum.IDLE)
    assert output_state.stop_blade == True
    assert output_state.entry_conveyor == False
    
    await fsm.transition_to(SystemStateEnum.STARTING)
    assert output_state.entry_conveyor == True
    assert output_state.exit_conveyor == True
    assert output_state.stop_blade == True

@pytest.mark.asyncio
async def test_emergency_stop_resets_outputs(system_state, output_state):
    fsm = StateMachine(system_state, output_state)
    await fsm.transition_to(SystemStateEnum.RUNNING)
    assert output_state.entry_conveyor == True
    
    await fsm.transition_to(SystemStateEnum.EMERGENCY_STOP)
    assert output_state.entry_conveyor == False
    assert output_state.exit_conveyor == False
    assert output_state.stop_blade == True
