"""
Tests for ConveyorErrorDetector.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from control.conveyor_error_detector import ConveyorErrorDetector, ErrorCode
from control.event_manager import EventManager, SystemEvent
from models.system_state import SystemState, SystemStateEnum


@pytest.fixture
def system_state():
    state = SystemState()
    state.set_state(SystemStateEnum.RUNNING)
    return state


@pytest.fixture
def event_manager():
    return EventManager()


@pytest.fixture
def mock_http():
    client = AsyncMock()
    client.post_telemetry = AsyncMock(return_value=True)
    return client


@pytest.fixture
def detector(system_state, event_manager, mock_http):
    return ConveyorErrorDetector(
        system_state=system_state,
        event_manager=event_manager,
        http_client=mock_http,
        jam_timeout_ms=5000.0,
        vision_stall_timeout_ms=3000.0,
        sudden_stop_debounce_ms=500.0,
    )


class TestCheckSuddenStop:
    """Test sudden stop detection: motor OFF while state is RUNNING."""

    @pytest.mark.asyncio
    async def test_no_trigger_when_motor_running(self, detector):
        """Motor ON → no error."""
        result = await detector.check_sudden_stop(motor_running=True)
        assert result is False

    @pytest.mark.asyncio
    async def test_no_trigger_when_not_running_state(self, detector, system_state):
        """State is IDLE → motor OFF is fine."""
        system_state.set_state(SystemStateEnum.IDLE)
        result = await detector.check_sudden_stop(motor_running=False)
        assert result is False

    @pytest.mark.asyncio
    async def test_trigger_after_debounce(self, detector, system_state, mock_http):
        """Motor OFF while RUNNING for > debounce_ms → trigger."""
        # First call starts tracking
        await detector.check_sudden_stop(motor_running=False)

        # Simulate time passing: _motor_off_since is in ms (monotonic * 1000)
        # Subtract 1000ms to exceed 500ms debounce threshold
        detector._motor_off_since -= 1000.0

        result = await detector.check_sudden_stop(motor_running=False)
        assert result is True
        assert system_state.last_error is not None
        assert ErrorCode.SUDDEN_STOP in system_state.last_error
        mock_http.post_telemetry.assert_called_once()


class TestCheckJam:
    """Test jam detection: product stationary too long."""

    @pytest.mark.asyncio
    async def test_no_trigger_within_timeout(self, detector):
        """Product stationary < timeout → no error."""
        result = await detector.check_jam(product_position_unchanged_ms=3000.0)
        assert result is False

    @pytest.mark.asyncio
    async def test_trigger_on_jam(self, detector, system_state, mock_http):
        """Product stationary > timeout → trigger jam error."""
        result = await detector.check_jam(product_position_unchanged_ms=6000.0)
        assert result is True
        assert ErrorCode.JAM_DETECTED in system_state.last_error
        mock_http.post_telemetry.assert_called_once()


class TestCheckVisionStall:
    """Test vision stall: vision read but no movement."""

    @pytest.mark.asyncio
    async def test_no_trigger_when_no_product(self, detector):
        """Vision ID = 0 → no product → no error."""
        result = await detector.check_vision_stall(
            vision_product_id=0,
            time_since_vision_read_ms=5000.0,
            product_moved=False,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_no_trigger_when_product_moved(self, detector):
        """Product moved → no error."""
        result = await detector.check_vision_stall(
            vision_product_id=3,
            time_since_vision_read_ms=5000.0,
            product_moved=True,
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_trigger_on_stall(self, detector, system_state, mock_http):
        """Vision read + no movement + timeout exceeded → stall error."""
        result = await detector.check_vision_stall(
            vision_product_id=3,
            time_since_vision_read_ms=4000.0,
            product_moved=False,
        )
        assert result is True
        assert ErrorCode.VISION_STALL in system_state.last_error
        mock_http.post_telemetry.assert_called_once()


class TestTriggerEmergency:
    """Test emergency trigger: state update + event emit + HTTP publish."""

    @pytest.mark.asyncio
    async def test_updates_system_state(self, detector, system_state):
        """Emergency sets last_error on system state."""
        await detector.trigger_emergency("TEST_ERROR", "test detail")
        assert system_state.last_error == "TEST_ERROR: test detail"
        assert system_state.last_error_time is not None

    @pytest.mark.asyncio
    async def test_emits_event(self, detector, event_manager):
        """Emergency emits EMERGENCY_STOP_DETECTED event."""
        received = []
        event_manager.subscribe(
            SystemEvent.EMERGENCY_STOP_DETECTED,
            lambda e: received.append(e),
        )
        # Start dispatch loop
        import asyncio
        dispatch_task = asyncio.create_task(event_manager.dispatch_loop())

        await detector.trigger_emergency("TEST_ERROR", "test detail")
        await asyncio.sleep(0.1)  # Let dispatch process

        dispatch_task.cancel()
        try:
            await dispatch_task
        except asyncio.CancelledError:
            pass

        assert len(received) == 1
        assert received[0].data["error_code"] == "TEST_ERROR"

    @pytest.mark.asyncio
    async def test_publishes_http_telemetry(self, detector, mock_http):
        """Emergency publishes error telemetry via HTTP."""
        await detector.trigger_emergency("TEST_ERROR", "test detail")
        mock_http.post_telemetry.assert_called_once()
        payload = mock_http.post_telemetry.call_args[0][0]
        assert payload["error_code"] == "TEST_ERROR"
        assert payload["emergency_active"] is True
