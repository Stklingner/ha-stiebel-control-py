"""
Configuration management for the Stiebel Control package.
"""
import os
import yaml
import logging
from typing import Dict, Any, Optional, List
from stiebel_control.config.config_models import (
    CanConfig, 
    MqttConfig, 
    LoggingConfig, 
    EntityConfig
)

logger = logging.getLogger(__name__)

# Singleton instance
_config_manager_instance = None

class ConfigManager:
    """
    Manages loading, validation, and access to configuration settings.
    Uses specialized configuration classes for different subsystems.
    """
    
    def __init__(self, service_config_path: str):
        """
        Initialize the configuration manager.
        
        Args:
            service_config_path: Path to the service configuration file
        """
        self.service_config_path = service_config_path
        self.reload()
        
        logger.info(f"Configuration manager initialized with service config from {service_config_path}")
        
        # Register as singleton instance
        global _config_manager_instance
        _config_manager_instance = self
        
    def reload(self) -> bool:
        """
        Reload configuration from files.
        
        Returns:
            bool: True if reloaded successfully, False otherwise
        """
        try:
            # Reload service config
            self.service_config = self._load_yaml(self.service_config_path)
            
            # Reload entity config
            entity_config_path = self.service_config.get('entity_config')
            if entity_config_path:
                if not os.path.isabs(entity_config_path):
                    base_dir = os.path.dirname(os.path.abspath(self.service_config_path))
                    entity_config_path = os.path.join(base_dir, entity_config_path)
                self.raw_entity_config = self._load_yaml(entity_config_path)
            else:
                self.raw_entity_config = {}
                
            # Reinitialize specialized configs
            self._init_specialized_configs()
            return True
            
        except Exception as e:
            logger.error(f"Error reloading configuration: {e}")
            return False
            
    def _load_yaml(self, file_path: str) -> Dict[str, Any]:
        """
        Load a YAML file.
        
        Args:
            file_path: Path to the YAML file
            
        Returns:
            Parsed YAML content as dictionary
        """
        try:
            with open(file_path, 'r') as file:
                return yaml.safe_load(file) or {}
        except Exception as e:
            logger.error(f"Error loading configuration from {file_path}: {e}")
            return {}
            
    @classmethod
    def get_instance(cls) -> Optional['ConfigManager']:
        """
        Get the singleton instance of the ConfigManager.
        
        Returns:
            ConfigManager instance or None if not initialized
        """
        global _config_manager_instance
        return _config_manager_instance
    
    @classmethod
    def initialize(cls, service_config_path: str) -> 'ConfigManager':
        """
        Initialize the singleton instance of ConfigManager.
        
        Args:
            service_config_path: Path to service configuration file
            
        Returns:
            The singleton ConfigManager instance
        """
        global _config_manager_instance
        if _config_manager_instance is None:
            _config_manager_instance = cls(service_config_path)
        return _config_manager_instance
    
    def _init_specialized_configs(self):
        # Initialize specialized configuration objects
        self.can_config = CanConfig.from_dict(self.service_config.get('can', {}))
        self.mqtt_config = MqttConfig.from_dict(self.service_config.get('mqtt', {}))
        self.logging_config = LoggingConfig.from_dict(self.service_config.get('logging', {}))
        self.entity_config = EntityConfig.from_dict(
            self.raw_entity_config,
            self.service_config.get('dynamic_entity_registration', False)
        )
        
        # Store other common settings
        self.update_interval = int(self.service_config.get('update_interval', 60))
        
    def get_can_config(self) -> CanConfig:
        """
        Get CAN interface configuration.
        
        Returns:
            CAN configuration object
        """
        return self.can_config
        
    def get_mqtt_config(self) -> MqttConfig:
        """
        Get MQTT configuration.
        
        Returns:
            MQTT configuration object
        """
        return self.mqtt_config
        
    def get_logging_config(self) -> LoggingConfig:
        """
        Get logging configuration.
        
        Returns:
            Logging configuration object
        """
        return self.logging_config
        
    def get_entity_config(self) -> EntityConfig:
        """
        Get entity configuration.
        
        Returns:
            Entity configuration object
        """
        return self.entity_config
        
    def get_update_interval(self) -> int:
        """
        Get update interval in seconds.
        
        Returns:
            Update interval in seconds
        """
        return self.update_interval
        
    @staticmethod
    def get_instance() -> Optional['ConfigManager']:
        """
        Get the singleton instance of the ConfigManager.
        
        Returns:
            The ConfigManager instance, or None if not initialized
        """
        return _config_manager_instance
        
    def get_raw_config(self, section: str) -> Dict[str, Any]:
        """
        Get raw configuration for a specific section.
        Useful for accessing configuration sections that don't have specialized models.
        
        Args:
            section: Configuration section name
            
        Returns:
            Raw configuration dictionary for the section
        """
        return self.service_config.get(section, {})
