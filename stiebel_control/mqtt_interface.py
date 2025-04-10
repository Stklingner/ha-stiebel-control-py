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
    
    def __init__(self, host: str, port: int = 1883, username: str = None, password: str = None,
                 client_id: str = "stiebel_control", 
                 discovery_prefix: str = "homeassistant",
                 base_topic: str = "stiebel_control",
                 command_callback: Optional[Callable[[str, Any], None]] = None):
        """
        Initialize the MQTT interface.
        
        Args:
            host: MQTT broker hostname or IP
            port: MQTT broker port
            username: MQTT username (optional)
            password: MQTT password (optional)
            client_id: MQTT client ID
            discovery_prefix: Home Assistant discovery prefix
            base_topic: Base topic for this device
            command_callback: Callback function for commands received via MQTT
        """
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client_id = client_id
        self.discovery_prefix = discovery_prefix
        self.base_topic = base_topic
        self.command_callback = command_callback
        
        # Initialize MQTT client
        self.client = mqtt.Client(client_id=client_id)
        if username and password:
            self.client.username_pw_set(username, password)
            
        # Set up callbacks
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
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
        try:
            logger.info(f"Attempting to connect to MQTT broker at {self.host}:{self.port}")
            logger.debug(f"MQTT client ID: {self.client_id}")
            logger.debug(f"Using username: {'Yes' if self.username else 'No'}")
            
            # Set up LWT (Last Will and Testament) message so Home Assistant knows if we disconnect
            status_topic = f"{self.base_topic}/status"
            logger.debug(f"Setting LWT status topic: {status_topic}")
            self.client.will_set(status_topic, "offline", qos=1, retain=True)
            
            # Set connection timeout to something reasonable
            self.client.connect_async(self.host, self.port, keepalive=60)
            logger.info("MQTT connect_async call made, starting client loop")
            self.client.loop_start()
            
            if not self.wait_for_connection():
                # Stop the loop to clean up resources
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
            logger.info(f"Connected to MQTT broker at {self.host}:{self.port}")
            self.connected = True
            
            # Subscribe to all command topics
            command_topic = f"{self.base_topic}/+/command"
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
            
    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received from the broker."""
        topic = msg.topic
        try:
            payload = msg.payload.decode('utf-8')
            logger.debug(f"Received message on topic {topic}: {payload}")
            
            # Check if this is a command topic
            if topic.endswith('/command'):
                entity_id = topic.split('/')[-2]
                if self.command_callback:
                    self.command_callback(entity_id, payload)
                    
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            
    def register_sensor(self, entity_id: str, name: str, device_class: str = None, 
                      state_class: str = None, unit_of_measurement: str = None, 
                      icon: str = None, value_template: str = None) -> bool:
        """
        Register a sensor entity with Home Assistant using MQTT discovery.
        
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
        
        # Create config payload
        config = {
            "name": name,
            "unique_id": f"{self.client_id}_{entity_id}",
            "state_topic": f"{self.base_topic}/{entity_id}/state",
            "availability_topic": f"{self.base_topic}/status",
            "payload_available": "online",
            "payload_not_available": "offline",
        }
        
        # Add optional fields if provided
        if device_class:
            config["device_class"] = device_class
        if state_class:
            config["state_class"] = state_class
        if unit_of_measurement:
            config["unit_of_measurement"] = unit_of_measurement
        if icon:
            config["icon"] = icon
        if value_template:
            config["value_template"] = value_template
            
        # Add device info
        config["device"] = {
            "identifiers": [self.client_id],
            "name": "Stiebel Eltron Heat Pump",
            "model": "CAN Interface",
            "manufacturer": "Stiebel Eltron"
        }
        
        # Publish discovery config
        try:
            logger.debug(f"Publishing discovery config for {entity_id}")
            self.client.publish(discovery_topic, json.dumps(config), retain=True)
            
            # Track the entity
            self.entities[entity_id] = {
                "type": "sensor",
                "config": config
            }
            
            return True
        except Exception as e:
            logger.error(f"Error registering sensor {entity_id}: {e}")
            return False
            
    def register_select(self, entity_id: str, name: str, options: list,
                       icon: str = None, options_map: Dict[int, str] = None) -> bool:
        """
        Register a select entity with Home Assistant using MQTT discovery.
        
        Args:
            entity_id: Unique ID for the select entity
            name: Display name for the select
            options: List of options for the select
            icon: Icon to use (e.g., 'mdi:menu')
            options_map: Optional mapping between internal numeric values and human-readable strings.
                         If provided, a value_template will be set up for proper conversion.
            
        Returns:
            bool: True if registered successfully, False otherwise
        """
        if not self.is_connected():
            logger.error(f"Cannot register select {entity_id}: not connected to MQTT broker")
            return False
            
        try:
            # Create the topics
            state_topic = f"{self.base_topic}/{entity_id}/state"
            command_topic = f"{self.base_topic}/{entity_id}/command"
            logger.debug(f"State topic for {entity_id}: {state_topic}")
            logger.debug(f"Command topic for {entity_id}: {command_topic}")
            
            # Create the discovery payload
            config = {
                "name": name,
                "unique_id": f"{self.client_id}_{entity_id}",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "options": options,
                "device": {
                    "identifiers": [self.client_id],
                    "name": "Stiebel Eltron Heat Pump",
                    "model": "CAN Interface",
                    "manufacturer": "Stiebel Eltron"
                }
            }
            
            # If we have a mapping between internal values and display strings,
            # add a value template to convert numeric values to strings
            if options_map:
                # Create a value template that checks each possible numeric value
                # and converts it to the corresponding string option
                value_template_parts = []
                for value, text in options_map.items():
                    value_template_parts.append(f'{{% if value == "{value}" %}}"{text}"{{% endif %}}')
                    
                # Combine all parts with else conditions
                value_template = "{{" + " else ".join(value_template_parts) + " else value }}"
                config["value_template"] = value_template
                
                # Also create a command template to convert back to internal values
                command_template_parts = []
                for value, text in options_map.items():
                    command_template_parts.append(f'{{% if value == "{text}" %}}{value}{{% endif %}}')
                    
                command_template = "{{" + " else ".join(command_template_parts) + " }}"
                config["command_template"] = command_template
                
            # Add optional fields if provided
            if icon:
                config["icon"] = icon
                
            # Create the discovery topic
            discovery_topic = f"{self.discovery_prefix}/select/{self.client_id}/{entity_id}/config"
            logger.debug(f"Discovery topic for {entity_id}: {discovery_topic}")
            
            # Publish the discovery message
            logger.info(f"Publishing discovery config for select {entity_id} to {discovery_topic}")
            result = self.client.publish(discovery_topic, json.dumps(config), qos=1, retain=True)
            if result.rc == 0:
                logger.info(f"Successfully published discovery config for {entity_id}")
            else:
                logger.error(f"Failed to publish discovery config for {entity_id}, return code: {result.rc}")
                return False
            
            # Store the entity info for later use
            self.entities[entity_id] = {
                "type": "select",
                "state_topic": state_topic,
                "command_topic": command_topic,
                "config": config
            }
            
            logger.info(f"Select {entity_id} successfully registered with Home Assistant")
            return True
            
        except Exception as e:
            logger.error(f"Error registering select {entity_id}: {e}", exc_info=True)
            return False
            
    def register_button(self, entity_id: str, name: str, icon: str = None) -> bool:
        """
        Register a button entity with Home Assistant using MQTT discovery.
        
        Args:
            entity_id: Unique ID for the button
            name: Display name for the button
            icon: Icon to use (e.g., 'mdi:refresh')
            
        Returns:
            bool: True if registered successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Cannot register button: not connected to MQTT broker")
            return False
            
        try:
            # Create the command topic
            command_topic = f"{self.base_topic}/{entity_id}/command"
            
            # Create the discovery payload
            config = {
                "name": name,
                "unique_id": f"{self.client_id}_{entity_id}",
                "command_topic": command_topic,
                "device": {
                    "identifiers": [self.client_id],
                    "name": "Stiebel Eltron Heat Pump",
                    "model": "CAN Interface",
                    "manufacturer": "Stiebel Eltron"
                }
            }
            
            # Add optional fields if provided
            if icon:
                config["icon"] = icon
                
            # Create the discovery topic
            discovery_topic = f"{self.discovery_prefix}/button/{self.client_id}/{entity_id}/config"
            
            # Publish the discovery message
            self.client.publish(discovery_topic, json.dumps(config), qos=1, retain=True)
            logger.debug(f"Registered button {entity_id} with Home Assistant")
            
            # Store the entity info for later use
            self.entities[entity_id] = {
                "type": "button",
                "command_topic": command_topic,
                "config": config
            }
            
            return True
            
        except Exception as e:
            logger.error(f"Error registering button: {e}")
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
            
            # Convert state to string if necessary
            if not isinstance(state, str):
                state = str(state)
                
            # Publish the state
            result = self.client.publish(state_topic, state, qos=1)
            if result.rc == 0:
                logger.info(f"Published state for {entity_id}: {state}")
            else:
                logger.warning(f"Failed to publish state for {entity_id}, return code: {result.rc}")
            
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
            
        logger.info(f"Waiting up to {timeout_seconds} seconds for MQTT connection to establish")
        for i in range(timeout_seconds):
            if self.connected:
                logger.info("MQTT connection confirmed")
                return True
            logger.debug(f"Waiting for MQTT connection: {i+1}/{timeout_seconds} seconds")
            time.sleep(1)
                
        logger.error(f"Timed out waiting for MQTT connection to establish")
        return False
