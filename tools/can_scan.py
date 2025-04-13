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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("can_scan")

class CanScanner:
    """Scanner for Stiebel CAN bus devices"""
    
    def __init__(self, can_device: str, sender_id: int, trace: bool = False):
        """
        Initialize the CAN scanner
        
        Args:
            can_device: CAN device name (e.g., 'can0')
            sender_id: CAN ID to use as sender
            trace: Whether to enable trace logging
        """
        self.can_device = can_device
        self.sender_id = sender_id
        self.trace = trace
        
        if self.trace:
            logging.getLogger().setLevel(logging.DEBUG)
        
        # Initialize CAN interface
        self.transport = CanTransport(self.can_device)
        self.protocol = StiebelProtocol(self.transport)
        self.can_interface = CanInterface(self.protocol)
        
        # Set up sender as client
        self.sender_member = CanMember("SCANNER", self.sender_id, (0x00, 0x00), (0x00, 0x00), (0xE2, 0x00))
        self.protocol.can_members[0] = self.sender_member  # Replace HACLIENT with our scanner
        
        # Results storage
        self.results = {}
        self.response_event = asyncio.Event()
        self.current_value = None
        self.scan_complete = False
        
    async def start(self):
        """Start the CAN interface"""
        await self.can_interface.start()
    
    async def stop(self):
        """Stop the CAN interface"""
        await self.can_interface.stop()

    def _signal_callback(self, signal_index: int, value: Any, can_id: int):
        """Callback for signal responses"""
        if self.trace:
            logger.debug(f"Response received: CAN ID 0x{can_id:x}, index 0x{signal_index:04x}, value: {value}")
        
        member_name = "unknown"
        for member in self.protocol.can_members:
            if member and member.can_id == can_id:
                member_name = member.name
                break
        
        # Store result
        self.results[(can_id, signal_index)] = {
            'value_raw': value,
            'can_id': can_id,
            'can_member': member_name,
            'signal_index': signal_index
        }
        
        # Add additional information if we have it
        elster_entry = get_elster_entry_by_index(signal_index)
        if elster_entry:
            self.results[(can_id, signal_index)]['name'] = elster_entry.english_name
            self.results[(can_id, signal_index)]['type'] = elster_entry.type.name
            # Convert value according to type
            if value is not None:
                self.results[(can_id, signal_index)]['value'] = value_from_signal(value, elster_entry.type)
        
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
        logger.info(f"Scanning CAN ID 0x{receiver_id:x} from index 0x{start_index:04x} to 0x{end_index:04x}")
        
        # Find the member index for this CAN ID
        member_idx = None
        for i, member in enumerate(self.protocol.can_members):
            if member and member.can_id == receiver_id:
                member_idx = i
                break
        
        if member_idx is None:
            # Add it temporarily
            member = CanMember(f"DEVICE_{receiver_id:x}", receiver_id, 
                              ((receiver_id//0x80) & 0xFF, (receiver_id % 8) & 0xFF),
                              (0x00, 0x00), (0x00, 0x00))
            member_idx = len(self.protocol.can_members)
            self.protocol.can_members.append(member)
        
        count = 0
        for signal_idx in range(start_index, end_index + 1):
            # Register callback for this signal
            self.protocol.register_signal_callback(signal_idx, receiver_id, self._signal_callback)
            
            # Reset event
            self.response_event.clear()
            
            # Request the signal
            if self.trace:
                logger.debug(f"Requesting CAN ID 0x{receiver_id:x}, index 0x{signal_idx:04x}")
            
            success = self.protocol.read_signal(member_idx, signal_idx)
            
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
            member = CanMember(f"DEVICE_{receiver_id:x}", receiver_id, 
                              ((receiver_id//0x80) & 0xFF, (receiver_id % 8) & 0xFF),
                              (0x00, 0x00), (0x00, 0x00))
            member_idx = len(self.protocol.can_members)
            self.protocol.can_members.append(member)
        
        # Register callback for this signal
        self.protocol.register_signal_callback(signal_idx, receiver_id, self._signal_callback)
        
        # Reset event
        self.response_event.clear()
        self.current_value = None
        
        # Request the signal
        success = self.protocol.read_signal(member_idx, signal_idx)
        
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
            logger.info(f"{'Index':^8} | {'Value (HEX)':^12} | {'Value':^15} | {'Name':<30} | {'Type':<15}")
            logger.info("-" * 80)
            
            for result in sorted(results, key=lambda x: x['signal_index']):
                idx = result['signal_index']
                raw = result.get('value_raw')
                raw_hex = f"0x{raw:04x}" if raw is not None else "N/A"
                val = result.get('value', "N/A")
                name = result.get('name', "Unknown")
                type_name = result.get('type', "Unknown")
                
                logger.info(f"0x{idx:04x} | {raw_hex:^12} | {val!s:^15} | {name:<30} | {type_name:<15}")

async def main():
    """Main entry point for the CAN scanner utility"""
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
    
    args = parser.parse_args()
    
    # Validate sender ID
    if args.sender_id not in [0x680, 0x700, 0x780]:
        logger.error("Allowed sender CAN IDs: 0x680, 0x700, 0x780")
        return 1
    
    # Initialize scanner
    scanner = CanScanner(args.can_device, args.sender_id, args.trace)
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
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("Scan interrupted by user")
        sys.exit(130)  # Standard exit code for SIGINT
