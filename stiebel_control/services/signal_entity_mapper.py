"""
Service for mapping between CAN signals and Home Assistant entities.
"""
import logging
from typing import Dict, Any, Optional, List, Set, Tuple
from stiebel_control.elster_table import get_elster_index_by_english_name

logger = logging.getLogger(__name__)

class SignalEntityMapper:
    """
    Handles mapping between CAN signals and Home Assistant entities.
    """
    
    def __init__(self):
        """Initialize the signal entity mapper."""
        # Entity mapping from signal to entity ID
        # Format: {(signal_name, can_id): entity_id}
        self.entity_map = {}
        
        # Reverse mapping from entity_id to signal details
        # Format: {entity_id: (signal_name, can_id)}
        self.entity_to_signal_map = {}
        
        # CAN member ID to name mapping
        self.can_id_to_name_map = {
            0x180: "PUMP",
            0x480: "MANAGER",
            0x301: "FE7X", 
            0x302: "FEK",
            0x500: "HEATING",  # Heating Module (0x500)
            0x602: "FE7",
            0x680: "ESPCLIENT"
        }
        
        logger.info("Signal entity mapper initialized")
        
    def build_entity_mapping(self, entity_config: Dict[str, Dict[str, Any]], can_interface) -> None:
        """
        Build mapping between CAN signals and Home Assistant entities.
        
        Args:
            entity_config: Entity configuration dictionary
            can_interface: CAN interface for resolving CAN IDs
        """
        logger.info("Building entity mapping from configuration")
        
        if not entity_config:
            logger.warning("No entity configuration found")
            return
            
        # Process each entity in the configuration
        for entity_id, entity_def in entity_config.items():
            signal_name = entity_def.get('signal')
            can_member = entity_def.get('can_member')
            can_member_ids = entity_def.get('can_member_ids', [])
            
            if not signal_name:
                logger.warning(f"Missing signal name for entity {entity_id}")
                continue
                
            # Process entities that define a single CAN member
            if can_member and not can_member_ids:
                can_id = can_interface.get_can_id_by_name(can_member)
                if can_id is not None:
                    self.add_mapping(signal_name, can_id, entity_id)
                    logger.debug(f"Mapped signal {signal_name} from {can_member} (ID: 0x{can_id:X}) to entity {entity_id}")
                else:
                    logger.warning(f"Unknown CAN member '{can_member}' for entity {entity_id}")
                    
            # Process entities that define multiple CAN members
            elif can_member_ids:
                for member_id in can_member_ids:
                    self.add_mapping(signal_name, member_id, entity_id)
                    logger.debug(f"Mapped signal {signal_name} from CAN ID 0x{member_id:X} to entity {entity_id}")
        
        logger.info(f"Built entity mapping with {len(self.entity_map)} signal-to-entity mappings")
        
    def add_mapping(self, signal_name: str, can_id: int, entity_id: str) -> None:
        """
        Add a mapping between a signal/CAN ID and an entity ID.
        
        Args:
            signal_name: Name of the signal
            can_id: CAN ID of the member
            entity_id: Entity ID in Home Assistant
        """
        self.entity_map[(signal_name, can_id)] = entity_id
        self.entity_to_signal_map[entity_id] = (signal_name, can_id)
        
    def get_entity_by_signal(self, signal_name: str, can_id: int) -> Optional[str]:
        """
        Get entity ID for a given signal and CAN ID.
        
        Args:
            signal_name: Name of the signal
            can_id: CAN ID of the member that sent the message
            
        Returns:
            Entity ID, or None if no mapping found
        """
        return self.entity_map.get((signal_name, can_id))
        
    def get_signal_by_entity(self, entity_id: str) -> Optional[Tuple[str, int]]:
        """
        Get signal name and CAN ID for a given entity ID.
        
        Args:
            entity_id: Entity ID in Home Assistant
            
        Returns:
            Tuple of (signal_name, can_id), or None if no mapping found
        """
        return self.entity_to_signal_map.get(entity_id)
        
    def create_dynamic_entity_id(self, signal_name: str, can_id: int) -> str:
        """
        Create a dynamic entity ID based on signal name and CAN ID.
        
        Args:
            signal_name: Name of the signal
            can_id: CAN ID of the member
            
        Returns:
            Entity ID string
        """
        # Get CAN member name from ID
        can_member_name = self.get_can_member_name(can_id) or f"can_0x{can_id:x}"
        
        # Create a unique entity ID based on CAN member and signal
        # Format: can_member_signal_name (lowercase, underscores)
        entity_id = f"{can_member_name.lower()}_{signal_name.lower()}"
        entity_id = entity_id.replace(' ', '_')
        
        return entity_id
        
    def create_friendly_name(self, signal_name: str, can_id: int) -> str:
        """
        Create a friendly name for an entity based on signal name and CAN ID.
        
        Args:
            signal_name: Name of the signal
            can_id: CAN ID of the member
            
        Returns:
            Friendly name string
        """
        # Get CAN member name from ID
        can_member_name = self.get_can_member_name(can_id) or f"CAN 0x{can_id:X}"
        
        # Create a friendly name with proper capitalization and spaces
        # Format: Can Member Signal Name (Title Case, spaces)
        friendly_name = f"{can_member_name.title()} {signal_name.title()}"
        friendly_name = friendly_name.replace('_', ' ')
        
        return friendly_name
        
    def get_can_member_name(self, can_id: int) -> Optional[str]:
        """
        Get the name of a CAN member from its ID.
        
        Args:
            can_id: CAN ID to look up
            
        Returns:
            Name of the CAN member, or None if not found
        """
        return self.can_id_to_name_map.get(can_id)
        
    def get_entity_signal_info(self, signal_name: str) -> Dict[str, Any]:
        """
        Get information about a signal from the Elster table.
        
        Args:
            signal_name: Name of the signal to look up
            
        Returns:
            Dictionary with signal information
        """
        ei = get_elster_index_by_english_name(signal_name)
        return {
            'name': ei.name,
            'type': ei.type,
            'index': ei.index
        }
