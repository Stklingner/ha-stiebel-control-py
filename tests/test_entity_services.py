"""
Tests for the entity_registration_service and signal_entity_mapper components.
"""
import pytest
import logging
from unittest.mock import MagicMock
from stiebel_control.services.entity_registration_service import EntityRegistrationService
from stiebel_control.services.signal_entity_mapper import SignalEntityMapper
from stiebel_control.heatpump.elster_table import ElsterType

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


class TestSignalEntityMapper:
    """Tests for the SignalEntityMapper."""
    
    def test_entity_mapping(self):
        """Test entity mapping functionality."""
        mapper = SignalEntityMapper()
        
        # Mock CAN interface
        can_interface = MagicMock()
        can_interface.get_can_id_by_name.return_value = 0x180  # PUMP
        
        # Create mock entity configuration
        entity_config = {
            'pump_temperature': {
                'signal': 'TEMPERATURE',
                'can_member': 'PUMP',
                'type': 'sensor',
                'device_class': 'temperature',
                'unit_of_measurement': '°C'
            },
            'manager_status': {
                'signal': 'STATUS',
                'can_member_ids': [0x480],  # MANAGER
                'type': 'binary_sensor'
            }
        }
        
        # Build the entity mapping
        mapper.build_entity_mapping(entity_config, can_interface)
        
        # Test entity lookup
        entity_id = mapper.get_entity_by_signal('TEMPERATURE', 0x180)
        logger.info(f"Entity for TEMPERATURE/0x180: {entity_id}")
        assert entity_id == 'pump_temperature', "Entity lookup by signal failed"
        
        # Test signal lookup
        signal_info = mapper.get_signal_by_entity('manager_status')
        logger.info(f"Signal for manager_status: {signal_info}")
        assert signal_info == ('STATUS', 0x480), "Signal lookup by entity failed"
    
    def test_dynamic_entity_creation(self):
        """Test dynamic entity creation functionality."""
        mapper = SignalEntityMapper()
        
        # Mock CAN interface
        can_interface = MagicMock()
        can_interface.get_can_id_by_name.return_value = 0x180  # PUMP
        
        # Test dynamic entity ID creation
        entity_id = mapper.create_dynamic_entity_id('PRESSURE', 0x180)
        logger.info(f"Dynamic entity ID: {entity_id}")
        assert entity_id == 'pump_pressure', "Dynamic entity ID creation failed"
        
        # Test friendly name creation
        friendly_name = mapper.create_friendly_name('PRESSURE', 0x180)
        logger.info(f"Friendly name: {friendly_name}")
        assert friendly_name == 'Pump Pressure', "Friendly name creation failed"


class TestEntityRegistrationService:
    """Tests for the EntityRegistrationService."""
    
    def test_entity_registration_from_config(self):
        """Test entity registration from configuration."""
        # Mock MQTT interface
        mqtt_interface = MagicMock()
        mqtt_interface.register_sensor.return_value = True
        
        service = EntityRegistrationService(mqtt_interface)
        
        # Test entity registration from config
        entity_def = {
            'type': 'sensor',
            'name': 'Test Temperature',
            'device_class': 'temperature',
            'unit_of_measurement': '°C'
        }
        
        success = service.register_entity_from_config('test_temp', entity_def)
        assert success, "Entity registration from config failed"
        assert 'test_temp' in service.get_registered_entities(), "Entity not added to registered set"
        
        # Test sensor registration was called with right parameters
        mqtt_interface.register_sensor.assert_called_with(
            entity_id='test_temp',
            name='Test Temperature',
            device_class='temperature', 
            state_class=None,
            unit_of_measurement='°C',
            icon=None
        )
    
    def test_dynamic_entity_registration(self):
        """Test dynamic entity registration."""
        # Mock MQTT interface
        mqtt_interface = MagicMock()
        mqtt_interface.register_sensor.return_value = True
        
        service = EntityRegistrationService(mqtt_interface)
        
        # Test dynamic entity registration
        success = service.register_dynamic_entity(
            entity_id='pump_pressure',
            friendly_name='Pump Pressure',
            signal_type=ElsterType.ET_PERCENT,
            signal_name='PRESSURE',
            value=42
        )
        
        assert success, "Dynamic entity registration failed"
        assert 'pump_pressure' in service.get_registered_entities(), "Dynamic entity not added to registered set"
    
    def test_entity_registration_checks(self):
        """Test entity registration checking functionality."""
        # Mock MQTT interface
        mqtt_interface = MagicMock()
        mqtt_interface.register_sensor.return_value = True
        
        service = EntityRegistrationService(mqtt_interface)
        
        # Register an entity
        entity_def = {
            'type': 'sensor',
            'name': 'Test Temperature',
            'device_class': 'temperature',
            'unit_of_measurement': '°C'
        }
        service.register_entity_from_config('test_temp', entity_def)
        
        # Test duplicate detection
        assert service.is_entity_registered('test_temp'), "Entity registration check failed"
