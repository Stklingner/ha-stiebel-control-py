"""
Signal Gateway for the Stiebel Control package.

Serves as a bidirectional gateway between CAN signals and MQTT entities.
Routes data between the CAN bus and Home Assistant via MQTT.
"""
import logging
from typing import Dict, Any, Optional

from stiebel_control.ha_mqtt.entity_registration_service import EntityRegistrationService
from stiebel_control.ha_mqtt.mqtt_interface import MqttInterface
from stiebel_control.ha_mqtt.signal_entity_mapper import SignalEntityMapper
from stiebel_control.ha_mqtt.command_handler import CommandHandler
from stiebel_control.can.interface import CanInterface
from stiebel_control.config.config_models import EntityConfig
from stiebel_control.can.protocol import StiebelProtocol
from stiebel_control.ha_mqtt.transformations import transform_value

logger = logging.getLogger(__name__)

class SignalGateway:
    """
    Acts as a bidirectional gateway between CAN signals and MQTT entities.
    
    Responsibilities:
    1. Routes CAN signals to appropriate MQTT entities
    2. Translates MQTT commands to CAN signals
    3. Handles dynamic entity registration based on observed signals
    """
    
    def __init__(self, 
                 entity_service: EntityRegistrationService,
                 mqtt_interface: MqttInterface,
                 can_interface: CanInterface,
                 signal_mapper: SignalEntityMapper,
                 entity_config: EntityConfig,
                 protocol: Optional[StiebelProtocol] = None):
        """
        Initialize the signal gateway.
        
        Args:
            entity_service: Service for registering entities with Home Assistant
            mqtt_interface: MQTT interface for publishing states
            can_interface: CAN interface for reading signal values
            signal_mapper: Maps between signals and entities
            entity_config: Entity configuration
            protocol: Optional StiebelProtocol instance for CAN member lookups
        """
        self.entity_service = entity_service
        self.mqtt_interface = mqtt_interface
        self.can_interface = can_interface
        self.signal_mapper = signal_mapper
        self.entity_config = entity_config
        self.protocol = protocol
        self.signal_callbacks = {}
        
        # Initialize the command handler without a transformation service
        self.command_handler = CommandHandler(
            can_interface=can_interface,
            entity_config=entity_config.entities if hasattr(entity_config, 'entities') else {}
        )
        
        logger.info("Signal gateway initialized")
    
    def process_signal(self, signal_name: str, value: Any, can_id: int) -> Optional[str]:
        """
        Route a CAN signal to the appropriate MQTT entity (CAN → MQTT direction).
        
        This method receives signals from the CAN bus and publishes the corresponding
        state updates to Home Assistant via MQTT. It handles dynamic entity registration
        when new signals are encountered.
        
        Args:
            signal_name: Name of the signal received from CAN bus
            value: Value of the CAN signal
            can_id: CAN ID of the message source
        """
        # Skip processing if not connected to MQTT
        if not self.mqtt_interface.is_connected():
            return
            
        # Get the CAN member name from ID for better readability
        member_name = self.get_can_member_name(can_id) or f"device_{can_id:x}"
        
        # Get existing entity or create one dynamically
        entity_id = self.signal_mapper.get_entity_by_signal(signal_name, member_name)
        
        if not entity_id:
            # Register dynamically if no mapping exists
            entity_id = self.entity_service.register_dynamic_entity(
                signal_name=signal_name,
                value=value,
                member_name=member_name,
                signal_type=self._get_signal_type(signal_name)
            )
            
            if not entity_id:
                logger.warning(f"Failed to process signal {signal_name} - could not register entity")
                return None
                
        # Skip if this is a pending command being processed
        if self.command_handler.is_pending_command(entity_id, value):
            logger.debug(f"Ignoring pending command echo for {entity_id}: {value}")
            return
        
        # Transform and publish the value
        transformed_value = self._transform_value(signal_name, entity_id, value)
        
        # Publish the update
        success = self.mqtt_interface.publish_state(entity_id, transformed_value)
        
        if success:
            # Execute any registered callbacks for this signal
            callback_key = (signal_name, member_name)
            if callback_key in self.signal_callbacks:
                for callback in self.signal_callbacks[callback_key]:
                    try:
                        callback(signal_name, transformed_value, entity_id)
                    except Exception as e:
                        logger.error(f"Error in signal callback for {signal_name}: {e}")
            
            logger.debug(f"Updated entity {entity_id} with value {transformed_value}")
            return entity_id
        else:
            logger.warning(f"Failed to update entity state for {entity_id}")
            return None
    
    def handle_command(self, entity_id: str, command: str) -> None:
        """
        Route a command from MQTT to the CAN bus (MQTT → CAN direction).
        
        This method receives commands from Home Assistant via MQTT and translates them
        to appropriate CAN messages that control the heat pump.
        
        Args:
            entity_id: ID of the entity that received the command
            command: Command string from Home Assistant
        """
        # Delegate directly to command handler
        try:
            self.command_handler.handle_command(entity_id, command)
        except Exception as e:
            logger.error(f"Error handling command for {entity_id}: {e}")
    
    def _transform_value(self, signal_name: str, entity_id: str, value: Any) -> Any:
        """Transform CAN signal values to the appropriate format for MQTT entities."""
        # Get entity type and other metadata
        entity_info = self.entity_service.entities.get(entity_id, {})
        entity_type = entity_info.get('type', 'sensor')
        
        # Get the signal type if possible
        signal_type = self._get_signal_type(signal_name)
        unit = self._get_signal_unit(signal_name)
        
        # Apply transformations based on the entity and signal type
        return transform_value(
            value=value,
            entity_id=entity_id,
            entity_type=entity_type,
            signal_name=signal_name,
            signal_type=signal_type,
            unit=unit
        )
        
    def _get_signal_type(self, signal_name: str) -> Optional[str]:
        """Get the signal type from the protocol if available."""
        if self.protocol:
            elster_entry = self.protocol.get_elster_entry_by_english_name(signal_name)
            if elster_entry:
                return elster_entry.get('ha_entity_type', 'sensor')
        return None
        
    def _get_signal_unit(self, signal_name: str) -> str:
        """Get the signal unit from the protocol if available."""
        if self.protocol:
            elster_entry = self.protocol.get_elster_entry_by_english_name(signal_name)
            if elster_entry:
                return elster_entry.get('unit_of_measurement', '')
        return ''
        
    def get_can_member_name(self, can_id: int) -> Optional[str]:
        """
        Get the name of a CAN member by its ID.
        
        Args:
            can_id: CAN ID to look up
            
        Returns:
            String name if found, None otherwise
        """
        # Use the protocol if available
        if self.protocol:
            for member in self.protocol.can_members:
                if member.can_id == can_id:
                    return member.name
        
        # If no match found
        return None
        
    def get_can_id_by_member_name(self, member_name: str) -> Optional[int]:
        """
        Get the CAN ID for a given member name.
        
        Args:
            member_name: CAN member name to look up
            
        Returns:
            CAN ID if found, None otherwise
        """
        # Use the protocol if available
        if self.protocol:
            for member in self.protocol.can_members:
                if member.name == member_name:
                    return member.can_id
        
        # If no match found
        return None
    
    def register_signal_callback(
        self, 
        signal_name: str, 
        member_name_or_id: Any, 
        callback: callable
    ) -> None:
        """
        Register a callback function for a specific signal.
        
        Args:
            signal_name: The signal name to watch
            member_name_or_id: The CAN member name or ID to watch
            callback: Function to call when the signal is processed
                     Takes (signal_name, value, entity_id) as arguments
        """
        # Convert ID to member name if needed
        if isinstance(member_name_or_id, int):
            member_name = self.get_can_member_name(member_name_or_id) or f"device_{member_name_or_id:x}"
        else:
            member_name = member_name_or_id
            
        key = (signal_name, member_name)
        if key not in self.signal_callbacks:
            self.signal_callbacks[key] = []
        
        self.signal_callbacks[key].append(callback)
        logger.debug(f"Registered callback for signal {signal_name}@{member_name}")
