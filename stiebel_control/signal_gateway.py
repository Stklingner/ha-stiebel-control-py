"""
Signal Gateway for the Stiebel Control package.

Serves as a bidirectional gateway between CAN signals and MQTT entities.
Routes data between the CAN bus and Home Assistant via MQTT.
"""
import logging
import time
from typing import Dict, Any, Optional, List, Tuple

from stiebel_control.ha_mqtt.entity_registration_service import EntityRegistrationService
from stiebel_control.ha_mqtt.mqtt_interface import MqttInterface
from stiebel_control.ha_mqtt.signal_entity_mapper import SignalEntityMapper
from stiebel_control.command_handler import CommandHandler
from stiebel_control.can.interface import CanInterface
from stiebel_control.config.config_models import EntityConfig
from stiebel_control.can.protocol import StiebelProtocol
from stiebel_control.heatpump.elster_table import get_elster_entry_by_index, get_elster_entry_by_english_name
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
                 protocol: Optional[StiebelProtocol] = None,
                 ignore_unsolicited_signals: bool = False):
        """
        Initialize the signal gateway.
        
        Args:
            entity_service: Service for registering entities with Home Assistant
            mqtt_interface: MQTT interface for publishing states
            can_interface: CAN interface for reading signal values
            signal_mapper: Maps between signals and entities
            entity_config: Entity configuration
            protocol: Optional StiebelProtocol instance for CAN member lookups
            ignore_unsolicited_signals: If True, only process signals that were explicitly polled or commanded
        """
        self.entity_service = entity_service
        self.mqtt_interface = mqtt_interface
        self.can_interface = can_interface
        self.signal_mapper = signal_mapper
        self.entity_config = entity_config
        self.protocol = protocol
        self.permissive_signal_handling = entity_config.permissive_signal_handling if entity_config else False
        self.signal_callbacks = {}
        
        # Track polled signal indices with timestamps
        # Format: {signal_index: last_poll_time}
        self.polled_signals = {}
        
        # How long to consider a signal as "polled" in seconds
        self.polled_signal_timeout = 300  # 5 minutes
        
        # Whether to ignore signals that weren't explicitly polled
        self.ignore_unsolicited_signals = ignore_unsolicited_signals
        
        # Initialize the command handler without a transformation service
        self.command_handler = CommandHandler(
            can_interface=can_interface,
            entity_config=entity_config.entities if hasattr(entity_config, 'entities') else {},
            get_elster_entry_by_english_name=get_elster_entry_by_english_name,
            transformation_service=None # TODO: Add transformation service
        )
        
        logger.info("Signal gateway initialized")
    
    def process_signal(self, signal_index: int, value: Any, can_id: int) -> Optional[str]:
        """
        Route a CAN signal to the appropriate MQTT entity (CAN → MQTT direction).
        
        This method receives signals from the CAN bus and publishes the corresponding
        state updates to Home Assistant via MQTT. It handles dynamic entity registration
        when new signals are encountered.
        
        Args:
            signal_index: Index of the signal received from CAN bus
            value: Value of the CAN signal
            can_id: CAN ID of the message source
        """
        logger.debug(f"New signal 0x{can_id:x}:{signal_index} = {value}")
        
        # Skip processing if not connected to MQTT
        if not self.mqtt_interface.is_connected():
            return
            

            
        # Get the CAN member name from ID
        member_name = self.get_can_member_name(can_id) or f"device_{can_id:x}"
        
        # Get signal name from index
        elster_entry = get_elster_entry_by_index(signal_index)
        if not elster_entry:
            logger.warning(f"Unknown signal index: {signal_index}, can't process")
            return None
            
        signal_name = elster_entry.english_name
        
        logger.info(f"Translated signal {member_name}:{signal_name} = {value}")

        # Check if this is an unsolicited signal that should be filtered
        is_unsolicited = False
        if self.ignore_unsolicited_signals:
            current_time = time.time()
            
            # Check if this signal is in the polled signals list
            if signal_index in self.polled_signals:
                last_poll_time = self.polled_signals[signal_index]
                
                # Check if the polled signal has expired
                if current_time - last_poll_time > self.polled_signal_timeout:
                    # Signal has expired, remove it from the list
                    del self.polled_signals[signal_index]
                    logger.debug(f"Signal {signal_index} poll expired after {self.polled_signal_timeout}s")
                    is_unsolicited = True
                else:
                    # Update timestamp and process
                    self.polled_signals[signal_index] = current_time
                    logger.debug(f"Processing previously polled signal {signal_index}")
            else:
                # Not a polled signal
                is_unsolicited = True
                logger.debug(f"Signal {signal_index} from CAN ID 0x{can_id:X} is unsolicited")
        
        # Skip entity registration and MQTT publishing for unsolicited signals
        if is_unsolicited:
            return None
            
        # Get existing entity or create one dynamically
        entity_id = self.signal_mapper.get_entity_by_signal(signal_name, member_name)
        
        if entity_id:
            logger.debug(f"Resolved {member_name}:{signal_name} = {value} -> {entity_id}")
        else:
            logger.debug(f"Resolved {member_name}:{signal_name} = {value} -> No entity registered")
        if not entity_id:
            # Register dynamically if no mapping exists
            entity_id = self.entity_service.register_dynamic_entity(
                signal_name=signal_name,
                value=value,
                member_name=member_name,
                permissive_signal_handling=self.permissive_signal_handling
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
        topic = self.entity_service.entities[entity_id].get("state_topic")
        success = self.mqtt_interface.publish_state(topic, transformed_value)
        
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
            # Get signal info for tracking purposes
            signal_info = self.command_handler.get_signal_info_for_entity(entity_id)
            if signal_info and 'signal_index' in signal_info:
                # Mark this signal as polled/commanded - we expect updates
                import time
                self.polled_signals[signal_info['signal_index']] = time.time()
                logger.debug(f"Marked signal {signal_info['signal_index']} as polled due to command")
                
            # Handle the command
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
        """Get the signal type from the elster table if available."""
        elster_entry = get_elster_entry_by_english_name(signal_name)
        if elster_entry:
            return elster_entry.ha_entity_type
        return None
        
    def _get_signal_unit(self, signal_name: str) -> str:
        """Get the signal unit from the elster table if available."""
        elster_entry = get_elster_entry_by_english_name(signal_name)
        if elster_entry:
            return elster_entry.unit_of_measurement
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

    def get_signal_index_by_name(self, signal_name: str) -> Optional[int]:
        """
        Get the signal index for a given signal name.
        
        Args:
            signal_name: English name of the signal
            
        Returns:
            int: Signal index if found, None otherwise
        """
        elster_entry = get_elster_entry_by_english_name(signal_name)
        if elster_entry:
            return elster_entry.index
        return None
        
    def update_system_status(self, status: str) -> None:
        """
        Update the system status sensor.
        
        Args:
            status: Current system status (online, offline, starting, error)
        """
        logger.info(f"System status: {status}")
        self.entity_service.update_entity_state("system_status", status)
        
    def update_entities_count(self, count: Optional[int] = None) -> None:
        """
        Update the entities count sensor.
        
        Args:
            count: Number of entities or None to count automatically
        """
        if count is None:
            # Count the number of registered entities
            count = len(self.entity_service.entities) + len(self.entity_service.dyn_registered_entities)
            
        logger.debug(f"Entities count: {count}")
        self.entity_service.update_entity_state("entities_count", count)
