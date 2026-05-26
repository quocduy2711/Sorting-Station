"""
Application configuration — loaded from environment variables via python-dotenv.

RULE: No hardcoded values. All settings come from .env or environment.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv


def _load_env() -> None:
    """Load .env file from project root (one level above this package)."""
    project_root = Path(__file__).parent.parent
    env_file = project_root / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=False)  # Don't override already-set OS vars


def _get_str(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _get_int(key: str, default: int = 0) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_float(key: str, default: float = 0.0) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _get_bool(key: str, default: bool = False) -> bool:
    val = os.getenv(key, str(default)).lower()
    return val in ("1", "true", "yes", "on")


# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ModbusConfig:
    """Modbus TCP connection settings."""
    host: str
    port: int
    timeout: float
    unit_id: int
    max_retries: int


@dataclass(frozen=True)
class MQTTConfig:
    """MQTT client settings (kept for compatibility, but populated from TB settings)."""
    host: str
    port: int
    username: str
    password: str
    access_token: str
    ca_certs: str
    clean_session: bool


@dataclass(frozen=True)
class ThingsBoardConfig:
    """ThingsBoard server and device settings."""
    host: str
    http_port: int
    mqtt_port: int
    device_name: str
    station_id: str
    access_token: str
    use_provisioning: bool
    provision_key: str
    provision_secret: str
    lwt_topic: str


@dataclass(frozen=True)
class TimingConfig:
    """Timing parameters for control loops (all in ms unless noted)."""
    io_scan_ms: int
    sorter_tick_ms: int
    supervision_ms: int
    telemetry_ms: int
    emitter_pulse_ms: int
    blade_stabilize_ms: int
    conveyor_ramp_ms: int


@dataclass(frozen=True)
class TimeoutConfig:
    """Timeout thresholds for operations (seconds unless noted)."""
    vision_read_timeout: float
    sort_timeout: float
    jam_detection: float
    blade_timeout: float
    conveyor_timeout: float
    watchdog_scan_timeout_ms: int
    watchdog_telemetry_timeout_ms: int


@dataclass(frozen=True)
class ReconnectConfig:
    """Reconnect strategy configuration."""
    modbus_base_s: float
    modbus_max_s: float
    mqtt_base_s: float
    mqtt_max_s: float
    mqtt_offline_buffer_size: int


@dataclass(frozen=True)
class HttpTransportConfig:
    """HTTP transport pipeline configuration."""
    timeout_s: float
    max_retries: int
    batch_window_s: float
    max_batch_size: int
    max_queue_size: int
    spool_db_path: str
    max_spool_size: int
    retry_check_interval_s: float
    circuit_breaker_threshold: int
    circuit_breaker_reset_s: float
    heartbeat_interval_s: float
    shared_attr_poll_interval_s: float


@dataclass(frozen=True)
class LoggingConfig:
    """Logging configuration."""
    level: str
    log_dir: str
    max_bytes: int
    backup_count: int


@dataclass(frozen=True)
class SerialConfig:
    """Serial bridge configuration for ESP32 gateway.

    RULE: If serial_port is None → SerialBridge is disabled.
    """
    serial_port: str | None   # None = disabled (no SERIAL_ENABLED flag needed)
    baud_rate: int


@dataclass(frozen=True)
class AppConfig:
    """
    Top-level application configuration.

    Composed of typed sub-configs.  All values are frozen at startup.
    """
    modbus: ModbusConfig
    mqtt: MQTTConfig
    thingsboard: ThingsBoardConfig
    timing: TimingConfig
    timeout: TimeoutConfig
    reconnect: ReconnectConfig
    http_transport: HttpTransportConfig
    serial: SerialConfig
    logging: LoggingConfig


def load_config() -> AppConfig:
    """
    Load application config from environment variables.

    Reads .env file first (if present), then OS environment.
    Call this ONCE at startup, then pass the returned object everywhere.

    Returns:
        Fully-populated, frozen AppConfig.
    """
    _load_env()

    modbus = ModbusConfig(
        host=_get_str("MODBUS_HOST", "127.0.0.1"),
        port=_get_int("MODBUS_PORT", 502),
        timeout=_get_float("MODBUS_TIMEOUT", 2.0),
        unit_id=_get_int("MODBUS_UNIT_ID", 1),
        max_retries=_get_int("MODBUS_MAX_RETRIES", 3),
    )

    tb_host = _get_str("TB_HOST", "127.0.0.1")
    # IMPORTANT: tb-dev.imespro.ai uses a non-standard MQTT port.
    # Run tools/probe_mqtt_port.py to discover it, then set in .env:
    #   TB_MQTT_PORT=<port>
    #   MQTT_PORT=<port>
    tb_mqtt_port = int(os.getenv("MQTT_PORT", os.getenv("TB_MQTT_PORT", "1883")))
    tb_token = _get_str("TB_DEVICE_TOKEN", "")

    thingsboard = ThingsBoardConfig(
        host=tb_host,
        http_port=_get_int("TB_HTTP_PORT", 58090),
        mqtt_port=tb_mqtt_port,
        device_name=_get_str("TB_DEVICE_NAME", "sorting-station-01"),
        station_id=_get_str("TB_STATION_ID", "SS-01"),
        access_token=tb_token,
        use_provisioning=_get_bool("TB_USE_PROVISIONING", False),
        provision_key=_get_str("TB_PROVISION_KEY", ""),
        provision_secret=_get_str("TB_PROVISION_SECRET", ""),
        lwt_topic="v1/devices/me/telemetry",
    )

    mqtt = MQTTConfig(
        host=_get_str("MQTT_HOST", tb_host),
        port=_get_int("MQTT_PORT", tb_mqtt_port),
        username=_get_str("MQTT_USERNAME", ""),
        password=_get_str("MQTT_PASSWORD", ""),
        access_token=_get_str("MQTT_ACCESS_TOKEN", tb_token),
        ca_certs=_get_str("MQTT_TLS_CA_CERTS", ""),
        clean_session=_get_bool("MQTT_CLEAN_SESSION", True),
    )

    timing = TimingConfig(
        io_scan_ms=_get_int("SCAN_INTERVAL_MS", 50),
        sorter_tick_ms=_get_int("SORTER_TICK_MS", 35),
        supervision_ms=_get_int("SUPERVISION_MS", 100),
        telemetry_ms=_get_int("TELEMETRY_MS", 150),
        emitter_pulse_ms=_get_int("EMITTER_PULSE_MS", 200),
        blade_stabilize_ms=_get_int("BLADE_STABILIZE_MS", 500),
        conveyor_ramp_ms=_get_int("CONVEYOR_RAMP_MS", 100),
    )

    timeout = TimeoutConfig(
        vision_read_timeout=_get_float("VISION_READ_TIMEOUT", 3.0),
        sort_timeout=_get_float("SORT_TIMEOUT", 5.0),
        jam_detection=_get_float("JAM_DETECTION_TIMEOUT", 12.0),
        blade_timeout=_get_float("BLADE_TIMEOUT", 2.0),
        conveyor_timeout=_get_float("CONVEYOR_TIMEOUT", 10.0),
        watchdog_scan_timeout_ms=_get_int("WATCHDOG_SCAN_TIMEOUT_MS", 1000),
        watchdog_telemetry_timeout_ms=_get_int("WATCHDOG_TELEMETRY_TIMEOUT_MS", 5000),
    )

    reconnect = ReconnectConfig(
        modbus_base_s=_get_float("MODBUS_RECONNECT_BASE_S", 1.0),
        modbus_max_s=_get_float("MODBUS_RECONNECT_MAX_S", 30.0),
        mqtt_base_s=_get_float("MQTT_RECONNECT_BASE_S", 2.0),
        mqtt_max_s=_get_float("MQTT_RECONNECT_MAX_S", 60.0),
        mqtt_offline_buffer_size=_get_int("MQTT_OFFLINE_BUFFER_SIZE", 500),
    )

    http_transport = HttpTransportConfig(
        timeout_s=_get_float("HTTP_TIMEOUT_S", 5.0),
        max_retries=_get_int("HTTP_MAX_RETRIES", 5),
        batch_window_s=_get_float("TELEMETRY_BATCH_WINDOW_S", 1.0),
        max_batch_size=_get_int("TELEMETRY_MAX_BATCH_SIZE", 20),
        max_queue_size=_get_int("TELEMETRY_MAX_QUEUE_SIZE", 1000),
        spool_db_path=_get_str("TELEMETRY_SPOOL_DB", "data/telemetry_spool.db"),
        max_spool_size=_get_int("TELEMETRY_MAX_SPOOL_SIZE", 10000),
        retry_check_interval_s=_get_float("TELEMETRY_RETRY_INTERVAL_S", 5.0),
        circuit_breaker_threshold=_get_int("HTTP_CB_THRESHOLD", 5),
        circuit_breaker_reset_s=_get_float("HTTP_CB_RESET_S", 30.0),
        heartbeat_interval_s=_get_float("HEARTBEAT_INTERVAL_S", 30.0),
        shared_attr_poll_interval_s=_get_float("SHARED_ATTR_POLL_S", 60.0),
    )

    logging_cfg = LoggingConfig(
        level=_get_str("LOG_LEVEL", "INFO"),
        log_dir=_get_str("LOG_DIR", "logs"),
        max_bytes=_get_int("LOG_MAX_BYTES", 10_485_760),  # 10 MB
        backup_count=_get_int("LOG_BACKUP_COUNT", 5),
    )

    serial_port_raw = _get_str("SERIAL_PORT", "")
    serial = SerialConfig(
        serial_port=serial_port_raw if serial_port_raw else None,
        baud_rate=_get_int("SERIAL_BAUD", 115200),
    )

    return AppConfig(
        modbus=modbus,
        mqtt=mqtt,
        thingsboard=thingsboard,
        timing=timing,
        timeout=timeout,
        reconnect=reconnect,
        http_transport=http_transport,
        serial=serial,
        logging=logging_cfg,
    )
