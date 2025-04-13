#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Value transformations for Stiebel Control.

This module provides functions to transform values between CAN signals
and Home Assistant entities.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def transform_value(
    value: Any, 
    entity_id: str, 
    entity_type: str,
    signal_name: str,
    signal_type: str = 'value',
    unit: str = ''
) -> Any:
    """
    Transform a value based on entity type and signal characteristics.
    
    Args:
        value: The original value
        entity_id: The entity ID
        entity_type: The entity type (sensor, binary_sensor, etc.)
        signal_name: The signal name
        signal_type: The type of signal (from Elster table)
        unit: The unit of measurement
        
    Returns:
        The transformed value suitable for the entity type
    """
    # Handle based on entity type
    if entity_type == 'binary_sensor':
        return transform_to_binary_state(value, signal_type)
    elif entity_type == 'select':
        return transform_to_select_state(value, signal_name)
    else:  # Default to sensor transformation
        return transform_to_sensor_state(value, signal_type, unit)


def transform_to_sensor_state(value: Any, signal_type: str, unit: str) -> Any:
    """
    Transform a value for a sensor entity.
    
    Args:
        value: The original value
        signal_type: The type of signal
        unit: The unit of measurement
        
    Returns:
        The transformed sensor value
    """
    # Temperature values often need scaling
    if signal_type in ['temperature', 'temp'] or unit in ['°C', '°F']:
        # Convert to float and fix precision for temperature
        try:
            temp_value = float(value)
            # Stiebel often uses tenths of degrees, scale if needed
            if temp_value > 100 and unit == '°C':  # Likely in tenths of degrees
                temp_value = temp_value / 10.0
            return round(temp_value, 1)
        except (ValueError, TypeError):
            logger.warning(f"Failed to convert temperature value: {value}")
            return value
            
    # Power/energy values
    elif signal_type in ['power', 'energy'] or unit in ['W', 'kW', 'kWh']:
        try:
            power_value = float(value)
            # Scale if needed
            if signal_type == 'power' and unit == 'kW' and power_value > 1000:
                power_value = power_value / 1000.0
            return round(power_value, 2)
        except (ValueError, TypeError):
            logger.warning(f"Failed to convert power value: {value}")
            return value
            
    # Percentage values
    elif signal_type == 'percentage' or unit == '%':
        try:
            pct_value = float(value)
            # Ensure in 0-100 range
            if pct_value > 1.0 and pct_value <= 1.0:
                pct_value = pct_value * 100.0
            return round(pct_value, 1)
        except (ValueError, TypeError):
            logger.warning(f"Failed to convert percentage value: {value}")
            return value
            
    # Pass through other values
    return value


def transform_to_binary_state(value: Any, signal_type: str) -> str:
    """
    Transform a value to a binary state (ON/OFF).
    
    Args:
        value: The original value
        signal_type: The type of signal
        
    Returns:
        "ON" or "OFF" string
    """
    # For boolean signal types
    if signal_type in ['boolean', 'bool', 'switch']:
        # Handle string representations
        if isinstance(value, str):
            if value.lower() in ['true', 'on', '1', 'yes']:
                return "ON"
            elif value.lower() in ['false', 'off', '0', 'no']:
                return "OFF"
        
        # Handle numeric and boolean values
        try:
            bool_value = bool(value)
            return "ON" if bool_value else "OFF"
        except (ValueError, TypeError):
            logger.warning(f"Failed to convert to binary state: {value}")
            return "OFF"
            
    # For numeric values, treat non-zero as ON
    if isinstance(value, (int, float)):
        return "ON" if value else "OFF"
        
    # Default to OFF for safety
    return "OFF"


def transform_to_select_state(value: Any, signal_name: str = None) -> str:
    """
    Transform a value to a select state, applying appropriate list lookups for modes and errors.
    
    Args:
        value: The original value
        signal_name: The name of the signal, used to determine signal type
        
    Returns:
        String representation of the state
    """
    # Handle None/unavailable values
    if value is None:
        return "unknown"
    
    # If we have a signal name, check if this is a special value type (mode or error)
    if signal_name:
        from stiebel_control.heatpump.elster_table import (
            get_elster_entry_by_english_name, 
            ElsterType, 
            MODELIST, 
            ERRORLIST
        )
        
        # Get the signal's ElsterType
        elster_entry = get_elster_entry_by_english_name(signal_name)
        
        if elster_entry and elster_entry.type:
            # Try to convert value to int for lookup
            try:
                int_value = int(float(value))
                
                # Check if it's an operating mode
                if elster_entry.type == ElsterType.ET_MODE:
                    return MODELIST.get(int_value, f"Mode {int_value}")
                    
                # Check if it's an error code
                elif elster_entry.type == ElsterType.ET_ERR_CODE:
                    if int_value == 0:
                        return "No Error"
                    return ERRORLIST.get(int_value, f"Error {int_value}")
            except (ValueError, TypeError):
                # If conversion fails, just continue to default behavior
                logger.debug(f"Could not convert {value} to int for {signal_name}")
    
    # Default: ensure we have a string representation
    return str(value)


def transform_from_ha_to_can(value: Any, entity_type: str, signal_type: str = None) -> Any:
    """
    Transform a value from Home Assistant to CAN signal format.
    
    This is used for commands sent from HA to the heat pump.
    
    Args:
        value: The value from Home Assistant
        entity_type: The entity type
        signal_type: The signal type if known
        
    Returns:
        The transformed value suitable for CAN signals
    """
    if entity_type == 'select':
        # Select values are usually passed through
        return value
        
    elif entity_type == 'number':
        # Convert to appropriate numeric type
        try:
            if signal_type in ['integer', 'int']:
                return int(float(value))
            else:
                return float(value)
        except (ValueError, TypeError):
            logger.error(f"Failed to convert number value: {value}")
            return value
            
    elif entity_type in ['switch', 'binary_sensor']:
        # Convert to boolean
        if isinstance(value, str):
            return value.lower() in ['on', 'true', '1', 'yes']
        return bool(value)
        
    # Default pass-through
    return value
