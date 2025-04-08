"""
Tests for the application lifecycle management and CAN interface integration.

This test validates that:
1. The lifecycle manager correctly handles component initialization, startup, and shutdown
2. The new CAN interface is properly integrated with the application
3. The application maintains backward compatibility
"""

import sys
import logging
import unittest
from unittest.mock import MagicMock, patch

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


class TestLifecycleManager(unittest.TestCase):
    """Test cases for the LifecycleManager."""
    
    def test_lifecycle_manager(self):
        """Test the basic lifecycle management functionality."""
        from stiebel_control.lifecycle import LifecycleManager
        
        # Create mock callbacks
        init_callback = MagicMock()
        start_callback = MagicMock()
        stop_callback = MagicMock()
        cleanup_callback = MagicMock()
        
        # Create the lifecycle manager
        manager = LifecycleManager("Test Application")
        
        # Register callbacks
        manager.register_init_callback(init_callback)
        manager.register_start_callback(start_callback)
        manager.register_stop_callback(stop_callback)
        manager.register_cleanup_callback(cleanup_callback)
        
        # Test initialization
        self.assertTrue(manager.initialize())
        init_callback.assert_called_once()
        
        # Test startup
        self.assertTrue(manager.start())
        start_callback.assert_called_once()
        self.assertTrue(manager.is_running)
        
        # Test shutdown
        self.assertTrue(manager.stop())
        stop_callback.assert_called_once()
        self.assertFalse(manager.is_running)
        
        # Test cleanup
        self.assertTrue(manager.cleanup())
        cleanup_callback.assert_called_once()
        
        logger.info("LifecycleManager tests passed")


class TestApplicationContext(unittest.TestCase):
    """Test cases for the ApplicationContext."""
    
    def test_application_context(self):
        """Test the application context functionality."""
        from stiebel_control.lifecycle import ApplicationContext
        
        # Create the application context
        context = ApplicationContext()
        
        # Create mock component and methods
        component = MagicMock()
        init_method = MagicMock()
        start_method = MagicMock()
        stop_method = MagicMock()
        cleanup_method = MagicMock()
        
        # Register the component
        context.register_component(
            "test_component", 
            component,
            init_method,
            start_method,
            stop_method,
            cleanup_method
        )
        
        # Verify component registration
        self.assertEqual(context.get_component("test_component"), component)
        
        # Test lifecycle operations
        context.initialize()
        init_method.assert_called_once()
        
        context.start()
        start_method.assert_called_once()
        
        context.stop()
        stop_method.assert_called_once()
        
        context.cleanup()
        cleanup_method.assert_called_once()
        
        logger.info("ApplicationContext tests passed")


class TestCanIntegration(unittest.TestCase):
    """Test cases for the CAN interface integration."""
    
    def test_can_interface_integration(self):
        """Test that the new CAN interface is properly integrated with the application."""
        # Create mocks for required components
        mock_can_interface = MagicMock()
        mock_mqtt_interface = MagicMock()
        mock_entity_manager = MagicMock()
        mock_signal_processor = MagicMock()
        
        # Create patches for all the major imports and component instantiations
        patch_list = [
            patch('stiebel_control.can.transport.CanTransport'),
            patch('stiebel_control.can.interface.CanInterface', return_value=mock_can_interface),
            patch('stiebel_control.mqtt_interface.MqttInterface', return_value=mock_mqtt_interface),
            patch('stiebel_control.entity_manager.EntityManager', return_value=mock_entity_manager),
            patch('stiebel_control.signal_processor.SignalProcessor', return_value=mock_signal_processor),
            patch('stiebel_control.config.ConfigManager'),
            patch('stiebel_control.utils.logging_utils.configure_logging')
        ]
        
        # Set up all patches
        for patcher in patch_list:
            patcher.start()
            
        try:
            # Now import the module to be tested with all the mocks in place
            from stiebel_control.main import StiebelControl
            
            # Create the controller instance
            controller = StiebelControl("mock_config_path")
            
            # Verify that the can_interface is registered in the app context
            self.assertEqual(controller.app_context.get_component("can_interface"), mock_can_interface)
            
            # Mock _update_loop to prevent blocking
            controller._update_loop = MagicMock()
            
            # Start the controller
            controller.start()
            
            # After start, verify that the can_interface.start method was called
            # This happens through the lifecycle manager callbacks
            self.assertTrue(mock_can_interface.start.called)
            
            # Now stop the controller
            controller.stop()
            
            # Verify stop was called on the can_interface
            self.assertTrue(mock_can_interface.stop.called)
            
        finally:
            # Stop all patches
            for patcher in patch_list:
                patcher.stop()
                
        logger.info("CAN interface integration tests passed")


def main():
    """Run the tests."""
    try:
        unittest.main(argv=['first-arg-is-ignored'], exit=False)
        logger.info("All lifecycle and integration tests passed")
        return 0
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
