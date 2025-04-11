"""
CAN Signal Handler for Stiebel Eltron heat pump communication.

This module handles the high-level signal operations, including tracking
signal values, providing callbacks, and managing state.
"""

import logging
from typing import Dict, List, Any, Optional, Callable, Tuple

from stiebel_control.can.protocol import StiebelProtocol

# Configure logger
logger = logging.getLogger(__name__)


class CanSignalHandler:
    """
    High-level handler for CAN signals.
    
    Tracks signal values, provides callbacks, and manages signal-related state.
    This is the main interface for application code to interact with the CAN bus.
    """
    
    def __init__(self, protocol: StiebelProtocol):
        """
        Initialize the signal handler.
        
        Args:
            protocol: The Stiebel protocol layer to use
        """
        self.protocol = protocol
        
        # Register ourselves as a signal handler with the protocol
        self.protocol.add_signal_handler(self._on_signal_update)
        
        # Dictionary to store latest values, keyed by (can_id, signal_name)
        self.latest_values: Dict[Tuple[int, str], Any] = {}
        
        # Dictionary to store per-signal callbacks, keyed by (can_id, signal_name)
        self.signal_callbacks: Dict[Tuple[int, str], List[Callable[[str, Any, int], None]]] = {}
        
        # General callbacks that receive all signals
        self.global_callbacks: List[Callable[[str, Any, int], None]] = []
    
    def add_signal_callback(self, signal_name: str, can_id: int, callback: Callable[[str, Any, int], None]):
        """
        Add a callback for a specific signal.
        
        Args:
            signal_name: Name of the signal
            can_id: CAN ID of the member
            callback: Callback function that takes (signal_name, value, can_id)
        """
        key = (can_id, signal_name)
        if key not in self.signal_callbacks:
            self.signal_callbacks[key] = []
        if callback not in self.signal_callbacks[key]:
            self.signal_callbacks[key].append(callback)
    
    def remove_signal_callback(self, signal_name: str, can_id: int, callback: Callable[[str, Any, int], None]):
        """
        Remove a callback for a specific signal.
        
        Args:
            signal_name: Name of the signal
            can_id: CAN ID of the member
            callback: The callback to remove
        """
        key = (can_id, signal_name)
        if key in self.signal_callbacks and callback in self.signal_callbacks[key]:
            self.signal_callbacks[key].remove(callback)
    
    def add_global_callback(self, callback: Callable[[str, Any, int], None]):
        """
        Add a callback for all signals.
        
        Args:
            callback: Function to call when any signal is received
        """
        if callback not in self.global_callbacks:
            self.global_callbacks.append(callback)
            
    def remove_global_callback(self, callback: Callable[[str, Any, int], None]):
        """
        Remove a global callback.
        
        Args:
            callback: Function to remove from global callbacks
        """
        if callback in self.global_callbacks:
            self.global_callbacks.remove(callback)
    
    def _on_signal_update(self, signal_name: str, value: Any, can_id: int):
        """
        Internal callback for when a signal is updated.
        
        Args:
            signal_name: Name of the signal updated
            value: New value of the signal
            can_id: CAN ID of the source
        """
        # Store the latest value
        key = (can_id, signal_name)
        self.latest_values[key] = value
        
        # Process callbacks
        self._process_callbacks(key, signal_name, value, can_id)
    
    def _process_callbacks(self, key: Tuple[int, str], signal_name: str, value: Any, can_id: int):
        """Process all callbacks for a signal update."""
        # Signal-specific callbacks
        for callback in self.signal_callbacks.get(key, []):
            self._call_callback(callback, signal_name, value, can_id)
            
        # Global callbacks
        for callback in self.global_callbacks:
            self._call_callback(callback, signal_name, value, can_id)
    
    def _call_callback(self, callback: Callable, signal_name: str, value: Any, can_id: int):
        """Safely call a callback with error handling."""
        try:
            callback(signal_name, value, can_id)
        except Exception as e:
            logger.error(f"Error in callback for {signal_name}: {e}")
    
    def read_signal(self, member_index: int, signal_name: str, callback: Optional[Callable] = None) -> bool:
        """
        Read a signal from a CAN member.
        
        Args:
            member_index: Index of the CAN member in the can_members list
            signal_name: Name of the signal to read
            callback: Optional one-time callback for the response
            
        Returns:
            bool: True if the request was sent successfully, False otherwise
        """
        return self.protocol.read_signal(member_index, signal_name, callback)
    
    def write_signal(self, member_index: int, signal_name: str, value: Any) -> bool:
        """
        Write a value to a signal on a CAN member.
        
        Args:
            member_index: Index of the CAN member in the can_members list
            signal_name: Name of the signal to write to
            value: Value to write
            
        Returns:
            bool: True if the request was sent successfully, False otherwise
        """
        return self.protocol.write_signal(member_index, signal_name, value)
    
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
        # Get the CAN member's ID
        member = self.protocol.can_members[member_index]
        member_id = member.can_id
        
        # First check the primary member
        value = self.latest_values.get((member_id, signal_name))
        if value is not None:
            return value
            
        # If a list of additional CAN IDs was provided, check those too
        if can_member_ids:
            for can_id in can_member_ids:
                value = self.latest_values.get((can_id, signal_name))
                if value is not None:
                    return value
                    
        # Fall back to primary member's value (which will be None at this point)
        return None
