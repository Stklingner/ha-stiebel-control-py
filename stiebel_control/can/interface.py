"""
CAN Interface for Stiebel Eltron heat pump communication.

This module provides a direct interface to the CAN bus for
interacting with Stiebel Eltron heat pump components.
"""

import logging
from typing import Dict, List, Optional, Callable, Any, Tuple

from stiebel_control.can.transport import CanTransport
from stiebel_control.can.protocol import StiebelProtocol, CanMember

# Configure logger
logger = logging.getLogger(__name__)


class CanInterface:
    """
    Interface for CAN communication.
    
    This class provides direct access to the CAN bus and
    handles signal tracking, callback management, and signal processing.
    """
    
    def __init__(self, can_interface: str = 'can0', 
                 can_members: List[CanMember] = None, 
                 bitrate: int = 20000, 
                 callback: Optional[Callable[[int, Any, int], None]] = None):
        """Initialize the CAN interface.
        
        Args:
            can_interface: Name of the CAN interface (e.g., 'can0')
            can_members: Optional list of CanMember objects; defaults to DEFAULT_CAN_MEMBERS
            bitrate: CAN bus bitrate, default is 20000 for Stiebel Eltron heat pumps
            callback: Optional callback function for value updates (signal_index, value, can_id)
        """
        # Create the layered components
        self.transport = CanTransport(can_interface, bitrate)
        self.protocol = StiebelProtocol(self.transport, can_members)
        
        # Register with the protocol as a signal handler
        self.protocol.add_signal_handler(self._on_signal_update)
        
        # Store parameters
        self.can_interface = can_interface
        self.can_members = can_members or self.protocol.DEFAULT_CAN_MEMBERS
        self.bitrate = bitrate
        
        # Dictionary to store latest values, keyed by (can_id, signal_index)
        self.latest_values: Dict[Tuple[int, int], Any] = {}
        
        # Dictionary to store per-signal callbacks, keyed by (can_id, signal_index)
        self.signal_callbacks: Dict[Tuple[int, int], List[Callable[[int, Any, int], None]]] = {}
        
        # General callbacks that receive all signals
        self.global_callbacks: List[Callable[[int, Any, int], None]] = []
        
        # Store the callback for property access
        self._callback = None
        
        # If a callback was provided, add it as a global callback
        if callback:
            self.add_global_callback(callback)
        
        # Flag to track if the interface is running
        self.running = False
    
    @property
    def callback(self) -> Optional[Callable[[int, Any, int], None]]:
        """Get the current global callback."""
        return self._callback
        
    @callback.setter
    def callback(self, callback: Optional[Callable[[int, Any, int], None]]):
        """Set a new global callback."""
        # If we had a previous callback, remove it
        if self._callback and self._callback in self.global_callbacks:
            self.remove_global_callback(self._callback)
            
        # Store the new callback
        self._callback = callback
        
        # Register it if not None
        if callback:
            self.add_global_callback(callback)
    
    def _on_signal_update(self, signal_index: int, value: Any, can_id: int):
        """
        Internal callback for when a signal is updated.
        
        Args:
            signal_index: Index of the signal updated
            value: New value of the signal
            can_id: CAN ID of the source
        """
        # Store the latest value
        key = (can_id, signal_index)
        self.latest_values[key] = value
        
        # Process callbacks
        self._process_callbacks(key, signal_index, value, can_id)
    
    def _process_callbacks(self, key: Tuple[int, int], signal_index: int, value: Any, can_id: int):
        """Process all callbacks for a signal update."""
        # Signal-specific callbacks
        for callback in self.signal_callbacks.get(key, []):
            self._call_callback(callback, signal_index, value, can_id)
            
        # Global callbacks
        for callback in self.global_callbacks:
            self._call_callback(callback, signal_index, value, can_id)
    
    def _call_callback(self, callback: Callable, signal_index: int, value: Any, can_id: int):
        """Safely call a callback with error handling."""
        try:
            callback(signal_index, value, can_id)
        except Exception as e:
            logger.error(f"Error in callback for signal {signal_index}: {e}")
        
    def start(self):
        """Start the CAN interface."""
        success = self.transport.start()
        self.running = success
        return success
    
    def stop(self):
        """Stop the CAN interface."""
        self.transport.stop()
        self.running = False
    
    def read_signal(self, member_index: int, signal_index: int, callback: Optional[Callable] = None) -> bool:
        """
        Read a signal from a CAN member.
        
        Args:
            member_index: Index of the CAN member in the can_members list
            signal_index: Index of the signal to read
            callback: Optional callback for the response (will be called with the value)
            
        Returns:
            bool: True if the request was sent successfully, False otherwise
        """
        return self.protocol.read_signal(member_index, signal_index, callback)
    
    def write_signal(self, member_index: int, signal_index: int, value: Any) -> bool:
        """
        Write a value to a signal on a CAN member.
        
        Args:
            member_index: Index of the CAN member in the can_members list
            signal_index: Index of the signal to write to
            value: Value to write (will be converted according to the signal type)
            
        Returns:
            bool: True if the request was sent successfully, False otherwise
        """
        return self.protocol.write_signal(member_index, signal_index, value)
    
    def add_signal_callback(self, signal_index: int, can_id: int, callback: Callable[[int, Any, int], None]) -> None:
        """
        Add a callback for a specific signal.
        
        Args:
            signal_index: Index of the signal to subscribe to
            can_id: CAN ID of the member
            callback: Callback function that will be called when the signal is updated
        """
        key = (can_id, signal_index)
        if key not in self.signal_callbacks:
            self.signal_callbacks[key] = []
        if callback not in self.signal_callbacks[key]:
            self.signal_callbacks[key].append(callback)
    
    def remove_signal_callback(self, signal_index: int, can_id: int, callback: Callable[[int, Any, int], None]) -> None:
        """
        Remove a callback for a specific signal.
        
        Args:
            signal_index: Index of the signal
            can_id: CAN ID of the member
            callback: The callback to remove
        """
        key = (can_id, signal_index)
        if key in self.signal_callbacks and callback in self.signal_callbacks[key]:
            self.signal_callbacks[key].remove(callback)
            
    def add_global_callback(self, callback: Callable[[int, Any, int], None]) -> None:
        """
        Add a callback for all signals.
        
        Args:
            callback: Function to call when any signal is received
        """
        if callback not in self.global_callbacks:
            self.global_callbacks.append(callback)
            
    def remove_global_callback(self, callback: Callable[[int, Any, int], None]) -> None:
        """
        Remove a global callback.
        
        Args:
            callback: Function to remove from global callbacks
        """
        if callback in self.global_callbacks:
            self.global_callbacks.remove(callback)
        
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
    
    def get_member_name_by_can_id(self, can_id: int) -> Optional[str]:
        """
        Get the member name corresponding to a CAN ID.
        
        Args:
            can_id: CAN ID of the member
            
        Returns:
            str: Member name if found, None otherwise
        """
        for member in self.can_members:
            if member.can_id == can_id:
                return member.name
        return None
        
    def get_latest_value(self, signal_index: int, can_id: int) -> Optional[Any]:
        """
        Get the latest value for a signal.
        
        Args:
            signal_index: Index of the signal
            can_id: CAN ID of the member
            
        Returns:
            The latest value if available, None otherwise
        """
        key = (can_id, signal_index)
        return self.latest_values.get(key)
        
    def set_value(self, can_id: int, signal_index: int, value: Any) -> bool:
        """
        Set a value on the CAN bus.
        
        Args:
            can_id: CAN ID of the target device
            signal_index: Index of the signal to set
            value: Value to set
            
        Returns:
            bool: True if successful, False otherwise
        """
        # Find the member index for the given CAN ID
        member_index = None
        for i, member in enumerate(self.can_members):
            if member.can_id == can_id:
                member_index = i
                break
                
        if member_index is None:
            logger.error(f"Cannot set value: unknown CAN ID 0x{can_id:X}")
            return False
            
        return self.write_signal(member_index, signal_index, value)
