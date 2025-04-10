"""
Entity management for the Stiebel Control package.
"""
import logging
from typing import Dict, Any, Optional, Tuple
from stiebel_control.mqtt_interface import MqttInterface
from stiebel_control.heatpump.elster_table import get_elster_entry_by_english_name
from stiebel_control.services.entity_registration_service import EntityRegistrationService
from stiebel_control.services.signal_entity_mapper import SignalEntityMapper
from stiebel_control.config.config_models import EntityConfig

logger = logging.getLogger(__name__)

class EntityManager:
    """
    Manages Home Assistant entities and their registration.
    Acts as a coordinator between the specialized services.
    """
    
    def __init__(self, mqtt_interface: MqttInterface, entity_config: EntityConfig):
        """
        Initialize the entity manager.
        
        Args:
            mqtt_interface: MQTT interface for Home Assistant communication
            entity_config: Entity configuration model
        """
        self.mqtt_interface = mqtt_interface
        self.entity_config = entity_config
        
        # Initialize specialized services
        self.registration_service = EntityRegistrationService(mqtt_interface)
        self.signal_mapper = SignalEntityMapper()
        
        logger.info(f"Entity manager initialized with dynamic registration {'enabled' if self.entity_config.dynamic_registration_enabled else 'disabled'}")
        
    def build_entity_mapping(self, can_interface) -> None:
        """
        Build mapping between CAN signals and Home Assistant entities.
        
        Args:
            can_interface: CAN interface for resolving CAN IDs
        """
        logger.info("Building entity mapping from configuration")
        
        # Check if MQTT is connected before trying to register entities
        if not self.mqtt_interface.is_connected():
            logger.warning("MQTT is not connected; entity registration will be deferred until connection is established")
            return
            
        # Process manual entity registration from entity_config.yaml
        # This handles the nested structure with categories (sensors, buttons, etc.)
        from stiebel_control.config.config_manager import ConfigManager
        config_manager = ConfigManager.get_instance()
        if config_manager:
            raw_entity_config = config_manager.raw_entity_config
            if raw_entity_config:
                self.registration_service.register_manual_entities(raw_entity_config)
            else:
                logger.warning("No raw entity configuration available")
                
        # Build signal-to-entity mapping for dynamic entities
        if self.entity_config.entities:
            self.signal_mapper.build_entity_mapping(self.entity_config.entities, can_interface)
        else:
            logger.info("No explicit entity mapping configuration found")
            
    def get_entity_by_signal(self, signal_name: str, can_id: int) -> Optional[str]:
        """
        Get entity ID for a given signal and CAN ID.
        
        Args:
            signal_name: Name of the signal
            can_id: CAN ID of the member that sent the message
            
        Returns:
            Entity ID, or None if no mapping found
        """
        return self.signal_mapper.get_entity_by_signal(signal_name, can_id)
        
    def get_signal_by_entity(self, entity_id: str) -> Optional[Tuple[str, int]]:
        """
        Get signal name and CAN ID for a given entity ID.
        
        Args:
            entity_id: Entity ID in Home Assistant
            
        Returns:
            Tuple of (signal_name, can_id), or None if no mapping found
        """
        return self.signal_mapper.get_signal_by_entity(entity_id)
        
    def dynamically_register_entity(self, signal_name: str, value: Any, can_id: int) -> Optional[str]:
        """
        Dynamically register an entity with Home Assistant based on signal characteristics.
        
        Args:
            signal_name: Name of the signal
            value: Current value of the signal
            can_id: CAN ID of the member that sent the message
            
        Returns:
            str: The newly created entity ID, or None if registration failed
        """
        if not self.entity_config.dynamic_registration_enabled:
            return None
            
        # Get signal information
        ei = get_elster_entry_by_english_name(signal_name)
        if ei.name == "UNKNOWN":
            logger.warning(f"Cannot register unknown signal: {signal_name}")
            return None
            
        # Get CAN member name from ID
        can_member_name = self.signal_mapper.get_can_member_name(can_id)
        if not can_member_name:
            logger.warning(f"Cannot register signal from unknown CAN ID: 0x{can_id:X}")
            return None
            
        # Register the entity with the registration service - the entity ID is generated inside
        entity_id = self.registration_service.register_dynamic_entity(
            signal_name=signal_name,
            signal_type=ei.type,
            value=value,
            can_id=can_id
        )
        
        if entity_id:
            # Also add to the signal mapper for future lookups
            self.signal_mapper.add_mapping(signal_name, can_id, entity_id)
            return entity_id
        else:
            logger.error(f"Failed to dynamically register entity for signal {signal_name}")
            return None
            
    def get_entity_config(self, entity_id: str) -> Dict[str, Any]:
        """
        Get the configuration for an entity.
        
        Args:
            entity_id: Entity ID to get configuration for
            
        Returns:
            Entity configuration dictionary, or empty dict if not found
        """
        return self.entity_config.get_entity_def(entity_id)
