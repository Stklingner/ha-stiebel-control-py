"""
ElsterTable module - contains the mapping of Stiebel Eltron signal codes.

This is a Python port of the original C++ implementation in ElsterTable.h.
Generated automatically by the convert_elster_table_improved.py script.
"""

import os
import yaml
import logging
from enum import Enum, auto
from pathlib import Path
from typing import List, Dict, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

class ElsterType(Enum):
    """Enumeration of Elster value types."""
    ET_NONE = auto()        # Unknown/unspecified type (read-only)
    ET_INTEGER = auto()     # et_default - Plain integer value
    ET_BOOLEAN = auto()     # et_bool - Boolean value (0/1)
    ET_DEC_VAL = auto()     # et_dec_val - Value with 1 decimal place (scaled by 10)
    ET_CENT_VAL = auto()    # et_cent_val - Value with 2 decimal places (scaled by 100)
    ET_MIL_VAL = auto()     # et_mil_val - Value with 3 decimal places (scaled by 1000)
    ET_BYTE = auto()        # et_byte - Raw byte value
    ET_LITTLE_BOOL = auto() # et_little_bool - Boolean in different format (0x0100/0x0000)
    ET_LITTLE_ENDIAN = auto() # et_little_endian - Byte-swapped integers
    ET_MODE = auto()        # et_betriebsart - Operation mode enum
    ET_TIME = auto()        # et_zeit - Time value
    ET_DATE = auto()        # et_datum - Date value
    ET_TIME_DOMAIN = auto() # et_time_domain - Time range with special formatting
    ET_DEV_NR = auto()      # et_dev_nr - Device number
    ET_ERR_CODE = auto()    # et_err_nr - Error code
    ET_DEV_ID = auto()      # et_dev_id - Device ID


# Import enum values into global namespace for backward compatibility
ET_NONE = ElsterType.ET_NONE
ET_INTEGER = ElsterType.ET_INTEGER
ET_BOOLEAN = ElsterType.ET_BOOLEAN
ET_DEC_VAL = ElsterType.ET_DEC_VAL
ET_CENT_VAL = ElsterType.ET_CENT_VAL
ET_MIL_VAL = ElsterType.ET_MIL_VAL
ET_BYTE = ElsterType.ET_BYTE
ET_LITTLE_BOOL = ElsterType.ET_LITTLE_BOOL
ET_LITTLE_ENDIAN = ElsterType.ET_LITTLE_ENDIAN
ET_MODE = ElsterType.ET_MODE
ET_TIME = ElsterType.ET_TIME
ET_DATE = ElsterType.ET_DATE
ET_TIME_DOMAIN = ElsterType.ET_TIME_DOMAIN
ET_DEV_NR = ElsterType.ET_DEV_NR
ET_ERR_CODE = ElsterType.ET_ERR_CODE
#ET_DEV_ID = ElsterType.ET_DEV_ID


class ElsterEntry:
    """Class representing an Elster signal index with metadata."""
    
    def __init__(self, name, english_name, index, value_type):
        """Initialize ElsterEntry.
        
        Args:
            name (str): Original German name of the signal
            english_name (str): English name of the signal
            index (int): Signal index
            value_type (ElsterType): Type of the signal value
        """
        self.name = name
        self.english_name = english_name
        self.index = index
        self.type = value_type


def load_elster_signals_from_yaml() -> List[ElsterEntry]:
    """
    Load Elster signal definitions from YAML file.
    
    Returns:
        list: List of ElsterEntry objects
    """
    # Define an emergency fallback in case loading fails
    fallback_signals = [
        ElsterEntry("INDEX_NOT_FOUND", "INDEX_NOT_FOUND", 0, ET_NONE),
    ]
    
    # Update the path to account for the heatpump subfolder
    config_file = Path(__file__).parent / 'elster_signals.yaml'
    
    if not config_file.exists():
        logger.warning(f"Elster signals YAML file not found: {config_file}")
        return fallback_signals
    
    try:
        with open(config_file, 'r') as f:
            signals_data = yaml.safe_load(f)
        
        signals = []
        for signal_data in signals_data:
            # Convert string type to ElsterType enum
            type_string = signal_data['type']
            
            # Get ElsterType value by name
            if hasattr(ElsterType, type_string):
                value_type = getattr(ElsterType, type_string)
            else:
                # Default to ET_NONE if type not found
                logger.warning(f"Unknown ElsterType '{type_string}' for signal {signal_data['name']}, defaulting to ET_NONE")
                value_type = ElsterType.ET_NONE
            
            signal = ElsterEntry(
                signal_data['name'],
                signal_data['english_name'],
                signal_data['index'],
                value_type
            )
            signals.append(signal)
        
        logger.info(f"Loaded {len(signals)} Elster signals from YAML file")
        return signals
    except Exception as e:
        logger.error(f"Failed to load Elster signals from YAML: {e}")
        return fallback_signals


