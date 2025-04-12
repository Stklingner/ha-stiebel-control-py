"""
Service for mapping between CAN signals and Home Assistant entities.
"""
import logging
from typing import Dict, Any, Optional, List, Set, Tuple
from stiebel_control.heatpump.elster_table import get_elster_entry_by_english_name

logger = logging.getLogger(__name__)

class SignalEntityMapper:
    """
    Handles mapping between CAN signals and Home Assistant entities.
    """
    
    def __init__(self):
        """Initialize the signal entity mapper."""
        # Entity mapping from signal to entity ID
        # Format: {(signal_name, member_name): entity_id}
        self.entity_map = {}
        
        # Reverse mapping from entity_id to signal details
        # Format: {entity_id: (signal_name, member_name)}
        self.entity_to_signal_map = {}
        
        logger.info("Signal entity mapper initialized")
        
    def build_entity_mapping(self, entity_config: Dict[str, Dict[str, Any]]) -> None:
        """
        Build mapping between CAN signals and Home Assistant entities.
        
        Args:
            entity_config: Entity configuration dictionary
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
                # Use the member name directly
                self.add_mapping(signal_name, can_member, entity_id)
                logger.debug(f"Mapped signal {signal_name} from {can_member} to entity {entity_id}")
                    
            # Process entities that define multiple CAN members
            elif can_member_ids:
                for member_id in can_member_ids:
                    # Convert all member_ids to strings for consistent handling
                    member_name = str(member_id)
                    self.add_mapping(signal_name, member_name, entity_id)
                    logger.debug(f"Mapped signal {signal_name} from member {member_name} to entity {entity_id}")
        
        logger.info(f"Built entity mapping with {len(self.entity_map)} signal-to-entity mappings")
        
    def add_mapping(self, signal_name: str, member_name: str, entity_id: str) -> None:
        """
        Add a mapping between a signal/member name and an entity ID.
        
        Args:
            signal_name: Name of the signal
            member_name: CAN member name
            entity_id: Entity ID in Home Assistant
        """
        self.entity_map[(signal_name, member_name)] = entity_id
        self.entity_to_signal_map[entity_id] = (signal_name, member_name)
        
    def get_entity_by_signal(self, signal_name: str, member_name: str) -> Optional[str]:
        """
        Get entity ID for a given signal and member name.
        
        Args:
            signal_name: Name of the signal
            member_name: Name of the CAN member that sent the message
            
        Returns:
            Entity ID, or None if no mapping found
        """
        return self.entity_map.get((signal_name, member_name))
        
    def get_entity_by_signal_with_id(self, signal_name: str, can_id: int) -> Optional[str]:
        """
        Get entity ID for a given signal and CAN ID (legacy support).
        
        Args:
            signal_name: Name of the signal
            can_id: CAN ID of the member that sent the message
            
        Returns:
            Entity ID, or None if no mapping found
        """
        # Convert ID to member name first
        member_name = self.get_can_member_name_by_id(can_id)
        if member_name:
            return self.get_entity_by_signal(signal_name, member_name)
        return None
        
    def get_signal_by_entity(self, entity_id: str) -> Optional[Tuple[str, int]]:
        """
        Get signal name and CAN ID for a given entity ID.
        
        Args:
            entity_id: Entity ID in Home Assistant
            
        Returns:
            Tuple of (signal_name, member_name), or None if no mapping found
        """
        return self.entity_to_signal_map.get(entity_id)
        
    def create_dynamic_entity_id(self, signal_name: str, member_name: str) -> str:
        """
        Create a dynamic entity ID for a given signal and member name.
        
        Args:
            signal_name: Name of the signal
            member_name: Name of the CAN member
            
        Returns:
            Generated entity ID string
        """
        # Clean up signal name for use in entity ID
        signal_id = signal_name.lower().replace(' ', '_').replace('.', '_')
        
        # Create entity ID
        entity_id = f"{signal_id}_{member_name.lower()}"
        
        return entity_id
        
    def create_friendly_name(self, signal_name: str, member_name: str) -> str:
        """
        Create a friendly display name for a signal and member name.
        
        Args:
            signal_name: Name of the signal
            member_name: Name of the CAN member
            
        Returns:
            Human-readable display name
        """
        # Format friendly name
        friendly_name = f"{signal_name.replace('_', ' ').title()} ({member_name})"
        
        return friendly_name
        

        
    def get_entity_signal_info(self, signal_name: str) -> Dict[str, Any]:
        """
        Get information about a signal from the Elster table.
        
        Args:
            signal_name: Name of the signal to look up
            
        Returns:
            Dictionary with signal information
        """
        ei = get_elster_entry_by_english_name(signal_name)
        return {
            'name': ei.name,
            'type': ei.type,
            'index': ei.index
        }
