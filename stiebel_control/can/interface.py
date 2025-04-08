"""
CAN Interface facade for Stiebel Eltron heat pump communication.

This module provides a backward-compatible interface that integrates
the layered CAN components (transport, protocol, signal_handler) for
easy integration with existing code.
"""

import logging
from typing import List, Optional, Callable, Any

from stiebel_control.can.transport import CanTransport
from stiebel_control.can.protocol import StiebelProtocol, CanMember
from stiebel_control.can.signal_handler import CanSignalHandler

# Configure logger
logger = logging.getLogger(__name__)


class CanInterface:
    """
    Facade for CAN communication components.
    
    This class provides a backward-compatible interface for the existing code
    while utilizing the new layered architecture internally.
    """
    
    # CAN member indices - maintaining compatibility with the original interface
    CM_ESPCLIENT = 0
    CM_PUMP = 1
    CM_FE7X = 2
    CM_FEK = 3
    CM_MANAGER = 4
    CM_HEATING = 5
    CM_FE7 = 6
    
    def __init__(self, can_interface: str = 'can0', 
                 can_members: List[CanMember] = None, 
                 bitrate: int = 20000, 
                 callback: Optional[Callable[[str, Any, int], None]] = None):
        """Initialize the CAN interface.
        
        Args:
            can_interface: Name of the CAN interface (e.g., 'can0')
            can_members: Optional list of CanMember objects; defaults to DEFAULT_CAN_MEMBERS
            bitrate: CAN bus bitrate, default is 20000 for Stiebel Eltron heat pumps
            callback: Optional callback function for value updates
        """
        # Create the layered components
        self.transport = CanTransport(can_interface, bitrate)
        self.protocol = StiebelProtocol(self.transport, can_members)
        self.signal_handler = CanSignalHandler(self.protocol)
        
        # Store parameters
        self.can_interface = can_interface
        self.can_members = can_members or self.protocol.DEFAULT_CAN_MEMBERS
        self.bitrate = bitrate
        
        # If a callback was provided, add it as a global callback
        if callback:
            self.signal_handler.add_global_callback(callback)
        
        # Flag to track if the interface is running
        self.running = False
        
    def start(self):
        """Start the CAN interface."""
        success = self.transport.start()
        self.running = success
        return success
    
    def stop(self):
        """Stop the CAN interface."""
        self.transport.stop()
        self.running = False
    
    def read_signal(self, member_index: int, signal_name: str, callback: Optional[Callable] = None) -> bool:
        """
        Read a signal from a CAN member.
        
        Args:
            member_index: Index of the CAN member in the can_members list
            signal_name: Name of the signal to read (must exist in ElsterTable)
            callback: Optional callback for the response (will be called with the value)
            
        Returns:
            bool: True if the request was sent successfully, False otherwise
        """
        return self.signal_handler.read_signal(member_index, signal_name, callback)
    
    def write_signal(self, member_index: int, signal_name: str, value: Any) -> bool:
        """
        Write a value to a signal on a CAN member.
        
        Args:
            member_index: Index of the CAN member in the can_members list
            signal_name: Name of the signal to write to (must exist in ElsterTable)
            value: Value to write (will be converted according to the signal type)
            
        Returns:
            bool: True if the request was sent successfully, False otherwise
        """
        return self.signal_handler.write_signal(member_index, signal_name, value)
    
    def get_latest_value(self, member_index: int, signal_name: str, can_member_ids: List[int] = None) -> Optional[Any]:
        """
        Get the latest value for a signal.
        
        Args:
            member_index: Primary index of the CAN member
            signal_name: Name of the signal
            can_member_ids: Optional list of specific CAN IDs to check in addition to the primary member
            
        Returns:
            The latest value if available, None otherwise
        """
        return self.signal_handler.get_latest_value(member_index, signal_name, can_member_ids)
    
    @property
    def latest_values(self):
        """
        Provide backward compatibility access to latest values.
        
        The data structure is different from the original implementation,
        but this property provides the expected interface.
        """
        # The original uses (can_id, index) as keys, but our new implementation uses (can_id, signal_name)
        # For now, just pass through to signal_handler's latest_values
        # In a real implementation, we'd need to convert between the two formats
        return self.signal_handler.latest_values
