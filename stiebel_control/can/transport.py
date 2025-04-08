"""
CAN Transport layer for Stiebel Eltron heat pump communication.

This module handles the low-level communication with the CAN bus
via the python-can library.
"""

import logging
import threading
from typing import Optional, Callable, Dict, Any

import can
from can import Message

# Configure logger
logger = logging.getLogger(__name__)


class CanTransport:
    """
    Low-level CAN bus transport layer.
    
    Handles connection to the CAN bus and raw message sending/receiving
    without any protocol-specific knowledge.
    """
    
    def __init__(self, can_interface: str = 'can0', 
                 bitrate: int = 20000,
                 message_processor: Optional[Callable[[Message], None]] = None):
        """Initialize the CAN transport.
        
        Args:
            can_interface: Name of the CAN interface (e.g., 'can0')
            bitrate: CAN bus bitrate, default is 20000 for Stiebel Eltron heat pumps
            message_processor: Callback function for processing received messages
        """
        self.can_interface = can_interface
        self.bitrate = bitrate
        self.message_processor = message_processor
        self.bus = None
        self.running = False
        self.receiver_thread = None
        
    def start(self) -> bool:
        """
        Start the CAN transport.
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        try:
            self.bus = can.interface.Bus(
                channel=self.can_interface,
                bustype='socketcan',
                bitrate=self.bitrate
            )
            self.running = True
            logger.info(f"CAN transport started on {self.can_interface}")
            
            # Start the message receiver in a separate thread
            self.receiver_thread = threading.Thread(
                target=self._receive_messages,
                daemon=True  # Allow the thread to exit when the main program exits
            )
            self.receiver_thread.start()
            logger.info("CAN message receiver thread started")
            
            return True
        except Exception as e:
            logger.error(f"Failed to start CAN transport: {e}")
            return False
    
    def stop(self):
        """Stop the CAN transport."""
        self.running = False
        if self.bus:
            self.bus.shutdown()
            self.bus = None
            logger.info("CAN transport stopped")
    
    def _receive_messages(self):
        """
        Start receiving CAN messages in a dedicated thread.
        This is typically run in a separate thread.
        """
        if not self.bus:
            logger.error("CAN bus not initialized")
            return
            
        while self.running:
            try:
                msg = self.bus.recv(timeout=1.0)
                if msg and self.message_processor:
                    self.message_processor(msg)
            except Exception as e:
                logger.error(f"Error receiving CAN message: {e}")
    
    def send_message(self, arbitration_id: int, data: list, is_extended_id: bool = False) -> bool:
        """
        Send a raw CAN message.
        
        Args:
            arbitration_id: CAN arbitration ID
            data: Data bytes to send
            is_extended_id: Whether to use extended IDs
            
        Returns:
            bool: True if sent successfully, False otherwise
        """
        if not self.bus:
            logger.error("CAN bus not initialized")
            return False
            
        try:
            msg = Message(
                arbitration_id=arbitration_id,
                data=data,
                is_extended_id=is_extended_id
            )
            self.bus.send(msg)
            logger.debug(f"Sent CAN message: ID=0x{arbitration_id:X}, data={[hex(d) for d in data]}")
            return True
        except Exception as e:
            logger.error(f"Error sending CAN message: {e}")
            return False
