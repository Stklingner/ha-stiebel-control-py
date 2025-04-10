"""
Service for registering entities with Home Assistant via MQTT.
"""
import logging
from typing import Dict, Any, Optional, List, Set
from stiebel_control.mqtt_interface import MqttInterface
from stiebel_control.heatpump.elster_table import (
    ElsterType,
    MODELIST,
    ERRORLIST
)

logger = logging.getLogger(__name__)

class EntityRegistrationService:
    """
    Handles registration of entities with Home Assistant via MQTT.
    """
    
    def __init__(self, mqtt_interface: MqttInterface):
        """
        Initialize the entity registration service.
        
        Args:
            mqtt_interface: MQTT interface for Home Assistant communication
        """
        self.mqtt_interface = mqtt_interface
        
        # Track registered entities to avoid duplicates
        self.registered_entities = set()
        
        logger.info("Entity registration service initialized")
        
    def register_entity_from_config(self, entity_id: str, entity_def: Dict[str, Any]) -> bool:
        """
        Register an entity with Home Assistant based on configuration.
        
        Args:
            entity_id: Unique entity ID
            entity_def: Entity definition from configuration
            
        Returns:
            bool: True if registration was successful, False otherwise
        """
        # Skip if already registered
        if entity_id in self.registered_entities:
            logger.debug(f"Entity {entity_id} already registered, skipping")
            return True
            
        entity_type = entity_def.get('type', 'sensor')
        name = entity_def.get('name', entity_id)
        success = False
        
        if entity_type == 'sensor':
            # Register a sensor entity
            success = self.mqtt_interface.register_sensor(
                entity_id=entity_id,
                name=name,
                device_class=entity_def.get('device_class'),
                state_class=entity_def.get('state_class'),
                unit_of_measurement=entity_def.get('unit_of_measurement'),
                icon=entity_def.get('icon')
            )
        elif entity_type == 'binary_sensor':
            # Register a binary sensor entity
            success = self.mqtt_interface.register_binary_sensor(
                entity_id=entity_id,
                name=name,
                device_class=entity_def.get('device_class'),
                icon=entity_def.get('icon')
            )
        elif entity_type == 'select':
            # Register a select entity
            options = entity_def.get('options', [])
            success = self.mqtt_interface.register_select(
                entity_id=entity_id,
                name=name,
                options=options,
                icon=entity_def.get('icon')
            )
        else:
            logger.warning(f"Unsupported entity type '{entity_type}' for entity {entity_id}")
            return False
            
        if success:
            # Add to registered entities
            self.registered_entities.add(entity_id)
            logger.info(f"Registered {entity_type} entity {entity_id}")
            
        return success
        
    def register_dynamic_entity(
        self, 
        entity_id: str, 
        friendly_name: str, 
        signal_type: ElsterType, 
        signal_name: str, 
        value: Any
    ) -> bool:
        """
        Dynamically register an entity based on signal characteristics.
        
        Args:
            entity_id: Unique entity ID to use
            friendly_name: Human-readable name for the entity
            signal_type: Type of the Elster signal
            signal_name: Name of the signal
            value: Current value of the signal
            
        Returns:
            bool: True if registration was successful, False otherwise
        """
        # Skip if already registered
        if entity_id in self.registered_entities:
            return True
            
        # Determine entity type and attributes based on signal type
        entity_type = "sensor"  # Default entity type
        device_class = None
        state_class = "measurement"
        unit_of_measurement = None
        icon = None
        
        # Match signal type to appropriate entity configuration
        if signal_type == ElsterType.ET_DEC_VAL:  # Temperature values usually have one decimal place
            device_class = "temperature"
            unit_of_measurement = "°C"
            icon = "mdi:thermometer-lines"
        elif signal_type == ElsterType.ET_BOOLEAN:
            device_class = "binary_sensor" 
            icon = "mdi:toggle-switch"
        elif signal_type == ElsterType.ET_INTEGER and "PERCENT" in signal_name:
            unit_of_measurement = "%"
            icon = "mdi:percent"
        elif signal_type == ElsterType.ET_INTEGER and ("HOUR" in signal_name or "TIME" in signal_name):
            device_class = "duration"
            unit_of_measurement = "h"
            icon = "mdi:timer"
        elif signal_type == ElsterType.ET_MODE:  # Operating mode select
            # This should be a select entity, not a sensor
            entity_type = "select"
            icon = "mdi:tune-vertical"
        elif signal_type == ElsterType.ET_ERR_CODE:  # Error code select
            # This should be a select entity too
            entity_type = "select"
            icon = "mdi:alert-circle-outline"
        elif signal_type == ElsterType.ET_DATE:
            device_class = "date"
            icon = "mdi:calendar"
        elif signal_type in [ElsterType.ET_DEC_VAL, ElsterType.ET_CENT_VAL, ElsterType.ET_MIL_VAL]:  # Previously DOUBLE/TRIPLE_VALUE
            # Likely energy value, but could be other types
            if "ENERGY" in signal_name or "KWH" in signal_name:
                device_class = "energy"
                unit_of_measurement = "kWh"
                icon = "mdi:lightning-bolt"
            elif "POWER" in signal_name:
                device_class = "power"
                unit_of_measurement = "W"
                icon = "mdi:flash"
            else:
                # Generic numeric value
                unit_of_measurement = ""
                icon = "mdi:numeric"
                
        # Register the entity with Home Assistant
        logger.info(f"Dynamically registering {entity_type} for signal {signal_name}")
        success = False
        
        if entity_type == "sensor":
            success = self.mqtt_interface.register_sensor(
                entity_id=entity_id,
                name=friendly_name,
                device_class=device_class,
                state_class=state_class,
                unit_of_measurement=unit_of_measurement,
                icon=icon
            )
        elif entity_type == "select":
            # For selects, we need to determine the options and mapping
            options = []
            options_map = None
            
            if signal_type == ElsterType.ET_MODE:
                # For operating modes, use MODELIST for both options and mapping
                options = list(MODELIST.values())
                options_map = MODELIST
            elif signal_type == ElsterType.ET_ERR_CODE:
                # For error codes, use ERRORLIST for both options and mapping
                options = list(ERRORLIST.values())
                options_map = ERRORLIST
            
            success = self.mqtt_interface.register_select(
                entity_id=entity_id,
                name=friendly_name,
                options=options,
                icon=icon,
                options_map=options_map
            )
        else:
            # Fallback to sensor for unsupported types
            success = self.mqtt_interface.register_sensor(
                entity_id=entity_id,
                name=friendly_name,
                icon="mdi:help-circle"
            )
            
        if success:
            logger.info(f"Successfully registered dynamic entity {entity_id}")
            # Add to registered entities
            self.registered_entities.add(entity_id)
            return True
        else:
            logger.warning(f"Failed to register dynamic entity for {signal_name}")
            return False
            
    def is_entity_registered(self, entity_id: str) -> bool:
        """
        Check if an entity is already registered.
        
        Args:
            entity_id: Entity ID to check
            
        Returns:
            bool: True if entity is registered, False otherwise
        """
        return entity_id in self.registered_entities
        
    def get_registered_entities(self) -> Set[str]:
        """
        Get the set of registered entity IDs.
        
        Returns:
            Set of registered entity IDs
        """
        return self.registered_entities.copy()