# Load signals from YAML file
ELSTER_TABLE = load_elster_signals_from_yaml()


# Create lookup dictionaries for fast index lookups
ELSTER_INDEX_BY_NAME = {signal.name: signal for signal in ELSTER_TABLE}
ELSTER_INDEX_BY_ENGLISH_NAME = {signal.english_name: signal for signal in ELSTER_TABLE}
ELSTER_INDEX_BY_INDEX = {signal.index: signal for signal in ELSTER_TABLE}


# BetriebsartList from original C++ code
# BETRIEBSARTLIST = {
#     0: "Notbetrieb",
#     1: "Bereitschaft",
#     2: "Programmbetrieb",
#     3: "Tagbetrieb",
#     4: "Absenkbetrieb",
#     5: "Sommer(WW)",
#     6: "Aus"
# }

MODELIST = {
    0: "Emergency",
    1: "Standby",
    2: "Auto mode",
    3: "Day mode",
    4: "Night mode",
    5: "Warm Water"
}

# ErrorList from original C++ code
ERRORLIST = {
    2: "Contactor stuck",
    3: "ERR HD sensor",
    4: "High pressure",
    5: "Evaporator sensor",
    6: "Relay driver",
    7: "Relay level",
    8: "Hex switch",
    9: "Fan speed",
    10: "Fan driver",
    11: "Reset module",
    12: "Low pressure (ND)",
    13: "ROM",
    14: "Source min. temp",
    16: "Defrosting",
    18: "ERR T-HEI IWS",
    23: "ERR T-FRO IWS",
    26: "Low pressure",
    27: "ERR low pressure",
    28: "ERR high pressure",
    29: "HD sensor max",
    30: "Hot gas max",
    31: "ERR HD sensor",
    32: "Freeze protection",
    33: "No output"
}

def get_elster_entry_by_name(name):
    """Get ElsterEntry by German name.
    
    Args:
        name (str): German name of the signal
        
    Returns:
        ElsterEntry: Corresponding ElsterEntry or UNKNOWN if not found
    """
    return ELSTER_INDEX_BY_NAME.get(name, ELSTER_TABLE[0])


def get_elster_entry_by_english_name(english_name):
    """Get ElsterEntry by English name.
    
    Args:
        english_name (str): English name of the signal
        
    Returns:
        ElsterEntry: Corresponding ElsterEntry or UNKNOWN if not found
    """
    return ELSTER_INDEX_BY_ENGLISH_NAME.get(english_name, ELSTER_TABLE[0])


def get_elster_entry_by_index(index):
    """Get ElsterEntry by index value.
    
    Args:
        index (int): Index value of the signal
        
    Returns:
        ElsterEntry: Corresponding ElsterEntry or UNKNOWN if not found
    """
    return ELSTER_INDEX_BY_INDEX.get(index, ELSTER_TABLE[0])


