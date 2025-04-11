"""
CAN Interface facade for Stiebel Eltron heat pump communication.

This module provides an interface that integrates
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
        
        # Store the callback for property access
        self._callback = callback
        
        # If a callback was provided, add it as a global callback
        if callback:
            self.signal_handler.add_global_callback(callback)
        
        # Flag to track if the interface is running
        self.running = False
    
    @property
    def callback(self) -> Optional[Callable[[str, Any, int], None]]:
        """Get the current global callback."""
        return self._callback
        
    @callback.setter
    def callback(self, callback: Optional[Callable[[str, Any, int], None]]):
        """Set a new global callback and register it with the signal handler."""
        # If we had a previous callback, remove it
        if self._callback:
            self.signal_handler.remove_global_callback(self._callback)
            
        # Store the new callback
        self._callback = callback
        
        # Register with the signal handler if not None
        if callback:
            self.signal_handler.add_global_callback(callback)
        
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
    
    def add_signal_callback(self, signal_name: str, can_id: int, callback: Callable[[str, Any, int], None]) -> None:
        """
        Add a callback for a specific signal.
        
        Args:
            signal_name: Name of the signal to subscribe to
            can_id: CAN ID of the member
            callback: Callback function that will be called when the signal is updated
        """
        self.signal_handler.add_signal_callback(signal_name, can_id, callback)
        
    def get_can_id_by_name(self, member_name: str) -> Optional[int]:
        """
        Get the CAN ID corresponding to a member name.
        
        Args:
            member_name: Name of the CAN member (e.g., 'PUMP', 'MANAGER')
            
        Returns:
            int: CAN ID if found, None otherwise
        """
        for member in self.can_members:
            if member.name == member_name:
                return member.can_id
        return None
        
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
