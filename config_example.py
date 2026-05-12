"""
Example configuration file.

Copy this to 'config_custom.py' and modify for your environment.
"""

from config import ModbusConfig, MQTTConfig, TimingConfig, TimeoutConfig

# === MODBUS CONFIGURATION ===
MODBUS_CONFIG = ModbusConfig(
    host="127.0.0.1",  # Factory I/O default
    port=502,           # Modbus TCP standard port
    unit_id=1,
    timeout=2.0,
    max_retries=3
)

# === MQTT CONFIGURATION ===
MQTT_CONFIG = MQTTConfig(
    broker="localhost",
    port=1883,
    access_token="YOUR_THINGSBOARD_TOKEN",
    ca_certs="",  # Set if using TLS
    tls_version=0,  # 0=no TLS, 3=TLSv1.2, 4=TLSv1.3
    clean_session=True
)

# === TIMING CONFIGURATION ===
TIMING_CONFIG = TimingConfig(
    io_scan_ms=50,              # Main IO scan cycle
    sorter_tick_ms=35,          # Sorter-specific updates
    supervision_ms=100,         # Timeout/alarm checks
    telemetry_ms=150,           # MQTT publish interval
    emitter_pulse_ms=200,       # Emitter pulse width
    blade_stabilize_delay_ms=500,  # Blade stabilization
    conveyor_ramp_ms=100        # Conveyor acceleration
)

# === TIMEOUT CONFIGURATION ===
TIMEOUT_CONFIG = TimeoutConfig(
    vision_read_timeout=3.0,    # Vision sensor read
    sort_timeout=5.0,           # Sorter removal
    jam_detection=12.0,         # Conveyor jam
    blade_timeout=2.0,          # Blade movement
    conveyor_timeout=10.0,      # Conveyor operation
    modbus_timeout=2.0          # Modbus communication
)

# === THINGSBOARD DASHBOARD SETUP ===
"""
Create a dashboard in ThingsBoard with these widgets:

1. SYSTEM STATE (Card)
   - Alias: System/State
   - Label: System State
   
2. CURRENT PRODUCT (Card)
   - Alias: Product/ID
   - Alias: Product/Shape
   - Alias: Product/Color
   - Alias: Product/Sorter

3. THROUGHPUT (Chart)
   - Alias: Throughput/PerMin
   
4. SORTER STATUS (Indicator)
   - Alias: Sorter/1/Active
   - Alias: Sorter/2/Active
   - Alias: Sorter/3/Active

5. ALARMS (Table)
   - Alias: Alarms/Active
   
6. PERFORMANCE (Gauge)
   - Alias: System/ScanCycleMs
   - Alias: System/ErrorRate

7. CONNECTIVITY (Indicator)
   - Alias: System/ModbusConnected
   - Alias: System/MqttConnected
"""

# === FACTORY I/O MODBUS MAPPING ===
"""
Configure Factory I/O like this:

[Modbus Server]
Enabled = True
Port = 502
Unit ID = 1

[Input Registers]
0 = Vision Sensor ID

[Discrete Inputs]
0 = At Exit Sensor
1 = Start Button
2 = Stop Button
3 = Emergency Stop
4 = Auto Mode
5 = Manual Mode

[Coils - Outputs]
0 = Emitter
1 = Entry Conveyor
2 = Exit Conveyor
3 = Stop Blade
4 = Sorter 1 Belt
5 = Sorter 1 Turn
6 = Sorter 2 Belt
7 = Sorter 2 Turn
8 = Sorter 3 Belt
9 = Sorter 3 Turn
10 = Remover 1
11 = Remover 2
12 = Remover 3
13 = Start Light
14 = Stop Light
15 = Reset Light
"""

# === STARTUP CHECKLIST ===
"""
Before running the runtime:

1. ✓ Factory I/O Modbus configured on port 502
2. ✓ Modbus slave devices mapped as above
3. ✓ MQTT broker running (mosquitto or other)
4. ✓ ThingsBoard running and accessible
5. ✓ Device and access token created in ThingsBoard
6. ✓ Python 3.8+ installed
7. ✓ Dependencies installed: pip install -r requirements.txt
8. ✓ This config file reviewed and customized
9. ✓ Logs directory writable
"""

if __name__ == "__main__":
    print("Configuration loaded successfully")
    print(f"Modbus: {MODBUS_CONFIG.host}:{MODBUS_CONFIG.port}")
    print(f"MQTT: {MQTT_CONFIG.broker}:{MQTT_CONFIG.port}")
    print(f"IO Scan: {TIMING_CONFIG.io_scan_ms}ms")
