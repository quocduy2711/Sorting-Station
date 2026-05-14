"""
System-level state machine.

RULE: Only state machine owns outputs.
RULE: Other modules calculate/validate but don't control outputs.
"""
import logging
from models.system_state import SystemStateEnum, SystemState
from models.output_state import OutputState


logger = logging.getLogger(__name__)


class StateMachine:
    """
    Main finite state machine for system control.
    
    RULE: This is the ONLY module that directly controls OutputState.
    
    Other modules can:
    - Emit events
    - Calculate logic
    - Validate conditions
    
    But only FSM sets outputs.
    """

    def __init__(self, system_state: SystemState, output_state: OutputState):
        """Initialize state machine."""
        self.system_state = system_state
        self.output_state = output_state

    def register_handlers(self, em: 'EventManager') -> None:
        """Register to listen to system events."""
        self._em = em
        from control.event_manager import SystemEvent
        em.subscribe(SystemEvent.START_BUTTON_PRESSED, self._on_start)
        em.subscribe(SystemEvent.STOP_BUTTON_PRESSED, self._on_stop)
        em.subscribe(SystemEvent.ESTOP_ACTIVATED, self._on_estop)
        em.subscribe(SystemEvent.ESTOP_CLEARED, self._on_estop_clear)
        em.subscribe(SystemEvent.SORT_COMMAND, self._on_sort_command)

    async def _on_start(self, event):
        if self.system_state.state in (SystemStateEnum.IDLE, SystemStateEnum.STOPPED):
            await self.transition_to(SystemStateEnum.STARTING)
            import asyncio
            # Wait 500ms for conveyors to spin up before fully running
            asyncio.create_task(self._delayed_run())

    async def _delayed_run(self):
        import asyncio
        await asyncio.sleep(0.5)
        if self.system_state.state == SystemStateEnum.STARTING:
            await self.transition_to(SystemStateEnum.RUNNING)

    async def _on_stop(self, event):
        if self.system_state.state not in (SystemStateEnum.EMERGENCY_STOP, SystemStateEnum.ERROR):
            await self.transition_to(SystemStateEnum.STOPPED)

    async def _on_estop(self, event):
        await self.transition_to(SystemStateEnum.EMERGENCY_STOP)

    async def _on_estop_clear(self, event):
        if self.system_state.state == SystemStateEnum.EMERGENCY_STOP:
            await self.transition_to(SystemStateEnum.STOPPED)

    async def _on_sort_command(self, event):
        sorter_id = event.data.get("sorter_id")
        if sorter_id:
            import asyncio
            asyncio.create_task(self._sort_sequence(sorter_id))

    async def _sort_sequence(self, sorter_id: int):
        import asyncio
        logger.info(f"FSM: Starting sort sequence for sorter {sorter_id}")
        
        # Lower blade
        await self.lower_blade()
        await self.activate_sorter(sorter_id)
        
        # Let product pass the blade
        await asyncio.sleep(1.5)
        
        # Raise blade
        await self.raise_blade()
        
        # Let product reach and clear the sorter
        await asyncio.sleep(4.0)
        
        # Turn off sorter
        await self.deactivate_sorter(sorter_id)
        
        # Notify sorting done
        from control.event_manager import SystemEvent
        if hasattr(self, '_em'):
            self._em.emit(SystemEvent.PRODUCT_SORT_DONE, source="StateMachine")

    async def transition_to(self, new_state: SystemStateEnum) -> None:
        """
        Transition to a new system state.
        
        Updates output configuration based on new state.
        
        Args:
            new_state: Target state
        """
        old_state = self.system_state.state
        
        if old_state == new_state:
            return  # No change
        
        logger.info(f"State transition: {old_state.value} -> {new_state.value}")
        self.system_state.set_state(new_state)
        
        # Update outputs based on new state
        await self._configure_outputs_for_state(new_state)

    async def _configure_outputs_for_state(self, state: SystemStateEnum) -> None:
        """
        Configure outputs appropriate for the given state.
        
        RULE: Output configuration centralized here.
        """
        if state == SystemStateEnum.IDLE:
            # All off except stop blade
            self.output_state.emitter = False
            self.output_state.entry_conveyor = False
            self.output_state.exit_conveyor = False
            self.output_state.stop_blade = True
            self._disable_all_sorters()

        elif state == SystemStateEnum.STARTING:
            # Initialize conveyors
            self.output_state.entry_conveyor = True
            self.output_state.exit_conveyor = True
            self.output_state.stop_blade = True

        elif state == SystemStateEnum.RUNNING:
            # Conveyors running
            self.output_state.entry_conveyor = True
            self.output_state.exit_conveyor = True
            self.output_state.emitter = False  # Will pulse separately

        elif state == SystemStateEnum.WAITING_CLEAR_ZONE:
            # Blade is up, conveyors stopped
            self.output_state.entry_conveyor = False
            self.output_state.exit_conveyor = False
            self.output_state.stop_blade = True

        elif state == SystemStateEnum.READING_ID:
            # Hold product at blade, exit conveyor ready
            self.output_state.entry_conveyor = False
            self.output_state.exit_conveyor = True
            self.output_state.stop_blade = True

        elif state == SystemStateEnum.MOVING_TO_SORTER:
            # Both conveyors running
            self.output_state.entry_conveyor = True
            self.output_state.exit_conveyor = True

        elif state == SystemStateEnum.SORTING:
            # Sorter active (controls its own outputs)
            self.output_state.entry_conveyor = False
            self.output_state.exit_conveyor = False

        elif state == SystemStateEnum.STOPPED or state == SystemStateEnum.ERROR:
            # Safe state
            self.output_state.entry_conveyor = False
            self.output_state.exit_conveyor = False
            self.output_state.stop_blade = True
            self._disable_all_sorters()

        elif state == SystemStateEnum.EMERGENCY_STOP:
            # CRITICAL: Failsafe
            self.output_state.reset_all()

    def _disable_all_sorters(self) -> None:
        """Turn off all sorter outputs."""
        self.output_state.sorter1_belt = False
        self.output_state.sorter1_turn = False
        self.output_state.sorter2_belt = False
        self.output_state.sorter2_turn = False
        self.output_state.sorter3_belt = False
        self.output_state.sorter3_turn = False
        self.output_state.remover1 = False
        self.output_state.remover2 = False
        self.output_state.remover3 = False

    async def activate_sorter(self, sorter_id: int) -> None:
        """
        Activate a specific sorter.
        
        Args:
            sorter_id: Sorter number (1, 2, or 3)
        """
        logger.info(f"Activating sorter {sorter_id}")
        
        if sorter_id == 1:
            self.output_state.sorter1_belt = True
            self.output_state.sorter1_turn = True
        elif sorter_id == 2:
            self.output_state.sorter2_belt = True
            self.output_state.sorter2_turn = True
        elif sorter_id == 3:
            self.output_state.sorter3_belt = True
            self.output_state.sorter3_turn = True

    async def deactivate_sorter(self, sorter_id: int) -> None:
        """
        Deactivate a specific sorter.
        
        Args:
            sorter_id: Sorter number (1, 2, or 3)
        """
        logger.info(f"Deactivating sorter {sorter_id}")
        
        if sorter_id == 1:
            self.output_state.sorter1_belt = False
            self.output_state.sorter1_turn = False
        elif sorter_id == 2:
            self.output_state.sorter2_belt = False
            self.output_state.sorter2_turn = False
        elif sorter_id == 3:
            self.output_state.sorter3_belt = False
            self.output_state.sorter3_turn = False

    async def raise_blade(self) -> None:
        """Raise stop blade."""
        self.output_state.stop_blade = True
        logger.debug("Blade raised")

    async def lower_blade(self) -> None:
        """Lower stop blade."""
        self.output_state.stop_blade = False
        logger.debug("Blade lowered")

    async def pulse_emitter(self, pulse_duration_ms: int) -> None:
        """
        Pulse emitter for product creation.
        
        RULE: Emitter must pulse, not stay on.
        
        Args:
            pulse_duration_ms: Duration in milliseconds
        """
        import asyncio
        
        logger.debug(f"Emitter pulse for {pulse_duration_ms}ms")
        self.output_state.emitter = True
        
        await asyncio.sleep(pulse_duration_ms / 1000.0)
        
        self.output_state.emitter = False

    def get_current_state(self) -> SystemStateEnum:
        """Get current system state."""
        return self.system_state.state

    def is_running(self) -> bool:
        """Check if system is in running state."""
        return self.system_state.state == SystemStateEnum.RUNNING

    def is_emergency_stop(self) -> bool:
        """Check if in emergency stop."""
        return self.system_state.state == SystemStateEnum.EMERGENCY_STOP

    def is_error(self) -> bool:
        """Check if in error state."""
        return self.system_state.state == SystemStateEnum.ERROR
