"""
Entity classification and configuration rules for Home Assistant MQTT integration.

This module contains pure functions for determining entity types and configurations
based on signal characteristics. It handles the classification logic separate from
the registration process.
"""
import logging
from typing import Dict, Any, Optional, List, Tuple

from stiebel_control.heatpump.elster_table import get_elster_entry_by_english_name, ElsterType

logger = logging.getLogger(__name__)

HA_ENTITY_TYPES = {
    "sensor": {"entity_type": "sensor","device_class": "", "unit_of_measurement": "", "state_class": ""},
    "sensor.temperature": {"entity_type": "sensor","device_class": "temperature", "unit_of_measurement": "°C", "state_class": "measurement", "icon": "mdi:thermometer"},
    "sensor.power": {"entity_type": "sensor","device_class": "power", "unit_of_measurement": "kW", "state_class": "measurement", "icon": "mdi:light-bulb"},
    "sensor.energy": {"entity_type": "sensor","device_class": "energy", "unit_of_measurement": "kWh", "state_class": "total_increasing", "icon": "mdi:lightning-bolt"},
    "sensor.pressure": {"entity_type": "sensor","device_class": "pressure", "unit_of_measurement": "bar", "state_class": "measurement", "icon": "mdi:gauge"},
    "sensor.percent": {"entity_type": "sensor","device_class": "", "unit_of_measurement": "%", "state_class": "", "icon": "mdi:percent"},
    "sensor.hour": {"entity_type": "sensor","device_class": "", "unit_of_measurement": "h", "state_class": "", "icon": "mdi:clock-outline"},
    "sensor.day": {"entity_type": "sensor","device_class": "", "unit_of_measurement": "d", "state_class": "", "icon": "mdi:calendar"},
    "sensor.month": {"entity_type": "sensor","device_class": "", "unit_of_measurement": "m", "state_class": "", "icon": "mdi:calendar-month-outline"},
    "sensor.year": {"entity_type": "sensor","device_class": "", "unit_of_measurement": "y", "state_class": "", "icon": "mdi:calendar-year-outline"},
    "binary_sensor": {"entity_type": "binary_sensor"},
    "binary_sensor.power": {"entity_type": "binary_sensor","device_class": "power"},
}

