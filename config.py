"""
config.py — Backward-compatibility shim.

This module delegates to the new `config/` package.
Kept so existing imports don't break during transition.

DEPRECATED: Import directly from `config` package instead:
    from config import load_config, ModbusConfig, MQTTConfig, ...
"""
from config.app_config import (   # noqa: F401
    ModbusConfig,
    MQTTConfig,
    TimingConfig,
    TimeoutConfig,
    ReconnectConfig,
    LoggingConfig,
    AppConfig,
    load_config,
)
from config.constants import (    # noqa: F401
    SORT_MAP,
    PRODUCT_MAP,
    VALID_PRODUCT_IDS,
)


def get_default_config():
    """Backward-compat wrapper. Use load_config() instead."""
    cfg = load_config()
    return {
        "modbus": cfg.modbus,
        "mqtt": cfg.mqtt,
        "timing": cfg.timing,
        "timeout": cfg.timeout,
    }
