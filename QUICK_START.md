# Quick Reference Guide

## File Structure Summary

```
d:\PROJECT\New folder\
├── main.py                          # START HERE - Entry point
├── config.py                        # Base configuration
├── config_example.py                # Example setup
├── requirements.txt                 # pip install these
├── README.md                        # User documentation
├── IMPLEMENTATION.md                # Architecture details
│
├── models/ (Data Objects)
│   ├── product.py                   # Product lifecycle
│   ├── system_state.py              # System FSM state
│   ├── output_state.py              # Modbus output buffer
│   └── input_snapshot.py            # Input data snapshot
│
├── drivers/ (Hardware I/O)
│   ├── modbus_client.py             # Modbus TCP communication
│   ├── input_reader.py              # Read inputs (50ms scan)
│   └── output_writer.py             # Write outputs (shadow state)
│
├── control/ (Control Logic)
│   ├── runtime_engine.py            # Main orchestrator
│   ├── state_machine.py             # System FSM (13 states)
│   ├── product_tracking.py          # Product lifecycle mgmt
│   ├── sorting_logic.py             # Routing & validation
│   ├── event_manager.py             # Event bus (14 events)
│   ├── timers.py                    # Timeout management
│   ├── debounce.py                  # Sensor debouncing
│   └── watchdog.py                  # Health monitoring
│
├── alarms/ (Fault Handling)
│   ├── alarm_manager.py             # Alarm tracking (8 types)
│   └── fault_handler.py             # Failsafe shutdown
│
├── telemetry/ (MQTT & Metrics)
│   ├── mqtt_client.py               # MQTT to ThingsBoard
│   ├── metrics.py                   # Metrics collection
│   └── publisher.py                 # Telemetry publishing
│
├── utils/                           # Utilities
├── logs/                            # Runtime logs
```

---

## System States

### System FSM (13 states)
- IDLE → STARTING → RUNNING → WAITING_PRODUCT
- WAITING_CLEAR_ZONE → READING_ID → MOVING_TO_SORTER
- SORTING → COMPLETE → STOPPED
- EMERGENCY_STOP, ERROR, RESETTING

### Product Lifecycle (10 states)
- CREATED → WAITING_BLADE → PASSED_BLADE
- WAITING_CLEAR_ZONE → READING_ID → ID_CONFIRMED
- MOVING_TO_SORTER → SORTING → REMOVED
- COMPLETE / FAILED

---

## Key Components

### Central Output Buffer
```python
output_state.emitter = True
output_state.entry_conveyor = True
output_state.sorter1_belt = True
await output_writer.flush()  # ONLY place outputs are written
```

### Product Tracking
```python
product = product_tracker.create_product(vision_id, shape, color)
product.target_sorter = sorter_id
product_tracker.set_current_product_state(ProductState.READING_ID)
product_tracker.complete_product()
```

### Event System
```python
await event_manager.emit(SystemEvent.VISION_ID_READ, 
                        source="VisionSensor",
                        data={"product_id": 4})
```

### Timeout Protection
```python
timer = timer_manager.create_timer("vision_read", 3.0)
# ... do work ...
if timer.check_expired():
    # timeout occurred
```

---

## Async Control Loops

| Loop | Frequency | Tasks |
|------|-----------|-------|
| IO Scan | 50ms | Read inputs, update FSM, write outputs |
| Sorter Tick | 35ms | Sorter-specific logic |
| Supervision | 100ms | Check timers, watchdog, alarms |
| Telemetry | 150ms | Publish to MQTT/ThingsBoard |

---

## Getting Started

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure
- Edit `config.py` with your settings:
  - Modbus: `host`, `port`
  - MQTT: `broker`, `access_token`
  - Timing: scan intervals

### 3. Setup Factory I/O
- Enable Modbus TCP server (port 502)
- Map inputs/outputs as specified in `config_example.py`
- Test connection with Modbus explorer

### 4. Setup ThingsBoard
- Create device
- Get access token
- Update config with token
- Create dashboard

### 5. Run
```bash
python main.py
```

---

## Monitoring

### Console Output
- Real-time logs with timestamps
- Error messages and warnings
- System state changes

### Log File
```
logs/runtime.log
```

