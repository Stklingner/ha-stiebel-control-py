"""
Signal Gateway for the Stiebel Control package.

Serves as a bidirectional gateway between CAN signals and MQTT entities.
Routes data between the CAN bus and Home Assistant via MQTT.
"""
import logging
from typing import Dict, Any, Optional

from stiebel_control.ha_mqtt.entity_registration_service import EntityRegistrationService
from stiebel_control.ha_mqtt.mqtt_interface import MqttInterface
from stiebel_control.ha_mqtt.signal_entity_mapper import SignalEntityMapper
from stiebel_control.ha_mqtt.command_handler import CommandHandler
from stiebel_control.can.interface import CanInterface
from stiebel_control.config.config_models import EntityConfig

logger = logging.getLogger(__name__)

class SignalGateway:
    """
    Acts as a bidirectional gateway between CAN signals and MQTT entities.
    
    Responsibilities:
    1. Routes CAN signals to appropriate MQTT entities
    2. Translates MQTT commands to CAN signals
    3. Handles dynamic entity registration based on observed signals
    """
    
    def __init__(self, 
                 entity_service: EntityRegistrationService,
                 mqtt_interface: MqttInterface,
                 can_interface: CanInterface,
                 signal_mapper: SignalEntityMapper,
                 entity_config: EntityConfig):
        """
        Initialize the signal gateway.
        
        Args:
            entity_service: Service for registering entities with Home Assistant
            mqtt_interface: MQTT interface for publishing states
            can_interface: CAN interface for reading signal values
            signal_mapper: Maps between signals and entities
            entity_config: Entity configuration
        """
        self.entity_service = entity_service
        self.mqtt_interface = mqtt_interface
        self.can_interface = can_interface
        self.signal_mapper = signal_mapper
        self.entity_config = entity_config
        
        # Initialize command handler with proper dependencies
        # Get transformation service or create a simple one if needed
        from stiebel_control.ha_mqtt.transformation_service import TransformationService
        self.transformation_service = TransformationService()
        
        # Initialize the command handler
        self.command_handler = CommandHandler(
            can_interface=can_interface,
            entity_config=entity_config.entities if hasattr(entity_config, 'entities') else {},
            transformation_service=self.transformation_service
        )
        
        logger.info("Signal gateway initialized")
    
    def process_signal(self, signal_name: str, value: Any, can_id: int) -> None:
        """
        Route a CAN signal to the appropriate MQTT entity (CAN → MQTT direction).
        
        This method receives signals from the CAN bus and publishes the corresponding
        state updates to Home Assistant via MQTT. It handles dynamic entity registration
        when new signals are encountered.
        
        Args:
            signal_name: Name of the signal received from CAN bus
            value: Value of the CAN signal
            can_id: CAN ID of the message source
        """
        # Skip processing if not connected to MQTT
        if not self.mqtt_interface.is_connected():
            return
            
        # Get the CAN member name from ID for better readability
        member_name = self.signal_mapper.get_can_member_name(can_id) or f"device_{can_id:x}"
        
        # Get existing entity or create one dynamically
        entity_id = self.signal_mapper.get_entity_by_signal(signal_name, can_id) or \
                    self.entity_service.register_dynamic_entity(
                        signal_name=signal_name,
                        value=value,
                        member_name=member_name
                    )
        
        if not entity_id:
            return
                
        # Skip if this is a pending command being processed
        if self.command_handler.is_pending_command(entity_id, value):
            logger.debug(f"Ignoring pending command echo for {entity_id}: {value}")
            return
        
        # Transform and publish the value
        transformed_value = self._transform_value(signal_name, entity_id, value)
        
        # Publish the update
        self.mqtt_interface.publish_state(entity_id, transformed_value)
    
    def handle_command(self, entity_id: str, command: str) -> None:
        """
        Route a command from MQTT to the CAN bus (MQTT → CAN direction).
        
        This method receives commands from Home Assistant via MQTT and translates them
        to appropriate CAN messages that control the heat pump.
        
        Args:
            entity_id: ID of the entity that received the command
            command: Command string from Home Assistant
        """
        # Delegate directly to command handler
        try:
            self.command_handler.handle_command(entity_id, command)
        except Exception as e:
            logger.error(f"Error handling command for {entity_id}: {e}")
    
    def _transform_value(self, signal_name: str, entity_id: str, value: Any) -> Any:
        """Transform CAN signal values to the appropriate format for MQTT entities."""
        # For now, just return the value as-is
        # In a complete implementation, this would handle value mapping, scaling, etc.
        return value
