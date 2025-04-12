"""
MQTT Interface module for communication with Home Assistant.

This module handles low-level MQTT communication with Home Assistant,
providing basic publish/subscribe functionality and connection management.
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
    Low-level interface for MQTT communication with Home Assistant.
    
    This class handles the core MQTT connectivity and messaging operations,
    providing methods for publishing to topics and subscribing to commands.
    It does not contain entity-specific logic, which is handled by the
    EntityRegistrationService.
    """
    
    def __init__(self, client_id: str = "stiebel_control", broker_host: str = "localhost",
                 broker_port: int = 1883, username: str = None, password: str = None,
                 base_topic: str = "homeassistant",
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
            discovery_prefix: Home Assistant discovery prefix used for auto-discovery
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
        
        # Device-specific information
        self.client_id = client_id
        self.base_topic = base_topic
        self.discovery_prefix = discovery_prefix
        
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
            
    def publish_discovery(self, discovery_topic: str, config: dict) -> bool:
        """
        Publish discovery configuration to Home Assistant for automatic entity setup.
        
        Args:
            discovery_topic: Full MQTT discovery topic
            config: Discovery configuration payload
            
        Returns:
            bool: True if published successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Cannot publish discovery: not connected to MQTT broker")
            return False
            
        logger.debug(f"Publishing to discovery topic: {discovery_topic}")
        logger.debug(f"Discovery config: {config}")
        
        result = self.client.publish(discovery_topic, json.dumps(config), qos=1, retain=True)
        return result.rc == 0
            
    def publish_state(self, topic: str, state: Any) -> bool:
        """
        Publish a state update to a topic.
        
        Args:
            topic: The MQTT topic to publish to
            state: The state value to publish
            
        Returns:
            bool: True if published successfully, False otherwise
        """
        if not self.is_connected():
            logger.error("Cannot publish state: not connected to MQTT broker")
            return False
            
        try:
            logger.debug(f"Publishing to topic {topic}: {state}")
            
            # Convert state to string if needed and publish
            state_str = str(state) if not isinstance(state, str) else state
            result = self.client.publish(topic, state_str, qos=1)
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
