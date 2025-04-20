"""
Configuration model classes for the Stiebel Control application.
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List

@dataclass
class CanConfig:
    """Configuration for CAN interface."""
    interface: str = "can0"
    bitrate: int = 20000
    mock: bool = False
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'CanConfig':
        """Create a CanConfig instance from a dictionary."""
        if not config_dict:
            return cls()
            
        return cls(
            interface=config_dict.get('interface', cls.interface),
            bitrate=config_dict.get('bitrate', cls.bitrate),
            mock=config_dict.get('mock', cls.mock)
        )
        
@dataclass
class MqttConfig:
    """Configuration for MQTT connection."""
    host: str = "localhost"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    client_id: str = "stiebel_control"
    discovery_prefix: str = "homeassistant"
    base_topic: str = "stiebel_control"
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'MqttConfig':
        """Create a MqttConfig instance from a dictionary."""
        if not config_dict:
            return cls()
            
        return cls(
            host=config_dict.get('host', cls.host),
            port=config_dict.get('port', cls.port),
            username=config_dict.get('username'),
            password=config_dict.get('password'),
            client_id=config_dict.get('client_id', cls.client_id),
            discovery_prefix=config_dict.get('discovery_prefix', cls.discovery_prefix),
            base_topic=config_dict.get('base_topic', cls.base_topic)
        )
        
@dataclass
class LoggingConfig:
    """Configuration for logging."""
    level: str = "INFO"
    file: Optional[str] = None
    max_size: int = 10485760  # 10 MB
    backup_count: int = 3
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'LoggingConfig':
        """Create a LoggingConfig instance from a dictionary."""
        if not config_dict:
            return cls()
            
        return cls(
            level=config_dict.get('level', cls.level),
            file=config_dict.get('file'),
            max_size=config_dict.get('max_size', cls.max_size),
            backup_count=config_dict.get('backup_count', cls.backup_count)
        )
        
@dataclass
class ControlsConfig:
    """Configuration for interactive controls that change heat pump settings."""
    controls: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'ControlsConfig':
        """Create a ControlsConfig instance from a dictionary."""
        if not config_dict:
            return cls()
        
        return cls(
            controls=config_dict.get('controls', {})
        )
    
    def get_control_def(self, control_id: str) -> Optional[Dict[str, Any]]:
        """Get control definition by ID."""
        return self.controls.get(control_id)

@dataclass
class EntityConfig:
    """Configuration for entities and dynamic registration."""
    entities: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    controls_config: Optional[ControlsConfig] = None
    dynamic_registration_enabled: bool = False
    permissive_signal_handling: bool = False
    ignore_unsolicited_signals: bool = False
    
    @classmethod
    def from_dict(cls, entity_config: Dict[str, Dict[str, Any]], 
                 dynamic_registration: bool,
                 permissive_signal_handling: bool = False,
                 ignore_unsolicited_signals: bool = False,
                 controls_config: Optional[ControlsConfig] = None) -> 'EntityConfig':
        """Create an EntityConfig instance from entity configuration."""
        if not entity_config:
            return cls(dynamic_registration_enabled=dynamic_registration,
                      permissive_signal_handling=permissive_signal_handling,
                      ignore_unsolicited_signals=ignore_unsolicited_signals,
                      controls_config=controls_config)
            
        return cls(
            entities=entity_config.get('entities', {}),
            dynamic_registration_enabled=dynamic_registration,
            permissive_signal_handling=permissive_signal_handling,
            ignore_unsolicited_signals=ignore_unsolicited_signals,
            controls_config=controls_config
        )
        
    def get_entity_def(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """Get entity definition by ID."""
        return self.entities.get(entity_id)
    
    def get_control_def(self, control_id: str) -> Optional[Dict[str, Any]]:
        """Get control definition by ID."""
        if self.controls_config:
            return self.controls_config.get_control_def(control_id)
        return None
