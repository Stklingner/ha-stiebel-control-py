"""
Service for registering entities with Home Assistant via MQTT.
"""
import logging
from typing import Dict, Any, Optional, List, Set
from stiebel_control.ha_mqtt.mqtt_interface import MqttInterface
from stiebel_control.heatpump.elster_table import (
    ElsterType,
    MODELIST,
    ERRORLIST,
    get_elster_entry_by_english_name
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
        signal_name: str,
        value: Any,
        member_name: str,
        signal_type: str = None
    ) -> Optional[str]:
        """
        Register an entity dynamically based on signal information from the Elster table.
        
        Args:
            signal_name: Name of the signal
            value: Current value of the signal
            member_name: Name of the CAN member that sent the message (e.g., 'PUMP', 'MANAGER')
            signal_type: ElsterType of the signal as string (e.g., 'ET_DEC_VAL'), optional
            
        Returns:
            str: Generated entity ID, or None if registration failed
        """
        # Get signal info from Elster table
        elster_entry = get_elster_entry_by_english_name(signal_name)
        
        # Skip if we don't have valid values to register with
        if elster_entry.name == "UNKNOWN" or elster_entry.type == ElsterType.ET_NONE:
            return None
        
        # Generate entity ID using member name instead of raw CAN ID
        entity_id = f"{signal_name.lower()}_{member_name.lower()}"
        
        # Skip if already registered
        if entity_id in self.registered_entities:
            logger.debug(f"Entity {entity_id} already registered, skipping dynamic registration")
            return entity_id
        # Determine entity type and attributes based on Elster table data
        entity_type = "sensor"  # Default entity type
        device_class = None
        state_class = "measurement"
        unit_of_measurement = None
        icon = None
        
        # Get HA entity type and unit from Elster table when available
        if hasattr(elster_entry, 'ha_entity_type') and elster_entry.ha_entity_type:
            ha_entity_parts = elster_entry.ha_entity_type.split('.')
            entity_type = ha_entity_parts[0]  # e.g., 'sensor' from 'sensor.temperature'
            
            # Extract device class if specified
            if len(ha_entity_parts) > 1:
                device_class = ha_entity_parts[1]  # e.g., 'temperature' from 'sensor.temperature'
        
        # Get unit from Elster table
        if hasattr(elster_entry, 'unit_of_measurement') and elster_entry.unit_of_measurement:
            unit_of_measurement = elster_entry.unit_of_measurement
        
        # Map icons based on device class and entity type
        if device_class == "temperature":
            icon = "mdi:thermometer-lines"
        elif device_class == "humidity":
            icon = "mdi:water-percent"
        elif device_class == "pressure":
            icon = "mdi:gauge"
        elif device_class == "power":
            icon = "mdi:flash"
        elif device_class == "energy":
            icon = "mdi:lightning-bolt"
        elif "PERCENT" in signal_name or unit_of_measurement == "%":
            icon = "mdi:percent"
        elif "HOUR" in signal_name or "TIME" in signal_name or unit_of_measurement == "h":
            device_class = "duration"
            icon = "mdi:timer"
        elif entity_type == "enum" or entity_type == "select":
            icon = "mdi:format-list-bulleted"
        elif "ERROR" in signal_name or "FAULT" in signal_name:
            icon = "mdi:alert-circle-outline"
        elif "MODE" in signal_name:
            icon = "mdi:format-list-bulleted"
        else:
            logger.warning(f"Unsupported signal type '{signal_type}' for signal {signal_name}")
            return None
                
        # Generate friendly name with device context
        friendly_name = f"{signal_name} ({member_name})"
        
        # Now register the entity based on its type
        if entity_type.lower() == "sensor" and device_class != "enum":
            success = self.mqtt_interface.register_sensor(
                entity_id=entity_id,
                name=friendly_name,
                device_class=device_class,
                state_class=state_class,
                unit_of_measurement=unit_of_measurement,
                icon=icon
            )
        elif entity_type.lower() == "binary_sensor":
            success = self.mqtt_interface.register_binary_sensor(
                entity_id=entity_id,
                name=friendly_name,
                device_class=device_class,
                icon=icon
            )
        elif device_class == "sensor.enum":
            # Check if we have mode list options
            if "MODE" in signal_name:
                options_map = list(MODELIST.values())
            # Check if we have error list options
            elif "ERROR" in signal_name:
                options_map = list(ERRORLIST.values())
            if options_map:
                success = self.mqtt_interface.register_select(
                    entity_id=entity_id,
                    name=friendly_name,
                    icon=icon,
                    attributes={"options": options_map}
            )
        else:
            # Unknown type, register as generic sensor
            success = self.mqtt_interface.register_sensor(
                entity_id=entity_id,
                name=friendly_name
            )
            
        # Update registered entities list if successful
        if success:
            self.registered_entities.add(entity_id)
            logger.info(f"Dynamically registered entity {entity_id} for signal {signal_name}")
            return entity_id  # Return entity_id on success (not boolean)
        else:
            logger.warning(f"Failed to dynamically register entity {entity_id}")
            return None  # Return None on failure (not boolean)
