"""
Central configuration for the industrial control runtime.
"""
from dataclasses import dataclass
from typing import Dict


@dataclass
class ModbusConfig:
    """Modbus TCP connection settings."""
    host: str = "127.0.0.1"
    port: int = 502
    unit_id: int = 1
    timeout: float = 2.0
    max_retries: int = 3


@dataclass
class MQTTConfig:
    """MQTT client settings for ThingsBoard."""
    broker: str = "localhost"
    port: int = 1883
    access_token: str = "your_access_token"
    ca_certs: str = ""  # Set for TLS
    tls_version: int = 0  # 0=no TLS, 3=TLSv1.2, etc.
    clean_session: bool = True


@dataclass
class TimingConfig:
    """Timing parameters for control loops."""
    io_scan_ms: int = 50  # Input/Output scan cycle
    sorter_tick_ms: int = 35  # Sorter FSM tick
    supervision_ms: int = 100  # Timeout/alarm checks
    telemetry_ms: int = 150  # MQTT publish interval
    emitter_pulse_ms: int = 200  # Pulse width for emitter
    blade_stabilize_delay_ms: int = 500  # Stabilization after blade movement
    conveyor_ramp_ms: int = 100  # Conveyor acceleration time


@dataclass
class TimeoutConfig:
    """Timeout thresholds for operations."""
    vision_read_timeout: float = 3.0
    sort_timeout: float = 5.0
    jam_detection: float = 12.0
    blade_timeout: float = 2.0
    conveyor_timeout: float = 10.0
    modbus_timeout: float = 2.0


# Product ID to sorter mapping
SORT_MAP: Dict[int, int] = {
    1: 1,  # Flat/Blue -> Sorter 1
    2: 1,  # Flat/Green -> Sorter 1
    3: 2,  # Circle/Blue -> Sorter 2
    4: 2,  # Circle/Green -> Sorter 2
    5: 3,  # Complex/Blue -> Sorter 3
    6: 3,  # Complex/Green -> Sorter 3
}

# Product ID to shape/color mapping
PRODUCT_MAP = {
    1: ("Flat", "Blue"),
    2: ("Flat", "Green"),
    3: ("Circle", "Blue"),
    4: ("Circle", "Green"),
    5: ("Complex", "Blue"),
    6: ("Complex", "Green"),
}

# Valid product IDs
VALID_PRODUCT_IDS = set(SORT_MAP.keys())


# Default configuration instances
def get_default_config():
    """Get default configuration."""
    return {
        "modbus": ModbusConfig(),
        "mqtt": MQTTConfig(),
        "timing": TimingConfig(),
        "timeout": TimeoutConfig(),
    }