def classify_signal(signal_name: str, signal_type: Optional[str] = None, value: Any = None) -> Dict[str, Any]:
    """
    Determine the appropriate entity type and attributes for a signal.
    
    Args:
        signal_name: Name of the signal
        signal_type: Type of the signal from the elster table (optional)
        value: Current value of the signal (optional)
        
    Returns:
        Dictionary with entity type and configuration
    """
    entity_type = "sensor"  # Default entity type
    entity_config = {}
    
    # Get Elster entry to access ha_entity_type if available
    elster_entry = get_elster_entry_by_english_name(signal_name)
    
    # If no signal type provided, try to get it from elster table
    if not signal_type and elster_entry:
        signal_type = elster_entry.type
    
    # First check if we have an ha_entity_type in the Elster entry
    if elster_entry and hasattr(elster_entry, 'ha_entity_type'):
        ha_type = elster_entry.ha_entity_type
        if ha_type in HA_ENTITY_TYPES:
            # Use the predefined configuration from HA_ENTITY_TYPES
            config = HA_ENTITY_TYPES[ha_type].copy()
            entity_type = config.pop("entity_type")
            
            # Add non-empty values to entity_config
            for key, value in config.items():
                if value:  # Only add non-empty values
                    entity_config[key] = value
            # Override the units if we have one from the Elster entry
            if hasattr(elster_entry, 'unit_of_measurement'):
                entity_config['unit_of_measurement'] = elster_entry.unit_of_measurement

            logger.debug(f"Using ha_entity_type '{ha_type}' for signal {signal_name}")
            
        else:
            logger.warning(f"Unknown ha_entity_type '{ha_type}' for signal {signal_name}")
    
    # If we didn't get configuration from ha_entity_type, use rules
    if not entity_config:
        if signal_type == ElsterType.ET_MODE.name or signal_type == ElsterType.ET_ERR_CODE.name:
            # For dynamically registered entities, always use sensor with enum device_class
            # instead of select to match existing behavior
            entity_type = "sensor"
            entity_config["device_class"] = "enum"
        elif signal_type in [ElsterType.ET_BOOLEAN.name, ElsterType.ET_LITTLE_BOOL.name]:
            entity_type = "binary_sensor"
        elif "STATUS" in signal_name or "STATE" in signal_name:
            # Status or state signals could be binary sensors or select entities
            if isinstance(value, bool) or (isinstance(value, (int, float)) and (value == 0 or value == 1)):
                entity_type = "binary_sensor"
            else:
                entity_type = "sensor"
        elif "TEMP" in signal_name:
            entity_type = "sensor"
            entity_config["device_class"] = "temperature"
            entity_config["unit_of_measurement"] = "°C"
            entity_config["state_class"] = "measurement"
        elif "PRESSURE" in signal_name:
            entity_type = "sensor"
            entity_config["device_class"] = "pressure"
            entity_config["unit_of_measurement"] = "bar"
            entity_config["state_class"] = "measurement"
        elif "PERCENT" in signal_name or signal_name.endswith("_PCT"):
            entity_type = "sensor"
            entity_config["unit_of_measurement"] = "%"
            entity_config["state_class"] = "measurement"
        elif "HOUR" in signal_name or "TIME" in signal_name:
            entity_type = "sensor"
            entity_config["unit_of_measurement"] = "h"
            entity_config["state_class"] = "total_increasing"
        elif "COUNT" in signal_name or "COUNTER" in signal_name:
            entity_type = "sensor"
            entity_config["state_class"] = "total_increasing"
    
    # Add state class for numeric values if not already set
    if entity_type == "sensor" and "state_class" not in entity_config:
        # For raw numeric values, adding a state class helps with history/graphing
        if isinstance(value, (int, float)):
            entity_config["state_class"] = "measurement"
    
    # Add icon based on entity type
    entity_config["icon"] = get_icon_for_entity(entity_type, entity_config.get("device_class"), signal_name)
    
    return {
        "entity_type": entity_type,
        "config": entity_config
    }

def format_friendly_name(text: str) -> str:
    """
    Format a name to be more human-readable.
    
    Args:
        text: Text to format
        
    Returns:
        Formatted text with spaces instead of underscores and title case
    """
    # Replace underscores with spaces
    text = text.replace("_", " ")
    
    # Handle special cases for common abbreviations that should remain uppercase
    words = text.split()
    formatted_words = []
    for word in words:
        if word.upper() in ["ID", "CAN", "MQTT", "IP", "URL", "WPS", "PIN", "HTTP", "CRC"]:
            formatted_words.append(word.upper())
        else:
            # Capitalize only the first letter, keeping the rest lowercase
            formatted_words.append(word.capitalize())
    
    return " ".join(formatted_words)

def get_entity_id_from_signal(signal_name: str, member_name: str) -> str:
    """
    Generate an entity ID from signal and member names.
    
    Args:
        signal_name: Name of the signal
        member_name: Name of the CAN member
        
    Returns:
        Valid entity ID string
    """
    # Clean member name (lowercase, replace spaces)
    clean_member = member_name.lower().replace(" ", "_")
    
    # Clean signal name (lowercase, replace spaces)
    clean_signal = signal_name.lower().replace(" ", "_")
    
    # Create entity ID
    entity_id = f"{clean_member}_{clean_signal}"
    
    # Ensure it's valid (no special chars except underscore)
    entity_id = "".join(c for c in entity_id if c.isalnum() or c == "_")
    
    return entity_id

