# Industrial Control Runtime for Sorting Station

## Core Architecture

### System Philosophy
- **NOT** an automation script, but a **Soft PLC Runtime**
- Replaces PLC, TIA Portal, and Ladder Logic
- Python-based deterministic control engine
- Event-driven architecture with async coroutines

### Guiding Principles

1. **Single Active Product Pipeline**: Only 1 product in system at any time
2. **Deterministic Timing**: Scan cycle driven, not sleep-based
3. **Event-Driven Logic**: No polling, event handlers only
4. **Timeout Protection**: Every operation has timeout
5. **State Machine Owns Outputs**: Only FSM controls OutputState
6. **Central Output Buffer**: No direct Modbus writes, only through OutputState
7. **Async Lock Protection**: Critical state protected by asyncio.Lock
8. **Failsafe on Error**: Any critical error triggers shutdown
9. **Edge-Triggered Sensors**: Vision sensor uses 0→X transitions only
10. **Pulsed Emitter**: Emitter must pulse, never continuous

## Project Structure

```
project/
├── main.py                    # Entry point
├── config.py                  # Configuration
├── models/                    # Data models
│   ├── product.py             # Product lifecycle
│   ├── system_state.py        # System FSM state
│   ├── output_state.py        # Modbus output buffer
│   └── input_snapshot.py      # Immutable input snapshot
├── drivers/                   # Hardware communication
│   ├── modbus_client.py       # Modbus TCP
│   ├── input_reader.py        # Input scanning (50ms)
│   └── output_writer.py       # Output writing
├── control/                   # Control logic
│   ├── runtime_engine.py      # Main runtime orchestrator
│   ├── state_machine.py       # System FSM
│   ├── product_tracking.py    # Product lifecycle
│   ├── sorting_logic.py       # Product routing
│   ├── event_manager.py       # Event system
│   ├── timers.py              # Timeout management
│   ├── debounce.py            # Sensor debounce
│   └── watchdog.py            # Runtime watchdog
├── alarms/                    # Fault handling
│   ├── alarm_manager.py       # Alarm tracking
│   └── fault_handler.py       # Failsafe shutdown
├── telemetry/                 # MQTT & metrics
│   ├── mqtt_client.py         # MQTT communication
│   ├── metrics.py             # Metrics collection
│   └── publisher.py           # ThingsBoard publisher
├── utils/                     # Utilities
└── logs/                      # Log files
```

## Control Flow

```
EMITTER PULSE
    ↓
ENTRY CONVEYOR MOVES
    ↓
STOP BLADE: UP → PRODUCT PASSES
    ↓
WAIT_CLEAR_ZONE (prevent overlap)
    ↓
VISION READS ID
    ↓
VALIDATE & ROUTE PRODUCT
    ↓
STOP BLADE: DOWN
    ↓
ENTRY CONVEYOR PAUSES
    ↓
EXIT CONVEYOR RUNS
    ↓
PRODUCT MOVES TO SORTER
    ↓
SORTER ACTIVATED
    ↓
REMOVER TRIGGERS
    ↓
PRODUCT REMOVED
    ↓
SORTER RESET
    ↓
PIPELINE CLEARED
    ↓
NEXT PRODUCT ALLOWED
```

## Product Mapping

| ID | Shape   | Color | Sorter |
|----|---------|-------|--------|
| 1  | Flat    | Blue  | 1      |
| 2  | Flat    | Green | 1      |
| 3  | Circle  | Blue  | 2      |
| 4  | Circle  | Green | 2      |
| 5  | Complex | Blue  | 3      |
| 6  | Complex | Green | 3      |

## Async Control Loops

### IO Scan Loop (50ms)
- Read all inputs (single bulk read)
- Process input logic
- Update FSM state
- Flush changed outputs only
- Record timing metrics

### Sorter Tick Loop (35ms)
- Sorter FSM state transitions
- Remover activation timing
- Sorter-specific logic

### Supervision Loop (100ms)
- Check timeout timers
- Monitor watchdog heartbeats
- Track alarm status
- Handle critical states

