"""
Tests for the CAN interface implementation with separation of concerns.

This test file validates the layered architecture of the CAN interface:
1. Transport layer - handling raw CAN communication
2. Protocol layer - implementing Stiebel Eltron specific protocol
3. Signal handler layer - managing signal values and callbacks
4. Facade layer - providing backward compatibility
"""

import pytest
import logging
from unittest.mock import MagicMock, patch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


class TestCanLayers:
    """Test cases for the CAN interface layers."""
    
    def test_can_transport(self):
        """Test the CanTransport layer."""
        from stiebel_control.can.transport import CanTransport
        
        # Create a mock for can.interface.Bus
        with patch('can.interface.Bus') as mock_bus:
            # Setup the mock
            mock_bus_instance = MagicMock()
            mock_bus.return_value = mock_bus_instance
            
            # Setup mock message processor
            message_processor = MagicMock()
            
            # Create the transport
            transport = CanTransport(
                can_interface='mock_can',
                bitrate=20000,
                message_processor=message_processor
            )
            
            # Test start
            result = transport.start()
            assert result is True
            mock_bus.assert_called_once_with(
                channel='mock_can',
                bustype='socketcan',
                bitrate=20000
            )
            
            # Test send_message
            transport.send_message(
                arbitration_id=0x123,
                data=[0x01, 0x02, 0x03, 0x04]
            )
            mock_bus_instance.send.assert_called_once()
            
            # Test stop
            transport.stop()
            mock_bus_instance.shutdown.assert_called_once()
            
        logger.info("CanTransport tests passed")
    
    def test_protocol_layer(self):
        """Test the StiebelProtocol layer."""
        from stiebel_control.can.protocol import StiebelProtocol
        from stiebel_control.can.transport import CanTransport
        
        # Create a mock transport
        mock_transport = MagicMock(spec=CanTransport)
        
        # Create the protocol
        protocol = StiebelProtocol(mock_transport)
        
        # Test adding a signal handler
        mock_handler = MagicMock()
        protocol.add_signal_handler(mock_handler)
        assert mock_handler in protocol.signal_handlers
        
        # Test removing a signal handler
        protocol.remove_signal_handler(mock_handler)
        assert mock_handler not in protocol.signal_handlers
        
        # Add the handler back for further tests
        protocol.add_signal_handler(mock_handler)
        
        # Test read_signal
        with patch('stiebel_control.can.protocol.get_elster_entry_by_english_name') as mock_get_entry:
            # Setup mock
            mock_entry = MagicMock()
            mock_entry.name = "TEST_SIGNAL"
            mock_entry.english_name = "TEST_SIGNAL"
            mock_entry.index = 42
            mock_get_entry.return_value = mock_entry
            
            # Test read with standard index
            protocol.read_signal(
                member_index=protocol.CM_PUMP,
                signal_name="TEST_SIGNAL"
            )
            
            # Verify transport.send_message was called
            mock_transport.send_message.assert_called_once()
            
            # Reset mock for next test
            mock_transport.send_message.reset_mock()
            
            # Test read with extended index
            mock_entry.index = 0x1234  # Use an index that requires extended format
            protocol.read_signal(
                member_index=protocol.CM_PUMP,
                signal_name="TEST_SIGNAL"
            )
            
            # Verify transport.send_message was called again
            mock_transport.send_message.assert_called_once()
        
        logger.info("StiebelProtocol tests passed")
    
    def test_signal_handler(self):
        """Test the CanSignalHandler layer."""
        from stiebel_control.can.signal_handler import CanSignalHandler
        from stiebel_control.can.protocol import StiebelProtocol
        
        # Create a mock protocol
        mock_protocol = MagicMock(spec=StiebelProtocol)
        
        # Setup can_members for the mock protocol
        mock_protocol.can_members = [
            MagicMock(can_id=0x680),  # ESPCLIENT
            MagicMock(can_id=0x180),  # PUMP
        ]
        
        # Create the signal handler
        handler = CanSignalHandler(mock_protocol)
        
        # Verify that it registered itself with the protocol
        mock_protocol.add_signal_handler.assert_called_once_with(handler._on_signal_update)
        
        # Test adding and removing signal callbacks
        mock_callback = MagicMock()
        handler.add_signal_callback("TEST_SIGNAL", 0x180, mock_callback)
        assert mock_callback in handler.signal_callbacks[(0x180, "TEST_SIGNAL")]
        
        handler.remove_signal_callback("TEST_SIGNAL", 0x180, mock_callback)
        assert not any(mock_callback in callbacks for callbacks in handler.signal_callbacks.values())
        
        # Test global callbacks
        handler.add_global_callback(mock_callback)
        assert mock_callback in handler.global_callbacks
        
        handler.remove_global_callback(mock_callback)
        assert mock_callback not in handler.global_callbacks
        
        # Test signal update handling
        handler.add_signal_callback("TEST_SIGNAL", 0x180, mock_callback)
        handler._on_signal_update("TEST_SIGNAL", 42.5, 0x180)
        mock_callback.assert_called_once_with("TEST_SIGNAL", 42.5, 0x180)
        
        # Test latest value storage
        assert handler.latest_values[(0x180, "TEST_SIGNAL")] == 42.5
        
        # Test read_signal passthrough
        handler.read_signal(1, "TEST_SIGNAL")
        mock_protocol.read_signal.assert_called_once_with(1, "TEST_SIGNAL", None)
        
        # Test write_signal passthrough
        handler.write_signal(1, "TEST_SIGNAL", 50)
        mock_protocol.write_signal.assert_called_once_with(1, "TEST_SIGNAL", 50)
        
        logger.info("CanSignalHandler tests passed")
    
    def test_can_interface_facade(self):
        """Test the CanInterface facade."""
        with patch('stiebel_control.can.transport.CanTransport') as mock_transport_class, \
             patch('stiebel_control.can.protocol.StiebelProtocol') as mock_protocol_class, \
             patch('stiebel_control.can.signal_handler.CanSignalHandler') as mock_handler_class:
            
            # Setup mocks
            mock_transport = MagicMock()
            mock_protocol = MagicMock()
            mock_handler = MagicMock()
            
            mock_transport_class.return_value = mock_transport
            mock_protocol_class.return_value = mock_protocol
            mock_handler_class.return_value = mock_handler
            
            # Import interface here to use the mocks
            from stiebel_control.can.interface import CanInterface
            
            # Test initialization
            mock_callback = MagicMock()
            interface = CanInterface(
                can_interface='mock_can',
                bitrate=20000,
                callback=mock_callback
            )
            
            # Verify component instantiation
            mock_transport_class.assert_called_once_with('mock_can', 20000)
            mock_protocol_class.assert_called_once_with(mock_transport, None)
            mock_handler_class.assert_called_once_with(mock_protocol)
            
            # Verify callback registration
            mock_handler.add_global_callback.assert_called_once_with(mock_callback)
            
            # Test start/stop propagation
            interface.start()
            mock_transport.start.assert_called_once()
            
            interface.stop()
            mock_transport.stop.assert_called_once()
            
            # Test method delegation
            interface.read_signal(1, "TEST_SIGNAL")
            mock_handler.read_signal.assert_called_once_with(1, "TEST_SIGNAL", None)
            
            interface.write_signal(1, "TEST_SIGNAL", 50)
            mock_handler.write_signal.assert_called_once_with(1, "TEST_SIGNAL", 50)
            
            interface.get_latest_value(1, "TEST_SIGNAL")
            mock_handler.get_latest_value.assert_called_once_with(1, "TEST_SIGNAL", None)
            
        logger.info("CanInterface facade tests passed")