def get_icon_for_entity(entity_type: str, device_class: str, signal_name: str) -> str:
    """
    Determine an appropriate icon for the entity.
    
    Args:
        entity_type: Type of entity (sensor, binary_sensor, select)
        device_class: Device class of the entity
        signal_name: Name of the signal
        
    Returns:
        mdi icon string
    """
    if entity_type == "binary_sensor":
        if "STATUS" in signal_name:
            return "mdi:information-outline"
        elif "ALARM" in signal_name or "ERROR" in signal_name:
            return "mdi:alert-circle-outline"
        else:
            return "mdi:toggle-switch"
    elif entity_type == "select":
        return "mdi:format-list-bulleted"
    elif entity_type == "sensor":
        if "TEMP" in signal_name or device_class == "temperature":
            return "mdi:thermometer"
        elif "PRESSURE" in signal_name or device_class == "pressure":
            return "mdi:gauge"
        elif "PERCENT" in signal_name or signal_name.endswith("_PCT") or device_class == "enum":
            return "mdi:percent"
        elif "MINUTE" in signal_name or device_class == "timestamp":
            return "mdi:clock-outline"
        elif "HOUR" in signal_name or device_class == "timestamp":
            return "mdi:clock-outline"
        elif "DAY" in signal_name or device_class == "date":
            return "mdi:calendar"
        elif "MONTH" in signal_name or device_class == "month":
            return "mdi:calendar-month-outline"
        elif "YEAR" in signal_name or device_class == "year":
            return "mdi:calendar-year-outline"
        elif "COUNT" in signal_name or "COUNTER" in signal_name:
            return "mdi:counter"
        else:
            return "mdi:chart-line"
            
    # Default fallback icon
    return "mdi:information-outline"

def create_entity_config(entity_type: str, entity_id: str, name: str, 
                        discovery_prefix: str, base_topic: str, client_id: str,
                        device_info: Dict[str, Any], **kwargs) -> Tuple[Dict[str, Any], str]:
    """
    Create discovery configuration based on entity type.
    
    Args:
        entity_type: Type of entity (sensor, binary_sensor, select)
        entity_id: Entity ID
        name: Friendly name of the entity
        discovery_prefix: MQTT discovery prefix
        base_topic: Base topic for MQTT
        client_id: Client ID for MQTT
        device_info: Device information dictionary
        **kwargs: Additional entity-specific configuration
        
    Returns:
        Tuple of (discovery_config, state_topic)
    """
    # Generate discovery topic
    discovery_topic = f"{discovery_prefix}/{entity_type}/{entity_id}/config"
    
    # Generate state topic
    state_topic = f"{base_topic}/{entity_id}/state"
    
    # Base configuration for all entity types
    config = {
        "name": name,
        "unique_id": f"{client_id}_{entity_id}",
        "state_topic": state_topic,
        "availability_topic": f"{base_topic}/status",
        "payload_available": "online",
        "payload_not_available": "offline",
    }
    
    # Add device info
    config["device"] = device_info
    
    # Add entity-specific configuration
    if entity_type == "binary_sensor":
        config["payload_on"] = "ON"
        config["payload_off"] = "OFF"
    elif entity_type == "select":
        config["command_topic"] = f"{base_topic}/{entity_id}/set"
        if "options" in kwargs:
            config["options"] = kwargs["options"]
    
    # Add additional attributes from kwargs
    for key, value in kwargs.items():
        if key not in ["options"] and value is not None:  # options already handled for select
            config[key] = value
    
    return config, state_topic

def format_value(value: Any, entity_type: str) -> Any:
    """
    Format a value based on entity type for MQTT publishing.
    
    Args:
        value: The value to format
        entity_type: Type of entity
        
    Returns:
        Formatted value ready for MQTT publishing
    """
    if entity_type == "binary_sensor":
        # Convert to ON/OFF
        return "ON" if value else "OFF"
    elif isinstance(value, bool):
        # Convert boolean to ON/OFF for other entity types
        return "ON" if value else "OFF"
    elif value is None:
        # Convert None to unknown
        return "unknown"
    elif isinstance(value, dict):
        # For attributes or other JSON data, leave as dict for MQTT interface to handle
        return value
    else:
        # Convert other types to string
        return str(value)
