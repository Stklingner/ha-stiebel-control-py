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
        transformation_service
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
            
        logger.info(f"Received command for entity {entity_id}: {payload}")
        
        # Find entity configuration
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
        if transform_config:
            value = self.transformation_service.apply_inverse_transformation(
                payload, transform_config
            )
        else:
            value = payload
            
        # Record pending command to avoid echo
        self.pending_commands[entity_id] = value
        
        # Send command to the CAN bus
        self.can_interface.set_value(can_id, signal_name, value)
        logger.info(f"Sent command to CAN bus: signal={signal_name}, value={value}, can_id=0x{can_id:X}")
        
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