### Telemetry Loop (150ms)
- Publish metrics to MQTT
- Send to ThingsBoard
- Handle RPC commands

## Timeouts (seconds)

| Operation | Timeout |
|-----------|---------|
| Vision read | 3.0 |
| Sort operation | 5.0 |
| Jam detection | 12.0 |
| Blade movement | 2.0 |
| Conveyor operation | 10.0 |
| Modbus communication | 2.0 |

## Output Signals

All outputs controlled through OutputState buffer:

**Conveyors:**
- Emitter (pulse only)
- Entry conveyor
- Exit conveyor

**Stop Blade:**
- Stop blade (UP=True, DOWN=False)

**Sorters:**
- Sorter 1: belt, turn
- Sorter 2: belt, turn
- Sorter 3: belt, turn

**Removers:**
- Remover 1, 2, 3

**Indicators:**
- Start light, Stop light, Reset light

## Input Signals

**Analog:**
- Vision sensor ID (0-6)

**Digital:**
- At exit sensor
- Start button
- Stop button
- Emergency stop
- Auto mode
- Manual mode

## Telemetry Payload

Published to ThingsBoard every 150ms:

```json
{
  "system_state": "RUNNING",
  "current_product_id": 4,
  "current_product_shape": "Circle",
  "current_product_color": "Green",
  "current_product_sorter": 2,
  "throughput_per_min": 12.5,
  "avg_sort_time_s": 4.3,
  "error_rate": 0.0,
  "scan_cycle_ms": 45,
  "modbus_connected": true,
  "mqtt_connected": true,
  "total_products": 45,
  "successful_sorts": 44,
  "failed_sorts": 1,
  "alarm_count": 0,
  "uptime_seconds": 3600
}
```

## Key Features Implemented

### Runtime Engine
- ✅ Main orchestrator
- ✅ Multiple async coroutines
- ✅ Signal handling
- ✅ Error recovery

### State Management
- ✅ System FSM (13 states)
- ✅ Product lifecycle (10 states)
- ✅ Output buffer management
- ✅ Thread-safe updates

### Input/Output
- ✅ Bulk input reading
- ✅ Edge-triggered vision
- ✅ Vision debouncing
- ✅ Shadow state output optimization
- ✅ Retry logic

### Control Logic
- ✅ Sorting logic & routing
- ✅ Product tracking
- ✅ Event system
- ✅ Timeout management
- ✅ Watchdog monitoring

### Fault Handling
- ✅ Alarm system
- ✅ Failsafe shutdown
- ✅ Error recovery
- ✅ Modbus error handling

### Telemetry
- ✅ MQTT publishing
- ✅ Metrics collection
- ✅ ThingsBoard integration
- ✅ Real-time monitoring

## Running the System

### Installation
```bash
pip install -r requirements.txt
```

### Configuration
Edit `config.py`:
- Modbus host/port (default: localhost:502)
- MQTT broker (default: localhost:1883)
- Scan cycle times
- Timeout values

### Start Runtime
```bash
python main.py
```

### Monitor
- Check logs in `logs/runtime.log`
- View ThingsBoard dashboard
- Monitor MQTT topics

## Design Rules

| Rule | Description |
|------|-------------|
| RULE 1 | Only one active product |
| RULE 2 | No fixed sleep synchronization |
| RULE 3 | Always use event-driven logic |
| RULE 4 | All operations require timeout |
| RULE 5 | Only state machine owns outputs |
| RULE 6 | All Modbus writes through output buffer |
| RULE 7 | Critical state protected by locks |
| RULE 8 | Critical error triggers failsafe |
| RULE 9 | Use edge-triggered sensor logic |
| RULE 10 | Python acts as industrial runtime |

## Future Enhancements

- Computer vision integration
- Advanced AI for routing
- Network redundancy
- High availability mode
- Dashboard extensions
- Mobile app integration
- Historical data storage
- Predictive maintenance

---

**Status**: Production-Ready
**Version**: 1.0.0
**Last Updated**: 2026-05-12
