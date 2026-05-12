"""
Modbus TCP client for Factory I/O communication.

Library: pymodbus
"""
import logging
from typing import Dict, List, Optional
from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ModbusException, ConnectionException
from config import ModbusConfig


logger = logging.getLogger(__name__)


class ModbusClient:
    """
    Manages Modbus TCP connection to Factory I/O.
    
    Handles:
    - Connection lifecycle
    - Bulk read operations
    - Coil writes with retry logic
    - Error recovery
    """

    def __init__(self, config: ModbusConfig):
        """Initialize Modbus client."""
        self.config = config
        self.client = ModbusTcpClient(
            host=config.host,
            port=config.port,
            timeout=config.timeout
        )
        self.connected = False
        self.last_error: Optional[str] = None

    async def connect(self) -> bool:
        """
        Connect to Modbus server.
        
        Returns:
            True if connected successfully.
        """
        try:
            result = self.client.connect()
            self.connected = result
            if result:
                logger.info(f"Modbus connected to {self.config.host}:{self.config.port}")
            else:
                self.last_error = "Failed to connect to Modbus server"
                logger.error(self.last_error)
            return result
        except ConnectionException as e:
            self.connected = False
            self.last_error = f"Connection error: {str(e)}"
            logger.error(self.last_error)
            return False

    async def disconnect(self) -> None:
        """Disconnect from Modbus server."""
        if self.client:
            self.client.close()
            self.connected = False
            logger.info("Modbus disconnected")

    async def read_discrete_inputs(self, address: int = 0, count: int = 6) -> Optional[List[bool]]:
        """
        Read discrete inputs (digital inputs).
        
        Args:
            address: Starting address
            count: Number of inputs to read
            
        Returns:
            List of boolean values or None on error.
        """
        if not self.connected:
            self.last_error = "Not connected to Modbus server"
            return None

        try:
            response = self.client.read_discrete_inputs(
                address=address,
                count=count,
                slave=self.config.unit_id
            )
            
            if response.isError():
                self.last_error = f"Read discrete inputs error: {response}"
                logger.error(self.last_error)
                return None
            
            return list(response.bits)
            
        except (ModbusException, ConnectionException) as e:
            self.connected = False
            self.last_error = f"Modbus read error: {str(e)}"
            logger.error(self.last_error)
            return None

    async def read_input_registers(self, address: int = 0, count: int = 1) -> Optional[List[int]]:
        """
        Read input registers (analog inputs).
        
        Args:
            address: Starting address
            count: Number of registers to read
            
        Returns:
            List of register values or None on error.
        """
        if not self.connected:
            self.last_error = "Not connected to Modbus server"
            return None

        try:
            response = self.client.read_input_registers(
                address=address,
                count=count,
                slave=self.config.unit_id
            )
            
            if response.isError():
                self.last_error = f"Read input registers error: {response}"
                logger.error(self.last_error)
                return None
            
            return list(response.registers)
            
        except (ModbusException, ConnectionException) as e:
            self.connected = False
            self.last_error = f"Modbus read error: {str(e)}"
            logger.error(self.last_error)
            return None

    async def write_coil(self, address: int, value: bool, retries: int = 0) -> bool:
        """
        Write a single coil.
        
        Args:
            address: Coil address
            value: True/False value
            retries: Number of retries on failure
            
        Returns:
            True if write successful.
        """
        if not self.connected:
            self.last_error = "Not connected to Modbus server"
            return False

        retry_count = 0
        while retry_count <= retries:
            try:
                response = self.client.write_coil(
                    address=address,
                    value=value,
                    slave=self.config.unit_id
                )
                
                if response.isError():
                    self.last_error = f"Write coil error at address {address}: {response}"
                    retry_count += 1
                    if retry_count > retries:
                        logger.error(self.last_error)
                        return False
                    continue
                
                return True
                
            except (ModbusException, ConnectionException) as e:
                self.connected = False
                self.last_error = f"Modbus write error: {str(e)}"
                retry_count += 1
                if retry_count > retries:
                    logger.error(self.last_error)
                    return False

        return False

    async def write_coils(self, address: int, values: List[bool], retries: int = 0) -> bool:
        """
        Write multiple coils.
        
        Args:
            address: Starting address
            values: List of boolean values
            retries: Number of retries on failure
            
        Returns:
            True if write successful.
        """
        if not self.connected:
            self.last_error = "Not connected to Modbus server"
            return False

        retry_count = 0
        while retry_count <= retries:
            try:
                response = self.client.write_coils(
                    address=address,
                    values=values,
                    slave=self.config.unit_id
                )
                
                if response.isError():
                    self.last_error = f"Write coils error at address {address}: {response}"
                    retry_count += 1
                    if retry_count > retries:
                        logger.error(self.last_error)
                        return False
                    continue
                
                return True
                
            except (ModbusException, ConnectionException) as e:
                self.connected = False
                self.last_error = f"Modbus write error: {str(e)}"
                retry_count += 1
                if retry_count > retries:
                    logger.error(self.last_error)
                    return False

        return False

    def is_connected(self) -> bool:
        """Check if Modbus is connected."""
        return self.connected

    def get_last_error(self) -> Optional[str]:
        """Get last error message."""
        return self.last_error
