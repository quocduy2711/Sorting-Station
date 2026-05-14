"""
Tests for Modbus reconnect logic.
"""
import pytest
from unittest.mock import AsyncMock, patch
from drivers.modbus_client import ModbusClient

@pytest.mark.asyncio
async def test_modbus_reconnect(mock_config):
    client = ModbusClient(mock_config.modbus, mock_config.reconnect)
    client.connect = AsyncMock(side_effect=[False, True])
    
    await client.start_reconnect_loop()
    
    assert client.connect.call_count == 2
    assert client.reconnect_count == 1
