"""
Shared pytest fixtures for the sorting station tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from models.system_state import SystemState
from models.output_state import OutputState
from config.app_config import AppConfig, ModbusConfig, MQTTConfig, TimingConfig, TimeoutConfig, ReconnectConfig, LoggingConfig

@pytest.fixture
def mock_config():
    return AppConfig(
        modbus=ModbusConfig(host="127.0.0.1", port=502, timeout=2.0, unit_id=1, max_retries=3),
        mqtt=MQTTConfig(host="127.0.0.1", port=1883, username="", password="", access_token="", ca_certs="", clean_session=True),
        timing=TimingConfig(io_scan_ms=50, sorter_tick_ms=35, supervision_ms=100, telemetry_ms=150, emitter_pulse_ms=200, blade_stabilize_ms=500, conveyor_ramp_ms=100),
        timeout=TimeoutConfig(vision_read_timeout=3.0, sort_timeout=5.0, jam_detection=12.0, blade_timeout=2.0, conveyor_timeout=10.0, watchdog_scan_timeout_ms=1000, watchdog_telemetry_timeout_ms=5000),
        reconnect=ReconnectConfig(modbus_base_s=1.0, modbus_max_s=30.0, mqtt_base_s=2.0, mqtt_max_s=60.0, mqtt_offline_buffer_size=500),
        logging=LoggingConfig(level="INFO", log_dir="logs", max_bytes=1000, backup_count=1)
    )

@pytest.fixture
def system_state():
    return SystemState()

@pytest.fixture
def output_state():
    return OutputState()
