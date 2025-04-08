"""
Stiebel Eltron Heat Pump Control - Main Application
"""
import os
import sys
import time
import logging
import signal
from typing import Optional

# Import the new CAN interface from the can package
from stiebel_control.can.interface import CanInterface
from stiebel_control.mqtt_interface import MqttInterface
from stiebel_control.config import ConfigManager
from stiebel_control.entity_manager import EntityManager
from stiebel_control.signal_processor import SignalProcessor
from stiebel_control.utils.logging_utils import configure_logging
from stiebel_control.lifecycle import ApplicationContext, LifecycleManager

logger = logging.getLogger(__name__)

class StiebelControl:
    """
    Main controller class for the Stiebel Eltron Heat Pump Control.
    """
    
    def __init__(self, config_path: str):
        """
        Initialize the controller.
        
        Args:
            config_path: Path to the service configuration file
        """
        # Create application context
        self.app_context = ApplicationContext()
        
        # Load configuration
        self.config_manager = ConfigManager(config_path)
        self.app_context.register_component("config_manager", self.config_manager)
        
        # Configure logging
        configure_logging(self.config_manager.get_logging_config())
        
        # Initialize interfaces
        self._init_can_interface()
        self._init_mqtt_interface()
        
        # Initialize entity management and signal processing
        self.entity_manager = EntityManager(
            self.mqtt_interface, 
            self.config_manager.get_entity_config()
        )
        self.app_context.register_component(
            "entity_manager", 
            self.entity_manager,
            init_method=lambda: self.entity_manager.build_entity_mapping(self.can_interface)
        )
        
        self.signal_processor = SignalProcessor(
            self.entity_manager,
            self.mqtt_interface,
            self.can_interface,
            self.config_manager.get_entity_config()
        )
        self.app_context.register_component("signal_processor", self.signal_processor)
        
        # Set up callbacks
        self._setup_callbacks()
        
        logger.info("Stiebel Control initialized")
        
    def _init_can_interface(self) -> None:
        """
        Initialize the CAN interface.
        """
        can_config = self.config_manager.get_can_config()
        
        try:
            logger.info(f"Initializing CAN interface {can_config.interface} at {can_config.bitrate} bps")
            # We'll initialize the CAN interface without a callback first
            # and set it later after signal_processor is initialized
            self.can_interface = CanInterface(
                can_interface=can_config.interface,
                bitrate=can_config.bitrate
            )
            
            # Register with app context
            self.app_context.register_component(
                "can_interface",
                self.can_interface,
                start_method=self.can_interface.start,
                stop_method=self.can_interface.stop
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize CAN interface: {e}")
            sys.exit(1)
            
    def _init_mqtt_interface(self) -> None:
        """
        Initialize the MQTT interface.
        """
        mqtt_config = self.config_manager.get_mqtt_config()
        
        try:
            logger.info(f"Initializing MQTT interface to {mqtt_config.host}:{mqtt_config.port}")
            self.mqtt_interface = MqttInterface(
                host=mqtt_config.host,
                port=mqtt_config.port,
                username=mqtt_config.username,
                password=mqtt_config.password,
                client_id=mqtt_config.client_id,
                discovery_prefix=mqtt_config.discovery_prefix,
                base_topic=mqtt_config.base_topic
            )
            
            # Register with app context
            self.app_context.register_component(
                "mqtt_interface",
                self.mqtt_interface,
                start_method=self.mqtt_interface.connect,
                stop_method=self.mqtt_interface.disconnect
            )
                
        except Exception as e:
            logger.error(f"Failed to initialize MQTT interface: {e}")
            sys.exit(1)
            
    def _setup_callbacks(self) -> None:
        """
        Set up callbacks between components.
        """
        # Set the callback for the CAN interface
        self.can_interface.callback = self.signal_processor.process_signal
        
        # Set the MQTT command callback
        self.mqtt_interface.command_callback = self.signal_processor.handle_command
        
        logger.debug("Callbacks set up")
        
    def start(self) -> None:
        """
        Start the controller.
        """
        logger.info("Starting Stiebel Control")
        
        try:
            # Initialize all components
            self.app_context.initialize()
            
            # Start all components using the lifecycle manager
            self.app_context.start()
            
            # Start update loop
            self._update_loop()
            
        except Exception as e:
            logger.error(f"Error in controller: {e}")
            self.stop()
            
    def stop(self) -> None:
        """
        Stop the controller and clean up resources.
        """
        logger.info("Stopping Stiebel Control")
        
        try:
            # Use lifecycle manager to stop and cleanup all components
            self.app_context.shutdown()
                
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            
    def _update_loop(self) -> None:
        """
        Main update loop.
        """
        update_interval = self.config_manager.get_update_interval()
        logger.info(f"Starting update loop with interval of {update_interval} seconds")
        
        try:
            while self.app_context.lifecycle_manager.is_running:
                # The CAN interface is already sending updates asynchronously
                # via the callback. This loop can be used for periodic tasks
                # like polling values that don't automatically update.
                
                # Process any pending updates
                time.sleep(update_interval)
                
        except KeyboardInterrupt:
            logger.info("Update loop interrupted by user")
            self.stop()
            
        except Exception as e:
            logger.error(f"Error in update loop: {e}")
            self.stop()

def main():
    """
    Main entry point.
    """
    # Default configuration path
    config_path = os.environ.get(
        'STIEBEL_CONFIG_PATH', 
        os.path.join(os.path.dirname(os.path.dirname(__file__)), 'service_config.yaml')
    )
    
    # Allow overriding config path from command line
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
        
    # Create and start the controller
    controller = StiebelControl(config_path)
    controller.start()

if __name__ == "__main__":
    main()
