"""
Stiebel Eltron specific CAN protocol implementation.

This module implements the protocol-specific logic for communicating
with Stiebel Eltron heat pumps over the CAN bus.
"""

import time
import logging
from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional, Callable, Any

from can import Message

from stiebel_control.can.transport import CanTransport
from stiebel_control.heatpump.elster_table import (
    get_elster_entry_by_index,
    value_from_signal,
    signal_from_value
)

# Configure logger
logger = logging.getLogger(__name__)


@dataclass
class CanMember:
    """Represents a CAN bus member with its addressing information."""
    name: str
    can_id: int
    read_id: Tuple[int, int]
    write_id: Tuple[int, int]
    confirmation_id: Tuple[int, int] = (0, 0)


class StiebelProtocol:
    """
    Protocol implementation for Stiebel Eltron heat pumps.
    
    This class handles the protocol details specific to Stiebel Eltron heat pumps,
    including message formatting and parsing, while delegating actual transport
    to the CanTransport layer.
    """
    
    # Default CAN members definition
    DEFAULT_CAN_MEMBERS = [
    # Name,        CAN ID,  Read ID,      Write ID,     Confirmation ID
    CanMember("HACLIENT", 0x680, (0x00, 0x00), (0x00, 0x00), (0xE2, 0x00)),  # This Client (Uses diagnostic software add.)
    CanMember("BOILER",   0x180, (0x31, 0x00), (0x30, 0x00), (0x00, 0x00)),  # Boiler
    CanMember("FE7X",     0x301, (0x61, 0x01), (0x00, 0x00), (0x00, 0x00)),  # FE7X
    CanMember("FEK",      0x302, (0x61, 0x02), (0x00, 0x00), (0x00, 0x00)),  # FEK
    CanMember("MANAGER",  0x480, (0x91, 0x00), (0x90, 0x00), (0x00, 0x00)),  # WPM2 Manager (typically)
    CanMember("HEATING",  0x500, (0xA1, 0x00), (0xA0, 0x00), (0x00, 0x00)),  # Heating Module
    CanMember("MIXER",    0x601, (0xC1, 0x01), (0xC0, 0x01), (0x00, 0x00)),  # Mixer Module
    CanMember("FE7",      0x602, (0xC1, 0x02), (0x00, 0x00), (0x00, 0x00)),
    ]
    
    # CAN member indices for easier reference
    CM_HACLIENT = 0
    CM_BOILER = 1
    CM_FE7X = 2
    CM_FEK = 3
    CM_MANAGER = 4
    CM_HEATING = 5
    CM_MIXER = 6
    CM_FE7 = 7
    
    def __init__(self, transport: CanTransport, can_members: List[CanMember] = None):
        """
        Initialize the protocol layer.
        
        Args:
            transport: The CAN transport layer to use
            can_members: Optional list of CanMember objects; defaults to DEFAULT_CAN_MEMBERS
        """
        self.transport = transport
        self.can_members = can_members or self.DEFAULT_CAN_MEMBERS
        
        # Set up the transport to use our message processor
        self.transport.message_processor = self._process_can_message
        
        # Signal handlers
        self.signal_handlers = []
        
        # Dictionary of pending requests, keyed by (can_id, index)
        self.pending_requests = {}
        
    def add_signal_handler(self, handler: Callable[[str, Any, int], None]):
        """
        Add a signal handler function that will be called when signals are received.
        
        Args:
            handler: Callback function that takes (signal_name, value, can_id)
        """
        if handler not in self.signal_handlers:
            self.signal_handlers.append(handler)
    
    def remove_signal_handler(self, handler: Callable[[str, Any, int], None]):
        """
        Remove a previously added signal handler.
        
        Args:
            handler: The handler to remove
        """
        if handler in self.signal_handlers:
            self.signal_handlers.remove(handler)
            
    def _process_can_message(self, msg: Message):
        """
        Process an incoming CAN message.
        
        Args:
            msg: CAN message received from the bus
        """
        try:
            can_id = msg.arbitration_id
            can_member = self._get_can_member(can_id)
            data = msg.data
            
            # Check message length
            if len(data) < 7:
                logger.debug(f"Ignoring short message from ID 0x{can_id:X}")
                return
                
            # Extract the index and value bytes from the message
            if data[2] == 0xFA:
                # Extended index format
                index = (data[3] << 8) + data[4]
                value_byte1 = data[5]
                value_byte2 = data[6]
            else:
                # Standard index format
                index = data[2]
                value_byte1 = data[3]
                value_byte2 = data[4]
            
            # Get the signal definition from the Elster table
            ei = get_elster_entry_by_index(index)
            
            # Calculate the raw value
            raw_value = (value_byte1 << 8) + value_byte2
            
            # Translate the value according to its type
            typed_value = value_from_signal(raw_value, ei.type)
            
            # Log the received signal
            logger.debug(f"CAN 0x{can_id:X}:{index} = {typed_value}")
            
            # If this is a response to a pending request, handle it
            request_key = (can_id, index)
            if request_key in self.pending_requests:
                request_info = self.pending_requests.pop(request_key)
                # If there's a callback, invoke it
                if request_info.get('callback'):
                    request_info['callback'](typed_value)
            
            # Notify all signal handlers
            for handler in self.signal_handlers:
                handler(ei.index, typed_value, can_id)
                
        except Exception as e:
            logger.error(f"Error processing CAN message: {e}")
    
    def _get_can_member(self, can_id: int) -> Optional[CanMember]:
        """
        Get a CAN member by its ID.
        
        Args:
            can_id: CAN ID of the member
            
        Returns:
            Optional[CanMember]: The CAN member if found, None otherwise
        """
        for member in self.can_members:
            if member.can_id == can_id:
                return member
        return None

    def read_signal(self, member_index: int, signal_index: int, callback: Optional[Callable] = None) -> bool:
        """
        Read a signal from a CAN member.
        
        Args:
            member_index: Index of the CAN member in the can_members list
            signal_index: Index of the signal to read (must exist in ElsterTable)
            callback: Optional callback for the response (will be called with the value)
            
        Returns:
            bool: True if the request was sent successfully, False otherwise
        """
        try:
            # Get the CAN member
            if member_index >= len(self.can_members):
                logger.error(f"Invalid CAN member index: {member_index}. Available members: {[m.name for m in self.can_members]}")
                return False
                
            member = self.can_members[member_index]
            
            # Get the signal definition
            ei = get_elster_entry_by_index(signal_index)
            if not ei:
                logger.error(f"Unknown signal: {signal_index}")
                return False
                
            logger.debug(f"Preparing to read signal {ei.english_name} (index {ei.index}) from member {member.name} (CAN ID 0x{member.can_id:X})")
            
            # Create the request message
            index_byte1 = (ei.index >> 8) & 0xFF
            index_byte2 = ei.index & 0xFF
            
            # Format the message depending on whether we need an extended index
            if index_byte1 == 0:
                data = [
                    member.read_id[0],
                    member.read_id[1],
                    index_byte2,
                    0x00,
                    0x00,
                    0x00,
                    0x00
                ]
            else:
                data = [
                    member.read_id[0],
                    member.read_id[1],
                    0xFA,
                    index_byte1,
                    index_byte2,
                    0x00,
                    0x00
                ]
                
            # Register the pending request
            if callback:
                self.pending_requests[(member.can_id, ei.index)] = {
                    'callback': callback,
                    'timestamp': time.time()
                }
                
            # Send the message using the transport layer
            success = self.transport.send_message(
                arbitration_id=self.can_members[self.CM_HACLIENT].can_id,
                data=data,
                is_extended_id=False
            )
            
            if success:
                logger.debug(f"Sent read request for {ei.english_name} to {member.name}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending read request: {e}")
            return False
            
    def write_signal(self, member_index: int, signal_index: int, value: Any) -> bool:
        """
        Write a value to a signal on a CAN member.
        
        Args:
            member_index: Index of the CAN member in the can_members list
            signal_name: Name of the signal to write to (must exist in ElsterTable)
            value: Value to write (will be converted according to the signal type)
            
        Returns:
            bool: True if the request was sent successfully, False otherwise
        """
        try:
            # Get the CAN member
            member = self.can_members[member_index]
            
            # Get the signal definition
            ei = get_elster_entry_by_index(signal_index)
            if not ei:
                logger.error(f"Unknown signal: {signal_index}")
                return False
                
            # Convert the value to the raw format
            if isinstance(value, str):
                raw_value = signal_from_value(value, ei.type)
            else:
                raw_value = signal_from_value(str(value), ei.type)
                
            # Create the request message
            index_byte1 = (ei.index >> 8) & 0xFF
            index_byte2 = ei.index & 0xFF
            value_byte1 = (raw_value >> 8) & 0xFF
            value_byte2 = raw_value & 0xFF
            
            # Format the message depending on whether we need an extended index
            if index_byte1 == 0:
                data = [
                    member.write_id[0],
                    member.write_id[1],
                    index_byte2,
                    value_byte1,
                    value_byte2,
                    0x00,
                    0x00
                ]
            else:
                data = [
                    member.write_id[0],
                    member.write_id[1],
                    0xFA,
                    index_byte1,
                    index_byte2,
                    value_byte1,
                    value_byte2
                ]
                
            # Send the message using the transport layer
            success = self.transport.send_message(
                arbitration_id=self.can_members[self.CM_HACLIENT].can_id,
                data=data,
                is_extended_id=False
            )
            
            if success:
                logger.debug(f"Sent write request for {signal_name}={value} to {member.name}")
                
                # After writing, we should read back the value to confirm
                self.read_signal(member_index, signal_name)
            
            return success
            
        except Exception as e:
            logger.error(f"Error sending write request: {e}")
            return False
