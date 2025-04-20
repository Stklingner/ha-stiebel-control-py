"""
Handler for processing commands from Home Assistant to the heat pump.
"""
import logging
import datetime
from typing import Dict, Any, Optional, Callable, List, Union

logger = logging.getLogger(__name__)

class CommandHandler:
    """
    Handles commands from Home Assistant to the heat pump.
    """
    
    def __init__(
        self, 
        can_interface, 
        entity_config: Dict[str, Dict[str, Any]],
        get_elster_entry_by_english_name: Callable,
        transformation_service=None,
        controls_config: Dict[str, Dict[str, Any]] = None
    ):
        """
        Initialize the command handler.
        
        Args:
            can_interface: Interface for sending commands to the CAN bus
            entity_config: Entity configuration dictionary (legacy)
            get_elster_entry_by_english_name: Function to lookup signal info
            transformation_service: Service for value transformations
            controls_config: Controls configuration dictionary (new structure)
        """
        self.can_interface = can_interface
        self.entity_config = entity_config or {}
        self.controls_config = controls_config or {}
        self.get_elster_entry_by_english_name = get_elster_entry_by_english_name
        self.transformation_service = transformation_service
        
        # Keep track of pending commands to avoid echoes
        self.pending_commands = {}
        
        logger.info("Command handler initialized with %d entities and %d controls",
                  len(self.entity_config), len(self.controls_config))
        
    def handle_command(self, entity_id: str, payload: str) -> None:
        """
        Process a command from Home Assistant.
        
        Args:
            entity_id: Entity ID that received the command
            payload: Command payload
        """
        if not entity_id:
            logger.warning(f"Invalid command: missing entity_id")
            return
        
        if not payload and not self._is_button_entity(entity_id):
            logger.warning(f"Invalid command: empty payload for non-button entity {entity_id}")
            return
            
        # Skip special Home Assistant values that shouldn't be processed
        SKIP_VALUES = ['unknown', 'unavailable', 'null', 'none']
        if payload.lower() in SKIP_VALUES:
            logger.warning(f"Skipping special Home Assistant value '{payload}' for entity {entity_id}")
            return
            
        logger.info(f"Received command for entity {entity_id}: {payload}")
        
        # Check if this is a control entity (new structure)
        control_def = self.controls_config.get(entity_id)
        if control_def:
            return self._handle_control_command(entity_id, control_def, payload)
            
        # Legacy entity handling (backward compatibility)
        entity_def = self.entity_config.get(entity_id)
        if not entity_def:
            logger.warning(f"Cannot process command: no configuration for entity {entity_id}")
            return
            
        # Extract signal info
        signal_name = entity_def.get('signal')
        can_member = entity_def.get('can_member')
        can_member_ids = entity_def.get('can_member_ids', [])
        
        if not signal_name:
            logger.warning(f"Cannot process command: no signal name for entity {entity_id}")
            return
            
        # Get CAN ID for the command
        can_id = self._resolve_can_id(can_member, can_member_ids)
        if can_id is None:
            logger.warning(f"Cannot process command: no valid CAN ID for entity {entity_id}")
            return
            
        # Transform command value if needed
        transform_config = entity_def.get('transform', {})
        if transform_config and self.transformation_service:
            value = self.transformation_service.apply_inverse_transformation(
                payload, transform_config
            )
        else:
            value = payload
            
        # Record pending command to avoid echo
        self.pending_commands[entity_id] = value
        
        # Convert signal name to index
        elster_entry = self.get_elster_entry_by_english_name(signal_name)
        if not elster_entry:
            logger.error(f"Cannot process command: unknown signal {signal_name}")
            return
            
        signal_index = elster_entry.index
        
        # Send command to the CAN bus
        self.can_interface.set_value(can_id, signal_index, value)
        logger.info(f"Sent command to CAN bus: signal={signal_name} (index {signal_index}), value={value}, can_id=0x{can_id:X}")
    
    def _handle_control_command(self, entity_id: str, control_def: Dict[str, Any], payload: str) -> None:
        """
        Process a command for a control entity.
        
        Args:
            entity_id: Entity ID that received the command
            control_def: Control definition dictionary
            payload: Command payload
        """
        control_type = control_def.get('type')
        can_member = control_def.get('can_member')
        
        # Handle different control types
        if control_type == 'button':
            return self._handle_button_command(entity_id, control_def, can_member)
        elif control_type == 'number':
            return self._handle_number_command(entity_id, control_def, can_member, payload)
        elif control_type == 'select':
            return self._handle_select_command(entity_id, control_def, can_member, payload)
        else:
            logger.warning(f"Unknown control type '{control_type}' for entity {entity_id}")
            
    def _handle_button_command(self, entity_id: str, control_def: Dict[str, Any], can_member: str) -> None:
        """
        Handle button press actions.
        
        Args:
            entity_id: Entity ID of the button
            control_def: Button control definition
            can_member: CAN member name
        """
        action_type = control_def.get('action_type')
        
        if action_type == 'system_time':
            # Update heat pump time from system time
            now = datetime.datetime.now()
            
            # Get the CAN ID
            can_id = self._resolve_can_id(can_member, [])
            if not can_id:
                logger.error(f"Cannot find CAN ID for member {can_member}")
                return
                
            # Set the time values
            hour_entry = self.get_elster_entry_by_english_name('TIME_HOUR')
            minute_entry = self.get_elster_entry_by_english_name('TIME_MINUTE')
            
            if not hour_entry or not minute_entry:
                logger.error("Cannot find TIME signals in the Elster table")
                return
                
            logger.info(f"Updating heat pump time to {now.hour}:{now.minute}")
            
            # Set hour and minute
            self.can_interface.set_value(can_id, hour_entry.index, now.hour)
            self.can_interface.set_value(can_id, minute_entry.index, now.minute)
            
            # Optional: set day, month, year if those signals exist
            day_entry = self.get_elster_entry_by_english_name('TIME_DAY')
            month_entry = self.get_elster_entry_by_english_name('TIME_MONTH')
            year_entry = self.get_elster_entry_by_english_name('TIME_YEAR')
            
            if day_entry:
                self.can_interface.set_value(can_id, day_entry.index, now.day)
            if month_entry:
                self.can_interface.set_value(can_id, month_entry.index, now.month)
            if year_entry:
                self.can_interface.set_value(can_id, year_entry.index, now.year)
                
            logger.info(f"Heat pump time updated successfully")
            
        elif action_type == 'reset_error':
            # Implement reset error logic here
            logger.info(f"Reset error action requested for {entity_id}")
            # This would need to be implemented based on the specific heat pump behavior
        else:
            logger.warning(f"Unknown button action type: {action_type}")
    
    def _handle_number_command(self, entity_id: str, control_def: Dict[str, Any], 
                             can_member: str, payload: str) -> None:
        """
        Handle number control commands.
        
        Args:
            entity_id: Entity ID of the number control
            control_def: Number control definition
            can_member: CAN member name
            payload: Command payload (numeric value)
        """
        write_signal = control_def.get('write_signal')
        if not write_signal:
            logger.error(f"Missing write_signal in control definition for {entity_id}")
            return
            
        # Get the CAN ID
        can_id = self._resolve_can_id(can_member, [])
        if not can_id:
            logger.error(f"Cannot find CAN ID for member {can_member}")
            return
            
        # Convert signal name to index
        elster_entry = self.get_elster_entry_by_english_name(write_signal)
        if not elster_entry:
            logger.error(f"Cannot find signal {write_signal} in the Elster table")
            return
            
        # Parse the numeric value
        try:
            value = float(payload)
            
            # Apply any min/max limits
            min_value = control_def.get('min')
            max_value = control_def.get('max')
            
            if min_value is not None and value < float(min_value):
                logger.warning(f"Value {value} below minimum {min_value}, adjusting")
                value = float(min_value)
                
            if max_value is not None and value > float(max_value):
                logger.warning(f"Value {value} above maximum {max_value}, adjusting")
                value = float(max_value)
                
            # Record pending command to avoid echo
            self.pending_commands[entity_id] = value
            
            # Send command to the CAN bus
            self.can_interface.set_value(can_id, elster_entry.index, value)
            logger.info(f"Sent temperature command: signal={write_signal}, value={value}, can_id=0x{can_id:X}")
            
        except ValueError:
            logger.error(f"Invalid numeric value: {payload}")
    
    def _handle_select_command(self, entity_id: str, control_def: Dict[str, Any], 
                             can_member: str, payload: str) -> None:
        """
        Handle select control commands.
        
        Args:
            entity_id: Entity ID of the select control
            control_def: Select control definition
            can_member: CAN member name
            payload: Command payload (selected option)
        """
        write_signal = control_def.get('write_signal')
        if not write_signal:
            logger.error(f"Missing write_signal in control definition for {entity_id}")
            return
            
        # Get the CAN ID
        can_id = self._resolve_can_id(can_member, [])
        if not can_id:
            logger.error(f"Cannot find CAN ID for member {can_member}")
            return
            
        # Convert signal name to index
        elster_entry = self.get_elster_entry_by_english_name(write_signal)
        if not elster_entry:
            logger.error(f"Cannot find signal {write_signal} in the Elster table")
            return
            
        # Map option to value if needed
        options = control_def.get('options', [])
        if options:
            try:
                # Value is the index in the options list (0-based)
                value = options.index(payload)
                
                # Record pending command to avoid echo
                self.pending_commands[entity_id] = payload
                
                # Send command to the CAN bus
                self.can_interface.set_value(can_id, elster_entry.index, value)
                logger.info(f"Sent select command: signal={write_signal}, option={payload}, value={value}, can_id=0x{can_id:X}")
                
            except ValueError:
                logger.error(f"Invalid option '{payload}'. Valid options: {options}")
        else:
            logger.error(f"No options defined for select control {entity_id}")
    
    def _is_button_entity(self, entity_id: str) -> bool:
        """
        Check if an entity is a button type entity.
        
        Args:
            entity_id: Entity ID to check
            
        Returns:
            True if the entity is a button, False otherwise
        """
        # Check in controls config
        control_def = self.controls_config.get(entity_id)
        if control_def and control_def.get('type') == 'button':
            return True
            
        # Check in entity config
        entity_def = self.entity_config.get(entity_id)
        if entity_def and entity_def.get('type') == 'button':
            return True
            
        return False
        
    def _resolve_can_id(self, can_member: Optional[str], can_member_ids: list) -> Optional[int]:
        """
        Resolve CAN ID from member name or explicit IDs.
        
        Args:
            can_member: Name of the CAN member
            can_member_ids: List of explicit CAN member IDs
            
        Returns:
            Resolved CAN ID or None if not found
        """
        can_id = None
        
        if can_member:
            can_id = self.can_interface.get_can_id_by_name(can_member)
        elif can_member_ids and len(can_member_ids) > 0:
            # Use first ID in the list
            can_id = can_member_ids[0]
            
        return can_id
    
    def _get_signal_index_by_name(self, signal_name: str) -> Optional[int]:
        """Convert a signal name to its corresponding index."""
        elster_entry = self.get_elster_entry_by_english_name(signal_name)
        if elster_entry:
            return elster_entry.index
        return None
        
    def get_signal_info_for_entity(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get signal information for a given entity ID.
        
        Used by the SignalGateway to track which signals should be monitored.
        
        Args:
            entity_id: Entity ID to lookup
            
        Returns:
            Dict with signal information or None if not found
        """
        # Find entity configuration
        entity_def = self.entity_config.get(entity_id)
        if not entity_def:
            return None
            
        # Extract signal info
        signal_name = entity_def.get('signal')
        if not signal_name:
            return None
            
        signal_index = self._get_signal_index_by_name(signal_name)
        if signal_index is None:
            return None
            
        can_member = entity_def.get('can_member')
        can_member_ids = entity_def.get('can_member_ids', [])
        
        # Get CAN ID for the command
        can_id = self._resolve_can_id(can_member, can_member_ids)
        
        return {
            'signal_name': signal_name,
            'signal_index': signal_index,
            'can_member': can_member,
            'can_id': can_id
        }

    def is_pending_command(self, entity_id: str, value: Any) -> bool:
        """
        Check if a value update is from a pending command.
        
        Args:
            entity_id: Entity ID receiving the update
            value: Updated value
            
        Returns:
            True if this is a pending command echo, False otherwise
        """
        if entity_id in self.pending_commands:
            command_value = self.pending_commands[entity_id]
            if str(value) == str(command_value):
                logger.debug(f"Detected echo of command for entity {entity_id}: {value}")
                del self.pending_commands[entity_id]
                return True
                
        return False
