# ESP32 Gateway Firmware

Gateway firmware for the sorting station — bridges Python control system to ThingsBoard via WiFi.

## Features

- **DS18B20** temperature sensor reading (GPIO 4)
- **Serial JSON bridge** to Python control system (115200 baud)
- **HTTP telemetry forwarding** to ThingsBoard
- **MQTT RPC receive** from ThingsBoard → Serial forwarding to Python

## Wiring

| Component       | ESP32 Pin | Notes                        |
|-----------------|-----------|------------------------------|
| DS18B20 DATA    | GPIO 4    | 4.7kΩ pull-up to VCC         |
| DS18B20 VCC     | 3.3V      |                              |
| DS18B20 GND     | GND       |                              |
| USB             | micro-USB | Serial bridge to Python host |

## Build & Flash

### 1. Set environment variables

```bash
export WIFI_SSID="YourNetworkSSID"
export WIFI_PASSWORD="YourNetworkPassword"
export TB_HOST="tb-dev.imespro.ai"
export TB_HTTP_PORT=58090
export TB_ACCESS_TOKEN="your-device-token"
```

Or update the `build_flags` in `platformio.ini` directly.

### 2. Build and upload

```bash
pio run --target upload
```

### 3. Monitor serial output

```bash
pio device monitor
```

## Serial Protocol

- **Baudrate**: 115200
- **Line-delimited JSON** (each message ends with `\n`)

### Python → ESP32

```json
{"type": "telemetry", "data": {"machine_state": "RUNNING", "remover1_count": 5, ...}}
```

ESP32 injects `temperature_c` and `mqtt_rpc_available` into `data` before forwarding to ThingsBoard via HTTP.

### ESP32 → Python

```json
{"type": "rpc", "method": "start_machine", "params": {"speed": 100}, "request_id": "42"}
```

RPC commands received from ThingsBoard via MQTT are forwarded to Python for execution.

### Status messages

```json
{"type": "status", "wifi": true, "ip": "192.168.1.100"}
```
