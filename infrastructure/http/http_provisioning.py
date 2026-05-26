"""
TBProvisioning — Auto-provision device with ThingsBoard.

Flow:
1. Try loading credentials from data/device_credentials.json.
2. If exist, return token.
3. If not, and provisioning enabled:
   a. Connect to TB using provision key/secret via MQTT.
   b. Send request to /provision/request.
   c. Wait for /provision/response.
   d. Extract access_token.
   e. Save to data/device_credentials.json.
   f. Return token.

NOTE: Provisioning uses MQTT internally even though runtime telemetry
uses HTTP. This is the standard TB provisioning protocol.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)

PROVISION_REQUEST_TOPIC = "/provision/request"
PROVISION_RESPONSE_TOPIC = "/provision/response"
CREDENTIALS_FILE = Path("data/device_credentials.json")


class TBProvisioning:
    """Handles ThingsBoard device auto-provisioning via MQTT."""

    @staticmethod
    async def load_credentials() -> Optional[str]:
        """Load saved access token from file, if it exists."""
        if not CREDENTIALS_FILE.exists():
            return None
        try:
            with CREDENTIALS_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("access_token")
        except Exception as exc:
            logger.error(f"Failed to load credentials: {exc}")
            return None

    @staticmethod
    async def save_credentials(token: str, device_name: str) -> None:
        """Save access token to file."""
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "access_token": token,
            "device_name": device_name,
        }
        try:
            with CREDENTIALS_FILE.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved device credentials to {CREDENTIALS_FILE}")
        except Exception as exc:
            logger.error(f"Failed to save credentials: {exc}")

    @staticmethod
    async def provision(
        host: str,
        port: int,
        device_name: str,
        provision_key: str,
        provision_secret: str,
        timeout_s: float = 10.0,
    ) -> Optional[str]:
        """Run the provisioning flow. Returns the access_token if successful."""
        logger.info(f"Starting provisioning for {device_name}...")

        loop = asyncio.get_event_loop()
        future: asyncio.Future[Optional[str]] = loop.create_future()

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                client.subscribe(PROVISION_RESPONSE_TOPIC)
                payload = json.dumps({
                    "deviceName": device_name,
                    "provisionDeviceKey": provision_key,
                    "provisionDeviceSecret": provision_secret,
                })
                client.publish(PROVISION_REQUEST_TOPIC, payload)
            else:
                if not future.done():
                    loop.call_soon_threadsafe(
                        future.set_exception,
                        ConnectionError(f"Connect failed rc={rc}"),
                    )

        def on_message(client, userdata, msg):
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
                if payload.get("status") == "SUCCESS":
                    token = payload.get("credentialsValue")
                    if not future.done():
                        loop.call_soon_threadsafe(future.set_result, token)
                else:
                    if not future.done():
                        error_msg = payload.get(
                            "errorMsg", "Unknown provisioning error"
                        )
                        loop.call_soon_threadsafe(
                            future.set_exception, ValueError(error_msg)
                        )
            except Exception as e:
                if not future.done():
                    loop.call_soon_threadsafe(future.set_exception, e)

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        client.on_connect = on_connect
        client.on_message = on_message

        try:
            client.connect(host, port)
            client.loop_start()

            token = await asyncio.wait_for(future, timeout=timeout_s)

            if token:
                await TBProvisioning.save_credentials(token, device_name)
            return token

        except asyncio.TimeoutError:
            logger.error("Provisioning timed out")
            return None
        except Exception as exc:
            logger.error(f"Provisioning failed: {exc}")
            return None
        finally:
            client.loop_stop()
            client.disconnect()
