"""
Handler for processing commands from Home Assistant to the heat pump.
"""
import logging
from typing import Dict, Any, Optional, Callable

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
        transformation_service=None
    ):
        """
        Initialize the command handler.
        
        Args:
            can_interface: Interface for sending commands to the CAN bus
            entity_config: Entity configuration dictionary
            transformation_service: Service for value transformations
        """
        self.can_interface = can_interface
        self.entity_config = entity_config
        self.get_elster_entry_by_english_name = get_elster_entry_by_english_name
        self.transformation_service = transformation_service
        
        # Keep track of pending commands to avoid echoes
        self.pending_commands = {}
        
        logger.info("Command handler initialized")
        
    def handle_command(self, entity_id: str, payload: str) -> None:
        """
        Process a command from Home Assistant.
        
        Args:
            entity_id: Entity ID that received the command
            payload: Command payload
        """

        if not entity_id or not payload:
            logger.warning(f"Invalid command: entity_id={entity_id}, payload={payload}")
            return
            
        # Skip special Home Assistant values that shouldn't be processed
        SKIP_VALUES = ['unknown', 'unavailable', 'null', 'none', '']
        if payload.lower() in SKIP_VALUES:
            logger.warning(f"Skipping special Home Assistant value '{payload}' for entity {entity_id}")
            return
            
        logger.info(f"Received command for entity {entity_id}: {payload}")
        
        # Find entity configuration
        entity_def = self.entity_config.get(entity_id)
        if not entity_def:
            logger.warning(f"Cannot process command: no configuration for entity {entity_id}")
            return
            
        # Extract signal info
        signal_name = entity_def.get('signal')
        signal_index = self._get_signal_index_by_name(signal_name)
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
