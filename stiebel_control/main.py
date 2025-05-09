"""
Stiebel Eltron Heat Pump Control - Main Application
"""
import os
import sys
import time
import logging
import signal
import json
from typing import Any

# Import the components from their packages
from stiebel_control.can.interface import CanInterface
from stiebel_control.ha_mqtt.mqtt_interface import MqttInterface
from stiebel_control.config.config_manager import ConfigManager
from stiebel_control.config.config_models import EntityConfig
from stiebel_control.ha_mqtt.signal_entity_mapper import SignalEntityMapper
from stiebel_control.ha_mqtt.entity_registration_service import EntityRegistrationService
from stiebel_control.signal_gateway import SignalGateway
from stiebel_control.utils.logging_utils import configure_logging
from stiebel_control.heatpump.signal_poller import SignalPoller

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
        
        # Initialize signal gateway with new controls-focused approach
        self.signal_gateway = SignalGateway(
            entity_service=self.entity_service,
            mqtt_interface=self.mqtt_interface,
            can_interface=self.can_interface,
            signal_mapper=self.signal_mapper,
            controls_config=self.config_manager.get_controls_config(),
            protocol=self.can_interface.protocol,
            ignore_unsolicited_signals=self.config_manager.should_ignore_unsolicited_signals()
        )
        
        # Now set the signal gateway's process_signal method as the CAN interface callback
        self.can_interface.callback = self.signal_gateway.process_signal
        
        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._handle_signal)
        signal.signal(signal.SIGTERM, self._handle_signal)
        
        logger.info("Stiebel Control initialized")
        
    def _init_can_interface(self) -> None:
        """
        Initialize the CAN bus interface.
        """
        can_config = self.config_manager.get_can_config()
        
        try:
            logger.info(f"Initializing CAN interface {can_config.interface} at {can_config.bitrate} bps")
            # Initialize without a callback - we'll set it after signal_gateway is created
            self.can_interface = CanInterface(
                can_interface=can_config.interface,
                bitrate=can_config.bitrate
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
        Start the Stiebel Control service.
        """
        logger.info("Starting Stiebel Control")
        
        # Initialize start time for uptime tracking
        self.start_time = time.time()
        
        try:
            # Connect to MQTT broker and initialize sensors first
            if not self.mqtt_interface.connect():
                logger.error("Failed to connect to MQTT broker")
                return
            
            # Register system sensors
            self._register_system_sensors()
            
            # Update initial system status
            self.signal_gateway.update_system_status("starting")
                
            # Start CAN interface
            self.can_interface.start()
            
            # Register pre-configured entities
            self._register_configured_entities()
            
            # Initialize the signal poller
            self.signal_poller = SignalPoller(self.can_interface)
            
            # Connect signal poller to signal gateway for polled signals tracking
            self.signal_gateway.set_signal_poller(self.signal_poller)
            
            # Update status to online
            self.signal_gateway.update_system_status("online")
            
            # Update entity count
            self.signal_gateway.update_entities_count(None)
            
            # Mark as running
            self.running = True
            
            # Start update loop
            self._update_loop()
            
        except Exception as e:
            logger.error(f"Error in controller: {e}", exc_info=True)
            self.signal_gateway.update_system_status("error")
            self.stop()
            
    def _register_configured_entities(self) -> None:
        """
        Register controls from the controls configuration.
        """
        controls_config = self.config_manager.get_controls_config()
        
        if not controls_config:
            logger.warning("No controls configuration found")
            return
            
        logger.info(f"Registering {len(controls_config)} controls")
        
        for control_id, control_def in controls_config.items():
            try:
                control_type = control_def.get('type')
                name = control_def.get('name', control_id)
                icon = control_def.get('icon')
                
                if control_type == 'select':
                    options = control_def.get('options', [])
                    self.entity_service.register_select(
                        entity_id=control_id,
                        name=name,
                        options=options,
                        icon=icon
                    )
                elif control_type == 'number':
                    min_value = control_def.get('min')
                    max_value = control_def.get('max')
                    step = control_def.get('step')
                    unit = control_def.get('unit_of_measurement')
                    self.entity_service.register_number(
                        entity_id=control_id,
                        name=name,
                        min_value=min_value,
                        max_value=max_value,
                        step=step,
                        unit_of_measurement=unit,
                        icon=icon
                    )
                elif control_type == 'button':
                    self.entity_service.register_button(
                        entity_id=control_id,
                        name=name,
                        icon=icon
                    )
                else:
                    logger.warning(f"Unknown control type '{control_type}' for control {control_id}")
            except Exception as e:
                logger.error(f"Error registering control {control_id}: {e}", exc_info=True)
                
    def _register_system_sensors(self) -> None:
        """
        Register system status sensors that track the application state.
        
        Only the main system_status entity is registered as a sensor, and all other
        monitoring metrics will be added as attributes to this entity.
        """
        logger.info("Registering system status entity")
        
        # Register device status sensor - this will be our main monitoring entity
        self.entity_service.register_sensor(
            entity_id="system_status",
            name="System Status",
            icon="mdi:heart-pulse",
            device_class="enum",
            state_class=None,
            unit_of_measurement=None,
            attributes={"placeholder": True},
            options=["online", "offline", "starting", "error"]
        )
        
        # Initial entity count
        try:
            self.signal_gateway.update_entities_count(0)
        except Exception as e:
            logger.warning(f"Unable to set initial entity count: {e}")
            
    def stop(self) -> None:
        """
        Stop the controller and clean up resources.
        """
        logger.info("Stopping Stiebel Control")
        self.running = False
        
        # Update status to offline
        try:
            self.signal_gateway.update_system_status("offline")
        except Exception as e:
            logger.warning(f"Unable to update status during shutdown: {e}")
        
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
        
        # Track time for different update frequencies
        last_poller_check = 0
        last_poller_stats_update = 0
        last_polled_signals_update = 0
        
        try:
            while self.running:
                current_time = time.time()
                
                # Run the signal poller every second
                if current_time - last_poller_check >= 1:
                    self.signal_poller.update()
                    last_poller_check = current_time
                    
                # Update system monitoring statistics every 30 seconds
                if current_time - last_poller_stats_update >= 30:
                    # Get polling stats
                    stats = self.signal_poller.get_stats()
                    
                    # Get entity counts
                    entity_count = len(self.entity_service.entities)
                    
                    # Consolidate all monitoring metrics as attributes on system_status entity
                    system_attributes = {
                        "entities_count": entity_count,
                        "polled_entities_count": stats['total_polled_entities'],
                        "responsive_entities_count": stats['total_responsive_entities'],
                        "non_responsive_entities": stats['non_responsive_entities_list'],
                        "uptime_seconds": int(current_time - self.start_time)
                    }
                    
                    # Update attributes
                    self.entity_service.update_entity_attributes("system_status", system_attributes)
                    last_poller_stats_update = current_time
                    
                # Update the polled signals tracking every 15 seconds
                # This keeps the signal gateway aware of what's been polled by the poller
                if current_time - last_polled_signals_update >= 15:
                    self.signal_gateway.track_polled_signals()
                    last_polled_signals_update = current_time
                
                # Short sleep to prevent CPU hogging
                time.sleep(0.2)
                
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
