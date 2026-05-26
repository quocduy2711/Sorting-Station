"""
Shared pytest fixtures for the sorting station tests.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from models.system_state import SystemState
from models.output_state import OutputState
from config.app_config import (
    AppConfig, ModbusConfig, MQTTConfig, ThingsBoardConfig,
    TimingConfig, TimeoutConfig, ReconnectConfig,
    HttpTransportConfig, SerialConfig, LoggingConfig,
)

@pytest.fixture
def mock_config():
    return AppConfig(
        modbus=ModbusConfig(host="127.0.0.1", port=502, timeout=2.0, unit_id=1, max_retries=3),
        mqtt=MQTTConfig(host="127.0.0.1", port=1883, username="", password="", access_token="test_token", ca_certs="", clean_session=True),
        thingsboard=ThingsBoardConfig(
            host="127.0.0.1", http_port=8080, mqtt_port=1883,
            device_name="test-station", station_id="SS-TEST",
            access_token="test_token", use_provisioning=False,
            provision_key="", provision_secret="",
            lwt_topic="v1/devices/me/telemetry",
        ),
        timing=TimingConfig(io_scan_ms=50, sorter_tick_ms=35, supervision_ms=100, telemetry_ms=150, emitter_pulse_ms=200, blade_stabilize_ms=500, conveyor_ramp_ms=100),
        timeout=TimeoutConfig(vision_read_timeout=3.0, sort_timeout=5.0, jam_detection=12.0, blade_timeout=2.0, conveyor_timeout=10.0, watchdog_scan_timeout_ms=1000, watchdog_telemetry_timeout_ms=5000),
        reconnect=ReconnectConfig(modbus_base_s=1.0, modbus_max_s=30.0, mqtt_base_s=2.0, mqtt_max_s=60.0, mqtt_offline_buffer_size=500),
        http_transport=HttpTransportConfig(
            timeout_s=5.0, max_retries=3, batch_window_s=1.0,
            max_batch_size=20, max_queue_size=1000,
            spool_db_path="data/test_spool.db", max_spool_size=10000,
            retry_check_interval_s=5.0, circuit_breaker_threshold=5,
            circuit_breaker_reset_s=30.0, heartbeat_interval_s=30.0,
            shared_attr_poll_interval_s=60.0,
        ),
        serial=SerialConfig(serial_port=None, baud_rate=115200),
        logging=LoggingConfig(level="INFO", log_dir="logs", max_bytes=1000, backup_count=1),
    )

@pytest.fixture
def system_state():
    return SystemState()

@pytest.fixture
def output_state():
    return OutputState()
