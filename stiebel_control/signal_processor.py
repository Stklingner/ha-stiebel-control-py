"""
Signal processing for the Stiebel Control package.
"""
import logging
from typing import Dict, Any, Optional
from stiebel_control.entity_manager import EntityManager
from stiebel_control.services.transformation_service import TransformationService
from stiebel_control.services.command_handler import CommandHandler
from stiebel_control.config.config_models import EntityConfig

logger = logging.getLogger(__name__)

class SignalProcessor:
    """
    Processes signals from the CAN bus and updates Home Assistant entities.
    """
    
    def __init__(self, entity_manager: EntityManager, mqtt_interface, 
                 can_interface, entity_config: EntityConfig):
        """
        Initialize the signal processor.
        
        Args:
            entity_manager: Entity manager for entity registration and lookup
            mqtt_interface: MQTT interface for publishing updates
            can_interface: CAN interface for accessing signal values
            entity_config: Entity configuration model
        """
        self.entity_manager = entity_manager
        self.mqtt_interface = mqtt_interface
        self.can_interface = can_interface
        self.entity_config = entity_config
        
        # Initialize our service components
        self.transformation_service = TransformationService()
        self.command_handler = CommandHandler(
            can_interface,
            self.entity_config.entities,
            self.transformation_service
        )
        
        logger.info("Signal processor initialized")
        
    def process_signal(self, signal_name: str, value: Any, can_id: int) -> None:
        """
        Process a signal update from the CAN bus.
        
        Args:
            signal_name: Name of the signal
            value: Updated signal value
            can_id: CAN ID of the member that sent the message
        """
        # Check if MQTT is connected before proceeding
        if not self.mqtt_interface.is_connected():
            logger.debug(f"Received signal {signal_name} = {value} from CAN ID 0x{can_id:X} but MQTT is not connected, skipping processing")
            return
            
        # First, try to find an existing entity for this signal
        entity_id = self.entity_manager.get_entity_by_signal(signal_name, can_id)
        
        if not entity_id:
            # If no existing entity found and dynamic registration is enabled,
            # try to create one dynamically
            entity_id = self.entity_manager.dynamically_register_entity(signal_name, value, can_id)
            
            if not entity_id:
                # No existing entity and dynamic registration failed or disabled
                logger.debug(f"No entity found for signal {signal_name} from CAN ID 0x{can_id:X}")
                return
                
        # Skip if this is a pending command being processed
        if self.command_handler.is_pending_command(entity_id, value):
            return
                
        # Get entity configuration
        entity_def = self.entity_config.get_entity_def(entity_id)
        
        # Apply any transformations to the value using our dedicated service
        transform_config = entity_def.get('transform', {})
        if transform_config:
            value = self.transformation_service.apply_transformation(value, transform_config)
            
        # Publish the updated value to MQTT
        result = self.mqtt_interface.publish_state(entity_id, value)
        if result:
            logger.debug(f"Published state for entity {entity_id}: {value}")
        else:
            logger.warning(f"Failed to publish state for entity {entity_id}")
        
    def handle_command(self, entity_id: str, payload: str) -> None:
        """
        Handle a command received from Home Assistant.
        Delegates to the CommandHandler service.
        
        Args:
            entity_id: Entity ID that received the command
            payload: Command payload
        """
        # Delegate to the command handler service
        self.command_handler.handle_command(entity_id, payload)
