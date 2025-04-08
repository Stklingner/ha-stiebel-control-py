"""
Tests for the configuration management system.
"""
import pytest
import logging
import tempfile
import os
import yaml
from stiebel_control.config.config_models import (
    CanConfig,
    MqttConfig, 
    LoggingConfig,
    EntityConfig
)
from stiebel_control.config.config_manager import ConfigManager

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


class TestConfigModels:
    """Tests for the configuration model classes."""
    
    def test_can_config(self):
        """Test the CanConfig class."""
        # Test with custom values
        can_dict = {
            'interface': 'vcan0',
            'bitrate': 50000,
            'mock': True
        }
        can_config = CanConfig.from_dict(can_dict)
        assert can_config.interface == 'vcan0', "CanConfig interface not set correctly"
        assert can_config.bitrate == 50000, "CanConfig bitrate not set correctly"
        assert can_config.mock is True, "CanConfig mock flag not set correctly"
        
        # Test with default values
        empty_can_config = CanConfig.from_dict({})
        assert empty_can_config.interface == 'can0', "Default interface not set correctly"
        assert empty_can_config.bitrate == 20000, "Default bitrate not set correctly"
    
    def test_mqtt_config(self):
        """Test the MqttConfig class."""
        mqtt_dict = {
            'host': 'mqtt.example.com',
            'port': 8883,
            'username': 'testuser',
            'password': 'testpass',
            'client_id': 'test_client',
            'discovery_prefix': 'hass',
            'base_topic': 'test/topic'
        }
        mqtt_config = MqttConfig.from_dict(mqtt_dict)
        assert mqtt_config.host == 'mqtt.example.com', "MQTT host not set correctly"
        assert mqtt_config.port == 8883, "MQTT port not set correctly"
        assert mqtt_config.username == 'testuser', "MQTT username not set correctly"
    
    def test_entity_config(self):
        """Test the EntityConfig class."""
        entity_dict = {
            'entity1': {
                'signal': 'TEMP',
                'type': 'sensor',
                'device_class': 'temperature'
            },
            'entity2': {
                'signal': 'STATUS',
                'type': 'binary_sensor'
            }
        }
        entity_config = EntityConfig.from_dict(entity_dict, dynamic_registration=True)
        assert entity_config.dynamic_registration_enabled is True, "Dynamic registration flag not set"
        assert len(entity_config.entities) == 2, "Incorrect number of entities"
        assert entity_config.get_entity_def('entity1').get('device_class') == 'temperature', "Entity definition incorrect"


class TestConfigManager:
    """Tests for the ConfigManager."""
    
    @pytest.fixture
    def config_files(self):
        """Create temporary config files for testing."""
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.yaml', delete=False) as temp_config:
            config = {
                'can': {
                    'interface': 'vcan0',
                    'bitrate': 50000
                },
                'mqtt': {
                    'host': 'localhost',
                    'port': 1883,
                    'username': 'user',
                    'password': 'pass'
                },
                'logging': {
                    'level': 'DEBUG',
                    'file': 'test.log'
                },
                'update_interval': 30,
                'dynamic_entity_registration': True,
                'entity_config': 'entities.yaml'
            }
            yaml.dump(config, temp_config)
            config_path = temp_config.name
        
        # Create a temporary entity config file
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.yaml', delete=False) as temp_entities:
            entity_config = {
                'temp_sensor': {
                    'signal': 'TEMPERATURE',
                    'can_member': 'PUMP',
                    'type': 'sensor',
                    'device_class': 'temperature'
                }
            }
            yaml.dump(entity_config, temp_entities)
            entity_path = temp_entities.name
        
        # Update the main config to point to the entity config
        with open(config_path, 'r') as f:
            config_data = yaml.safe_load(f)
        
        config_data['entity_config'] = entity_path
        
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        # Yield the paths to the test
        yield (config_path, entity_path)
        
        # Clean up temporary files
        try:
            os.unlink(config_path)
            os.unlink(entity_path)
        except:
            pass
    
    def test_config_manager(self, config_files):
        """Test the ConfigManager with sample configuration files."""
        config_path, _ = config_files
        
        # Test loading the configuration
        config_manager = ConfigManager(config_path)
        
        # Test that configuration objects are created correctly
        can_config = config_manager.get_can_config()
        assert isinstance(can_config, CanConfig), "Can config is not correct type"
        assert can_config.interface == 'vcan0', "CAN interface not loaded correctly"
        
        mqtt_config = config_manager.get_mqtt_config()
        assert isinstance(mqtt_config, MqttConfig), "MQTT config is not correct type"
        assert mqtt_config.host == 'localhost', "MQTT host not loaded correctly"
        
        entity_config = config_manager.get_entity_config()
        assert isinstance(entity_config, EntityConfig), "Entity config is not correct type"
        assert entity_config.dynamic_registration_enabled is True, "Dynamic registration setting incorrect"
        assert 'temp_sensor' in entity_config.entities, "Entity not loaded correctly"
        
        update_interval = config_manager.get_update_interval()
        assert update_interval == 30, "Update interval not loaded correctly"
