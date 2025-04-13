#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Unit tests for the PriorityPoller module.
"""

import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
import yaml
import time

# Import the SignalPoller class
from stiebel_control.heatpump.signal_poller import SignalPoller

class TestSignalPoller(unittest.TestCase):
    """Test cases for the PriorityPoller class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create a mock CAN interface
        self.mock_can_interface = MagicMock()
        
        # Set up test CAN members
        self.mock_can_members = [
            MagicMock(name="PUMP"),
            MagicMock(name="MANAGER")
        ]
        self.mock_can_interface.can_members = self.mock_can_members
        
        # Create a temporary config file
        self.temp_config = tempfile.NamedTemporaryFile(delete=False, suffix=".yaml")
        
        # Basic test configuration
        self.test_config = {
            "polling_intervals": {
                "high": 10,
                "medium": 30,
                "low": 60
            },
            "priority_groups": {
                "high": [
                    {"signal": "OUTSIDE_TEMP", "can_member": "PUMP"}
                ],
                "medium": [
                    {"signal": "FLOW_INTERNAL_TEMP", "can_member": "PUMP"}
                ],
                "low": [
                    {"signal": "SOFTWARE_NUMBER", "can_member": "PUMP"}
                ]
            }
        }
        
        # Write the test configuration to the temporary file
        with open(self.temp_config.name, 'w') as f:
            yaml.dump(self.test_config, f)
    
    def tearDown(self):
        """Tear down test fixtures."""
        # Delete the temporary config file
        if hasattr(self, 'temp_config') and os.path.exists(self.temp_config.name):
            os.unlink(self.temp_config.name)
    
    @patch('stiebel_control.heatpump.signal_poller.get_elster_entry_by_english_name')
    def test_load_config(self, mock_get_elster):
        """Test loading configuration from a YAML file."""
        # Mock the elster entry lookup
        mock_outside_temp = MagicMock(index=100)
        mock_flow_temp = MagicMock(index=101)
        mock_software = MagicMock(index=102)
        
        # Setup return values for different signal names
        mock_get_elster.side_effect = lambda signal_name: {
            "OUTSIDE_TEMP": mock_outside_temp,
            "FLOW_INTERNAL_TEMP": mock_flow_temp,
            "SOFTWARE_NUMBER": mock_software
        }.get(signal_name)
        
        # Create the poller with our test config
        poller = SignalPoller(self.mock_can_interface, self.temp_config.name)
        
        # Check if polling intervals were loaded correctly
        self.assertEqual(poller.polling_intervals["high"], 10)
        self.assertEqual(poller.polling_intervals["medium"], 30)
        self.assertEqual(poller.polling_intervals["low"], 60)
        
        # Check if polling tasks were loaded correctly
        self.assertEqual(len(poller.polling_tasks["high"]), 1)
        self.assertEqual(len(poller.polling_tasks["medium"]), 1)
        self.assertEqual(len(poller.polling_tasks["low"]), 1)
        
        # Verify the high priority task
        signal_index, member_index, _ = poller.polling_tasks["high"][0]
        self.assertEqual(signal_index, 100)  # OUTSIDE_TEMP
        self.assertEqual(member_index, 0)    # PUMP is index 0
    
    @patch('stiebel_control.heatpump.signal_poller.get_elster_entry_by_english_name')
    def test_update(self, mock_get_elster):
        """Test the update method."""
        # Mock the elster entry lookup
        mock_outside_temp = MagicMock(index=100)
        
        # Setup return values
        mock_get_elster.return_value = mock_outside_temp
        
        # Create the poller with our test config
        poller = SignalPoller(self.mock_can_interface, self.temp_config.name)
        
        # Force the last poll time to be far in the past
        poller.polling_tasks["high"][0] = (100, 0, 0)  # signal_index, member_index, last_poll_time
        
        # Call update
        poller.update()
        
        # Verify that read_signal was called
        self.mock_can_interface.read_signal.assert_called_once_with(0, 100)
        
        # Verify that last poll time was updated
        _, _, last_poll_time = poller.polling_tasks["high"][0]
        self.assertGreater(last_poll_time, 0)
    
    @patch('stiebel_control.heatpump.signal_poller.get_elster_entry_by_english_name')
    def test_get_stats(self, mock_get_elster):
        """Test the get_stats method."""
        # Mock the elster entry lookup
        mock_elster = MagicMock(index=100)
        mock_get_elster.return_value = mock_elster
        
        # Create the poller
        poller = SignalPoller(self.mock_can_interface, self.temp_config.name)
        
        # Get stats
        stats = poller.get_stats()
        
        # Verify stats structure
        self.assertIn('total_signals', stats)
        self.assertIn('priorities', stats)
        self.assertEqual(stats['total_signals'], 3)  # 1 in each priority level
        
        # Verify each priority has expected stats
        for priority in ['high', 'medium', 'low']:
            self.assertIn(priority, stats['priorities'])
            priority_stats = stats['priorities'][priority]
            self.assertIn('count', priority_stats)
            self.assertIn('interval', priority_stats)
            self.assertIn('due_for_polling', priority_stats)

if __name__ == '__main__':
    unittest.main()
