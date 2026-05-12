"""
Telemetry publisher for streaming metrics to ThingsBoard.
"""
import logging
from typing import Optional
from telemetry.mqtt_client import MQTTClient
from telemetry.metrics import MetricsCollector, Metrics
from models.system_state import SystemState
from models.product import Product


logger = logging.getLogger(__name__)


class TelemetryPublisher:
    """
    Publishes system telemetry to ThingsBoard via MQTT.
    """

    # ThingsBoard MQTT topics
    TELEMETRY_TOPIC = "v1/devices/me/telemetry"
    ATTRIBUTES_TOPIC = "v1/devices/me/attributes"
    RPC_RESPONSE_TOPIC = "v1/devices/me/rpc/response"

    def __init__(self, mqtt: MQTTClient, metrics: MetricsCollector):
        """Initialize publisher."""
        self.mqtt = mqtt
        self.metrics = metrics
        self.last_publish_time = 0.0
        self.publish_count = 0

    async def publish_telemetry(
        self,
        system_state: SystemState,
        current_product: Optional[Product],
        scan_cycle_ms: float,
        sorter_states: dict
    ) -> bool:
        """
        Publish current telemetry to ThingsBoard.
        
        Args:
            system_state: Current system state
            current_product: Current product or None
            scan_cycle_ms: Current scan cycle time
            sorter_states: Dict of sorter active states
            
        Returns:
            True if published successfully.
        """
        if not self.mqtt.is_connected():
            logger.warning("MQTT not connected, skipping telemetry publish")
            return False

        # Build metrics
        metrics = Metrics()
        metrics.system_state = system_state.state.value
        metrics.scan_cycle_ms = scan_cycle_ms
        metrics.modbus_connected = system_state.modbus_connected
        metrics.mqtt_connected = True
        metrics.total_products = system_state.total_products
        metrics.successful_sorts = system_state.successful_sorts
        metrics.failed_sorts = system_state.failed_sorts
        metrics.alarm_count = system_state.alarm_count
        metrics.uptime_seconds = system_state.get_uptime_seconds()

        # Add current product info
        if current_product:
            metrics.current_product_id = current_product.vision_id
            metrics.current_product_shape = current_product.shape.value
            metrics.current_product_color = current_product.color.value
            metrics.current_product_sorter = current_product.target_sorter

        # Calculate derived metrics
        metrics.throughput_per_min = self.metrics.calculate_throughput(
            system_state.successful_sorts,
            system_state.get_uptime_seconds()
        )
        metrics.avg_sort_time_s = self.metrics.get_avg_sort_time_s()
        metrics.error_rate = self.metrics.calculate_error_rate(
            system_state.total_products,
            system_state.failed_sorts
        )

        # Sorter states
        metrics.sorter1_active = sorter_states.get("sorter1", False)
        metrics.sorter2_active = sorter_states.get("sorter2", False)
        metrics.sorter3_active = sorter_states.get("sorter3", False)

        # Publish
        payload = metrics.to_dict()
        success = await self.mqtt.publish(self.TELEMETRY_TOPIC, payload)

        if success:
            self.publish_count += 1
            logger.debug(f"Telemetry published ({self.publish_count})")
        else:
            logger.warning("Failed to publish telemetry")

        return success

    async def publish_alarm(
        self,
        alarm_type: str,
        message: str,
        severity: str = "WARNING"
    ) -> bool:
        """
        Publish alarm event.
        
        Args:
            alarm_type: Type of alarm
            message: Alarm message
            severity: Severity level (WARNING, CRITICAL, ERROR)
            
        Returns:
            True if published successfully.
        """
        if not self.mqtt.is_connected():
            return False

        payload = {
            "alarm_type": alarm_type,
            "message": message,
            "severity": severity,
        }

        return await self.mqtt.publish(self.TELEMETRY_TOPIC, payload)

    async def publish_rpc_response(self, request_id: str, response: dict) -> bool:
        """
        Publish RPC response.
        
        Args:
            request_id: RPC request ID
            response: Response data
            
        Returns:
            True if published successfully.
        """
        if not self.mqtt.is_connected():
            return False

        topic = f"{self.RPC_RESPONSE_TOPIC}/{request_id}"
        return await self.mqtt.publish(topic, response)

    def get_publish_count(self) -> int:
        """Get total publishes count."""
        return self.publish_count

    async def disconnect(self) -> None:
        """Disconnect publisher."""
        await self.mqtt.disconnect()
