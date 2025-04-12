"""
Stiebel Eltron Heat Pump Control - Main Application
"""
import os
import sys
import time
import logging
import signal
from typing import Optional, Callable, Any

# Import the components from their packages
from stiebel_control.can.interface import CanInterface
from stiebel_control.ha_mqtt.mqtt_interface import MqttInterface
from stiebel_control.ha_mqtt.entity_registration_service import EntityRegistrationService
from stiebel_control.ha_mqtt.signal_entity_mapper import SignalEntityMapper
from stiebel_control.signal_gateway import SignalGateway
from stiebel_control.config.config_manager import ConfigManager
from stiebel_control.utils.logging_utils import configure_logging

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
        # Set shutdown flag
        self.running = False
        
        # Load configuration
        self.config_manager = ConfigManager(config_path)
        
        # Configure logging
        log_config = self.config_manager.get_logging_config()
        configure_logging(log_config)
        
        # Initialize interfaces
        self._init_can_interface()
        self._init_mqtt_interface()
        
        # Initialize entity management and signal processing
        self.signal_mapper = SignalEntityMapper()
        self.entity_service = EntityRegistrationService(
            mqtt_interface=self.mqtt_interface,
            signal_mapper=self.signal_mapper
        )
        
        # Initialize signal gateway
        self.signal_gateway = SignalGateway(
            entity_service=self.entity_service,
            mqtt_interface=self.mqtt_interface,
            can_interface=self.can_interface,
            signal_mapper=self.signal_mapper,
            entity_config=self.config_manager.get_entity_config(),
            protocol=self.can_interface.protocol
        )
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        
        logger.info("Stiebel Control initialized")
        
    def _init_can_interface(self) -> None:
        """
        Initialize the CAN interface.
        """
        can_config = self.config_manager.get_can_config()
        
        try:
            logger.info(f"Initializing CAN interface {can_config.interface} at {can_config.bitrate} bps")
            # Set up callback to the signal gateway
            self.can_interface = CanInterface(
                can_interface=can_config.interface,
                bitrate=can_config.bitrate,
                callback=self._can_signal_callback
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
                client_id=mqtt_config.client_id,
                broker_host=mqtt_config.host,
                broker_port=mqtt_config.port,
                username=mqtt_config.username,
                password=mqtt_config.password,
                discovery_prefix=mqtt_config.discovery_prefix,
                base_topic=mqtt_config.base_topic,
                command_callback=self._mqtt_command_callback
            )
                
        except Exception as e:
            logger.error(f"Failed to initialize MQTT interface: {e}")
            sys.exit(1)
            
    def _can_signal_callback(self, signal_name: str, value: Any, can_id: int) -> None:
        """
        Callback for CAN signals.
        
        Args:
            signal_name: Name of the signal
            value: Signal value
            can_id: CAN ID of the device
        """
        # Pass the signal to the gateway for processing
        self.signal_gateway.process_signal(signal_name, value, can_id)
        
    def _mqtt_command_callback(self, entity_id: str, command: str) -> None:
        """
        Callback for MQTT commands.
        
        Args:
            entity_id: ID of the entity receiving the command
            command: Command string
        """
        # Pass the command to the gateway for processing
        self.signal_gateway.handle_command(entity_id, command)
        
    def _handle_signal(self, signum, frame):
        """
        Handle shutdown signals.
        
        Args:
            signum: Signal number
            frame: Current stack frame
        """
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
        
    def start(self) -> None:
        """
        Start the controller.
        """
        logger.info("Starting Stiebel Control")
        
        try:
            # Connect to MQTT broker
            if not self.mqtt_interface.connect():
                logger.error("Failed to connect to MQTT broker")
                return
                
            # Start CAN interface
            self.can_interface.start()
            
            # Register pre-configured entities
            self._register_configured_entities()
            
            # Mark as running
            self.running = True
            
            # Start update loop
            self._update_loop()
            
        except Exception as e:
            logger.error(f"Error in controller: {e}", exc_info=True)
            self.stop()
            
    def _register_configured_entities(self) -> None:
        """
        Register pre-configured entities from the configuration.
        """
        entity_config = self.config_manager.get_entity_config()
        
        if not entity_config or not hasattr(entity_config, 'entities'):
            logger.warning("No entity configuration found")
            return
            
        logger.info(f"Registering {len(entity_config.entities)} configured entities")
        
        for entity_id, entity_def in entity_config.entities.items():
            try:
                self.entity_service.register_entity_from_config(entity_id, entity_def)
            except Exception as e:
                logger.error(f"Error registering entity {entity_id}: {e}")
            
    def stop(self) -> None:
        """
        Stop the controller and clean up resources.
        """
        logger.info("Stopping Stiebel Control")
        self.running = False
        
        try:
            # Stop CAN interface
            try:
                if hasattr(self, 'can_interface'):
                    self.can_interface.stop()
            except Exception as e:
                logger.error(f"Error stopping CAN interface: {e}")
            
            # Disconnect from MQTT
            try:
                if hasattr(self, 'mqtt_interface'):
                    self.mqtt_interface.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting from MQTT: {e}")
                
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            
    def _update_loop(self) -> None:
        """
        Main update loop.
        """
        update_interval = self.config_manager.get_update_interval()
        logger.info(f"Starting update loop with interval of {update_interval} seconds")
        
        try:
            while self.running:
                # The CAN interface is already sending updates asynchronously
                # via the callback. This loop can be used for periodic tasks
                # like polling values that don't automatically update.
                
                # Sleep for the configured interval
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
    
    try:
        controller.start()
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
    except Exception as e:
        logger.error(f"Application error: {e}", exc_info=True)
    finally:
        controller.stop()

if __name__ == "__main__":
    main()
