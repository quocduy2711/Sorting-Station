# Industrial Sorting Station Runtime

A robust, event-driven Python runtime for controlling an industrial sorting station in Factory I/O via Modbus TCP and streaming telemetry to ThingsBoard via MQTT.

## Architecture

The system is built with a production-ready architecture featuring:
- **Dependency Injection**: Centralized configuration and component wiring (`config/runtime_context.py`).
- **Async Modbus Client**: Non-blocking I/O with exponential backoff reconnect.
- **Event-Driven Pub/Sub**: Loose coupling via `EventManager` (asyncio.Queue).
- **Service Layer**: Separation of orchestration from hardware/drivers.
- **Failsafe Watchdog**: Heartbeat monitoring for scan loop and Modbus.
- **Runtime Metrics**: Rolling window averages for scan cycle time, latency, and throughput.
- **Offline Buffering**: MQTT telemetry buffers in memory if the network drops.

## Directory Structure

```text
project/
├── alarms/         # Fault handlers and alarm management
├── config/         # Environment config, DI container, domain constants
├── control/        # Event bus, FSM, sorting logic, watchdog
├── drivers/        # Modbus client, async input/output mapping
├── models/         # Data classes (SystemState, OutputState, Product)
├── services/       # Orchestration (Sorting, Telemetry, Alarms, Runtime)
├── telemetry/      # MQTT client, publisher, metrics calculator
├── utils/          # Logging, health monitor, runtime metrics
├── tests/          # Pytest suite
├── logs/           # Rotating logs (runtime.log, alarms.log)
├── .env.example    # Environment variables template
├── setup.bat       # Windows setup script
├── setup.sh        # Linux/Mac setup script
└── main.py         # Application entry point
```

## Quick Start (Local)

1. **Clone and run setup**:
   - On Windows: Double-click `setup.bat` or run it from CMD.
   - On Linux/Mac: `./setup.sh`
   
2. **Configure Environment**:
   - Edit `.env` to match your Factory I/O Modbus IP and ThingsBoard MQTT credentials.

3. **Run**:
   ```bash
   # Windows
   call .venv\Scripts\activate.bat
   python main.py
   
   # Linux/Mac
   source .venv/bin/activate
   python main.py
   ```

## Docker Setup

```bash
docker-compose up -d --build
```

Ensure your `.env` file contains correct IP addresses for Modbus and MQTT (do not use `127.0.0.1` inside Docker unless `network_mode: host` is set).

## Factory I/O Setup
- Select the **Sorting by Type 3** scene.
- Go to File > Drivers > Modbus TCP Client.
- Set Configuration:
  - Digital Inputs: 6 (Starts at 0)
  - Digital Outputs: 16 (Starts at 0)
  - Input Registers: 1 (Starts at 0)
- Connect vision sensor output to Input Register 0.
- Verify coil mapping matches `drivers/output_writer.py`.