### ThingsBoard Dashboard
- System state display
- Current product info
- Throughput metrics
- Sorter activity
- Alarm status
- Scan cycle performance

### MQTT Topics
```
v1/devices/me/telemetry     # Metrics publishing
v1/devices/me/attributes    # Device attributes
v1/devices/me/rpc/...       # Remote procedure calls
```

---

## Troubleshooting

### "Failed to connect to Modbus"
- Check Factory I/O is running
- Verify Modbus server enabled (port 502)
- Check config.py host/port
- Run: `telnet localhost 502`

### "Failed to connect to MQTT"
- Check MQTT broker running
- Verify config.py broker address
- Check access token correct
- Connection is non-critical - system continues

### "Vision sensor not reading"
- Check vision sensor input address in Factory I/O
- Verify debounce time (50ms default)
- Check sensor returns 0-6 valid IDs
- See logs for timeout messages

### "Product stuck in WAITING_BLADE"
- Check blade motor connectivity
- Verify blade timeout (2 seconds)
- Check alarms in ThingsBoard

### High scan cycle time (>200ms)
- Watchdog will trigger failsafe
- Check CPU usage
- Reduce other background processes
- Increase system resources

---

## Design Principles Checklist

- ✅ Single active product pipeline
- ✅ No sleep-based synchronization
- ✅ Event-driven processing
- ✅ All operations timed out
- ✅ FSM owns outputs exclusively
- ✅ Central output buffer
- ✅ Thread-safe locks
- ✅ Failsafe on critical errors
- ✅ Edge-triggered sensors
- ✅ Pulsed emitter (not continuous)

---

## Output Mapping

| Function | Coil | Type |
|----------|------|------|
| Emitter | 0 | Pulse |
| Entry Conveyor | 1 | Coil |
| Exit Conveyor | 2 | Coil |
| Stop Blade | 3 | Coil (UP=1) |
| Sorter 1 Belt | 4 | Coil |
| Sorter 1 Turn | 5 | Coil |
| Sorter 2 Belt | 6 | Coil |
| Sorter 2 Turn | 7 | Coil |
| Sorter 3 Belt | 8 | Coil |
| Sorter 3 Turn | 9 | Coil |
| Remover 1 | 10 | Coil |
| Remover 2 | 11 | Coil |
| Remover 3 | 12 | Coil |
| Start Light | 13 | Coil |
| Stop Light | 14 | Coil |
| Reset Light | 15 | Coil |

---

## Input Mapping

| Function | Type | Register |
|----------|------|----------|
| Vision ID | Register | 0 |
| At Exit | Digital | 0 |
| Start Button | Digital | 1 |
| Stop Button | Digital | 2 |
| Emergency Stop | Digital | 3 |
| Auto Mode | Digital | 4 |
| Manual Mode | Digital | 5 |

---

## Key Metrics

- **Throughput**: Products/minute (telemetry: throughput_per_min)
- **Sort Time**: Average duration (telemetry: avg_sort_time_s)
- **Error Rate**: Failed/Total % (telemetry: error_rate)
- **Scan Cycle**: IO loop duration ms (telemetry: scan_cycle_ms)
- **Uptime**: System runtime seconds (telemetry: uptime_seconds)

---

## Command Line Options

```bash
# Normal operation
python main.py

# With debug logging (edit config.py)
# Change: setup_logging(logging.DEBUG)

# Check dependencies
pip list | grep -E "pymodbus|paho"

# View logs
tail -f logs/runtime.log

# Monitor MQTT (external terminal)
mosquitto_sub -h localhost -t "v1/devices/me/telemetry"
```

---

## Support Resources

- **README.md**: User guide & features
- **IMPLEMENTATION.md**: Architecture & design
- **config_example.py**: Configuration guide
- **Docstrings**: In-code documentation
- **Type hints**: Everywhere for IDE support

---

**Status**: ✅ Production Ready
**Version**: 1.0.0
**Python**: 3.8+
**License**: Proprietary Industrial Automation

---

## Quick Test

```python
# In Python REPL
from control.runtime_engine import RuntimeEngine
import asyncio

async def test():
    engine = RuntimeEngine()
    status = engine.get_status()
    print(status)

asyncio.run(test())
```

---

**For full details, see IMPLEMENTATION.md**
