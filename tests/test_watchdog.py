"""
Tests for watchdog.
"""
import pytest
import time
from control.watchdog import Watchdog

@pytest.mark.asyncio
async def test_watchdog_heartbeat():
    wd = Watchdog()
    wd.register("test", timeout_sec=0.1)
    
    # Give heartbeat
    wd.heartbeat("test")
    failed = await wd.check_all()
    assert len(failed) == 0
    
    # Wait for timeout
    time.sleep(0.15)
    failed = await wd.check_all()
    assert "test" in failed
