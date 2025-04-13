"""
Service for registering entities with Home Assistant via MQTT.

This service manages entity registration, tracking, and state updates.
It provides methods for registering different types of entities (sensors,
binary sensors, selects) and updating their states.
"""
import logging
from typing import Dict, Any, Optional

from stiebel_control.ha_mqtt.mqtt_interface import MqttInterface
from stiebel_control.ha_mqtt.signal_entity_mapper import SignalEntityMapper
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
        # Set up device info
        self.device_info = self._create_device_info()
        
        logger.info("Entity registration service initialized")
        
    def _create_device_info(self) -> Dict[str, Any]:
        """
        Create device info for Home Assistant.
        
        Returns:
            Dict[str, Any]: Device info
        """
        device_info = {
            "identifiers": [self.mqtt_interface.client_id],
            "name": "Stiebel Eltron Heat Pump",
            "model": "CAN Interface",
            "manufacturer": "Stiebel Eltron",
            "sw_version": "1.0.0"
        }
        
        return device_info
        
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
        if entity_id in self.entities:
            logger.debug(f"Entity {entity_id} already registered, skipping")
            return True
            
        entity_type = entity_def.get('type', 'sensor')
        name = entity_def.get('name', entity_id)
        success = False
        
        # Store signal mapping if provided
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
        
        if entity_type == 'sensor':
            # Register a sensor entity
            success = self.register_sensor(
                entity_id=entity_id,
                name=name,
                device_class=entity_def.get('device_class'),
                state_class=entity_def.get('state_class'),
                unit_of_measurement=entity_def.get('unit_of_measurement'),
                icon=entity_def.get('icon')
            )
        elif entity_type == 'binary_sensor':
            # Register a binary sensor entity
            success = self.register_binary_sensor(
                entity_id=entity_id,
                name=name,
                device_class=entity_def.get('device_class'),
                icon=entity_def.get('icon')
            )
        elif entity_type == 'select':
            # Register a select entity
            options = entity_def.get('options', [])
            success = self.register_select(
                entity_id=entity_id,
                name=name,
                options=options,
                icon=entity_def.get('icon'),
                options_map=entity_def.get('options_map')
            )
        else:
            logger.warning(f"Unsupported entity type '{entity_type}' for entity {entity_id}")
            return False
            
        if success:
            # Add to registered entities
            self.dyn_registered_entities.add(entity_id)
            logger.info(f"Registered {entity_type} entity {entity_id}")
            
        return success
        
    def register_sensor(self, entity_id: str, name: str, device_class: str = None,
                       state_class: str = None, unit_of_measurement: str = None,
                       icon: str = None, value_template: str = None, options: list = None) -> bool:
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
                "options_map": options_map
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
        # Get signal info from Elster table
        elster_entry = get_elster_entry_by_english_name(signal_name)
        
        # Skip if we don't have valid values to register with
        if elster_entry.name == "UNKNOWN":
            logger.warning(f"Signal {signal_name} not found in Elster table, skipping dynamic registration")
            return None
        elif elster_entry.type == ElsterType.ET_NONE:
            # Check if permissive signal handling is enabled
            if permissive_signal_handling:
                logger.info(f"Signal {signal_name} has unknown type, but registering anyway due to permissive mode")
                # Will continue with registration below
            else:
                logger.warning(f"Signal {signal_name} has unknown type, skipping dynamic registration")
                return None
        
        # Clean up signal name for use in entity ID
        signal_id = signal_name.lower().replace(' ', '_').replace('.', '_')
        
        # Create entity ID
        entity_id = f"{member_name.lower()}_{signal_id}"

        # Skip if already registered
        if entity_id in self.dyn_registered_entities:
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
            logger.debug(f"Entity type from Elster table: {entity_type}")
            
            # Extract device class if specified
            if len(ha_entity_parts) > 1:
                device_class = ha_entity_parts[1]  # e.g., 'temperature' from 'sensor.temperature'
                logger.debug(f"Device class from Elster table: {device_class}")
        
        # Get unit from Elster table
        if hasattr(elster_entry, 'unit_of_measurement') and elster_entry.unit_of_measurement:
            unit_of_measurement = elster_entry.unit_of_measurement
            logger.debug(f"Unit of measurement from Elster table: {unit_of_measurement}")
        
        # Map icons based on device class and entity type
        if device_class == "temperature" or unit_of_measurement == "°C":
            icon = "mdi:thermometer-lines"
        elif device_class == "humidity":
            icon = "mdi:water-percent"
        elif device_class == "pressure":
            icon = "mdi:gauge"
        elif device_class == "power" or unit_of_measurement == "W":
            icon = "mdi:flash"
        elif device_class == "energy" or unit_of_measurement == "Wh":
            icon = "mdi:lightning-bolt"
        elif "PERCENT" in signal_name or unit_of_measurement == "%":
            icon = "mdi:percent"
        elif "HOUR" in signal_name or unit_of_measurement == "h":
            icon = "mdi:timer"
        elif "MINUTE" in signal_name or unit_of_measurement == "min":
            icon = "mdi:timer-outline"
        elif "TIME" in signal_name:
            icon = "mdi:clock-outline"
        elif "DAY" in signal_name or unit_of_measurement == "d":
            icon = "mdi:calendar-today"
        elif "MONTH" in signal_name:
            icon = "mdi:calendar-month"
        elif "YEAR" in signal_name:
            icon = "mdi:calendar"
        elif entity_type == "enum" or entity_type == "select":
            icon = "mdi:format-list-bulleted"
        elif "ERROR" in signal_name or "FAULT" in signal_name:
            icon = "mdi:alert-circle-outline"
        elif "MODE" in signal_name:
            icon = "mdi:format-list-bulleted"
        else:
            icon = "mdi:information-outline"
            logger.debug(f"Unresolved signal type '{signal_type}' for signal {signal_name}")
                
        # Generate friendly name with device context
        friendly_name = f"{signal_name.replace('_', ' ').title()} ({member_name.replace('_', ' ').title()})"
        
        # Register with Home Assistant
        if entity_type.lower() == "sensor" and device_class != "enum":
            success = self.register_sensor(
                entity_id=entity_id,
                name=friendly_name,
                device_class=device_class,
                state_class=state_class,
                unit_of_measurement=unit_of_measurement,
                icon=icon
            )
        elif entity_type.lower() == "binary_sensor":
            success = self.register_binary_sensor(
                entity_id=entity_id,
                name=friendly_name,
                device_class=device_class,
                icon=icon
            )
        elif device_class == "sensor.enum":
            # Check if we have mode list options
            options_map = None
            if "MODE" in signal_name:
                options_map = list(MODELIST.values())
            # Check if we have error list options
            elif "ERROR" in signal_name:
                options_map = list(ERRORLIST.values())
                
            if options_map:
                success = self.mqtt_interface.register_sensor(
                    entity_id=entity_id,
                    name=friendly_name,
                    device_class=device_class,
                    icon=icon,
                    attributes={"options": options_map}
                )
            else:
                # No options available, register as regular sensor
                success = self.mqtt_interface.register_sensor(
                    entity_id=entity_id,
                    name=friendly_name,
                    device_class=device_class,
                    icon=icon
                )
        else:
            # Unknown type, register as generic sensor
            permissive_info = " (permissive mode)" if permissive_signal_handling else ""
            logger.info(f"Registering {entity_id} as generic sensor{permissive_info}")
            
            # In permissive mode, try to guess better defaults based on signal name
            if permissive_signal_handling and elster_entry.type == ElsterType.ET_NONE:
                # Add a special icon for permissive mode signals
                if not icon:
                    icon = "mdi:test-tube"
                    
                # Try to extract unit from signal name if not set
                if not unit_of_measurement:
                    if "TEMP" in signal_name:
                        unit_of_measurement = "°C"
                    elif "PERCENT" in signal_name:
                        unit_of_measurement = "%"
                    elif "TIME" in signal_name or "HOUR" in signal_name:
                        unit_of_measurement = "h"
            
            success = self.mqtt_interface.register_sensor(
                entity_id=entity_id,
                name=friendly_name,
                icon=icon,
                unit_of_measurement=unit_of_measurement
            )
                
        # Update entity list and register signal mapping if successful
        if success:
            logger.info(f"Dynamically registered entity {entity_id} for signal {signal_name}")
            # Register the signal mapping in SignalEntityMapper
            # Use the member_name directly, no need to convert
            self.signal_mapper.add_mapping(signal_name, member_name, entity_id)
                    
            return entity_id  # Return entity_id on success (not boolean)
        else:
            logger.warning(f"Failed to dynamically register entity {entity_id}")
            return None  # Return None on failure (not boolean)
        
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
            logger.warning(f"Entity {entity_id} not registered, cannot update state")
            return False
        
        entity_info = self.entities[entity_id]
        state_topic = entity_info.get("state_topic")
        
        if not state_topic:
            logger.warning(f"Entity {entity_id} has no state topic")
            return False
        
        logger.info(f"Updating state for entity {entity_id} to {state}")
        return self.mqtt_interface.publish_state(state_topic, state)
    
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
    

