#!/usr/bin/env python3
"""
Improved Conversion tool to convert ElsterTable.h (C++ format) to YAML format.

This script extracts the signal definitions from the ElsterTable.h file
and generates a YAML file with all signal definitions (for configuration).
The Python module will load this YAML file during initialization.
"""

import os
import re
import yaml
import argparse
from pathlib import Path
from typing import List, Dict, Tuple


def get_type_mapping() -> Dict[str, str]:
    """
    Get a mapping of C++ type names to Python type names.
    
    Returns:
        Dictionary mapping C++ type names to Python type names.
    """
    type_mapping = {
        'et_default': 'ET_INTEGER',       # Plain integer values
        'et_dec_val': 'ET_DEC_VAL',      # Values with 1 decimal place (typically temperatures)
        'et_cent_val': 'ET_CENT_VAL',         # Values with 2 decimal places (typically percentages)
        'et_mil_val': 'ET_MIL_VAL',     # Values with 3 decimal places
        'et_byte': 'ET_BYTE',             # Byte values (8-bit integers)
        'et_bool': 'ET_BOOLEAN',             # Boolean values (0x0001/0x0000)
        'et_little_bool': 'ET_LITTLE_BOOL',      # Boolean values in different format (0x0100/0x0000)
        'et_double_val': 'ET_DEC_VAL',  # Map to ET_DEC_VAL instead of ET_DOUBLE_VALUE 
        'et_triple_val': 'ET_MIL_VAL',  # Map to ET_MIL_VAL instead of ET_TRIPLE_VALUE
        'et_little_endian': 'ET_LITTLE_ENDIAN',    # Byte-swapped integers
        'et_betriebsart': 'ET_MODE', # Operation modes
        'et_zeit': 'ET_TIME',                # Map to ET_TIME instead of ET_HOUR
        'et_datum': 'ET_DATE',               # Date values (DD.MM)
        'et_time_domain': 'ET_TIME_DOMAIN',  # Map to ET_TIME_DOMAIN instead of ET_INTEGER
        'et_dev_nr': 'ET_DEV_NR',            # Device numbers
        'et_err_nr': 'ET_ERR_CODE',          # Error codes
        'et_dev_id': 'ET_DEV_ID'             # Device IDs
    }
    
    return type_mapping


def parse_elster_table(content: str, type_map: Dict[str, str]) -> List[Dict]:
    """
    Parse the ElsterTable array from the C++ header file.
    
    Args:
        content: Content of the ElsterTable.h file
        type_map: Mapping of C++ type names to Python type names
        
    Returns:
        List of dictionaries representing ElsterIndex entries
    """
    # Find the ElsterTable definition
    table_pattern = r'static\s+const\s+ElsterIndex\s+ElsterTable\[\]\s*=\s*\{(.*?)\};'
    table_match = re.search(table_pattern, content, re.DOTALL)
    
    if not table_match:
        print("WARNING: Could not find ElsterTable definition in header file!")
        return []
    
    table_content = table_match.group(1)
    
    # Split the content into individual entries
    entries = []
    # Regular expression to match each table entry
    entry_pattern = r'\{"([^"]+)"\s*,\s*(0x[0-9a-fA-F]+|\d+)\s*,\s*([a-zA-Z0-9_]+)\s*,\s*"([^"]*)"\}'
    
    for match in re.finditer(entry_pattern, table_content):
        name = match.group(1)
        index_str = match.group(2)
        cpp_type = match.group(3)
        english_name = match.group(4) or name  # Use name if English name is empty
        
        # Convert hex format to int
        if index_str.startswith('0x'):
            index_val = int(index_str, 16)
        else:
            index_val = int(index_str)
            
        # Map the C++ type to Python type
        py_type = type_map.get(cpp_type, "ET_NONE")  # Default to ET_NONE if type not found
        
        entries.append({
            "name": name,
            "english_name": english_name,
            "index": index_val,
            "type": py_type,
            "cpp_type": cpp_type
        })
    
    print(f"Found {len(entries)} entries in ElsterTable")
    return entries


