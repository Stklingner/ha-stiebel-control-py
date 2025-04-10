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
        signal_name: str, 
        signal_type: ElsterType, 
        value: Any, 
        can_id: int
    ) -> Optional[str]:
        """
        Register an entity dynamically based on signal type, name, and value.
        
        Args:
            signal_name: Name of the signal
            signal_type: ElsterType of the signal
            value: Current value of the signal
            can_id: CAN ID of the member that sent the message
            
        Returns:
            str: Generated entity ID, or None if registration failed
        """
        # Skip if we don't have valid values to register with
        if signal_name == "UNKNOWN" or signal_type == ElsterType.ET_NONE:
            return None
            
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
                device_class = None
                unit_of_measurement = None
                icon = "mdi:gauge"
                
        # Create a unique entity ID based on signal name and CAN member
        entity_id = f"{signal_name.lower()}_{can_id:x}"
        
        # Skip if already registered
        if entity_id in self.registered_entities:
            logger.debug(f"Entity {entity_id} already registered, skipping dynamic registration")
            return entity_id
        
        # Register based on entity type
        if entity_type == "sensor":
            result = self.mqtt_interface.register_sensor(
                entity_id=entity_id,
                name=signal_name,
                device_class=device_class,
                state_class=state_class,
                unit_of_measurement=unit_of_measurement,
                icon=icon
            )
        elif entity_type == "select":
            # For selects, determine appropriate options
            options_map = None
            if signal_type == ElsterType.ET_MODE:
                # Use the MODELIST for operating modes
                options = list(MODELIST.values())
                options_map = {key: value for key, value in MODELIST.items()}
            elif signal_type == ElsterType.ET_ERR_CODE:
                # Use ERRORLIST for error codes
                options = list(ERRORLIST.values())
                options_map = {key: value for key, value in ERRORLIST.items()}
            else:
                # Generic options if no specific map is available
                options = ["Unknown"]
            
            result = self.mqtt_interface.register_select(
                entity_id=entity_id,
                name=signal_name,
                options=options,
                icon=icon,
                options_map=options_map
            )
        else:
            logger.warning(f"Unsupported entity type {entity_type} for dynamic registration")
            return None
            
        if result:
            self.registered_entities.add(entity_id)
            logger.info(f"Dynamically registered {entity_type} entity {entity_id} for signal {signal_name}")
        else:
            logger.error(f"Failed to dynamically register entity for signal {signal_name}")
            return None
            
        return entity_id
            
    def register_manual_entities(self, raw_config: Dict[str, Any]) -> int:
        """
        Process and register entities from a structured configuration file.
        Handles nested configuration structure from entity_config.yaml.
        
        Args:
            raw_config: Raw configuration dictionary from entity_config.yaml
            
        Returns:
            int: Number of successfully registered entities
        """
        if not raw_config or 'entities' not in raw_config:
            logger.warning("No entities section found in configuration")
            return 0
            
        entities_config = raw_config['entities']
        successful_registrations = 0
        
        # Process each entity category (sensors, buttons, selects)
        for category, entities in entities_config.items():
            if not isinstance(entities, dict):
                logger.warning(f"Invalid format for category '{category}', expected dictionary")
                continue
                
            logger.info(f"Processing {len(entities)} {category} entities from manual configuration")
            
            # Process each entity in this category
            for entity_id, entity_def in entities.items():
                # Add the entity type if not explicitly defined
                if 'type' not in entity_def:
                    # Remove trailing 's' from category name for entity type
                    entity_type = category[:-1] if category.endswith('s') else category
                    entity_def['type'] = entity_type
                
                # Register the entity
                if self.register_entity_from_config(entity_id, entity_def):
                    successful_registrations += 1
        
        logger.info(f"Successfully registered {successful_registrations} manual entities")
        return successful_registrations
        
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
