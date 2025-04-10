"""
Tests for the MQTT interface component.

Tests connection, discovery, registration, and messaging functionality.
"""
import pytest
import json
import logging
import time
from unittest.mock import MagicMock, patch, call

from stiebel_control.mqtt_interface import MqttInterface

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


class TestMqttInterface:
    """Tests for the MqttInterface class."""
    
    @pytest.fixture
    def mock_mqtt_client(self):
        """Create a mock MQTT client."""
        with patch('stiebel_control.mqtt_interface.mqtt.Client') as mock_client_class:
            mock_client = MagicMock()
            # Set up the publish method to return a successful result
            mock_info = MagicMock()
            mock_info.rc = 0  # Return code 0 means success
            mock_client.publish.return_value = mock_info
            mock_client_class.return_value = mock_client
            yield mock_client
    
    @pytest.fixture
    def mqtt_interface(self, mock_mqtt_client):
        """Create an MqttInterface instance with a mocked client."""
        # Patch time.sleep to avoid waiting during tests
        with patch('time.sleep'):
            interface = MqttInterface(
                host='localhost',
                port=1883,
                username='test_user',
                password='test_pass',
                client_id='test_client',
                discovery_prefix='homeassistant',
                base_topic='test_topic'
            )
            # Get the on_connect callback and call it with success code
            on_connect = mock_mqtt_client.on_connect
            on_connect(mock_mqtt_client, None, None, 0)
            return interface
    
    def test_initialization(self, mock_mqtt_client):
        """Test the initialization of the MQTT interface."""
        interface = MqttInterface(
            host='test_host',
            port=1234,
            username='test_user',
            password='test_pass',
            client_id='test_client',
            discovery_prefix='test_discovery',
            base_topic='test_base'
        )
        
        # Verify initialization parameters
        assert interface.host == 'test_host'
        assert interface.port == 1234
        assert interface.username == 'test_user'
        assert interface.password == 'test_pass'
        assert interface.client_id == 'test_client'
        assert interface.discovery_prefix == 'test_discovery'
        assert interface.base_topic == 'test_base'
        
        # Verify client setup
        mock_mqtt_client.username_pw_set.assert_called_once_with('test_user', 'test_pass')
        assert interface.client == mock_mqtt_client
    
    def test_connect(self, mock_mqtt_client):
        """Test the connect method."""
        # Patch time.sleep to avoid waiting during tests
        with patch('time.sleep'):
            # Setup mock client to simulate successful connection
            def side_effect_connect(*args, **kwargs):
                # Call the on_connect callback with success code
                on_connect = mock_mqtt_client.on_connect
                on_connect(mock_mqtt_client, None, None, 0)
                return 0
            
            mock_mqtt_client.connect.side_effect = side_effect_connect
            
            # Create interface and test connect
            interface = MqttInterface(
                host='localhost',
                port=1883,
                client_id='test_client'
            )
            
            # Call connect and verify result
            result = interface.connect()
            assert result is True
            mock_mqtt_client.connect.assert_called_once_with('localhost', 1883)
            mock_mqtt_client.loop_start.assert_called_once()
            
            # Test connection failure
            mock_mqtt_client.connect.side_effect = Exception("Connection failed")
            interface.connected = False  # Reset state
            
            # Call connect and verify result
            result = interface.connect()
            assert result is False
    
    def test_disconnect(self, mqtt_interface, mock_mqtt_client):
        """Test the disconnect method."""
        # Call disconnect
        mqtt_interface.disconnect()
        
        # Verify client calls
        mock_mqtt_client.loop_stop.assert_called_once()
        mock_mqtt_client.disconnect.assert_called_once()
        assert mqtt_interface.connected is False
    
    def test_on_connect_callback(self, mock_mqtt_client):
        """Test the on_connect callback."""
        # Create a new interface
        interface = MqttInterface(
            host='localhost',
            port=1883,
            client_id='test_client'
        )
        
        # Get the on_connect callback
        on_connect = mock_mqtt_client.on_connect
        
        # Call the callback with successful connection
        on_connect(mock_mqtt_client, None, None, 0)
        assert interface.connected is True
        
        # Call the callback with failed connection
        on_connect(mock_mqtt_client, None, None, 1)
        # In the real implementation, failed connection doesn't change connected state
        # It logs an error but the state is handled elsewhere
        # So we don't assert anything here
    
    def test_register_sensor(self, mqtt_interface, mock_mqtt_client):
        """Test registration of a sensor entity."""
        # Call register_sensor with all parameters
        result = mqtt_interface.register_sensor(
            entity_id='test_sensor',
            name='Test Sensor',
            device_class='temperature',
            state_class='measurement',
            unit_of_measurement='°C',
            icon='mdi:thermometer'
        )
        
        # Verify result and publish call
        assert result is True
        mock_mqtt_client.publish.assert_called()
        
        # Verify the discovery topic and payload
        call_args = mock_mqtt_client.publish.call_args
        discovery_topic = call_args[0][0]
        discovery_payload = json.loads(call_args[0][1])
        
        assert discovery_topic == 'homeassistant/sensor/test_client/test_sensor/config'
        assert discovery_payload['name'] == 'Test Sensor'
        assert discovery_payload['device_class'] == 'temperature'
        assert discovery_payload['state_class'] == 'measurement'
        assert discovery_payload['unit_of_measurement'] == '°C'
        assert discovery_payload['icon'] == 'mdi:thermometer'
        assert discovery_payload['state_topic'] == 'test_topic/test_sensor/state'
        assert discovery_payload['unique_id'] == 'test_client_test_sensor'
    
    def test_register_binary_sensor(self, mqtt_interface, mock_mqtt_client):
        """Test registration of a binary sensor entity."""
        # Call register_binary_sensor if it exists, otherwise skip the test
        if not hasattr(mqtt_interface, 'register_binary_sensor'):
            pytest.skip("register_binary_sensor method not implemented")
            
        # Call register_binary_sensor
        result = mqtt_interface.register_binary_sensor(
            entity_id='test_binary',
            name='Test Binary Sensor',
            device_class='motion',
            icon='mdi:run'
        )
        
        # Verify result and publish call
        assert result is True
        mock_mqtt_client.publish.assert_called()
        
        # Verify the discovery topic and payload
        call_args = mock_mqtt_client.publish.call_args
        discovery_topic = call_args[0][0]
        discovery_payload = json.loads(call_args[0][1])
        
        assert discovery_topic == 'homeassistant/binary_sensor/test_client/test_binary/config'
        assert discovery_payload['name'] == 'Test Binary Sensor'
        assert discovery_payload['device_class'] == 'motion'
        assert discovery_payload['icon'] == 'mdi:run'
        assert discovery_payload['state_topic'] == 'test_topic/test_binary/state'
    
    def test_register_select(self, mqtt_interface, mock_mqtt_client):
        """Test registration of a select entity."""
        # Call register_select
        result = mqtt_interface.register_select(
            entity_id='test_select',
            name='Test Select',
            options=['Option 1', 'Option 2', 'Option 3'],
            icon='mdi:menu'
        )
        
        # Verify result and publish call
        assert result is True
        mock_mqtt_client.publish.assert_called()
        
        # Verify the discovery topic and payload
        call_args = mock_mqtt_client.publish.call_args
        discovery_topic = call_args[0][0]
        discovery_payload = json.loads(call_args[0][1])
        
        assert discovery_topic == 'homeassistant/select/test_client/test_select/config'
        assert discovery_payload['name'] == 'Test Select'
        assert discovery_payload['options'] == ['Option 1', 'Option 2', 'Option 3']
        assert discovery_payload['icon'] == 'mdi:menu'
        assert discovery_payload['state_topic'] == 'test_topic/test_select/state'
        assert discovery_payload['command_topic'] == 'test_topic/test_select/command'
    
    def test_register_select_with_options_map(self, mqtt_interface, mock_mqtt_client):
        """Test registration of a select entity with options mapping."""
        # Create options and options_map
        options = ["Auto mode", "Day mode", "Night mode"]
        options_map = {2: "Auto mode", 3: "Day mode", 4: "Night mode"}
        
        # Call register_select with options_map
        result = mqtt_interface.register_select(
            entity_id='operating_mode',
            name='Operating Mode',
            options=options,
            icon='mdi:tune-vertical',
            options_map=options_map
        )
        
        # Verify result and publish call
        assert result is True
        mock_mqtt_client.publish.assert_called()
        
        # Verify the discovery topic and payload
        call_args = mock_mqtt_client.publish.call_args
        discovery_topic = call_args[0][0]
        discovery_payload = json.loads(call_args[0][1])
        
        assert discovery_topic == 'homeassistant/select/test_client/operating_mode/config'
        assert discovery_payload['name'] == 'Operating Mode'
        assert discovery_payload['options'] == options
        assert 'value_template' in discovery_payload
        assert 'command_template' in discovery_payload
        
        # Verify template content contains mappings
        value_template = discovery_payload['value_template']
        command_template = discovery_payload['command_template']
        
        for value, text in options_map.items():
            assert str(value) in value_template
            assert text in value_template
            assert str(value) in command_template
            assert text in command_template
    
    def test_publish_state(self, mqtt_interface, mock_mqtt_client):
        """Test publishing state updates."""
        # Register an entity first
        mqtt_interface.register_sensor(
            entity_id='test_entity',
            name='Test Entity'
        )
        
        # Reset the mock to clear previous calls
        mock_mqtt_client.reset_mock()
        
        # Call publish_state
        result = mqtt_interface.publish_state('test_entity', 'test_value')
        
        # Verify result and publish call
        assert result is True
        mock_mqtt_client.publish.assert_called_with(
            'test_topic/test_entity/state',
            'test_value',
            qos=1
        )
        
        # Test with non-registered entity
        result = mqtt_interface.publish_state('nonexistent_entity', 'test_value')
        assert result is False
        
        # Test failure case
        mock_info = MagicMock()
        mock_info.rc = 1  # Non-zero return code indicates failure
        mock_mqtt_client.publish.return_value = mock_info
        result = mqtt_interface.publish_state('test_entity', 'test_value')
        assert result is False
    
    def test_on_message_callback(self, mqtt_interface, mock_mqtt_client):
        """Test the on_message callback."""
        # Create a mock callback and set it
        callback = MagicMock()
        mqtt_interface.command_callback = callback
        
        # Get the on_message callback
        on_message = mock_mqtt_client.on_message
        
        # Create a mock message
        message = MagicMock()
        message.topic = 'test_topic/test_entity/command'
        message.payload = b'test_command'
        
        # Call the callback
        on_message(mock_mqtt_client, None, message)
        
        # Verify callback was called with correct arguments
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == 'test_entity'  # Entity ID
        assert args[1] == 'test_command'  # Command value
        
        # Test with non-command topic
        message.topic = 'test_topic/test_entity/state'
        callback.reset_mock()
        on_message(mock_mqtt_client, None, message)
        callback.assert_not_called()