def infer_ha_entity_type_and_unit(signal_name, english_name, value_type):
    """
    Infer the Home Assistant entity type and unit based on signal name patterns and ElsterType.
    
    Args:
        signal_name (str): The original German signal name
        english_name (str): The English translation of the signal name
        value_type (str): The ElsterType value as a string
        
    Returns:
        tuple: (entity_type, unit_of_measurement)
    """
    # First, define default mappings
    type_to_ha_mapping = {
        'ET_NONE': ('sensor', None),
        'ET_INTEGER': ('sensor', None),
        'ET_BOOLEAN': ('binary_sensor', None),
        'ET_DEC_VAL': ('sensor', None),
        'ET_CENT_VAL': ('sensor', None),
        'ET_MIL_VAL': ('sensor', None),
        'ET_BYTE': ('sensor', None),
        'ET_LITTLE_BOOL': ('binary_sensor', None),
        'ET_LITTLE_ENDIAN': ('sensor', None),
        'ET_MODE': ('sensor', None),
        'ET_TIME': ('sensor', None),
        'ET_DATE': ('sensor', None),
        'ET_TIME_DOMAIN': ('sensor', None),
        'ET_DEV_NR': ('sensor', None),
        'ET_ERR_CODE': ('sensor', None),
        'ET_DEV_ID': ('sensor', None),
    }
    
    # Get the base entity type and unit from the type mapping
    entity_type, unit = type_to_ha_mapping.get(value_type, ('sensor', None))
    
    # Now check if we can infer better entity types based on the name patterns
    name_for_matching = (english_name + " " + signal_name).upper()
    
    # Temperature patterns
    if any(pattern in name_for_matching for pattern in ['TEMP', 'TEMPERATURE', 'GRAD']):
        return 'sensor.temperature', '°C'
        
    # Pressure patterns
    if any(pattern in name_for_matching for pattern in ['DRUCK', 'PRESSURE']):
        return 'sensor.pressure', 'bar'
        
    # Percentage patterns
    if any(pattern in name_for_matching for pattern in ['PERCENT', 'PROZENT', 'HUMIDITY', 'FEUCHTIGKEIT']):
        return 'sensor.humidity', '%'
    
    # Power/Energy patterns
    if any(pattern in name_for_matching for pattern in ['POWER', 'LEISTUNG']):
        return 'sensor.power', 'kW'
    if any(pattern in name_for_matching for pattern in ['ENERGY', 'ENERGIE', 'ERTRAG', 'YIELD']):
        return 'sensor.energy', 'kWh'
        
    # Runtime/Duration patterns
    if any(pattern in name_for_matching for pattern in ['RUNTIME', 'LAUFZEIT', 'BETRIEBSSTUNDEN', 'OPERATING_HOURS']):
        return 'sensor.duration', 'h'
    
    # Time patterns
    if any(pattern in name_for_matching for pattern in ['ZEIT', 'TIME']) and not 'RUNTIME' in name_for_matching:
        if any(timeunit in name_for_matching for timeunit in ['STUNDE', 'HOUR']):
            return 'sensor.duration', 'h'
        elif any(timeunit in name_for_matching for timeunit in ['MINUTE']):
            return 'sensor.duration', 'min'
        else:
            return 'sensor.timestamp', None
        
    # Binary/Boolean patterns
    if any(pattern in name_for_matching for pattern in ['ON/OFF', 'EIN_AUS', 'EIN/AUS', 'STATUS']):
        return 'binary_sensor.power', None
    
    # Operation mode patterns
    if any(pattern in name_for_matching for pattern in ['MODE', 'BETRIEBSART', 'OPERATION_MODE']):
        return 'sensor.enum', None
    
    # Error patterns
    if any(pattern in name_for_matching for pattern in ['ERROR', 'FEHLER', 'FAULT']):
        return 'sensor.enum', None
    
    # Counting patterns
    if any(pattern in name_for_matching for pattern in ['COUNTER', 'ZÄHLER', 'COUNT', 'ANZAHL']):
        return 'sensor', None
    
    # Flow patterns
    if any(pattern in name_for_matching for pattern in ['FLOW', 'DURCHFLUSS', 'VOLUME']):
        return 'sensor.flow', 'm³/h'
        
    # Date patterns
    if any(pattern in name_for_matching for pattern in ['DATE', 'DATUM', 'YEAR', 'JAHR', 'MONTH', 'MONAT', 'DAY', 'TAG']):
        return 'sensor.date', None
    
    # If no specific pattern matches, return the default mapping based on type
    return entity_type, unit


def generate_yaml(elster_table: List[Dict], output_path: str) -> None:
    """
    Generate a YAML file with all Elster signal definitions.
    
    Args:
        elster_table: List of parsed ElsterEntry objects
        output_path: Path to write the YAML file
    """
    # Create the directory if it doesn't exist
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Convert to YAML-friendly format
    yaml_data = []
    for entry in elster_table:
        if 'name' in entry and 'english_name' in entry and 'index' in entry and 'type' in entry:
            # Infer Home Assistant entity type and unit
            ha_entity_type, unit = infer_ha_entity_type_and_unit(
                entry['name'], 
                entry['english_name'], 
                entry['type']
            )
            
            yaml_entry = {
                'name': entry['name'],
                'english_name': entry['english_name'],
                'index': entry['index'],
                'type': entry['type'],
                'ha_entity_type': ha_entity_type,
                'unit_of_measurement': unit
            }
            yaml_data.append(yaml_entry)
    
    # Write to YAML file
    with open(output_path, 'w') as f:
        yaml.dump(yaml_data, f, sort_keys=False, allow_unicode=True)
    
    print(f"Generated YAML file with {len(yaml_data)} signal definitions: {output_path}")
    print(f"Successfully converted {len(yaml_data)} signals to YAML format.")


def main():
    """Main entry point for the script."""
    parser = argparse.ArgumentParser(
        description='Convert ElsterTable.h to YAML format'
    )
    parser.add_argument(
        '--input', '-i',
        default='ElsterTable.h',
        help='Input ElsterTable.h file path'
    )
    parser.add_argument(
        '--yaml-output', '-y',
        default='../stiebel_control/heatpump/elster_signals.yaml',
        help='Output YAML file path'
    )
    
    args = parser.parse_args()
    
    # Check if input file exists
    if not os.path.exists(args.input):
        print(f"Input file not found: {args.input}")
        return 1
    
    # Read the header file
    with open(args.input, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse the header file
    type_map = get_type_mapping()
    elster_table = parse_elster_table(content, type_map)
    
    # Generate output files
    generate_yaml(elster_table, args.yaml_output)
    
    print(f"Successfully converted {len(elster_table)} signals to YAML format.")
    return 0


if __name__ == '__main__':
    main()
