"""
MQTT client for ThingsBoard communication.
"""
import logging
import json
from typing import Dict, Optional, Callable
import paho.mqtt.client as mqtt
from config import MQTTConfig


logger = logging.getLogger(__name__)


class MQTTClient:
    """
    MQTT client for publishing telemetry to ThingsBoard.
    """

    def __init__(self, config: MQTTConfig):
        """Initialize MQTT client."""
        self.config = config
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.connected = False
        self.last_error: Optional[str] = None
        
        # Callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message
        
        # User callbacks
        self.on_message_callback: Optional[Callable] = None

    def _on_connect(self, client, userdata, flags, rc):
        """MQTT connect callback."""
        if rc == 0:
            logger.info("MQTT connected successfully")
            self.connected = True
        else:
            logger.error(f"MQTT connection failed with code {rc}")
            self.connected = False
            self.last_error = f"Connection failed (code {rc})"

    def _on_disconnect(self, client, userdata, rc):
        """MQTT disconnect callback."""
        if rc != 0:
            logger.warning(f"MQTT disconnected unexpectedly (code {rc})")
        self.connected = False

    def _on_message(self, client, userdata, msg):
        """MQTT message callback."""
        logger.debug(f"MQTT message received: {msg.topic}")
        
        if self.on_message_callback:
            try:
                payload = msg.payload.decode()
                self.on_message_callback(msg.topic, payload)
            except Exception as e:
                logger.error(f"Error in message callback: {e}")

    async def connect(self) -> bool:
        """
        Connect to MQTT broker.
        
        Returns:
            True if connected successfully.
        """
        try:
            if self.config.ca_certs:
                self.client.tls_set(
                    ca_certs=self.config.ca_certs,
                    certfile=None,
                    keyfile=None,
                    cert_reqs=mqtt.ssl.CERT_REQUIRED,
                    tls_version=self.config.tls_version or mqtt.ssl.PROTOCOL_TLSv1_2,
                    ciphers=None
                )

            self.client.username_pw_set(self.config.access_token, password="")
            self.client.connect(self.config.broker, self.config.port, keepalive=60)
            
            # Start network loop
            self.client.loop_start()
            
            logger.info(f"MQTT connecting to {self.config.broker}:{self.config.port}")
            return True

        except Exception as e:
            self.connected = False
            self.last_error = f"Connection error: {str(e)}"
            logger.error(self.last_error)
            return False

    async def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("MQTT disconnected")
        except Exception as e:
            logger.error(f"Error disconnecting: {e}")

    async def publish(self, topic: str, payload: Dict) -> bool:
        """
        Publish a message to MQTT.
        
        Args:
            topic: MQTT topic
            payload: Dictionary payload (will be JSON encoded)
            
        Returns:
            True if successful.
        """
        if not self.connected:
            self.last_error = "Not connected to MQTT broker"
            return False

        try:
            message = json.dumps(payload)
            result = self.client.publish(topic, message, qos=1)
            
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                self.last_error = f"Publish failed: {mqtt.error_string(result.rc)}"
                logger.error(self.last_error)
                return False
            
            return True

        except Exception as e:
            self.last_error = f"Publish error: {str(e)}"
            logger.error(self.last_error)
            return False

    async def subscribe(self, topic: str) -> bool:
        """
        Subscribe to an MQTT topic.
        
        Args:
            topic: MQTT topic pattern
            
        Returns:
            True if successful.
        """
        if not self.connected:
            return False

        try:
            result = self.client.subscribe(topic)
            if result[0] != mqtt.MQTT_ERR_SUCCESS:
                logger.error(f"Subscribe failed: {topic}")
                return False
            
            logger.debug(f"Subscribed to: {topic}")
            return True

        except Exception as e:
            logger.error(f"Subscribe error: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if MQTT is connected."""
        return self.connected

    def set_message_callback(self, callback: Callable) -> None:
        """Set callback for incoming messages."""
        self.on_message_callback = callback

    def get_last_error(self) -> Optional[str]:
        """Get last error message."""
        return self.last_error
