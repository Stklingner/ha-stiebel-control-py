"""Service for registering entities with Home Assistant via MQTT.

This service manages entity registration, tracking, and state updates.
It provides methods for registering different types of entities (sensors,
binary sensors, selects) and updating their states.
"""
import logging
from typing import Dict, Any, Optional, List, Tuple

from stiebel_control.ha_mqtt.mqtt_interface import MqttInterface
from stiebel_control.ha_mqtt.signal_entity_mapper import SignalEntityMapper
from stiebel_control.ha_mqtt.entity_rules import (
    classify_signal, get_entity_id_from_signal, create_entity_config, 
    format_value, format_friendly_name
)
from stiebel_control.ha_mqtt.transformations import transform_value
from stiebel_control.heatpump.elster_table import get_elster_entry_by_english_name, ElsterType

logger = logging.getLogger(__name__)

class EntityRegistrationService:
    """
    Handles registration and tracking of entities with Home Assistant via MQTT.
    
    This service is responsible for:
    1. Registering entities from static configuration
    2. Dynamically creating entities based on observed signals
    3. Tracking all registered entities
    4. Managing entity states
    """
    
    def __init__(self, 
                 mqtt_interface: MqttInterface, 
                 signal_mapper: SignalEntityMapper):
        """
        Initialize the entity registration service.
        
        Args:
            mqtt_interface: The MQTT interface for publishing entity discovery/states
            signal_mapper: The signal entity mapper for mapping signals to entities
        """
        self.mqtt_interface = mqtt_interface
        self.signal_mapper = signal_mapper
        self.entities = {}  # Store registered entities
        self.dyn_registered_entities = set()  # Store dynamically registered entities
        
        logger.info("Entity registration service initialized")
        
    @property
    def device_info(self) -> Dict[str, Any]:
        """
        Get device information to include in discovery messages.
        
        Returns:
            Dict with device information
        """
        return {
            "identifiers": [f"stiebel_control_{self.mqtt_interface.client_id}"],
            "name": "Stiebel Eltron Heat Pump",
            "model": "WPL",
            "manufacturer": "Stiebel Eltron",
            "sw_version": "1.0.0"
        }
        
        
    def register_entity_from_config(self, entity_id: str, entity_def: Dict[str, Any]) -> bool:
        """
        Register an entity from configuration.
        
        Args:
            entity_id: ID for the entity
            entity_def: Entity definition from config file
        
        Returns:
            bool: True if registration was successful, False otherwise
        """
        entity_type = entity_def.get('type', 'sensor')
        name = entity_def.get('name', entity_id)
        
        logger.info(f"Registering entity {entity_id} of type {entity_type}")
        
        # Store signal mapping if provided - critical for SignalGateway to route signals
        signal_name = entity_def.get('signal')
        can_member = entity_def.get('can_member')
        can_member_ids = entity_def.get('can_member_ids', [])
        
        if signal_name and (can_member or can_member_ids):
            # Create a mapping key for each potential CAN ID
            if can_member_ids:
                for can_id in can_member_ids:
                    self.signal_mapper.add_mapping(signal_name, can_id, entity_id)
            else:
                # Use symbolic CAN member name for now
                # The actual CAN ID will be resolved later
                self.signal_mapper.add_mapping(signal_name, can_member, entity_id)
        
        # Create a dictionary of kwargs for entity configuration
        kwargs = {}
        for key, value in entity_def.items():
            if key not in ['type', 'name', 'signal', 'can_member', 'can_member_ids']:
                kwargs[key] = value
        
        # Create discovery configuration
        config, state_topic = create_entity_config(
            entity_type=entity_type,
            entity_id=entity_id,
            name=name,
            discovery_prefix=self.mqtt_interface.discovery_prefix,
            base_topic=self.mqtt_interface.base_topic,
            client_id=self.mqtt_interface.client_id,
            device_info=self.device_info,
            **kwargs
        )
        
        # Publish discovery through MQTT interface
        discovery_topic = f"{self.mqtt_interface.discovery_prefix}/{entity_type}/{entity_id}/config"
        if self.mqtt_interface.publish_discovery(discovery_topic, config):
            # Store entity info
            self.entities[entity_id] = {
                "type": entity_type,
                "state_topic": state_topic,
                "config": config
            }
            logger.info(f"Successfully registered entity {entity_id} as {entity_type}")
            return True
        else:
            logger.error(f"Failed to publish discovery for {entity_id}")
            return False
        
    def register_sensor(self, entity_id: str, name: str, device_class: str = None,
                       state_class: str = None, unit_of_measurement: str = None,
                       icon: str = None, value_template: str = None, options: list = None,
                       attributes: dict = None) -> bool:
        """
        Register a sensor entity with Home Assistant.
        
        Args:
            entity_id: Unique ID for the entity
            name: Display name for the entity
            device_class: Home Assistant device class (e.g., temperature, humidity)
            state_class: Home Assistant state class (e.g., measurement)
            unit_of_measurement: Unit of measurement (e.g., °C, %, W)
            icon: Material Design Icon to use (e.g., mdi:thermometer)
            value_template: Optional value template for processing state values
            options: Optional list of options for enum or select entities
            
        Returns:
            bool: True if registered successfully, False otherwise
        """
        logger.debug(f"Registering sensor entity: {entity_id}, name='{name}', device_class={device_class}, " 
                   f"state_class={state_class}, unit={unit_of_measurement}, icon={icon}")
                   
        # Generate discovery topic
        discovery_topic = f"{self.mqtt_interface.discovery_prefix}/sensor/{entity_id}/config"
        
        # Generate state topic
        state_topic = f"{self.mqtt_interface.base_topic}/{entity_id}/state"
        
        # Create config payload
        config = {
            "name": name,
            "unique_id": f"{self.mqtt_interface.client_id}_{entity_id}",
            "state_topic": state_topic,
            "availability_topic": f"{self.mqtt_interface.base_topic}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        
        if attributes:
            config.update({
                "json_attributes_topic": state_topic.replace("state", "attributes"),
                "json_attributes_template": "{{ value_json | tojson }}"
            })

        # Add optional fields only if they have values
        for key, value in {
            "device_class": device_class,
            "state_class": state_class,
            "unit_of_measurement": unit_of_measurement,
            "icon": icon,
            "options": options,
            "value_template": value_template
        }.items():
            if value:
                config[key] = value
                
        # Add device info
        config["device"] = self.device_info
        
        # Publish discovery through MQTT interface
        if self.mqtt_interface.publish_discovery(discovery_topic, config):
            # Store entity info
            self.entities[entity_id] = {
                "type": "sensor",
                "state_topic": state_topic,
                "config": config
            }
            logger.debug(f"Successfully registered entity {entity_id} as sensor")
            return True
        else:
            logger.error(f"Failed to publish discovery for {entity_id}")
            return False
            
    def register_binary_sensor(self, entity_id: str, name: str, device_class: str = None,
                              icon: str = None) -> bool:
        """
        Register a binary sensor entity with Home Assistant.
        
        Args:
            entity_id: Unique ID for the entity
            name: Display name for the entity
            device_class: Home Assistant device class (e.g., power, battery)
            icon: Material Design Icon to use
            
        Returns:
            bool: True if registered successfully, False otherwise
        """
        logger.debug(f"Registering binary sensor entity: {entity_id}, name='{name}', device_class={device_class}, icon={icon}")
        
        # Generate discovery topic
        discovery_topic = f"{self.mqtt_interface.discovery_prefix}/binary_sensor/{entity_id}/config"
        
        # Generate state topic
        state_topic = f"{self.mqtt_interface.base_topic}/{entity_id}/state"
        
        # Create config payload
        config = {
            "name": name,
            "unique_id": f"{self.mqtt_interface.client_id}_{entity_id}",
            "state_topic": state_topic,
            "availability_topic": f"{self.mqtt_interface.base_topic}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
            "payload_on": "ON",
            "payload_off": "OFF"
        }
        
        # Add optional fields
        if device_class:
            config["device_class"] = device_class
        if icon:
            config["icon"] = icon
            
        # Add device info
        config["device"] = self.device_info
        
        # Publish discovery through MQTT interface
        if self.mqtt_interface.publish_discovery(discovery_topic, config):
            # Store entity info
            self.entities[entity_id] = {
                "type": "binary_sensor",
                "state_topic": state_topic,
                "config": config
            }
            logger.debug(f"Successfully registered entity {entity_id} as binary sensor")
            return True
        else:
            logger.error(f"Failed to publish discovery for {entity_id}")
            return False
            
    def register_select(self, entity_id: str, name: str, options: list = None,
                       icon: str = None, options_map: dict = None) -> bool:
        """
        Register a select entity with Home Assistant.
        
        Args:
            entity_id: Unique ID for the entity
            name: Display name for the entity
            options: List of options for the select entity
            icon: Material Design Icon to use
            options_map: Optional mapping of raw values to display options
            
        Returns:
            bool: True if registered successfully, False otherwise
        """
        logger.debug(f"Registering select entity: {entity_id}, name='{name}', options={options}, "
                   f"icon={icon}, options_map={options_map}")
        
        # Generate discovery topic
        discovery_topic = f"{self.mqtt_interface.discovery_prefix}/select/{entity_id}/config"
        
        # Generate topics
        state_topic = f"{self.mqtt_interface.base_topic}/{entity_id}/state"
        command_topic = f"{self.mqtt_interface.base_topic}/{entity_id}/command"
        
        # Create config payload
        config = {
            "name": name,
            "unique_id": f"{self.mqtt_interface.client_id}_{entity_id}",
            "state_topic": state_topic,
            "command_topic": command_topic,
            "availability_topic": f"{self.mqtt_interface.base_topic}/status",
            "payload_available": "online",
            "payload_not_available": "offline"
        }
        
        # Add options if provided
        if options is not None:
            config["options"] = options
        elif options_map is not None:
            # Use options from options_map if direct options not provided
            if isinstance(options_map, dict):
                config["options"] = list(options_map.values())
            else:
                config["options"] = list(options_map)
                
        # Add icon if provided
        if icon:
            config["icon"] = icon
            
        # Add device info
        config["device"] = self.device_info
        
        # Publish discovery through MQTT interface
        if self.mqtt_interface.publish_discovery(discovery_topic, config):
            # Store entity info
            self.entities[entity_id] = {
                "type": "select",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "config": config,
                "options": options
            }
            logger.debug(f"Successfully registered entity {entity_id} as select entity")
            return True
        else:
            logger.error(f"Failed to publish discovery for {entity_id}")
            return False
            
    def register_dynamic_entity(
        self, 
        signal_name: str,
        value: Any,
        member_name: str,
        signal_type: Optional[str] = None,
        permissive_signal_handling: bool = False
    ) -> Optional[str]:
        """
        Register an entity dynamically based on signal information from the Elster table.
        
        Args:
            signal_name: Name of the signal
            value: Current value of the signal
            member_name: Name of the CAN member that sent the message (e.g., 'PUMP', 'MANAGER')
            signal_type: ElsterType of the signal as string (e.g., 'ET_DEC_VAL'), optional
            permissive_signal_handling: If True, attempt to register signals even with unknown types
            
        Returns:
            str: Generated entity ID, or None if registration failed
        """
        # Get signal info from Elster table if not provided
        elster_entry = get_elster_entry_by_english_name(signal_name)
        if not elster_entry and not permissive_signal_handling:
            logger.warning(f"Cannot register entity for unknown signal: {signal_name}")
            return None
        
        # Use signal_type from elster_entry if not provided
        if signal_type is None and elster_entry:
            signal_type = elster_entry.type
            
        # Generate entity ID
        entity_id = get_entity_id_from_signal(signal_name, member_name)
        
        # Skip if already registered
        if entity_id in self.entities or entity_id in self.dyn_registered_entities:
            logger.debug(f"Entity {entity_id} already registered")
            return entity_id
        
        # Get entity classification from rules module
        entity_config = classify_signal(signal_name, signal_type, value)
        entity_type = entity_config['entity_type']
        config = entity_config['config']
        
        # Create friendly name for the entity
        formatted_signal = format_friendly_name(signal_name)
        formatted_member = format_friendly_name(member_name)
        friendly_name = f"{formatted_signal} ({formatted_member})"
        
        # Create discovery configuration
        discovery_config, state_topic = create_entity_config(
            entity_type=entity_type,
            entity_id=entity_id,
            name=friendly_name,
            discovery_prefix=self.mqtt_interface.discovery_prefix,
            base_topic=self.mqtt_interface.base_topic,
            client_id=self.mqtt_interface.client_id,
            device_info=self.device_info,
            **config
        )
        
        # Publish discovery configuration
        discovery_topic = f"{self.mqtt_interface.discovery_prefix}/{entity_type}/{entity_id}/config"
        success = self.mqtt_interface.publish_discovery(discovery_topic, discovery_config)
        
        # Update entity list and register signal mapping if successful
        if success:
            # Store entity info
            self.entities[entity_id] = {
                "type": entity_type,
                "state_topic": state_topic,
                "config": discovery_config
            }
            self.dyn_registered_entities.add(entity_id)
            
            logger.info(f"Dynamically registered entity {entity_id} for signal {signal_name}")
            
            # Register the signal mapping in SignalEntityMapper
            self.signal_mapper.add_mapping(signal_name, member_name, entity_id)
            
            return entity_id
        else:
            logger.warning(f"Failed to dynamically register entity {entity_id}")
            return None
            
    # The _format_state_value method has been replaced by format_value from entity_rules

    def update_entity_state(self, entity_id: str, state: Any) -> bool:
        """
        Update the state of an entity.
            
        Args:
            entity_id: Entity ID to update
            state: New state value
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        if entity_id not in self.entities:
            logger.warning(f"Cannot update state for unknown entity: {entity_id}")
            return False

        state_topic = self.entities[entity_id].get("state_topic")
        if not state_topic:
            logger.warning(f"No state topic found for entity {entity_id}")
            return False

        # Format state value based on entity type
        entity_type = self.entities[entity_id].get("type")
        formatted_state = format_value(state, entity_type)

        # Publish state
        success = self.mqtt_interface.publish_state(state_topic, formatted_state)
        
        if success:
            logger.debug(f"Updated state for {entity_id}: {formatted_state}")
        else:
            logger.warning(f"Failed to update state for {entity_id}")
            
        return success
        
    def update_entity_attributes(self, entity_id: str, attributes: Dict[str, Any]) -> bool:
        """
        Update the attributes of an entity.
            
        Args:
            entity_id: Entity ID to update
            attributes: Dictionary of attributes to update
            
        Returns:
            bool: True if update was successful, False otherwise
        """
        if entity_id not in self.entities:
            logger.warning(f"Cannot update attributes for unknown entity: {entity_id}")
            return False

        # Get the attributes topic
        attributes_topic = f"{self.mqtt_interface.base_topic}/{entity_id}/attributes"
        
        # Publish attributes
        success = self.mqtt_interface.publish_state(attributes_topic, attributes)
        
        if success:
            logger.debug(f"Updated attributes for {entity_id}: {attributes}")
        else:
            logger.warning(f"Failed to update attributes for {entity_id}")
            
        return success

    def get_entity_command_topic(self, entity_id: str) -> Optional[str]:
        """
        Get the command topic for an entity if it exists.
        
        Args:
            entity_id: Entity ID to look up
            
        Returns:
            str: Command topic or None if the entity doesn't exist or doesn't support commands
        """
        if entity_id not in self.entities:
            return None
            
        entity_info = self.entities[entity_id]
        return entity_info.get("command_topic")
    

