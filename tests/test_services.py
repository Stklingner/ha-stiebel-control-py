"""
Tests for the transformation_service and command_handler components.
"""
import pytest
import logging
from unittest.mock import MagicMock, patch
from stiebel_control.services.transformation_service import TransformationService
from stiebel_control.services.command_handler import CommandHandler

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)


class TestTransformationService:
    """Tests for the TransformationService."""
    
    def test_scaling_transformation(self):
        """Test scaling transformation."""
        service = TransformationService()
        
        scale_config = {
            'type': 'scale',
            'factor': 0.1,
            'offset': 5,
            'precision': 1
        }
        
        raw_value = 100
        transformed = service.apply_transformation(raw_value, scale_config)
        inverse = service.apply_inverse_transformation(transformed, scale_config)
        
        logger.info(f"Scale: {raw_value} -> {transformed} -> {inverse}")
        assert abs(transformed - 15.0) < 0.01, "Scaling transformation failed"
        assert abs(raw_value - inverse) < 0.01, "Inverse scaling failed"
    
    def test_mapping_transformation(self):
        """Test mapping transformation."""
        service = TransformationService()
        
        map_config = {
            'type': 'map',
            'mapping': {
                '0': 'Off',
                '1': 'Economy',
                '2': 'Normal',
                '3': 'Comfort'
            }
        }
        
        for i in range(4):
            raw_value = str(i)
            expected_values = ['Off', 'Economy', 'Normal', 'Comfort']
            transformed = service.apply_transformation(raw_value, map_config)
            inverse = service.apply_inverse_transformation(transformed, map_config)
            
            logger.info(f"Map: {raw_value} -> {transformed} -> {inverse}")
            assert transformed == expected_values[i], f"Mapping transformation failed for {raw_value}"
            assert inverse == raw_value, f"Inverse mapping failed for {raw_value}"
    
    def test_boolean_transformation(self):
        """Test boolean transformation."""
        service = TransformationService()
        
        bool_config = {
            'type': 'boolean',
            'true_values': [1, '1', 'true', 'True', True],
            'true_raw': 1,
            'false_raw': 0
        }
        
        # Test true values
        for test_val in [1, '1', 'true', 'True', True]:
            transformed = service.apply_transformation(test_val, bool_config)
            assert transformed is True, f"Boolean transformation failed for {test_val}"
            
            inverse = service.apply_inverse_transformation(transformed, bool_config)
            assert inverse == bool_config['true_raw'], f"Inverse boolean transformation failed for {test_val}"
        
        # Test false values
        for test_val in [0, '0', 'false', 'False', False]:
            transformed = service.apply_transformation(test_val, bool_config)
            assert transformed is False, f"Boolean transformation failed for {test_val}"
            
            inverse = service.apply_inverse_transformation(transformed, bool_config)
            assert inverse == bool_config['false_raw'], f"Inverse boolean transformation failed for {test_val}"


class TestCommandHandler:
    """Tests for the CommandHandler."""
    
    def test_command_handler(self):
        """Test command handler functionality with mocks."""
        # Mock CAN interface
        can_interface = MagicMock()
        can_interface.set_value = MagicMock()
        
        # Create mock entity configuration
        entity_config = {
            'test_entity': {
                'signal': 'TEST_SIGNAL',
                'can_member': 'PUMP',
                'transform': {
                    'type': 'boolean',
                    'true_raw': 42
                }
            }
        }
        
        # Mock transformation_service
        transformation_service = MagicMock()
        transformation_service.apply_inverse_transformation.return_value = 42
        
        # Mock the _resolve_can_id method which would normally use the can_member value
        with patch.object(CommandHandler, '_resolve_can_id', return_value=0x180):
            # Create command handler
            handler = CommandHandler(can_interface, entity_config, transformation_service)
            
            # Test handle_command method
            handler.handle_command('test_entity', 'ON')
            
            # Verify the expected method calls
            transformation_service.apply_inverse_transformation.assert_called_once()
            can_interface.set_value.assert_called_once_with(0x180, 'TEST_SIGNAL', 42)
