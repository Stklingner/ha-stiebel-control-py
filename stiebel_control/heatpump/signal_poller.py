"""
Signal Poller for Stiebel Eltron Heat Pump Control.

This module handles periodic polling of signals from the heat pump
with configurable priority levels and intervals.
"""

import time
import yaml
import random
import logging
import os
from typing import Dict, List, Tuple, Optional, Any, Callable
from pathlib import Path

from stiebel_control.heatpump.elster_table import get_elster_entry_by_english_name

logger = logging.getLogger(__name__)

class SignalPoller:
    """
    Handles periodic polling of signals with different priority levels.
    
    Signals are grouped by priority (high, medium, low) with configurable
    polling intervals for each group.
    """
    
    def __init__(self, can_interface, config_path: Optional[str] = None, poll_jitter_fraction: float = 0.1, poll_jitter_seconds: Optional[float] = None):
        """
        Initialize the signal poller.
        
        Args:
            can_interface: Interface for sending read requests to the CAN bus
            config_path: Optional path to the pollable signals config file
            poll_jitter_fraction: Fraction of the interval to use as jitter (default 0.1 = 10%)
            poll_jitter_seconds: If set, use this many seconds as jitter instead of fraction
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
        # Structure: {priority: [(signal_index, member_index, last_poll_time, last_response_time, response_count, poll_count), ...]}
        self.polling_tasks: Dict[str, List[Tuple[int, int, float, float, int, int]]] = {
            'high': [],
            'medium': [],
            'low': []
        }
        
        # Track pending poll requests to match with responses
        # Structure: {(member_index, signal_index): (request_time, callback)}
        self.pending_polls: Dict[Tuple[int, int], Tuple[float, Callable]] = {}
        
        # Jitter configuration
        self.poll_jitter_fraction = poll_jitter_fraction
        self.poll_jitter_seconds = poll_jitter_seconds
        
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
                    
                    # Add to polling tasks with initial values
                    # (signal_index, member_index, last_poll_time, last_response_time, response_count, poll_count)
                    self.polling_tasks[priority].append((signal_index, member_index, 0, 0, 0, 0))
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
            # Calculate jitter for this interval
            if self.poll_jitter_seconds is not None:
                jitter = self.poll_jitter_seconds
            else:
                jitter = interval * self.poll_jitter_fraction
            
            for i, (signal_index, member_index, last_poll_time, last_response_time, response_count, poll_count) in enumerate(tasks):
                # Add jitter to each poll schedule
                next_poll_time = last_poll_time + interval + random.uniform(-jitter, jitter)
                # Check if it's time to poll this signal
                if current_time >= next_poll_time:
                    # First, clean up any previous pending poll for this signal
                    poll_key = (member_index, signal_index)
                    if poll_key in self.pending_polls:
                        prev_time, prev_callback = self.pending_polls[poll_key]
                        member = self.can_interface.can_members[member_index]
                        self.can_interface.remove_signal_callback(signal_index, member.can_id, prev_callback)
                        del self.pending_polls[poll_key]
                    
                    # Create the callback for this signal
                    response_callback = self._create_response_callback(member_index, signal_index)
                    
                    # Register for all responses from this member
                    member = self.can_interface.can_members[member_index]
                    self.can_interface.add_signal_callback(signal_index, member.can_id, response_callback)
                    
                    # Send read request
                    success = self.can_interface.read_signal(member_index, signal_index)
                    
                    # Update poll count and last poll time regardless of success
                    # (to avoid flooding with requests if there's an issue)
                    new_poll_count = poll_count + 1 if success else poll_count
                    
                    # Update task with new poll time and count
                    self.polling_tasks[priority][i] = (
                        signal_index, 
                        member_index, 
                        current_time,  # last_poll_time 
                        last_response_time, 
                        response_count, 
                        new_poll_count
                    )
                    
                    # Track this poll in pending polls
                    if success:
                        self.pending_polls[(member_index, signal_index)] = (current_time, response_callback)
                        logger.debug(f"Polled signal index {signal_index} from member index {member_index}")
                    else:
                        logger.warning(f"Failed to poll signal index {signal_index} from member index {member_index}")
    
    def _create_response_callback(self, member_index: int, signal_index: int) -> Callable[[int, Any, int], None]:
        """
        Create a callback function for handling a specific signal response.
        
        Args:
            member_index: Index of the CAN member
            signal_index: Index of the signal
            
        Returns:
            Callback function that handles the response
        """
        def callback(received_signal_index: int, value: Any, can_id: int) -> None:
            """
            Handle response from signal poll.
            
            Args:
                received_signal_index: Index of the signal received
                value: The value received from the signal
                can_id: CAN ID of the sender
            """
            # Only process if this is the signal we're waiting for
            if received_signal_index != signal_index:
                return
                
            # Get member_index from CAN ID to verify it matches
            can_member_idx = None
            for idx, member in enumerate(self.can_interface.can_members):
                if member.can_id == can_id:
                    can_member_idx = idx
                    break
                    
            # Only proceed if member matches
            if can_member_idx != member_index:
                return
                
            current_time = time.time()
            logger.info(f"Received response for signal {signal_index} from member {member.name}: {value}")
            
            # Update response count and time in polling tasks
            for priority, tasks in self.polling_tasks.items():
                for i, (s_idx, m_idx, last_poll, last_resp, resp_count, poll_count) in enumerate(tasks):
                    if s_idx == signal_index and m_idx == member_index:
                        # Update task with response information
                        self.polling_tasks[priority][i] = (
                            s_idx,
                            m_idx,
                            last_poll,
                            current_time,  # update last_response_time
                            resp_count + 1,  # increment response count
                            poll_count
                        )
                        break
            
            # Remove from pending polls and clean up the callback
            poll_key = (member_index, signal_index)
            if poll_key in self.pending_polls:
                _, callback_ref = self.pending_polls[poll_key]
                member = self.can_interface.can_members[member_index]
                self.can_interface.remove_signal_callback(signal_index, member.can_id, callback_ref)
                del self.pending_polls[poll_key]
                
        return callback
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the polling tasks.
        
        Returns:
            Dict with simplified statistics focusing on key metrics
        """
        current_time = time.time()
        
        # Clean up stale pending polls (older than 60 seconds)
        stale_keys = []
        for poll_key, (req_time, callback) in self.pending_polls.items():
            if current_time - req_time > 60:  # 60 seconds timeout
                member_idx, signal_idx = poll_key
                member = self.can_interface.can_members[member_idx]
                self.can_interface.remove_signal_callback(signal_idx, member.can_id, callback)
                stale_keys.append(poll_key)
                
        for key in stale_keys:
            del self.pending_polls[key]
        
        # Calculate polled vs responsive entities
        polled_entities = set()
        responsive_entities = set()
        non_responsive_entities = []
        
        # Collect stats across all priorities
        for priority, tasks in self.polling_tasks.items():
            for signal_idx, member_idx, _, last_response, response_count, poll_count in tasks:
                if poll_count > 0:
                    # This entity has been polled
                    polled_entities.add((member_idx, signal_idx))
                    
                    if response_count > 0:
                        # This entity has responded at least once
                        responsive_entities.add((member_idx, signal_idx))
                    else:
                        # This entity has never responded
                        try:
                            member_name = self.can_interface.can_members[member_idx].name
                            non_responsive_entities.append(f"{member_name}:{signal_idx}")
                        except IndexError:
                            # Fall back to index if member not found
                            non_responsive_entities.append(f"Member({member_idx}):{signal_idx}")
        
        # Create simplified stats
        stats = {
            'total_polled_entities': len(polled_entities),
            'total_responsive_entities': len(responsive_entities),
            'non_responsive_count': len(non_responsive_entities),
            'non_responsive_entities_list': ', '.join(non_responsive_entities) if non_responsive_entities else "All entities responding"
        }
        
        return stats
