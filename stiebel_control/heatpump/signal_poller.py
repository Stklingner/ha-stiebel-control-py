"""
Signal Poller for Stiebel Eltron Heat Pump Control.

This module handles periodic polling of signals from the heat pump
with configurable priority levels and intervals.
"""

import time
import yaml
import logging
import os
from typing import Dict, List, Tuple, Optional, Any
from pathlib import Path

from stiebel_control.heatpump.elster_table import get_elster_entry_by_english_name

logger = logging.getLogger(__name__)

class SignalPoller:
    """
    Handles periodic polling of signals with different priority levels.
    
    Signals are grouped by priority (high, medium, low) with configurable
    polling intervals for each group.
    """
    
    def __init__(self, can_interface, config_path: Optional[str] = None):
        """
        Initialize the signal poller.
        
        Args:
            can_interface: Interface for sending read requests to the CAN bus
            config_path: Optional path to the pollable signals config file
        """
        self.can_interface = can_interface
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), 'pollable_signals.yaml'
        )
        
        # Default polling intervals (in seconds)
        self.polling_intervals = {
            'high': 60,    # Every minute
            'medium': 300, # Every 5 minutes
            'low': 900     # Every 15 minutes
        }
        
        # Polling tasks by priority
        # Structure: {priority: [(signal_index, member_index, last_poll_time), ...]}
        self.polling_tasks: Dict[str, List[Tuple[int, int, float]]] = {
            'high': [],
            'medium': [],
            'low': []
        }
        
        # Load configuration
        self._load_config()
        
        logger.info(f"Signal poller initialized with {len(self.polling_tasks['high'])} high, "
                   f"{len(self.polling_tasks['medium'])} medium, "
                   f"{len(self.polling_tasks['low'])} low priority tasks")
    
    def _load_config(self) -> None:
        """Load polling configuration from YAML file."""
        try:
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            # Load custom polling intervals if available
            if 'polling_intervals' in config:
                for priority, interval in config['polling_intervals'].items():
                    if priority in self.polling_intervals:
                        self.polling_intervals[priority] = interval
            
            # Load polling tasks
            if 'priority_groups' not in config:
                logger.warning("No priority groups found in poller configuration")
                return
                
            for priority, signals in config['priority_groups'].items():
                if priority not in self.polling_tasks:
                    logger.warning(f"Unknown priority level '{priority}' in config")
                    continue
                    
                for signal_def in signals:
                    signal_name = signal_def.get('signal')
                    can_member = signal_def.get('can_member')
                    
                    if not signal_name or not can_member:
                        logger.warning("Missing signal name or CAN member in poller config")
                        continue
                    
                    # Translate signal name to index
                    elster_entry = get_elster_entry_by_english_name(signal_name)
                    if not elster_entry:
                        logger.warning(f"Unknown signal name: {signal_name}")
                        continue
                        
                    signal_index = elster_entry.index
                    
                    # Find the CAN member index
                    member_index = self._get_member_index(can_member)
                    if member_index is None:
                        logger.warning(f"Unknown CAN member: {can_member}")
                        continue
                    
                    # Add to polling tasks with initial last_poll_time of 0
                    self.polling_tasks[priority].append((signal_index, member_index, 0))
                    logger.debug(f"Added {signal_name} ({signal_index}) from {can_member} to {priority} priority group")
                
        except Exception as e:
            logger.error(f"Error loading polling configuration: {e}")
    
    def _get_member_index(self, member_name: str) -> Optional[int]:
        """
        Get the index of a CAN member by name.
        
        Args:
            member_name: Name of the CAN member
            
        Returns:
            int: Member index if found, None otherwise
        """
        try:
            # Get all CAN members from the CAN interface
            members = self.can_interface.can_members
            
            for idx, member in enumerate(members):
                if member.name == member_name:
                    return idx
        except Exception as e:
            logger.error(f"Error getting member index: {e}")
        
        return None
    
    def update(self) -> None:
        """
        Check for signals that need polling and issue read requests.
        
        This should be called regularly (e.g., every second) from the main loop.
        """
        current_time = time.time()
        
        # Process each priority group
        for priority, tasks in self.polling_tasks.items():
            interval = self.polling_intervals[priority]
            
            for i, (signal_index, member_index, last_poll_time) in enumerate(tasks):
                # Check if it's time to poll this signal
                if current_time - last_poll_time >= interval:
                    # Send read request
                    success = self.can_interface.read_signal(member_index, signal_index)
                    
                    # Update last poll time regardless of success
                    # (to avoid flooding with requests if there's an issue)
                    self.polling_tasks[priority][i] = (signal_index, member_index, current_time)
                    
                    if success:
                        logger.debug(f"Polled signal index {signal_index} from member index {member_index}")
                    else:
                        logger.warning(f"Failed to poll signal index {signal_index} from member index {member_index}")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the polling tasks.
        
        Returns:
            Dict with statistics about polling tasks
        """
        current_time = time.time()
        stats = {
            'total_signals': sum(len(tasks) for tasks in self.polling_tasks.values()),
            'priorities': {}
        }
        
        for priority, tasks in self.polling_tasks.items():
            due_count = sum(1 for _, _, last_poll_time in tasks 
                          if current_time - last_poll_time >= self.polling_intervals[priority])
            
            stats['priorities'][priority] = {
                'count': len(tasks),
                'interval': self.polling_intervals[priority],
                'due_for_polling': due_count
            }
            
        return stats
