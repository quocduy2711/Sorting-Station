"""
Metrics collection system.

Collects industrial metrics for telemetry streaming.
"""
import logging
import time
from dataclasses import dataclass
from typing import Dict
from collections import deque


logger = logging.getLogger(__name__)


@dataclass
class Metrics:
    """Snapshot of current metrics."""
    system_state: str = "IDLE"
    current_product_id: int = 0
    current_product_shape: str = ""
    current_product_color: str = ""
    current_product_sorter: int = 0
    
    throughput_per_min: float = 0.0
    avg_sort_time_s: float = 0.0
    error_rate: float = 0.0
    
    scan_cycle_ms: float = 0.0
    modbus_connected: bool = False
    mqtt_connected: bool = False
    
    total_products: int = 0
    successful_sorts: int = 0
    failed_sorts: int = 0
    alarm_count: int = 0
    
    sorter1_active: bool = False
    sorter2_active: bool = False
    sorter3_active: bool = False
    
    uptime_seconds: float = 0.0
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "system_state": self.system_state,
            "current_product_id": self.current_product_id,
            "current_product_shape": self.current_product_shape,
            "current_product_color": self.current_product_color,
            "current_product_sorter": self.current_product_sorter,
            "throughput_per_min": round(self.throughput_per_min, 2),
            "avg_sort_time_s": round(self.avg_sort_time_s, 2),
            "error_rate": round(self.error_rate, 2),
            "scan_cycle_ms": round(self.scan_cycle_ms, 2),
            "modbus_connected": self.modbus_connected,
            "mqtt_connected": self.mqtt_connected,
            "total_products": self.total_products,
            "successful_sorts": self.successful_sorts,
            "failed_sorts": self.failed_sorts,
            "alarm_count": self.alarm_count,
            "sorter1_active": self.sorter1_active,
            "sorter2_active": self.sorter2_active,
            "sorter3_active": self.sorter3_active,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }


class MetricsCollector:
    """
    Collects and calculates industrial metrics.
    """

    def __init__(self, history_size: int = 60):
        """
        Initialize metrics collector.
        
        Args:
            history_size: Number of scan cycles to track
        """
        self.history_size = history_size
        self.scan_times = deque(maxlen=history_size)
        self.sort_times = deque(maxlen=history_size)
        self.startup_time = time.monotonic()

    def record_scan_time(self, cycle_ms: float) -> None:
        """Record scan cycle duration."""
        self.scan_times.append(cycle_ms)

    def record_sort_time(self, duration_s: float) -> None:
        """Record sort operation duration."""
        self.sort_times.append(duration_s)

    def get_avg_scan_time_ms(self) -> float:
        """Get average scan cycle time."""
        if not self.scan_times:
            return 0.0
        return sum(self.scan_times) / len(self.scan_times)

    def get_max_scan_time_ms(self) -> float:
        """Get maximum scan cycle time."""
        if not self.scan_times:
            return 0.0
        return max(self.scan_times)

    def get_avg_sort_time_s(self) -> float:
        """Get average sort duration."""
        if not self.sort_times:
            return 0.0
        return sum(self.sort_times) / len(self.sort_times)

    def calculate_throughput(self, products_completed: int, elapsed_sec: float) -> float:
        """
        Calculate throughput in products per minute.
        
        Args:
            products_completed: Number of completed products
            elapsed_sec: Elapsed time in seconds
            
        Returns:
            Products per minute
        """
        if elapsed_sec == 0:
            return 0.0
        
        return (products_completed / elapsed_sec) * 60

    def calculate_error_rate(self, total: int, failed: int) -> float:
        """
        Calculate error rate as percentage.
        
        Args:
            total: Total products
            failed: Failed products
            
        Returns:
            Error rate (0-100)
        """
        if total == 0:
            return 0.0
        
        return (failed / total) * 100

    def get_uptime_seconds(self) -> float:
        """Get system uptime."""
        return time.monotonic() - self.startup_time

    def reset_history(self) -> None:
        """Clear metric history."""
        self.scan_times.clear()
        self.sort_times.clear()
