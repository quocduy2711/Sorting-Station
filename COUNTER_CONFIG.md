# Remover Counter Configuration Guide

## Problem Solved
✅ **Issue**: Remover counters showed 0 on ThingsBoard and Factory IO electrical box  
✅ **Root Cause**: Counters were tracked in Python but NOT written back to Modbus  
✅ **Solution**: Added Modbus holding register writes for counter values  

## How It Works

### Data Flow
```
1. Product falls into remover → InputReader detects at_exit sensor
2. RuntimeService emits AT_EXIT_TRIGGERED event
3. SortingService._on_at_exit() handler:
   - Increments SystemState.remover_counts
   - Calls output_writer.write_counter(remover_id, count)
4. OutputWriter writes counter to Modbus holding register
5. Factory IO electrical box reads register and displays count
6. TelemetryService publishes count to ThingsBoard
```

## Modbus Register Configuration

### Default Addresses (adjust if needed)
```
Remover 1 Count: Holding Register 100 (0x64)
Remover 2 Count: Holding Register 101 (0x65)
Remover 3 Count: Holding Register 102 (0x66)
```

### How to Find Your Addresses

1. **In Factory IO**, check the Modbus Master configuration:
   - Right-click Modbus Master → Properties
   - Look at "Holding Registers" section
   - Find where your counter displays are reading from
   - Note the register addresses

2. **Example**: If counter displays read from registers 100, 101, 102, keep defaults.

3. **If different**: Update `output_writer.py`:

```python
REGISTER_MAP: Dict[str, int] = {
    "remover1_count": 100,  # Change to your address
    "remover2_count": 101,  # Change to your address
    "remover3_count": 102,  # Change to your address
}
```

## Testing the Fix

### 1. Check Logs
Run the application and look for:
```
[INFO    ] Wrote counter register remover1_count (addr 100) = 1
[INFO    ] Wrote counter register remover2_count (addr 101) = 2
[INFO    ] Wrote counter register remover3_count (addr 102) = 1
```

### 2. Verify Factory IO Display
- Run Factory IO simulation
- Watch the electrical box counters update as products are sorted
- They should match the logs

### 3. Check ThingsBoard
- Go to ThingsBoard dashboard
- View "Latest telemetry"
- Check: `remover1_count`, `remover2_count`, `remover3_count`
- Values should match Factory IO display

### 4. Check Modbus Registers
In Factory IO Modbus viewer:
1. STOP the simulation
2. Go to Modbus → View Registers
3. Check Holding Registers 100, 101, 102
4. Values should show current counts
5. Start simulation again

## File Changes

### Modified Files
- `drivers/modbus_client.py` - Added write_register() and write_registers()
- `drivers/output_writer.py` - Added counter register mapping and write methods
- `services/sorting_service.py` - Updated to write counters on product drop
- `services/runtime_service.py` - Initialize counters on startup

### New Methods
```python
# Write single counter to Modbus
await output_writer.write_counter(remover_id=1, count=5)

# Write all counters at once
await output_writer.write_all_counters({1: 5, 2: 3, 2: 1})

# ModbusClient methods
await modbus.write_register(address=100, value=5)
await modbus.write_registers(address=100, values=[5, 3, 1])
```

## Troubleshooting

### Counters Still Show 0
1. ✅ Check logs for "write_counter" messages
2. ✅ Verify Modbus connection is OK (not degraded mode)
3. ✅ Confirm REGISTER_MAP addresses match Factory IO setup
4. ✅ Check Factory IO Modbus viewer - registers may have wrong addresses there

### Modbus Write Errors
```
[ERROR   ] Failed to write counter register remover1_count
```
**Solutions**:
- Verify Modbus connection is connected (not degraded mode)
- Check network connectivity to Factory IO / Modbus device
- Confirm register addresses are valid (should be 0-65535)

### Factory IO Display Not Updating
1. Check Modbus registers are being written (Factory IO Modbus viewer)
2. Verify your counter displays read from correct registers
3. Check Factory IO Modbus server is running
4. Restart Factory IO simulation

## Shadow State Optimization

To avoid excessive Modbus writes, counter values are only written if they changed:
```python
# Only writes if value is different from previous write
if self._last_counter_values.get(reg_name) == count:
    return True  # Skip write, value unchanged
```

This reduces Modbus traffic and improves performance.

## Reset Counters

To reset all counters to 0:
```python
# In code
system_state.remover_counts = {1: 0, 2: 0, 3: 0}
await output_writer.write_all_counters({1: 0, 2: 0, 3: 0})

# Via RPC command (recommended)
# Add reset_counters RPC handler in mqtt_rpc_listener.py
```

---

**Questions or issues?** Check the logs for detailed Modbus write feedback.
