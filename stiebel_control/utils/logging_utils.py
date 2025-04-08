"""
Logging utilities for the Stiebel Control package.
"""
import logging
import os
import sys
from typing import Dict, Any, Union
from stiebel_control.config.config_models import LoggingConfig

def configure_logging(config: Union[Dict[str, Any], LoggingConfig]) -> None:
    """
    Configure logging based on provided configuration.
    
    Args:
        config: Logging configuration (either a dictionary or LoggingConfig object)
    """
    # Handle both dictionary and LoggingConfig objects
    if isinstance(config, dict):
        level = config.get('level', 'INFO').upper()
        log_file = config.get('file')
    else:  # LoggingConfig object
        level = config.level.upper()
        log_file = config.file
    
    log_level = getattr(logging, level, logging.INFO)
    
    # Configure the root logger
    handlers = [logging.StreamHandler(sys.stdout)]
    
    # Add file handler if log file is specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        handlers.append(file_handler)
    
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=handlers
    )
    
    # Log the configuration
    logger = logging.getLogger(__name__)
    logger.debug(f"Logging configured with level: {level}")
