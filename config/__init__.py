"""
config/ — Central configuration package.

Usage:
    from config import load_config, AppConfig, ApplicationContext
    cfg = load_config()
"""
from .app_config import (
    AppConfig,
    ModbusConfig,
    MQTTConfig,
    HttpTransportConfig,
    TimingConfig,
    TimeoutConfig,
    ReconnectConfig,
    LoggingConfig,
    load_config,
)
from .runtime_context import (
    ApplicationContext,
    RuntimeState,
    InfrastructureContext,
    RuntimeContext,  # backwards-compat alias
)
from .constants import SORT_MAP, PRODUCT_MAP, VALID_PRODUCT_IDS

__all__ = [
    "AppConfig",
    "ModbusConfig",
    "MQTTConfig",
    "HttpTransportConfig",
    "TimingConfig",
    "TimeoutConfig",
    "ReconnectConfig",
    "LoggingConfig",
    "load_config",
    "ApplicationContext",
    "RuntimeState",
    "InfrastructureContext",
    "RuntimeContext",
    "SORT_MAP",
    "PRODUCT_MAP",
    "VALID_PRODUCT_IDS",
]