def value_from_signal(value, value_type):
    """Convert a raw signal value to a meaningful value based on its type.
    
    Args:
        value (int): Raw value from the CAN signal
        value_type (ElsterType): Type of the value
        
    Returns:
        The converted value in the appropriate type (float, int, str)
    """
    if value_type == ElsterType.ET_NONE:
        return value  # Return raw value without conversion for ET_NONE type
    elif    lsterType.ET_INTEGER or value_type == ElsterType.ET_BYTE:
        return value  # Return integer values as is
    elif value_type == ElsterType.ET_BOOLEAN or value_type == ElsterType.ET_LITTLE_BOOL:
        # For ET_LITTLE_BOOL, value is 0x0100 (256) instead of 0x0001 (1)
        if value_type == ElsterType.ET_LITTLE_BOOL:
            return bool(value & 0x0100)
        return bool(value)
    elif value_type == ElsterType.ET_DEC_VAL:
        # Handle values with 1 decimal place (scaled by 10)
        if value > 32767:  # If high bit is set, it's negative
            signed_value = value - 65536
            return signed_value / 10.0
        return value / 10.0
    elif value_type == ElsterType.ET_CENT_VAL:
        # Handle values with 2 decimal places (scaled by 100)
        if value > 32767:  # If high bit is set, it's negative
            signed_value = value - 65536
            return signed_value / 100.0
        return value / 100.0
    elif value_type == ElsterType.ET_MIL_VAL:
        # Handle values with 3 decimal places (scaled by 1000)
        if value > 32767:  # If high bit is set, it's negative
            signed_value = value - 65536
            return signed_value / 1000.0
        return value / 1000.0
    elif value_type == ElsterType.ET_MODE:
        # Lookup operation mode in the MODELIST
        return MODELIST.get(value, "Unknown")
    elif value_type == ElsterType.ET_ERR_CODE:
        # Lookup error code in the ERRORLIST
        return ERRORLIST.get(value, "Unknown")
    elif value_type == ElsterType.ET_TIME:
        # Convert time in seconds to hours
        return value / 3600.0
    elif value_type == ElsterType.ET_DATE:
        # Format date as YYYY-MM-DD (assuming format YYYYMMDD)
        year = value // 10000
        month = (value // 100) % 100
        day = value % 100
        return f"{year:04d}-{month:02d}-{day:02d}"
    elif value_type == ElsterType.ET_LITTLE_ENDIAN:
        # Byte-swapped integer values
        high_byte = (value & 0xFF00) >> 8
        low_byte = (value & 0x00FF) << 8
        return high_byte | low_byte
    elif value_type == ElsterType.ET_TIME_DOMAIN:
        # Time domain format (implementation depends on specific format)
        return value
    elif value_type in [ElsterType.ET_DEV_NR, ElsterType.ET_DEV_ID]:
        # Device-related values are just integers
        return value
    else:
        return value  # No translation for other types


def signal_from_value(string_value, value_type):
    """Convert a meaningful value to a raw signal value based on its type.
    
    Args:
        string_value (str): String representation of value
        value_type (ElsterType): Type of the value
        
    Returns:
        int: The raw integer value to write to the CAN signal
    """
    if value_type == ElsterType.ET_NONE:
        raise ValueError("Cannot write to signals with ET_NONE type")
    elif value_type == ElsterType.ET_INTEGER or value_type == ElsterType.ET_BYTE:
        return int(string_value)
    elif value_type == ElsterType.ET_BOOLEAN:
        return 1 if string_value.lower() in ["true", "1", "on", "yes"] else 0
    elif value_type == ElsterType.ET_LITTLE_BOOL:
        # For ET_LITTLE_BOOL, use 0x0100 (256) instead of 0x0001 (1)
        return 0x0100 if string_value.lower() in ["true", "1", "on", "yes"] else 0
    elif value_type == ElsterType.ET_DEC_VAL:
        # Values with 1 decimal place (scaled by 10)
        float_val = float(string_value) * 10
        # Convert to 16-bit signed integer representation if needed
        if float_val < 0:
            return int(float_val) & 0xFFFF  # Convert to 16-bit unsigned representation of signed value
        return int(float_val)
    elif value_type == ElsterType.ET_CENT_VAL:
        # Values with 2 decimal places (scaled by 100)
        float_val = float(string_value) * 100
        # Convert to 16-bit signed integer representation if needed
        if float_val < 0:
            return int(float_val) & 0xFFFF
        return int(float_val)
    elif value_type == ElsterType.ET_MIL_VAL:
        # Values with 3 decimal places (scaled by 1000)
        float_val = float(string_value) * 1000
        # Convert to 16-bit signed integer representation if needed
        if float_val < 0:
            return int(float_val) & 0xFFFF
        return int(float_val)
    elif value_type == ElsterType.ET_MODE:
        # Reverse lookup in MODELIST
        for code, desc in MODELIST.items():
            if desc == string_value:
                return code
        return 0  # Default to first value if not found
    elif value_type == ElsterType.ET_ERR_CODE:
        for code, desc in ERRORLIST.items():
            if desc == string_value:
                return code
        return 0  # Default to first value if not found
    elif value_type == ElsterType.ET_TIME:
        return int(float(string_value) * 3600)  # Hours to seconds
    elif value_type == ElsterType.ET_DATE:
        # Parse YYYY-MM-DD and convert to YYYYMMDD integer
        parts = string_value.split('-')
        if len(parts) == 3:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            return year * 10000 + month * 100 + day
        else:
            return 0
    elif value_type == ElsterType.ET_LITTLE_ENDIAN:
        # Swap bytes for little endian values
        value = int(string_value)
        high_byte = (value & 0xFF00) >> 8
        low_byte = (value & 0x00FF) << 8
        return high_byte | low_byte
    elif value_type == ElsterType.ET_TIME_DOMAIN:
        # Time domain format conversion depends on specific format
        return int(string_value)
    elif value_type in [ElsterType.ET_DEV_NR, ElsterType.ET_DEV_ID]:
        # Device-related values are integers
        return int(string_value)
    else:
        return int(string_value)  # Simple int conversion for other types
