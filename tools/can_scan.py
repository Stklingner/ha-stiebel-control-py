#!/usr/bin/env python3
"""
Elster-Kromschröder CAN-bus Address Scanner and Test Utility

This is a Python implementation of the original C tool by Jürg Müller.
It provides functionality to:
1. Scan all available CAN IDs on the bus
2. Read all values from a specific CAN ID
3. Read a specific value by Elster index
4. Write a new value to a specific Elster index

BE CAREFUL WITH THIS TOOL! Writing values can potentially damage your system.
"""

import argparse
import asyncio
import sys
import time
import logging
import os
from typing import Optional, Dict, Any, Tuple, List

# Ensure proper path for imports regardless of where the script is run from
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from stiebel_control.can.interface import CanInterface
from stiebel_control.can.transport import CanTransport
from stiebel_control.can.protocol import StiebelProtocol, CanMember
from stiebel_control.heatpump.elster_table import get_elster_entry_by_index, get_elster_entry_by_english_name
from stiebel_control.heatpump.elster_table import ElsterType, value_from_signal

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("can_scan")

class CanScanner:
    """Scanner for Stiebel CAN bus devices"""
    
    def __init__(self, can_device: str, sender_id: int, labels_file: str = None, signals_file: str = None, trace: bool = False):
        """
        Initialize the CAN scanner
        
        Args:
            can_device: CAN device name (e.g., 'can0')
            sender_id: CAN ID to use as sender
            labels_file: Optional file with custom labels (format: 0xXXXX:Label)
            signals_file: Optional file with signal names to scan (one per line)
            trace: Whether to enable trace logging
        """
        self.can_device = can_device
        self.sender_id = sender_id
        self.trace = trace
        
        if self.trace:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Initialize CAN interface correctly
        self.can_interface = CanInterface(can_interface=self.can_device)
        self.transport = self.can_interface.transport
        self.protocol = self.can_interface.protocol
        
        # Set up sender as client
        self.sender_member = CanMember("SCANNER", self.sender_id, (0x00, 0x00), (0x00, 0x00), (0xE2, 0x00))
        self.protocol.can_members[0] = self.sender_member  # Replace HACLIENT with our scanner
        
        # Results storage
        self.results = {}
        self.response_event = asyncio.Event()
        self.current_value = None
        self.scan_complete = False
        
        # Custom labels
        self.custom_labels = {}
        if labels_file:
            self._load_custom_labels(labels_file)
            
        # Specific signals to scan
        self.signal_indexes_to_scan = []
        if signals_file:
            self._load_signals_to_scan(signals_file)
        
    def _load_signals_to_scan(self, signals_file):
        """Load signal names to scan from a file
        
        Format: One signal name per line, matching the English names in the Elster table
        Example:
            OUTSIDE_TEMP
            ROOM_INTERNAL_TEMP
        """
        try:
            with open(signals_file, 'r') as f:
                signal_names = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
                
            indexes = []
            # Convert signal names to indexes using the Elster table
            from stiebel_control.heatpump.elster_table import get_elster_entry_by_english_name
            for name in signal_names:
                entry = get_elster_entry_by_english_name(name)
                if entry and entry.index > 0:  # Skip the unknown entry (index 0)
                    indexes.append(entry.index)
                    logger.info(f"Will scan signal: {name} (index: 0x{entry.index:04x})")
                else:
                    logger.warning(f"Unknown signal name: {name}")
            
            self.signal_indexes_to_scan = indexes
            logger.info(f"Loaded {len(indexes)} signal indexes to scan from {signals_file}")
            
        except (IOError, OSError) as e:
            logger.error(f"Failed to load signals file: {e}")
            self.signal_indexes_to_scan = []
    
    def _load_custom_labels(self, labels_file):
        """Load custom labels from a file
        
        Format: <index_hex>:<label>
        Example: 0x0126:Outside Temperature
        """
        try:
            with open(labels_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    parts = line.split(':', 1)
                    if len(parts) != 2:
                        logger.warning(f"Invalid label format: {line}")
                        continue
                        
                    index_str, label = parts
                    try:
                        # Convert hex string to int
                        if index_str.lower().startswith('0x'):
                            index = int(index_str, 16)
                        else:
                            index = int(index_str)
                            
                        self.custom_labels[index] = label.strip()
                    except ValueError:
                        logger.warning(f"Invalid index format: {index_str}")
                        
            logger.info(f"Loaded {len(self.custom_labels)} custom labels from {labels_file}")
        except (IOError, OSError) as e:
            logger.error(f"Failed to load labels file: {e}")
    
    def _ensure_int(self, value):
        """Ensure a value is an integer"""
        if isinstance(value, str):
            # Try to convert to int, assuming hex if starts with 0x
            if value.startswith('0x'):
                return int(value, 16)
            return int(value)
        return int(value)
        
    async def start(self):
        """Start the CAN interface"""
        success = self.can_interface.start()
        if not success:
            raise RuntimeError("Failed to start CAN interface")
    
    async def stop(self):
        """Stop the CAN interface"""
        self.can_interface.stop()

    def _signal_callback(self, signal_index: int, value: Any, can_id: int):
        """Callback for signal responses"""
        # Find member name
        member_name = "unknown"
        for member in self.protocol.can_members:
            if member and member.can_id == can_id:
                member_name = member.name
                break
        
        # Get signal name (from custom labels or Elster table)
        signal_name = None
        converted_value = None
        type_name = "Unknown"
        
        # Check custom labels first
        if signal_index in self.custom_labels:
            signal_name = self.custom_labels[signal_index]
        
        # Then try Elster table
        elster_entry = get_elster_entry_by_index(signal_index)
        if elster_entry:
            if not signal_name:  # Only use Elster name if no custom label
                signal_name = elster_entry.english_name
            type_name = elster_entry.type.name
            # Convert value according to type
            if value is not None:
                converted_value = value_from_signal(value, elster_entry.type)
        
        # Final fallback
        if not signal_name:
            signal_name = f"Unknown-0x{signal_index:04x}"
        
        # Format raw/converted value for display
        if converted_value is not None:
            value_str = f"{converted_value} ({value:04x}h)"
        else:
            value_str = f"0x{value:04x}"
        
        # Log every response at INFO level
        logger.info(f"SIGNAL: CAN 0x{can_id:X} [0x{signal_index:04x}] {signal_name} = {value_str}")
        
        # Store result
        self.results[(can_id, signal_index)] = {
            'value_raw': value,
            'can_id': can_id,
            'can_member': member_name,
            'signal_index': signal_index
        }
        
        # Add additional information if we have it - using what we already determined above
        if signal_name:
            self.results[(can_id, signal_index)]['name'] = signal_name
        
        # Add type information
        self.results[(can_id, signal_index)]['type'] = type_name
        
        # Add converted value
        if converted_value is not None:
            self.results[(can_id, signal_index)]['value'] = converted_value
        
        self.current_value = value
        self.response_event.set()

    async def scan_can_id(self, receiver_id: int, start_index: int = 0, end_index: int = 0x1FFF):
        """
        Scan a range of Elster indices for a specific CAN ID
        
        Args:
            receiver_id: Target CAN ID to scan
            start_index: Starting Elster index (default: 0)
            end_index: Ending Elster index (default: 0x1FFF)
        """
        # If we have specific signal indexes to scan, use those instead of the range
        if self.signal_indexes_to_scan:
            logger.info(f"Scanning CAN ID 0x{receiver_id:x} for {len(self.signal_indexes_to_scan)} specific signals")
            indexes_to_scan = self.signal_indexes_to_scan
        else:
            logger.info(f"Scanning CAN ID 0x{receiver_id:x} from index 0x{start_index:04x} to 0x{end_index:04x}")
            indexes_to_scan = range(start_index, end_index + 1)
        
        # Find the member index for this CAN ID
        member_idx = None
        for i, member in enumerate(self.protocol.can_members):
            if member and member.can_id == receiver_id:
                member_idx = i
                break
        
        if member_idx is None:
            # Add it temporarily
            receiver_id = self._ensure_int(receiver_id)
            member = CanMember(f"DEVICE_{receiver_id:x}", receiver_id, 
                              ((receiver_id//0x80) & 0xFF, (receiver_id % 8) & 0xFF),
                              (0x00, 0x00), (0x00, 0x00))
            member_idx = len(self.protocol.can_members)
            self.protocol.can_members.append(member)
        
        count = 0
        for signal_idx in indexes_to_scan:
            # Reset event
            self.response_event.clear()
            
            # Request the signal with a callback
            if self.trace:
                logger.debug(f"Requesting CAN ID 0x{receiver_id:x}, index 0x{signal_idx:04x}")
            
            # Define a callback function that will handle the response
            def callback(value):
                self._signal_callback(signal_idx, value, receiver_id)
            
            success = self.protocol.read_signal(member_idx, signal_idx, callback)
            
            if not success:
                logger.error(f"Failed to send request for index 0x{signal_idx:04x}")
                continue
            
            # Wait for response with timeout
            try:
                await asyncio.wait_for(self.response_event.wait(), timeout=0.5)
                if self.current_value is not None:
                    count += 1
                    if count % 100 == 0:
                        logger.info(f"Processed {count} signals...")
            except asyncio.TimeoutError:
                pass
            
            # Small delay to not overwhelm the bus
            await asyncio.sleep(0.01)
        
        logger.info(f"Scan complete. Found {count} valid signals.")
        self.scan_complete = True

    async def read_value(self, receiver_id: int, signal_idx: int) -> Optional[Dict[str, Any]]:
        """
        Read a specific value by CAN ID and Elster index
        
        Args:
            receiver_id: Target CAN ID
            signal_idx: Elster index to read
            
        Returns:
            Dictionary with the response data or None if no response
        """
        logger.info(f"Reading CAN ID 0x{receiver_id:x}, index 0x{signal_idx:04x}")
        
        # Find the member index for this CAN ID
        member_idx = None
        for i, member in enumerate(self.protocol.can_members):
            if member and member.can_id == receiver_id:
                member_idx = i
                break
        
        if member_idx is None:
            # Add it temporarily
            receiver_id = self._ensure_int(receiver_id)
            member = CanMember(f"DEVICE_{receiver_id:x}", receiver_id, 
                              ((receiver_id//0x80) & 0xFF, (receiver_id % 8) & 0xFF),
                              (0x00, 0x00), (0x00, 0x00))
            member_idx = len(self.protocol.can_members)
            self.protocol.can_members.append(member)
        
        # Reset event
        self.response_event.clear()
        self.current_value = None
        
        # Define a callback function that will handle the response
        def callback(value):
            self._signal_callback(signal_idx, value, receiver_id)
        
        # Request the signal with a callback
        success = self.protocol.read_signal(member_idx, signal_idx, callback)
        
        if not success:
            logger.error(f"Failed to send request for index 0x{signal_idx:04x}")
            return None
        
        # Wait for response with timeout
        try:
            await asyncio.wait_for(self.response_event.wait(), timeout=2.0)
            if (receiver_id, signal_idx) in self.results:
                return self.results[(receiver_id, signal_idx)]
        except asyncio.TimeoutError:
            logger.warning(f"Timeout waiting for response from CAN ID 0x{receiver_id:x}, index 0x{signal_idx:04x}")
        
        return None

    async def write_value(self, receiver_id: int, signal_idx: int, new_value: int) -> bool:
        """
        Write a value to a specific CAN ID and Elster index
        
        Args:
            receiver_id: Target CAN ID
            signal_idx: Elster index to write to
            new_value: New value to write
            
        Returns:
            True if successful, False otherwise
        """
        logger.warning(f"WRITING to CAN ID 0x{receiver_id:x}, index 0x{signal_idx:04x}, value: 0x{new_value:04x}")
        logger.warning("BE CAREFUL! THIS WILL MODIFY YOUR SYSTEM CONFIGURATION!")
        
        # Safety confirmation
        confirmation = input("Are you sure you want to proceed? (y/N): ")
        if confirmation.lower() != 'y':
            logger.info("Write operation cancelled.")
            return False
        
        # Find the member index for this CAN ID
        member_idx = None
        for i, member in enumerate(self.protocol.can_members):
            if member and member.can_id == receiver_id:
                member_idx = i
                break
        
        if member_idx is None:
            # Add it temporarily
            member = CanMember(f"DEVICE_{receiver_id:x}", receiver_id, 
                              (0x00, 0x00),
                              ((receiver_id//0x80) & 0xFF, (receiver_id % 8) & 0xFF),
                              (0x00, 0x00))
            member_idx = len(self.protocol.can_members)
            self.protocol.can_members.append(member)
        
        # Create write request using low-level access
        # Format: n2 0m fa xx xx vv vv where n = <receiver can id> / 80, m = <receiver can id> % 8
        n = (receiver_id // 0x80) & 0xFF
        m = (receiver_id % 8) & 0xFF
        
        data = [
            0x2 | (n << 4), 
            m, 
            0xFA, 
            (signal_idx >> 8) & 0xFF, 
            signal_idx & 0xFF,
            (new_value >> 8) & 0xFF,
            new_value & 0xFF
        ]
        
        if self.trace:
            data_hex = ' '.join(f"{b:02x}" for b in data)
            logger.debug(f"Sending write request: {data_hex}")
        
        # Send the write request
        success = self.transport.send_message(
            arbitration_id=self.sender_id,
            data=bytes(data),
            is_extended_id=False
        )
        
        if not success:
            logger.error(f"Failed to send write request")
            return False
        
        logger.info(f"Write request sent successfully")
        
        # Wait a moment before reading back to verify
        await asyncio.sleep(1.0)
        
        # Read back the value to verify
        result = await self.read_value(receiver_id, signal_idx)
        if result:
            verify_value = result.get('value_raw')
            if verify_value == new_value:
                logger.info(f"Write verified! New value is 0x{verify_value:04x}")
                return True
            else:
                logger.warning(f"Write verification failed. Expected 0x{new_value:04x}, got 0x{verify_value:04x}")
        else:
            logger.warning("Could not verify write operation.")
        
        return False

    async def scan_all_can_ids(self):
        """
        Scan all common CAN IDs for available devices
        """
        logger.info("Scanning for active CAN devices...")
        
        # Common CAN IDs used in Stiebel systems
        can_ids = [0x180, 0x300, 0x301, 0x302, 0x303, 0x480, 0x500, 0x600, 0x601, 0x602, 0x603]
        
        active_ids = []
        for can_id in can_ids:
            # Try to read a common index like 0x0001 (usually device type)
            result = await self.read_value(can_id, 0x0001)
            if result and result.get('value_raw') is not None:
                active_ids.append(can_id)
                logger.info(f"Found active device at CAN ID 0x{can_id:x}: {result.get('value_raw')}")
        
        logger.info(f"Active CAN IDs: {', '.join(f'0x{x:x}' for x in active_ids)}")
        return active_ids
    
    def print_results(self):
        """Print the results of the scan in a formatted table"""
        if not self.results:
            logger.info("No results to display.")
            return
        
        # Group results by CAN ID
        by_can_id = {}
        for (can_id, signal_idx), result in self.results.items():
            if can_id not in by_can_id:
                by_can_id[can_id] = []
            by_can_id[can_id].append(result)
        
        # Print results
        logger.info("=" * 80)
        logger.info("CAN SCAN RESULTS")
        logger.info("=" * 80)
        
        for can_id, results in sorted(by_can_id.items()):
            logger.info(f"\nCAN ID: 0x{can_id:x} ({results[0].get('can_member', 'unknown')})")
            logger.info("-" * 80)
            logger.info(f"{'Value':^15} | {'Name':<50} | {'Type':<15}")
            logger.info("-" * 80)
            
            for result in sorted(results, key=lambda x: x['signal_index']):
                # Store index in case we need to include it in the name for unknown signals
                idx = result['signal_index']
                val = result.get('value', "N/A")
                name = result.get('name', f"Unknown-0x{idx:04x}")
                type_name = result.get('type', "Unknown")
                
                logger.info(f"{val!s:^15} | {name:<50} | {type_name:<15}")

async def main():
    """Main entry point for the CAN scanner utility"""
    # Set up handler for graceful termination
    loop = asyncio.get_running_loop()
    signals = (signal.SIGINT, signal.SIGTERM)
    for s in signals:
        loop.add_signal_handler(s, lambda: asyncio.create_task(shutdown()))
        
    async def shutdown():
        """Handle graceful shutdown on keyboard interrupt"""
        logger.info("Shutting down scanner...")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        loop.stop()
    parser = argparse.ArgumentParser(
        description="Elster-Kromschröder CAN-bus address scanner and test utility"
    )
    
    parser.add_argument("can_device", help="CAN device to use (e.g., 'can0')")
    parser.add_argument("sender_id", help="CAN ID to use as sender (e.g., '680')", type=lambda x: int(x, 0))
    
    # Optional action arguments
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--total", action="store_true", help="Scan all CAN IDs for available devices")
    group.add_argument("--receiver", type=lambda x: int(x, 0), 
                      help="CAN ID to scan or interact with (e.g., '180')")
    group.add_argument("--target", type=str, 
                      help="Format: <can_id>[.<index>[.<new_value>]] (e.g., '180.0126' or '180.0126.0f00')")
    
    # Additional options
    parser.add_argument("--trace", action="store_true", help="Enable detailed logging")
    parser.add_argument("--range", type=str, help="Scan index range in format 'start-end' (default: '0-1fff')")
    parser.add_argument("--labels", type=str, help="Path to a file with custom labels for Elster indexes (format: 0xXXXX:Label)")
    parser.add_argument("--signals", type=str, help="Path to a file with signal names to scan (one per line)")
    
    args = parser.parse_args()
    
    # Validate sender ID
    if args.sender_id not in [0x680, 0x700, 0x780]:
        logger.error("Allowed sender CAN IDs: 0x680, 0x700, 0x780")
        return 1
    
    # Initialize scanner
    scanner = CanScanner(args.can_device, args.sender_id, args.labels, args.signals, args.trace)
    await scanner.start()
    
    try:
        # Determine the action based on arguments
        if args.total:
            # Scan for all available CAN IDs
            active_ids = await scanner.scan_all_can_ids()
            
            # For each active ID, scan some basic indices
            for can_id in active_ids:
                await scanner.scan_can_id(can_id, 0x0000, 0x0010)  # Scan basic system info
            
        elif args.receiver:
            # Scan a specific CAN ID
            if args.range:
                start, end = args.range.split('-')
                start_idx = int(start, 16)
                end_idx = int(end, 16)
            else:
                start_idx = 0x0000
                end_idx = 0x1FFF
                
            await scanner.scan_can_id(args.receiver, start_idx, end_idx)
            
        elif args.target:
            # Parse the target string
            parts = args.target.split('.')
            
            if len(parts) < 2:
                logger.error("Target format should be <can_id>.<index>[.<new_value>]")
                return 1
                
            can_id = int(parts[0], 0)
            index = int(parts[1], 16)
            
            if len(parts) >= 3:
                # Write operation
                new_value = int(parts[2], 16)
                success = await scanner.write_value(can_id, index, new_value)
                if not success:
                    logger.error("Write operation failed")
                    return 1
            else:
                # Read operation
                result = await scanner.read_value(can_id, index)
                if result:
                    raw = result.get('value_raw')
                    val = result.get('value', raw)
                    name = result.get('name', "Unknown")
                    
                    logger.info(f"CAN ID: 0x{can_id:x}, Index: 0x{index:04x}")
                    logger.info(f"Raw value: 0x{raw:04x}")
                    logger.info(f"Converted value: {val}")
                    logger.info(f"Signal name: {name}")
                else:
                    logger.warning(f"No response for CAN ID 0x{can_id:x}, index 0x{index:04x}")
        else:
            # No specific action, show usage
            parser.print_help()
            return 1
            
        # Print results if we did a scan
        if args.total or args.receiver:
            scanner.print_results()
            
    finally:
        # Clean up
        await scanner.stop()
    
    return 0

if __name__ == "__main__":
    try:
        # Import signal module locally to avoid issues if not available
        import signal
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Scan interrupted by user")
        sys.exit(130)  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
