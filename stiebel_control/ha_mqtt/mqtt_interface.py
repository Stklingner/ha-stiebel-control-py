"""
MQTT Interface module for communication with Home Assistant.

This module handles the MQTT communication with Home Assistant, 
publishing sensor values and subscribing to command topics.
"""

import json
import logging
import time
from typing import Dict, Any, Callable, Optional

import paho.mqtt.client as mqtt

# Configure logger
logger = logging.getLogger(__name__)


class MqttInterface:
    """
    Interface for MQTT communication with Home Assistant.
    
    This class handles the MQTT communication, including automatic discovery 
    for Home Assistant, publishing sensor values, and subscribing to command topics.
    """
    
    def __init__(self, client_id: str = "stiebel_control", broker_host: str = "localhost",
                 broker_port: int = 1883, username: str = None, password: str = None,
                 base_topic: str = "homeassistant", flat_topics: bool = True,
                 discovery_prefix: str = "homeassistant",
                 command_callback: Optional[Callable[[str, Any], None]] = None):
        """
        Initialize the MQTT interface.
        
        Args:
            client_id: MQTT client ID
            broker_host: MQTT broker hostname or IP
            broker_port: MQTT broker port
            username: MQTT username (optional)
            password: MQTT password (optional)
            base_topic: Base topic for this device
            flat_topics: Use flat topic structure (True) or hierarchical (False)
            discovery_prefix: Home Assistant discovery prefix
            command_callback: Callback function for commands received via MQTT
        """
        self.client_id = client_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.base_topic = base_topic
        self.flat_topics = flat_topics
        self.discovery_prefix = discovery_prefix
        self.command_callback = command_callback
        
        # Initialize MQTT client
        self.client = mqtt.Client(client_id=client_id)
        if username and password:
            self.client.username_pw_set(username, password)
            
        # Set up callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self._on_disconnect
        
        # Flag to track connection state
        self.connected = False
        
        # Dictionary to track registered entities
        self.entities = {}
        
    def connect(self) -> bool:
        """
        Connect to the MQTT broker.
        
        Returns:
            bool: True if connected successfully, False otherwise
        """
        # Skip connection if already connected
        if self.connected:
            logger.info("MQTT interface already connected")
            return True
            
        try:
            logger.info(f"Connecting to MQTT broker: {self.broker_host}:{self.broker_port}")
            
            # Set up LWT (Last Will and Testament)
            status_topic = f"{self.base_topic}/status"
            self.client.will_set(status_topic, "offline", qos=1, retain=True)
            
            # Connect
            self.client.connect_async(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            
            if not self.wait_for_connection():
                self.client.loop_stop()
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to MQTT broker: {e}", exc_info=True)
            # Make sure loop is stopped if connection fails
            try:
                self.client.loop_stop()
            except:
                pass
            return False
            
    def disconnect(self):
        """Disconnect from the MQTT broker."""
        logger.info("Stopping MQTT client loop")
        self.client.loop_stop()
        logger.info("Disconnecting from MQTT broker")
        self.client.disconnect()
        self.connected = False
        logger.info("Disconnected from MQTT broker")
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client connects to the broker."""
        # Map result codes to human-readable messages
        result_codes = {
            0: "Connection successful",
            1: "Incorrect protocol version",
            2: "Invalid client identifier",
            3: "Server unavailable",
            4: "Bad username or password",
            5: "Not authorized"
        }
        
        if rc == 0:
            logger.info(f"Connected to MQTT broker at {self.broker_host}:{self.broker_port}")
            self.connected = True
            
            # Use a flat topic structure for Home Assistant compatibility
            command_topic = f"{self.base_topic}/cmd/+"
            logger.info(f"Subscribing to command topic: {command_topic}")
            self.client.subscribe(command_topic)
            
            # Publish online status
            status_topic = f"{self.base_topic}/status"
            logger.info(f"Publishing online status to: {status_topic}")
            self.client.publish(status_topic, "online", qos=1, retain=True)
        else:
            error_message = result_codes.get(rc, f"Unknown error code: {rc}")
            logger.error(f"Failed to connect to MQTT broker: {error_message}")
            self.connected = False
            
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker, return code: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")
            
    def on_message(self, client, userdata, message):
        """
        Callback for when a message is received.
        
        Args:
            client: MQTT client instance
            userdata: User data
            message: Message received
        """
        try:
            topic = message.topic
            payload = message.payload.decode('utf-8')
            
            logger.debug(f"Received message on topic {topic}: {payload}")
            
            # Check if this is a command message
            # Handle both flat and hierarchical topic structures
            entity_id = None
            is_command = False
            
            if "/command" in topic:
                entity_id = topic.split("/")[-1]
                is_command = True
            elif "/cmd/" in topic:
                entity_id = topic.split("/")[-1]
                is_command = True
                
            if is_command and self.command_callback:
                self.command_callback(entity_id, payload)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
    def register_entity(self, entity_id: str, name: str, device_class: str = None,
                       state_class: str = None, unit_of_measurement: str = None,
                       icon: str = None, value_template: str = None) -> bool:
        """
        Register an entity with Home Assistant using MQTT discovery.
        
        Args:
            entity_id: Unique ID for the entity
            name: Display name for the entity
            device_class: Home Assistant device class (e.g., temperature, humidity)
            state_class: Home Assistant state class (e.g., measurement)
            unit_of_measurement: Unit of measurement (e.g., °C, %, W)
            icon: Material Design Icon to use (e.g., mdi:thermometer)
            value_template: Optional value template for processing state values
            
        Returns:
            bool: True if registered successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Cannot register sensor entities: not connected to MQTT broker")
            return False
            
        # Generate discovery topic
        discovery_topic = f"{self.discovery_prefix}/sensor/{entity_id}/config"
        
        # Topic structures - support both legacy and new formats for compatibility
        if self.flat_topics:
            state_topic = f"{self.base_topic}/state/{entity_id}"
        else:
            state_topic = f"{self.base_topic}/{entity_id}/state"
        
        # Create config payload with only necessary fields
        config = {
            "name": name,
            "unique_id": f"{self.client_id}_{entity_id}",
            "state_topic": state_topic,
            "availability_topic": f"{self.base_topic}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        
        # Add optional fields only if they have values
        for key, value in {
            "device_class": device_class,
            "state_class": state_class,
            "unit_of_measurement": unit_of_measurement,
            "icon": icon,
            "value_template": value_template
        }.items():
            if value:
                config[key] = value
                
        # Add device info
        config["device"] = {
            "identifiers": [self.client_id],
            "name": "Stiebel Eltron Heat Pump",
            "model": "CAN Interface",
            "manufacturer": "Stiebel Eltron",
            "sw_version": "1.0.0"
        }
            
        # Publish discovery and store entity if successful
        result = self.client.publish(discovery_topic, json.dumps(config), qos=1, retain=True)
        if result.rc == 0:
            # Store entity info
            self.entities[entity_id] = {
                "type": "sensor",
                "state_topic": state_topic,
                "config": config
            }
            return True
        else:
            logger.error(f"Failed to publish discovery for {entity_id}")
            return False
    
    def register_sensor(self, entity_id: str, name: str, device_class: str = None,
                      state_class: str = None, unit_of_measurement: str = None,
                      icon: str = None) -> bool:
        """
        Register a sensor entity with Home Assistant.
        
        Args:
            entity_id: Unique ID for the entity
            name: Display name for the entity
            device_class: Home Assistant device class (e.g., temperature, humidity)
            state_class: Home Assistant state class (e.g., measurement)
            unit_of_measurement: Unit of measurement (e.g., °C, %, W)
            icon: Material Design Icon to use (e.g., mdi:thermometer)
            
        Returns:
            bool: True if registered successfully, False otherwise
        """
        return self.register_entity(
            entity_id=entity_id,
            name=name,
            device_class=device_class,
            state_class=state_class,
            unit_of_measurement=unit_of_measurement,
            icon=icon
        )
    
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
        if not self.is_connected():
            logger.error("Cannot register binary sensor entities: not connected to MQTT broker")
            return False
            
        # Generate discovery topic
        discovery_topic = f"{self.discovery_prefix}/binary_sensor/{entity_id}/config"
        
        # Topic structures
        if self.flat_topics:
            state_topic = f"{self.base_topic}/state/{entity_id}"
        else:
            state_topic = f"{self.base_topic}/{entity_id}/state"
        
        # Create config payload
        config = {
            "name": name,
            "unique_id": f"{self.client_id}_{entity_id}",
            "state_topic": state_topic,
            "availability_topic": f"{self.base_topic}/status",
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
        config["device"] = {
            "identifiers": [self.client_id],
            "name": "Stiebel Eltron Heat Pump",
            "model": "CAN Interface",
            "manufacturer": "Stiebel Eltron",
            "sw_version": "1.0.0"
        }
            
        # Publish discovery
        result = self.client.publish(discovery_topic, json.dumps(config), qos=1, retain=True)
        if result.rc == 0:
            # Store entity info
            self.entities[entity_id] = {
                "type": "binary_sensor",
                "state_topic": state_topic,
                "config": config
            }
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
        if not self.is_connected():
            logger.error("Cannot register select entities: not connected to MQTT broker")
            return False
            
        # Generate discovery topic
        discovery_topic = f"{self.discovery_prefix}/select/{entity_id}/config"
        
        # Topic structures
        if self.flat_topics:
            state_topic = f"{self.base_topic}/state/{entity_id}"
            command_topic = f"{self.base_topic}/cmd/{entity_id}"
        else:
            state_topic = f"{self.base_topic}/{entity_id}/state"
            command_topic = f"{self.base_topic}/{entity_id}/command"
        
        # Create config payload
        config = {
            "name": name,
            "unique_id": f"{self.client_id}_{entity_id}",
            "state_topic": state_topic,
            "command_topic": command_topic,
            "availability_topic": f"{self.base_topic}/status",
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
        config["device"] = {
            "identifiers": [self.client_id],
            "name": "Stiebel Eltron Heat Pump",
            "model": "CAN Interface",
            "manufacturer": "Stiebel Eltron",
            "sw_version": "1.0.0"
        }
            
        # Publish discovery
        result = self.client.publish(discovery_topic, json.dumps(config), qos=1, retain=True)
        if result.rc == 0:
            # Store entity info
            self.entities[entity_id] = {
                "type": "select",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "config": config,
                "options_map": options_map
            }
            return True
        else:
            logger.error(f"Failed to publish discovery for {entity_id}")
            return False
            
    def publish_state(self, entity_id: str, state: Any) -> bool:
        """
        Publish a state update for an entity.
        
        Args:
            entity_id: ID of the entity to update
            state: New state value
            
        Returns:
            bool: True if published successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Cannot publish state: not connected to MQTT broker")
            return False
            
        if entity_id not in self.entities:
            logger.warning(f"Entity {entity_id} not registered, cannot publish state")
            return False
            
        try:
            # Get the state topic for this entity
            entity_info = self.entities[entity_id]
            logger.debug(f"Entity info for {entity_id}: {entity_info}")
            
            if "state_topic" not in entity_info:
                logger.warning(f"Entity {entity_id} has no state topic")
                return False
                
            state_topic = entity_info["state_topic"]
            logger.debug(f"Publishing to topic {state_topic}")
            
            # Convert state to string if needed and publish
            state_str = str(state) if not isinstance(state, str) else state
            result = self.client.publish(state_topic, state_str, qos=1)
            return result.rc == 0
            
        except Exception as e:
            logger.error(f"Error publishing state: {e}", exc_info=True)
            return False

    def is_connected(self) -> bool:
        """Check if the interface is currently connected to the MQTT broker.
        
        Returns:
            bool: True if connected, False otherwise
        """
        return self.connected

    def wait_for_connection(self, timeout_seconds: int = 10) -> bool:
        """Wait for the MQTT connection to be established.
        
        Args:
            timeout_seconds: Maximum time to wait in seconds
            
        Returns:
            bool: True if connected successfully within the timeout, False otherwise
        """
        if self.connected:
            return True
            
        for i in range(timeout_seconds):
            if self.connected:
                logger.info("MQTT connection established")
                return True
            time.sleep(1)
                
        logger.error("MQTT connection timed out")
        return False
